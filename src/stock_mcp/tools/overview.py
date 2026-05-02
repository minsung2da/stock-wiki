"""``get_ticker_overview`` MCP tool — composite Claude-judgment context bundle (MCP-03, JUDGE-01).

Single-call axis aggregator that composes three Wave-2 reads — recent events,
portfolio meta row, related notes — into one ``OverviewResponse``. Three
Phase-10 placeholder axes (``valuation``, ``supply_demand``, ``private_thesis``)
are typed ``T | None = None`` and always serialized as ``None`` in Phase 6
(D-01 stable signature; Phase 10 fills the fields without breaking callers).

Truncation (D-22): a soft 7000-token cap (safety margin under the 8000-token
hard ceiling per D-19) drives a priority-ordered drop loop —
``private_thesis < valuation < supply_demand < portfolio < related_notes <
events`` — and ``events`` is hard-capped at 20 rows (D-02). The
``truncation_applied`` list records every axis that was shrunk or dropped.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from db.engine import get_engine
from db.entity import resolve_entity

from ..errors import ErrorCode, StructuredError, to_error_response
from ..logging import log_tool_call
from ..models import EventRow, OverviewResponse, PortfolioRow, SearchHit
from ..search_core import hybrid_search
from .events import get_recent_events
from .portfolio import get_portfolio_state
from .search import mcp

__all__ = ["TARGET_TOKENS", "EVENTS_CAP", "get_ticker_overview"]


# D-19 soft cap (under 8k hard ceiling) — drives the priority drop loop.
TARGET_TOKENS = 7000
EVENTS_CAP = 20  # D-02 explicit cap on overview's events axis (vs 50 in get_recent_events).
RELATED_NOTES_TOP_K = 5


def _estimate_tokens(result: OverviewResponse) -> int:
    """4-char-per-token heuristic, consistent with logging.py."""
    return len(result.model_dump_json()) // 4


def _shrink_related(result: OverviewResponse) -> OverviewResponse:
    new_len = max(1, len(result.related_notes) // 2)
    return result.model_copy(update={"related_notes": result.related_notes[:new_len]})


def _shrink_events(result: OverviewResponse) -> OverviewResponse:
    new_len = max(1, len(result.events) // 2)
    return result.model_copy(update={"events": result.events[:new_len]})


def _drop_private_thesis(result: OverviewResponse) -> OverviewResponse:
    return result.model_copy(update={"private_thesis": None})


def _drop_valuation(result: OverviewResponse) -> OverviewResponse:
    return result.model_copy(update={"valuation": None})


def _drop_supply_demand(result: OverviewResponse) -> OverviewResponse:
    return result.model_copy(update={"supply_demand": None})


def _drop_portfolio(result: OverviewResponse) -> OverviewResponse:
    return result.model_copy(update={"portfolio": None})


def _drop_related(result: OverviewResponse) -> OverviewResponse:
    return result.model_copy(update={"related_notes": []})


def _drop_events(result: OverviewResponse) -> OverviewResponse:
    return result.model_copy(update={"events": []})


# (axis, shrink_fn or None, drop_fn) — earliest entries are sacrificed first.
ITEM_DROP_ORDER = [
    ("private_thesis", None, _drop_private_thesis),
    ("valuation", None, _drop_valuation),
    ("supply_demand", None, _drop_supply_demand),
    ("portfolio", None, _drop_portfolio),
    ("related_notes", _shrink_related, _drop_related),
    ("events", _shrink_events, _drop_events),
]


def _apply_truncation(
    result: OverviewResponse, target_tokens: int = TARGET_TOKENS
) -> OverviewResponse:
    """Iteratively shrink/drop axes by priority until under the soft token cap.

    Returns a new ``OverviewResponse`` with ``truncation_applied`` extended to
    include every shrink/drop that fired. Pure function — no I/O.
    """
    applied = list(result.truncation_applied)
    while _estimate_tokens(result) > target_tokens:
        progressed = False
        for axis, shrink, drop in ITEM_DROP_ORDER:
            if shrink is not None:
                # List axes (related_notes, events): shrink first, drop only when empty.
                current = getattr(result, axis)
                if current:
                    new_result = shrink(result)
                    new_current = getattr(new_result, axis)
                    if len(new_current) < len(current):
                        result = new_result
                        applied.append(f"{axis}:shrunk")
                        progressed = True
                        break
                    # Single element left: fall through to drop.
                    result = drop(result)
                    applied.append(f"{axis}:dropped")
                    progressed = True
                    break
            else:
                current = getattr(result, axis)
                if current is not None:
                    result = drop(result)
                    applied.append(f"{axis}:dropped")
                    progressed = True
                    break
        if not progressed:
            break
    return result.model_copy(update={"truncation_applied": applied})


def _portfolio_row_for(ticker: str) -> PortfolioRow | None:
    """Find the matching ``PortfolioRow`` for ``ticker`` in holdings or watchlist."""
    state = get_portfolio_state()
    if isinstance(state, dict):
        # Error envelope from get_portfolio_state — best-effort: return None and
        # let the caller continue with portfolio=None.
        return None
    for row in state.holdings:
        if row.ticker == ticker:
            return row
    for row in state.watchlist:
        if row.ticker == ticker:
            return row
    return None


def _related_notes_for(engine, query: str, ticker: str) -> list[SearchHit]:
    """Fetch up to ``RELATED_NOTES_TOP_K`` note hits via hybrid_search.

    Returns ``[]`` on any retrieval error — composite tool must not fail the
    whole response when one axis is empty.
    """
    try:
        raw_hits = hybrid_search(
            engine,
            query=query,
            ticker=ticker,
            source="note",
            mode="hybrid",
            top_k=RELATED_NOTES_TOP_K,
        )
    except Exception:  # noqa: BLE001 — defensive: never block overview on retrieval error.
        return []
    hits: list[SearchHit] = []
    for raw in raw_hits:
        try:
            hits.append(
                SearchHit(
                    vault_path=raw["vault_path"],
                    excerpt=raw["excerpt"],
                    frontmatter_ref=raw["frontmatter_ref"],
                    score=float(raw["score"]),
                    source=raw["source"],
                    doc_id=raw["doc_id"],
                )
            )
        except Exception:  # noqa: BLE001 — skip malformed hits.
            continue
    return hits


def get_ticker_overview(ticker: str) -> OverviewResponse | dict:
    """Composite Claude-judgment context bundle for a ticker (MCP-03, JUDGE-01).

    Single-call aggregator that composes three Wave-2 axes — recent events,
    portfolio meta row, related notes — into one ``OverviewResponse``.
    Phase-10 placeholders (``valuation``, ``supply_demand``,
    ``private_thesis``) are always ``None`` in Phase 6 (D-01).

    ### Behavior contract
    - ``ticker``: 6-digit KRX ticker (e.g. ``"005930"``) **or** 8-digit DART
      ``corp_code`` (e.g. ``"00126380"``); both forms resolve to the same
      entity via ``resolve_entity`` and yield identical responses.
    - No ``as_of`` parameter — Phase 10 owns historical lookups.
    - ``since`` for the events axis is computed internally as
      ``now KST − 90 days`` (D-02 implies recent).
    - Events axis hard-capped at 20 rows (D-02). ``truncation_applied``
      includes ``"events:cap20"`` whenever the cap fires.
    - Truncation priority order (D-22): ``private_thesis`` < ``valuation`` <
      ``supply_demand`` < ``portfolio`` < ``related_notes`` < ``events``.
      The drop loop runs until estimated tokens fall below 7000 (soft cap
      under the 8000-token D-19 hard ceiling).

    ### Response shape
    Returns ``OverviewResponse`` with:
    - ``ticker``: resolved 6-digit ticker (``entity.current_ticker``).
    - ``corp_code``: ``entity.corp_code`` (8-digit DART id).
    - ``events``: list of ``EventRow``, capped at 20.
    - ``portfolio``: ``PortfolioRow`` if ticker is in holdings or watchlist,
      else ``None``.
    - ``related_notes``: list of ``SearchHit`` from a hybrid search restricted
      to ``source='note'``, top-5.
    - ``valuation`` / ``supply_demand`` / ``private_thesis``: always ``None``
      in Phase 6 (D-01 placeholders for Phase 10).
    - ``truncation_applied``: list of strings, each naming a section dropped
      or shrunk during the token-guard pass (D-22).

    ### Errors
    Returns ``{"error": {"code": ..., "message": ..., "details": {...}}}`` —
    never raises. Codes:
    - ``INVALID_TICKER``: ticker not resolvable via ``resolve_entity``.
    - ``DB_UNAVAILABLE``: Postgres unreachable.
    - ``INTERNAL``: unexpected failure (string truncated to 200 chars).

    ### Performance budget
    p95 latency < 5s. Response p95 < 8000 tokens (cl100k_base) — enforced by
    a soft 7000-token cap with priority-ordered shrink/drop loop. Composite
    of three internal calls (events, portfolio, hybrid_search); each axis
    fails open (empty list / None) so no single backend can sink the bundle.
    """
    t0 = time.perf_counter()
    args_log = {"ticker": ticker}
    try:
        engine = get_engine()
        entity = resolve_entity(engine, ticker)
        if entity is None:
            raise StructuredError(
                ErrorCode.INVALID_TICKER,
                f"unknown ticker: {ticker}",
                details={"ticker": ticker},
            )
        resolved_ticker = entity.current_ticker or ticker
        corp_code = entity.corp_code

        # 1) Events axis (default since = now KST - 90d).
        since_default = (
            datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(days=90)
        ).strftime("%Y-%m-%d")
        events_response = get_recent_events(ticker=resolved_ticker, since=since_default)
        truncation_applied: list[str] = []
        events: list[EventRow] = []
        if isinstance(events_response, dict):
            truncation_applied.append("events:error")
        else:
            events = list(events_response.events)

        # 2) D-02 hard cap at 20.
        if len(events) > EVENTS_CAP:
            events = events[:EVENTS_CAP]
            truncation_applied.append("events:cap20")

        # 3) Portfolio axis.
        portfolio_row = _portfolio_row_for(resolved_ticker)

        # 4) Related notes axis — hybrid_search restricted to source='note'.
        related_notes = _related_notes_for(
            engine, query=entity.canonical_name, ticker=resolved_ticker
        )

        # 5) Construct + truncate.
        result = OverviewResponse(
            ticker=resolved_ticker,
            corp_code=corp_code,
            events=events,
            portfolio=portfolio_row,
            related_notes=related_notes,
            valuation=None,
            supply_demand=None,
            private_thesis=None,
            truncation_applied=truncation_applied,
        )
        result = _apply_truncation(result, TARGET_TOKENS)

        # 6) Re-assert hard cap on events (may have grown back through model_copy
        # only if shrink overshot; defensive).
        if len(result.events) > EVENTS_CAP:
            applied = list(result.truncation_applied)
            applied.append("events:cap20")
            result = result.model_copy(
                update={"events": result.events[:EVENTS_CAP], "truncation_applied": applied}
            )

        latency = int((time.perf_counter() - t0) * 1000)
        log_tool_call(
            "get_ticker_overview",
            args_log,
            latency,
            len(result.model_dump_json()) // 4,
        )
        return result
    except StructuredError as e:
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(e)
        log_tool_call("get_ticker_overview", args_log, latency, 0, error=err["error"])
        return err
    except Exception as e:  # noqa: BLE001 — D-21 catch-all
        wrapped = StructuredError(ErrorCode.INTERNAL, str(e)[:200])
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(wrapped)
        log_tool_call("get_ticker_overview", args_log, latency, 0, error=err["error"])
        return err


mcp.tool()(get_ticker_overview)
