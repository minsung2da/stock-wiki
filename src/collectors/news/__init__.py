"""News collector (COLL-03, D-09..D-13). No anthropic/openai imports (COLL-07).

PHASE 1 v2.0 (plan 01-06): cutover from ``vault/raw/news/*.md`` Markdown writes
to direct UPSERTs into the ``news`` Postgres table via ``db_writer``.

The collector still extracts the same 2-paragraph body (D-13 cap), still
respects the R-08 retry semantics, and still runs the R-09 startup guard
that refuses to operate without seeded entity aliases. Only the persistence
backend changed.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from collectors.news import client, db_writer, fetcher, matcher
from collectors.news.feeds import FEEDS_BY_OUTLET
from collectors.news.matcher import NoAliasesSeededError
from shared.portfolio import Portfolio
from shared.run_log import record_collector_run

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_log = logging.getLogger(__name__)

__all__ = ["collect_news", "NoAliasesSeededError", "FEEDS_BY_OUTLET"]


def collect_news(
    *,
    engine: Engine,
    since: str | None = None,
    max_per_feed: int = 100,
) -> dict[str, Any]:
    """Run the news collector (한경 + 이데일리).

    D-10 step 4: alias-match article title+body against scope entity aliases;
    drop unmatched.
    D-12: scope = portfolio.holdings ∪ portfolio.watchlist (single DB query
    loads alias inventory once per run — R-01).
    D-13: body hard-capped to 2 paragraphs, license_flag='summary_only'.
    D-24: license_flag='summary_only' persisted on the news row.
    R-08: RSS fetched via requests; article HTML via trafilatura — independent
    retry scopes, shared scheme guard.
    R-09: startup guard raises NoAliasesSeededError if entity_aliases unseeded.
    R-11: content_hash is URL-independent; two distinct URLs with identical
    body produce two news rows with identical ``content_hash`` (accepted
    tradeoff — surfaces in DB queries as duplicate-body detection).
    """
    start = time.monotonic()
    if engine is None:
        raise RuntimeError("collect_news requires a DB engine for alias resolution")

    # R-09: refuse to run when aliases are not seeded (BEFORE any HTTP call).
    matcher.assert_aliases_seeded(engine)

    # Portfolio still lives on disk at <repo_root>/notes/private/portfolio.md
    # (Phase 6 P-01). repo_root is the current working directory under v2.0
    # — the CLI no longer accepts ``--vault-root``.
    repo_root = Path(".")
    portfolio = Portfolio.load(repo_root)
    scope = portfolio.scope_tickers()
    # R-01: single DB round-trip for the scoped alias inventory.
    alias_map = matcher.load_scoped_aliases(engine, scope)

    stats: dict[str, Any] = {
        "total": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "failed": [],
    }

    for outlet, urls in FEEDS_BY_OUTLET.items():
        for feed_url in urls:
            try:
                rss_bytes = client.fetch_rss_feed(feed_url)  # R-08: requests
                if not rss_bytes:
                    continue
                items = fetcher.parse_rss(rss_bytes)[:max_per_feed]
                for item in items:
                    stats["total"] += 1
                    try:
                        html = client.fetch_article_html(item.url)  # R-08: trafilatura
                        if not html:
                            stats["skipped"] += 1
                            continue
                        body = fetcher.extract_first_two_paragraphs(html)
                        if not body:
                            stats["skipped"] += 1
                            continue
                        matches = matcher.match_tickers_in_text(
                            f"{item.title}\n{body}", alias_map
                        )
                        if not matches:
                            stats["skipped"] += 1
                            continue
                        # matcher returns [{"corp_code", "ticker", "name"}, ...].
                        # Extract ticker strings for the TEXT[] column, and use
                        # the first match's corp_code for the FK (Q1 §news).
                        tickers = [m["ticker"] for m in matches]
                        primary_corp_code = matches[0].get("corp_code")
                        published_at = (
                            item.published
                            if item.published is not None
                            else datetime.fromtimestamp(0, tz=UTC)
                        )
                        outcome = db_writer.upsert_news_article(
                            engine,
                            url=item.url,
                            outlet=outlet,
                            published_at=published_at,
                            title=item.title,
                            body_md=body,
                            tickers=tickers,
                            corp_code=primary_corp_code,
                        )
                        if outcome == "inserted":
                            stats["inserted"] += 1
                        elif outcome == "updated":
                            stats["updated"] += 1
                        else:
                            stats["skipped"] += 1
                    except Exception as exc:
                        _log.exception("news item failed")
                        stats["failed"].append({"doc": item.url, "error": str(exc)})
            except Exception as exc:
                _log.exception("news feed failed")
                stats["failed"].append({"doc": feed_url, "error": str(exc)})

    stats["elapsed_ms"] = int((time.monotonic() - start) * 1000)
    _log.info(
        "collector_run_complete",
        extra={
            "source": "news",
            "stats": stats,
            "elapsed_ms": stats["elapsed_ms"],
        },
    )
    # Plan 01-08: dual-sink DB row (RESEARCH.md Q5). News collector has no
    # per-source extras at Phase 1 (matcher/RSS retry info already lives in
    # stats.failed); pass extra=None.
    record_collector_run(engine, "news", stats, stats["elapsed_ms"], extra=None)
    return stats
