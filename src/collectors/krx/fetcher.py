"""KRX fetcher with tenacity retry on transient network errors (COLL-02).

Reuses the Phase 3 DART `_RETRYABLE_EXC` classification verbatim. pykrx
surfaces requests/urllib3 exceptions under the hood for transient flakes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from requests.exceptions import ChunkedEncodingError
from requests.exceptions import ConnectionError as ReqConnectionError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from urllib3.exceptions import ProtocolError

from collectors.krx import client

if TYPE_CHECKING:
    import pandas as pd

_log = logging.getLogger(__name__)

_RETRYABLE_EXC: tuple[type[BaseException], ...] = (
    ReqConnectionError,
    ChunkedEncodingError,
    ProtocolError,
)


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1.0, min=1.0, max=30.0),
    retry=retry_if_exception_type(_RETRYABLE_EXC),
    before_sleep=before_sleep_log(_log, logging.WARNING),
    reraise=True,
)
def fetch_ohlcv(ticker: str, date_str: str) -> pd.DataFrame:
    return client.get_ohlcv(ticker, date_str)


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1.0, min=1.0, max=30.0),
    retry=retry_if_exception_type(_RETRYABLE_EXC),
    before_sleep=before_sleep_log(_log, logging.WARNING),
    reraise=True,
)
def fetch_trading_value(ticker: str, date_str: str) -> pd.DataFrame:
    return client.get_trading_value(ticker, date_str)


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1.0, min=1.0, max=30.0),
    retry=retry_if_exception_type(_RETRYABLE_EXC),
    before_sleep=before_sleep_log(_log, logging.WARNING),
    reraise=True,
)
def fetch_shorting_balance(ticker: str, date_str: str) -> pd.DataFrame:
    return client.get_shorting_balance(ticker, date_str)
