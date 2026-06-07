"""Fundamentals fetcher with tenacity retry on transient network errors (D-06).

Reuses the KRX ``_RETRYABLE_EXC`` classification verbatim (it is itself the
Phase-3 DART set). pykrx surfaces requests/urllib3 exceptions under the hood for
transient flakes. Mirrors ``collectors.krx.fetcher`` exactly.
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

from collectors.fundamentals import client

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
def fetch_market_fundamental(ticker: str, date_str: str) -> pd.DataFrame:
    return client.get_market_fundamental(ticker, date_str)
