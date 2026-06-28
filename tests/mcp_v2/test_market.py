"""Tests for ohlcv_range / flow_range / peer_view — Plan 03-05 Task 3.

All db-marked (live Postgres at migration 0008). Seeds ``ohlcv`` rows for the
range tools and same-sector ``entities`` + ``fundamentals`` rows for peer_view's
``percentile_cont(0.5)`` median (D-06). Veto #6: every assertion is on typed
numbers — no body_md / embedding column exists on these tables.

``fundamentals`` is NOT in tests/conftest.py ``_LIVE_TABLES`` (added in migration
0008 after that list was authored), so ``pg_clean`` does not truncate it. The
peer_view tests DELETE the fundamentals + extra entities they own up-front.
"""

from __future__ import annotations

import re
from datetime import date

import pytest
from sqlalchemy import text

from mcp_v2.errors import EntityNotFound, InvalidArgument
from mcp_v2.models import OhlcvRange, _TICKER_PATTERN
from mcp_v2.tools.market import _TICKER_RE, flow_range, ohlcv_range, peer_view

pytestmark = pytest.mark.db


# --------------------------------------------------------------------------- #
# widened ticker guard ^[0-9A-Z]{6}$ — DB-FREE regex/model checks (quick-260628-n8d)
# --------------------------------------------------------------------------- #
_ACCEPT_TICKERS = ["0001A0", "005930", "AAAAAA", "0A0A0A"]
_REJECT_TICKERS = [
    "00593",       # 5-char
    "0059300",     # 7-char
    "0001a0",      # lowercase
    "0001A!",      # path/shell metachar
    "0;DROP",      # SQL metachar
    "²" * 6,  # non-ASCII superscript (str.isdigit would accept — guard must not)
]


@pytest.mark.parametrize("ticker", _ACCEPT_TICKERS)
def test_ticker_guards_accept_alphanumeric(ticker: str) -> None:
    """Both _TICKER_RE and _TICKER_PATTERN accept 6-char uppercase-alphanumeric codes."""
    assert _TICKER_RE.match(ticker) is not None
    assert re.compile(_TICKER_PATTERN).match(ticker) is not None


@pytest.mark.parametrize("ticker", _REJECT_TICKERS)
def test_ticker_guards_reject_bad_shapes(ticker: str) -> None:
    """Wrong-length / lowercase / metachar / non-ASCII tickers still rejected."""
    assert _TICKER_RE.match(ticker) is None
    assert re.compile(_TICKER_PATTERN).match(ticker) is None


def test_ohlcv_range_model_accepts_alphanumeric_ticker() -> None:
    """OhlcvRange (and FlowRange via shared _TICKER_PATTERN) constructs with 0001A0."""
    assert OhlcvRange(ticker="0001A0").ticker == "0001A0"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _seed_ohlcv(engine, ticker: str, corp_code: str, days: list[tuple[date, float]]) -> None:
    """Insert ohlcv rows with OHLCV + flow + short for each (trade_date, close)."""
    with engine.begin() as conn:
        for d, close in days:
            conn.execute(
                text(
                    "INSERT INTO ohlcv (ticker, trade_date, open, high, low, close, volume, "
                    "trading_value, foreign_net, inst_net, retail_net, short_volume, "
                    "short_balance, corp_code, fetched_at) "
                    "VALUES (:t, :d, :o, :h, :l, :c, :v, :tv, :fn, :inn, :rn, :sv, :sb, :cc, now())"
                ),
                {
                    "t": ticker,
                    "d": d,
                    "o": close - 100,
                    "h": close + 200,
                    "l": close - 300,
                    "c": close,
                    "v": 1_000_000,
                    "tv": 70_000_000_000,
                    "fn": 12345,
                    "inn": -6789,
                    "rn": -5556,
                    "sv": 1234,
                    "sb": 87_000_000_000,
                    "cc": corp_code,
                },
            )


def _clean_peer_fixtures(engine) -> None:
    """Remove fundamentals + the non-Samsung peer entities used by peer_view tests."""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM fundamentals"))


