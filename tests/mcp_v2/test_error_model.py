"""D-01 contract: every return model is empty-able; every error is a ToolError.

No DB. Covers:
- Each :mod:`mcp_v2.models` return model constructs in its empty state (empty
  list / ``found=False`` / ``median=None``) given only its identifier args.
- The full :mod:`mcp_v2.errors` hierarchy subclasses ``fastmcp.exceptions.ToolError``
  (so FastMCP surfaces the message even under ``mask_error_details=True``).
- The shared ``mcp`` instance is a ``FastMCP`` named "stock-mcp-v2".
- ``errors.py`` carries no archive dict-return error pattern.

Run: ``.venv/Scripts/python.exe -m pytest tests/mcp_v2/test_error_model.py -x -q -m "not db"``
"""

from __future__ import annotations

import pathlib

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import ValidationError

from mcp_v2 import _mcp
from mcp_v2.errors import (
    DataBackendError,
    EntityNotFound,
    FilingNotFound,
    InvalidArgument,
    McpToolError,
    NoteNotFound,
    NotePathForbidden,
)
from mcp_v2.models import (
    Briefing,
    CardView,
    FilingDetail,
    FlowRange,
    NoteContent,
    OhlcvRange,
    PeerView,
    PortfolioView,
    SearchFilingsResult,
    SearchHit,
    SearchResult,
)

_TICKER = "005930"
_CORP = "00126380"


# --------------------------------------------------------------------------- #
# D-01 — empty-able return models
# --------------------------------------------------------------------------- #
def test_ohlcv_range_empty_bars() -> None:
    assert OhlcvRange(ticker=_TICKER).bars == []


def test_flow_range_empty_rows() -> None:
    assert FlowRange(ticker=_TICKER).rows == []


def test_search_filings_empty_hits() -> None:
    assert SearchFilingsResult(corp_code=_CORP).hits == []


def test_search_result_empty_hits() -> None:
    assert SearchResult().hits == []


def test_peer_view_empty_median() -> None:
    pv = PeerView(metric="per")
    assert pv.median is None
    assert pv.n == 0


def test_card_view_not_found() -> None:
    cv = CardView(corp_code=_CORP)
    assert cv.found is False
    assert cv.card is None


def test_briefing_not_found_empty_entries() -> None:
    b = Briefing(date="2026-06-07", type="daily")
    assert b.found is False
    assert b.entries == []


def test_portfolio_view_empty() -> None:
    pv = PortfolioView()
    assert pv.holdings == []
    assert pv.watchlist == []


def test_narrative_models_default_no_injection() -> None:
    """Narrative models default to no-injection flags; flags are advisory, never
    a substitute for the body (D-03: body always present, never stripped)."""
    fd = FilingDetail(
        rcept_no="20260101000001",
        corp_code=_CORP,
        body_md="<untrusted>x</untrusted>",
    )
    assert fd.injection_suspected is False
    assert fd.injection_flags == []
    assert fd.body_md  # body present

    nc = NoteContent(path="notes/private/a.md", content_md="<untrusted>y</untrusted>")
    assert nc.injection_suspected is False
    assert nc.injection_flags == []

    hit = SearchHit(
        source_type="filing",
        id_or_path="20260101000001",
        rrf_score=0.5,
        snippet="<untrusted>z</untrusted>",
    )
    assert hit.injection_suspected is False
    assert hit.injection_flags == []


def test_models_forbid_extra() -> None:
    """Every return model uses ConfigDict(extra='forbid') (V5, matches cards)."""
    with pytest.raises(ValidationError):
        OhlcvRange(ticker=_TICKER, bogus=1)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        CardView(corp_code=_CORP, bogus=1)  # type: ignore[call-arg]


def test_ticker_regex_rejects_non_ascii_digits() -> None:
    """ASCII-only ticker regex (str.isdigit would accept superscripts)."""
    with pytest.raises(ValidationError):
        OhlcvRange(ticker="00593⁵")  # superscript 5
    with pytest.raises(ValidationError):
        OhlcvRange(ticker="12345")  # 5 digits


# --------------------------------------------------------------------------- #
# D-01 — typed exception hierarchy
# --------------------------------------------------------------------------- #
_SUBCLASSES = [
    InvalidArgument,
    EntityNotFound,
    FilingNotFound,
    NotePathForbidden,
    NoteNotFound,
    DataBackendError,
]


def test_base_is_tool_error() -> None:
    assert issubclass(McpToolError, ToolError)


@pytest.mark.parametrize("exc", _SUBCLASSES)
def test_each_subclass_is_tool_error(exc: type) -> None:
    assert issubclass(exc, ToolError)
    assert issubclass(exc, McpToolError)


def test_raising_preserves_message() -> None:
    with pytest.raises(InvalidArgument, match="ticker must be 6 ASCII digits"):
        raise InvalidArgument("ticker must be 6 ASCII digits")


# --------------------------------------------------------------------------- #
# shared FastMCP instance
# --------------------------------------------------------------------------- #
def test_shared_mcp_instance() -> None:
    assert isinstance(_mcp.mcp, FastMCP)
    assert _mcp.mcp.name == "stock-mcp-v2"


def test_no_dict_return_error_pattern() -> None:
    """errors.py must NOT *define* the archive StructuredError/ErrorCode/to_error_response
    dict-return pattern (D-01 raises typed exceptions instead).

    AST-based, not a substring scan: the explanatory docstring is allowed to *name*
    the rejected archive pattern, but no such class/function may actually be defined.
    """
    import ast

    src = (pathlib.Path(__file__).resolve().parents[2] / "src" / "mcp_v2" / "errors.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)
    forbidden = {"StructuredError", "ErrorCode", "to_error_response"}
    defined: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            defined.add(node.name)
    leaked = defined & forbidden
    assert not leaked, f"errors.py must not define the archive dict-return pattern: {leaked} (D-01)"
