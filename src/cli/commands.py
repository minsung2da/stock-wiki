"""stock CLI subcommand handlers.

Each ``cmd_*`` takes the parsed ``argparse.Namespace`` and returns an int
exit code. Handlers delegate to the domain modules (collectors.*, ingest.*) —
CLI logic stays thin so it can be unit-tested via ``main(argv)`` +
monkeypatching at the module boundary.

Phase 4 Plan 06 (D-18..D-21):
- ``cmd_collect_{krx,news,macro,kind}`` — individual collectors.
- ``cmd_collect_all`` — runs default {krx, news, macro, kind} (dart excluded
  by D-18 backward-compat) with in-process try/except isolation (D-19),
  stderr JSON report (D-20), and ``--sources=a,b`` filtering with
  fail-fast on unknown names (D-21).
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "cmd_collect_dart",
    "cmd_collect_krx",
    "cmd_collect_news",
    "cmd_collect_macro",
    "cmd_collect_kind",
    "cmd_collect_all",
    "cmd_ingest_run",
    "cmd_ingest_rebuild",
    "cmd_sync",
]

# D-18: default `collect all` source set excludes dart (Phase 3 kept standalone).
_KNOWN_SOURCES: tuple[str, ...] = ("dart", "krx", "news", "macro", "kind")
_DEFAULT_ALL: tuple[str, ...] = ("krx", "news", "macro", "kind")


def _dispatch() -> dict[str, Any]:
    """Lazy-import collector entrypoints.

    Keeps import cost off the CLI startup path and lets tests inject fakes by
    patching this symbol (``monkeypatch.setattr(cli.commands, "_dispatch", ...)``).
    """
    from collectors.dart import collect_dart
    from collectors.kind import collect_kind
    from collectors.krx import collect_krx
    from collectors.macro import collect_macro
    from collectors.news import collect_news

    return {
        "dart": collect_dart,
        "krx": collect_krx,
        "news": collect_news,
        "macro": collect_macro,
        "kind": collect_kind,
    }


def _engine() -> Any:
    """Lazy-construct the SQLAlchemy engine so tests can stub it cheaply."""
    from db.engine import get_engine

    return get_engine()


# ---------- individual subcommands ----------


def cmd_collect_dart(args) -> int:  # noqa: ANN001
    """Handle `stock collect dart ...`. Returns exit code.

    Wires ``engine=get_engine()`` so production runs auto-seed
    ``entities``/``entity_aliases`` (Bug C fix, quick-260418-asr). Failure to
    open an engine here bubbles up — the CLI cannot meaningfully continue
    without DB seeding for downstream ``stock ingest run``.

    D-18 backward compat: signature unchanged from Phase 3.
    """
    from collectors.dart import collect_dart
    from db.engine import get_engine

    stats = collect_dart(
        corp_code=args.corp_code,
        since=args.since,
        max_docs=args.max_docs,
        vault_root=Path(args.vault_root),
        engine=get_engine(),
    )
    print(json.dumps(stats, ensure_ascii=False, default=str))
    return 0


def cmd_collect_krx(args) -> int:  # noqa: ANN001
    """Handle `stock collect krx ...` (COLL-02)."""
    stats = _dispatch()["krx"](
        vault_root=Path(args.vault_root),
        engine=_engine(),
        since=args.since,
    )
    print(json.dumps(stats, ensure_ascii=False, default=str))
    return 0 if not stats.get("failed") else 1


def cmd_collect_news(args) -> int:  # noqa: ANN001
    """Handle `stock collect news ...` (COLL-03)."""
    stats = _dispatch()["news"](
        vault_root=Path(args.vault_root),
        engine=_engine(),
        since=args.since,
        max_per_feed=args.max_per_feed,
    )
    print(json.dumps(stats, ensure_ascii=False, default=str))
    return 0 if not stats.get("failed") else 1


def cmd_collect_macro(args) -> int:  # noqa: ANN001
    """Handle `stock collect macro ...` (COLL-04)."""
    series = [s.strip() for s in args.series.split(",") if s.strip()] if args.series else None
    stats = _dispatch()["macro"](
        vault_root=Path(args.vault_root),
        engine=_engine(),
        series=series,
    )
    print(json.dumps(stats, ensure_ascii=False, default=str))
    return 0 if not stats.get("failed") else 1


def cmd_collect_kind(args) -> int:  # noqa: ANN001
    """Handle `stock collect kind ...` (COLL-05)."""
    stats = _dispatch()["kind"](
        vault_root=Path(args.vault_root),
        engine=_engine(),
        since=args.since,
    )
    print(json.dumps(stats, ensure_ascii=False, default=str))
    return 0 if not stats.get("failed") else 1


# ---------- orchestrator ----------


def cmd_collect_all(args) -> int:  # noqa: ANN001
    """Handle `stock collect all [--sources=a,b,...]` (D-18..D-21).

    In-process try/except isolation (D-19): one collector's exception is
    recorded into the per-source report entry; sibling collectors still run.

    Exit codes (D-20):
    - ``0`` when every source ran to completion without failures
    - ``1`` when any source ``status`` is ``"error"`` or ``"partial"``
    - ``2`` when ``--sources`` contains an unknown name (D-21 fail-fast)
    """
    raw = args.sources if getattr(args, "sources", None) else ",".join(_DEFAULT_ALL)
    requested = [s.strip() for s in raw.split(",") if s.strip()]
    unknown = [s for s in requested if s not in _KNOWN_SOURCES]
    if unknown:
        print(f"Unknown sources: {sorted(unknown)}", file=sys.stderr)
        return 2

    dispatch = _dispatch()
    vault_root = Path(args.vault_root)
    engine = _engine()
    since = getattr(args, "since", None)

    results: dict[str, dict[str, Any]] = {}
    for src in requested:
        t0 = time.monotonic()
        try:
            kwargs: dict[str, Any] = {"vault_root": vault_root, "engine": engine}
            if src in ("krx", "news", "kind"):
                kwargs["since"] = since
            src_stats = dispatch[src](**kwargs)
            status = "partial" if src_stats.get("failed") else "ok"
            entry: dict[str, Any] = {
                "status": status,
                "docs_processed": int(src_stats.get("succeeded", 0)),
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            }
            if src_stats.get("failed"):
                entry["failed_count"] = len(src_stats["failed"])
            results[src] = entry
        except Exception as exc:  # noqa: BLE001 — D-19 per-source isolation
            results[src] = {
                "status": "error",
                "error": str(exc),
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            }

    report = {
        "run_at": datetime.now(UTC).isoformat(),
        "sources": results,
    }
    print(json.dumps(report, ensure_ascii=False), file=sys.stderr)

    any_bad = any(r["status"] in ("error", "partial") for r in results.values())
    return 1 if any_bad else 0


# ---------- ingest (unchanged) ----------


def cmd_ingest_run(args) -> int:  # noqa: ANN001
    """Handle `stock ingest run ...`. Returns exit code."""
    from db.engine import get_engine
    from ingest.worker import ingest_run

    stats = ingest_run(
        Path(args.vault_root),
        get_engine(),
        force_reembed=args.force_reembed,
    )
    print(json.dumps(stats, ensure_ascii=False, default=str))
    return 0


def cmd_ingest_rebuild(args) -> int:  # noqa: ANN001
    """Handle `stock ingest rebuild ...` (STORE-05; D-25/28/29). Returns exit code."""
    from db.engine import get_engine
    from ingest.rebuild import rebuild_from_vault

    report = rebuild_from_vault(
        Path(args.vault_root),
        get_engine(),
        force_reembed=args.force_reembed,
        dry_run=args.dry_run,
        assume_yes=args.yes,
    )
    print(json.dumps(report, ensure_ascii=False, default=str))
    if report.get("aborted"):
        return 2
    return 0


# ---------- sync (Phase 5.1) ----------


def _git(*args: str) -> tuple[int, str, str]:
    """Run a git command, return (returncode, stdout, stderr).

    Kept thin so cmd_sync can be unit-tested by monkeypatching this symbol.
    """
    import subprocess

    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def cmd_sync(args) -> int:  # noqa: ANN001
    """Handle ``stock sync [--reingest] [--remote NAME] [--branch NAME]``.

    Brings the local clone up to date with the Routine's enrichment pushes.
    Default: fast-forward only — refuses to merge or rebase.

    Exit codes:
    - 0 : already up-to-date OR fast-forwarded successfully (and reingest, if
          requested, returned 0)
    - 1 : pull failed (network, conflict, divergence, dirty tree). Reason on stderr.
    - 2 : reingest step failed.
    """
    remote = getattr(args, "remote", "origin")
    branch = getattr(args, "branch", "main")
    reingest = getattr(args, "reingest", False)
    quiet = getattr(args, "quiet", False)

    report: dict[str, Any] = {"remote": remote, "branch": branch}

    # 1. Working tree must be clean — refuse to pull on top of dirty TRACKED
    # edits. Untracked files (lines starting with '??') are tolerated: a
    # fast-forward merge can't write through them, and git's own merge will
    # refuse if a remote-incoming file would clobber an untracked local one.
    # Common case: Obsidian canvas / .claude/worktrees/ / scratch files.
    rc, status, err = _git("status", "--porcelain")
    if rc != 0:
        report["status"] = "error"
        report["error"] = f"git status failed: {err}"
        print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
        return 1
    tracked_dirty = [line for line in status.splitlines() if line and not line.startswith("??")]
    if tracked_dirty:
        report["status"] = "dirty"
        report["dirty_files"] = tracked_dirty[:10]
        report["error"] = (
            "working tree has uncommitted tracked changes — commit or stash before sync"
        )
        print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
        return 1

    # 2. Fetch remote.
    rc, _, err = _git("fetch", remote, branch)
    if rc != 0:
        report["status"] = "error"
        report["error"] = f"git fetch failed: {err}"
        print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
        return 1

    # 3. Compare HEAD vs FETCH_HEAD.
    rc, counts, _ = _git("rev-list", "--left-right", "--count", "HEAD...FETCH_HEAD")
    if rc != 0 or "\t" not in counts:
        report["status"] = "error"
        report["error"] = "could not compute ahead/behind counts"
        print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
        return 1
    ahead_str, behind_str = counts.split("\t")
    ahead, behind = int(ahead_str), int(behind_str)
    report["ahead"] = ahead
    report["behind"] = behind

    if behind == 0 and ahead == 0:
        report["status"] = "up_to_date"
    elif ahead > 0 and behind > 0:
        report["status"] = "diverged"
        report["error"] = (
            f"local is {ahead} ahead and {behind} behind {remote}/{branch} — "
            f"resolve manually (rebase or merge)"
        )
        print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
        return 1
    elif ahead > 0:
        report["status"] = "ahead_only"
        # nothing to pull; still allow reingest if requested
    else:
        # behind only — safe fast-forward
        rc, _, err = _git("merge", "--ff-only", "FETCH_HEAD")
        if rc != 0:
            report["status"] = "error"
            report["error"] = f"fast-forward failed: {err}"
            print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
            return 1
        report["status"] = "fast_forwarded"

    # 4. Optional re-ingest.
    if reingest:
        try:
            from db.engine import get_engine
            from ingest.worker import ingest_run

            stats = ingest_run(Path(args.vault_root), get_engine(), force_reembed=False)
            report["ingest"] = stats
        except Exception as exc:  # noqa: BLE001
            report["status"] = "ingest_failed"
            report["ingest_error"] = repr(exc)
            print(json.dumps(report, ensure_ascii=False, default=str), file=sys.stderr)
            return 2

    if not quiet:
        print(json.dumps(report, ensure_ascii=False, default=str))
    return 0