def _seed_sector(engine, corp_code: str, name: str, ticker: str, sector: str | None) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entities (corp_code, canonical_name, current_ticker, market, sector) "
                "VALUES (:cc, :n, :t, 'KOSPI', :s) "
                "ON CONFLICT (corp_code) DO UPDATE SET sector = EXCLUDED.sector"
            ),
            {"cc": corp_code, "n": name, "t": ticker, "s": sector},
        )


def _set_sector(engine, corp_code: str, sector: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE entities SET sector = :s WHERE corp_code = :cc"),
            {"s": sector, "cc": corp_code},
        )


def _seed_fundamentals(engine, ticker: str, corp_code: str, per: float, pbr: float, roe: float):
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO fundamentals (ticker, fdate, per, pbr, eps, bps, roe, "
                "corp_code, source, fetched_at) "
                "VALUES (:t, :d, :per, :pbr, :eps, :bps, :roe, :cc, 'fundamentals', now()) "
                "ON CONFLICT (ticker, fdate) DO UPDATE SET per=EXCLUDED.per, pbr=EXCLUDED.pbr, "
                "roe=EXCLUDED.roe"
            ),
            {
                "t": ticker,
                "d": date(2026, 4, 17),
                "per": per,
                "pbr": pbr,
                "eps": 5000.0,
                "bps": 40000.0,
                "roe": roe,
                "cc": corp_code,
            },
        )


# --------------------------------------------------------------------------- #
# ohlcv_range / flow_range
# --------------------------------------------------------------------------- #
def test_ohlcv_range_returns_ordered_bars(seeded_engine) -> None:
    _seed_ohlcv(
        seeded_engine,
        "005930",
        "00126380",
        [(date(2026, 4, 15), 70000.0), (date(2026, 4, 16), 70500.0), (date(2026, 4, 17), 71000.0)],
    )
    result = ohlcv_range("005930", "2026-04-15", "2026-04-17")
    assert result.ticker == "005930"
    assert [b.trade_date for b in result.bars] == ["2026-04-15", "2026-04-16", "2026-04-17"]
    assert result.bars[0].close == pytest.approx(70000.0)
    assert result.bars[-1].close == pytest.approx(71000.0)
    assert result.bars[0].volume == 1_000_000
    assert result.bars[0].trading_value == pytest.approx(70_000_000_000)


def test_ohlcv_range_window_bounds_are_inclusive(seeded_engine) -> None:
    _seed_ohlcv(
        seeded_engine,
        "005930",
        "00126380",
        [(date(2026, 4, 14), 69000.0), (date(2026, 4, 15), 70000.0), (date(2026, 4, 18), 72000.0)],
    )
    result = ohlcv_range("005930", "2026-04-15", "2026-04-17")
    # only 2026-04-15 falls in [15, 17]
    assert [b.trade_date for b in result.bars] == ["2026-04-15"]


def test_ohlcv_range_empty_window_returns_empty_model(seeded_engine) -> None:
    result = ohlcv_range("005930", "2030-01-01", "2030-12-31")
    assert result.ticker == "005930"
    assert result.bars == []


def test_ohlcv_range_bad_ticker_raises_invalid_argument(seeded_engine) -> None:
    with pytest.raises(InvalidArgument):
        ohlcv_range("12AB", "2026-04-15", "2026-04-17")


def test_ohlcv_range_unknown_ticker_raises_entity_not_found(seeded_engine) -> None:
    with pytest.raises(EntityNotFound):
        ohlcv_range("999999", "2026-04-15", "2026-04-17")


def test_flow_range_returns_numeric_rows(seeded_engine) -> None:
    _seed_ohlcv(
        seeded_engine,
        "005930",
        "00126380",
        [(date(2026, 4, 16), 70500.0), (date(2026, 4, 17), 71000.0)],
    )
    result = flow_range("005930", "2026-04-16", "2026-04-17")
    assert result.ticker == "005930"
    assert [r.trade_date for r in result.rows] == ["2026-04-16", "2026-04-17"]
    assert result.rows[0].foreign_net == pytest.approx(12345)
    assert result.rows[0].inst_net == pytest.approx(-6789)
    assert result.rows[0].retail_net == pytest.approx(-5556)
    assert result.rows[0].short_volume == pytest.approx(1234)
    assert result.rows[0].short_balance == pytest.approx(87_000_000_000)


