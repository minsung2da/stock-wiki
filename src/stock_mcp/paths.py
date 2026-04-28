"""Path helpers for ``add_note`` and other write-capable MCP tools.

Two surfaces:

- ``safe_join(repo_root, user_path)``: enforces the D-09 write-scope contract.
  Resolves the joined path (following ``..`` and symlinks) and rejects anything
  outside the whitelist ``vault/notes/`` ∪ ``notes/private/``. Raises
  ``StructuredError(WRITE_FORBIDDEN)`` on violation.

- ``resolve_path_alias(user_path)``: D-12 user-friendly aliases. Translates
  ``journal/today`` → ``notes/private/journal/{KST date}.md``,
  ``{6-digit ticker}/{kind}`` → ``notes/private/{ticker}/{kind}.md``, etc.
  Always ensures a ``.md`` extension on the final segment.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .errors import ErrorCode, StructuredError

__all__ = ["WHITELIST_PREFIXES", "safe_join", "resolve_path_alias"]


WHITELIST_PREFIXES: tuple[str, ...] = ("vault/notes/", "notes/private/")


def _allowed_roots(repo_root: Path) -> tuple[Path, ...]:
    rr = repo_root.resolve()
    return tuple((rr / p.rstrip("/")).resolve() for p in WHITELIST_PREFIXES)


def safe_join(repo_root: Path, user_path: str) -> Path:
    """Resolve ``user_path`` under ``repo_root`` and enforce the write whitelist.

    The candidate is ``Path.resolve()``-d, which follows symlinks AND collapses
    ``..`` segments. Then we require ``candidate.is_relative_to(root)`` for one
    of the whitelisted roots. This rejects:
      - ``../etc/passwd`` (escapes via ``..``)
      - ``raw/dart/foo.md`` (outside whitelist)
      - symlink targets pointing outside the whitelist

    Raises:
        StructuredError(ErrorCode.WRITE_FORBIDDEN): if the resolved path is not
            within the whitelist.
    """
    rr = repo_root.resolve()
    candidate = (rr / user_path).resolve()
    roots = _allowed_roots(repo_root)
    if not any(candidate == r or candidate.is_relative_to(r) for r in roots):
        raise StructuredError(
            ErrorCode.WRITE_FORBIDDEN,
            f"path outside whitelist: {user_path!r}",
            details={"allowed_prefixes": list(WHITELIST_PREFIXES)},
        )
    return candidate


_TICKER6 = re.compile(r"^[0-9]{6}$")


def _ensure_md(p: str) -> str:
    return p if p.endswith(".md") else f"{p}.md"


def resolve_path_alias(user_path: str) -> str:
    """Convert a user-friendly alias to a repo-relative ``.md`` path (D-12).

    Aliases:
        ``journal``, ``journal/today``  →  ``notes/private/journal/{YYYY-MM-DD KST}.md``
        ``journal/<name>``              →  ``notes/private/journal/<name>.md``
        ``<6-digit-ticker>/<kind>``     →  ``notes/private/<ticker>/<kind>.md``

    Otherwise the path is returned unchanged (with ``.md`` appended if missing).
    Whitelist enforcement is the caller's job — pass the result to ``safe_join``.
    """
    p = user_path.strip().rstrip("/")
    kst_today = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    if p in ("journal", "journal/today"):
        return f"notes/private/journal/{kst_today}.md"
    if p.startswith("journal/"):
        name = p[len("journal/") :]
        return f"notes/private/journal/{_ensure_md(name)}"
    parts = p.split("/", 1)
    if len(parts) == 2 and _TICKER6.match(parts[0]):
        kind = parts[1]
        return f"notes/private/{parts[0]}/{_ensure_md(kind)}"
    if any(p.startswith(prefix) for prefix in WHITELIST_PREFIXES):
        return _ensure_md(p)
    return _ensure_md(p)
