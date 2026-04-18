"""Thin pykrx wrapper for KRX market data (COLL-02).

No secrets required. pykrx scrapes public KRX/Naver endpoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def get_ohlcv(ticker: str, date_str: str) -> pd.DataFrame:
    """One-day OHLCV DataFrame for a ticker. Empty DF on non-trading days."""
    from pykrx import stock

    return stock.get_market_ohlcv_by_date(date_str, date_str, ticker)


def get_trading_value(ticker: str, date_str: str) -> pd.DataFrame:
    """Investor-flow DataFrame projected to 외국인/기관합계/개인 (RESEARCH §1.2)."""
    from pykrx import stock

    df = stock.get_market_trading_value_by_date(date_str, date_str, ticker)
    if df.empty:
        return df
    return df[["외국인", "기관합계", "개인"]]


def get_shorting_balance(ticker: str, date_str: str) -> pd.DataFrame:
    """Short-balance DataFrame. T+2 lag — may be empty for recent dates."""
    from pykrx import stock

    return stock.get_shorting_balance_by_date(date_str, date_str, ticker)
