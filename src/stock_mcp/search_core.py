"""Hybrid dense+BM25 retrieval core (RET-01, RET-02, RET-03; D-09/10/11/12/13/14; JUDGE-04).

The canonical CTE fuses pgvector HNSW dense ranking with VectorChord-BM25
sparse ranking via Reciprocal Rank Fusion at k=60 (D-09). Structured filters
(ticker → corp_code via resolve_entity, source, date_range) apply BEFORE the
vector scan on the ``documents`` table (D-13, D-14). The HNSW session GUC
``hnsw.iterative_scan = 'relaxed_order'`` is set per connection to preserve
filtered-scan recall in pgvector 0.8.

SQL discipline: every SQL literal is a module-level constant bound through
``text()`` + named parameters. Zero f-string interpolation of user values.

Excerpts returned to MCP clients are wrapped in ``<vault_excerpt>`` delimiters
(D-17) so downstream LLM contexts can identify untrusted retrieval spans.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from ingest.embedder import encode_query
from ingest.injection_defense import wrap_untrusted
from ingest.tokenizer import tokenize_ko

from db.entity import resolve_entity  # isort: skip

from .errors import ErrorCode, StructuredError
from .models import DateRange

__all__ = ["hybrid_search", "build_filter_clause"]


# D-10: top_k clamp. Defends against pathological oversized responses.
_MAX_TOP_K = 50
_DEFAULT_EXCERPT = 400
# D-09: RRF fusion constant.
_RRF_K = 60

_TICKER_RE = re.compile(r"^[0-9]{6}$")
_CORP_CODE_RE = re.compile(r"^[0-9]{8}$")


# --- Canonical SQL templates (bind params only) ----------------------------

# SET hnsw.iterative_scan = 'relaxed_order'   <-- D-13 session GUC
_SESSION_SET_ITERATIVE_SCAN = sa.text("SET hnsw.iterative_scan = 'relaxed_order'")

# Hybrid (dense + BM25 + RRF k=60). documents.corp_code is filtered DIRECTLY —
# migration 0002 added the column + btree index precisely so Plan 05 can
# bypass a LEFT JOIN entities / EXISTS probe (RET-02).
# All NULLable filter bind params are explicitly cast to their column
# types — psycopg3 + Postgres cannot infer the type of a parameter that
# only appears in ``$x IS NULL`` predicates (AmbiguousParameter $2).
_FILTER_WHERE = """
          AND (CAST(:corp_code AS char(8)) IS NULL OR d.corp_code = CAST(:corp_code AS char(8)))
          AND (CAST(:source    AS text)    IS NULL OR d.source    = CAST(:source    AS text))
          AND (CAST(:date_from AS date)    IS NULL OR d.first_seen_at >= CAST(:date_from AS date))
          AND (CAST(:date_to   AS date)    IS NULL OR d.first_seen_at <  CAST(:date_to   AS date))
"""

_HYBRID_SQL_TEMPLATE = """
    WITH dense AS (
        SELECT c.id AS chunk_id,
               ROW_NUMBER() OVER (
                   ORDER BY c.embedding <=> CAST(:qvec AS vector)
               ) AS rk
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE TRUE
          __FILTER__
        ORDER BY c.embedding <=> CAST(:qvec AS vector)
        LIMIT 50
    ),
    sparse AS (
        SELECT c.id AS chunk_id,
               ROW_NUMBER() OVER (
                   ORDER BY bm25_catalog.search_bm25query(
                       (c.bm25_tokens)::bm25_catalog.bm25vector,
                       bm25_catalog.to_bm25query(
                           'ix_chunks_bm25'::regclass,
                           CAST(:qtoks AS int[])::bm25_catalog.bm25vector
                       )
                   ) ASC NULLS LAST
               ) AS rk
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.bm25_tokens IS NOT NULL
          __FILTER__
        LIMIT 50
    )
    SELECT COALESCE(dense.chunk_id, sparse.chunk_id) AS chunk_id,
           COALESCE(1.0/(60 + dense.rk), 0)
         + COALESCE(1.0/(60 + sparse.rk), 0) AS rrf_score
    FROM dense
    FULL OUTER JOIN sparse USING (chunk_id)
    ORDER BY rrf_score DESC
    LIMIT :top_k
