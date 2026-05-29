"""KIND collector — Phase 1 v2.0 DB-direct (Plan 01-05 cutover).

Orchestrates two fundamental-axis sources (see sources.py docstring):

1. DART ``pblntf_ty="I"`` (primary) — suspension / watchlist_designation /
   unfaithful_disclosure events classified from ``report_nm``. Each event
   produces a **paired write**: a row in ``filings`` (the underlying
   disclosure) AND a row in ``events`` (the KIND classifier row pointing
   at the filing via ``filing_rcept_no``).
2. KIND undisclosure AJAX (auxiliary, reference only; EUC-KR scraper).
   Each event produces ONLY a single ``events`` row with ``source='kind'``
   — KIND-only events have no DART rcept_no, so no filings row is written.

Per-source failure is isolated via try/except. Selector drift on the KIND
scrape (R-17) is surfaced via ``kind_parse_error=True`` on the structured
log; the run still completes (resilient).

R-12: ``engine`` is REQUIRED. FK resolution + DB writes are the collector's
contract — no DB = no work.

Phase 1 transition notes:
- ``writer.py`` is NOT imported. Anyone re-importing it gets a hard
  ``ModuleNotFoundError`` after plan 01-09 deletes the module from disk.
- ``shared.heartbeat`` is NOT imported. Runtime stats land on a structured
  stderr log; plan 01-08 wires that into a ``collector_runs`` table row.
- ``suspension_cross_check_mismatch`` is deferred to Phase 9 ops dashboard
  (RESEARCH Q5 — Phase 9 can query both ``collector_runs.extra`` JSONB
  columns instead of reading a Markdown heartbeat file). The structured
  log emits an empty list as a pass-through placeholder.
- Phase 1 KIND ``filings.body_md`` is ``''`` for every event. Full body
  fetching is a Phase 3 backfill task (RESEARCH Q1).

NO imports of ``anthropic`` or ``openai`` — guarded by
tests/test_import_guard.py (COLL-07).
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from collectors.kind import dart_events, db_writer, scraper
from collectors.kind.selectors import ParseError
from collectors.kind.sources import KindEventType
from db.entity import resolve_entity, resolve_entity_by_alias
from shared.portfolio import Portfolio
from shared.run_log import record_collector_run

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_log = logging.getLogger(__name__)

__all__ = ["collect_kind"]

_ALLOWED_EVENT_TYPES = frozenset(e.value for e in KindEventType)
_KST = ZoneInfo("Asia/Seoul")
_KRX_CLOSE = dtime(15, 30)


def _default_window(since: str | None) -> tuple[str, str]:
    """Return (bgn_de, end_de) as YYYYMMDD. Default window is last 30 days."""
    end = datetime.now().date()
    bgn_dt = datetime.strptime(since, "%Y-%m-%d").date() if since else end - timedelta(days=30)
    return bgn_dt.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _filed_at_from_event_date(ev_date: date) -> datetime:
    """KIND events use the DART rcept_dt as their filed timestamp.

    The dart_events fetcher does not expose a wall-clock time, so we pin
    each filing to KST 15:30 (KRX market close) — the conventional cutoff
    for exchange-status events. Phase 3 backfill may refine this once the
    full filing body is fetched.
    """
    return datetime.combine(ev_date, _KRX_CLOSE, tzinfo=_KST)


def collect_kind(
    *,
    engine: Engine | None = None,
    since: str | None = None,
    enable_kind_scrape: bool = False,
) -> dict[str, Any]:
    """Collect DART pblntf_ty="I" + (optional) KIND undisclosure AJAX events.

    ``enable_kind_scrape`` defaults to False because the KIND AJAX path
    issues live HTTP — tests opt in via a monkey-patched fetcher.

    Returns stats: ``{total, inserted, updated, skipped, failed[], elapsed_ms}``.
    Phase 1 schema delta — ``succeeded`` is replaced by inserted+updated
    (UPSERT semantics make a single counter misleading).

    Raises:
        RuntimeError: if ``engine`` is None — collector contract requires DB.
    """
    if engine is None:
        raise RuntimeError("collect_kind requires a DB engine for FK resolution")

    start = time.monotonic()
    bgn_de, end_de = _default_window(since)

    # Phase 6 P-01: portfolio lives at <repo_root>/notes/private/portfolio.md
    repo_root = Path(".")
    portfolio = Portfolio.load(repo_root)
    scope = set(portfolio.scope_tickers())

    stats: dict[str, Any] = {
        "total": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "failed": [],
    }
    dart_events_stats: dict[str, Any] = {"docs_processed": 0, "status": "ok"}
    kind_scrape_stats: dict[str, Any] = {"docs_processed": 0, "status": "skipped"}
    parse_error = False
    events: list[dict[str, Any]] = []
    dart_suspended_tickers: set[str] = set()

    # 1) DART pblntf_ty="I" (primary)
    dart_start = time.monotonic()
    try:
        dart_evts = dart_events.fetch_exchange_events(bgn_de=bgn_de, end_de=end_de)
        events.extend(dart_evts)
        dart_events_stats["docs_processed"] = len(dart_evts)
        for e in dart_evts:
            if e["event_type"] == "suspension" and e.get("ticker"):
                dart_suspended_tickers.add(e["ticker"])
    except Exception as exc:  # noqa: BLE001 — per-source isolation
        _log.exception("dart pblntf_ty=I fetch failed")
        dart_events_stats["status"] = "error"
        dart_events_stats["error"] = str(exc)
        stats["failed"].append({"doc": "dart_events", "error": str(exc)})
    dart_events_stats["elapsed_ms"] = int((time.monotonic() - dart_start) * 1000)

    # 2) KIND undisclosure AJAX (optional)
    if enable_kind_scrape:
        kind_start = time.monotonic()
        kind_scrape_stats["status"] = "ok"
        try:
            kind_evts = scraper.fetch_undisclosure_events()
            # Resolve company_name → ticker via entity_aliases (KIND AJAX has
            # no ticker column).
            for e in kind_evts:
                if e.get("ticker"):
                    continue
                ent = resolve_entity_by_alias(engine, e.get("company_name") or "")
                if ent is not None:
                    e["ticker"] = ent.current_ticker
                    e["corp_code"] = ent.corp_code
            events.extend(kind_evts)
            kind_scrape_stats["docs_processed"] = len(kind_evts)
        except ParseError as exc:
            # R-17: selector drift is logged + flagged, run continues
            _log.warning("kind undisclosure parse error: %s", exc)
            parse_error = True
            kind_scrape_stats["status"] = "parse_error"
            kind_scrape_stats["error"] = str(exc)
            stats["failed"].append({"doc": "kind_undiscl", "error": f"ParseError: {exc}"})
        except Exception as exc:  # noqa: BLE001 — per-source isolation
            _log.exception("kind undisclosure fetch failed")
            kind_scrape_stats["status"] = "error"
            kind_scrape_stats["error"] = str(exc)
            stats["failed"].append({"doc": "kind_undiscl", "error": str(exc)})
        kind_scrape_stats["elapsed_ms"] = int((time.monotonic() - kind_start) * 1000)

    # 3) Scope filter + dedup + paired write
    seen_keys: set[tuple[str, str, str]] = set()
    for e in events:
        stats["total"] += 1
        ticker = e.get("ticker") or ""
        event_date = (e.get("event_date") or "").replace("-", "").strip()
        event_type = e["event_type"]

        # Collector-side filter: event_type must be in the 5-value enum
        # (the DB CHECK is belt-and-suspenders; this gives a cheaper, more
        # informative failure than a rolled-back transaction).
        if event_type not in _ALLOWED_EVENT_TYPES:
            stats["failed"].append({
                "doc": f"{event_type}_{ticker}_{event_date}",
                "error": f"unknown event_type: {event_type!r}",
            })
            continue

        if not ticker or len(ticker) != 6 or not ticker.isdigit():
            stats["skipped"] += 1
            continue
        if ticker not in scope:
            stats["skipped"] += 1
            continue
        if not event_date or len(event_date) != 8 or not event_date.isdigit():
            stats["skipped"] += 1
            continue

        key = (event_type, ticker, event_date)
        if key in seen_keys:
            stats["skipped"] += 1
            continue
        seen_keys.add(key)

        try:
            ent = resolve_entity(engine, ticker)
            corp_code = (ent.corp_code if ent else None) or e.get("corp_code")
            if not corp_code:
                stats["failed"].append({
                    "doc": f"{event_type}_{ticker}_{event_date}",
                    "error": "missing_corp_code",
                })
                continue

            ev_date = date.fromisoformat(
                f"{event_date[:4]}-{event_date[4:6]}-{event_date[6:8]}"
            )
            # Classify the event source from the shape of source_id.
            # DART rcept_no is 14 ASCII digits; KIND synthesized ids are not.
            source_id_raw = str(e.get("source_id") or "")
            source_kind = "dart" if source_id_raw.isdigit() and len(source_id_raw) == 14 else "kind"

            # 3a) Paired write: DART branch writes filings first
            filing_outcome: str | None = None
            filing_rcept_no: str | None = None
            if source_kind == "dart":
                filing_rcept_no = source_id_raw
                filed_at = _filed_at_from_event_date(ev_date)
                filing_outcome = db_writer.upsert_kind_filing(
                    engine,
                    rcept_no=filing_rcept_no,
                    corp_code=corp_code,
                    ticker=ticker,
                    filed_at=filed_at,
                    report_nm=e.get("report_nm") or e.get("reason", "") or "",
                    event_type=event_type,
                    source_url=e.get("source_url", ""),
                    body_md="",  # Phase 1 KIND policy; backfilled Phase 3
                )

            # 3b) events row (always)
            event_outcome = db_writer.upsert_kind_event(
                engine,
                event_type=event_type,
                ticker=ticker,
                event_date=ev_date,
                corp_code=corp_code,
                subtype=e.get("subtype"),
                reason=e.get("reason", "") or "",
                source=source_kind,
                source_id=source_id_raw,
                source_url=e.get("source_url", ""),
                filing_rcept_no=filing_rcept_no,
            )

            # 3c) classify outcome — any insert/update on either table counts
            if filing_outcome == "inserted" or event_outcome == "inserted":
                stats["inserted"] += 1
            elif filing_outcome == "updated":
                stats["updated"] += 1
            else:
                stats["skipped"] += 1
        except Exception as exc:  # noqa: BLE001 — per-event isolation (COLL-08)
            _log.exception("kind write failed for %s %s %s", event_type, ticker, event_date)
            stats["failed"].append(
                {"doc": f"{event_type}_{ticker}_{event_date}", "error": str(exc)}
            )

    stats["elapsed_ms"] = int((time.monotonic() - start) * 1000)

    # 4) Structured run-complete log
    # `suspension_cross_check_mismatch` is deferred to Phase 9 ops dashboard
    # (RESEARCH Q5). Emitting the key as an empty list keeps the contract
    # stable for downstream observers.
    cross_check_mismatch: list[str] = []

    _log.info(
        "collector_run_complete",
        extra={
            "source": "kind",
            "stats": stats,
            "elapsed_ms": stats["elapsed_ms"],
            "dart_events": dart_events_stats,
            "kind_scrape": kind_scrape_stats,
            "kind_parse_error": parse_error,
            "suspension_cross_check_mismatch": cross_check_mismatch,
            "dart_suspended_tickers": sorted(dart_suspended_tickers),
        },
    )
    # Plan 01-08: dual-sink DB row (RESEARCH.md Q5). KIND has the richest
    # per-source extras; collapse them into a single dict for the
    # ``collector_runs.extra`` JSONB column. ``suspension_cross_check_mismatch``
    # is a Phase 9 placeholder (always [] in Phase 1) and ``dart_suspended_tickers``
    # is observability-only.
    kind_extra: dict[str, Any] = {
        "dart_events": dart_events_stats,
        "kind_scrape": kind_scrape_stats,
        "kind_parse_error": parse_error,
        "suspension_cross_check_mismatch": cross_check_mismatch,
        "dart_suspended_tickers": sorted(dart_suspended_tickers),
    }
    record_collector_run(
        engine, "kind", stats, stats["elapsed_ms"], extra=kind_extra
    )
    return stats
