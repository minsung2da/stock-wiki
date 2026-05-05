"""GRAPH-02 D-12: windowed staging directory."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.graph.window import build_staging

try:
    from zoneinfo import ZoneInfo

    KST = ZoneInfo("Asia/Seoul")
except ImportError:  # pragma: no cover
    KST = timezone(timedelta(hours=9))


_CONFIG = {"graphify": {"raw_windows_days": {"dart": 365, "news": 30, "kind": 90, "macro": 180}}}


def _touch(path: Path, days_ago: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    ts = (datetime.now(KST) - timedelta(days=days_ago)).timestamp()
    os.utime(path, (ts, ts))


def test_window_filters_by_mtime_days(tmp_path):
    """Files at mtime today, today-100d, today-400d under vault/raw/dart/.
    With config raw_windows_days.dart=365, staging contains only the first two."""
    repo_root = tmp_path
    dart_root = repo_root / "vault" / "raw" / "dart"
    today_file = dart_root / "today.md"
    mid_file = dart_root / "mid.md"
    old_file = dart_root / "old.md"
    _touch(today_file, 0)
    _touch(mid_file, 100)
    _touch(old_file, 400)

    staging = repo_root / "vault" / ".graphify-staging" / "2026-05-05"
    counts = build_staging(repo_root, staging, _CONFIG)

    staged_dart = staging / "vault" / "raw" / "dart"
    assert (staged_dart / "today.md").exists()
    assert (staged_dart / "mid.md").exists()
    assert not (staged_dart / "old.md").exists()
    assert counts["dart"] == 2


def test_notes_private_always_included(tmp_path):
    """notes/private/foo.md (mtime far in the past) appears in staging regardless."""
    repo_root = tmp_path
    private_md = repo_root / "notes" / "private" / "foo.md"
    _touch(private_md, 9999)  # ancient mtime

    staging = repo_root / "vault" / ".graphify-staging" / "2026-05-05"
    counts = build_staging(repo_root, staging, _CONFIG)

    staged_private = staging / "notes" / "private"
    # Either symlink to dir resolved, or copytree fallback — either way, foo.md must be reachable.
    assert (staged_private / "foo.md").exists()
    assert counts["private"] >= 1
