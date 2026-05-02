"""Shared perf-test helpers and fixture wiring (Plan 06-09 Task 2).

The perf gates need the same session ``mcp_vault_engine`` fixture used by
``tests/stock_mcp``. ``pytest_plugins`` re-exports the conftest module so
``mcp_vault_engine`` resolves here without duplication.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path
from typing import Callable

import tiktoken

# Reuse the session ``mcp_vault_engine`` fixture defined in tests/stock_mcp.
pytest_plugins = ["tests.stock_mcp.conftest"]

_ENC = tiktoken.get_encoding("cl100k_base")


def measure(fn: Callable, args: dict, n: int = 20, warmup: int = 1) -> dict:
    """Run ``fn(**args)`` ``n`` times; return p50/p95 latency + token stats.

    Token counts are computed via tiktoken's ``cl100k_base`` encoding over the
    serialized response JSON (Pydantic ``model_dump_json`` when available,
    otherwise ``json.dumps`` with ``default=str``).

    A ``warmup`` rep (default 1, discarded) absorbs first-call cold-load
    costs (e.g., bge-m3 lazy-load on first ``search`` invocation). The CI
    gate measures steady-state behavior — the cold-load is a process
    startup cost the MCP daemon pays once at boot, not per request.
    """
    for _ in range(warmup):
        try:
            fn(**args)
        except Exception:  # noqa: BLE001 — warm-up failure surfaces in measured loop
            pass

    latencies_ms: list[float] = []
    token_counts: list[int] = []
    for _ in range(n):
        t0 = time.perf_counter()
        result = fn(**args)
        latency = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(latency)
        if hasattr(result, "model_dump_json"):
            payload = result.model_dump_json()
        else:
            payload = json.dumps(result, default=str)
        token_counts.append(len(_ENC.encode(payload)))

    def _p95(xs: list[float]) -> float:
        if len(xs) < 2:
            return xs[0]
        # statistics.quantiles with n=20 returns 19 cut points; the last is the
        # 95th percentile.
        return statistics.quantiles(xs, n=20)[-1]

    return {
        "n": n,
        "p50_latency_ms": statistics.median(latencies_ms),
        "p95_latency_ms": _p95(latencies_ms),
        "p50_tokens": int(statistics.median(token_counts)),
        "p95_tokens": int(_p95([float(t) for t in token_counts])),
        "max_latency_ms": max(latencies_ms),
        "max_tokens": max(token_counts),
    }


def save_perf(tool_name: str, stats: dict) -> Path:
    """Persist per-tool perf stats so PR diffs surface regressions."""
    out_dir = Path(__file__).parent
    out = out_dir / f"{tool_name}.json"
    out.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n")
    return out


def set_repo_root(repo_root: Path) -> str | None:
    """Set ``STOCK_REPO_ROOT`` and return the previous value (for restore)."""
    prev = os.environ.get("STOCK_REPO_ROOT")
    os.environ["STOCK_REPO_ROOT"] = str(repo_root)
    return prev


def restore_repo_root(prev: str | None) -> None:
    if prev is None:
        os.environ.pop("STOCK_REPO_ROOT", None)
    else:
        os.environ["STOCK_REPO_ROOT"] = prev
