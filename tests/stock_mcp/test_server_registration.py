"""Verify all 8 Phase 6 tools are registered on the FastMCP singleton.

Importing ``stock_mcp.server`` triggers side-effect registration of every
tool module. This test asserts the resulting registry contains the full
Phase 6 surface (search + 7 new tools).
"""

from __future__ import annotations


def test_eight_tools_registered() -> None:
    # Importing server has the side effect of registering every tool.
    from stock_mcp.server import mcp

    # FastMCP 2.x stores registered Tool instances on the ToolManager's
    # ``_tools`` dict (private but stable across the 2.x line). The async
    # ``get_tools()`` accessor returns the same dict after applying
    # transformations — for registration smoke-testing, the raw dict is
    # sufficient and avoids the asyncio dance.
    tool_names: set[str] = set()
    tm = getattr(mcp, "_tool_manager", None)
    if tm is not None and hasattr(tm, "_tools"):
        tool_names = set(tm._tools.keys())

    expected = {
        "search",
        "get_ticker_overview",
        "get_recent_events",
        "get_portfolio_state",
        "get_related",
        "get_filing",
        "add_note",
        "health",
    }
    missing = expected - tool_names
    assert not missing, (
        f"Phase 6 tools missing from registry: {missing}; "
        f"got: {sorted(tool_names)}"
    )
