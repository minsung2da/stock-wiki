"""Fundamentals collector — D-06 (Phase 3 v2.0).

This collector INSERTs directly into the ``fundamentals`` Postgres table via
``db_writer.upsert_fundamentals``. Mirrors ``collectors.krx`` pattern-for-pattern:
``Portfolio.load(Path(".")).scope_tickers()`` for scope, per-ticker try/except
isolation (COLL-08), ``resolve_entity`` pre-write (R-03 missing-entity), and a
dual-sink observability record (``_log.info("collector_run_complete", ...)`` +
``record_collector_run(engine, "fundamentals", ...)``).

Data sources (Veto #6 — all typed NUMERIC, never embedded):
- pykrx ``get_market_fundamental_by_date`` → PER / PBR / EPS / BPS.
- Official DART annual index → ROE, independently of KRX availability.

The ``fundamentals`` source name is already allowed by Plan 03-01 (which owns
``run_log._ALLOWED_SOURCES`` and the ``collector_runs.source`` CHECK widening
in migration 0008). This module only CALLS ``record_collector_run`` — it does
NOT edit ``run_log.py`` and adds NO CHECK SQL.

COLL-07: no LLM SDK imports anywhere under ``collectors/`` (enforced by
``tests/test_import_guard.py``). Official ROE uses the deterministic DART API.

ROE fill-in COALESCE: ``db_writer`` preserves an existing ROE when a later
pykrx-only fetch returns ``roe=None`` (mirror of the KRX T+2 short fill-in) so a
fundamentals re-run never NULL-clobbers a prior sourced ROE.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from collectors.fundamentals import dart_roe, db_writer, fetcher
from db.entity import resolve_entity
from shared.portfolio import Portfolio
from shared.run_log import record_collector_run

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_log = logging.getLogger(__name__)

__all__ = ["collect_fundamentals"]


def _today_iso_krx() -> str:
    """Return today's date as ISO ``YYYY-MM-DD`` string in KST."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()


def _coerce_fundamental_row(df) -> dict[str, Any] | None:
    """Map a pykrx ``get_market_fundamental`` one-row DataFrame to db_writer shape.

    pykrx columns: BPS / PER / PBR / EPS / DIV / DPS (Korean market frame uses
    these ASCII labels). Returns None on an empty frame (non-trading day /
    illiquid name). Missing columns map to None (typed NUMERIC nullable).
    """
    if df is None or len(df) == 0:
        return None
    row = df.iloc[0]

    def _num(col: str) -> float | None:
        if col not in row.index:
            return None
        v = row[col]
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        if f != f:  # NaN
            return None
        return f

    return {
        "per": _num("PER"),
        "pbr": _num("PBR"),
        "eps": _num("EPS"),
        "bps": _num("BPS"),
        "dividend_yield": _num("DIV"),
        "dps": _num("DPS"),
    }


def collect_fundamentals(
    *,
    engine: Engine | None = None,
    since: str | None = None,
) -> dict[str, Any]:
    """Run the fundamentals collector for the current scope (holdings ∪ watchlist).

    Fetch market metrics and official prior-year annual ROE independently.
    ROE is currently observed published data, not a historical point-in-time
    reconstruction for ``since``. Its reporting period and observation time
    are stored separately from the market snapshot date.

    Per-ticker isolation (COLL-08): any exception during a single ticker is
    captured into ``stats["failed"]`` and does NOT abort the loop.

    R-03 (missing-entity): if ``resolve_entity(ticker)`` returns None, the ticker
    lands in ``stats["failed"]`` with ``error="missing_entity"`` and no row is
    written.

    Returns stats: ``{total, inserted, updated, skipped, failed[], elapsed_ms}``.

    Raises:
        RuntimeError: if ``engine`` is None — FK resolution requires it.
    """
    if engine is None:
        raise RuntimeError("collect_fundamentals requires a DB engine for FK resolution")

    start = time.monotonic()
    date_iso = since or _today_iso_krx()
    date_str = date_iso.replace("-", "")
    fdate_obj = date.fromisoformat(date_iso)
    roe_year = fdate_obj.year - 1

    repo_root = Path(".")
    portfolio = Portfolio.load(repo_root)
    scope = portfolio.scope_tickers()

    stats: dict[str, Any] = {
        "total": len(scope),
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "failed": [],
        "roe": {"requested": 0, "available": 0, "missing": 0, "failed": 0},
    }
    empty_tickers: list[str] = []
    missing_entities: list[str] = []

    for ticker in scope:
        try:
            # R-03: resolve entity BEFORE writing. Missing entity → no write.
            ent = resolve_entity(engine, ticker)
            if ent is None:
                missing_entities.append(ticker)
                stats["failed"].append({"doc": ticker, "error": "missing_entity"})
                continue

            outcomes: list[str] = []
            failures: list[dict[str, str]] = []
            try:
                fund_df = fetcher.fetch_market_fundamental(ticker, date_str)
                fund_row = _coerce_fundamental_row(fund_df)
                if fund_row is None:
                    empty_tickers.append(ticker)
                else:
                    outcomes.append(
                        db_writer.upsert_fundamentals(
                            engine,
                            ticker=ticker,
                            fdate=fdate_obj,
                            corp_code=ent.corp_code,
                            **fund_row,
                            roe=None,
                            source="fundamentals",
                        )
                    )
            except Exception as exc:  # noqa: BLE001 — isolate independent sources
                failures.append({"source": "krx", "error": type(exc).__name__})

            stats["roe"]["requested"] += 1
            try:
                observation = dart_roe.fetch_annual_roe(ent.corp_code, roe_year)
                if observation is None:
                    stats["roe"]["missing"] += 1
                else:
                    outcomes.append(
                        db_writer.upsert_roe(
                            engine,
                            ticker=ticker,
                            fdate=fdate_obj,
                            corp_code=ent.corp_code,
                            observation=observation,
                        )
                    )
                    stats["roe"]["available"] += 1
            except Exception as exc:  # noqa: BLE001 — market data survives DART failure
                stats["roe"]["failed"] += 1
                failures.append({"source": "dart_roe", "error": type(exc).__name__})
            if failures:
                # Exception messages may contain authenticated provider URLs.
                stats["failed"].append(
                    {"doc": ticker, "error": "source_failure", "sources": failures}
                )
                _log.warning("fundamentals source failure for %s: %s", ticker, failures)
            if "inserted" in outcomes:
                stats["inserted"] += 1
            elif "updated" in outcomes:
                stats["updated"] += 1
            elif outcomes or not failures:
                stats["skipped"] += 1
        except Exception as exc:  # noqa: BLE001 — per-ticker isolation (COLL-08)
            _log.warning("fundamentals collect failed for %s: %s", ticker, type(exc).__name__)
            stats["failed"].append({"doc": ticker, "error": type(exc).__name__})

    stats["elapsed_ms"] = int((time.monotonic() - start) * 1000)

    extra: dict[str, Any] = {}
    if empty_tickers:
        extra["empty_tickers"] = empty_tickers
    if missing_entities:
        extra["missing_entity"] = missing_entities

    _log.info(
        "collector_run_complete",
        extra={
            "source": "fundamentals",
            "stats": stats,
            "elapsed_ms": stats["elapsed_ms"],
            "extra": extra or None,
        },
    )
    record_collector_run(engine, "fundamentals", stats, stats["elapsed_ms"], extra=extra or None)
    return stats
