"""One-shot seeder: insert an entities row for every ticker in
notes/private/portfolio.md (holdings ∪ watchlist) via OpenDART corp lookup.

Runs once per new machine / once per new watchlist addition. Idempotent:
`upsert_entity` uses ON CONFLICT. Missing DART corp for a ticker is logged
and skipped (doesn't abort the batch).

Operational command:
    uv run python -m src.db.seed_entities              # reads DATABASE_URL + DART_API_KEY
    uv run python -m src.db.seed_entities --repo .
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from sqlalchemy.engine import Engine

from collectors.dart import client as dart_client
from db.engine import get_engine
from db.entity import upsert_entity
from shared.portfolio import Portfolio

log = logging.getLogger(__name__)


def seed_entities_from_portfolio(engine: Engine, repo_root: Path) -> tuple[int, list[str]]:
    """Seed entities for every ticker in portfolio scope.

    Returns (upserted_count, failed_tickers). Failures are tickers with no
    matching DART corp; they do not abort the batch.
    """
    portfolio = Portfolio.load(repo_root)
    tickers = sorted(set(portfolio.scope_tickers()))

    import dart_fss

    dart_client.get_client()
    corp_list = dart_fss.get_corp_list()

    upserted = 0
    failed: list[str] = []
    for ticker in tickers:
        try:
            corp = corp_list.find_by_stock_code(ticker)
        except Exception as exc:
            log.warning("dart_fss lookup failed for ticker=%s: %s", ticker, exc)
            failed.append(ticker)
            continue
        if corp is None:
            log.warning("no DART corp for ticker=%s", ticker)
            failed.append(ticker)
            continue
        upsert_entity(
            engine,
            corp_code=corp.corp_code,
            canonical_name=corp.corp_name,
            ticker=corp.stock_code,
            market=None,
        )
        upserted += 1
    return upserted, failed


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Seed entities from portfolio.md via OpenDART.")
    parser.add_argument("--repo", default=".", help="Repo root (default: .)")
    args = parser.parse_args()

    up, failed = seed_entities_from_portfolio(get_engine(), Path(args.repo))
    print(f"seed_entities: upserted {up} rows; failed {len(failed)}: {failed}")
    sys.exit(0 if not failed else 1)
