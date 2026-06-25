"""Shared tenacity retry classification for collector HTTP fetches (CAP-2).

Extends the transient-network retry set to also cover HTTP **429** (Too Many
Requests) and **503** (Service Unavailable) — explicit throttle / availability
signals — WITHOUT retrying other 4xx (permanent client errors fail fast, which
matters most on gray-area scrapers where wasted requests raise IP-ban risk).
A server-provided ``Retry-After`` header is honored when present.

Used by the gray-area scraper clients (``news``, ``krx``). The keyed-API
fetchers (``dart`` Open DART, ``fundamentals`` pykrx) keep their network-only
classification for now and can adopt this helper later — their wrapped calls
do not surface 429 as an ``HTTPError`` today (they return empty frames), so the
extension would be a no-op there.
"""

from __future__ import annotations

from requests.exceptions import ChunkedEncodingError
from requests.exceptions import ConnectionError as ReqConnectionError
from requests.exceptions import HTTPError
from urllib3.exceptions import ProtocolError

__all__ = [
    "NETWORK_RETRY_EXC",
    "RETRYABLE_STATUS",
    "is_retryable",
    "retry_after_seconds",
    "make_retry_after_wait",
]

# Transient network failures (truncated bodies, encoding flakes, socket drops).
NETWORK_RETRY_EXC: tuple[type[BaseException], ...] = (
    ReqConnectionError,
    ChunkedEncodingError,
    ProtocolError,
)

# HTTP statuses that mean "back off and retry", not "you did something wrong".
RETRYABLE_STATUS: frozenset[int] = frozenset({429, 503})


def _status_of(exc: BaseException) -> int | None:
    """Best-effort HTTP status code from a requests HTTPError, else None."""
    resp = getattr(exc, "response", None)
    if resp is None:
        return None
    return getattr(resp, "status_code", None)


def is_retryable(exc: BaseException) -> bool:
    """True for transient network errors and HTTP 429/503; False otherwise.

    Generic 4xx (400/403/404…) are NOT retried — they are permanent client
    errors, and retrying them wastes requests against a rate-sensitive source.
    """
    if isinstance(exc, NETWORK_RETRY_EXC):
        return True
    if isinstance(exc, HTTPError):
        return _status_of(exc) in RETRYABLE_STATUS
    return False


def retry_after_seconds(exc: BaseException | None) -> float | None:
    """Parse a numeric ``Retry-After`` (delta-seconds) header from an HTTPError.

    Returns ``None`` when the exception is not an HTTPError, has no response,
    lacks the header, or the value is not a non-negative number. The HTTP-date
    form of ``Retry-After`` is intentionally not parsed — exponential backoff
    covers that case.
    """
    if not isinstance(exc, HTTPError):
        return None
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None) if resp is not None else None
    if not headers:
        return None
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        secs = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return secs if secs >= 0 else None


def make_retry_after_wait(base_wait):
    """Wrap a tenacity wait strategy so a server ``Retry-After`` takes priority.

    ``base_wait`` is any tenacity wait callable (e.g. ``wait_exponential(...)``);
    when the failing attempt carried a numeric ``Retry-After``, that value (in
    seconds) is used instead of the base backoff.
    """

    def _wait(retry_state) -> float:
        outcome = getattr(retry_state, "outcome", None)
        exc = outcome.exception() if outcome is not None and outcome.failed else None
        ra = retry_after_seconds(exc)
        if ra is not None:
            return ra
        return base_wait(retry_state)

    return _wait
