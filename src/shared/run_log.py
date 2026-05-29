"""Collector-run observability sink (Plan 01-08).

Replaces the deleted ``shared.heartbeat`` no-op stub. Each collector calls
:func:`record_collector_run` once at end of run; it INSERTs one row into the
``collector_runs`` table established by migration 0006 (Plan 01-01).

Dual-sink contract (RESEARCH.md Q5):

1. **Structured stderr log** — already emitted by each collector via
   ``_log.info("collector_run_complete", extra={...})``. Synchronous, no DB
   dependency. This is the real-time visibility channel.
2. **``collector_runs`` row** — this module. Persistent history for the
   Phase 9 ops dashboard. Best-effort: DB failure logs a WARNING and the
   helper returns ``None``; the collect run is NEVER aborted by an
   observability write failure.

Phase 9 deferral (RESEARCH.md Open Question 4): retention/cleanup of
``collector_runs`` rows is NOT a Phase 1 concern. Daily-cadence runs
accumulate ~1.8k rows/year at 5 sources × 1/day. A future Phase 9 prune
routine owns the bounded-retention policy.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_log = logging.getLogger(__name__)

# Mirrors the CHECK constraint on collector_runs.source (migration 0006).
# Surfaced here as a Python-side gate so an unknown source name fails fast
# with a clear ValueError instead of a less-informative DB-side rollback.
_ALLOWED_SOURCES: frozenset[str] = frozenset({"dart", "krx", "news", "macro", "kind"})

__all__ = ["record_collector_run"]


def record_collector_run(
    engine: Engine | None,
    source: str,
    stats: dict[str, Any],
    elapsed_ms: int,
    extra: dict[str, Any] | None = None,
) -> int | None:
    """INSERT one row into ``collector_runs``; degrade gracefully on failure.

    Parameters
    ----------
    engine : sqlalchemy.engine.Engine | None
        Live engine; if ``None`` the helper returns ``None`` without raising
        (lets tests and dry-runs skip the observability sink cleanly).
    source : str
        One of ``{'dart','krx','news','macro','kind'}``. Anything else
        raises ``ValueError`` — programmer error, not runtime data.
    stats : dict
        Per-source counter shape ``{total, inserted, updated, skipped,
        failed[]}``. Stored as JSONB. Non-JSON-serializable values
        (Path, datetime, …) are coerced via ``json.dumps(default=str)``.
    elapsed_ms : int
        Wall-clock duration of the collect run.
    extra : dict | None
        Per-source detail (revisions[], holiday_tickers[], dart_events{},
        kind_scrape{}, parse_error, …). ``None`` → SQL NULL.

    Returns
    -------
    int | None
        Inserted row id on success; ``None`` on best-effort failure or
        ``engine=None``.

    Notes
    -----
    The observability write is **best-effort**. A live DB outage during
    this call must not abort the collect — a single missing dashboard row
    is recoverable; a half-collected day's data is not.
    """
    if source not in _ALLOWED_SOURCES:
        raise ValueError(f"unknown source: {source!r}")
    if engine is None:
        return None

    try:
        stats_json = json.dumps(stats, default=str, ensure_ascii=False)
        extra_json = (
            json.dumps(extra, default=str, ensure_ascii=False)
            if extra is not None
            else None
        )
        with engine.begin() as conn:
            row_id = conn.execute(
                text(
                    """
                    INSERT INTO collector_runs
                        (source, elapsed_ms, stats, extra)
                    VALUES
                        (:source, :ms,
                         CAST(:stats AS jsonb),
                         CAST(:extra AS jsonb))
                    RETURNING id
                    """
                ),
                {
                    "source": source,
                    "ms": int(elapsed_ms),
                    "stats": stats_json,
                    # ``CAST(NULL AS jsonb)`` is the SQL-NULL JSONB; psycopg3
                    # binds Python None as a typed NULL when the column
                    # accepts NULL, but a bare ``:extra`` in a ``CASE WHEN``
                    # branch can be untyped (`could not determine data type
                    # of parameter`). Direct ``CAST(:extra AS jsonb)`` is
                    # unambiguous: None → SQL NULL → CAST(NULL AS jsonb).
                    "extra": extra_json,
                },
            ).scalar()
        return int(row_id) if row_id is not None else None
    except Exception as exc:  # noqa: BLE001 — best-effort sink, swallow & log
        # Note: ``message`` is a stdlib LogRecord-reserved key, so we use the
        # safe key ``collector_source`` for the extra. The exception type +
        # str(exc) go through positional format args so they surface in the
        # default formatter (and via caplog assertions in tests).
        _log.warning(
            "collector_runs INSERT failed (degrade to stderr-only): %s: %s",
            type(exc).__name__,
            exc,
            extra={"collector_source": source},
        )
        return None
