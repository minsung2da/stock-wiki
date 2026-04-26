"""Tests for `stock sync` (Phase 5.1).

Mocks the `_git` thunk in `cli.commands` so no real git process runs.
"""

from __future__ import annotations

import argparse
from typing import Any

from cli import commands as cli_commands


def _make_args(**overrides: Any) -> argparse.Namespace:
    defaults = {
        "remote": "origin",
        "branch": "main",
        "reingest": False,
        "quiet": False,
        "vault_root": "vault",
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _git_responder(responses: dict[tuple[str, ...], tuple[int, str, str]]):
    """Build a fake _git that returns the configured (rc, stdout, stderr) per arg tuple."""

    def _git(*args: str) -> tuple[int, str, str]:
        return responses[args]

    return _git


# ---- 1. clean tree, up-to-date ----


def test_sync_up_to_date(monkeypatch, capsys):
    fake = _git_responder(
        {
            ("status", "--porcelain"): (0, "", ""),
            ("fetch", "origin", "main"): (0, "", ""),
            ("rev-list", "--left-right", "--count", "HEAD...FETCH_HEAD"): (0, "0\t0", ""),
        }
    )
    monkeypatch.setattr(cli_commands, "_git", fake)
    rc = cli_commands.cmd_sync(_make_args())
    assert rc == 0
    assert '"status": "up_to_date"' in capsys.readouterr().out


# ---- 2. behind only → fast-forward ----


def test_sync_fast_forward(monkeypatch, capsys):
    fake = _git_responder(
        {
            ("status", "--porcelain"): (0, "", ""),
            ("fetch", "origin", "main"): (0, "", ""),
            ("rev-list", "--left-right", "--count", "HEAD...FETCH_HEAD"): (0, "0\t3", ""),
            ("merge", "--ff-only", "FETCH_HEAD"): (0, "Updating ...\nFast-forward", ""),
        }
    )
    monkeypatch.setattr(cli_commands, "_git", fake)
    rc = cli_commands.cmd_sync(_make_args())
    assert rc == 0
    out = capsys.readouterr().out
    assert '"status": "fast_forwarded"' in out
    assert '"behind": 3' in out


# ---- 3. dirty tree → refuse ----


def test_sync_dirty_tracked_tree_refused(monkeypatch, capsys):
    """Tracked modifications block sync (could conflict on FF merge)."""
    fake = _git_responder(
        {
            ("status", "--porcelain"): (0, " M README.md", ""),
        }
    )
    monkeypatch.setattr(cli_commands, "_git", fake)
    rc = cli_commands.cmd_sync(_make_args())
    assert rc == 1
    err = capsys.readouterr().err
    assert "dirty" in err
    assert "tracked" in err


def test_sync_untracked_only_allowed(monkeypatch, capsys):
    """Untracked files (Obsidian canvas, scratch dirs) must NOT block sync — git's
    own FF merge refuses if a remote file would overwrite an untracked local one,
    so we don't need to be more conservative than git itself."""
    fake = _git_responder(
        {
            ("status", "--porcelain"): (0, "?? scratch.md\n?? .claude/worktrees/", ""),
            ("fetch", "origin", "main"): (0, "", ""),
            ("rev-list", "--left-right", "--count", "HEAD...FETCH_HEAD"): (0, "0\t0", ""),
        }
    )
    monkeypatch.setattr(cli_commands, "_git", fake)
    rc = cli_commands.cmd_sync(_make_args())
    assert rc == 0
    out = capsys.readouterr().out
    assert '"status": "up_to_date"' in out


def test_sync_mixed_tracked_and_untracked_refused(monkeypatch, capsys):
    """If tracked dirt exists, untracked alongside doesn't make it OK."""
    fake = _git_responder(
        {
            ("status", "--porcelain"): (
                0,
                " M src/foo.py\n?? scratch.txt\nM  staged.py",
                "",
            ),
        }
    )
    monkeypatch.setattr(cli_commands, "_git", fake)
    rc = cli_commands.cmd_sync(_make_args())
    assert rc == 1
    err = capsys.readouterr().err
    assert "dirty" in err
    # Only tracked lines should appear in dirty_files
    assert "scratch.txt" not in err


# ---- 4. diverged → refuse ----


def test_sync_diverged_refused(monkeypatch, capsys):
    fake = _git_responder(
        {
            ("status", "--porcelain"): (0, "", ""),
            ("fetch", "origin", "main"): (0, "", ""),
            ("rev-list", "--left-right", "--count", "HEAD...FETCH_HEAD"): (0, "2\t3", ""),
        }
    )
    monkeypatch.setattr(cli_commands, "_git", fake)
    rc = cli_commands.cmd_sync(_make_args())
    assert rc == 1
    err = capsys.readouterr().err
    assert '"status": "diverged"' in err


# ---- 5. fetch failure ----


def test_sync_fetch_failed(monkeypatch, capsys):
    fake = _git_responder(
        {
            ("status", "--porcelain"): (0, "", ""),
            ("fetch", "origin", "main"): (128, "", "fatal: unable to access ..."),
        }
    )
    monkeypatch.setattr(cli_commands, "_git", fake)
    rc = cli_commands.cmd_sync(_make_args())
    assert rc == 1
    assert "git fetch failed" in capsys.readouterr().err


# ---- 6. ahead-only (local has commits, remote behind) → no-op success ----


def test_sync_ahead_only_no_op(monkeypatch, capsys):
    fake = _git_responder(
        {
            ("status", "--porcelain"): (0, "", ""),
            ("fetch", "origin", "main"): (0, "", ""),
            ("rev-list", "--left-right", "--count", "HEAD...FETCH_HEAD"): (0, "1\t0", ""),
        }
    )
    monkeypatch.setattr(cli_commands, "_git", fake)
    rc = cli_commands.cmd_sync(_make_args())
    assert rc == 0
    assert '"status": "ahead_only"' in capsys.readouterr().out


# ---- 7. quiet flag suppresses stdout ----


def test_sync_quiet_suppresses_stdout(monkeypatch, capsys):
    fake = _git_responder(
        {
            ("status", "--porcelain"): (0, "", ""),
            ("fetch", "origin", "main"): (0, "", ""),
            ("rev-list", "--left-right", "--count", "HEAD...FETCH_HEAD"): (0, "0\t0", ""),
        }
    )
    monkeypatch.setattr(cli_commands, "_git", fake)
    rc = cli_commands.cmd_sync(_make_args(quiet=True))
    assert rc == 0
    assert capsys.readouterr().out == ""


# ---- 8. --reingest invokes ingest_run ----


def test_sync_reingest_invoked(monkeypatch, capsys):
    fake = _git_responder(
        {
            ("status", "--porcelain"): (0, "", ""),
            ("fetch", "origin", "main"): (0, "", ""),
            ("rev-list", "--left-right", "--count", "HEAD...FETCH_HEAD"): (0, "0\t0", ""),
        }
    )
    monkeypatch.setattr(cli_commands, "_git", fake)

    calls = []

    def _fake_engine():
        return "fake_engine"

    def _fake_ingest_run(vault_root, engine, force_reembed=False):
        calls.append((str(vault_root), engine, force_reembed))
        return {"docs_processed": 8, "chunks_upserted": 42}

    # Inject fake modules into sys.modules so the lazy imports inside cmd_sync
    # pick up the fakes.
    import sys
    import types

    fake_engine_mod = types.ModuleType("db.engine")
    fake_engine_mod.get_engine = _fake_engine  # type: ignore[attr-defined]
    fake_worker_mod = types.ModuleType("ingest.worker")
    fake_worker_mod.ingest_run = _fake_ingest_run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "db.engine", fake_engine_mod)
    monkeypatch.setitem(sys.modules, "ingest.worker", fake_worker_mod)

    rc = cli_commands.cmd_sync(_make_args(reingest=True))
    assert rc == 0
    assert len(calls) == 1
    assert calls[0] == ("vault", "fake_engine", False)
    out = capsys.readouterr().out
    assert '"docs_processed": 8' in out


# ---- 9. ingest_run failure surfaces as exit 2 ----


def test_sync_reingest_failure_exits_2(monkeypatch, capsys):
    fake = _git_responder(
        {
            ("status", "--porcelain"): (0, "", ""),
            ("fetch", "origin", "main"): (0, "", ""),
            ("rev-list", "--left-right", "--count", "HEAD...FETCH_HEAD"): (0, "0\t0", ""),
        }
    )
    monkeypatch.setattr(cli_commands, "_git", fake)

    import sys
    import types

    fake_engine_mod = types.ModuleType("db.engine")
    fake_engine_mod.get_engine = lambda: "engine"  # type: ignore[attr-defined]
    fake_worker_mod = types.ModuleType("ingest.worker")

    def _boom(*a, **k):
        raise RuntimeError("DB unreachable")

    fake_worker_mod.ingest_run = _boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "db.engine", fake_engine_mod)
    monkeypatch.setitem(sys.modules, "ingest.worker", fake_worker_mod)

    rc = cli_commands.cmd_sync(_make_args(reingest=True))
    assert rc == 2
    assert "ingest_failed" in capsys.readouterr().err
