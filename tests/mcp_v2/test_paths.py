"""V12 — get_note read-only path-traversal defense (safe_resolve).

No DB; uses tmp_path as a fake repo root with a ``notes/private/`` tree. Proves:
- A file under ``notes/private/`` resolves OK (returns the resolved Path).
- ``../etc/passwd`` traversal and an absolute path outside the whitelist raise
  ``NotePathForbidden``.
- A symlink under ``notes/private/`` pointing OUTSIDE the whitelist raises
  ``NotePathForbidden`` (resolve() follows it before the whitelist check).
- A whitelisted but missing file raises ``NoteNotFound``.
- The whitelist is ``notes/private/`` only (no ``vault/notes`` — Veto #9).

Run: ``.venv/Scripts/python.exe -m pytest tests/mcp_v2/test_paths.py -x -q -m "not db"``
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mcp_v2.errors import NoteNotFound, NotePathForbidden
from mcp_v2.paths import WHITELIST_PREFIXES, safe_resolve


def _make_repo(tmp_path: Path) -> Path:
    """Create a fake repo root with notes/private/ and an outside dir + file."""
    (tmp_path / "notes" / "private").mkdir(parents=True)
    (tmp_path / "notes" / "private" / "005930").mkdir()
    note = tmp_path / "notes" / "private" / "005930" / "thesis.md"
    note.write_text("# thesis\n반도체 업황 메모.", encoding="utf-8")
    # An outside-the-whitelist secret the traversal/symlink tests aim at.
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET", encoding="utf-8")
    return tmp_path


def test_whitelist_is_notes_private_only() -> None:
    assert WHITELIST_PREFIXES == ("notes/private/",)


def test_resolves_whitelisted_file(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    out = safe_resolve(repo, "notes/private/005930/thesis.md")
    assert out == (repo / "notes" / "private" / "005930" / "thesis.md").resolve()
    assert out.is_file()


def test_dotdot_traversal_forbidden(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    with pytest.raises(NotePathForbidden):
        safe_resolve(repo, "notes/private/../../secret.txt")


def test_absolute_path_outside_whitelist_forbidden(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    outside = str((repo / "secret.txt").resolve())
    with pytest.raises(NotePathForbidden):
        safe_resolve(repo, outside)


def test_path_outside_whitelist_forbidden(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    # raw/dart/... is a real path under the repo but NOT in the whitelist.
    (repo / "raw" / "dart").mkdir(parents=True)
    (repo / "raw" / "dart" / "x.md").write_text("x", encoding="utf-8")
    with pytest.raises(NotePathForbidden):
        safe_resolve(repo, "raw/dart/x.md")


def test_symlink_escape_forbidden(tmp_path: Path) -> None:
    """A symlink inside notes/private pointing outside the whitelist is rejected.

    resolve() follows the symlink before the is_relative_to check. Skips if the OS
    refuses symlink creation (e.g. Windows without the privilege).
    """
    repo = _make_repo(tmp_path)
    link = repo / "notes" / "private" / "escape.md"
    target = repo / "secret.txt"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform/account")
    with pytest.raises(NotePathForbidden):
        safe_resolve(repo, "notes/private/escape.md")


def test_whitelisted_but_missing_file_not_found(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    with pytest.raises(NoteNotFound):
        safe_resolve(repo, "notes/private/does_not_exist.md")


def test_whitelisted_directory_not_a_file(tmp_path: Path) -> None:
    """A whitelisted path that is a directory (not a file) → NoteNotFound."""
    repo = _make_repo(tmp_path)
    with pytest.raises(NoteNotFound):
        safe_resolve(repo, "notes/private/005930")
