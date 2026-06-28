"""Tests for DART fetcher retry behavior.

The body source is the OpenDART document API (``document.xml``); ``fetch_body``
wraps the HTTP call (``fetcher._http_get``) in a tenacity retry. These tests
exercise the retry policy by patching that seam — they NEVER hit the network.

Covers:
- R1: retries on requests.ConnectionError up to 5 attempts then raises
- R2: retries on urllib3.ProtocolError (RemoteDisconnected wrapper), succeeds
      on attempt 3, returns the body
- R3: before_sleep_log emits a WARNING per retry attempt (visible via caplog)
- R4: non-retryable exception (ValueError) is NOT retried — raises on attempt 1
- R5: ChunkedEncodingError is retried (large 사업보고서 truncation case)
- R6: requests.HTTPError (transient 5xx from the OpenDART edge) is retried
- R7: OpenDART status 020 throttle envelope retries then succeeds (Bug 2)
- R8: persistent status 020 reraises DartThrottleError after exactly 5 attempts
- R9: status 014 (file does not exist) is permanent — NOT retried (1 attempt)
"""

from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass

import pytest
from requests.exceptions import ChunkedEncodingError
from requests.exceptions import ConnectionError as ReqConnectionError
from requests.exceptions import HTTPError as ReqHTTPError
from tenacity import wait_none
from urllib3.exceptions import ProtocolError


@dataclass
class _FakeFiling:
    rcept_no: str = "20260101000001"


@dataclass
class _FakeResp:
    content: bytes

    def raise_for_status(self) -> None:  # pragma: no cover - trivial
        return None


