"""notes-ingest collector — D-05 (Phase 3 Wave-0).

Loads the user's on-disk thesis memos under ``notes/private/**/*.md`` into the
``notes`` Postgres table so ``hybrid_search`` (Plan 06) covers all three
narrative sources (filings / news / notes). Local-only: ``notes/private/`` is
gitignored and NEVER committed (D-05; CLAUDE.md Veto #9 — the only on-disk
narrative source that survives the LLM-wiki shutdown).

Orchestration mirrors ``collectors.krx.collect_krx``:
- per-file try/except isolation (one bad memo never aborts the run),
- ``stats = {total, inserted, updated, skipped, failed[]}``,
- a structured ``collector_run_complete`` stderr log, and
- a best-effort ``record_collector_run(engine, "notes_ingest", ...)`` row.

``"notes_ingest"`` is already an allowed ``collector_runs.source`` (owned by
Plan 03-01's ``_ALLOWED_SOURCES`` + migration 0008 CHECK). This module does NOT
edit ``shared.run_log``.

Embedding/tokenization use the ``mcp_v2`` leaves (kept as siblings so the
Wave-0 backfill can import them outside the MCP server context). The first
embed loads bge-m3 (~2GB download then cached). ``portfolio.md`` is config, not
a thesis memo, so it is excluded from ingest.

This module imports neither ``anthropic`` nor ``openai`` (COLL-07 CI guard):
embeddings are computed in-process via sentence-transformers (CLAUDE.md §4).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from collectors.notes_ingest import db_writer
from mcp_v2.embedding import get_default_embedder
from mcp_v2.tokenizer import tokenize_ko
from shared.run_log import record_collector_run

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from mcp_v2.embedding import Embedder

_log = logging.getLogger(__name__)

__all__ = ["ingest_notes"]

# portfolio.md is the collector scope source (parsed by Portfolio.load), not a
# narrative thesis memo — exclude it from the searchable notes corpus.
_EXCLUDED_NAMES: frozenset[str] = frozenset({"portfolio.md"})


def ingest_notes(
    *,
    engine: Engine,
    repo_root: Path = Path("."),
    embedder: Embedder | None = None,
) -> dict[str, Any]:
    """Ingest ``<repo_root>/notes/private/**/*.md`` into the ``notes`` table.

    Args:
        engine: SQLAlchemy engine (REQUIRED — no DB = no work).
        repo_root: repo root holding ``notes/private/`` (default cwd).
        embedder: an injectable :class:`mcp_v2.embedding.Embedder` (tests pass a
            deterministic stub to avoid the bge-m3 download). Defaults to the
            process-wide lazy bge-m3 singleton.

    Returns:
        ``{total, inserted, updated, skipped, failed[], elapsed_ms}``.

    Raises:
        RuntimeError: if ``engine`` is None.
    """
    if engine is None:
        raise RuntimeError("ingest_notes requires a DB engine")

    start = time.monotonic()
    rr = Path(repo_root)
    notes_dir = rr / "notes" / "private"
    files = (
        [
            p
            for p in sorted(notes_dir.rglob("*.md"))
            if p.is_file() and p.name not in _EXCLUDED_NAMES
        ]
        if notes_dir.exists()
        else []
    )

    stats: dict[str, Any] = {
        "total": len(files),
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "failed": [],
    }

    emb = embedder if embedder is not None else get_default_embedder()

    for f in files:
        rel_path = f.relative_to(rr).as_posix()
        try:
            content_md = f.read_text(encoding="utf-8")
            embedding = emb.encode([content_md])[0]
            bm25_tokens = tokenize_ko(content_md)
            outcome = db_writer.upsert_note(
                engine,
                path=rel_path,
                content_md=content_md,
                embedding=embedding,
                bm25_tokens=bm25_tokens,
            )
            stats[outcome] += 1
        except Exception as exc:  # noqa: BLE001 — per-file isolation
            _log.exception("notes ingest failed for %s", rel_path)
            stats["failed"].append({"doc": rel_path, "error": str(exc)})

    stats["elapsed_ms"] = int((time.monotonic() - start) * 1000)

    _log.info(
        "collector_run_complete",
        extra={
            "source": "notes_ingest",
            "stats": stats,
            "elapsed_ms": stats["elapsed_ms"],
            "extra": None,
        },
    )
    # Best-effort observability row (source already allowed by Plan 03-01).
    record_collector_run(engine, "notes_ingest", stats, stats["elapsed_ms"])
    return stats
