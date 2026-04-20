"""Tests for the macro collector (ECOS + FRED) — Plan 04-03 Task 2.

Covers:
- catalog loading from .planning/macro_series.yaml
- writer: vault path, frontmatter observations, body markdown table
- writer: idempotent re-run (content_hash match → skip)
- writer: append new observation merges via read-existing-frontmatter
- writer: (date, value) dedup
- writer: R-06 same-date revision tracking
- writer: path traversal guard
- collect_macro: end-to-end with monkeypatched fetchers
- collect_macro: R-05 fail-fast startup (missing key) vs soft-fail per series
- collect_macro: heartbeat revision extra propagation (R-06)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

# -------- catalog -----------------------------------------------------------


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


# -------- writer ------------------------------------------------------------


def test_write_macro_doc_emits_observations_in_frontmatter_and_body(vault_tmp: Path):
    from collectors.macro.writer import write_macro_doc
    from shared.frontmatter import read_frontmatter

    obs = [{"date": "2026-04-15", "value": 4.28}]
    path, content_hash, rewrote, revisions = write_macro_doc(
        vault_root=vault_tmp,
        source="fred",
        series_id="DGS10",
        label="us_10y",
        observations=obs,
        source_url="https://fred.stlouisfed.org/series/DGS10",
    )
    assert rewrote is True
    assert revisions == []
    assert path.exists()
    fm, body = read_frontmatter(str(path))
    # D-07: observations structured in frontmatter
    assert fm.provenance.observations is not None
    assert len(fm.provenance.observations) == 1
    assert fm.provenance.observations[0].date.isoformat() == "2026-04-15"
    assert fm.provenance.observations[0].value == 4.28
    # human-readable body table
    assert "| 2026-04-15 | 4.28 |" in body
    assert fm.provenance.trust_level == "trusted"
    assert fm.provenance.source == "fred"


def test_write_macro_doc_idempotent_rerun_skips(vault_tmp: Path):
    from collectors.macro.writer import write_macro_doc

    obs = [{"date": "2026-04-15", "value": 4.28}]
    _, h1, rewrote1, _ = write_macro_doc(
        vault_root=vault_tmp,
        source="fred",
        series_id="DGS10",
        label="us_10y",
        observations=obs,
        source_url="https://fred.stlouisfed.org/series/DGS10",
    )
    _, h2, rewrote2, _ = write_macro_doc(
        vault_root=vault_tmp,
        source="fred",
        series_id="DGS10",
        label="us_10y",
        observations=obs,
        source_url="https://fred.stlouisfed.org/series/DGS10",
    )
    assert h1 == h2
    assert rewrote1 is True
    assert rewrote2 is False


def test_write_macro_doc_appends_new_observation(vault_tmp: Path):
    from collectors.macro.writer import write_macro_doc
    from shared.frontmatter import read_frontmatter

    write_macro_doc(
        vault_root=vault_tmp,
        source="fred",
        series_id="DGS10",
        label="us_10y",
        observations=[{"date": "2026-04-15", "value": 4.28}],
        source_url="https://fred.stlouisfed.org/series/DGS10",
    )
    _, _, rewrote, revisions = write_macro_doc(
        vault_root=vault_tmp,
        source="fred",
        series_id="DGS10",
        label="us_10y",
        observations=[{"date": "2026-04-16", "value": 4.32}],
        source_url="https://fred.stlouisfed.org/series/DGS10",
    )
    assert rewrote is True
    assert revisions == []
    fm, body = read_frontmatter(str(vault_tmp / "raw/macro/fred/DGS10.md"))
    dates = sorted(o.date.isoformat() for o in fm.provenance.observations)
    assert dates == ["2026-04-15", "2026-04-16"]
    assert "| 2026-04-15 | 4.28 |" in body
    assert "| 2026-04-16 | 4.32 |" in body


def test_write_macro_doc_date_value_dedup(vault_tmp: Path):
    from collectors.macro.writer import write_macro_doc

    write_macro_doc(
        vault_root=vault_tmp,
        source="fred",
        series_id="DGS10",
        label="us_10y",
        observations=[{"date": "2026-04-15", "value": 4.28}],
        source_url="https://fred.stlouisfed.org/series/DGS10",
    )
    # Exact same (date, value) — no revision, no rewrite
    _, _, rewrote, revisions = write_macro_doc(
        vault_root=vault_tmp,
        source="fred",
        series_id="DGS10",
        label="us_10y",
        observations=[{"date": "2026-04-15", "value": 4.28}],
        source_url="https://fred.stlouisfed.org/series/DGS10",
    )
    assert rewrote is False
    assert revisions == []


def test_write_macro_doc_same_date_different_value_records_revision(vault_tmp: Path):
    """R-06: same date + different value → new value persisted, revision surfaced."""
    from collectors.macro.writer import write_macro_doc
    from shared.frontmatter import read_frontmatter

    write_macro_doc(
        vault_root=vault_tmp,
        source="fred",
        series_id="DGS10",
        label="us_10y",
        observations=[{"date": "2026-04-15", "value": 4.28}],
        source_url="https://fred.stlouisfed.org/series/DGS10",
    )
    _, _, rewrote, revisions = write_macro_doc(
        vault_root=vault_tmp,
        source="fred",
        series_id="DGS10",
        label="us_10y",
        observations=[{"date": "2026-04-15", "value": 4.30}],
        source_url="https://fred.stlouisfed.org/series/DGS10",
    )
    assert rewrote is True
    assert revisions == [{"date": "2026-04-15", "old_value": 4.28, "new_value": 4.30}]
    fm, _ = read_frontmatter(str(vault_tmp / "raw/macro/fred/DGS10.md"))
    assert fm.provenance.observations[0].value == 4.30


def test_write_macro_doc_path_traversal_guard(vault_tmp: Path):
    from collectors.macro.writer import write_macro_doc

    with pytest.raises(ValueError):
        write_macro_doc(
            vault_root=vault_tmp,
            source="fred",
            series_id="../etc",
            label="bad",
            observations=[],
            source_url="x",
        )
    with pytest.raises(ValueError):
        write_macro_doc(
            vault_root=vault_tmp,
            source="invalid_source",
            series_id="DGS10",
            label="bad",
            observations=[],
            source_url="x",
        )


# -------- collect_macro -----------------------------------------------------


def _fixtures_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures"


def _ecos_fixture_to_fetcher_output(path: Path) -> list[dict]:
    """Transform raw ECOS fixture rows into fetcher output shape."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for r in rows:
        t = str(r["TIME"])
        date_iso = f"{t[:4]}-{t[4:6]}-{t[6:8]}"
        out.append({"date": date_iso, "value": float(r["DATA_VALUE"])})
    return out