def _zip_bytes(text: str) -> bytes:
    """A one-member document ZIP whose XML strips down to ``text``."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("20260101000001.xml", f"<DOC>{text}</DOC>".encode("utf-8"))
    return buf.getvalue()


class _FlakyGet:
    """Stand-in for fetcher._http_get: fail N times, then return a ZIP response."""

    def __init__(self, fail_exc: Exception, fail_count: int, success_text: str):
        self.fail_exc = fail_exc
        self.fail_count = fail_count
        self.success_content = _zip_bytes(success_text)
        self.calls = 0

    def __call__(self, rcept_no: str, api_key: str) -> _FakeResp:
        self.calls += 1
        if self.calls <= self.fail_count:
            raise self.fail_exc
        return _FakeResp(self.success_content)


def _envelope(status: str, message: str) -> bytes:
    """An OpenDART non-ZIP error envelope carrying ``status``/``message``."""
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        + f"<result><status>{status}</status>"
        f"<message>{message}</message></result>".encode("utf-8")
    )


class _EnvelopeThenZip:
    """Return an OpenDART error envelope N times, then a one-member ZIP.

    fetch_body inspects the envelope at the application layer and (for a
    transient status) raises a retryable DartThrottleError that tenacity then
    retries — so this seam stays a plain successful HTTP response each call.
    """

    def __init__(self, status: str, message: str, fail_count: int, success_text: str):
        self.envelope = _envelope(status, message)
        self.fail_count = fail_count
        self.success_content = _zip_bytes(success_text)
        self.calls = 0

    def __call__(self, rcept_no: str, api_key: str) -> _FakeResp:
        self.calls += 1
        if self.calls <= self.fail_count:
            return _FakeResp(self.envelope)
        return _FakeResp(self.success_content)


@pytest.fixture(autouse=True)
def _fast_retry_and_key(monkeypatch):
    """Make retries instant and inject a dummy API key for every retry test."""
    from collectors.dart import fetcher

    monkeypatch.setattr("collectors.dart.client.get_api_key", lambda: "dummy-key")
    # Override the tenacity wait so the 5-attempt path does not sleep 1+2+4+8s.
    monkeypatch.setattr(fetcher.fetch_body.retry, "wait", wait_none())


class TestFetcherRetry:
    def test_R1_connection_error_retries_5_attempts_then_raises(self, monkeypatch) -> None:
        from collectors.dart import fetcher

        get = _FlakyGet(ReqConnectionError("socket closed"), fail_count=10,
                        success_text="never reached")
        monkeypatch.setattr(fetcher, "_http_get", get)

        with pytest.raises(ReqConnectionError):
            fetcher.fetch_body(_FakeFiling())
        assert get.calls == 5, f"expected 5 attempts, got {get.calls}"

    def test_R2_protocol_error_succeeds_on_third_attempt(self, monkeypatch) -> None:
        from collectors.dart import fetcher

        get = _FlakyGet(
            ProtocolError("Remote end closed connection without response"),
            fail_count=2,
            success_text="삼성전자 사업보고서 본문",
        )
        monkeypatch.setattr(fetcher, "_http_get", get)

        body = fetcher.fetch_body(_FakeFiling())
        assert "삼성전자 사업보고서 본문" in body
        assert get.calls == 3

    def test_R3_warning_logged_per_retry(self, monkeypatch,
                                         caplog: pytest.LogCaptureFixture) -> None:
        from collectors.dart import fetcher

        get = _FlakyGet(ProtocolError("truncated stream"), fail_count=2,
                        success_text="ok body")
        monkeypatch.setattr(fetcher, "_http_get", get)

        with caplog.at_level(logging.WARNING, logger="collectors.dart.fetcher"):
            fetcher.fetch_body(_FakeFiling())

        retry_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(retry_records) >= 2, (
            f"expected >=2 WARNING records, got {len(retry_records)}: "
            f"{[r.getMessage() for r in retry_records]}"
        )

    def test_R4_non_retryable_raises_on_first_attempt(self, monkeypatch) -> None:
        from collectors.dart import fetcher

        get = _FlakyGet(ValueError("programming bug, not a network flake"),
                        fail_count=10, success_text="x")
        monkeypatch.setattr(fetcher, "_http_get", get)

        with pytest.raises(ValueError):
            fetcher.fetch_body(_FakeFiling())
        assert get.calls == 1

    def test_R5_chunked_encoding_error_retried(self, monkeypatch) -> None:
        from collectors.dart import fetcher

        get = _FlakyGet(ChunkedEncodingError("chunked stream truncated"),
                        fail_count=1, success_text="recovered body")
        monkeypatch.setattr(fetcher, "_http_get", get)

        body = fetcher.fetch_body(_FakeFiling())
        assert "recovered body" in body
        assert get.calls == 2

    def test_R6_http_error_retried(self, monkeypatch) -> None:
        from collectors.dart import fetcher

        get = _FlakyGet(ReqHTTPError("503 Service Unavailable"),
                        fail_count=1, success_text="edge recovered")
        monkeypatch.setattr(fetcher, "_http_get", get)

        body = fetcher.fetch_body(_FakeFiling())
        assert "edge recovered" in body
        assert get.calls == 2

    def test_status_020_throttle_retries_then_succeeds(self, monkeypatch) -> None:
        from collectors.dart import fetcher

        get = _EnvelopeThenZip("020", "requests exceeded the limit",
                               fail_count=2, success_text="삼성전자 본문 recovered")
        monkeypatch.setattr(fetcher, "_http_get", get)

        body = fetcher.fetch_body(_FakeFiling())
        assert "삼성전자 본문 recovered" in body
        assert get.calls == 3  # 020 twice, then ZIP

    def test_status_020_exhausts_then_raises_throttle(self, monkeypatch) -> None:
        from collectors.dart import fetcher

        get = _EnvelopeThenZip("020", "requests exceeded the limit",
                               fail_count=99, success_text="never reached")
        monkeypatch.setattr(fetcher, "_http_get", get)

        with pytest.raises(fetcher.DartThrottleError):
            fetcher.fetch_body(_FakeFiling())
        assert get.calls == 5  # stop_after_attempt(5)

    def test_status_014_not_retried(self, monkeypatch) -> None:
        from collectors.dart import fetcher

        get = _EnvelopeThenZip("014", "file does not exist",
                               fail_count=99, success_text="never reached")
        monkeypatch.setattr(fetcher, "_http_get", get)

        with pytest.raises(fetcher.DartDocumentError) as exc:
            fetcher.fetch_body(_FakeFiling())
        assert not isinstance(exc.value, fetcher.DartThrottleError)
        assert get.calls == 1  # permanent → no retry
