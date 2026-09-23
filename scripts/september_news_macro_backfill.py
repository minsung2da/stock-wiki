"""Bounded September 2026 RSS and configured macro ingestion; no archive crawl."""

from __future__ import annotations

import json
import logging
import math
import os
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from sqlalchemy import text

from collectors.macro import load_catalog
from collectors.macro.db_writer import upsert_macro_observations
from collectors.news import client, db_writer, fetcher, matcher
from collectors.news.feeds import FEEDS_BY_OUTLET
from db.engine import get_engine
from shared.portfolio import Portfolio
from shared.run_log import record_collector_run

START, END = date(2026, 9, 1), date(2026, 9, 23)
KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "notes/private/september-news-macro-report.json"


def stats() -> dict:
    return dict(total=0, inserted=0, updated=0, skipped=0, failed=[])


def checkpoint(report: dict) -> None:
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def coverage(engine) -> dict:
    with engine.connect() as conn:
        news = dict(
            conn.execute(
                text(
                    "SELECT count(*) AS rows, min(published_at) AS earliest, "
                    "max(published_at) AS latest FROM news WHERE "
                    "(published_at AT TIME ZONE 'Asia/Seoul')::date BETWEEN :start AND :end"
                ),
                {"start": START, "end": END},
            )
            .mappings()
            .one()
        )
        macro = [
            dict(row)
            for row in conn.execute(
                text(
                    "SELECT source, series_id, item_code, count(*) AS rows, "
                    "min(obs_date) AS earliest, max(obs_date) AS latest FROM macro_series "
                    "WHERE obs_date BETWEEN :start AND :end GROUP BY source, series_id, "
                    "item_code ORDER BY source, series_id"
                ),
                {"start": START, "end": END},
            ).mappings()
        ]
        return {"news": news, "macro": macro}


def run_macro(engine, report: dict) -> None:
    began = time.monotonic()
    result = stats()
    result["series"] = []
    report["macro"] = result
    catalog = load_catalog()
    for source, entries in catalog.items():
        for entry in entries:
            result["total"] += 1
            detail = {"source": source, "series_id": entry["series_id"], "label": entry["label"]}
            try:
                time.sleep(1)
                if source == "ecos":
                    key = os.environ["ECOS_API_KEY"]
                    endpoint = (
                        f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/1000/"
                        f"{entry['series_id']}/{entry.get('cycle', 'D')}/"
                        f"{START:%Y%m%d}/{END:%Y%m%d}/{entry.get('item_code', '')}"
                    )
                    response = requests.get(endpoint, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    raw = data.get("StatisticSearch", {}).get("row", [])
                    detail["api_result_code"] = data.get("RESULT", {}).get("CODE")
                    observations = []
                    for row in raw:
                        if row.get("ITEM_CODE1") != entry.get("item_code"):
                            continue
                        stamp = row["TIME"]
                        day = date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))
                        value = float(row["DATA_VALUE"])
                        if START <= day <= END and math.isfinite(value):
                            observations.append(
                                {
                                    "date": day,
                                    "value": value,
                                    "unit": row.get("UNIT_NAME") or entry.get("unit"),
                                }
                            )
                else:
                    response = requests.get(
                        "https://api.stlouisfed.org/fred/series/observations",
                        params={
                            "api_key": os.environ["FRED_API_KEY"],
                            "file_type": "json",
                            "series_id": entry["series_id"],
                            "observation_start": START.isoformat(),
                            "observation_end": END.isoformat(),
                        },
                        timeout=30,
                    )
                    response.raise_for_status()
                    raw = response.json().get("observations", [])
                    observations = []
                    for row in raw:
                        if row["value"] == ".":
                            continue
                        day = date.fromisoformat(row["date"])
                        value = float(row["value"])
                        if START <= day <= END and math.isfinite(value):
                            observations.append(
                                {
                                    "date": day,
                                    "value": value,
                                    "unit": {"DGS10": "%", "DCOILWTICO": "USD/barrel"}[
                                        entry["series_id"]
                                    ],
                                }
                            )
                detail["returned"] = len(raw)
                detail["eligible"] = len(observations)
                if not observations:
                    raise ValueError("No September observations returned")
                inserted, updated, revisions = upsert_macro_observations(
                    engine,
                    source=source,
                    series_id=entry["series_id"],
                    item_code=entry.get("item_code", ""),
                    label=entry["label"],
                    cycle=entry.get("cycle", "D"),
                    observations=observations,
                )
                result["inserted"] += inserted
                result["updated"] += updated
                result["skipped"] += len(observations) - inserted - updated
                detail.update(
                    inserted=inserted,
                    updated=updated,
                    revisions=revisions,
                    earliest=min(o["date"] for o in observations),
                    latest=max(o["date"] for o in observations),
                )
                with engine.connect() as conn:
                    stored = {
                        row.obs_date: float(row.value)
                        for row in conn.execute(
                            text(
                                "SELECT obs_date, value FROM macro_series WHERE source=:source "
                                "AND series_id=:sid AND item_code=:item "
                                "AND obs_date BETWEEN :start AND :end"
                            ),
                            {
                                "source": source,
                                "sid": entry["series_id"],
                                "item": entry.get("item_code", ""),
                                "start": START,
                                "end": END,
                            },
                        )
                    }
                assert all(
                    math.isclose(stored[o["date"]], o["value"], rel_tol=1e-8) for o in observations
                )
                detail["verified"] = True
            except Exception as exc:
                detail["error_type"] = type(exc).__name__
                result["failed"].append({"doc": entry["label"], "error": type(exc).__name__})
            result["series"].append(detail)
            checkpoint(report)
            print(json.dumps(detail, ensure_ascii=False, default=str), flush=True)
    result["elapsed_ms"] = int((time.monotonic() - began) * 1000)
    result["run_id"] = record_collector_run(
        engine,
        "macro",
        result,
        result["elapsed_ms"],
        extra={"range_start": str(START), "range_end": str(END), "date_filter_before_upsert": True},
    )


