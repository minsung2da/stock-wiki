"""The single ``search`` MCP tool exposed by stock-mcp (MCP-01, MCP-02; D-22).

Registers ``search`` on the shared ``mcp`` instance using FastMCP 2.x's
``@mcp.tool()`` decorator. The tool delegates to
``stock_mcp.search_core.hybrid_search`` and shapes the result as a
``SearchResult`` Pydantic model (or a structured error dict on failure).

Errors NEVER raise past this boundary — stdout is the MCP JSON-RPC protocol
stream and a raw traceback would corrupt it (D-21).
"""

from __future__ import annotations

import time
from typing import Literal

from fastmcp import FastMCP

from db.engine import get_engine

from ..errors import ErrorCode, StructuredError, to_error_response
from ..logging import log_tool_call
from ..models import DateRange, SearchHit, SearchResult
from ..search_core import hybrid_search

__all__ = ["mcp", "search"]


mcp = FastMCP("stock-mcp")


_HIT_FIELDS = ("vault_path", "excerpt", "frontmatter_ref", "score", "source", "doc_id")


def _hits_to_models(raw_hits: list[dict]) -> list[SearchHit]:
    return [SearchHit(**{k: h[k] for k in _HIT_FIELDS}) for h in raw_hits]


def search(
    query: str,
    ticker: str | None = None,
    date_range: DateRange | None = None,
    source: Literal["dart", "news", "note"] | None = None,
    mode: Literal["hybrid", "semantic", "bm25"] = "hybrid",
    top_k: int = 10,
) -> SearchResult | dict:
    """Hybrid retrieval over the stock-wiki vault (JUDGE-04, RET-01/02/03).

    Runs dense (bge-m3 via pgvector HNSW) + BM25 (VectorChord-BM25) in a
    single SQL CTE and fuses the two rankings via Reciprocal Rank Fusion at
    k=60. Structured filters (ticker, date_range, source) apply BEFORE the
    vector scan so recall is preserved on narrow slices.

    ### Behavior contract
    - ``query``: required natural-language question (Korean or English).
    - ``ticker``: 6-digit KRX ticker; resolved to a canonical corp_code via
      ``resolve_entity`` so ticker recycling (Pitfall 3) is handled.
    - ``date_range``: half-open ``[start, end)`` ISO-8601 interval filtering
      ``documents.first_seen_at``.
    - ``source``: one of ``"dart"``, ``"news"``, ``"note"``.
    - ``mode``: ``"hybrid"`` (default), ``"semantic"`` (dense only), or
      ``"bm25"`` (sparse only).
    - ``top_k``: 1-50; values > 50 are silently clamped.

    ### Response shape
    Returns a ``SearchResult`` with ``hits`` — each hit carries:
    - ``vault_path``: citable path within the vault (required for JUDGE-04)
    - ``excerpt``: chunk text wrapped in ``<vault_excerpt>`` delimiters so
      downstream LLMs can distinguish trusted prompt from retrieved content.
    - ``frontmatter_ref``: source / corp_code / section_path / first_seen_at
    - ``score``: fused RRF score (higher is better)
    - ``source``, ``doc_id``

    ### Errors
    On failure returns ``{"error": {"code": ..., "message": ...,
    "details": {...}}}`` — never raises. Codes include ``INVALID_TICKER``,
    ``DB_UNAVAILABLE``, ``EMBEDDING_FAILED``, ``INTERNAL``.

    ### Performance budget
    p95 latency < 5s, serialized response < 8k tokens at top_k=10.
    """
    t0 = time.perf_counter()
    args_log = {
        "query": query,
        "ticker": ticker,
        "date_range": (date_range.model_dump() if date_range else None),
        "source": source,
        "mode": mode,
        "top_k": top_k,
    }
    try:
        engine = get_engine()
        raw_hits = hybrid_search(
            engine,
            query,
            ticker=ticker,
            date_range=date_range,
            source=source,
            mode=mode,
            top_k=top_k,
        )
        result = SearchResult(
            hits=_hits_to_models(raw_hits),
            query=query,
            mode=mode,
            total=len(raw_hits),
        )
        latency = int((time.perf_counter() - t0) * 1000)
        result_json = result.model_dump_json()
        log_tool_call("search", args_log, latency, len(result_json) // 4)
        return result
    except StructuredError as e:
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(e)
        log_tool_call("search", args_log, latency, 0, error=err["error"])
        return err
    except Exception as e:  # noqa: BLE001 — D-21 catch-all
        wrapped = StructuredError(ErrorCode.INTERNAL, str(e)[:200])
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(wrapped)
        log_tool_call("search", args_log, latency, 0, error=err["error"])
        return err


# Register the callable as an MCP tool. Keeping the decorator as a separate
# call (rather than @mcp.tool()) preserves ``search`` as a plain function so
# tests + direct callers can invoke it without going through FunctionTool.
mcp.tool()(search)
