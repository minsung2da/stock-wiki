"""News collector (COLL-03, D-09..D-13). No anthropic/openai imports (COLL-07)."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from collectors.news import client, fetcher, matcher, writer
from collectors.news.feeds import FEEDS_BY_OUTLET
from collectors.news.matcher import NoAliasesSeededError
from ingest.heartbeat import record_source_run
from shared.frontmatter import read_frontmatter
from shared.portfolio import Portfolio

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_log = logging.getLogger(__name__)

__all__ = ["collect_news", "NoAliasesSeededError", "FEEDS_BY_OUTLET"]


def _read_existing_hash(path: Path) -> str | None:
    try:
        fm, _ = read_frontmatter(str(path))
        return fm.provenance.content_hash
    except Exception:
        return None


def collect_news(
    *,
    vault_root: Path = Path("."),
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
    D-24: trust_level='semi_trusted'.
    R-08: RSS fetched via requests; article HTML via trafilatura — independent
    retry scopes, shared scheme guard.
    R-09: startup guard raises NoAliasesSeededError if entity_aliases unseeded.
    R-11: content_hash is URL-independent; two distinct URLs with identical
    body yield two files with identical content_hash (accepted tradeoff).
    """
    start = time.monotonic()
    if engine is None:
        raise RuntimeError("collect_news requires a DB engine for alias resolution")

    # R-09: refuse to run when aliases are not seeded (BEFORE any HTTP call).
    matcher.assert_aliases_seeded(engine)

    portfolio = Portfolio.load(vault_root)
    scope = portfolio.scope_tickers()
    # R-01: single DB round-trip for the scoped alias inventory.
    alias_map = matcher.load_scoped_aliases(engine, scope)

    stats: dict[str, Any] = {"total": 0, "succeeded": 0, "skipped": 0, "failed": []}

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
                        url_hash = client.url_hash8(item.url)
                        pub_iso = item.published.isoformat() if item.published else "1970-01-01"
                        yyyymm = pub_iso[:7].replace("-", "")
                        html = client.fetch_article_html(item.url)  # R-08: trafilatura
                        if not html:
                            stats["skipped"] += 1
                            continue
                        body = fetcher.extract_first_two_paragraphs(html)
                        if not body:
                            stats["skipped"] += 1
                            continue
                        tickers = matcher.match_tickers_in_text(f"{item.title}\n{body}", alias_map)
                        if not tickers:
                            stats["skipped"] += 1
                            continue
                        # Idempotency: skip if an existing file has the same content_hash.
                        path = writer.vault_path_for_news(vault_root, outlet, yyyymm, url_hash)
                        new_hash = writer.compute_news_content_hash(item.title, body)
                        if path.exists() and _read_existing_hash(path) == new_hash:
                            stats["skipped"] += 1
                            continue
                        writer.write_news_doc(
                            vault_root=vault_root,
                            outlet=outlet,
                            url=item.url,
                            url_hash8=url_hash,
                            yyyymm=yyyymm,
                            title=item.title,
                            published_iso=pub_iso,
                            tickers=tickers,
                            body=body,
                        )
                        stats["succeeded"] += 1
                    except Exception as exc:
                        _log.exception("news item failed")
                        stats["failed"].append({"doc": item.url, "error": str(exc)})
            except Exception as exc:
                _log.exception("news feed failed")
                stats["failed"].append({"doc": feed_url, "error": str(exc)})

    stats["elapsed_ms"] = int((time.monotonic() - start) * 1000)
    record_source_run(
        "news", stats, heartbeat_path=vault_root / "ingested" / "_status" / "heartbeat.md"
    )
    return stats
