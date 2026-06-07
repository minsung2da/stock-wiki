"""``hybrid_search`` — the narrative-only RRF k=60 retrieval tool (SC#4, D-02/D-04).

The 10th and final locked read-side tool. Delegates the heavy lifting to
:func:`mcp_v2.retrieval.hybrid_search` (the RRF k=60 dense+BM25 core over the
whole-body ``filings``/``news``/``notes`` tables) and wraps the returned
:class:`~mcp_v2.models.SearchHit`\\ s in a :class:`~mcp_v2.models.SearchResult`.

Contract:

- **SC#4 / Veto #6** — narrative tables ONLY. A ``source_filter`` naming a
  numeric/structured table (``ohlcv`` / ``macro_series`` / ``decision_cards``)
  raises :class:`~mcp_v2.errors.InvalidArgument` at this boundary (and again,
  defensively, inside ``retrieval.hybrid_search``).
- **D-02 references-not-blobs** — each hit carries ``source_type`` + ``id_or_path``
  + ``rrf_score`` + a short WRAP+FLAG ``snippet`` (D-03/SC#5), NEVER the whole
  body. The agent re-fetches the full text via ``get_filing`` / ``get_note``.
- **D-04** — default ``limit=10`` (top-10 after RRF k=60 fusion).
- **D-01** — an empty corpus / no match → ``SearchResult(hits=[])`` (not an error).

Registration mirrors the 03-04/03-05 template: the public name stays a plain
in-process callable and is registered on the shared ``mcp`` via the call form
``mcp.tool(...)(fn)`` (the ``@mcp.tool`` decorator would replace the name with a
non-callable ``FunctionTool``).
"""

from __future__ import annotations

from mcp.types import ToolAnnotations

from db.engine import get_engine

from .. import retrieval
from .._mcp import mcp
from ..errors import InvalidArgument
from ..models import SearchResult

__all__ = ["hybrid_search"]

# Numeric/structured tables hybrid_search must never search (SC#4, Veto #6). The
# retrieval layer also enforces this; rejecting at the tool boundary gives the
# caller a clear, early error before any DB work.
_FORBIDDEN_SOURCES: frozenset[str] = frozenset({"ohlcv", "macro_series", "decision_cards"})


def hybrid_search(
    query: str,
    source_filter: str | None = None,
    date_range: tuple[str | None, str | None] | None = None,
    limit: int = 10,
) -> SearchResult:
    """Hybrid RRF k=60 narrative search over filings/news/notes (SC#4, D-02/D-04).

    Fuses pgvector dense ranking with VectorChord-BM25 sparse ranking via
    Reciprocal Rank Fusion at a FIXED k=60, over the WHOLE-body narrative tables
    only (Veto #8 — one candidate is one whole filing/article/note). Returns the
    top ``limit`` hits as references + bounded snippets (D-02), each snippet wrapped
    in the ``<untrusted>`` delimiter and injection-flagged (D-03/SC#5).

    Args:
        query: the natural-language search query (untrusted text).
        source_filter: ``None`` to search all of filings/news/notes, or a single
            narrative source name (``"filings"`` / ``"news"`` / ``"notes"``). Naming
            a numeric/structured table raises ``InvalidArgument`` (SC#4, Veto #6).
        date_range: optional ``(from, to)`` ISO-8601 date strings (``from``
            inclusive, ``to`` exclusive). Applied to filings/news; notes have no
            date axis.
        limit: max hits after RRF fusion (D-04 default 10). ``< 1`` raises
            ``InvalidArgument``.

    Returns:
        SearchResult: ``hits`` is the RRF-ordered list (possibly empty, D-01).

    Raises:
        InvalidArgument: ``source_filter`` names a forbidden/unknown source, or
            ``limit`` < 1.
        DataBackendError: the DB is unreachable or a query failed.
    """
    # SC#4 boundary check: forbidden numeric/structured source → loud, early.
    if source_filter is not None and source_filter.strip().lower() in _FORBIDDEN_SOURCES:
        raise InvalidArgument(
            f"hybrid_search searches narrative tables only "
            f"(filings/news/notes); '{source_filter}' is forbidden (SC#4, Veto #6)"
        )

    hits = retrieval.hybrid_search(
        get_engine(),
        query,
        source_filter=source_filter,
        date_range=date_range,
        limit=limit,
    )
    return SearchResult(hits=hits)


# Register on the shared mcp via the call form ``mcp.tool(...)(fn)`` (NOT the
# ``@mcp.tool`` decorator — that replaces the name with a non-callable
# FunctionTool, breaking in-process callers; see Plan 03-04 SUMMARY).
_READ_ONLY = ToolAnnotations(readOnlyHint=True)
mcp.tool(annotations=_READ_ONLY)(hybrid_search)
