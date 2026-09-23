"""Explicit replay of Jev shadow reviews over existing canonical records."""

from __future__ import annotations

import json
from argparse import Namespace
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

from cards.models import DecisionCard
from collectors.news.matcher import load_scoped_aliases, match_tickers_in_text
from db.engine import get_engine
from orchestration.card_review import review_card
from orchestration.news_review import review_news
from shared.portfolio import Portfolio

_NEWS = text(
    "SELECT url,title,body_md FROM news WHERE published_at>=:start AND published_at<:end "
    "AND tickers && CAST(:scope AS text[]) ORDER BY published_at,id LIMIT :limit"
)
_CARD = text(
    "SELECT payload,body_md FROM decision_cards WHERE card_id=:card_id AND report_type IS NULL"
)


def print_summary(reports: list[dict[str, Any]]) -> int:
    counts = Counter(r["status"] for r in reports)
    summary = {
        "reviewed": len(reports),
        "statuses": dict(counts),
        "cached": sum(bool(r.get("cached")) for r in reports),
        "requires_review": sum(bool(r.get("requires_review")) for r in reports),
        "reviews": [
            {
                k: r.get(k)
                for k in ("review_id", "status", "error_code", "cached", "answers", "request_id")
            }
            for r in reports
        ],
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if counts["error"] else 0


def cmd_review_news(args: Namespace) -> int:
    if args.since > args.until or args.until == date.max or not 1 <= args.limit <= 500:
        print("Invalid date range or limit (1..500)")
        return 2
    scope = Portfolio.load(Path(".")).scope_tickers()
    engine = get_engine()
    aliases = load_scoped_aliases(engine, scope)
    kst = ZoneInfo("Asia/Seoul")
    params = {
        "start": datetime.combine(args.since, time.min, tzinfo=kst),
        "end": datetime.combine(args.until + timedelta(days=1), time.min, tzinfo=kst),
        "scope": scope,
        "limit": args.limit,
    }
    with engine.connect() as connection:
        rows = connection.execute(_NEWS, params).mappings().all()
    reports = []
    for row in rows:
        reports.append(
            review_news(
                engine,
                url=row["url"],
                title=row["title"],
                body=row["body_md"],
                matches=match_tickers_in_text(f"{row['title']}\n{row['body_md']}", aliases),
            )
        )
    return print_summary(reports)


def cmd_review_card(args: Namespace) -> int:
    engine = get_engine()
    with engine.connect() as connection:
        row = connection.execute(_CARD, {"card_id": args.card_id}).mappings().first()
    if row is None:
        print("Decision card not found")
        return 2
    card = DecisionCard.model_validate({**row["payload"], "body_md": row["body_md"]})
    result = review_card(engine, card)
    if result["status"] == "disabled":
        print(json.dumps(result))
        return 0
    return print_summary(result["items"])
