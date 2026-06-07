"""Thin pykrx wrapper for KRX fundamental valuation metrics (D-06).

No secrets required. pykrx scrapes public KRX/Naver endpoints. Mirrors
``collectors.krx.client`` shape — a lazy ``from pykrx import stock`` inside each
function keeps the import cost off module load and lets tests monkeypatch the
fetcher boundary above this layer.

Veto #6: the returned values (PER/PBR/EPS/BPS) are pure numbers — they flow into
typed NUMERIC columns and are NEVER embedded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def get_market_fundamental(ticker: str, date_str: str) -> pd.DataFrame:
    """One-day fundamentals DataFrame for a ticker (PER/PBR/EPS/BPS/DIV/DPS/BPS).

    Empty DataFrame on non-trading days / illiquid names. ``date_str`` is the
    ``YYYYMMDD`` business day; the call asks pykrx for a single-day window.
    """
    from pykrx import stock

    return stock.get_market_fundamental_by_date(date_str, date_str, ticker)
