"""collect_fundamentals integration tests — Plan 03-05 Task 1 (DB-state assertions).

Each test:
1. Materializes a temporary repo root via ``tmp_path`` with a
   ``notes/private/portfolio.md`` so ``Portfolio.load(Path("."))`` resolves.
2. Mocks the pykrx fundamentals fetcher + the dart-fss ROE source via
   ``monkeypatch`` (NO live network — environment note).
3. Invokes ``collect_fundamentals`` and asserts both the returned stats dict AND
   the ``fundamentals`` table state via SQL.

Hard Veto #6 reminder: the fundamentals table is pure NUMERIC; we assert on
per/pbr/eps/bps/roe and NEVER on any body_md / embedding column (none exist).

``fundamentals`` is NOT in tests/conftest.py ``_LIVE_TABLES`` (added in migration
0008 after that list was authored), so ``pg_clean`` does not truncate it. Each
test DELETEs the fundamentals rows it owns up-front for isolation.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text

from collectors.fundamentals import collect_fundamentals
from collectors.fundamentals import fetcher as fund_fetcher
from collectors.fundamentals import roe as fund_roe

pytestmark = pytest.mark.db


_SAMSUNG_PORTFOLIO = (
    "---\n"
    "holdings:\n"
    '  - ticker: "005930"\n'
    "    qty: 1\n"
    "    avg_cost: 70000\n"
    "watchlist: []\n"
    "---\n"
    "# Portfolio\n"
)


def _write_portfolio(tmp_path: Path, content: str = _SAMSUNG_PORTFOLIO) -> None:
    p = tmp_path / "notes" / "private"
    p.mkdir(parents=True, exist_ok=True)
    (p / "portfolio.md").write_text(content, encoding="utf-8")


def _fundamental_df() -> pd.DataFrame:
    """One-row pykrx fundamentals frame (ASCII labels as pykrx returns them)."""
    return pd.DataFrame(
        [{"BPS": 50000.0, "PER": 12.5, "PBR": 1.4, "EPS": 5600.0, "DIV": 2.1, "DPS": 1416.0}]
    )


def _empty_fundamental_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["BPS", "PER", "PBR", "EPS", "DIV", "DPS"])


def _clean_fundamentals(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM fundamentals"))


def _count_fundamentals(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM fundamentals")).scalar_one()


def _fund_row(engine, ticker: str, fdate: date):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT ticker, fdate, per, pbr, eps, bps, roe, dividend_yield, dps, corp_code, source "
                "FROM fundamentals WHERE ticker=:t AND fdate=:d"
            ),
            {"t": ticker, "d": fdate},
        ).first()


def test_collect_fundamentals_inserts_typed_row(tmp_path: Path, seeded_engine, monkeypatch) -> None:
    """pykrx PER/PBR/EPS/BPS + dart-fss ROE → one typed fundamentals row."""
    _clean_fundamentals(seeded_engine)
    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(fund_fetcher, "fetch_market_fundamental", lambda t, d: _fundamental_df())
    # ROE = 당기순이익 / 자본총계 = 100 / 1000 = 0.1
    monkeypatch.setattr(fund_roe, "compute_roe", lambda cc, bgn: 0.1)

    stats = collect_fundamentals(engine=seeded_engine, since="2026-04-17")

    assert stats["inserted"] == 1
    assert stats["updated"] == 0
    assert stats["skipped"] == 0
    assert stats["failed"] == []

    row = _fund_row(seeded_engine, "005930", date(2026, 4, 17))
    assert row is not None
    assert float(row.per) == pytest.approx(12.5)
    assert float(row.pbr) == pytest.approx(1.4)
    assert float(row.eps) == pytest.approx(5600.0)
    assert float(row.bps) == pytest.approx(50000.0)
    assert float(row.dividend_yield) == pytest.approx(2.1)
    assert float(row.dps) == pytest.approx(1416.0)
    assert float(row.roe) == pytest.approx(0.1)
    assert row.corp_code == "00126380"
    assert row.source == "fundamentals"


def test_dividend_update_and_idempotence(tmp_path: Path, seeded_engine, monkeypatch) -> None:
    _clean_fundamentals(seeded_engine)
    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)
    frame = _fundamental_df()
    monkeypatch.setattr(fund_fetcher, "fetch_market_fundamental", lambda t, d: frame)
    monkeypatch.setattr(fund_roe, "compute_roe", lambda cc, bgn: 0.1)
    assert collect_fundamentals(engine=seeded_engine, since="2026-04-17")["inserted"] == 1
    assert collect_fundamentals(engine=seeded_engine, since="2026-04-17")["skipped"] == 1
    frame.loc[0, "DIV"] = 0
    frame.loc[0, "DPS"] = 1500
    assert collect_fundamentals(engine=seeded_engine, since="2026-04-17")["updated"] == 1
    row = _fund_row(seeded_engine, "005930", date(2026, 4, 17))
    assert row.dividend_yield == 0
    assert row.dps == 1500
    frame.loc[0, "DIV"] = float("nan")
    frame.loc[0, "DPS"] = float("nan")
    assert collect_fundamentals(engine=seeded_engine, since="2026-04-17")["updated"] == 1
    row = _fund_row(seeded_engine, "005930", date(2026, 4, 17))
    assert row.dividend_yield is None and row.dps is None
    assert _count_fundamentals(seeded_engine) == 1


def test_collect_fundamentals_records_run(tmp_path: Path, seeded_engine, monkeypatch) -> None:
    """record_collector_run(engine, 'fundamentals', ...) inserts a collector_runs
    row — no ValueError, source allowed by Plan 03-01."""
    _clean_fundamentals(seeded_engine)
    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(fund_fetcher, "fetch_market_fundamental", lambda t, d: _fundamental_df())
    monkeypatch.setattr(fund_roe, "compute_roe", lambda cc, bgn: 0.1)

    collect_fundamentals(engine=seeded_engine, since="2026-04-17")

    with seeded_engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM collector_runs WHERE source = 'fundamentals'")
        ).scalar_one()
    assert n == 1


def test_collect_fundamentals_missing_entity_isolation(
    tmp_path: Path, seeded_engine, monkeypatch
) -> None:
    """R-03: ticker missing from entities → stats.failed, no DB row."""
    _clean_fundamentals(seeded_engine)
    _write_portfolio(
        tmp_path,
        "---\n"
        "holdings:\n"
        '  - ticker: "005930"\n'
        "    qty: 1\n"
        "    avg_cost: 70000\n"
        "watchlist:\n"
        '  - "999999"\n'
        "---\n"
        "# Portfolio\n",
    )
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(fund_fetcher, "fetch_market_fundamental", lambda t, d: _fundamental_df())
    monkeypatch.setattr(fund_roe, "compute_roe", lambda cc, bgn: 0.1)

    stats = collect_fundamentals(engine=seeded_engine, since="2026-04-17")

    assert stats["inserted"] == 1
    failed = {f["doc"]: f["error"] for f in stats["failed"]}
    assert failed.get("999999") == "missing_entity"

    assert _count_fundamentals(seeded_engine) == 1
    assert _fund_row(seeded_engine, "005930", date(2026, 4, 17)) is not None
    assert _fund_row(seeded_engine, "999999", date(2026, 4, 17)) is None


def test_collect_fundamentals_empty_frame_skips(tmp_path: Path, seeded_engine, monkeypatch) -> None:
    """Empty pykrx frame → no row, skipped++, no failed entry."""
    _clean_fundamentals(seeded_engine)
    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        fund_fetcher, "fetch_market_fundamental", lambda t, d: _empty_fundamental_df()
    )
    monkeypatch.setattr(fund_roe, "compute_roe", lambda cc, bgn: 0.1)

    stats = collect_fundamentals(engine=seeded_engine, since="2026-04-17")

    assert stats["skipped"] == 1
    assert stats["inserted"] == 0
    assert stats["failed"] == []
    assert _count_fundamentals(seeded_engine) == 0


def test_collect_fundamentals_roe_coalesce_fill_in(
    tmp_path: Path, seeded_engine, monkeypatch
) -> None:
    """Run 1: ROE unavailable (None). Run 2: same date, ROE arrives → 'updated',
    roe filled; PER/PBR preserved. A later pykrx-only refresh never NULL-clobbers."""
    _clean_fundamentals(seeded_engine)
    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(fund_fetcher, "fetch_market_fundamental", lambda t, d: _fundamental_df())

    # Run 1: ROE source returns None
    monkeypatch.setattr(fund_roe, "compute_roe", lambda cc, bgn: None)
    stats1 = collect_fundamentals(engine=seeded_engine, since="2026-04-17")
    assert stats1["inserted"] == 1
    row1 = _fund_row(seeded_engine, "005930", date(2026, 4, 17))
    assert row1.roe is None

    # Run 2: ROE arrives
    monkeypatch.setattr(fund_roe, "compute_roe", lambda cc, bgn: 0.0789)
    stats2 = collect_fundamentals(engine=seeded_engine, since="2026-04-17")
    assert stats2["updated"] == 1
    assert stats2["inserted"] == 0
    row2 = _fund_row(seeded_engine, "005930", date(2026, 4, 17))
    assert float(row2.roe) == pytest.approx(0.0789)
    # PER/PBR preserved through the fill-in
    assert float(row2.per) == pytest.approx(12.5)

    # Run 3: pykrx-only refresh (ROE None again) must NOT NULL-clobber the ROE
    monkeypatch.setattr(fund_roe, "compute_roe", lambda cc, bgn: None)
    stats3 = collect_fundamentals(engine=seeded_engine, since="2026-04-17")
    assert stats3["skipped"] == 1  # COALESCE-None on roe → no change
    row3 = _fund_row(seeded_engine, "005930", date(2026, 4, 17))
    assert float(row3.roe) == pytest.approx(0.0789)


def test_collect_fundamentals_no_engine_raises(tmp_path: Path, monkeypatch) -> None:
    """engine=None must raise — collector contract requires DB for FK lookup."""
    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(RuntimeError, match="engine"):
        collect_fundamentals(engine=None, since="2026-04-17")
