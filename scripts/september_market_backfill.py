"""Backfill September portfolio OHLCV using pykrx's adjusted Naver history.

KRX fundamentals/flow/short history currently returns empty even for Samsung.
Never replace those missing fields with estimates or erase existing flow data.
Run from the repository root; evidence is written only to gitignored notes.
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from pykrx import stock
from sqlalchemy import text

from collectors.fundamentals.db_writer import upsert_fundamentals
from collectors.krx.db_writer import upsert_ohlcv
from db.engine import get_engine
from shared.portfolio import Portfolio
from shared.run_log import record_collector_run

START = date(2026, 9, 1)
END = date(2026, 9, 23)
REPORT = Path("notes/private/september-2026-market.json")
FIELDS = {"시가": "open", "고가": "high", "저가": "low", "종가": "close", "거래량": "volume"}


def fundamentals_snapshot(engine, tickers, entities) -> None:
    """Persist current published metrics only on their real acquisition day."""
    if datetime.now(ZoneInfo("Asia/Seoul")).date() != END:
        raise ValueError("Current valuation cannot be backdated to September 23")
    started = time.monotonic()
    path = Path("notes/private/september-2026-fundamentals.json")
    report = {"asof": str(END), "source": "Naver integration current snapshot", "results": {}}
    codes = {
        "per": "per",
        "pbr": "pbr",
        "eps": "eps",
        "bps": "bps",
        "dividendYieldRatio": "dividend_yield",
        "dividend": "dps",
    }
    for index, ticker in enumerate(tickers, 1):
        try:
            base = f"https://m.stock.naver.com/api/stock/{ticker}"
            basic_response = requests.get(f"{base}/basic")
            basic_response.raise_for_status()
            basic = basic_response.json()
            if basic["itemCode"] != ticker or basic["localTradedAt"][:10] != str(END):
                raise ValueError("Ticker or source trade date mismatch")
            response = requests.get(f"{base}/integration")
            response.raise_for_status()
            payload = response.json()
            if payload["itemCode"] != ticker:
                raise ValueError("Integration ticker mismatch")
            raw = [item for item in payload["totalInfos"] if item["code"] in codes]
            values = {}
            for item in raw:
                cleaned = re.sub(r"[원배%,\s]", "", item["value"])
                value = Decimal(cleaned) if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", cleaned) else None
                values[codes[item["code"]]] = value
            if not any(value is not None for value in values.values()):
                raise ValueError("All fundamental metrics unavailable")
            with engine.connect() as conn:
                old = (
                    conn.execute(
                        text(
                            "SELECT per,pbr,eps,bps,dividend_yield,dps FROM fundamentals "
                            "WHERE ticker=:ticker AND fdate=:day"
                        ),
                        {"ticker": ticker, "day": END},
                    )
                    .mappings()
                    .first()
                )
            for field in codes.values():
                if values.get(field) is None:
                    values[field] = old[field] if old else None
            outcome = upsert_fundamentals(
                engine,
                ticker=ticker,
                fdate=END,
                corp_code=entities[ticker],
                roe=None,
                source=f"{base}/integration; observed=2026-09-23; current_snapshot",
                **values,
            )
            report["results"][ticker] = {
                "outcome": outcome,
                "localTradedAt": basic["localTradedAt"],
                "retrieved_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
                "raw_metrics": raw,
                "stored": values,
            }
        except Exception as exc:
            report["results"][ticker] = {"error": type(exc).__name__}
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        if index % 20 == 0 or index == len(tickers):
            print(json.dumps({"fundamentals_completed": index, "scope": len(tickers)}), flush=True)
    counts = Counter(result.get("outcome", "failed") for result in report["results"].values())
    record_collector_run(
        engine,
        "fundamentals",
        {
            "total": len(tickers),
            "inserted": counts["inserted"],
            "updated": counts["updated"],
            "skipped": counts["skipped"],
            "failed": [
                {"doc": ticker, "error": result["error"]}
                for ticker, result in report["results"].items()
                if "error" in result
            ],
        },
        int((time.monotonic() - started) * 1000),
        extra={"asof": str(END), "source": report["source"], "history_available": False},
    )


def main() -> None:
    started = time.monotonic()
    load_dotenv()
    engine = get_engine()
    tickers = Portfolio.load(Path.cwd()).scope_tickers()
    original_request = requests.sessions.Session.request
    last_request = 0.0

    def bounded_request(self, *args, **kwargs):
        nonlocal last_request
        time.sleep(max(0.0, 1.0 - (time.monotonic() - last_request)))
        last_request = time.monotonic()
        kwargs.setdefault("timeout", 25)
        return original_request(self, *args, **kwargs)

    requests.sessions.Session.request = bounded_request
    with engine.connect() as conn:
        entities = {
            r.current_ticker: r.corp_code
            for r in conn.execute(text("SELECT current_ticker, corp_code FROM entities"))
        }
        existing = {
            (r.ticker, r.trade_date): dict(r._mapping)
            for r in conn.execute(
                text(
                    "SELECT ticker, trade_date, trading_value, foreign_net, inst_net, retail_net "
                    "FROM ohlcv WHERE trade_date BETWEEN :start AND :end"
                ),
                {"start": START, "end": END},
            )
        }
    report = {
        "start": str(START),
        "end": str(END),
        "scope_count": len(tickers),
        "source": "pykrx.get_market_ohlcv_by_date adjusted=True (Naver)",
        "baseline_rows": sum(t in tickers for t, _ in existing),
        "gaps": [
            "KRX flow, short balance and fundamentals history returned empty for 005930; "
            "not estimated"
        ],
        "results": {},
    }
    try:
        if "--fundamentals-only" in sys.argv:
            fundamentals_snapshot(engine, tickers, entities)
            return
        for index, ticker in enumerate(tickers, 1):
            try:
                frame = stock.get_market_ohlcv_by_date("20260901", "20260923", ticker)
                outcomes: Counter[str] = Counter()
                dates = []
                for timestamp, row in frame.iterrows():
                    day = timestamp.date()
                    if not START <= day <= END:
                        continue
                    values = {target: int(row[source]) for source, target in FIELDS.items()}
                    if any(value < 0 for value in values.values()):
                        raise ValueError("Negative OHLCV value")
                    outcome = upsert_ohlcv(
                        engine,
                        ticker=ticker,
                        trade_date=day,
                        corp_code=entities[ticker],
                        ohlcv_row=values,
                        flow_row=existing.get((ticker, day)),
                    )
                    outcomes[outcome] += 1
                    dates.append(str(day))
                report["results"][ticker] = {"outcomes": dict(outcomes), "dates": dates}
            except Exception as exc:
                report["results"][ticker] = {"error": type(exc).__name__}
            REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            if index % 20 == 0 or index == len(tickers):
                print(
                    json.dumps({"completed": index, "scope": len(tickers)}, ensure_ascii=False),
                    flush=True,
                )
        counts: Counter[str] = Counter()
        for result in report["results"].values():
            counts.update(result.get("outcomes", {}))
        report["collector_run_id"] = record_collector_run(
            engine,
            "krx",
            {
                "total": sum(counts.values()),
                "inserted": counts["inserted"],
                "updated": counts["updated"],
                "skipped": counts["skipped"],
                "failed": [
                    {"doc": ticker, "error": result["error"]}
                    for ticker, result in report["results"].items()
                    if "error" in result
                ],
            },
            int((time.monotonic() - started) * 1000),
            extra={
                "period": [str(START), str(END)],
                "scope_count": len(tickers),
                "source": report["source"],
                "gaps": report["gaps"],
            },
        )
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        requests.sessions.Session.request = original_request
        engine.dispose()


if __name__ == "__main__":
    main()
