"""Tests for DART fetcher retry behavior (Bug B — quick-260418-asr).

Covers:
- R1: fetch_body retries on requests.ConnectionError up to 5 attempts then raises
- R2: fetch_body retries on urllib3.ProtocolError (RemoteDisconnected wrapper),
      succeeds on attempt 3, returns the body
- R3: before_sleep_log emits a WARNING per retry attempt (visible via caplog)
- R4: non-retryable exception (ValueError) is NOT retried — raises on attempt 1
- R5: ChunkedEncodingError is retried (large 사업보고서 truncation case)

These tests NEVER hit the real DART API — dart-fss pages are mocked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pytest
from requests.exceptions import ChunkedEncodingError
from requests.exceptions import ConnectionError as ReqConnectionError
from urllib3.exceptions import ProtocolError


@dataclass
class _FakePageFlaky:
    """Raises a configurable exception N times via the .html property, then
    returns success text."""

    fail_exc: Exception
    fail_count: int
    success_text: str = "본문 OK"
    calls: list[str] = field(default_factory=list)

    @property
    def html(self) -> str:
        self.calls.append("html")
        if len(self.calls) <= self.fail_count:
            raise self.fail_exc
        return f"<p>{self.success_text}</p>"


@dataclass
class _FakeFilingFlaky:
    rcept_no: str
    pages_list: list[Any]

    @property
    def pages(self) -> list[Any]:
        return self.pages_list

    def to_dict(self, summary: bool = False) -> dict[str, Any]:
        return {"rcept_no": self.rcept_no}


class TestFetcherRetry:
    def test_R1_connection_error_retries_5_attempts_then_raises(self) -> None:
        from collectors.dart import fetcher

        page = _FakePageFlaky(
            fail_exc=ReqConnectionError("socket closed"),
            fail_count=10,  # more than 5 — ensures exhaustion
        )
        filing = _FakeFilingFlaky("20260101000001", [page])

        with pytest.raises(ReqConnectionError):
            fetcher.fetch_body(filing)
        # 5 total attempts — .html accessed exactly 5 times.
        assert len(page.calls) == 5, f"expected 5 attempts, got {len(page.calls)}"

    def test_R2_protocol_error_succeeds_on_third_attempt(self) -> None:
        from collectors.dart import fetcher

        page = _FakePageFlaky(
            fail_exc=ProtocolError("Remote end closed connection without response"),
            fail_count=2,  # fails twice, succeeds on 3rd
            success_text="삼성전자 사업보고서 본문",
        )
        filing = _FakeFilingFlaky("20260101000002", [page])

        body = fetcher.fetch_body(filing)
        assert "삼성전자 사업보고서 본문" in body
        assert len(page.calls) == 3

    def test_R3_warning_logged_per_retry(self, caplog: pytest.LogCaptureFixture) -> None:
        from collectors.dart import fetcher

        page = _FakePageFlaky(
            fail_exc=ProtocolError("truncated stream"),
            fail_count=2,
            success_text="ok body",
        )
        filing = _FakeFilingFlaky("20260101000003", [page])

        with caplog.at_level(logging.WARNING, logger="collectors.dart.fetcher"):
            fetcher.fetch_body(filing)

        # before_sleep_log emits a WARNING per retry sleep — after 2 failures,
        # there should be 2 warnings (one before each retry sleep).
        retry_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(retry_records) >= 2, (
            f"expected ≥2 WARNING records, got {len(retry_records)}: "
            f"{[r.getMessage() for r in retry_records]}"
        )

    def test_R4_non_retryable_raises_on_first_attempt(self) -> None:
        from collectors.dart import fetcher

        page = _FakePageFlaky(
            fail_exc=ValueError("programming bug, not a network flake"),
            fail_count=10,
        )
        filing = _FakeFilingFlaky("20260101000004", [page])

        with pytest.raises(ValueError):
            fetcher.fetch_body(filing)
        # No retry — exactly 1 attempt.
        assert len(page.calls) == 1

    def test_R5_chunked_encoding_error_retried(self) -> None:
        from collectors.dart import fetcher

        page = _FakePageFlaky(
            fail_exc=ChunkedEncodingError("chunked stream truncated"),
            fail_count=1,
            success_text="recovered body",
        )
        filing = _FakeFilingFlaky("20260101000005", [page])

        body = fetcher.fetch_body(filing)
        assert "recovered body" in body
        assert len(page.calls) == 2
