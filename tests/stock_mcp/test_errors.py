"""Phase 6 Plan 06-02 Task 1: ErrorCode enum extension tests.

Verifies that the six new Phase 6 error codes exist and serialize correctly
without disturbing the original Phase 3 codes.
"""

from __future__ import annotations

from stock_mcp.errors import ErrorCode


def test_phase3_codes_preserved() -> None:
    # Sanity: existing codes still present (no reordering damage).
    for name in (
        "SEARCH_TIMEOUT",
        "INVALID_TICKER",
        "DB_UNAVAILABLE",
        "EMBEDDING_FAILED",
        "BM25_FAILED",
        "INTERNAL",
    ):
        assert hasattr(ErrorCode, name), f"missing legacy ErrorCode.{name}"


def test_phase6_codes_exist_and_serialize() -> None:
    expected = {
        "WRITE_FORBIDDEN": "WRITE_FORBIDDEN",
        "INVALID_FRONTMATTER": "INVALID_FRONTMATTER",
        "NOT_FOUND": "NOT_FOUND",
        "PATH_NOT_FOUND": "PATH_NOT_FOUND",
        "STALE_DATA": "STALE_DATA",
        "INVALID_DATE": "INVALID_DATE",
    }
    for name, value in expected.items():
        member = getattr(ErrorCode, name)
        assert member.value == value, f"ErrorCode.{name}.value != {value!r}"


def test_invalid_date_present_for_get_recent_events() -> None:
    # Plan 06-04 (get_recent_events) consumes INVALID_DATE on bad `since`.
    assert ErrorCode.INVALID_DATE.value == "INVALID_DATE"
