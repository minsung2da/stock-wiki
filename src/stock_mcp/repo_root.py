"""Public helper resolving the project repo root for stock_mcp tools.

Single source of truth — replaces per-tool ``_repo_root()`` duplications.
Plans 06-05 (portfolio), 06-06 (notes), 06-07 (health), and 06-08 (overview)
all import this function instead of redefining it.

Resolution order:
1. ``STOCK_REPO_ROOT`` env var (test/CI override) → resolved absolute Path.
2. Walk up from ``Path.cwd()`` looking for a directory containing both
   ``pyproject.toml`` AND ``vault/`` (project root markers).
3. Fallback: ``Path.cwd().resolve()`` (caller handles missing files via
   PATH_NOT_FOUND).
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["repo_root"]


def repo_root() -> Path:
    """Return an absolute Path to the project repo root."""
    env = os.environ.get("STOCK_REPO_ROOT")
    if env:
        return Path(env).resolve()
    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        if (parent / "pyproject.toml").exists() and (parent / "vault").exists():
            return parent
    return cwd
