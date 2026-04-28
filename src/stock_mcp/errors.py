"""Structured error types for stock-mcp (D-21).

MCP tool responses must never propagate raw exceptions to stdout — that would
corrupt the JSON-RPC protocol stream. Instead, tools catch ``StructuredError``
and return the ``to_error_response`` shape, which is safe JSON.
"""

from __future__ import annotations

from enum import Enum

__all__ = ["ErrorCode", "StructuredError", "to_error_response"]


class ErrorCode(str, Enum):
    SEARCH_TIMEOUT = "SEARCH_TIMEOUT"
    INVALID_TICKER = "INVALID_TICKER"
    DB_UNAVAILABLE = "DB_UNAVAILABLE"
    EMBEDDING_FAILED = "EMBEDDING_FAILED"
    BM25_FAILED = "BM25_FAILED"
    INTERNAL = "INTERNAL"
    # Phase 6 additions (Plan 06-02): tool-surface error codes consumed by
    # add_note (WRITE_FORBIDDEN, INVALID_FRONTMATTER), get_filing
    # (NOT_FOUND, PATH_NOT_FOUND), health (STALE_DATA), and
    # get_recent_events (INVALID_DATE).
    WRITE_FORBIDDEN = "WRITE_FORBIDDEN"
    INVALID_FRONTMATTER = "INVALID_FRONTMATTER"
    NOT_FOUND = "NOT_FOUND"
    PATH_NOT_FOUND = "PATH_NOT_FOUND"
    STALE_DATA = "STALE_DATA"
    INVALID_DATE = "INVALID_DATE"


class StructuredError(Exception):
    """Error carrying a fixed ErrorCode, a human message, and optional details."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def to_error_response(e: StructuredError) -> dict:
    """Convert a StructuredError into the D-21 MCP error response envelope."""
    return {
        "error": {
            "code": e.code.value,
            "message": e.message,
            "details": e.details or {},
        }
    }
