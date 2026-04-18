"""Tests for heartbeat.record_source_run extra kwarg extension (Plans 02/05)."""

from __future__ import annotations

from pathlib import Path

import yaml

from ingest.heartbeat import record_source_run


def _read_meta(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---")
    end = text.find("\n---", 3)
    return yaml.safe_load(text[3:end]) or {}


def test_extra_none_roundtrips_unchanged(tmp_path: Path) -> None:
    p = tmp_path / "heartbeat.md"
    record_source_run("krx", {"succeeded": 1, "failed": []}, heartbeat_path=p, extra=None)
    meta = _read_meta(p)
    block = meta["sources"]["krx"]
    assert block["docs_processed"] == 1
    assert "skipped_holiday" not in block


def test_extra_merges_into_source_block(tmp_path: Path) -> None:
    p = tmp_path / "heartbeat.md"
    record_source_run(
        "krx",
        {"succeeded": 0, "failed": []},
        heartbeat_path=p,
        extra={"skipped_holiday": True},
    )
    meta = _read_meta(p)
    block = meta["sources"]["krx"]
    assert block["skipped_holiday"] is True
    assert "last_run" in block
    assert "last_success" in block
    assert block["docs_processed"] == 0


def test_other_source_blocks_preserved(tmp_path: Path) -> None:
    p = tmp_path / "heartbeat.md"
    record_source_run("dart", {"succeeded": 3, "failed": []}, heartbeat_path=p)
    record_source_run(
        "krx",
        {"succeeded": 0, "failed": []},
        heartbeat_path=p,
        extra={"skipped_holiday": True},
    )
    meta = _read_meta(p)
    assert meta["sources"]["dart"]["docs_processed"] == 3
    assert meta["sources"]["krx"]["skipped_holiday"] is True


def test_extra_cannot_override_reserved_keys(tmp_path: Path) -> None:
    p = tmp_path / "heartbeat.md"
    record_source_run(
        "krx",
        {"succeeded": 1, "failed": []},
        heartbeat_path=p,
        extra={"last_run": "FAKE", "docs_processed": 999, "hint": "ok"},
    )
    meta = _read_meta(p)
    block = meta["sources"]["krx"]
    assert block["last_run"] != "FAKE"
    assert block["docs_processed"] == 1
    assert block["hint"] == "ok"
