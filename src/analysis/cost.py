"""SC#7 cost/time capture from the ``claude -p`` JSON envelope + structured-stderr sink.

Each Bull/Bear/Judge call returns a JSON envelope carrying the per-call cost/time
subset (live-verified, RESEARCH §3): ``total_cost_usd``, ``duration_ms``, and the
``usage{input_tokens, output_tokens, cache_*}`` / ``modelUsage{...}`` maps. This
module extracts that subset (:func:`capture_cost`) and emits ONE structured stderr
line per stage (:func:`emit_cost`) — the Phase 9 quota-analysis input.

Deliberately does NOT reuse ``shared.run_log.record_collector_run``: its
``_ALLOWED_SOURCES`` is a hard 7-source CHECK (``dart``/``krx``/``news``/``macro``/
``kind``/``fundamentals``/``notes_ingest``) that **excludes analysis** — a structured
stderr line alone satisfies SC#7 (RESEARCH §6 / Discretion #6). An ``analysis_runs``
persistence table is OPTIONAL this phase; if added later it must copy run_log's
best-effort-degrade pattern (a DB failure logs a WARNING and never aborts the debate).

Pure extraction + logging — no LLM, no subprocess, no DB. Every extractor is
defensive: a partial or empty envelope yields ``None`` fields, never an exception
(``total_cost_usd`` on Max is a quota-equivalent proxy, not a billed dollar).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict

_log = logging.getLogger(__name__)

__all__ = ["StageCost", "capture_cost", "emit_cost"]


class StageCost(BaseModel):
    """The SC#7 cost/time subset for one debate stage (bull / bear / judge).

    All numeric fields are optional: a degraded or partial envelope still yields a
    valid ``StageCost`` (with ``None`` where the key was absent) so the SC#7 sink
    never blocks the debate on a missing metric.
    """

    model_config = ConfigDict(extra="forbid")

    role: str
    total_cost_usd: float | None = None
    duration_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    model: str | None = None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def capture_cost(role: str, env: dict[str, Any]) -> StageCost:
    """Extract the SC#7 cost/time subset from a ``claude -p`` JSON envelope.

    Tolerates missing keys (a partial envelope), a non-dict ``usage`` / ``modelUsage``
    (defends to an empty map), and non-numeric values (coerced to ``None``). The
    model name is the first ``modelUsage`` key (e.g. ``claude-sonnet-4-6``).
    """
    usage = env.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    model_usage = env.get("modelUsage")
    model = (
        next(iter(model_usage), None)
        if isinstance(model_usage, dict) and model_usage
        else None
    )
    return StageCost(
        role=role,
        total_cost_usd=_as_float(env.get("total_cost_usd")),
        duration_ms=_as_int(env.get("duration_ms")),
        input_tokens=_as_int(usage.get("input_tokens")),
        output_tokens=_as_int(usage.get("output_tokens")),
        cache_read_input_tokens=_as_int(usage.get("cache_read_input_tokens")),
        model=model,
    )


def emit_cost(stage_cost: StageCost) -> None:
    """Emit ONE structured stderr line for ``stage_cost`` (SC#7 Phase 9 input).

    Matches the house stdout-JSON / stderr-logs convention
    (``logging.info(..., extra={...})``). Never raises — a partial ``StageCost`` (all
    ``None`` numerics) still logs cleanly; any logging fault degrades to a DEBUG line
    so the SC#7 sink can never abort the debate.
    """
    try:
        _log.info(
            "analysis_stage_cost",
            extra={
                "stage": stage_cost.role,
                "total_cost_usd": stage_cost.total_cost_usd,
                "duration_ms": stage_cost.duration_ms,
                "input_tokens": stage_cost.input_tokens,
                "output_tokens": stage_cost.output_tokens,
                "cache_read_input_tokens": stage_cost.cache_read_input_tokens,
                "cost_model": stage_cost.model,
            },
        )
    except Exception:  # noqa: BLE001 — SC#7 sink must never abort the debate
        _log.debug("emit_cost logging failed", exc_info=True)
