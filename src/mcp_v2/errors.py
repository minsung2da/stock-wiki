"""D-01 typed exception hierarchy for the stock-mcp-v2 read-side tools.

D-01 splits two outcomes that the v1.0 archive collapsed into a single
``{"error": {...}}`` dict:

- **Zero-row result = NORMAL.** A tool returns its Pydantic model with an empty
  collection / ``found=False`` / ``median=None`` (see :mod:`mcp_v2.models`). No
  exception is raised — "no data" is a valid, expected answer.
- **Genuine fault = LOUD.** A bad argument, a missing entity, a forbidden path,
  or a backend failure raises a typed :class:`McpToolError` subclass. FastMCP 2.x
  converts a raised ``ToolError`` into an MCP error response, and because every
  class here subclasses ``ToolError`` its message stays visible to the caller even
  under ``FastMCP(..., mask_error_details=True)`` (which only masks *non*-ToolError
  bugs). This is the documented FastMCP idiom — do NOT resurrect the archive's
  ``StructuredError``/``ErrorCode``/``to_error_response`` dict-return pattern.

Hierarchy (RESEARCH §Pattern 2, PATTERNS §errors.py):

    McpToolError (base, ToolError subclass)
    ├── InvalidArgument   — arg fails a shape/value check (ticker not ^[0-9]{6}$, bad view/type)
    ├── EntityNotFound    — ticker/corp_code resolves to no entity
    ├── FilingNotFound    — get_filing(rcept_no) has no such row
    ├── NotePathForbidden — get_note path escapes the notes/private/ whitelist
    ├── NoteNotFound      — get_note path is allowed but the file does not exist
    └── DataBackendError  — DB unreachable / query failure
"""

from __future__ import annotations

from fastmcp.exceptions import ToolError

__all__ = [
    "McpToolError",
    "InvalidArgument",
    "EntityNotFound",
    "FilingNotFound",
    "NotePathForbidden",
    "NoteNotFound",
    "DataBackendError",
]


class McpToolError(ToolError):
    """Base for all stock-mcp-v2 tool faults (bad arg, missing entity, DB error).

    Subclasses ``fastmcp.exceptions.ToolError`` so FastMCP surfaces the message
    to the MCP client even with ``mask_error_details=True`` (D-01 "tell the caller
    what to fix"). A raised ``McpToolError`` is a FAULT, never a "no-data" result.
    """


class InvalidArgument(McpToolError):
    """A tool argument failed a shape/value check before the DB was touched.

    Example: ``ticker`` not matching ``^[0-9]{6}$``, an unknown ``view`` /
    ``type`` / ``metric``. The message names the offending argument (D-01).
    """


class EntityNotFound(McpToolError):
    """A ticker/corp_code did not resolve to any known entity."""


class FilingNotFound(McpToolError):
    """``get_filing(rcept_no)`` found no matching filing row."""


class NotePathForbidden(McpToolError):
    """``get_note`` was asked for a path outside the ``notes/private/`` whitelist.

    Raised for ``..`` traversal, absolute paths outside the whitelist, and
    symlink targets that escape the whitelist (resolve() follows them first).
    """


class NoteNotFound(McpToolError):
    """``get_note`` path is inside the whitelist but the file does not exist."""


class DataBackendError(McpToolError):
    """The data backend is unreachable or a query failed (not a no-data result)."""
