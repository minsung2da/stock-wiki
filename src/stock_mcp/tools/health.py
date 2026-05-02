"""health tool — DB and per-source staleness telemetry (MCP-09, D-14..D-17).

Read-only diagnostic surface backing JUDGE-05 ("근거 없음/스테일" path).
Primary data source is the ``ingest_runs`` SQL aggregate; falls back to
``heartbeat.md`` when the DB is unreachable or ingest_runs is empty
(Pitfall 3 — pre-Phase-9 production state).

D-21: never raises past the MCP boundary; an unexpected internal failure
returns a structured error envelope instead.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from db.engine import get_engine

from ..errors import ErrorCode, StructuredError, to_error_response
from ..logging import log_tool_call
from ..models import HealthResponse, SourceHealth
from ..repo_root import repo_root as _resolve_repo_root
from .search import mcp

__all__ = ["health", "STALENESS_THRESHOLDS_HOURS", "DOWN_AFTER_HOURS"]


# D-14 — code constant; tests monkeypatch via ``setitem``.
STALENESS_THRESHOLDS_HOURS: dict[str, float] = {
    "dart": 26,
    "krx": 26,
    "news": 12,
    "macro": 26,
    "kind": 26,
}
DOWN_AFTER_HOURS = 168  # 7d — stale beyond this is treated as down.
HEARTBEAT_REL_PATH = Path("vault/ingested/_status/heartbeat.md")
_KST = ZoneInfo("Asia/Seoul")
_NO_TELEMETRY = "no telemetry available"
_ERR_TRUNC = 200


def _classify(age_hours: float | None, last_error: str | None, threshold: float) -> str:
    """Return one of {'ok', 'stale', 'down'} per D-14 rules."""
    if last_error:
        return "down"
    if age_hours is None:
        return "down"
    if age_hours >= DOWN_AFTER_HOURS:
        return "down"
    if age_hours >= threshold:
        return "stale"
    return "ok"


def _ensure_aware_utc(dt: datetime) -> datetime:
    """Treat naive datetimes as UTC (matches collectors' _now_iso())."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt


def _from_ingest_runs(engine) -> dict[str, SourceHealth]:
    """Aggregate ingest_runs per source. Returns {} if there are 0 rows."""
    sql = sa.text(
        """
        WITH ranked AS (
            SELECT source, started_at, finished_at, error,
                   ROW_NUMBER() OVER (
                     PARTITION BY source ORDER BY started_at DESC
                   ) AS rn
            FROM ingest_runs
            WHERE source IS NOT NULL
        )
        SELECT
          source,
          MAX(finished_at) FILTER (WHERE error IS NULL) AS last_success,
          MAX(CASE WHEN rn = 1 THEN error END) AS last_error
        FROM ranked
        GROUP BY source
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql).mappings().all()
    out: dict[str, SourceHealth] = {}
    now = datetime.now(_KST)
    for r in rows:
        source = r["source"]
        ls = r["last_success"]
        if ls is not None:
            ls = _ensure_aware_utc(ls)
        age = ((now - ls).total_seconds() / 3600.0) if ls else None
        threshold = STALENESS_THRESHOLDS_HOURS.get(source, 26)
        last_error = r["last_error"] or None
        if last_error:
            last_error = last_error[:_ERR_TRUNC]
        status = _classify(age, last_error, threshold)
        out[source] = SourceHealth(
            status=status,
            last_success=ls,
            age_hours=age,
            last_error=last_error,
        )
    return out


def _from_heartbeat(repo_root_path: Path) -> dict[str, SourceHealth]:
    """Fallback: parse heartbeat.md via the public ingest helper."""
    from src.ingest.heartbeat import read_sources

    path = repo_root_path / HEARTBEAT_REL_PATH
    try:
        meta = read_sources(path)
    except Exception:  # noqa: BLE001 — fallback must never raise
        meta = {}
    sources_block = meta.get("sources") if isinstance(meta, dict) else None
    if not isinstance(sources_block, dict):
        return {}
    out: dict[str, SourceHealth] = {}
    now = datetime.now(_KST)
    for src_name, info in sources_block.items():
        if not isinstance(info, dict):
            continue
        ls = info.get("last_success")
        if isinstance(ls, str):
            try:
                ls = datetime.fromisoformat(ls.replace("Z", "+00:00"))
            except ValueError:
                ls = None
        if isinstance(ls, datetime):
            ls = _ensure_aware_utc(ls)
        age = ((now - ls).total_seconds() / 3600.0) if isinstance(ls, datetime) else None
        threshold = STALENESS_THRESHOLDS_HOURS.get(src_name, 26)
        le = info.get("last_error") or info.get("last_failure")
        le_str = str(le)[:_ERR_TRUNC] if le else None
        out[src_name] = SourceHealth(
            status=_classify(age, le_str, threshold),
            last_success=ls if isinstance(ls, datetime) else None,
            age_hours=age,
            last_error=le_str,
        )
    return out


def _empty_sources_response() -> dict[str, SourceHealth]:
    return {
        s: SourceHealth(
            status="down",
            last_success=None,
            age_hours=None,
            last_error=_NO_TELEMETRY,
        )
        for s in STALENESS_THRESHOLDS_HOURS
    }


def _overall(sources: dict[str, SourceHealth], db: SourceHealth) -> str:
    if db.status == "down":
        return "down"
    statuses = [s.status for s in sources.values()]
    if "down" in statuses:
        return "down"
    if "stale" in statuses:
        return "stale"
    return "ok"


def health() -> HealthResponse | dict:
    """Per-source ingest staleness + DB connectivity (MCP-09, D-14..D-17).

    ### Behavior contract
    Takes no arguments. Returns a populated ``HealthResponse`` even when the
    database is unreachable — DB outage is *signal*, not failure: ``db.status``
    becomes ``"down"`` and ``sources`` is filled from ``heartbeat.md``. The
    response always carries every expected source key (``dart``, ``krx``,
    ``news``, ``macro``, ``kind``); sources missing from both telemetry stores
    fall through to ``status='down'`` with ``last_error='no telemetry available'``.

    ### Response shape
    ``HealthResponse`` with:
      - ``overall``: ``"ok" | "stale" | "down"`` — worst of all sources + DB.
      - ``sources``: dict keyed by source name → ``SourceHealth`` (status,
        last_success, age_hours, last_error truncated to 200 chars).
      - ``db``: ``SourceHealth`` (status='down' on DB outage, 'ok' otherwise).
      - ``timestamp``: KST tz-aware ``datetime``.

    Per-source status thresholds (``STALENESS_THRESHOLDS_HOURS``):
    dart=26h, krx=26h, news=12h, macro=26h, kind=26h. Beyond
    ``DOWN_AFTER_HOURS`` (168h / 7d) a source is reported as ``down``.

    ### Errors
    Only ``INTERNAL`` is ever returned and only for genuinely unexpected
    failures. ``DB_UNAVAILABLE`` is **not** raised here — DB-down is reported
    via ``db.status='down'`` so callers can still observe per-source
    heartbeat data.

    ### Performance budget
    p95 latency < 2s; p95 serialized response < 2k tokens. The DB query is a
    single window-function aggregate over ``ingest_runs``; the heartbeat.md
    fallback is one disk read.
    """
    t0 = time.perf_counter()
    try:
        repo_root_path = _resolve_repo_root()
        db_status = SourceHealth(
            status="ok", last_success=None, age_hours=None, last_error=None
        )
        sources: dict[str, SourceHealth] = {}
        try:
            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(sa.text("SELECT 1"))
            ingest_runs_data = _from_ingest_runs(engine)
            if ingest_runs_data:
                sources = ingest_runs_data
            else:
                # ingest_runs empty (Pitfall 3) — fall back to heartbeat.md.
                sources = _from_heartbeat(repo_root_path)
        except Exception as e:  # noqa: BLE001 — DB-down is signal, not failure
            db_status = SourceHealth(
                status="down",
                last_success=None,
                age_hours=None,
                last_error=str(e)[:_ERR_TRUNC],
            )
            sources = _from_heartbeat(repo_root_path)
        # Ensure every expected source is present in the response.
        for expected in STALENESS_THRESHOLDS_HOURS:
            if expected not in sources:
                sources[expected] = SourceHealth(
                    status="down",
                    last_success=None,
                    age_hours=None,
                    last_error=_NO_TELEMETRY,
                )
        result = HealthResponse(
            overall=_overall(sources, db_status),
            sources=sources,
            db=db_status,
            timestamp=datetime.now(_KST),
        )
        latency = int((time.perf_counter() - t0) * 1000)
        log_tool_call("health", {}, latency, len(result.model_dump_json()) // 4)
        return result
    except Exception as e:  # noqa: BLE001 — D-21 catch-all
        wrapped = StructuredError(ErrorCode.INTERNAL, str(e)[:_ERR_TRUNC])
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(wrapped)
        log_tool_call("health", {}, latency, 0, error=err["error"])
        return err


# Register the callable as an MCP tool. Match search.py's call-form pattern so
# tests / direct callers can invoke ``health`` without going through FunctionTool.
mcp.tool()(health)


# Suppress unused-import warning for timedelta which is referenced indirectly
# via tests; keep for type-readability of age_hours arithmetic.
_ = timedelta
