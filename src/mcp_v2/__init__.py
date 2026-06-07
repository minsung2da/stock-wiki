"""stock-mcp-v2 — FastMCP 2.x read-side tool surface (Phase 3).

Wave-0 status: this package is registered for the wheel build + ``.mcp.json``
(Plan 03-01) but the FastMCP server (``server.py``) and the 10 read-side tools
are wired by Plans 03-03/04/06. This plan (03-02) ports two schema-agnostic
leaf utilities the Wave-0 backfill job depends on:

- :mod:`mcp_v2.embedding` — lazy bge-m3 in-process query/document encoder.
- :mod:`mcp_v2.tokenizer` — mecab-ko content-POS → stable INT[] for BM25.

Both are kept as ``src/mcp_v2`` siblings (RESEARCH §Recommended Structure)
because the notes-ingest + embedding/tsv/bm25 backfill in
``src/collectors/notes_ingest/`` imports them OUTSIDE the MCP context.
"""

from __future__ import annotations

__all__: list[str] = []
