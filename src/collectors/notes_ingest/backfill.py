"""Narrative embedding/tsv/bm25 backfill — D-05 (Phase 3 Wave-0).

Phase 1 collectors INSERT ``filings``/``news`` rows but leave ``body_embedding``
(halfvec) and ``bm25_tokens`` (INT[]) NULL (and ``body_tsv`` unpopulated). Plan
06 ``hybrid_search`` returns empty for every query until those columns carry
non-NULL values. This job backfills them for existing rows:

  * embed ``body_md`` → ``body_embedding = CAST(:vec AS halfvec)`` (bge-m3),
  * tokenize ``body_md`` → ``bm25_tokens = :toks`` (mecab-ko content POS),
  * populate ``body_tsv = to_tsvector('simple', body_md)`` — NEVER ``'korean'``
    (PG17 has no korean tsearch config; RESEARCH Pitfall 1).

Hard Veto #6 reminder: only the narrative tables (filings/news, and notes via
the ingest job) are embedded. ohlcv/macro/fundamentals are pure numeric and are
NEVER touched here.

Hard Veto #7: every statement is a module-level ``text()`` constant bound with
params. The halfvec value is a literal string CAST in SQL (no f-string SQL).

Hard Veto #8: ``body_md`` is embedded/tokenized whole (subject to bge-m3's 8K
context truncation on the dense side); BM25 carries Korean keyword recall over
the full token array. No chunking.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from collectors.notes_ingest.db_writer import format_halfvec_literal
from mcp_v2.embedding import get_default_embedder
from mcp_v2.tokenizer import tokenize_ko

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from mcp_v2.embedding import Embedder

_log = logging.getLogger(__name__)

__all__ = ["backfill_narrative"]


# Rows missing either the dense or sparse signal are backfill candidates.
_SELECT_FILINGS_SQL = text(
    """
    SELECT rcept_no, body_md
    FROM filings
    WHERE body_embedding IS NULL OR bm25_tokens IS NULL
    ORDER BY rcept_no
    """
)
_SELECT_NEWS_SQL = text(
    """
    SELECT id, body_md
    FROM news
    WHERE body_embedding IS NULL OR bm25_tokens IS NULL
    ORDER BY id
    """
)

_UPDATE_FILINGS_SQL = text(
    """
    UPDATE filings
    SET body_embedding = CAST(:vec AS halfvec),
        bm25_tokens    = :toks,
        body_tsv       = to_tsvector('simple', body_md)
    WHERE rcept_no = :r
    """
)
_UPDATE_NEWS_SQL = text(
    """
    UPDATE news
    SET body_embedding = CAST(:vec AS halfvec),
        bm25_tokens    = :toks,
        body_tsv       = to_tsvector('simple', body_md)
    WHERE id = :id
    """
)


def _backfill_table(
    engine: Engine,
    *,
    select_sql,
    update_sql,
    id_field: str,
    update_id_key: str,
    emb: Embedder,
    batch_size: int,
) -> int:
    """Embed+tokenize a NULL-signal table's bodies; return count updated."""
    with engine.begin() as conn:
        rows = conn.execute(select_sql).all()

    updated = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        bodies = [r.body_md for r in batch]
        vectors = emb.encode(bodies)
        with engine.begin() as conn:
            for row, vec in zip(batch, vectors, strict=True):
                conn.execute(
                    update_sql,
                    {
                        "vec": format_halfvec_literal(vec),
                        "toks": tokenize_ko(row.body_md),
                        update_id_key: getattr(row, id_field),
                    },
                )
                updated += 1
    return updated


def backfill_narrative(
    *,
    engine: Engine,
    batch_size: int = 16,
    embedder: Embedder | None = None,
) -> dict[str, Any]:
    """Backfill embeddings/tokens/tsv for filings + news rows missing them.

    Args:
        engine: SQLAlchemy engine (REQUIRED).
        batch_size: bge-m3 encode batch size (rows per embed call).
        embedder: injectable :class:`mcp_v2.embedding.Embedder` (tests pass a
            deterministic stub). Defaults to the lazy bge-m3 singleton.

    Returns:
        ``{filings_updated, news_updated, total_updated, elapsed_ms}``.

    Raises:
        RuntimeError: if ``engine`` is None.
    """
    if engine is None:
        raise RuntimeError("backfill_narrative requires a DB engine")

    start = time.monotonic()
    emb = embedder if embedder is not None else get_default_embedder()

    filings_updated = _backfill_table(
        engine,
        select_sql=_SELECT_FILINGS_SQL,
        update_sql=_UPDATE_FILINGS_SQL,
        id_field="rcept_no",
        update_id_key="r",
        emb=emb,
        batch_size=batch_size,
    )
    news_updated = _backfill_table(
        engine,
        select_sql=_SELECT_NEWS_SQL,
        update_sql=_UPDATE_NEWS_SQL,
        id_field="id",
        update_id_key="id",
        emb=emb,
        batch_size=batch_size,
    )

    elapsed_ms = int((time.monotonic() - start) * 1000)
    stats = {
        "filings_updated": filings_updated,
        "news_updated": news_updated,
        "total_updated": filings_updated + news_updated,
        "elapsed_ms": elapsed_ms,
    }
    _log.info("narrative_backfill_complete", extra={"stats": stats})
    return stats
