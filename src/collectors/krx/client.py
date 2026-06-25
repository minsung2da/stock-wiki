"""Thin pykrx wrapper for KRX market data (COLL-02).

No secrets required. pykrx scrapes public KRX/Naver endpoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from shared.throttle import Throttle

if TYPE_CHECKING:
    import pandas as pd

# CAP-1 (collector hardening): proactive politeness throttle. pykrx scrapes
# KRX/Naver public endpoints with NO formal rate limit — the binding constraint
# is IP-throttle. Korean quant-community norm is 1-2 req/s
# (.planning/research/STACK.md line 93). One shared throttle paces all three
# KRX scrape calls; tests lower ``_throttle.min_interval_sec`` to run fast.
KRX_MIN_REQUEST_INTERVAL_SEC = 1.0
_throttle = Throttle(KRX_MIN_REQUEST_INTERVAL_SEC)


def get_ohlcv(ticker: str, date_str: str) -> pd.DataFrame:
    """One-day OHLCV DataFrame for a ticker. Empty DF on non-trading days."""
    from pykrx import stock

    _throttle.wait()
    return stock.get_market_ohlcv_by_date(date_str, date_str, ticker)


def get_trading_value(ticker: str, date_str: str) -> pd.DataFrame:
    """Investor-flow DataFrame projected to 외국인/기관합계/개인 (RESEARCH §1.2)."""
    from pykrx import stock

    _throttle.wait()
    df = stock.get_market_trading_value_by_date(date_str, date_str, ticker)
    if df.empty:
        return df
    return df[["외국인", "기관합계", "개인"]]


def get_shorting_balance(ticker: str, date_str: str) -> pd.DataFrame:
    """Short-balance DataFrame. T+2 lag — may be empty for recent dates."""
    from pykrx import stock

    _throttle.wait()
    return stock.get_shorting_balance_by_date(date_str, date_str, ticker)


def get_market_ohlcv_all(date_str: str) -> pd.DataFrame:
    """Whole-market one-day OHLCV, indexed by 6-digit ticker (CAP-3 bulk fetch).

    Replaces N per-ticker ``get_market_ohlcv_by_date`` scrapes with ONE
    market-wide call (KOSPI+KOSDAQ via ``market='ALL'``). Fewer requests =
    lower IP-throttle risk, which is the binding constraint for pykrx (no
    formal API rate limit). Empty DataFrame on a non-trading day. The frame
    carries the same Korean OHLCV columns (시가/고가/저가/종가/거래량/거래대금)
    as the per-ticker call, so the collector's coercion is unchanged.
    """
    from pykrx import stock

    _throttle.wait()
    return stock.get_market_ohlcv(date_str, market="ALL")
