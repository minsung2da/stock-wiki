"""Phase 7 GRAPH-02: stock graph snapshot — vault-wide graphifyy snapshot.

Calls graphifyy 0.7.5 Python API in-process (CONTEXT D-10). Stages source
files into a symlink farm at vault/.graphify-staging/<KST_DATE>/ scoped per
config raw_windows_days (D-12), invokes graphify deep+directed (D-11), writes
{index.html, graph.json, GRAPH_REPORT.md} into vault/graph/<KST_DATE>/ (D-13),
prunes dated dirs beyond N=14 by mtime (D-14), cleans staging.

KST: directory names are plain ISO ``YYYY-MM-DD``. The date is computed in
Asia/Seoul (RESEARCH §Pitfall 6 — avoid spaces and non-ASCII in dir names).

Failure policy: on graphify exception, the partial output dir is preserved
for postmortem but staging is unconditionally removed in ``finally``.

NB: This module imports graphify lazily inside ``_run_graphify`` so importing
``src.graph.snapshot`` in environments without the ``graph`` dependency group
(e.g., the ingest CI guard suite) does not error.

API mapping vs probe-findings.md (graphifyy 0.7.5):

* ``graphify.detect.detect`` — PRESENT
* ``graphify.extract.collect_files`` / ``graphify.extract.extract`` — PRESENT
* ``graphify.build.build_from_json`` — PRESENT (accepts ``directed=True`` kw)
* ``graphify.cluster.cluster`` / ``score_all`` — PRESENT
* ``graphify.analyze.god_nodes`` / ``surprising_connections`` /
  ``suggest_questions`` — PRESENT (suggest_questions requires
  ``community_labels``)
* ``graphify.report.generate`` — PRESENT (requires ``community_labels``)
* ``graphify.export.to_json`` / ``to_html`` — PRESENT (to_html accepts
  ``community_labels`` and ``member_counts``; we derive both from cluster
  output as Plan 01 SUMMARY directs).
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
    """Run a vault-wide graphify snapshot.

    Returns:
        Path to ``vault/graph/<KST_DATE>/`` (created on entry).

    Args:
        repo_root: project root containing the ``vault/`` subtree.
        config: parsed ``config/graphify.json`` (top-level dict).
        dry_run: build staging only, skip graphify call.
    """
    today = _today_kst()
    out_dir = repo_root / "vault" / "graph" / today
    staging = repo_root / "vault" / ".graphify-staging" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    # Local import so ``src.graph.window`` substitution in tests stays cheap
    # and the module remains importable when the ``graph`` group is absent.
    from src.graph.window import build_staging

    try:
        link_counts = build_staging(repo_root, staging, config)
        logger.info("staging built: %s", link_counts)
        if not dry_run:
            _run_graphify(staging, out_dir)
        _prune_old(out_dir.parent, KEEP_DATED_DIRS)
        return out_dir
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _run_graphify(input_dir: Path, out_dir: Path) -> None:
    """In-process graphify call. Symbol set matches probe-findings.md for 0.7.5.

    AST-only path (RESEARCH §Pattern 3 caveat — no LLM subagent dispatch in
    unattended ``stock graph snapshot``).
    """
    # Lazy imports — keep ``graph`` group optional for non-snapshot envs.
    from graphify.analyze import (
        god_nodes,
        suggest_questions,
        surprising_connections,
    )
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.detect import detect
    from graphify.export import to_html, to_json
    from graphify.extract import collect_files, extract
    from graphify.report import generate

    detection = detect(Path(input_dir))
    files = collect_files(detection)
    extraction = extract(files, mode="deep", semantic=False)

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
    report_text = generate(
        G,
        communities,
        cohesion,
        labels,
        gods,
        surprises,
        detection,
        {"input": 0, "output": 0},
        str(input_dir),
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
