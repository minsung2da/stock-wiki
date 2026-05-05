"""Phase 7 GRAPH-02 D-12: windowed staging directory builder.

Constructs a symlink farm at ``staging/`` mirroring two scopes:

1. Always-included (no time window): ``vault/notes/``, ``notes/private/``
2. Source-windowed (per config ``raw_windows_days``):
   ``vault/raw/<source>/<file>.md`` where file mtime is within the configured
   day window from now (KST).

Symlink-vs-copy: WSL/Linux uses symlinks (cheap, no duplication). On Windows
without Developer Mode/admin, ``OSError`` is caught and ``shutil.copy``
fallback is used (RESEARCH §Pitfall 5).

Returns ``dict {source_name: count}`` for observability.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo

    KST = ZoneInfo("Asia/Seoul")
except ImportError:  # pragma: no cover
    KST = timezone(timedelta(hours=9))

logger = logging.getLogger(__name__)


def _link_or_copy(target: Path, link: Path, *, target_is_directory: bool = False) -> None:
    """Create a symlink; fall back to copy on OSError (Windows non-admin)."""
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except (OSError, NotImplementedError) as exc:
        logger.debug("symlink failed (%s); copying %s -> %s", exc, target, link)
        if target.is_dir():
            shutil.copytree(target, link, dirs_exist_ok=True)
        else:
            shutil.copy2(target, link)


def build_staging(repo_root: Path, staging: Path, config: dict) -> dict:
    """Populate ``staging/`` per CONTEXT D-12.

    Returns:
        dict mapping source name -> count of files staged. ``notes`` and
        ``private`` count their ``*.md`` recursively (the actual stage entry
        is one symlink to the directory root).
    """
    staging.mkdir(parents=True, exist_ok=True)
    counts: dict = {"notes": 0, "private": 0}

    # Always-included scopes (no time window).
    for src_rel, key in (("vault/notes", "notes"), ("notes/private", "private")):
        src = repo_root / src_rel
        if not src.exists():
            continue
        link = staging / src_rel
        link.parent.mkdir(parents=True, exist_ok=True)
        _link_or_copy(src, link, target_is_directory=True)
        counts[key] = sum(1 for _ in src.rglob("*.md"))

    # Source-windowed scopes.
    windows = (config.get("graphify") or {}).get("raw_windows_days") or {}
    now = datetime.now(KST)
    cutoffs = {s: now - timedelta(days=int(d)) for s, d in windows.items()}

    for source_name, cutoff in cutoffs.items():
        src_root = repo_root / "vault" / "raw" / source_name
        if not src_root.exists():
            counts[source_name] = 0
            continue
        target_root = staging / "vault" / "raw" / source_name
        target_root.mkdir(parents=True, exist_ok=True)
        n = 0
        for f in src_root.rglob("*.md"):
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=KST)
            if mtime < cutoff:
                continue
            rel = f.relative_to(src_root)
            tgt = target_root / rel
            tgt.parent.mkdir(parents=True, exist_ok=True)
            _link_or_copy(f, tgt)
            n += 1
        counts[source_name] = n
    return counts
