"""Read-only path-traversal defense for ``get_note`` (V12 / ASVS V12, T-path-traversal).

``get_note(path)`` is the only tool that touches the filesystem. :func:`safe_resolve`
is the boundary control: it resolves the caller-supplied path under the repo root and
admits it ONLY if it lands inside the ``notes/private/`` whitelist.

Why ``Path.resolve()`` and not a string ``..`` check (Don't Hand-Roll): ``resolve()``
collapses ``..`` segments AND follows symlinks *before* the whitelist comparison, so a
symlink inside ``notes/private/`` that points at ``/etc/passwd`` is rejected — a string
prefix check would miss that escape.

Read-only by design: this is the v2.0 variant of the archive ``stock_mcp/paths.py``
``safe_join``. The archive's two-root write whitelist (``vault/notes/`` ∪
``notes/private/``) collapses to ``("notes/private/",)`` ONLY — ``vault/`` is deleted
(Veto #9) — and the write-oriented ``resolve_path_alias`` is dropped (no write tools
this phase). Faults raise the typed :mod:`mcp_v2.errors` exceptions (not the archive's
``StructuredError`` dict).
"""

from __future__ import annotations

from pathlib import Path

from mcp_v2.errors import NoteNotFound, NotePathForbidden

__all__ = ["WHITELIST_PREFIXES", "safe_resolve"]

#: The ONLY readable root for get_note. ``notes/private/`` is the gitignored
#: user thesis/journal store (Veto #9 — no vault/). Read-only.
WHITELIST_PREFIXES: tuple[str, ...] = ("notes/private/",)


def _allowed_roots(repo_root: Path) -> tuple[Path, ...]:
    rr = repo_root.resolve()
    return tuple((rr / p.rstrip("/")).resolve() for p in WHITELIST_PREFIXES)


def safe_resolve(repo_root: Path, user_path: str) -> Path:
    """Resolve ``user_path`` under ``repo_root`` and enforce the read whitelist.

    The candidate is ``Path.resolve()``-d (collapses ``..`` AND follows symlinks),
    then required to equal or be ``is_relative_to`` a whitelisted root. This rejects:

      - ``../etc/passwd`` (escapes via ``..``)
      - an absolute path outside the whitelist
      - a symlink under ``notes/private/`` whose target is outside the whitelist
        (resolve() follows it before the check)

    Raises:
        NotePathForbidden: the resolved path is outside the whitelist.
        NoteNotFound: the path is whitelisted but is not an existing file.

    Returns:
        The resolved, whitelisted, existing-file :class:`~pathlib.Path`.
    """
    rr = repo_root.resolve()
    candidate = (rr / user_path).resolve()
    roots = _allowed_roots(repo_root)
    if not any(candidate == r or candidate.is_relative_to(r) for r in roots):
        raise NotePathForbidden(f"path outside whitelist: {user_path!r}")
    if not candidate.is_file():
        raise NoteNotFound(f"note not found: {user_path!r}")
    return candidate
