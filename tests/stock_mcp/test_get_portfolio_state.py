"""Tests for the ``get_portfolio_state`` MCP tool (Plan 06-05 Task 2, MCP-05/D-21)."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import Engine

from stock_mcp.tools.portfolio import get_portfolio_state

_TICKER_RE = re.compile(r"^[0-9]{6}$")


def test_returns_3_holdings_and_7_watchlist(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    engine, _vault_root, repo_root = mcp_vault_engine
    _ = engine
    prev = os.environ.get("STOCK_REPO_ROOT")
    os.environ["STOCK_REPO_ROOT"] = str(repo_root)
    try:
        result = get_portfolio_state()
    finally:
        if prev is None:
            os.environ.pop("STOCK_REPO_ROOT", None)
        else:
            os.environ["STOCK_REPO_ROOT"] = prev

    assert hasattr(result, "holdings"), f"unexpected error: {result!r}"
    assert len(result.holdings) == 3
    assert len(result.watchlist) == 7


def test_holdings_have_qty_avg_cost_corp_code(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    engine, _vault_root, repo_root = mcp_vault_engine
    _ = engine
    prev = os.environ.get("STOCK_REPO_ROOT")
    os.environ["STOCK_REPO_ROOT"] = str(repo_root)
    try:
        result = get_portfolio_state()
    finally:
        if prev is None:
            os.environ.pop("STOCK_REPO_ROOT", None)
        else:
            os.environ["STOCK_REPO_ROOT"] = prev

    for row in result.holdings:
        assert _TICKER_RE.match(row.ticker)
        assert row.qty is not None and row.qty > 0
        assert row.avg_cost is not None and row.avg_cost > 0
        # Fixture seeds entities for all 10 fixture tickers — corp_code resolves.
        assert row.corp_code is not None and len(row.corp_code) == 8
        assert row.tags == []
        assert row.note is None


def test_watchlist_rows_have_no_qty_or_avg_cost(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    engine, _vault_root, repo_root = mcp_vault_engine
    _ = engine
    prev = os.environ.get("STOCK_REPO_ROOT")
    os.environ["STOCK_REPO_ROOT"] = str(repo_root)
    try:
        result = get_portfolio_state()
    finally:
        if prev is None:
            os.environ.pop("STOCK_REPO_ROOT", None)
        else:
            os.environ["STOCK_REPO_ROOT"] = prev

    for row in result.watchlist:
        assert _TICKER_RE.match(row.ticker)
        assert row.qty is None
        assert row.avg_cost is None
        assert row.corp_code is not None and len(row.corp_code) == 8


def test_response_carries_no_price_or_eval_fields(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    """D-21: get_portfolio_state is meta-only. No price/eval/pnl anywhere."""
    engine, _vault_root, repo_root = mcp_vault_engine
    _ = engine
    prev = os.environ.get("STOCK_REPO_ROOT")
    os.environ["STOCK_REPO_ROOT"] = str(repo_root)
    try:
        result = get_portfolio_state()
    finally:
        if prev is None:
            os.environ.pop("STOCK_REPO_ROOT", None)
        else:
            os.environ["STOCK_REPO_ROOT"] = prev

    raw_json = result.model_dump_json()
    for forbidden in ("price", "eval", "evaluation_value", "pnl"):
        assert forbidden not in raw_json, f"forbidden field {forbidden!r} present in response"


def test_missing_portfolio_returns_path_not_found(
    tmp_path: Path,
) -> None:
    """When notes/private/portfolio.md is missing, error envelope returned."""
    fake_root = tmp_path / "empty-repo"
    fake_root.mkdir()
    prev = os.environ.get("STOCK_REPO_ROOT")
    os.environ["STOCK_REPO_ROOT"] = str(fake_root)
    try:
        result = get_portfolio_state()
    finally:
        if prev is None:
            os.environ.pop("STOCK_REPO_ROOT", None)
        else:
            os.environ["STOCK_REPO_ROOT"] = prev

    assert isinstance(result, dict), f"expected error envelope, got {result!r}"
    assert result["error"]["code"] == "PATH_NOT_FOUND"


def test_source_path_is_relative(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    engine, _vault_root, repo_root = mcp_vault_engine
    _ = engine
    prev = os.environ.get("STOCK_REPO_ROOT")
    os.environ["STOCK_REPO_ROOT"] = str(repo_root)
    try:
        result = get_portfolio_state()
    finally:
        if prev is None:
            os.environ.pop("STOCK_REPO_ROOT", None)
        else:
            os.environ["STOCK_REPO_ROOT"] = prev

    assert result.source_path == "notes/private/portfolio.md"


def test_last_modified_is_datetime(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    engine, _vault_root, repo_root = mcp_vault_engine
    _ = engine
    prev = os.environ.get("STOCK_REPO_ROOT")
    os.environ["STOCK_REPO_ROOT"] = str(repo_root)
    try:
        result = get_portfolio_state()
    finally:
        if prev is None:
            os.environ.pop("STOCK_REPO_ROOT", None)
        else:
            os.environ["STOCK_REPO_ROOT"] = prev

    assert isinstance(result.last_modified, datetime)


def test_docstring_has_four_sections(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    _ = mcp_vault_engine
    doc = get_portfolio_state.__doc__ or ""
    for section in (
        "### Behavior contract",
        "### Response shape",
        "### Errors",
        "### Performance budget",
    ):
        assert section in doc, f"missing docstring section: {section}"
