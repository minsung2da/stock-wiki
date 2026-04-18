"""Tests for src/shared/portfolio.py — Portfolio.load + scope_tickers (D-01..D-04)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from shared.portfolio import Holding, Portfolio, PortfolioLoadError

_SEED_YAML = (
    'holdings:\n  - ticker: "005930"\n    qty: 1\n    avg_cost: 70000\nwatchlist:\n  - "000660"\n'
)


def _write_portfolio(vault: Path, yaml_body: str, body: str = "# Portfolio\n") -> None:
    (vault / "notes").mkdir(parents=True, exist_ok=True)
    (vault / "notes" / "portfolio.md").write_text(f"---\n{yaml_body}---\n{body}", encoding="utf-8")


def test_load_seed_file_returns_expected_holdings_and_watchlist(tmp_path: Path) -> None:
    _write_portfolio(tmp_path, _SEED_YAML)
    p = Portfolio.load(tmp_path)
    assert p.holdings == [Holding(ticker="005930", qty=1, avg_cost=70000)]
    assert p.watchlist == ["000660"]


def test_load_missing_file_raises_portfolio_load_error(tmp_path: Path) -> None:
    with pytest.raises(PortfolioLoadError):
        Portfolio.load(tmp_path)


def test_invalid_5digit_ticker_raises_validation_error(tmp_path: Path) -> None:
    _write_portfolio(
        tmp_path,
        'holdings:\n  - ticker: "5930"\n    qty: 1\n    avg_cost: 70000\nwatchlist: []\n',
    )
    with pytest.raises(ValidationError):
        Portfolio.load(tmp_path)


def test_scope_tickers_returns_sorted_union(tmp_path: Path) -> None:
    _write_portfolio(tmp_path, _SEED_YAML)
    p = Portfolio.load(tmp_path)
    assert p.scope_tickers() == ["000660", "005930"]


def test_extra_unknown_key_raises_validation_error(tmp_path: Path) -> None:
    _write_portfolio(
        tmp_path,
        'holdings: []\nwatchlist: []\nunknown_key: "oops"\n',
    )
    with pytest.raises(ValidationError):
        Portfolio.load(tmp_path)
