"""stock CLI entry (D-20, D-28).

Usage examples::

    stock --help
    stock collect dart --corp-code=00126380 --since=2026-01-01
    stock ingest run
    stock ingest rebuild --dry-run
    stock ingest rebuild --yes
    stock ingest rebuild --force-reembed --yes

Uses argparse (no extra dependency). Subcommands are dispatched to thin
handler callables in ``cli.commands``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from cli.commands import (
    cmd_collect_all,
    cmd_collect_dart,
    cmd_collect_kind,
    cmd_collect_krx,
    cmd_collect_macro,
    cmd_collect_news,
    cmd_ingest_rebuild,
    cmd_ingest_run,
)

__all__ = ["main", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stock",
        description="stock-wiki CLI: collect, ingest, rebuild",
    )
    parser.add_argument(
        "--vault-root",
        default="vault",
        help="Vault root directory (default: vault)",
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

    news = collect_subs.add_parser("news", help="Collect 한경/이데일리 news (COLL-03)")
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

    # ingest
    ingest = subs.add_parser("ingest", help="Run ingest pipeline (parse + embed + index)")
    ingest_subs = ingest.add_subparsers(dest="action", required=True)

    ing_run = ingest_subs.add_parser("run", help="Incremental ingest (dedup by content_hash)")
    ing_run.add_argument(
        "--force-reembed",
        action="store_true",
        help="Re-embed all chunks even if content_hash unchanged",
    )
    ing_run.set_defaults(func=cmd_ingest_run)

    ing_rebuild = ingest_subs.add_parser(
        "rebuild",
        help="Full wipe + rebuild from vault (STORE-05, D-25)",
    )
    ing_rebuild.add_argument(
        "--force-reembed", action="store_true", help="Recompute every chunk embedding"
    )
    ing_rebuild.add_argument("--dry-run", action="store_true", help="Print plan without executing")
    ing_rebuild.add_argument(
        "--yes",
        action="store_true",
        help="Skip TTY confirmation prompt (D-28; for CI/cron)",
    )
    ing_rebuild.set_defaults(func=cmd_ingest_rebuild)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1
    return int(func(args))


if __name__ == "__main__":
    sys.exit(main())
