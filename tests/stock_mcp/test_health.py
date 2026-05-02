"""Tests for the ``health`` MCP tool (Plan 06-07, MCP-09).

Covers:
  T1: All sources fresh + DB up → overall='ok'.
  T2: One source stale (>26h) → that source.status='stale'; overall='stale'.
  T3: One source's last ingest_runs row carries error → status='down'; overall='down'.
  T4: DB unreachable → db.status='down'; sources from heartbeat.md fallback.
  T5: DB + heartbeat both missing → all 5 sources 'down'; overall='down'.
  T6: STALENESS_THRESHOLDS_HOURS monkeypatchable per source.
  T7: timestamp is recent and KST-aware.
  T8: Docstring contains the four mandated D-24 sections.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa

from stock_mcp.models import HealthResponse


def _set_repo_root(monkeypatch: pytest.MonkeyPatch, repo_root: Path) -> None:
    monkeypatch.setenv("STOCK_REPO_ROOT", str(repo_root))


def _import_health():
    """Import the module fresh so per-test monkeypatches on its module-level
    constants are isolated."""
    import importlib

    import stock_mcp.tools.health as health_mod

    importlib.reload(health_mod)
    return health_mod


def test_all_fresh_overall_ok(mcp_vault_engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """T1: every fixture source fresh and successful.

    The fixture seeds 4 fresh + 1 stale (macro). To get an all-ok response,
    monkey the macro threshold above 30h so its 30h-old run reads as 'ok'.
    """
    engine, _vault, repo_root = mcp_vault_engine
    _set_repo_root(monkeypatch, repo_root)
    health_mod = _import_health()
    monkeypatch.setitem(health_mod.STALENESS_THRESHOLDS_HOURS, "macro", 100)

    res = health_mod.health()
    assert isinstance(res, HealthResponse), res
    assert res.db.status == "ok"
    assert res.overall == "ok"
    assert set(res.sources.keys()) >= {"dart", "krx", "news", "macro", "kind"}
    for src in ("dart", "krx", "news", "macro", "kind"):
        assert res.sources[src].status == "ok", f"{src}={res.sources[src]}"


def test_stale_source_overall_stale(mcp_vault_engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """T2: macro is 30h stale → overall='stale'."""
    engine, _vault, repo_root = mcp_vault_engine
    _set_repo_root(monkeypatch, repo_root)
    health_mod = _import_health()

    res = health_mod.health()
    assert isinstance(res, HealthResponse), res
    assert res.sources["macro"].status == "stale"
    assert res.overall == "stale"


def test_source_with_error_overall_down(mcp_vault_engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """T3: insert a fresh-but-errored row for 'krx' → status='down', overall='down'."""
    engine, _vault, repo_root = mcp_vault_engine
    _set_repo_root(monkeypatch, repo_root)

    now = datetime.now(UTC)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO ingest_runs (started_at, finished_at, kind, source, "
                "stats, error) VALUES (:s, :f, 'collect', 'krx', "
                "CAST('{\"succeeded\": 0}' AS JSONB), :err)"
            ),
            {"s": now - timedelta(seconds=1), "f": now, "err": "boom"},
        )
    try:
        health_mod = _import_health()
        monkeypatch.setitem(health_mod.STALENESS_THRESHOLDS_HOURS, "macro", 100)
        res = health_mod.health()
        assert isinstance(res, HealthResponse)
        assert res.sources["krx"].status == "down"
        assert res.sources["krx"].last_error == "boom"
        assert res.overall == "down"
    finally:
        with engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM ingest_runs WHERE error = 'boom'"))


def test_db_unreachable_falls_back_to_heartbeat(
    mcp_vault_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T4: get_engine raises → db.status='down'; sources from heartbeat.md."""
    engine, _vault, repo_root = mcp_vault_engine
    _set_repo_root(monkeypatch, repo_root)

    # Make sure heartbeat.md has at least one source the fallback will see.
    heartbeat_path = repo_root / "vault" / "ingested" / "_status" / "heartbeat.md"
    assert heartbeat_path.exists(), "fixture missing heartbeat.md"

    health_mod = _import_health()

    def _explode(*a, **kw):
        raise RuntimeError("simulated DB outage")

    monkeypatch.setattr(health_mod, "get_engine", _explode)

    res = health_mod.health()
    assert isinstance(res, HealthResponse), res
    assert res.db.status == "down"
    assert "simulated DB outage" in (res.db.last_error or "")
    # All 5 expected sources are present in the response (filled if missing).
    assert set(res.sources.keys()) >= {"dart", "krx", "news", "macro", "kind"}
    assert res.overall == "down"  # db down → overall down


def test_db_and_heartbeat_both_missing(
    mcp_vault_engine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T5: empty repo (no heartbeat.md) + DB down → all 'no telemetry available'."""
    fake_root = tmp_path / "empty"
    (fake_root / "vault").mkdir(parents=True, exist_ok=True)
    _set_repo_root(monkeypatch, fake_root)

    health_mod = _import_health()
    monkeypatch.setattr(
        health_mod, "get_engine", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    )
    res = health_mod.health()
    assert isinstance(res, HealthResponse)
    assert res.db.status == "down"
    assert res.overall == "down"
    for src in ("dart", "krx", "news", "macro", "kind"):
        assert res.sources[src].status == "down"
        assert res.sources[src].last_error == "no telemetry available"


def test_threshold_monkeypatchable(mcp_vault_engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """T6: lowering 'news' threshold to 0.001h flips its fresh row to stale."""
    engine, _vault, repo_root = mcp_vault_engine
    _set_repo_root(monkeypatch, repo_root)
    health_mod = _import_health()
    monkeypatch.setitem(health_mod.STALENESS_THRESHOLDS_HOURS, "macro", 100)
    monkeypatch.setitem(health_mod.STALENESS_THRESHOLDS_HOURS, "news", 0.001)

    res = health_mod.health()
    assert isinstance(res, HealthResponse)
    assert res.sources["news"].status == "stale"
    assert res.overall == "stale"


def test_timestamp_is_recent_and_kst_aware(
    mcp_vault_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T7: response.timestamp is tz-aware (KST) and within 5s of now."""
    engine, _vault, repo_root = mcp_vault_engine
    _set_repo_root(monkeypatch, repo_root)
    health_mod = _import_health()

    before = datetime.now(UTC)
    res = health_mod.health()
    after = datetime.now(UTC)
    assert isinstance(res, HealthResponse)
    assert res.timestamp.tzinfo is not None, "timestamp must be tz-aware"
    # Convert KST → UTC for comparison.
    ts_utc = res.timestamp.astimezone(UTC)
    assert before - timedelta(seconds=5) <= ts_utc <= after + timedelta(seconds=5)


def test_docstring_has_four_sections() -> None:
    """T8: D-24 mandates four ### sections in the docstring."""
    health_mod = _import_health()
    doc = health_mod.health.__doc__ or ""
    for needle in (
        "### Behavior contract",
        "### Response shape",
        "### Errors",
        "### Performance budget",
    ):
        assert needle in doc, f"docstring missing {needle!r}"