def _fred_fixture(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _catalog_path() -> Path:
    return Path(__file__).resolve().parents[3] / ".planning" / "macro_series.yaml"


@pytest.fixture
def fixture_fetchers(monkeypatch):
    """Monkeypatch fetcher functions to return fixture data keyed by series_id."""
    fx = _fixtures_dir()
    ecos_map = {
        "722Y001": _ecos_fixture_to_fetcher_output(fx / "ecos/base_rate_kr.json"),
        "731Y001": _ecos_fixture_to_fetcher_output(fx / "ecos/usd_krw.json"),
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


def test_collect_macro_full_run_then_idempotent(vault_tmp: Path, fixture_fetchers):
    from collectors.macro import collect_macro

    stats1 = collect_macro(vault_root=vault_tmp, catalog_path=_catalog_path())
    assert stats1["total"] == 4
    assert stats1["succeeded"] == 4
    assert stats1["skipped"] == 0
    assert stats1["failed"] == []

    stats2 = collect_macro(vault_root=vault_tmp, catalog_path=_catalog_path())
    assert stats2["total"] == 4
    assert stats2["succeeded"] == 0
    assert stats2["skipped"] == 4
    assert stats2["failed"] == []


def test_collect_macro_missing_api_key_startup_fail_fast(vault_tmp: Path, monkeypatch):
    """R-05: startup fail-fast when ECOS_API_KEY unset (no series runs)."""
    from collectors.macro import collect_macro
    from collectors.macro.client import CollectorConfigError

    monkeypatch.delenv("ECOS_API_KEY", raising=False)
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    with pytest.raises(CollectorConfigError) as exc_info:
        collect_macro(vault_root=vault_tmp, catalog_path=_catalog_path())
    # secret never echoed
    msg = str(exc_info.value)
    assert "ECOS_API_KEY" in msg or "FRED_API_KEY" in msg


def test_collect_macro_empty_ecos_soft_fails_single_series(
    vault_tmp: Path, fixture_fetchers, monkeypatch
):
    """R-05: per-series empty result lands in stats['failed']; other series continue."""
    from collectors.macro import collect_macro
    from collectors.macro import fetcher as macro_fetcher
    from collectors.macro.client import MacroEmptyResultError

    # Force base_rate_kr to raise empty; others succeed
    orig = macro_fetcher.fetch_ecos_series

    def boom(api, series_id, cycle, item_code, **kw):
        if series_id == "722Y001":
            raise MacroEmptyResultError(f"ECOS empty: {series_id}")
        return orig(api, series_id, cycle, item_code, **kw)

    monkeypatch.setattr(macro_fetcher, "fetch_ecos_series", boom)

    stats = collect_macro(vault_root=vault_tmp, catalog_path=_catalog_path())
    assert stats["total"] == 4
    assert stats["succeeded"] == 3
    assert len(stats["failed"]) == 1
    assert stats["failed"][0]["doc"] == "base_rate_kr"


def test_collect_macro_logs_revisions_to_heartbeat(vault_tmp: Path, fixture_fetchers, monkeypatch):
    """R-06: same-date different-value revision propagates to heartbeat extra.revisions."""
    from collectors.macro import collect_macro
    from collectors.macro import fetcher as macro_fetcher

    # First pass: normal fixtures
    collect_macro(vault_root=vault_tmp, catalog_path=_catalog_path())

    # Second pass: mutate DGS10 2026-04-16 value (4.32 → 4.40) to trigger a revision
    def revised(fred, series_id, **kw):
        if series_id == "DGS10":
            return [
                {"date": "2026-04-14", "value": 4.29},
                {"date": "2026-04-15", "value": 4.31},
                {"date": "2026-04-16", "value": 4.40},  # revised
            ]
        return _fred_fixture(_fixtures_dir() / f"fred/{series_id}.json")

    monkeypatch.setattr(macro_fetcher, "fetch_fred_series", revised)
    collect_macro(vault_root=vault_tmp, catalog_path=_catalog_path())

    # Heartbeat yaml should carry revisions in macro section
    hb = (vault_tmp / "ingested/_status/heartbeat.md").read_text(encoding="utf-8")
    data = yaml.safe_load(hb.split("---", 2)[1])
    macro = data["sources"]["macro"]
    assert "revisions" in macro
    hits = [r for r in macro["revisions"] if r["series_id"] == "DGS10"]
    assert hits and hits[0]["date"] == "2026-04-16"
    assert hits[0]["old_value"] == 4.32
    assert hits[0]["new_value"] == 4.40
