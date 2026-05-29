"""DART collector — A+B filings only (D-01, COLL-06).

Post-Plan 01-07 (Phase 1 Wave 2 v2.0): writes directly into the ``filings``
Postgres table via ``db_writer.upsert_dart_filing``. The Markdown vault
intermediate is gone. Bug C entity upsert (quick-260418-asr) is preserved
— fires when at least one filing landed (inserted+updated > 0) so
downstream ``resolve_entity(ticker)`` matches.

DART rate limit (RESEARCH.md Pitfall 2) is preserved by KEEPING the
per-filing loop strictly serial. Do NOT parallelize across filings or
across corps.

Hard Veto #8 — DART body is stored WHOLE in ``filings.body_md`` (no
chunking on insert). The ``chunks`` table is NOT touched by this
collector; Phase 3 owns narrative-search rebuild.

Hard Veto #9 — no Markdown vault writes. There is no ``vault_root``
parameter and no ``writer.*`` call site. Plan 01-09 deletes
``writer.py`` from disk after every collector has cut over.

R-12 / 01-04 parity: ``engine`` is REQUIRED. FK on filings.corp_code +
the Bug C entity upsert both need a live engine.

NO imports of ``anthropic`` or ``openai`` — guarded by
tests/test_import_guard.py (COLL-07 CI discipline).
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from datetime import time as dtime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from collectors.dart import client, db_writer, fetcher
from db.entity import upsert_entity
from shared.run_log import record_collector_run

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_log = logging.getLogger(__name__)

__all__ = ["collect_dart"]


def collect_dart(
    *,
    corp_code: str,
    since: str,
    max_docs: int = 100,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Collect DART A+B filings for a single corp into the ``filings`` table.

    Parameters
    ----------
    corp_code : str
        8-digit DART corporation code (e.g., "00126380" for Samsung).
    since : str
        ISO date "YYYY-MM-DD" — earliest filing receipt date to include.
    max_docs : int
        Phase-3 cap (D-03). Phase 4 may revisit.
    engine : sqlalchemy.Engine
        REQUIRED for the filings UPSERT and the Bug C entity upsert. If None,
        a RuntimeError is raised — the v1.0 offline-mocked test pattern is
        replaced by DB-state-asserting tests under tests/collectors/dart/.

    Returns
    -------
    dict
        ``{"total", "inserted", "updated", "skipped", "failed": list[dict],
           "elapsed_ms": int}`` (Phase 1 v2.0 schema — "succeeded" split into
        inserted+updated; failures still carry per-doc isolation context).
    """
    if engine is None:
        raise RuntimeError(
            "collect_dart requires a DB engine for filings UPSERT"
        )

    start = time.monotonic()
    client.get_client()
    corp = client.find_corp(corp_code)
    ticker = getattr(corp, "stock_code", None)
    company_name = getattr(corp, "corp_name", None)

    filings = fetcher.list_ab_filings(corp_code, since, max_docs)

    stats: dict[str, Any] = {
        "total": len(filings),
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "failed": [],
    }

    for filing in filings:
        try:
            # Fetch body up-front so the content-hash comparison reflects
            # the current remote state (COLL-08: dedup on content, not URL).
            body = fetcher.fetch_body(filing)

            # rcept_dt is "YYYYMMDD"; compose TIMESTAMPTZ at KST close 15:30.
            rcept_dt = str(filing.rcept_dt)
            filed_at = datetime.combine(
                date.fromisoformat(
                    f"{rcept_dt[0:4]}-{rcept_dt[4:6]}-{rcept_dt[6:8]}"
                ),
                dtime(15, 30),
                tzinfo=ZoneInfo("Asia/Seoul"),
            )

            outcome = db_writer.upsert_dart_filing(
                engine,
                rcept_no=str(filing.rcept_no),
                corp_code=corp_code,
                ticker=ticker,
                filed_at=filed_at,
                report_nm=str(filing.report_nm),
                pblntf_ty=getattr(filing, "pblntf_ty", "A"),
                body_md=body,
                source_url=str(
                    getattr(
                        filing,
                        "source_url",
                        f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={filing.rcept_no}",
                    )
                ),
            )

            if outcome == "inserted":
                stats["inserted"] += 1
            elif outcome == "updated":
                stats["updated"] += 1
            else:
                stats["skipped"] += 1
        except Exception as exc:  # noqa: BLE001 — per-filing isolation (COLL-08)
            stats["failed"].append(
                {"doc": str(filing.rcept_no), "error": str(exc)}
            )

    # Bug C: seed entities/entity_aliases once per run so resolve_entity(ticker)
    # succeeds downstream. The v1.0 gate was ``stats["succeeded"] > 0``; the
    # Phase 1 stats shape splits succeeded → inserted + updated, so the gate
    # is now ``(inserted + updated) > 0``. Never allow entity seeding to fail
    # the collect run.
    if (stats["inserted"] + stats["updated"]) > 0:
        canonical_name = company_name or ticker or corp_code
        try:
            upsert_entity(engine, corp_code, canonical_name, ticker)
        except Exception as exc:  # noqa: BLE001
            stats.setdefault("warnings", []).append(
                f"entity upsert failed: {exc!r}"
            )

    stats["elapsed_ms"] = int((time.monotonic() - start) * 1000)

    # Structured run-complete log (01-08 wires this into collector_runs table).
    _log.info(
        "collector_run_complete",
        extra={
            "source": "dart",
            "stats": stats,
            "elapsed_ms": stats["elapsed_ms"],
        },
    )
    # Plan 01-08: dual-sink DB row (RESEARCH.md Q5). DART has no per-source
    # extras at Phase 1 (Phase 9 may add); pass extra=None.
    record_collector_run(engine, "dart", stats, stats["elapsed_ms"], extra=None)
    return stats
