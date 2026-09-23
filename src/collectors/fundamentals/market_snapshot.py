"""Current published market fundamentals with per-field reporting periods."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import requests  # type: ignore[import-untyped]

FIELDS = {
    "per": "per",
    "pbr": "pbr",
    "eps": "eps",
    "bps": "bps",
    "dividendYieldRatio": "dividend_yield",
    "dividend": "dps",
}


@dataclass(frozen=True)
class MarketSnapshot:
    values: dict[str, Decimal | None]
    market_asof: date
    metric_periods: dict[str, str | None]
    source: str
    fetched_at: datetime


def fetch_market_snapshot(ticker: str) -> MarketSnapshot:
    """Read current quotes; caller must never backdate this observation."""
    if not re.fullmatch(r"[0-9A-Z]{6}", ticker):
        raise ValueError("invalid_market_ticker")
    base = f"https://m.stock.naver.com/api/stock/{ticker}"
    try:
        basic_response = requests.get(base + "/basic", timeout=(5, 20))
        basic_response.raise_for_status()
        basic = basic_response.json()
        response = requests.get(base + "/integration", timeout=(5, 20))
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        raise RuntimeError("market_snapshot_request_failed") from None
    if (
        not isinstance(basic, dict)
        or not isinstance(payload, dict)
        or basic.get("itemCode") != ticker
        or payload.get("itemCode") != ticker
    ):
        raise ValueError("market_snapshot_ticker_mismatch")
    observed = datetime.now(UTC)
    try:
        traded_at = datetime.fromisoformat(basic["localTradedAt"])
        if traded_at.tzinfo is None or traded_at > observed:
            raise ValueError("invalid_market_timestamp")
        market_asof = traded_at.astimezone(ZoneInfo("Asia/Seoul")).date()
    except (KeyError, TypeError, ValueError):
        raise ValueError("market_snapshot_invalid_date") from None
    rows = payload.get("totalInfos")
    if not isinstance(rows, list):
        raise ValueError("market_snapshot_invalid_response")
    values: dict[str, Decimal | None] = dict.fromkeys(FIELDS.values())
    periods: dict[str, str | None] = dict.fromkeys(FIELDS.values())
    seen: set[str] = set()
    for item in rows:
        if not isinstance(item, dict) or item.get("code") not in FIELDS:
            continue
        field = FIELDS[item["code"]]
        if field in seen:
            raise ValueError("market_snapshot_duplicate_metric")
        seen.add(field)
        cleaned = re.sub(r"[원배%,\s]", "", str(item.get("value", "")))
        values[field] = Decimal(cleaned) if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", cleaned) else None
        period = item.get("valueDesc")
        periods[field] = str(period) if period else None
    if not any(value is not None for value in values.values()):
        raise ValueError("market_snapshot_no_values")
    return MarketSnapshot(values, market_asof, periods, base + "/integration", observed)
