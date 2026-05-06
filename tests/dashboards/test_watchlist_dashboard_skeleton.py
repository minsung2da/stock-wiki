"""Phase 8 Plan 03 — Task 2: dashboards/watchlist.md skeleton verification (D-07)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = REPO_ROOT / "dashboards" / "watchlist.md"


def _read() -> str:
    assert DASHBOARD_PATH.exists(), f"Missing {DASHBOARD_PATH}"
    return DASHBOARD_PATH.read_text(encoding="utf-8")


def test_file_exists_with_dataview() -> None:
    """D-07: SoT shared with notes/private/portfolio.md ## Watchlist."""
    content = _read()
    block_count = sum(
        1 for line in content.splitlines() if line.strip() == "```dataview"
    )
    assert block_count >= 1, (
        f"watchlist.md must have >=1 ```dataview block; found {block_count}"
    )
    assert (
        "notes/private/portfolio.md" in content or "dashboards/_data" in content
    ), (
        "watchlist.md must reference notes/private/portfolio.md or dashboards/_data (D-07 SoT)"
    )


def test_no_dataviewjs() -> None:
    """D-18 guard."""
    content = _read()
    assert "```dataviewjs" not in content, (
        "T-08-03-01: dataviewjs must NOT appear in watchlist.md"
    )
