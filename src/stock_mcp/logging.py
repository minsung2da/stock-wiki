"""Structured JSON log line per MCP tool call (D-23).

stdout is reserved for the MCP JSON-RPC protocol stream; all observability
goes to stderr. The log format is a single JSON object per line containing
``tool``, ``args`` (with long query redacted), ``latency_ms``,
``result_size_tokens``, and ``error`` (optional).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from typing import Any

__all__ = ["log_tool_call"]


_REDACT_QUERY_AT = 60


def _redact(args: dict[str, Any]) -> dict[str, Any]:
    """Redact long ``query`` values so no PII surfaces in logs (D-23)."""
    redacted = dict(args)
    q = redacted.get("query")
    if isinstance(q, str) and len(q) > _REDACT_QUERY_AT:
        redacted["query"] = q[:_REDACT_QUERY_AT] + "..."
    return redacted


def log_tool_call(
    tool: str,
    args: dict[str, Any],
    latency_ms: int,
    result_size_tokens: int,
    error: dict[str, Any] | None = None,
) -> None:
    """Emit a single JSON line to sys.stderr describing one MCP tool call."""
    record: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "tool": tool,
        "args": _redact(args),
        "latency_ms": int(latency_ms),
        "result_size_tokens": int(result_size_tokens),
    }
    if error is not None:
        record["error"] = error
    print(
        json.dumps(record, ensure_ascii=False, default=str),
        file=sys.stderr,
    )
