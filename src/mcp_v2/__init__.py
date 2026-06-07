"""stock-mcp-v2 — FastMCP 2.x read-side tool surface (Phase 3).

Wave-0 status: the FastMCP server (``server.py``) and the 10 read-side tool
*callables* are wired by Plans 03-04/05/06. Two schema-agnostic leaf utilities the
Wave-0 backfill job depends on were ported in Plan 03-02:

- :mod:`mcp_v2.embedding` — lazy bge-m3 in-process query/document encoder.
- :mod:`mcp_v2.tokenizer` — mecab-ko content-POS → stable INT[] for BM25.

Both are kept as ``src/mcp_v2`` siblings (RESEARCH §Recommended Structure)
because the notes-ingest + embedding/tsv/bm25 backfill in
``src/collectors/notes_ingest/`` imports them OUTSIDE the MCP context.

Plan 03-03 added the dependency-free leaf layer that the tool plans import as
contracts: the shared FastMCP instance (:data:`mcp`), the D-01 typed exception
hierarchy (:mod:`mcp_v2.errors`), the empty-able return models
(:mod:`mcp_v2.models`), the WRAP+FLAG injection helper (:mod:`mcp_v2.injection`),
and the read-only path-traversal defense (:mod:`mcp_v2.paths`).
"""

from __future__ import annotations

from mcp_v2._mcp import mcp
from mcp_v2.errors import (
    DataBackendError,
    EntityNotFound,
    FilingNotFound,
    InvalidArgument,
    McpToolError,
    NoteNotFound,
    NotePathForbidden,
)

__all__ = [
    "mcp",
    "McpToolError",
    "InvalidArgument",
    "EntityNotFound",
    "FilingNotFound",
    "NotePathForbidden",
    "NoteNotFound",
    "DataBackendError",
]