def test_flow_range_empty_window_returns_empty_model(seeded_engine) -> None:
    result = flow_range("005930", "2030-01-01", "2030-12-31")
    assert result.rows == []


def test_flow_range_bad_ticker_raises_invalid_argument(seeded_engine) -> None:
    with pytest.raises(InvalidArgument):
        flow_range("abc", "2026-04-16", "2026-04-17")


# --------------------------------------------------------------------------- #
# peer_view — real same-sector median (D-06)
# --------------------------------------------------------------------------- #
def test_peer_view_computes_same_sector_median(seeded_engine) -> None:
    """Two same-sector peers → median over both, n=2."""
    _clean_peer_fixtures(seeded_engine)
    # Samsung (already seeded) gets a sector + a peer in the SAME sector.
    _set_sector(seeded_engine, "00126380", "반도체")
    _seed_sector(seeded_engine, "00164779", "SK하이닉스", "000660", "반도체")

    _seed_fundamentals(seeded_engine, "005930", "00126380", per=10.0, pbr=1.0, roe=0.10)
    _seed_fundamentals(seeded_engine, "000660", "00164779", per=20.0, pbr=2.0, roe=0.20)

    result = peer_view("00126380", "per")
    assert result.metric == "per"
    assert result.n == 2
    assert result.median == pytest.approx(15.0)  # median of {10, 20}
    assert result.sector == "반도체"

    pbr_result = peer_view("00126380", "pbr")
    assert pbr_result.median == pytest.approx(1.5)
    assert pbr_result.n == 2

    roe_result = peer_view("00126380", "roe")
    assert roe_result.median == pytest.approx(0.15)
    assert roe_result.n == 2


def test_peer_view_excludes_other_sectors(seeded_engine) -> None:
    """A peer in a DIFFERENT sector is not counted in the median."""
    _clean_peer_fixtures(seeded_engine)
    _set_sector(seeded_engine, "00126380", "반도체")
    _seed_sector(seeded_engine, "00164779", "SK하이닉스", "000660", "반도체")
    _seed_sector(seeded_engine, "00111111", "현대차", "005380", "자동차")

    _seed_fundamentals(seeded_engine, "005930", "00126380", per=10.0, pbr=1.0, roe=0.10)
    _seed_fundamentals(seeded_engine, "000660", "00164779", per=20.0, pbr=2.0, roe=0.20)
    _seed_fundamentals(seeded_engine, "005380", "00111111", per=999.0, pbr=99.0, roe=0.99)

    result = peer_view("00126380", "per")
    assert result.n == 2  # the 자동차 peer is excluded
    assert result.median == pytest.approx(15.0)


def test_peer_view_no_peers_returns_empty_model(seeded_engine) -> None:
    """No same-sector peers (and no fundamentals) → median=None, n=0 (D-01)."""
    _clean_peer_fixtures(seeded_engine)
    _set_sector(seeded_engine, "00126380", "외톨이섹터")

    result = peer_view("00126380", "per")
    assert result.median is None
    assert result.n == 0
    assert result.sector == "외톨이섹터"


def test_peer_view_null_sector_returns_empty_model(seeded_engine) -> None:
    """corp_code with NULL sector → no peer set → median=None, n=0 (D-01)."""
    _clean_peer_fixtures(seeded_engine)
    with seeded_engine.begin() as conn:
        conn.execute(text("UPDATE entities SET sector = NULL WHERE corp_code = '00126380'"))
    _seed_fundamentals(seeded_engine, "005930", "00126380", per=10.0, pbr=1.0, roe=0.10)

    result = peer_view("00126380", "per")
    assert result.median is None
    assert result.n == 0


def test_peer_view_bad_metric_raises_invalid_argument(seeded_engine) -> None:
    with pytest.raises(InvalidArgument):
        peer_view("00126380", "ebitda")


def test_peer_view_bad_corp_code_raises_invalid_argument(seeded_engine) -> None:
    with pytest.raises(InvalidArgument):
        peer_view("12345", "per")  # 5 digits, not 8
