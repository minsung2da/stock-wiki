"""Phase 8 Plan 03 — Task 2: dashboards/portfolio.md skeleton verification."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = REPO_ROOT / "dashboards" / "portfolio.md"


def _read() -> str:
    assert DASHBOARD_PATH.exists(), f"Missing {DASHBOARD_PATH}"
    return DASHBOARD_PATH.read_text(encoding="utf-8")


def test_file_exists_with_dataview_block() -> None:
    """D-06 + D-08: ≥2 DQL blocks (holdings 평가액 + 7일 events) + dashboards/_data ref."""
    content = _read()
    dql_blocks = content.count("```dataview\n") + content.count("```dataview ")
    # also count fenced opens at line start
    block_count = sum(
        1 for line in content.splitlines() if line.strip() == "```dataview"
    )
    assert block_count >= 2, (
        f"portfolio.md must have >=2 ```dataview blocks (holdings 평가액 + 7일 events); "
        f"found {block_count}"
    )
    assert "dashboards/_data" in content, (
        "portfolio.md must reference dashboards/_data (prices.md SoT per D-08)"
    )


def test_no_dataviewjs() -> None:
    """D-18 + T-08-03-01: ```dataviewjs absent."""
    content = _read()
    assert "```dataviewjs" not in content, (
        "T-08-03-01: dataviewjs must NOT appear in portfolio.md"
    )


def test_freshness_indicator() -> None:
    """D-08 step 3: 'as_of' freshness label visible."""
    content = _read()
    assert "as_of" in content, (
        "portfolio.md must surface as_of freshness indicator (D-08 — '전영업일 종가 기준')"
    )
