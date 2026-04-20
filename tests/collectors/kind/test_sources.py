"""Unit tests for collectors.kind.sources — DART classification + constants."""

from __future__ import annotations

from collectors.kind.sources import (
    BROWSER_UA,
    DART_EXCHANGE_EVENT_PATTERNS,
    KIND_BASE,
    KIND_UNDISCLOSURE_URL,
    KIND_WARNING_RISKY_URL,
    KindEventType,
    classify_dart_exchange_event,
)


def test_classify_suspension():
    assert classify_dart_exchange_event("주권매매거래정지") == "suspension"
    assert classify_dart_exchange_event("주권매매거래정지기간변경") == "suspension"


def test_classify_watchlist_designation():
    assert (
        classify_dart_exchange_event("기타시장안내(관리종목지정우려종목)")
        == "watchlist_designation"
    )


def test_classify_unfaithful_disclosure():
    assert classify_dart_exchange_event("불성실공시법인지정(공시불이행)") == "unfaithful_disclosure"
    assert classify_dart_exchange_event("불성실공시법인지정(공시번복)") == "unfaithful_disclosure"


def test_classify_returns_none_for_unrelated():
    assert classify_dart_exchange_event("정기공시") is None
    assert classify_dart_exchange_event("") is None
    assert classify_dart_exchange_event(None) is None  # type: ignore[arg-type]


def test_constants_shape():
    assert KIND_BASE == "https://kind.krx.co.kr"
    assert KIND_WARNING_RISKY_URL.startswith(KIND_BASE)
    assert KIND_UNDISCLOSURE_URL.startswith(KIND_BASE)
    assert "Mozilla/5.0" in BROWSER_UA
    assert set(DART_EXCHANGE_EVENT_PATTERNS.keys()) == {
        "suspension",
        "watchlist_designation",
        "unfaithful_disclosure",
    }
    # Enum stable values (D-08)
    assert KindEventType.SUSPENSION.value == "suspension"
    assert KindEventType.UNFAITHFUL_DISCLOSURE.value == "unfaithful_disclosure"
