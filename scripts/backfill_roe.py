"""Enrich existing portfolio snapshots with current published annual DART ROE.

This is a current-data enrichment, not a historical point-in-time reconstruction.
Other valuation fields, their source and fetched_at are preserved byte-for-byte.
Run from the repository root; evidence is saved only to ignored private notes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

from collectors.fundamentals.dart_roe import fetch_annual_roe
from collectors.fundamentals.db_writer import upsert_roe
from db.engine import get_engine
from shared.portfolio import Portfolio
from shared.run_log import record_collector_run


def valuation_hash(engine) -> str:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT ticker,fdate,per,pbr,eps,bps,dividend_yield,dps,"
                "corp_code,source,fetched_at "
                "FROM fundamentals ORDER BY ticker,fdate"
            )
        ).all()
    return hashlib.sha256(json.dumps([list(row) for row in rows], default=str).encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date", required=True, type=date.fromisoformat, help="Existing valuation snapshot date"
    )
    args = parser.parse_args()
    if args.date.year < 2024 or args.date > date.today():
        parser.error("Date must be a past/current snapshot from 2024 onward")
    load_dotenv(".env")
    engine = get_engine()
    started = time.monotonic()
    year = args.date.year - 1
    tickers = Portfolio.load(Path(".")).scope_tickers()
    report = {
        "snapshot_date": str(args.date),
        "annual_year": year,
        "mode": "current_published_enrichment_not_point_in_time",
        "results": {},
    }
    before = valuation_hash(engine)
    stats = {
        "total": len(tickers),
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "available": 0,
        "missing": [],
        "failed": [],
    }
    report_path = Path(f"notes/private/roe-backfill-{args.date}.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        for index, ticker in enumerate(tickers, 1):
            try:
                with engine.connect() as conn:
                    row = (
                        conn.execute(
                            text(
                                "SELECT corp_code FROM fundamentals "
                                "WHERE ticker=:ticker AND fdate=:fdate"
                            ),
                            {"ticker": ticker, "fdate": args.date},
                        )
                        .mappings()
                        .first()
                    )
                if row is None or not row["corp_code"]:
                    raise ValueError("missing_snapshot_or_entity")
                observation = fetch_annual_roe(row["corp_code"], year)
                if observation is None:
                    stats["missing"].append(ticker)
                    stats["skipped"] += 1
                    report["results"][ticker] = {"status": "not_provided"}
                else:
                    outcome = upsert_roe(
                        engine,
                        ticker=ticker,
                        fdate=args.date,
                        corp_code=row["corp_code"],
                        observation=observation,
                    )
                    stats[outcome] += 1
                    stats["available"] += 1
                    report["results"][ticker] = {
                        "status": outcome,
                        "roe": str(observation.value),
                        "roe_percent": str(observation.value * 100),
                        "period_end": str(observation.period_end),
                        "source": observation.source,
                        "retrieved_at": observation.fetched_at.isoformat(),
                        "db_observation_timestamp_preserved": outcome == "skipped",
                    }
            except Exception as exc:
                # Never serialize a requests exception or its credential-bearing URL.
                stats["failed"].append({"ticker": ticker, "error": type(exc).__name__})
                report["results"][ticker] = {"status": "failed", "error": type(exc).__name__}
            report["stats"] = stats
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if index % 20 == 0 or index == len(tickers):
                print(
                    json.dumps(
                        {
                            "processed": index,
                            "total": len(tickers),
                            "available": stats["available"],
                            "missing": len(stats["missing"]),
                            "failed": len(stats["failed"]),
                        }
                    ),
                    flush=True,
                )
            time.sleep(0.1)
        after = valuation_hash(engine)
        report["other_metrics_unchanged"] = before == after
        report["valuation_hash_before"] = before
        report["valuation_hash_after"] = after
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if before != after:
            raise RuntimeError("Other valuation fields changed during enrichment")
        record_collector_run(
            engine,
            "fundamentals",
            stats,
            int((time.monotonic() - started) * 1000),
            extra={"mode": "roe_only", "year": year, "snapshot_date": str(args.date)},
        )
        print(json.dumps({"other_metrics_unchanged": True, "stats": stats}), flush=True)
        if stats["failed"]:
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
