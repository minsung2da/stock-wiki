"""Enforce D-24 docstring 4-section contract for every Phase 6 tool.

Each tool callable's ``__doc__`` must include the four canonical sections so
LLM clients (Claude Code) get a consistent contract surface.
"""

from __future__ import annotations

import pytest

REQUIRED_SECTIONS = (
    "### Behavior contract",
    "### Response shape",
    "### Errors",
    "### Performance budget",
)


def _all_tools() -> dict:
    from stock_mcp.tools import (
        events,
        filing,
        health,
        notes,
        overview,
        portfolio,
        related,
        search,
    )

    return {
        "search": search.search,
        "get_ticker_overview": overview.get_ticker_overview,
        "get_recent_events": events.get_recent_events,
        "get_portfolio_state": portfolio.get_portfolio_state,
        "get_related": related.get_related,
        "get_filing": filing.get_filing,
        "add_note": notes.add_note,
        "health": health.health,
    }


@pytest.mark.parametrize("name,fn", list(_all_tools().items()))
def test_docstring_has_four_sections(name: str, fn) -> None:
    doc = fn.__doc__ or ""
    for section in REQUIRED_SECTIONS:
        assert section in doc, (
            f"{name} docstring missing '{section}' section"
        )
