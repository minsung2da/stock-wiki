"""Tests for Phase 5 heartbeat extensions (D-23 enrich + disk section, D-24 SLA)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from ingest.heartbeat import (
    compute_enrich_alert_level,
    record_source_run,
    write_disk_section,
)


def _read(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    end = text.find("\n---", 3)
    return yaml.safe_load(text[3:end])


def test_enrich_section_written(tmp_path):
    hb = tmp_path / "heartbeat.md"
    record_source_run(
        "enrich",
        {"total": 47, "succeeded": 47, "skipped": 0, "failed": 0},
        heartbeat_path=hb,
        extra={
            "docs_skipped_oversize": 2,
            "docs_review_flagged": 3,
            "backlog_count": 12,
            "review_flags": {
                "sentiment_score_label_mismatch": 1,
                "dart_structured_disagreement": 2,
            },
            "consecutive_failures": 0,
        },
    )
    meta = _read(hb)
    src = meta["sources"]["enrich"]
    assert src["docs_processed"] == 47
    assert src["docs_skipped_oversize"] == 2
    assert src["backlog_count"] == 12
    assert "alert_level" in src


def test_other_sources_unchanged(tmp_path):
    """Non-enrich source block unchanged by Phase 5 extension (COLL-08 isolation)."""
    hb = tmp_path / "heartbeat.md"
    record_source_run(
        "dart",
        {"total": 10, "succeeded": 10, "skipped": 0, "failed": 0},
        heartbeat_path=hb,
        extra={"tickers": 3},
    )
    meta = _read(hb)
    assert "alert_level" not in meta["sources"]["dart"]  # not auto-added for non-enrich


def test_alert_level_warn_on_consecutive_failures():
    level = compute_enrich_alert_level(
        extra={
            "consecutive_failures": 2,
            "docs_processed": 10,
            "docs_review_flagged": 0,
            "backlog_count": 0,
        },
        prior_block=None,
    )
    assert level == "warn"


def test_alert_level_warn_on_backlog_over_50():
    level = compute_enrich_alert_level(
        extra={
            "consecutive_failures": 0,
            "docs_processed": 10,
            "docs_review_flagged": 0,
            "backlog_count": 51,
        },
        prior_block=None,
    )
    assert level == "warn"


def test_alert_level_info_on_flagged_over_10pct():
    level = compute_enrich_alert_level(
        extra={
            "consecutive_failures": 0,
            "docs_processed": 100,
            "docs_review_flagged": 15,
            "backlog_count": 0,
        },
        prior_block=None,
    )
    assert level == "info"


def test_alert_level_warn_overrides_info():
    level = compute_enrich_alert_level(
        extra={
            "consecutive_failures": 2,
            "docs_processed": 100,
            "docs_review_flagged": 15,
            "backlog_count": 0,
        },
        prior_block=None,
    )
    assert level == "warn"


def test_alert_level_none_clean():
    level = compute_enrich_alert_level(
        extra={
            "consecutive_failures": 0,
            "docs_processed": 50,
            "docs_review_flagged": 2,
            "backlog_count": 5,
        },
        prior_block=None,
    )
    assert level is None


def test_alert_level_stale_last_run():
    """now - last_run > 26h -> warn."""
    now = datetime(2026, 4, 24, 22, 0, 0, tzinfo=UTC)
    stale = (now - timedelta(hours=27)).isoformat()
    level = compute_enrich_alert_level(
        extra={
            "consecutive_failures": 0,
            "docs_processed": 10,
            "docs_review_flagged": 0,
            "backlog_count": 0,
        },
        prior_block={"last_run": stale},
        now_iso=now.isoformat(),
    )
    assert level == "warn"


def test_disk_section_written(tmp_path):
    hb = tmp_path / "heartbeat.md"
    # First write a source so sources exists
    record_source_run(
        "enrich",
        {"total": 1, "succeeded": 1, "skipped": 0, "failed": 0},
        heartbeat_path=hb,
    )
    # Now write disk
    write_disk_section(
        {"vault_mb": 487, "git_mb": 1203, "db_mb": 2450, "pgdata_mb": 3800, "alert_level": None},
        heartbeat_path=hb,
    )
    meta = _read(hb)
    assert meta["disk"]["vault_mb"] == 487
    assert meta["disk"]["alert_level"] is None
    # Existing sources preserved
    assert meta["sources"]["enrich"]["docs_processed"] == 1


def test_disk_overwrites_prior_disk(tmp_path):
    hb = tmp_path / "heartbeat.md"
    write_disk_section(
        {"vault_mb": 100, "git_mb": 0, "db_mb": 0, "pgdata_mb": 0, "alert_level": None},
        heartbeat_path=hb,
    )
    write_disk_section(
        {"vault_mb": 200, "git_mb": 0, "db_mb": 0, "pgdata_mb": 0, "alert_level": None},
        heartbeat_path=hb,
    )
    meta = _read(hb)
    assert meta["disk"]["vault_mb"] == 200
