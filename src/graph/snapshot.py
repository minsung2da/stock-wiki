"""Phase 7.1 GRAPH-02: stock graph snapshot — SQL-driven graphify snapshot.

Phase 7 had this module call ``graphify.detect / collect_files / extract`` on a
markdown vault; that path returned empty ``nodes``/``links`` (Phase 7 UAT
gap-1). Phase 7.1 replaces it with an SQL adapter
(``src.graph.sql_to_graph.build_extraction``) that reads the live ``edges`` +
``entities`` + ``documents`` tables — populated by Phase 2/3/7 collectors and
``src/ingest/edges.py`` — into a graphify ``build_from_json``-compatible
extraction dict, then runs the graphify cluster/analyze/export pipeline.

Output is unchanged: ``vault/graph/<KST_DATE>/{index.html, graph.json,
GRAPH_REPORT.md}``. KST date naming, 14-day prune, and dry-run semantics are
preserved per CONTEXT D-13/D-14.

KST: directory names are plain ISO ``YYYY-MM-DD`` (RESEARCH §Pitfall 6 —
avoid spaces and non-ASCII in dir names).

Failure policy: on graphify exception, the partial output dir is preserved
for postmortem.

NB: This module imports graphify lazily inside ``_run_graphify`` so importing
``src.graph.snapshot`` in environments without the ``graph`` dependency group
(e.g., the ingest CI guard suite) does not error.

API mapping (graphifyy 0.7.5, KEPT after Phase 7.1):

* ``graphify.build.build_from_json`` — PRESENT (accepts ``directed=True`` kw)
* ``graphify.cluster.cluster`` / ``score_all`` — PRESENT
* ``graphify.analyze.god_nodes`` / ``surprising_connections`` /
  ``suggest_questions`` — PRESENT (suggest_questions requires
  ``community_labels``)
* ``graphify.report.generate`` — PRESENT (requires ``community_labels``)
* ``graphify.export.to_json`` / ``to_html`` — PRESENT

DROPPED (no longer imported — gap-1 fix):

* ``graphify.detect.detect``
* ``graphify.extract.collect_files`` / ``graphify.extract.extract``
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo

    KST = ZoneInfo("Asia/Seoul")
except ImportError:  # pragma: no cover - Python <3.9 fallback
    KST = timezone(timedelta(hours=9))

KEEP_DATED_DIRS = 14  # CONTEXT D-14
logger = logging.getLogger(__name__)


def _today_kst() -> str:
    """Return the wall-clock KST date as plain ISO ``YYYY-MM-DD``."""
    return datetime.now(KST).date().isoformat()


def snapshot(repo_root: Path, config: dict, *, dry_run: bool = False) -> Path:
    """Run a vault-wide graphify snapshot from the SQL edge index.

    Returns:
        Path to ``vault/graph/<KST_DATE>/`` (created on entry).

    Args:
        repo_root: project root containing the ``vault/`` subtree.
        config: reserved for future extensions; currently unused (Phase 7.1
            removed the staging-window logic — SQL is the data source).
        dry_run: skip the graphify call but still create the output directory
            and prune old dirs.
    """
    del config  # Phase 7.1: no staging windowing — SQL is the data source.
    today = _today_kst()
    out_dir = repo_root / "vault" / "graph" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    if not dry_run:
        _run_graphify(out_dir)
    _prune_old(out_dir.parent, KEEP_DATED_DIRS)
    # Defensive: if a stale staging dir from a Phase 7 run still lives next
    # to the dated output, remove it so the layout matches the Phase 7.1
    # contract (CONTEXT D-13).
    staging = repo_root / "vault" / ".graphify-staging" / today
    shutil.rmtree(staging, ignore_errors=True)
    return out_dir


def _run_graphify(out_dir: Path) -> None:
    """SQL → graph snapshot.

    Phase 7.1 replaces graphifyy 0.7.5's AST extraction path
    (``detect/collect_files/extract``) which produced an empty graph on
    markdown vaults (gap-1, Phase 7 HUMAN-UAT.md). Reads SQL edges + entities
    + documents via ``sql_to_graph.build_extraction``; ``graphify.detect`` and
    ``graphify.extract`` are no longer imported.
    """
    # Lazy imports — keep ``graph`` group optional for non-snapshot envs.
    from graphify.analyze import (
        god_nodes,
        suggest_questions,
        surprising_connections,
    )
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.export import to_html, to_json
    from graphify.report import generate

    # Tolerate both import styles: ``src.graph.*`` (tests run from repo root)
    # and ``graph.*`` (CLI run via ``uv run stock`` puts ``src/`` on sys.path).
    try:
        from src.graph.sql_to_graph import build_extraction
    except ModuleNotFoundError:  # pragma: no cover - exercised under CLI path
        from graph.sql_to_graph import build_extraction
    try:
        from src.db.engine import get_engine
    except ModuleNotFoundError:  # pragma: no cover - exercised under CLI path
        from db.engine import get_engine

    extraction = build_extraction(get_engine())
    logger.info(
        "sql_to_graph extraction: %d nodes, %d edges",
        len(extraction.get("nodes", [])),
        len(extraction.get("edges", [])),
    )

    G = build_from_json(extraction, directed=True)
    communities = cluster(G)
    cohesion = score_all(G, communities)
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)

    # Plan 01 SUMMARY: cluster() returns indices only; derive labels +
    # member_counts ourselves before generate / to_html.
    labels = {cid: f"Community {cid}" for cid in communities}
    member_counts = {cid: len(members) for cid, members in communities.items()}

    questions = suggest_questions(G, communities, labels)

    to_json(G, communities, str(out_dir / "graph.json"), force=True)
    to_html(
        G,
        communities,
        str(out_dir / "index.html"),
        community_labels=labels,
        member_counts=member_counts,
    )
    # detection placeholder — graphify.report.generate's "Corpus Check"
    # branch reads ``warning`` (short-circuit) OR ``total_files`` /
    # ``total_words`` (counter branch). We populate both so the report renders
    # cleanly regardless of which branch graphify version picks. ``source``
    # records the actual data plane (SQL) for postmortem readability.
    n_doc_nodes = sum(1 for n in extraction.get("nodes", []) if n.get("type") == "document")
    detection = {
        "source": "sql:edges+entities+documents",
        "warning": (
            "Phase 7.1 SQL-driven snapshot — corpus stats from edge index, "
            "not file walk."
        ),
        "total_files": n_doc_nodes,
        "total_words": 0,
        "input_tokens": int(extraction.get("input_tokens", 0)),
        "output_tokens": int(extraction.get("output_tokens", 0)),
    }
    report_text = generate(
        G,
        communities,
        cohesion,
        labels,
        gods,
        surprises,
        detection,
        {"input": 0, "output": 0},
        "db://stock",
        suggested_questions=questions,
    )
    (out_dir / "GRAPH_REPORT.md").write_text(report_text, encoding="utf-8")


def _prune_old(graph_dir: Path, keep: int) -> int:
    """Keep the ``keep`` most-recent dated subdirs by mtime; remove the rest.

    Skips entries starting with ``.`` (e.g., ``.graphify-staging`` if
    accidentally placed alongside dated dirs).
    """
    if not graph_dir.exists():
        return 0
    dated = [d for d in graph_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    dated.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for d in dated[keep:]:
        shutil.rmtree(d, ignore_errors=True)
        removed += 1
    return removed
