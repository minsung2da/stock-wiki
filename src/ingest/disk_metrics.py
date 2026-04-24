"""Disk capacity metrics for heartbeat disk section (D-23, D-24).

Pure-function helpers. No Postgres client — caller passes db_size_mb as an
integer (obtained via text("SELECT pg_database_size(current_database())")
in the Routines skill). This module has zero DB deps.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _dir_mb(path: str | Path, exclude: tuple[str, ...] = (".git",)) -> float:
    """Sum file sizes under `path` in MB. Returns 0.0 if path missing."""
    p = Path(path)
    if not p.exists() or not p.is_dir():
        return 0.0
    total = 0
    for f in p.rglob("*"):
        if f.is_file():
            # Skip .git if in excluded components
            if any(part in exclude for part in f.parts):
                continue
            try:
                total += f.stat().st_size
            except OSError:
                continue
    return round(total / (1024 * 1024), 2)


def compute_disk_metrics(
    vault_path: str | Path = "vault",
    repo_path: str | Path = ".",
    db_size_mb: float | None = None,
    pgdata_path: str | Path | None = None,
) -> dict[str, Any]:
    """Compute the D-23 disk section dict.

    Args:
        vault_path: root of the Obsidian vault. Excludes ``.git`` (so a
            vault rooted at the repo root does not double-count git
            objects).
        repo_path: repo root (used to locate .git). The ``.git`` directory
            is measured in full (no exclusion) so packed objects count.
        db_size_mb: Postgres DB size in MB; caller supplies via pg_database_size.
            None -> 0.0 (not measured).
        pgdata_path: host path to Postgres pgdata volume if measurable. None
            (the default in our Docker setup) -> 0.0.

    Caller must ensure ``vault_path``, ``repo_path``, ``pgdata_path`` are
    non-overlapping. Otherwise nested data is double-counted across keys
    (WR-04 documented foot-gun).

    Returns:
        Dict with keys: vault_mb, git_mb, db_mb, pgdata_mb, alert_level.
    """
    vault_mb = _dir_mb(vault_path)
    git_mb = _dir_mb(Path(repo_path) / ".git", exclude=())
    db_mb = float(db_size_mb) if db_size_mb is not None else 0.0
    pgdata_mb = _dir_mb(pgdata_path) if pgdata_path is not None else 0.0
    metrics = {
        "vault_mb": vault_mb,
        "git_mb": git_mb,
        "db_mb": db_mb,
        "pgdata_mb": pgdata_mb,
    }
    metrics["alert_level"] = compute_disk_alert_level(metrics)
    return metrics


def compute_disk_alert_level(metrics: dict[str, Any]) -> str | None:
    """D-24 disk thresholds. 'warn' > 'info' > None."""
    level: str | None = None
    if metrics.get("vault_mb", 0) > 2000:
        level = "info"
    if metrics.get("db_mb", 0) > 10000:
        level = "warn"  # warn wins over info
    return level