"""

_SEMANTIC_SQL_TEMPLATE = """
    WITH dense AS (
        SELECT c.id AS chunk_id,
               ROW_NUMBER() OVER (
                   ORDER BY c.embedding <=> CAST(:qvec AS vector)
               ) AS rk
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE TRUE
          __FILTER__
        ORDER BY c.embedding <=> CAST(:qvec AS vector)
        LIMIT :top_k
    )
    SELECT chunk_id, 1.0/(60 + rk) AS rrf_score
    FROM dense
    ORDER BY rrf_score DESC
"""

_BM25_SQL_TEMPLATE = """
    WITH sparse AS (
        SELECT c.id AS chunk_id,
               ROW_NUMBER() OVER (
                   ORDER BY bm25_catalog.search_bm25query(
                       (c.bm25_tokens)::bm25_catalog.bm25vector,
                       bm25_catalog.to_bm25query(
                           'ix_chunks_bm25'::regclass,
                           CAST(:qtoks AS int[])::bm25_catalog.bm25vector
                       )
                   ) ASC NULLS LAST
               ) AS rk
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.bm25_tokens IS NOT NULL
          __FILTER__
        ORDER BY bm25_catalog.search_bm25query(
            (c.bm25_tokens)::bm25_catalog.bm25vector,
            bm25_catalog.to_bm25query(
                'ix_chunks_bm25'::regclass,
                CAST(:qtoks AS int[])::bm25_catalog.bm25vector
            )
        ) ASC NULLS LAST
        LIMIT :top_k
    )
    SELECT chunk_id, 1.0/(60 + rk) AS rrf_score
    FROM sparse
    ORDER BY rrf_score DESC
