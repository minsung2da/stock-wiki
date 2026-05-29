"""Tests for the macro collector (ECOS + FRED) — Phase 1 Plan 01-03.

Post-cutover: assertions are against Postgres row state (no Markdown vault).
The legacy ``writer.write_macro_doc`` path is exercised by no test here —
``writer.py`` stays on disk only because plan 01-09 owns physical deletion.

Coverage:
- catalog loading from .planning/macro_series.yaml (carry-over)
- collect_macro: INSERTs observations into macro_series
- collect_macro: R-06 revision detection surfaces via structured log extra
- collect_macro: catalog series filter (empty / non-existent)
- collect_macro: per-series soft-fail isolation (R-05)
- collect_macro: engine=None raises CollectorConfigError
- collect_macro: no Markdown directory created (CI fence against writer
  resurrection)
- fetcher: client-side ITEM_CODE1 filter + Korean column name support
  (Gap-04-04 / Gap-04-07 regression guards — kept verbatim)
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import yaml
from sqlalchemy import text

# -------- catalog (carry-over) ----------------------------------------------


def test_load_catalog_returns_two_ecos_and_two_fred():
    from collectors.macro import load_catalog

    cat = load_catalog()
    labels = {e["label"] for e in cat["ecos"]} | {e["label"] for e in cat["fred"]}
    assert {"base_rate_kr", "usd_krw", "us_10y", "wti"}.issubset(labels)
    for e in cat["ecos"]:
        assert e["series_id"] and e["item_code"]


def test_load_catalog_accepts_override_path(tmp_path: Path):
    from collectors.macro import load_catalog

    p = tmp_path / "cat.yaml"
    p.write_text(
        yaml.safe_dump(
            {
                "ecos": [{"label": "x", "series_id": "A", "item_code": "B", "cycle": "D"}],
                "fred": [{"label": "y", "series_id": "Z"}],
            }
        )
    )
    cat = load_catalog(p)
    assert cat["ecos"][0]["series_id"] == "A"
    assert cat["fred"][0]["series_id"] == "Z"


# -------- collect_macro (DB-based, post-cutover) ----------------------------


def _fixtures_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures"


def _ecos_fixture_to_fetcher_output(path: Path, item_code: str | None = None) -> list[dict]:
    """Transform raw ECOS fixture rows into fetcher output shape (date as date object).

    db_writer.upsert_macro_observations expects ``date`` to be a real ``datetime.date``
    (not an ISO string). The fetcher returns ISO strings (the fixture path), so we
    parse here for the new contract.
    """
    rows = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for r in rows:
        if item_code is not None and str(r.get("ITEM_CODE1", "")) != item_code:
            continue
        t = str(r["TIME"])
        out.append(
            {
                "date": date(int(t[:4]), int(t[4:6]), int(t[6:8])),
                "value": float(r["DATA_VALUE"]),
            }
        )
    return out


def _fred_fixture(path: Path) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for r in rows:
        d_str = r["date"]
        y, m, d = d_str.split("-")
        out.append({"date": date(int(y), int(m), int(d)), "value": float(r["value"])})
    return out


def _catalog_path() -> Path:
    return Path(__file__).resolve().parents[3] / ".planning" / "macro_series.yaml"


@pytest.fixture
def fixture_fetchers(monkeypatch):
    """Monkeypatch fetcher functions to return fixture data keyed by series_id."""
    fx = _fixtures_dir()
    ecos_map = {
        "722Y001": _ecos_fixture_to_fetcher_output(
            fx / "ecos/base_rate_kr.json", item_code="0101000"
        ),
        "731Y001": _ecos_fixture_to_fetcher_output(fx / "ecos/usd_krw.json", item_code="0000001"),
    }
    fred_map = {
        "DGS10": _fred_fixture(fx / "fred/DGS10.json"),
        "DCOILWTICO": _fred_fixture(fx / "fred/DCOILWTICO.json"),
    }
    monkeypatch.setenv("ECOS_API_KEY", "x")
    monkeypatch.setenv("FRED_API_KEY", "y")

    from collectors.macro import client as macro_client
    from collectors.macro import fetcher as macro_fetcher

    # Skip real library imports
    monkeypatch.setattr(macro_client, "ecos_client", lambda: object())
    monkeypatch.setattr(macro_client, "fred_client", lambda: object())
    monkeypatch.setattr(
        macro_fetcher,
        "fetch_ecos_series",
        lambda api, series_id, cycle, item_code, **kw: ecos_map[series_id],
    )
    monkeypatch.setattr(
        macro_fetcher,
        "fetch_fred_series",
        lambda fred, series_id, **kw: fred_map[series_id],
    )
    return ecos_map, fred_map


def test_collect_macro_inserts_observations(pg_clean, fixture_fetchers):
    """First pass: every observation lands as INSERT; stats show inserted-only."""
    from collectors.macro import collect_macro

    stats = collect_macro(engine=pg_clean, catalog_path=_catalog_path())
    assert stats["total"] == 4
    assert stats["inserted"] >= 4  # at least one per series (real fixture counts vary)
    assert stats["updated"] == 0
    assert stats["failed"] == []
    # 'succeeded' key no longer in shape (v2.0)
    assert "succeeded" not in stats

    # All four series should have rows in macro_series
    with pg_clean.begin() as conn:
        series_counts = dict(
            conn.execute(
                text(
                    "SELECT series_id, count(*) AS n FROM macro_series GROUP BY series_id"
                )
            ).fetchall()
        )
    assert "722Y001" in series_counts and series_counts["722Y001"] > 0
    assert "731Y001" in series_counts and series_counts["731Y001"] > 0
    assert "DGS10" in series_counts and series_counts["DGS10"] > 0
    assert "DCOILWTICO" in series_counts and series_counts["DCOILWTICO"] > 0


def test_collect_macro_idempotent_rerun_skips_all(pg_clean, fixture_fetchers):
    """Second pass with same fixtures: 0 inserted, 0 updated, all series 'skipped'."""
    from collectors.macro import collect_macro

    collect_macro(engine=pg_clean, catalog_path=_catalog_path())
    # Second identical run
    stats2 = collect_macro(engine=pg_clean, catalog_path=_catalog_path())
    assert stats2["total"] == 4
    assert stats2["inserted"] == 0
    assert stats2["updated"] == 0
    assert stats2["skipped"] == 4
    assert stats2["failed"] == []


def test_collect_macro_revision_detection(pg_clean, fixture_fetchers, monkeypatch, caplog):
    """R-06: second run with same date + different value -> updated + structured log
    extras carry the revision details (consumed by 01-08 into collector_runs.extra)."""
    import logging

    from collectors.macro import collect_macro
    from collectors.macro import fetcher as macro_fetcher

    # First pass uses normal fixtures
    collect_macro(engine=pg_clean, catalog_path=_catalog_path())

    # Pre-read the original DGS10 2026-04-16 value
    with pg_clean.begin() as conn:
        prev = conn.execute(
            text(
                "SELECT value FROM macro_series "
                "WHERE source='fred' AND series_id='DGS10' AND obs_date=:d"
            ),
            {"d": date(2026, 4, 16)},
        ).scalar()
    assert prev is not None
    prev_val = float(prev)

    # Second pass: mutate DGS10 2026-04-16 value (replace with 4.40) to trigger a revision
    def revised(fred, series_id, **kw):
        if series_id == "DGS10":
            return [
                {"date": date(2026, 4, 14), "value": 4.29},
                {"date": date(2026, 4, 15), "value": 4.31},
                {"date": date(2026, 4, 16), "value": 4.40},  # revised
            ]
        return _fred_fixture(_fixtures_dir() / f"fred/{series_id}.json")

    monkeypatch.setattr(macro_fetcher, "fetch_fred_series", revised)

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="collectors.macro"):
        stats = collect_macro(engine=pg_clean, catalog_path=_catalog_path())

    assert stats["updated"] >= 1, stats

    # New value persisted in DB
    with pg_clean.begin() as conn:
        new_val = float(
            conn.execute(
                text(
                    "SELECT value FROM macro_series "
                    "WHERE source='fred' AND series_id='DGS10' AND obs_date=:d"
                ),
                {"d": date(2026, 4, 16)},
            ).scalar()
        )
    assert new_val == 4.40

    # Structured log carries revisions=[{series_id, obs_date, old, new}, ...]
    rev_records = [r for r in caplog.records if r.getMessage() == "collector_run_complete"]
    assert rev_records, "no collector_run_complete log record captured"
    rec = rev_records[-1]
    revisions = getattr(rec, "revisions", None)
    assert revisions is not None, "structured log missing 'revisions' extra"
    dgs10_hits = [r for r in revisions if r["series_id"] == "DGS10"]
    assert dgs10_hits and dgs10_hits[0]["obs_date"] == "2026-04-16"
    assert dgs10_hits[0]["old"] == prev_val
    assert dgs10_hits[0]["new"] == 4.40


def test_collect_macro_empty_series_filter(pg_clean, fixture_fetchers):
    """series=['NotInCatalog'] -> total=0, no DB rows touched."""
    from collectors.macro import collect_macro

    stats = collect_macro(
        engine=pg_clean, series=["NotInCatalog"], catalog_path=_catalog_path()
    )
    assert stats["total"] == 0
    assert stats["inserted"] == 0
    assert stats["updated"] == 0
    assert stats["skipped"] == 0
    assert stats["failed"] == []

    with pg_clean.begin() as conn:
        count = conn.execute(text("SELECT count(*) FROM macro_series")).scalar()
    assert count == 0


def test_collect_macro_empty_ecos_soft_fails_single_series(
    pg_clean, fixture_fetchers, monkeypatch
):
    """R-05: per-series empty result lands in stats['failed']; other series continue."""
    from collectors.macro import collect_macro
    from collectors.macro import fetcher as macro_fetcher
    from collectors.macro.client import MacroEmptyResultError

    orig = macro_fetcher.fetch_ecos_series

    def boom(api, series_id, cycle, item_code, **kw):
        if series_id == "722Y001":
            raise MacroEmptyResultError(f"ECOS empty: {series_id}")
        return orig(api, series_id, cycle, item_code, **kw)

    monkeypatch.setattr(macro_fetcher, "fetch_ecos_series", boom)

    stats = collect_macro(engine=pg_clean, catalog_path=_catalog_path())
    assert stats["total"] == 4
    # 3 series succeed -> 3 series contribute inserts (count varies by fixture); 1 series
    # in stats['failed']
    assert len(stats["failed"]) == 1
    assert stats["failed"][0]["doc"] == "base_rate_kr"
    # The other three series should have inserted rows
    assert stats["inserted"] > 0


def test_collect_macro_no_engine_raises(monkeypatch):
    """collect_macro(engine=None) raises CollectorConfigError before any work."""
    from collectors.macro import collect_macro
    from collectors.macro.client import CollectorConfigError

    monkeypatch.setenv("ECOS_API_KEY", "x")
    monkeypatch.setenv("FRED_API_KEY", "y")

    with pytest.raises(CollectorConfigError) as exc_info:
        collect_macro(engine=None, catalog_path=_catalog_path())
    assert "engine" in str(exc_info.value).lower()


def test_collect_macro_missing_api_key_startup_fail_fast(pg_clean, monkeypatch):
    """R-05: startup fail-fast when ECOS_API_KEY unset (no series runs)."""
    from collectors.macro import collect_macro
    from collectors.macro.client import CollectorConfigError

    monkeypatch.delenv("ECOS_API_KEY", raising=False)
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    with pytest.raises(CollectorConfigError) as exc_info:
        collect_macro(engine=pg_clean, catalog_path=_catalog_path())
    msg = str(exc_info.value)
    # secret never echoed
    assert "ECOS_API_KEY" in msg or "FRED_API_KEY" in msg


def test_collect_macro_no_markdown_written(pg_clean, fixture_fetchers, tmp_path, monkeypatch):
    """CI fence: a successful collect produces NO legacy Markdown vault directory.

    Run from a clean tmp_path cwd so a writer accident would land here.
    """
    from collectors.macro import collect_macro

    monkeypatch.chdir(tmp_path)
    collect_macro(engine=pg_clean, catalog_path=_catalog_path())
    # Defense-in-depth assertion against accidental writer-resurrection: the
    # legacy on-disk layout must not exist anywhere reachable from cwd.
    legacy_root = tmp_path / "vault"
    assert not legacy_root.exists()
    legacy_macro_dir = legacy_root.joinpath("raw", "macro")
    assert not legacy_macro_dir.exists()


# -------- fetcher regressions (carry-over, Gap-04-04 / Gap-04-07) -----------


def test_fetch_ecos_series_client_side_filter_drops_unrelated_item_codes():
    """Gap-04-04 regression guard."""
    import pandas as pd

    from collectors.macro.fetcher import fetch_ecos_series

    rows = pd.DataFrame(
        [
            {"ITEM_CODE1": "0101000", "TIME": "20260414", "DATA_VALUE": "3.25"},
            {"ITEM_CODE1": "0104000", "TIME": "20260414", "DATA_VALUE": "3.41"},  # unrelated
            {"ITEM_CODE1": "0101000", "TIME": "20260415", "DATA_VALUE": "3.25"},
            {"ITEM_CODE1": "0104000", "TIME": "20260415", "DATA_VALUE": "3.42"},  # unrelated
        ]
    )

    class FakeApi:
        def __init__(self):
            self.kwargs_seen: dict = {}

        def get_statistic_search(self, **kwargs):
            self.kwargs_seen = kwargs
            return rows

    api = FakeApi()
    out = fetch_ecos_series(api, series_id="722Y001", cycle="D", item_code="0101000", days_back=30)

    assert len(out) == 2
    assert all(o["value"] == 3.25 for o in out)
    assert {o["date"] for o in out} == {"2026-04-14", "2026-04-15"}

    assert "통계항목코드1" not in api.kwargs_seen, (
        "Regression: fetch_ecos_series is passing 통계항목코드1 to PublicDataReader "
        "again. Per Gap-04-04, this kwarg is not translated into the ECOS URL "
        "segment and produces empty responses in live runs."
    )


def test_fetch_ecos_accepts_korean_column_names():
    """Gap-04-07 regression guard."""
    import pandas as pd

    from collectors.macro.fetcher import fetch_ecos_series

    rows = pd.DataFrame(
        [
            {"통계항목코드1": "0101000", "시점": "20260414", "값": "3.25"},
            {"통계항목코드1": "0104000", "시점": "20260414", "값": "3.41"},
            {"통계항목코드1": "0101000", "시점": "20260415", "값": "3.25"},
        ]
    )

    class FakeApi:
        def get_statistic_search(self, **kwargs):
            return rows

    out = fetch_ecos_series(
        FakeApi(), series_id="722Y001", cycle="D", item_code="0101000", days_back=30
    )
    assert len(out) == 2
    assert {o["date"] for o in out} == {"2026-04-14", "2026-04-15"}
    assert all(o["value"] == 3.25 for o in out)
