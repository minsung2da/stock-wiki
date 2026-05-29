"""KRX collector — COLL-02. No anthropic/openai imports (CI guarded).

PHASE 1 TRANSITION (v2.0): this collector still writes via writer.py but no
longer receives ``vault_root`` via CLI. ``_LEGACY_VAULT_ROOT`` will be
removed when ``db_writer.*`` replaces ``writer.*`` in plan 01-04.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from collectors.krx import fetcher, writer
from db.entity import resolve_entity
from shared.heartbeat import record_source_run
from shared.portfolio import Portfolio

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_log = logging.getLogger(__name__)

# Phase 1 transition placeholder; removed in 01-04 (KRX DB-direct cutover).
_LEGACY_VAULT_ROOT = Path("vault")

__all__ = ["collect_krx"]


def _today_iso_krx() -> str:
    """Return today's date as ISO `YYYY-MM-DD` string in KST."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()


def _read_existing_hash(path: Path) -> str | None:
    """Extract content_hash from an existing KRX vault file's frontmatter."""
    import re as _re

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = _re.search(r"content_hash:\s*([0-9a-f]+)", text)
    return m.group(1) if m else None


def collect_krx(
    *,
    engine: Engine | None = None,
    since: str | None = None,
) -> dict[str, Any]:
    """Run the KRX collector for the current scope (holdings ∪ watchlist).

    Per-ticker isolation (COLL-08): any exception during a single ticker is
    captured into stats["failed"] and does NOT abort the loop. Heartbeat is
    updated once at the end regardless of partial failures.

    R-03 (missing-entity Option A): if `engine` resolves a ticker to None, we
    do NOT write a file. The ticker lands in stats["failed"] with
    error='missing_entity' and `extra.missing_entity` on heartbeat.

    Holidays: empty pykrx OHLCV → no file written, ticker counted as skipped,
    and `extra.skipped_holiday=True` recorded on heartbeat.
    """
    start = time.monotonic()
    date_iso = since or _today_iso_krx()
    date_str = date_iso.replace("-", "")
    # repo_root = _LEGACY_VAULT_ROOT.parent → Path(".") (Phase 6 P-01: portfolio at notes/private/)
    repo_root = _LEGACY_VAULT_ROOT.parent
    portfolio = Portfolio.load(repo_root)
    scope = portfolio.scope_tickers()

    stats: dict[str, Any] = {
        "total": len(scope),
        "succeeded": 0,
        "skipped": 0,
        "failed": [],
    }
    holiday_tickers: list[str] = []
    missing_entities: list[str] = []

    for ticker in scope:
        try:
            ohlcv = fetcher.fetch_ohlcv(ticker, date_str)
            if ohlcv.empty:
                holiday_tickers.append(ticker)
                stats["skipped"] += 1
                continue

            # R-03: resolve entity BEFORE writing. Missing entity → no write.
            ent = resolve_entity(engine, ticker) if engine is not None else None
            if ent is None:
                missing_entities.append(ticker)
                stats["failed"].append({"doc": ticker, "error": "missing_entity"})
                continue

            flow = fetcher.fetch_trading_value(ticker, date_str)
            short = fetcher.fetch_shorting_balance(ticker, date_str)

            path = writer.vault_path_for_krx(_LEGACY_VAULT_ROOT, date_iso, ticker)
            if path.exists():
                new_body = writer._render_body(ohlcv, flow, short)
                new_hash = writer.compute_body_hash(new_body)
                existing_hash = _read_existing_hash(path)
                if existing_hash == new_hash:
                    stats["skipped"] += 1
                    continue

            writer.write_krx_doc(
                vault_root=_LEGACY_VAULT_ROOT,
                ticker=ticker,
                date_iso=date_iso,
                corp_code=ent.corp_code,
                company_name=ent.canonical_name,
                ohlcv=ohlcv,
                flow=flow,
                short=short,
            )
            stats["succeeded"] += 1
        except Exception as exc:  # noqa: BLE001 — per-ticker isolation (COLL-08)
            _log.exception("krx collect failed for %s", ticker)
            stats["failed"].append({"doc": ticker, "error": str(exc)})

    stats["elapsed_ms"] = int((time.monotonic() - start) * 1000)

    extra_merge: dict[str, Any] = {}
    if holiday_tickers:
        extra_merge["skipped_holiday"] = True
        extra_merge["holiday_tickers"] = holiday_tickers
    if missing_entities:
        extra_merge["missing_entity"] = missing_entities
    extra = extra_merge or None

    record_source_run(
        "krx",
        stats,
        heartbeat_path=_LEGACY_VAULT_ROOT / "ingested/_status/heartbeat.md",
        extra=extra,
    )
    return stats
