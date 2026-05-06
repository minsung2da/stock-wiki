"""Phase 8 Plan 02 Task 2: price_snapshot tests (D-08).

Covers:
- render_prices_md: pure function, frontmatter `as_of` + ticker × close table.
- Idempotency: same data → same string (no datetime.now() in output).
- run() writes to dashboards/_data/prices.md.
- .gitignore exclusion of dashboards/_data/ (Pitfall 6).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

from ingest.price_snapshot import PriceRow, render_prices_md, run


def _rows() -> list[PriceRow]:
    return [
        PriceRow(ticker="005930", name="삼성전자", latest_close=72000, prices_30d=[]),
        PriceRow(ticker="000660", name="SK하이닉스", latest_close=180000, prices_30d=[]),
    ]


# --- Test 1 ---------------------------------------------------------------
def test_render_prices_md() -> None:
    out = render_prices_md(_rows(), as_of=date(2026, 5, 5))
    assert "as_of: '2026-05-05'" in out or "as_of: 2026-05-05" in out
    assert "## Latest Close" in out
    assert "005930" in out
    assert "삼성전자" in out
    assert "72000" in out
    assert "180000" in out


# --- Test 2 ---------------------------------------------------------------
def test_prices_md_idempotent() -> None:
    """Same inputs → same output, every call (no datetime.now())."""
    a = render_prices_md(_rows(), as_of=date(2026, 5, 5))
    b = render_prices_md(_rows(), as_of=date(2026, 5, 5))
    assert a == b


# --- Test 3 ---------------------------------------------------------------
def test_run_writes_to_dashboards_data(tmp_path: Path) -> None:
    """run() places prices.md under dashboards/_data/."""
    fake_rows = _rows()
    fake_as_of = date(2026, 5, 5)

    with patch(
        "ingest.price_snapshot.collect_prices",
        return_value=(fake_rows, fake_as_of),
    ):
        wrote = run(engine=None, repo_root=tmp_path)

    out = tmp_path / "dashboards" / "_data" / "prices.md"
    assert out.exists()
    assert wrote is True
    text = out.read_text(encoding="utf-8")
    assert "as_of" in text
    assert "2026-05-05" in text


# --- Test 4 ---------------------------------------------------------------
def test_gitignore_excludes_dashboards_data() -> None:
    """Pitfall 6: dashboards/_data/ must be gitignored (derived cache)."""
    repo_root = Path(__file__).resolve().parents[2]
    gi = (repo_root / ".gitignore").read_text(encoding="utf-8")
    assert "dashboards/_data/" in gi