def run_news(engine, report: dict) -> None:
    began = time.monotonic()
    matcher.assert_aliases_seeded(engine)
    scope = Portfolio.load(ROOT).scope_tickers()
    aliases = matcher.load_scoped_aliases(engine, scope)
    result = stats()
    result.update(feeds=[], eligible=0, duplicates=0, unmatched=0, empty_body=0, articles=[])
    report["news"] = result
    seen = set()
    for outlet, urls in FEEDS_BY_OUTLET.items():
        for url in urls:
            detail = {"url": url, "outlet": outlet}
            try:
                rss = client.fetch_rss_feed(url)
                if not rss:
                    raise ValueError("Empty RSS")
                items = fetcher.parse_rss(rss)
                detail["returned"] = len(items)
                dates = sorted(
                    item.published.astimezone(KST).date()
                    for item in items
                    if item.published and item.published.tzinfo
                )
                detail["earliest"] = min(dates) if dates else None
                detail["latest"] = max(dates) if dates else None
                for item in items:
                    result["total"] += 1
                    if (
                        not item.published
                        or not item.published.tzinfo
                        or not START <= item.published.astimezone(KST).date() <= END
                    ):
                        result["skipped"] += 1
                        continue
                    if item.url in seen:
                        result["duplicates"] += 1
                        result["skipped"] += 1
                        continue
                    seen.add(item.url)
                    result["eligible"] += 1
                    try:
                        html = client.fetch_article_html(item.url)
                        body = fetcher.extract_first_two_paragraphs(html) if html else None
                        if not body:
                            result["empty_body"] += 1
                            result["failed"].append({"doc": item.url, "error": "EmptyArticleBody"})
                            continue
                        matches = matcher.match_tickers_in_text(f"{item.title}\n{body}", aliases)
                        if not matches:
                            result["unmatched"] += 1
                            result["skipped"] += 1
                            continue
                        tickers = [match["ticker"] for match in matches]
                        outcome = db_writer.upsert_news_article(
                            engine,
                            url=item.url,
                            outlet=outlet,
                            published_at=item.published,
                            title=item.title,
                            body_md=body,
                            tickers=tickers,
                            corp_code=matches[0]["corp_code"],
                        )
                        result[outcome if outcome in {"inserted", "updated"} else "skipped"] += 1
                        result["articles"].append(
                            {
                                "url": item.url,
                                "published_at": item.published,
                                "tickers": tickers,
                                "outcome": outcome,
                            }
                        )
                    except Exception as exc:
                        result["failed"].append({"doc": item.url, "error": type(exc).__name__})
                    checkpoint(report)
            except Exception as exc:
                detail["error_type"] = type(exc).__name__
                result["failed"].append({"doc": url, "error": type(exc).__name__})
            result["feeds"].append(detail)
            checkpoint(report)
            print(json.dumps(detail, ensure_ascii=False, default=str), flush=True)
    result["elapsed_ms"] = int((time.monotonic() - began) * 1000)
    result["run_id"] = record_collector_run(
        engine,
        "news",
        result,
        result["elapsed_ms"],
        extra={
            "range_start": str(START),
            "range_end": str(END),
            "rss_only": True,
            "historical_archive_complete": False,
        },
    )


def main() -> None:
    os.chdir(ROOT)
    load_dotenv(ROOT / ".env")
    logging.disable(logging.CRITICAL)
    engine = get_engine()
    report = {
        "range_start": START,
        "range_end": END,
        "started_at": datetime.now(KST),
        "limitations": [
            "RSS only: articles no longer present in feeds cannot be recovered.",
            "News relevance uses existing name-alias substring matcher and first two paragraphs.",
            "Macro observations are latest available revisions, not historical vintages.",
        ],
        "baseline": coverage(engine),
    }
    checkpoint(report)
    run_macro(engine, report)
    run_news(engine, report)
    report["after"] = coverage(engine)
    report["completed_at"] = datetime.now(KST)
    checkpoint(report)
    print(json.dumps(report["after"], ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
