"""Phase 8 Plan 03 — Task 2: dashboards/events-this-week.md skeleton (D-09)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = REPO_ROOT / "dashboards" / "events-this-week.md"


def _read() -> str:
    assert DASHBOARD_PATH.exists(), f"Missing {DASHBOARD_PATH}"
    return DASHBOARD_PATH.read_text(encoding="utf-8")


def test_file_exists_with_dataview() -> None:
    """D-09: vault/raw FROM clause + ```dataview block."""
    content = _read()
    block_count = sum(
        1 for line in content.splitlines() if line.strip() == "```dataview"
    )
    assert block_count >= 1, (
        f"events-this-week.md must have >=1 ```dataview block; found {block_count}"
    )
    assert "vault/raw" in content, (
        "events-this-week.md must reference vault/raw (D-09 FROM clause)"
    )


def test_event_type_priority_visible() -> None:
    """D-09: event_type sort priority traces in DQL or prose."""
    content = _read()
    assert "event_type" in content, (
        "events-this-week.md must surface event_type ordering (D-09 priority)"
    )


def test_seven_day_window() -> None:
    """D-09: 7-day window expression."""
    content = _read()
    assert "dur(7 days)" in content, (
        "events-this-week.md must use dur(7 days) day window (D-09)"
    )


def test_no_dataviewjs() -> None:
    """D-18 guard."""
    content = _read()
    assert "```dataviewjs" not in content, (
        "T-08-03-01: dataviewjs must NOT appear in events-this-week.md"
    )
