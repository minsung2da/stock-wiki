"""GRAPH-02: stock graph snapshot CLI — output dirs, 14-day prune, mocked graphify."""

import pytest


@pytest.mark.skip(reason="Plan 03 Task 1 — snapshot writes 3 expected files")
def test_snapshot_writes_index_html_graph_json_report_md(tmp_path, graphify_stub):
    """After `snapshot(repo_root=tmp_path, config={...})`, vault/graph/<KST_DATE>/
    contains exactly: index.html, graph.json, GRAPH_REPORT.md."""
    raise NotImplementedError


@pytest.mark.skip(reason="Plan 03 Task 2 — 14-day prune keeps newest 14 dirs")
def test_prune_keeps_14_most_recent(tmp_path):
    """Create 20 dated dirs in vault/graph/ with mtimes spread over 30 days; call
    _prune_old(tmp_path/'vault'/'graph', keep=14); assert exactly 14 dirs remain
    and the 6 oldest by mtime are gone."""
    raise NotImplementedError


@pytest.mark.skip(reason="Plan 03 Task 1 — staging dir cleaned even on graphify error")
def test_staging_cleaned_on_failure(tmp_path, graphify_stub):
    """If graphify_stub raises, finally-block removes vault/.graphify-staging/<date>/."""
    raise NotImplementedError
