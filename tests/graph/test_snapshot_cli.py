"""GRAPH-02: stock graph snapshot CLI — output dirs, 14-day prune, mocked graphify."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from src.graph.snapshot import KEEP_DATED_DIRS, _prune_old, _today_kst, snapshot

try:
    from zoneinfo import ZoneInfo

    KST = ZoneInfo("Asia/Seoul")
except ImportError:  # pragma: no cover
    KST = timezone(timedelta(hours=9))


_MIN_CONFIG = {
    "graphify": {
        "raw_windows_days": {"dart": 365, "news": 30, "kind": 90, "macro": 180},
        "mode": "deep",
        "directed": True,
    }
}


def _scaffold_repo(repo_root: Path) -> None:
    """Create a minimal vault layout that build_staging tolerates."""
    (repo_root / "vault" / "notes").mkdir(parents=True, exist_ok=True)
    (repo_root / "vault" / "notes" / "hello.md").write_text("hi", encoding="utf-8")
    (repo_root / "notes" / "private").mkdir(parents=True, exist_ok=True)
    (repo_root / "notes" / "private" / "thesis.md").write_text("p", encoding="utf-8")


def test_snapshot_writes_index_html_graph_json_report_md(tmp_path, graphify_stub):
    """After ``snapshot(repo_root=tmp_path, config={...})``, ``vault/graph/<KST_DATE>/``
    contains exactly: index.html, graph.json, GRAPH_REPORT.md."""
    _scaffold_repo(tmp_path)

    out_dir = snapshot(tmp_path, _MIN_CONFIG)

    today = _today_kst()
    assert out_dir == tmp_path / "vault" / "graph" / today
    assert (out_dir / "index.html").exists()
    assert (out_dir / "graph.json").exists()
    assert (out_dir / "GRAPH_REPORT.md").exists()
    # Staging removed in finally even on success
    assert not (tmp_path / "vault" / ".graphify-staging" / today).exists()


def test_prune_keeps_14_most_recent(tmp_path):
    """Create 20 dated dirs in ``vault/graph/`` with mtimes spread over 30 days;
    call ``_prune_old(tmp_path/'vault'/'graph', keep=14)``; assert exactly 14 dirs
    remain and the 6 oldest by mtime are gone."""
    graph_dir = tmp_path / "vault" / "graph"
    graph_dir.mkdir(parents=True, exist_ok=True)

    base = datetime(2026, 4, 1, tzinfo=KST)
    dirs = []
    for i in range(20):
        name = (base + timedelta(days=i)).date().isoformat()
        d = graph_dir / name
        d.mkdir()
        # Set mtime increasing with i so the latest 14 are i=6..19.
        ts = (base + timedelta(days=i)).timestamp()
        os.utime(d, (ts, ts))
        dirs.append((name, ts, d))

    removed = _prune_old(graph_dir, keep=14)
    assert removed == 6

    remaining = sorted(p.name for p in graph_dir.iterdir() if p.is_dir())
    assert len(remaining) == 14
    # The 6 oldest (i=0..5) must be gone; the 14 newest (i=6..19) remain.
    expected_remaining = sorted(name for name, _, _ in dirs[6:])
    assert remaining == expected_remaining
    assert KEEP_DATED_DIRS == 14


def test_staging_cleaned_on_failure(tmp_path, graphify_stub):
    """If ``graphify_stub`` raises, the ``finally`` block removes
    ``vault/.graphify-staging/<date>/``."""
    _scaffold_repo(tmp_path)
    graphify_stub["should_raise"] = True

    with pytest.raises(RuntimeError, match="graphify_stub: forced failure"):
        snapshot(tmp_path, _MIN_CONFIG)

    today = _today_kst()
    assert not (tmp_path / "vault" / ".graphify-staging" / today).exists()
