"""stock CLI entry — collectors only (post-LLM-wiki-shutdown).

The ingest, sync, and graph subcommands were removed as part of the LLM-wiki
shutdown (see git tag ``pre-llm-wiki-shutdown`` / branch
``archive/llm-wiki-2026-04``). What remains is the raw-data collection layer;
the DB-direct write path is pending redesign.

Phase 1 v2.0: ``--vault-root`` removed (collectors INSERT directly to
Postgres; ``DATABASE_URL`` env drives connection). Collector bodies still
call ``writer.*`` in Wave 0; those call sites are replaced in 01-03..01-07.

Usage examples::

    stock --help
    stock collect dart --corp-code=00126380 --since=2026-01-01
    stock collect all
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from cli.commands import (
    cmd_collect_all,
    cmd_collect_dart,
    cmd_collect_kind,
    cmd_collect_krx,
    cmd_collect_macro,
    cmd_collect_news,
)

__all__ = ["main", "build_parser"]

# Phase 1 v2.0 Veto #9 — runtime fence layer (RESEARCH.md Q9 + 01-09 R-5).
# Computed once at module import using an absolute, CWD-independent anchor.
# If any of these resurfaces at runtime (IDE-restored deleted file, accidental
# revert, etc.) main() fails fast with a clear pointer to the plan.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEGACY_WRITERS: tuple[Path, ...] = tuple(
    _REPO_ROOT / "src" / "collectors" / src / "writer.py"
    for src in ("dart", "krx", "news", "macro", "kind")
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stock",
        description="stock CLI: collect raw market data",
    )
    subs = parser.add_subparsers(dest="command", required=True)

    # collect
    collect = subs.add_parser("collect", help="Collect raw source data into raw/")
    collect_subs = collect.add_subparsers(dest="source", required=True)
    dart = collect_subs.add_parser("dart", help="Collect DART filings (COLL-01)")
    dart.add_argument("--corp-code", required=True, help="8-digit DART corp_code")
    dart.add_argument("--since", required=True, help="YYYY-MM-DD receipt date lower bound")
    dart.add_argument("--max-docs", type=int, default=100, help="Phase-3 cap (D-03)")
    dart.set_defaults(func=cmd_collect_dart)

    krx = collect_subs.add_parser("krx", help="Collect KRX OHLCV + flow + short (COLL-02)")
    krx.add_argument("--since", default=None, help="YYYY-MM-DD (default: today KST trading day)")
    krx.set_defaults(func=cmd_collect_krx)

    news = collect_subs.add_parser(
        "news",
        help="Collect 한경/이데일리 news (COLL-03)",
        epilog=(
            "Requires: entity_aliases table seeded before first use. "
            "Run `uv run python -m src.db.seed_name_aliases` once. "
            "See CLAUDE.md §First-time Setup."
        ),
    )
    news.add_argument("--since", default=None)
    news.add_argument("--max-per-feed", type=int, default=100)
    news.set_defaults(func=cmd_collect_news)

    macro = collect_subs.add_parser("macro", help="Collect ECOS+FRED macro (COLL-04)")
    macro.add_argument("--series", default=None, help="Comma-separated labels; default=all")
    macro.set_defaults(func=cmd_collect_macro)

    kind = collect_subs.add_parser("kind", help="Collect KIND events (COLL-05)")
    kind.add_argument("--since", default=None)
    kind.set_defaults(func=cmd_collect_kind)

    all_ = collect_subs.add_parser(
        "all", help="Run collectors with per-source isolation (D-18..D-21)"
    )
    all_.add_argument(
        "--sources",
        default="krx,news,macro,kind",
        help="Comma-separated subset; default excludes dart. Unknown entries fail-fast (D-21).",
    )
    all_.add_argument("--since", default=None)
    all_.set_defaults(func=cmd_collect_all)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    # Veto #9 runtime fence — fires before any work happens so a resurrected
    # writer.py cannot leak even a single Markdown file. Uses absolute paths
    # anchored to this module's location, NOT process CWD, so the check is
    # consistent whether ``stock`` is invoked from repo root or anywhere else.
    for _legacy in _LEGACY_WRITERS:
        if _legacy.exists():
            raise SystemExit(
                f"FATAL: vault writer module resurrected ({_legacy}). "
                "Phase 1 v2.0 deleted these (Veto #9); see "
                ".planning/phases/01-collector-db-cutover/01-09-PLAN.md."
            )
    load_dotenv(find_dotenv(usecwd=True))
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1
    return int(func(args))


if __name__ == "__main__":
    sys.exit(main())
