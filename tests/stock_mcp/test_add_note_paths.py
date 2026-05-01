"""add_note path whitelist + alias tests (Plan 06-06 Task 1, P1-P6)."""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from stock_mcp.tools.notes import add_note


def _is_error(resp) -> bool:
    return isinstance(resp, dict) and "error" in resp


def test_p1_creates_new_note_in_vault_notes(mcp_vault_isolated):
    _engine, _vault, repo = mcp_vault_isolated
    resp = add_note(path="vault/notes/foo.md", body="hi", frontmatter={"type": "note"})
    assert not _is_error(resp), resp
    assert resp.action == "created"
    assert resp.idempotent is False
    assert resp.vault_path == "vault/notes/foo.md"
    assert (repo / "vault" / "notes" / "foo.md").exists()


def test_p2_rejects_write_outside_whitelist_raw(mcp_vault_isolated):
    resp = add_note(path="raw/dart/x.md", body="x", frontmatter={"type": "note"})
    assert _is_error(resp)
    assert resp["error"]["code"] == "WRITE_FORBIDDEN"


def test_p3_rejects_traversal_escape(mcp_vault_isolated):
    resp = add_note(path="../etc/passwd", body="x", frontmatter={"type": "note"})
    assert _is_error(resp)
    assert resp["error"]["code"] == "WRITE_FORBIDDEN"


def test_p4_alias_journal_today(mcp_vault_isolated):
    _engine, _vault, repo = mcp_vault_isolated
    resp = add_note(path="journal/today", body="hi", frontmatter={"type": "journal"})
    assert not _is_error(resp), resp
    kst_today = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    expected = f"notes/private/journal/{kst_today}.md"
    assert resp.vault_path == expected
    assert (repo / expected).exists()


def test_p5_alias_ticker_thesis_auto_mkdir(mcp_vault_isolated):
    _engine, _vault, repo = mcp_vault_isolated
    resp = add_note(path="005930/thesis", body="x", frontmatter={"type": "thesis"})
    assert not _is_error(resp), resp
    assert resp.vault_path == "notes/private/005930/thesis.md"
    assert (repo / "notes" / "private" / "005930" / "thesis.md").exists()


def test_p6_symlink_escape_blocked(mcp_vault_isolated, tmp_path):
    _engine, _vault, repo = mcp_vault_isolated
    sneaky = repo / "notes" / "private" / "sneaky"
    sneaky.mkdir(parents=True, exist_ok=True)
    escape_target = tmp_path / "escape_target"
    escape_target.mkdir()
    link = sneaky / "escape"
    try:
        os.symlink(str(escape_target), str(link))
    except (OSError, NotImplementedError):
        pytest.skip("symlink not supported on this filesystem")
    resp = add_note(
        path="notes/private/sneaky/escape/foo.md",
        body="x",
        frontmatter={"type": "note"},
    )
    assert _is_error(resp)
    assert resp["error"]["code"] == "WRITE_FORBIDDEN"
