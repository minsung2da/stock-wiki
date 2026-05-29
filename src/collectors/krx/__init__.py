"""KRX collector — COLL-02 (Phase 1 v2.0, post-01-04).

This collector INSERTs directly into the ``ohlcv`` Postgres table via
``db_writer.upsert_ohlcv``. The Markdown writer path is gone. Plan 01-09
deletes ``writer.py`` from disk after every collector has cut over.

R-03 (missing-entity Option A): if ``resolve_entity(ticker)`` returns None,
the ticker lands in ``stats["failed"]`` with ``error="missing_entity"``
and the row is NOT written. Missing-entity tickers are also surfaced in
the structured run-complete log so Phase 9 observability can flag them.

R-12: ``engine`` is REQUIRED (no longer Optional). FK resolution is the
collector's contract — no DB = no work.

Holiday handling: empty pykrx OHLCV → no row written, ticker counted as
``skipped``, and ``extra.holiday_tickers`` recorded on the structured
run-complete log.

T+2 short fill-in: db_writer.upsert_ohlcv uses ``COALESCE(EXCLUDED.x,
ohlcv.x)`` on short_volume/short_balance/corp_code — a None on a later
fetch never NULL-clobbers prior data. See RESEARCH.md §Pitfall 4.

Phase 1 transition (v2.0): writer.py module remains on disk until plan
01-09 deletes it. We do NOT import it here — any reintroduction of
``from collectors.krx import writer`` would resurrect the Markdown path.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from collectors.krx import db_writer, fetcher
from db.entity import resolve_entity
from shared.portfolio import Portfolio
from shared.run_log import record_collector_run

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_log = logging.getLogger(__name__)

__all__ = ["collect_krx"]


def _today_iso_krx() -> str:
    """Return today's date as ISO ``YYYY-MM-DD`` string in KST."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()


# pykrx returns Korean column names; the writer used `.to_markdown(index=True)`
# on the raw frame. db_writer wants typed Python values, so we map at this
# boundary. Keep the table here (not in db_writer) so db_writer stays pure
# numeric / KRX-agnostic.
_OHLCV_COLS_KO = ("시가", "고가", "저가", "종가", "거래량")
_FLOW_COLS_KO = ("외국인", "기관합계", "개인")  # client.get_trading_value projects to these 3
_SHORT_COLS_KO = ("공매도잔고(주)", "공매도금액")


def _coerce_ohlcv_row(df) -> dict[str, Any]:
    """Map a pykrx OHLCV one-row DataFrame to the db_writer dict shape."""
    row = df.iloc[0]
    return {
        "open": row["시가"],
        "high": row["고가"],
        "low": row["저가"],
        "close": row["종가"],
        "volume": int(row["거래량"]),
    }


def _coerce_flow_row(df) -> dict[str, Any] | None:
    """Map pykrx investor-flow DataFrame to the db_writer flow shape.

    Returns None when the DataFrame is empty (some holidays/illiquid names
    return empty flow). retail_net = 개인. trading_value derived from
    abs(flow) is NOT included here — pykrx flow API doesn't surface it
    (the column comes from ohlcv 거래대금 instead — handled in caller).
    """
    if df is None or len(df) == 0:
        return None
    row = df.iloc[0]
    return {
        "trading_value": None,  # filled by caller from ohlcv 거래대금 if present
        "foreign_net": int(row["외국인"]) if "외국인" in row else None,
        "inst_net": int(row["기관합계"]) if "기관합계" in row else None,
        "retail_net": int(row["개인"]) if "개인" in row else None,
    }


def _coerce_short_row(df) -> dict[str, Any] | None:
    """Map pykrx short-balance DataFrame to db_writer short shape.

    KRX T+2 lag: many recent dates return empty. The COALESCE pattern in
    db_writer.upsert_ohlcv preserves prior values on a None return.
    """
    if df is None or len(df) == 0:
        return None
    row = df.iloc[0]
    out: dict[str, Any] = {}
    if "공매도잔고(주)" in row:
        out["short_volume"] = int(row["공매도잔고(주)"])
    if "공매도금액" in row:
        out["short_balance"] = int(row["공매도금액"])
    if not out:
        return None
    out.setdefault("short_volume", None)
    out.setdefault("short_balance", None)
    return out


