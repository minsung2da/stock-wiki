"""RRF k=60 hybrid retrieval core over the whole-body narrative tables (SC#4, D-02).

This is the data-dependent heart of ``hybrid_search``. It fuses two rankings via
**Reciprocal Rank Fusion at a FIXED k=60** (SC#4 — :data:`_RRF_K` is a module
constant, never a parameter):

- **dense** — pgvector HNSW cosine (``<=>``) over the ``halfvec(1024)`` embedding
  column of each narrative table (``filings.body_embedding`` /
  ``news.body_embedding`` / ``notes.content_emb``), against the bge-m3 query
  vector.
- **sparse** — VectorChord-BM25 ``bm25_catalog.search_bm25query`` over the
  ``bm25_tokens INT[]`` column, against the mecab-ko query token vector. BM25
  scores are NEGATIVE (more negative = more relevant), so the ``ROW_NUMBER`` orders
  ``ASC NULLS LAST`` (Pitfall 4) — sign is irrelevant once it becomes a rank.

Veto #8 — each candidate is one WHOLE filing / article / note row (no chunk join;
there is no chunk table in v2.0). Veto #6 / SC#4 — only the three NARRATIVE tables
are ever queried; a ``source_filter`` naming ``ohlcv`` / ``macro_series`` /
``decision_cards`` raises :class:`~mcp_v2.errors.InvalidArgument` HERE (at the
retrieval layer, not only at the tool boundary).

SQL discipline (Veto #7 / SC#3 AST guard): every statement is a module-level
``text()`` constant bound with parameters — NO f-string SQL. NULL filter binds are
CAST-guarded (Pitfall 3 — psycopg3 cannot infer the type of a param that only
appears in ``$x IS NULL``). The ``SET hnsw.iterative_scan = 'relaxed_order'``
session GUC is issued per connection (Pitfall 2 — filtered HNSW recall in pgvector
0.8).

References-not-blobs (D-02): the public :func:`hybrid_search` returns
:class:`~mcp_v2.models.SearchHit`\\ s carrying only ``source_type`` + ``id_or_path``
+ ``rrf_score`` + a short WRAP+FLAG ``snippet`` (D-03/SC#5) — NEVER the whole
``body_md``. The agent re-fetches the full body via ``get_filing`` / ``get_note``
for the hits it cares about.

Ported and adapted from the v1.0 archive ``src/stock_mcp/search_core.py`` (RRF CTE,
session GUC, NULL-cast guards, ``_format_vec``); the archive fused over the deleted
``chunks``/``documents`` tables — this rewrite fuses over the whole-body
``filings``/``news``/``notes`` per Veto #8.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from . import injection
from .embedding import encode_query
from .errors import DataBackendError, InvalidArgument
from .models import SearchHit
from .tokenizer import tokenize_ko

__all__ = ["hybrid_search", "make_snippet"]

# --------------------------------------------------------------------------- #
# Locks / constants
# --------------------------------------------------------------------------- #
#: RRF fusion constant — SC#4 LOCKED. NEVER expose this as a tool parameter; it is
#: hard-coded as the literal ``60`` inside the fusion tail of every SQL constant
#: below (kept in sync with this name for readability).
_RRF_K = 60

#: Default number of fused hits returned (D-04 top-10).
_DEFAULT_LIMIT = 10

#: Per-side candidate cap before fusion (archive used 50). Bounds the dense/sparse
#: scan so RRF works on a manageable candidate set.
_CANDIDATE_LIMIT = 50

#: Default snippet head when there is no literal query-term match offset.
_SNIPPET_HEAD = 300

#: The three NARRATIVE tables hybrid_search may touch (SC#4). Anything else is a
#: forbidden source.
_NARRATIVE_SOURCES: frozenset[str] = frozenset({"filings", "news", "notes"})

#: Numeric / structured tables that hybrid_search must NEVER search (Veto #6, SC#4).
#: Naming any of these in source_filter is a fault, not an empty result.
_FORBIDDEN_SOURCES: frozenset[str] = frozenset({"ohlcv", "macro_series", "decision_cards"})

#: Map the singular source_type tag (carried on each SearchHit) to the plural
#: table/source_filter name. The tool layer + tests use these source_type tags.
_TYPE_TO_TABLE: dict[str, str] = {
    "filing": "filings",
    "news": "news",
    "note": "notes",
}

# --------------------------------------------------------------------------- #
# SQL constants — bind params only (Veto #7, SC#3 AST guard); k=60 literal inline
# --------------------------------------------------------------------------- #
_SET_ITERATIVE_SCAN = text("SET hnsw.iterative_scan = 'relaxed_order'")  # Pitfall 2

# filings: candidate = one whole filing row (rcept_no). filed_at is the date axis.
# dense uses body_embedding (halfvec); sparse uses bm25_tokens via search_bm25query.
# NULL filter binds are CAST-guarded (Pitfall 3). k=60 is the inline literal.
_HYBRID_FILINGS_SQL = text(
    """
    WITH dense AS (
        SELECT f.rcept_no AS id,
               ROW_NUMBER() OVER (
                   ORDER BY f.body_embedding <=> CAST(:qvec AS halfvec)
               ) AS rk
          FROM filings f
         WHERE f.body_embedding IS NOT NULL
           AND (CAST(:corp_code AS char(8)) IS NULL OR f.corp_code = CAST(:corp_code AS char(8)))
           AND (CAST(:date_from AS date) IS NULL OR f.filed_at >= CAST(:date_from AS date))
           AND (CAST(:date_to   AS date) IS NULL OR f.filed_at <  CAST(:date_to   AS date))
         ORDER BY f.body_embedding <=> CAST(:qvec AS halfvec)
         LIMIT 50
    ),
    sparse AS (
        SELECT f.rcept_no AS id,
               ROW_NUMBER() OVER (
                   ORDER BY bm25_catalog.search_bm25query(
                       (f.bm25_tokens)::bm25_catalog.bm25vector,
                       bm25_catalog.to_bm25query(
                           'ix_filings_bm25'::regclass,
                           CAST(:qtoks AS int[])::bm25_catalog.bm25vector
                       )
                   ) ASC NULLS LAST
               ) AS rk
          FROM filings f
         WHERE f.bm25_tokens IS NOT NULL
           AND (CAST(:corp_code AS char(8)) IS NULL OR f.corp_code = CAST(:corp_code AS char(8)))
           AND (CAST(:date_from AS date) IS NULL OR f.filed_at >= CAST(:date_from AS date))
           AND (CAST(:date_to   AS date) IS NULL OR f.filed_at <  CAST(:date_to   AS date))
         LIMIT 50
    )
    SELECT COALESCE(dense.id, sparse.id) AS id,
           COALESCE(1.0/(60 + dense.rk), 0)
         + COALESCE(1.0/(60 + sparse.rk), 0) AS rrf_score
      FROM dense
      FULL OUTER JOIN sparse USING (id)
     ORDER BY rrf_score DESC
     LIMIT :top_k
    """
)

# news: candidate = one whole article row (id). published_at is the date axis.
_HYBRID_NEWS_SQL = text(
    """
    WITH dense AS (
        SELECT CAST(n.id AS text) AS id,
               ROW_NUMBER() OVER (
                   ORDER BY n.body_embedding <=> CAST(:qvec AS halfvec)
               ) AS rk
          FROM news n
         WHERE n.body_embedding IS NOT NULL
           AND (CAST(:corp_code AS char(8)) IS NULL OR n.corp_code = CAST(:corp_code AS char(8)))
           AND (CAST(:date_from AS date) IS NULL OR n.published_at >= CAST(:date_from AS date))
           AND (CAST(:date_to   AS date) IS NULL OR n.published_at <  CAST(:date_to   AS date))
         ORDER BY n.body_embedding <=> CAST(:qvec AS halfvec)
         LIMIT 50
    ),
    sparse AS (
        SELECT CAST(n.id AS text) AS id,
               ROW_NUMBER() OVER (
                   ORDER BY bm25_catalog.search_bm25query(
                       (n.bm25_tokens)::bm25_catalog.bm25vector,
                       bm25_catalog.to_bm25query(
                           'ix_news_bm25'::regclass,
                           CAST(:qtoks AS int[])::bm25_catalog.bm25vector
                       )
                   ) ASC NULLS LAST
               ) AS rk
          FROM news n
         WHERE n.bm25_tokens IS NOT NULL
           AND (CAST(:corp_code AS char(8)) IS NULL OR n.corp_code = CAST(:corp_code AS char(8)))
           AND (CAST(:date_from AS date) IS NULL OR n.published_at >= CAST(:date_from AS date))
           AND (CAST(:date_to   AS date) IS NULL OR n.published_at <  CAST(:date_to   AS date))
         LIMIT 50
    )
    SELECT COALESCE(dense.id, sparse.id) AS id,
           COALESCE(1.0/(60 + dense.rk), 0)
         + COALESCE(1.0/(60 + sparse.rk), 0) AS rrf_score
      FROM dense
      FULL OUTER JOIN sparse USING (id)
     ORDER BY rrf_score DESC
     LIMIT :top_k
    """
)

# notes: candidate = one whole note row (path). content_emb is the dense column;
# notes carry no date axis (updated_at exists but is not a filed/published date),
# so date_range is not applied to notes — only corp_code filters.
_HYBRID_NOTES_SQL = text(
    """
    WITH dense AS (
        SELECT nt.path AS id,
               ROW_NUMBER() OVER (
                   ORDER BY nt.content_emb <=> CAST(:qvec AS halfvec)
               ) AS rk
          FROM notes nt
         WHERE nt.content_emb IS NOT NULL
           AND (CAST(:corp_code AS char(8)) IS NULL OR nt.corp_code = CAST(:corp_code AS char(8)))
         ORDER BY nt.content_emb <=> CAST(:qvec AS halfvec)
         LIMIT 50
    ),
    sparse AS (
        SELECT nt.path AS id,
               ROW_NUMBER() OVER (
                   ORDER BY bm25_catalog.search_bm25query(
                       (nt.bm25_tokens)::bm25_catalog.bm25vector,
                       bm25_catalog.to_bm25query(
                           'ix_notes_bm25'::regclass,
                           CAST(:qtoks AS int[])::bm25_catalog.bm25vector
                       )
                   ) ASC NULLS LAST
               ) AS rk
          FROM notes nt
         WHERE nt.bm25_tokens IS NOT NULL
           AND (CAST(:corp_code AS char(8)) IS NULL OR nt.corp_code = CAST(:corp_code AS char(8)))
         LIMIT 50
    )
    SELECT COALESCE(dense.id, sparse.id) AS id,
           COALESCE(1.0/(60 + dense.rk), 0)
         + COALESCE(1.0/(60 + sparse.rk), 0) AS rrf_score
      FROM dense
      FULL OUTER JOIN sparse USING (id)
     ORDER BY rrf_score DESC
     LIMIT :top_k
    """
)

# Per-source body fetch for snippet extraction (id-keyed). Returned bodies never
# leave this module whole — only a make_snippet window does (D-02).
_BODY_FILINGS_SQL = text("SELECT body_md AS body FROM filings WHERE rcept_no = :id")
_BODY_NEWS_SQL = text("SELECT body_md AS body FROM news WHERE id = CAST(:id AS bigint)")
_BODY_NOTES_SQL = text("SELECT content_md AS body FROM notes WHERE path = :id")

# source_type tag → (RRF SQL, body-fetch SQL).
_SOURCE_SQL: dict[str, tuple[Any, Any]] = {
    "filing": (_HYBRID_FILINGS_SQL, _BODY_FILINGS_SQL),
    "news": (_HYBRID_NEWS_SQL, _BODY_NEWS_SQL),
    "note": (_HYBRID_NOTES_SQL, _BODY_NOTES_SQL),
}

# source_type tag → the injection-wrap source attribute (provenance).
_WRAP_SOURCE: dict[str, str] = {
    "filing": "dart",
    "news": "news",
    "note": "note",
}


def _format_vec(vec: list[float] | tuple[float, ...]) -> str:
    """Format a Python float sequence as a halfvec literal ``'[x,y,...]'``.

    The literal is bound through ``CAST(:qvec AS halfvec)`` in the SQL — the values
    are numbers from the embedder, never user text (no injection surface).
    """
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def make_snippet(body: str, query_terms: list[str], width: int = 200) -> str:
    """Extract a ±``width`` match-window snippet from ``body`` (Discretion #2).

    Finds the earliest offset of any literal ``query_terms`` token and returns a
    window of ``[offset-width, offset+width]``. When no term matches (a pure-dense
    hit), falls back to the first :data:`_SNIPPET_HEAD` chars. The result is always
    ≤ ``2*width`` (~400) chars — well under the token budget (D-02
    references-not-blobs). It is wrapped via :func:`injection.wrap_untrusted` by the
    caller, never returned raw to the model.
    """
    offsets = [body.find(t) for t in query_terms if t and body.find(t) >= 0]
    lo = min(offsets) if offsets else -1
    if lo < 0:
        return body[:_SNIPPET_HEAD]
    start = max(0, lo - width)
    return body[start : lo + width]


def _validate_source_filter(source_filter: str | None) -> list[str]:
    """Validate ``source_filter`` and return the list of source_type tags to run.

    ``None`` → all three narrative sources. A forbidden numeric/structured source
    (``ohlcv`` / ``macro_series`` / ``decision_cards``) → :class:`InvalidArgument`
    (SC#4, Veto #6 — at the retrieval layer). An unknown source → InvalidArgument.
    Both the plural table name (``filings``) and the singular type tag (``filing``)
    are accepted for a single source.
    """
    if source_filter is None:
        return ["filing", "news", "note"]

    sf = source_filter.strip().lower()
    if sf in _FORBIDDEN_SOURCES:
        raise InvalidArgument(
            f"hybrid_search searches narrative tables only "
            f"(filings/news/notes); '{sf}' is forbidden (SC#4, Veto #6)"
        )
    # Accept plural table name or singular type tag.
    plural_to_type = {v: k for k, v in _TYPE_TO_TABLE.items()}
    if sf in plural_to_type:
        return [plural_to_type[sf]]
    if sf in _SOURCE_SQL:
        return [sf]
    raise InvalidArgument(f"source_filter must be one of filings/news/notes (or None); got '{sf}'")


def hybrid_search(
    engine: Engine,
    query: str,
    source_filter: str | None = None,
    date_range: tuple[str | None, str | None] | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> list[SearchHit]:
    """RRF k=60 hybrid retrieval over the whole-body narrative tables (SC#4, D-02).

    Embeds ``query`` (bge-m3) + tokenizes it (mecab-ko), runs the per-source dense +
    BM25 + RRF(k=60) CTE on each requested narrative table, fuses the per-source
    results by ``rrf_score`` and returns the top ``limit`` as :class:`SearchHit`\\ s.
    Each hit carries a WRAP+FLAG ``snippet`` (D-03/SC#5) — NEVER the whole body
    (D-02). An empty corpus / no match → ``[]`` (the tool turns this into an empty
    ``SearchResult``, D-01).

    Args:
        engine: the SQLAlchemy engine (live Postgres at migration ≥ 0008).
        query: the natural-language search query (untrusted text).
        source_filter: ``None`` (all of filings/news/notes) or one narrative source
            name. Naming a numeric/structured table raises ``InvalidArgument``.
        date_range: optional ``(from, to)`` ISO-8601 date strings. ``from`` is
            inclusive, ``to`` is exclusive (half-open). Applied to filings.filed_at
            and news.published_at; notes carry no date axis.
        limit: max fused hits (D-04 default 10). ``< 1`` raises ``InvalidArgument``.

    Raises:
        InvalidArgument: bad ``source_filter`` (forbidden/unknown), or ``limit`` < 1.
        DataBackendError: the DB is unreachable or a query failed.
    """
    if limit < 1:
        raise InvalidArgument("limit must be >= 1")

    sources = _validate_source_filter(source_filter)

    date_from: str | None = None
    date_to: str | None = None
    if date_range is not None:
        date_from, date_to = date_range

    qvec_lit = _format_vec(encode_query(query))
    qtoks = tokenize_ko(query)
    # BM25 needs at least one query token; with none, the sparse side simply
    # contributes nothing (search_bm25query over an empty query vector) — the dense
    # side still ranks. An empty INT[] is a valid bm25query input.

    base_params: dict[str, Any] = {
        "qvec": qvec_lit,
        "qtoks": qtoks,
        "corp_code": None,
        "date_from": date_from,
        "date_to": date_to,
        "top_k": limit,
    }

    # (source_type, id, rrf_score) across all requested narrative sources.
    fused: list[tuple[str, str, float]] = []
    try:
        with engine.connect() as conn:
            conn.execute(_SET_ITERATIVE_SCAN)  # Pitfall 2 — per-session GUC
            for src in sources:
                rrf_sql, _body_sql = _SOURCE_SQL[src]
                params = dict(base_params)
                if src == "note":
                    # notes have no date axis — drop the date binds for clarity.
                    params["date_from"] = None
                    params["date_to"] = None
                ranked = conn.execute(rrf_sql, params).all()
                for r in ranked:
                    fused.append((src, str(r.id), float(r.rrf_score)))

            # Global RRF-score order; cap at the requested limit.
            fused.sort(key=lambda t: t[2], reverse=True)
            top = fused[:limit]

            # Fetch the body per top hit and build a snippet (D-02 — body never
            # leaves this module whole).
            hits: list[SearchHit] = []
            for src, ident, score in top:
                _rrf_sql, body_sql = _SOURCE_SQL[src]
                body_row = conn.execute(body_sql, {"id": ident}).first()
                body = body_row.body if body_row is not None else ""
                snippet = make_snippet(body, qtoks_terms(query))
                flags = [h["pattern_id"] for h in injection.detect(snippet)]
                wrapped = injection.wrap_untrusted(
                    snippet, _WRAP_SOURCE[src], _safe_ref(src, ident)
                )
                hits.append(
                    SearchHit(
                        source_type=src,
                        id_or_path=ident,
                        rrf_score=score,
                        snippet=wrapped,
                        injection_suspected=bool(flags),
                        injection_flags=flags,
                    )
                )
    except InvalidArgument:
        raise
    except Exception as e:  # noqa: BLE001 — map any backend failure to DataBackendError
        raise DataBackendError(f"hybrid_search query failed: {str(e)[:200]}") from e

    return hits


def qtoks_terms(query: str) -> list[str]:
    """Whitespace-split surface terms of ``query`` for snippet match-window finding.

    The snippet window is found by literal substring offset in the (Korean) body,
    so it uses the raw surface tokens of the query — NOT the mecab-ko integer token
    ids (those are for the BM25 index, not for ``str.find``). Empty/blank tokens are
    dropped.
    """
    return [t for t in query.split() if t.strip()]


def _safe_ref(source_type: str, ident: str) -> str:
    """Derive an injection ``_SAFE_ATTR``-valid ref id from a source + identifier.

    ``rcept_no`` (digits) and ``news.id`` (digits) already pass ``^[A-Za-z0-9_:.-]+$``;
    a note ``path`` carries ``/`` separators, so non-safe chars collapse to ``_`` and
    a ``note:`` prefix is prepended (mirrors ``tools/note.py``). Filing/news get a
    ``<source>:<id>`` provenance ref.
    """
    if source_type == "note":
        safe = "".join(c if c.isalnum() or c in "_:.-" else "_" for c in ident)
        return f"note:{safe}"
    return f"{source_type}:{ident}"
