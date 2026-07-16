"""No-DB tests for list_portfolio + get_briefing input validation.

list_portfolio reads ``notes/private/portfolio.md`` from the process cwd, so the
tests ``monkeypatch.chdir(tmp_path)`` and write a portfolio.md there.

The Phase-3 honest-empty get_briefing tests (``found=False`` daily/weekly + the
``report_type``-absence AST guard) were retired in Plan 05-04 — Phase 5 wired
``get_briefing`` to read a real row via ``cards.store.get_briefing_row``, so the
DB-backed behaviour now lives in ``test_briefing_wired.py`` (an EXPECTED change,
not a regression). Only the no-DB bad-``type`` guard stays here — it validates the
argument before any DB access and needs no engine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_v2.errors import DataBackendError, InvalidArgument
from mcp_v2.tools.briefing import get_briefing
from mcp_v2.tools.portfolio import list_portfolio

# No DB marker: portfolio reads disk, briefing is pure logic. Run -m "not db".

_PORTFOLIO_MD = (
    "---\n"
    "holdings:\n"
    "  - ticker: '005930'\n"
    "    qty: 10\n"
    "    avg_cost: 70000\n"
    "  - ticker: '000660'\n"
    "    qty: 5\n"
    "    avg_cost: 120000\n"
    "watchlist:\n"
    "  - '035720'\n"
    "---\n"
    "# Portfolio notes\n"
)


def _write_portfolio(repo_root: Path, content: str) -> None:
    target = repo_root / "notes" / "private" / "portfolio.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


# --------------------------------------------------------------------------- #
# list_portfolio
# --------------------------------------------------------------------------- #
def test_list_portfolio_returns_holdings_and_watchlist(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_portfolio(tmp_path, _PORTFOLIO_MD)

    result = list_portfolio()

    assert {h.ticker for h in result.holdings} == {"005930", "000660"}
    samsung = next(h for h in result.holdings if h.ticker == "005930")
    assert samsung.quantity == 10
    assert samsung.avg_price == 70000
    assert [w.ticker for w in result.watchlist] == ["035720"]


def test_list_portfolio_empty_is_valid(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_portfolio(tmp_path, "---\nholdings: []\nwatchlist: []\n---\n")

    result = list_portfolio()
    assert result.holdings == []
    assert result.watchlist == []


def test_list_portfolio_missing_file_raises_data_backend_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # no portfolio.md written
    with pytest.raises(DataBackendError):
        list_portfolio()


# --------------------------------------------------------------------------- #
# get_briefing — no-DB argument guard (the wired behaviour lives in
# test_briefing_wired.py; the Phase-3 honest-empty tests were retired in 05-04).
# --------------------------------------------------------------------------- #
def test_get_briefing_bad_type_raises_invalid_argument():
    with pytest.raises(InvalidArgument):
        get_briefing("2026-06-07", type="monthly")
    with pytest.raises(InvalidArgument):
        get_briefing("2026-06-07", type="")
