"""stock CLI subcommand handlers — collectors only (post-shutdown).

The ingest/sync/graph handlers were removed as part of the LLM-wiki shutdown
(see git tag ``pre-llm-wiki-shutdown`` / branch ``archive/llm-wiki-2026-04``).
Only the ``cmd_collect_*`` family remains; the DB-direct collector redesign
is pending.

Each ``cmd_*`` takes the parsed ``argparse.Namespace`` and returns an int
exit code. Handlers delegate to ``collectors.*`` — CLI logic stays thin so
it can be unit-tested via ``main(argv)`` + monkeypatching at the module
boundary.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

__all__ = [
    "cmd_collect_dart",
    "cmd_collect_krx",
    "cmd_collect_news",
    "cmd_collect_macro",
    "cmd_collect_fundamentals",
    "cmd_collect_all",
]

_KNOWN_SOURCES: tuple[str, ...] = ("dart", "krx", "news", "macro", "fundamentals")
_DEFAULT_ALL = _KNOWN_SOURCES


def _dispatch() -> dict[str, Any]:
    """Lazy-import collector entrypoints.

    Keeps import cost off the CLI startup path and lets tests inject fakes by
    patching this symbol (``monkeypatch.setattr(cli.commands, "_dispatch", ...)``).
    """
    from collectors.dart import collect_dart
    from collectors.fundamentals import collect_fundamentals
    from collectors.krx import collect_krx
    from collectors.macro import collect_macro
    from collectors.news import collect_news

    return {
        "dart": collect_dart,
        "krx": collect_krx,
        "news": collect_news,
        "macro": collect_macro,
        "fundamentals": collect_fundamentals,
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
    without DB seeding for downstream collectors.

    D-18 backward compat: signature unchanged from Phase 3.
    """
    from collectors.dart import collect_dart
    from db.engine import get_engine

    stats = collect_dart(
        corp_code=args.corp_code,
        since=args.since,
        max_docs=args.max_docs,
        engine=get_engine(),
    )
    print(json.dumps(stats, ensure_ascii=False, default=str))
    return 0


def cmd_collect_krx(args) -> int:  # noqa: ANN001
    """Handle `stock collect krx ...` (COLL-02)."""
    stats = _dispatch()["krx"](
        engine=_engine(),
        since=args.since,
    )
    print(json.dumps(stats, ensure_ascii=False, default=str))
    return 0 if not stats.get("failed") else 1


def cmd_collect_news(args) -> int:  # noqa: ANN001
    """Handle `stock collect news ...` (COLL-03)."""
    stats = _dispatch()["news"](
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
        engine=_engine(),
        series=series,
    )
    print(json.dumps(stats, ensure_ascii=False, default=str))
    return 0 if not stats.get("failed") else 1


def cmd_collect_fundamentals(args) -> int:  # noqa: ANN001
    """Handle `stock collect fundamentals ...` (D-06).

    Mirrors ``cmd_collect_krx``: build the engine, run ``collect_fundamentals``,
    emit the stats as stdout JSON (CLAUDE.md convention — structured logs to
    stderr, user output stdout JSON).
    """
    from collectors.fundamentals import collect_fundamentals

    stats = collect_fundamentals(
        engine=_engine(),
        since=args.since,
    )
    print(json.dumps(stats, ensure_ascii=False, default=str))
    return 0 if not stats.get("failed") else 1


# ---------- orchestrator ----------


def _collect_scoped_dart(collector, *, engine: Any, since: str) -> dict[str, Any]:
    """Collect every distinct portfolio corporation, isolating individual failures."""
    from db.entity import resolve_entities
    from shared.portfolio import Portfolio

    scope = Portfolio.load(Path(".")).scope_tickers()
    entities = resolve_entities(engine, scope)
    stats: dict[str, Any] = {"total": 0, "inserted": 0, "updated": 0, "skipped": 0, "failed": []}
    corp_codes: set[str] = set()
    for ticker in scope:
        entity = entities.get(ticker)
        if entity is None or not entity.corp_code:
            stats["failed"].append({"doc": ticker, "error": "missing_entity"})
        else:
            corp_codes.add(entity.corp_code)
    for corp_code in sorted(corp_codes):
        try:
            result = collector(engine=engine, corp_code=corp_code, since=since, max_docs=100)
            for key in ("total", "inserted", "updated", "skipped"):
                stats[key] += int(result.get(key, 0))
            stats["failed"].extend(result.get("failed", []))
        except Exception as exc:
            stats["failed"].append({"doc": corp_code, "error": str(exc)})
    return stats


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
    requested = list(dict.fromkeys(s.strip() for s in raw.split(",") if s.strip()))
    unknown = [s for s in requested if s not in _KNOWN_SOURCES]
    if unknown or not requested:
        print(f"Unknown sources: {sorted(unknown)}", file=sys.stderr)
        return 2

    try:
        since = (
            date.fromisoformat(args.since)
            if getattr(args, "since", None)
            else datetime.now(ZoneInfo("Asia/Seoul")).date()
        ).isoformat()
    except ValueError:
        print("Invalid --since: expected YYYY-MM-DD calendar date", file=sys.stderr)
        return 2
    dispatch = _dispatch()
    engine = _engine()

    results: dict[str, dict[str, Any]] = {}
    for src in requested:
        t0 = time.monotonic()
        try:
            kwargs: dict[str, Any] = {"engine": engine}
            if src in ("krx", "news", "fundamentals"):
                kwargs["since"] = since
            src_stats = (
                _collect_scoped_dart(dispatch[src], engine=engine, since=since)
                if src == "dart"
                else dispatch[src](**kwargs)
            )
            status = "partial" if src_stats.get("failed") else "ok"
            entry: dict[str, Any] = {
                "status": status,
                "docs_processed": sum(
                    int(src_stats.get(key, 0)) for key in ("inserted", "updated", "skipped")
                ),
                "inserted": int(src_stats.get("inserted", 0)),
                "updated": int(src_stats.get("updated", 0)),
                "skipped": int(src_stats.get("skipped", 0)),
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            }
            if src_stats.get("failed"):
                entry["failed_count"] = len(src_stats["failed"])
                entry["failed"] = src_stats["failed"]
            results[src] = entry
        except Exception as exc:  # noqa: BLE001 — D-19 per-source isolation
            results[src] = {
                "status": "error",
                "error": str(exc),
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            }

    report = {
        "run_at": datetime.now(UTC).isoformat(),
        "collection_date": since,
        "sources": results,
    }
    print(json.dumps(report, ensure_ascii=False), file=sys.stderr)

    any_bad = any(r["status"] in ("error", "partial") for r in results.values())
    return 1 if any_bad else 0
