"""KIND collector — exchange status events (Plan 05, Option D).

Orchestrates two fundamental-axis sources (see sources.py docstring):

1. DART `pblntf_ty="I"` (primary) — suspension / watchlist_designation /
   unfaithful_disclosure events classified from `report_nm`.
2. KIND undisclosure AJAX (auxiliary, reference only) — cross-check for
   unfaithful_disclosure via company-name lookup; requires entity_aliases.

Per-source failure is isolated via try/except so one source does not abort
the other. Heartbeat records `dart_events` / `kind_scrape` sub-dicts plus
`kind_parse_error: true` on selector drift (D-17) and
`suspension_cross_check_mismatch` when Plan 02's heartbeat exposes
`suspended_tickers` and they disagree with DART's suspension set (INFO-only).

NO imports of `anthropic` or `openai` — guarded by tests/test_import_guard.py
(COLL-07).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from collectors.kind import dart_events, scraper, writer
from collectors.kind.selectors import ParseError
from db.entity import resolve_entity, resolve_entity_by_alias
from shared.heartbeat import record_source_run
from shared.portfolio import Portfolio

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_log = logging.getLogger(__name__)

__all__ = ["collect_kind"]


def _default_window(since: str | None) -> tuple[str, str]:
    """Return (bgn_de, end_de) as YYYYMMDD. Default window is last 30 days."""
    end = datetime.now().date()
    bgn_dt = datetime.strptime(since, "%Y-%m-%d").date() if since else end - timedelta(days=30)
    return bgn_dt.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _read_heartbeat_extra(vault_root: Path, source: str, key: str) -> Any:
    """Read `sources.{source}.{key}` from the heartbeat file (best-effort)."""
    p = vault_root / "ingested/_status/heartbeat.md"
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    try:
        meta = yaml.safe_load(text[3:end]) or {}
    except Exception:  # noqa: BLE001
        return None
    return (meta.get("sources", {}) or {}).get(source, {}).get(key)


def collect_kind(
    *,
    vault_root: Path = Path("."),
    engine: Engine | None = None,
    since: str | None = None,
    enable_kind_scrape: bool = False,
) -> dict[str, Any]:
    """Collect DART pblntf_ty="I" + (optional) KIND undisclosure AJAX events.

    `enable_kind_scrape` defaults to False because the KIND AJAX path issues
    live HTTP — tests opt in via a monkey-patched fetcher. Production
    callers can set True once operator confirms EUC-KR AJAX stability.
    """
    start = time.monotonic()
    bgn_de, end_de = _default_window(since)

    # repo_root = vault_root.parent (Phase 6 P-01: portfolio moved to notes/private/)
    repo_root = vault_root.parent
    portfolio = Portfolio.load(repo_root)
    scope = set(portfolio.scope_tickers())

    stats: dict[str, Any] = {
        "total": 0,
        "succeeded": 0,
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
    except Exception as exc:  # noqa: BLE001
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
            # Resolve company_name → ticker via entity_aliases so the writer
            # path (which requires ticker) can be constructed.
            if engine is not None:
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
            _log.warning("kind undisclosure parse error: %s", exc)
            parse_error = True
            kind_scrape_stats["status"] = "parse_error"
            kind_scrape_stats["error"] = str(exc)
            stats["failed"].append({"doc": "kind_undiscl", "error": f"ParseError: {exc}"})
        except Exception as exc:  # noqa: BLE001
            _log.exception("kind undisclosure fetch failed")
            kind_scrape_stats["status"] = "error"
            kind_scrape_stats["error"] = str(exc)
            stats["failed"].append({"doc": "kind_undiscl", "error": str(exc)})
        kind_scrape_stats["elapsed_ms"] = int((time.monotonic() - kind_start) * 1000)

    # 3) Scope filter + dedup + write
    seen_keys: set[tuple[str, str, str]] = set()
    for e in events:
        stats["total"] += 1
        ticker = e.get("ticker") or ""
        event_date = (e.get("event_date") or "").replace("-", "").strip()
        event_type = e["event_type"]

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
            ent = resolve_entity(engine, ticker) if engine is not None else None
            corp_code = (ent.corp_code if ent else None) or e.get("corp_code")
            company_name = (ent.canonical_name if ent else None) or e.get("company_name")
            _path, _hash, rewrote = writer.write_kind_event(
                vault_root=vault_root,
                event_type=event_type,
                ticker=ticker,
                event_date=event_date,
                corp_code=corp_code,
                company_name=company_name,
                reason=e.get("reason", ""),
                source=("dart" if str(e.get("source_id", "")).isdigit() else "kind"),
                source_id=e.get("source_id"),
                source_url=e.get("source_url", ""),
                subtype=e.get("subtype"),
            )
            if rewrote:
                stats["succeeded"] += 1
            else:
                stats["skipped"] += 1
        except Exception as exc:  # noqa: BLE001
            _log.exception("kind write failed for %s %s %s", event_type, ticker, event_date)
            stats["failed"].append(
                {"doc": f"{event_type}_{ticker}_{event_date}", "error": str(exc)}
            )

    stats["elapsed_ms"] = int((time.monotonic() - start) * 1000)

    # 4) Cross-check DART suspension set against Plan 02's heartbeat (INFO-only)
    krx_suspended = _read_heartbeat_extra(vault_root, "krx", "suspended_tickers")
    cross_check_mismatch: list[str] = []
    if isinstance(krx_suspended, list):
        krx_set = {t for t in krx_suspended if isinstance(t, str)}
        # Mismatch = KRX says suspended but DART didn't have a matching event.
        cross_check_mismatch = sorted(krx_set - dart_suspended_tickers)

    extra: dict[str, Any] = {
        "dart_events": dart_events_stats,
        "kind_scrape": kind_scrape_stats,
    }
    if parse_error:
        extra["kind_parse_error"] = True
    if cross_check_mismatch:
        extra["suspension_cross_check_mismatch"] = cross_check_mismatch

    record_source_run(
        "kind",
        stats,
        heartbeat_path=vault_root / "ingested/_status/heartbeat.md",
        extra=extra,
    )
    return stats
