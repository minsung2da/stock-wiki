"""KRX fetcher with tenacity retry on transient errors + HTTP 429/503 (COLL-02, CAP-2).

Retry classification is ``shared.retry.is_retryable`` (transient network flakes
plus throttle/unavailable statuses, honoring ``Retry-After``); pykrx surfaces
requests/urllib3 exceptions under the hood for transient flakes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from collectors.krx import client
from shared.retry import is_retryable, make_retry_after_wait

if TYPE_CHECKING:
    import pandas as pd

_log = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(5),
    wait=make_retry_after_wait(wait_exponential(multiplier=1.0, min=1.0, max=30.0)),
    retry=retry_if_exception(is_retryable),
    before_sleep=before_sleep_log(_log, logging.WARNING),
    reraise=True,
)
def fetch_ohlcv(ticker: str, date_str: str) -> pd.DataFrame:
    return client.get_ohlcv(ticker, date_str)


@retry(
    stop=stop_after_attempt(5),
    wait=make_retry_after_wait(wait_exponential(multiplier=1.0, min=1.0, max=30.0)),
    retry=retry_if_exception(is_retryable),
    before_sleep=before_sleep_log(_log, logging.WARNING),
    reraise=True,
)
def fetch_trading_value(ticker: str, date_str: str) -> pd.DataFrame:
    return client.get_trading_value(ticker, date_str)


@retry(
    stop=stop_after_attempt(5),
    wait=make_retry_after_wait(wait_exponential(multiplier=1.0, min=1.0, max=30.0)),
    retry=retry_if_exception(is_retryable),
    before_sleep=before_sleep_log(_log, logging.WARNING),
    reraise=True,
)
def fetch_shorting_balance(ticker: str, date_str: str) -> pd.DataFrame:
    return client.get_shorting_balance(ticker, date_str)


@retry(
    stop=stop_after_attempt(5),
    wait=make_retry_after_wait(wait_exponential(multiplier=1.0, min=1.0, max=30.0)),
    retry=retry_if_exception(is_retryable),
    before_sleep=before_sleep_log(_log, logging.WARNING),
    reraise=True,
)
def fetch_market_ohlcv(date_str: str) -> pd.DataFrame:
    """Whole-market one-day OHLCV (CAP-3) — one scrape covering every ticker."""
    return client.get_market_ohlcv_all(date_str)
