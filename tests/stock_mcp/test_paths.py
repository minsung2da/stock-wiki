"""Phase 6 Plan 06-02 Task 2: paths helper tests (D-09 + D-12)."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from stock_mcp.errors import ErrorCode, StructuredError
from stock_mcp.paths import resolve_path_alias, safe_join


@pytest.fixture
def repo_root_tmp(tmp_path: Path) -> Path:
    """Build a tmp repo with vault/notes/ and notes/private/ ready."""
    (tmp_path / "vault" / "notes").mkdir(parents=True)
    (tmp_path / "notes" / "private").mkdir(parents=True)
    return tmp_path


# --- safe_join ---------------------------------------------------------------


def test_p1_safe_join_vault_notes(repo_root_tmp: Path) -> None:
    out = safe_join(repo_root_tmp, "vault/notes/foo.md")
    assert out.is_relative_to((repo_root_tmp / "vault" / "notes").resolve())


def test_p2_safe_join_notes_private(repo_root_tmp: Path) -> None:
    out = safe_join(repo_root_tmp, "notes/private/journal/2026-01-01.md")
    assert out.is_relative_to((repo_root_tmp / "notes" / "private").resolve())


def test_p3_safe_join_rejects_raw(repo_root_tmp: Path) -> None:
    with pytest.raises(StructuredError) as excinfo:
        safe_join(repo_root_tmp, "raw/dart/foo.md")
    assert excinfo.value.code == ErrorCode.WRITE_FORBIDDEN


def test_p4_safe_join_rejects_dotdot_escape(repo_root_tmp: Path) -> None:
    with pytest.raises(StructuredError) as excinfo:
        safe_join(repo_root_tmp, "../etc/passwd")
    assert excinfo.value.code == ErrorCode.WRITE_FORBIDDEN


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks unreliable on Windows")
def test_p5_safe_join_rejects_symlink_outside_whitelist(repo_root_tmp: Path) -> None:
    # Create a symlink under vault/notes/ pointing outside the whitelist.
    outside = repo_root_tmp / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("secret")
    link = repo_root_tmp / "vault" / "notes" / "evil_link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("filesystem refused symlink creation")
    with pytest.raises(StructuredError) as excinfo:
        safe_join(repo_root_tmp, "vault/notes/evil_link/secret.md")
    assert excinfo.value.code == ErrorCode.WRITE_FORBIDDEN


# --- resolve_path_alias ------------------------------------------------------


def test_p6_journal_today_resolves_to_kst_date() -> None:
    out = resolve_path_alias("journal/today")
    expected_date = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    assert out == f"notes/private/journal/{expected_date}.md"


def test_p6b_journal_alone_resolves_same_as_today() -> None:
    out = resolve_path_alias("journal")
    expected_date = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    assert out == f"notes/private/journal/{expected_date}.md"


def test_p7_ticker_alias_resolves_under_notes_private() -> None:
    out = resolve_path_alias("005930/thesis")
    assert out == "notes/private/005930/thesis.md"


def test_p8_vault_path_gets_md_suffix() -> None:
    out = resolve_path_alias("vault/notes/foo")
    assert out == "vault/notes/foo.md"


def test_journal_named_path_resolves_under_journal_dir() -> None:
    out = resolve_path_alias("journal/2026-04-29-recap")
    assert out == "notes/private/journal/2026-04-29-recap.md"


def test_already_md_path_unchanged() -> None:
    out = resolve_path_alias("notes/private/005930/thesis.md")
    assert out == "notes/private/005930/thesis.md"
