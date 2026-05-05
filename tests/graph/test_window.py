"""GRAPH-02 D-12: windowed staging directory."""

import pytest


@pytest.mark.skip(reason="Plan 03 Task 2 — config raw_windows_days respected")
def test_window_filters_by_mtime_days(tmp_path):
    """Create vault/raw/dart/ files with mtime today, today-100d, today-400d.
    With config {'graphify':{'raw_windows_days':{'dart':365}}}, staging contains
    symlinks to today + today-100d but NOT today-400d."""
    raise NotImplementedError


@pytest.mark.skip(reason="Plan 03 Task 2 — notes/private always included unwindowed")
def test_notes_private_always_included(tmp_path):
    """notes/private/*.md is symlinked into staging regardless of mtime (D-12)."""
    raise NotImplementedError
