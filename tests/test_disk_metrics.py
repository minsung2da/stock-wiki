"""Tests for ingest.disk_metrics (D-23, D-24 disk thresholds)."""

from __future__ import annotations

from ingest.disk_metrics import (
    compute_disk_alert_level,
    compute_disk_metrics,
)


def test_missing_paths_return_zero(tmp_path):
    m = compute_disk_metrics(
        vault_path=str(tmp_path / "nonexistent"),
        repo_path=str(tmp_path / "nonexistent"),
        db_size_mb=None,
        pgdata_path=None,
    )
    assert m["vault_mb"] == 0.0
    assert m["git_mb"] == 0.0
    assert m["db_mb"] == 0.0
    assert m["pgdata_mb"] == 0.0
    assert m["alert_level"] is None


def test_vault_file_counted(tmp_path):
    (tmp_path / "file.md").write_text("x" * 2048, encoding="utf-8")
    m = compute_disk_metrics(vault_path=str(tmp_path), repo_path=str(tmp_path))
    assert m["vault_mb"] >= 0.0


def test_git_dir_measured(tmp_path):
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    m = compute_disk_metrics(vault_path=str(tmp_path), repo_path=str(tmp_path))
    assert m["git_mb"] >= 0.0


def test_db_size_passthrough():
    m = compute_disk_metrics(vault_path=".", repo_path=".", db_size_mb=2450.5)
    assert m["db_mb"] == 2450.5


def test_alert_level_info_on_vault_over_2gb():
    level = compute_disk_alert_level({"vault_mb": 2500, "db_mb": 0})
    assert level == "info"


def test_alert_level_warn_on_db_over_10gb():
    level = compute_disk_alert_level({"vault_mb": 100, "db_mb": 11000})
    assert level == "warn"


def test_alert_level_warn_overrides_info():
    level = compute_disk_alert_level({"vault_mb": 2500, "db_mb": 11000})
    assert level == "warn"


def test_alert_level_none_when_under_threshold():
    level = compute_disk_alert_level({"vault_mb": 500, "db_mb": 500})
    assert level is None


def test_git_excluded_from_vault_mb(tmp_path):
    """Vault scan must skip .git contents (otherwise double-counted)."""
    (tmp_path / "doc.md").write_text("a" * 1000, encoding="utf-8")
    git = tmp_path / ".git"
    git.mkdir()
    (git / "objects").mkdir()
    (git / "objects" / "pack").write_bytes(b"x" * 10_000_000)  # 10MB
    m = compute_disk_metrics(vault_path=str(tmp_path), repo_path=str(tmp_path))
    # vault_mb should NOT include the 10MB inside .git
    assert m["vault_mb"] < 1  # just the 1KB doc
