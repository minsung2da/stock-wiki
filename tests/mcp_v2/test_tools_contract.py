"""SC#2 — every locked tool returns its declared Pydantic model; empty states valid.

Two layers:

1. **Return-annotation contract (no DB).** Every one of the 10 locked tool
   callables declares a Pydantic ``BaseModel`` subclass as its return type — never a
   dict / chunk / blob (SC#2). Read via ``typing.get_type_hints`` on the in-process
   callables (the ``mcp.tool(...)(fn)`` call form keeps the name a plain function).

2. **Empty-state validity (D-01).** A "no data" invocation returns a VALID model
   instance, not an error and not ``None``:
   - ``get_briefing`` — honest empty ``Briefing(found=False, entries=[])`` (no DB).
   - ``search_filings`` / ``ohlcv_range`` / ``flow_range`` — empty list models over
     a seeded entity with no rows (db).
   - ``peer_view`` — ``PeerView(median=None, n=0)`` over a seeded entity with no
     same-sector peers (db).
   - ``get_decision_card`` — ``CardView(found=False)`` over a seeded entity with no
     active card (db).
   - ``hybrid_search`` — ``SearchResult(hits=[])`` over an empty narrative corpus
     (db; covered in detail in test_hybrid_search.py — re-checked here as the
     contract empty state).
   - ``list_portfolio`` — a valid ``PortfolioView`` (no DB; reads disk portfolio).
"""

from __future__ import annotations

import typing

import pytest
from pydantic import BaseModel

import mcp_v2.server  # noqa: F401 — side-effect: registers all 10 tools
from mcp_v2.models import (
    Briefing,
    CardView,
    FlowRange,
    OhlcvRange,
    PeerView,
    PortfolioView,
    SearchFilingsResult,
    SearchResult,
)
from mcp_v2.tools.briefing import get_briefing
from mcp_v2.tools.card import get_decision_card
from mcp_v2.tools.filing import get_filing, search_filings
from mcp_v2.tools.market import flow_range, ohlcv_range, peer_view
from mcp_v2.tools.note import get_note
from mcp_v2.tools.portfolio import list_portfolio
from mcp_v2.tools.search import hybrid_search

_ALL_TOOLS = [
    get_filing,
    search_filings,
    ohlcv_range,
    flow_range,
    peer_view,
    hybrid_search,
    get_note,
    get_decision_card,
    list_portfolio,
    get_briefing,
]

_STUB_QVEC = tuple([0.01] * 1024)


# --------------------------------------------------------------------------- #
# Layer 1 — return-annotation contract (no DB)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("fn", _ALL_TOOLS, ids=lambda f: f.__name__)
def test_tool_returns_pydantic_model(fn) -> None:
    """SC#2: each tool's return annotation is a Pydantic BaseModel subclass."""
    ret = typing.get_type_hints(fn).get("return")
    assert ret is not None, f"{fn.__name__} has no return annotation"
    assert isinstance(ret, type) and issubclass(ret, BaseModel), (
        f"{fn.__name__} must return a Pydantic model, got {ret!r}"
    )


# --------------------------------------------------------------------------- #
# Layer 2 — empty-state validity (D-01)
# --------------------------------------------------------------------------- #
def test_get_briefing_empty_state() -> None:
    """get_briefing returns a valid empty Briefing model (no DB, D-01)."""
    out = get_briefing("2026-06-07", "daily")
    assert isinstance(out, Briefing)
    assert out.found is False
    assert out.entries == []


def test_list_portfolio_returns_model() -> None:
    """list_portfolio returns a valid PortfolioView (no DB — reads disk portfolio)."""
    from mcp_v2.errors import DataBackendError

    try:
        out = list_portfolio()
    except DataBackendError:
        pytest.skip("no notes/private/portfolio.md present in this checkout")
        return
    assert isinstance(out, PortfolioView)


@pytest.mark.db
def test_search_filings_empty_state(seeded_engine) -> None:
    """search_filings over a seeded entity with no filings → empty model (D-01)."""
    out = search_filings("00126380")
    assert isinstance(out, SearchFilingsResult)
    assert out.hits == []


@pytest.mark.db
def test_ohlcv_flow_empty_state(seeded_engine) -> None:
    """ohlcv_range / flow_range over a seeded entity with no bars → empty (D-01)."""
    o = ohlcv_range("005930", "2026-01-01", "2026-01-31")
    f = flow_range("005930", "2026-01-01", "2026-01-31")
    assert isinstance(o, OhlcvRange) and o.bars == []
    assert isinstance(f, FlowRange) and f.rows == []


@pytest.mark.db
def test_peer_view_empty_state(seeded_engine) -> None:
    """peer_view with no same-sector peers → PeerView(median=None, n=0) (D-01)."""
    from sqlalchemy import text

    with seeded_engine.begin() as conn:
        conn.execute(text("DELETE FROM fundamentals"))
    out = peer_view("00126380", "per")
    assert isinstance(out, PeerView)
    assert out.median is None
    assert out.n == 0


@pytest.mark.db
def test_get_decision_card_empty_state(seeded_engine) -> None:
    """get_decision_card with no active card → CardView(found=False) (D-01)."""
    out = get_decision_card("00126380")
    assert isinstance(out, CardView)
    assert out.found is False
    assert out.card is None


@pytest.mark.db
def test_hybrid_search_empty_state(seeded_engine, monkeypatch) -> None:
    """hybrid_search over an empty narrative corpus → SearchResult(hits=[]) (D-01)."""
    from mcp_v2 import retrieval

    monkeypatch.setattr(retrieval, "encode_query", lambda _q: _STUB_QVEC)
    out = hybrid_search("존재하지않는질의어")
    assert isinstance(out, SearchResult)
    assert out.hits == []


def test_get_note_and_get_filing_are_single_row_models() -> None:
    """get_note / get_filing single-row models are introspectable (contract only).

    These two tools have no valid "empty" return (a missing row RAISES, D-01) — the
    contract for them is purely the return-annotation check above. This test pins
    that their declared models are the expected single-row narrative models.
    """
    assert typing.get_type_hints(get_note)["return"].__name__ == "NoteContent"
    assert typing.get_type_hints(get_filing)["return"].__name__ == "FilingDetail"