def collect_krx(
    *,
    engine: Engine | None = None,
    since: str | None = None,
) -> dict[str, Any]:
    """Run the KRX collector for the current scope (holdings ∪ watchlist).

    Per-ticker isolation (COLL-08): any exception during a single ticker is
    captured into ``stats["failed"]`` and does NOT abort the loop.

    Returns stats: ``{total, inserted, updated, skipped, failed[], elapsed_ms}``
    (Phase 1 schema delta — ``succeeded`` is replaced with
    inserted+updated; ``skipped`` covers idempotent no-ops AND holiday days).

    Raises:
        RuntimeError: if ``engine`` is None — FK resolution requires it.
    """
    if engine is None:
        raise RuntimeError("collect_krx requires a DB engine for FK resolution")

    start = time.monotonic()
    date_iso = since or _today_iso_krx()
    date_str = date_iso.replace("-", "")
    trade_date_obj = date.fromisoformat(date_iso)
    # Phase 6 P-01: portfolio lives at <repo_root>/notes/private/portfolio.md
    repo_root = Path(".")
    portfolio = Portfolio.load(repo_root)
    scope = portfolio.scope_tickers()

    stats: dict[str, Any] = {
        "total": len(scope),
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "failed": [],
    }
    holiday_tickers: list[str] = []
    missing_entities: list[str] = []

    for ticker in scope:
        try:
            ohlcv_df = fetcher.fetch_ohlcv(ticker, date_str)
            if ohlcv_df.empty:
                holiday_tickers.append(ticker)
                stats["skipped"] += 1
                continue

            # R-03: resolve entity BEFORE writing. Missing entity → no write.
            ent = resolve_entity(engine, ticker)
            if ent is None:
                missing_entities.append(ticker)
                stats["failed"].append({"doc": ticker, "error": "missing_entity"})
                continue

            flow_df = fetcher.fetch_trading_value(ticker, date_str)
            short_df = fetcher.fetch_shorting_balance(ticker, date_str)

            ohlcv_row = _coerce_ohlcv_row(ohlcv_df)
            flow_row = _coerce_flow_row(flow_df)
            # pykrx's ohlcv frame may carry a 거래대금 column; surface it on flow_row
            if "거래대금" in ohlcv_df.iloc[0].index:
                if flow_row is None:
                    flow_row = {
                        "trading_value": int(ohlcv_df.iloc[0]["거래대금"]),
                        "foreign_net": None,
                        "inst_net": None,
                        "retail_net": None,
                    }
                else:
                    flow_row["trading_value"] = int(ohlcv_df.iloc[0]["거래대금"])
            short_row = _coerce_short_row(short_df)

            outcome = db_writer.upsert_ohlcv(
                engine,
                ticker=ticker,
                trade_date=trade_date_obj,
                corp_code=ent.corp_code,
                ohlcv_row=ohlcv_row,
                flow_row=flow_row,
                short_row=short_row,
            )
            if outcome == "inserted":
                stats["inserted"] += 1
            elif outcome == "updated":
                stats["updated"] += 1
            else:
                stats["skipped"] += 1
        except Exception as exc:  # noqa: BLE001 — per-ticker isolation (COLL-08)
            _log.exception("krx collect failed for %s", ticker)
            stats["failed"].append({"doc": ticker, "error": str(exc)})

    stats["elapsed_ms"] = int((time.monotonic() - start) * 1000)

    extra: dict[str, Any] = {}
    if holiday_tickers:
        extra["skipped_holiday"] = True
        extra["holiday_tickers"] = holiday_tickers
    if missing_entities:
        extra["missing_entity"] = missing_entities

    # Structured run-complete log (01-08 wires this into collector_runs table).
    _log.info(
        "collector_run_complete",
        extra={
            "source": "krx",
            "stats": stats,
            "elapsed_ms": stats["elapsed_ms"],
            "extra": extra or None,
        },
    )
    # Plan 01-08: dual-sink DB row (RESEARCH.md Q5). Best-effort: a DB
    # outage on this call logs a WARNING but does NOT fail the collect.
    record_collector_run(
        engine, "krx", stats, stats["elapsed_ms"], extra=extra or None
    )
    return stats