"""

_HYBRID_SQL = sa.text(_HYBRID_SQL_TEMPLATE.replace("__FILTER__", _FILTER_WHERE))
_SEMANTIC_SQL = sa.text(_SEMANTIC_SQL_TEMPLATE.replace("__FILTER__", _FILTER_WHERE))
_BM25_SQL = sa.text(_BM25_SQL_TEMPLATE.replace("__FILTER__", _FILTER_WHERE))

_CHUNK_FETCH_SQL = sa.text(
    """
    SELECT c.id        AS chunk_id,
           c.text      AS text,
           c.section_path,
           d.id        AS document_id,
           d.vault_path,
           d.source,
           d.corp_code,
           d.first_seen_at
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE c.id = ANY(:cids)
    """
)


def _format_vec(vec: list[float] | tuple[float, ...]) -> str:
    """Format a Python float sequence as a pgvector literal ('[x,y,...]')."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def build_filter_clause(
    ticker: str | None,
    date_range: DateRange | None,
    source: str | None,
    engine: Engine,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Produce the bind-parameter dict for the hybrid/semantic/bm25 SQL.

    Performs ticker validation (regex ^[0-9]{6}$) and ticker → corp_code
    resolution via ``resolve_entity`` (D-14). Raises
    ``StructuredError(INVALID_TICKER)`` if the ticker shape is wrong or the
    entity cannot be resolved.
    """
    corp_code: str | None = None
    if ticker is not None:
        if not _TICKER_RE.match(ticker):
            raise StructuredError(
                ErrorCode.INVALID_TICKER,
                "ticker must be 6 ASCII digits",
            )
        lookup_date: date | None = as_of
        if lookup_date is None and date_range is not None and date_range.end:
            try:
                lookup_date = date.fromisoformat(date_range.end)
            except ValueError:
                lookup_date = None
        resolved = resolve_entity(engine, ticker, as_of=lookup_date)
        if resolved is None:
            raise StructuredError(
                ErrorCode.INVALID_TICKER,
                "ticker did not resolve to any entity",
            )
        corp_code = resolved.corp_code

    date_from: str | None = None
    date_to: str | None = None
    if date_range is not None:
        date_from = date_range.start
        date_to = date_range.end

    return {
        "corp_code": corp_code,
        "source": source,
        "date_from": date_from,
        "date_to": date_to,
    }


def hybrid_search(
    engine: Engine,
    query: str,
    ticker: str | None = None,
    date_range: DateRange | None = None,
    source: str | None = None,
    mode: str = "hybrid",
    top_k: int = 10,
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Run dense + BM25 + RRF(k=60) retrieval and return enriched hits.

    Each returned dict conforms to the SearchHit shape: ``vault_path``,
    ``excerpt`` (wrapped in ``<vault_excerpt>``), ``frontmatter_ref``,
    ``score``, ``source``, ``doc_id``.
    """
    top_k = max(1, min(top_k, _MAX_TOP_K))

    params = build_filter_clause(ticker, date_range, source, engine, as_of)

    qvec_tuple = encode_query(query)
    qvec_lit = _format_vec(qvec_tuple)
    qtoks = tokenize_ko(query)

    # BM25 needs at least one query token; on empty tokens fall back to dense.
    effective_mode = mode
    if effective_mode in ("bm25", "hybrid") and not qtoks:
        if effective_mode == "bm25":
            return []
        effective_mode = "semantic"

    if effective_mode == "hybrid":
        sql = _HYBRID_SQL
        bind = {"qvec": qvec_lit, "qtoks": qtoks, **params, "top_k": top_k}
    elif effective_mode == "semantic":
        sql = _SEMANTIC_SQL
        bind = {"qvec": qvec_lit, **params, "top_k": top_k}
    elif effective_mode == "bm25":
        sql = _BM25_SQL
        bind = {"qtoks": qtoks, **params, "top_k": top_k}
    else:
        raise StructuredError(
            ErrorCode.INTERNAL,
            "mode must be one of hybrid | semantic | bm25",
        )

    with engine.connect() as conn:
        conn.execute(_SESSION_SET_ITERATIVE_SCAN)  # D-13 session GUC
        ranked = conn.execute(sql, bind).all()
        if not ranked:
            return []
        score_by_cid = {r.chunk_id: float(r.rrf_score) for r in ranked}
        rows = conn.execute(
            _CHUNK_FETCH_SQL,
            {"cids": list(score_by_cid.keys())},
        ).all()

    rows_by_cid = {r.chunk_id: r for r in rows}
    hits: list[dict[str, Any]] = []
    # Per-source trust level mapping (D-19).  dart public filings are trusted;
    # news and user notes are semi_trusted.  A Phase 4 follow-up should add a
    # documents.trust_level column populated at ingest time so individual
    # document overrides are honoured.
    _SOURCE_TRUST: dict[str, str] = {
        "dart": "trusted",
        "news": "semi_trusted",
        "note": "semi_trusted",
    }
    # Preserve RRF ordering from the ranked result.
    for r in ranked:
        row = rows_by_cid.get(r.chunk_id)
        if row is None:
            continue
        raw_excerpt = (row.text or "")[:_DEFAULT_EXCERPT]
        doc_id_hex = (row.document_id or "")[:8]
        # wrap_untrusted enforces doc_id ∈ ^[a-f0-9]{1,32}$; fall back to
        # a deterministic sanitized slug when the stored id is outside that
        # charset (shouldn't occur for sha256 ids, but defensive).
        if not doc_id_hex or not all(ch in "0123456789abcdef" for ch in doc_id_hex):
            doc_id_hex = "0" * 8
        trust = _SOURCE_TRUST.get(row.source or "", "semi_trusted")
        excerpt = wrap_untrusted(
            raw_excerpt,
            source=(row.source or "unknown"),
            trust_level=trust,
            doc_id=doc_id_hex,
        )
        hits.append(
            {
                # Plan-specified raw shape (H2): chunk_id, rrf_score, vault_path,
                # text, source, document_id.
                "chunk_id": int(r.chunk_id),
                "rrf_score": float(score_by_cid[r.chunk_id]),
                "vault_path": row.vault_path,
                "text": row.text,
                "source": row.source,
                "document_id": row.document_id,
                # SearchHit-facing fields (consumed by the tool layer).
                "excerpt": excerpt,
                "frontmatter_ref": {
                    "source": row.source,
                    "corp_code": row.corp_code,
                    "section_path": row.section_path,
                    "first_seen_at": (row.first_seen_at.isoformat() if row.first_seen_at else None),
                },
                "score": float(score_by_cid[r.chunk_id]),
                "doc_id": row.document_id,
            }
        )
    return hits
