"""Unit tests for shared.retry classification + Retry-After (CAP-2)."""

from __future__ import annotations

import pytest
import tenacity
from requests.exceptions import ConnectionError as ReqConnectionError
from requests.exceptions import HTTPError

from shared.retry import (
    is_retryable,
    make_retry_after_wait,
    retry_after_seconds,
)


class _Resp:
    def __init__(self, status: int, headers: dict | None = None) -> None:
        self.status_code = status
        self.headers = headers or {}


def _http_error(status: int, headers: dict | None = None) -> HTTPError:
    exc = HTTPError(f"HTTP {status}")
    exc.response = _Resp(status, headers)  # type: ignore[attr-defined]
    return exc


# ---- is_retryable ------------------------------------------------------------


def test_429_and_503_are_retryable() -> None:
    assert is_retryable(_http_error(429))
    assert is_retryable(_http_error(503))


def test_generic_4xx_not_retryable() -> None:
    for status in (400, 401, 403, 404):
        assert not is_retryable(_http_error(status))


def test_transient_network_errors_retryable() -> None:
    assert is_retryable(ReqConnectionError("socket drop"))


def test_unrelated_exception_not_retryable() -> None:
    assert not is_retryable(ValueError("nope"))


def test_http_error_without_response_not_retryable() -> None:
    assert not is_retryable(HTTPError("no response attached"))


# ---- retry_after_seconds -----------------------------------------------------


def test_retry_after_numeric_parsed() -> None:
    assert retry_after_seconds(_http_error(429, {"Retry-After": "5"})) == 5.0


def test_retry_after_absent_is_none() -> None:
    assert retry_after_seconds(_http_error(429)) is None
    assert retry_after_seconds(ReqConnectionError("x")) is None


def test_retry_after_http_date_not_parsed() -> None:
    # HTTP-date form is intentionally not parsed (backoff covers it).
    assert (
        retry_after_seconds(
            _http_error(429, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})
        )
        is None
    )


# ---- make_retry_after_wait ---------------------------------------------------


class _Outcome:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc
        self.failed = True

    def exception(self) -> BaseException:
        return self._exc


class _State:
    def __init__(self, exc: BaseException) -> None:
        self.outcome = _Outcome(exc)


def test_wait_honors_retry_after_header() -> None:
    wait = make_retry_after_wait(lambda state: 99.0)
    assert wait(_State(_http_error(429, {"Retry-After": "7"}))) == 7.0


def test_wait_falls_back_to_base_without_header() -> None:
    wait = make_retry_after_wait(lambda state: 99.0)
    assert wait(_State(_http_error(429))) == 99.0


# ---- tenacity integration (fast: zero wait) ----------------------------------


def _decorated(sequence: list) -> tuple:
    """Build a tenacity-wrapped fn that yields each item in ``sequence`` per call
    (raising it if it's an exception). Uses is_retryable + zero wait."""
    state = {"n": 0}

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_fixed(0),
        retry=tenacity.retry_if_exception(is_retryable),
        reraise=True,
    )
    def fn():
        i = state["n"]
        state["n"] += 1
        item = sequence[i]
        if isinstance(item, BaseException):
            raise item
        return item

    return fn, state


def test_tenacity_retries_429_then_succeeds() -> None:
    fn, state = _decorated([_http_error(429), "ok"])
    assert fn() == "ok"
    assert state["n"] == 2


def test_tenacity_does_not_retry_404() -> None:
    fn, state = _decorated([_http_error(404)])
    with pytest.raises(HTTPError):
        fn()
    assert state["n"] == 1  # no retry on permanent client error
