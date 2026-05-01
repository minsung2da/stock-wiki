---
phase: 06-full-mcp-tool-surface
plan: 04
subsystem: stock_mcp.tools
tags: [mcp-tool, mcp-04, mcp-07, wave-2]
requires:
  - Plan 06-02 (FilingDoc, EventItem models; ErrorCode; build_snippet; log_tool_call)
  - Plan 06-03 (mcp_vault_engine fixture)
  - src/stock_mcp/tools/search.py (exemplar pattern)
provides:
  - "src/stock_mcp/tools/filing.py — get_filing(id) returning full body for sha256 doc id"
  - "src/stock_mcp/tools/events.py — get_recent_events(ticker, since) returning EventItem[]"
affects:
  - Plan 06-08 (get_ticker_overview): events axis composes get_recent_events
  - Plan 06-09 (server registration): both tools registered via mcp.tool()
tech-stack:
  patterns:
    - "Search.py mirror: error envelope, log_tool_call, mcp.tool() registration"
    - "Sha256 doc id lookup for get_filing (D-07 contract)"
    - "Two-step snippet pattern for events (id + build_snippet)"
key-files:
  created:
    - src/stock_mcp/tools/filing.py
    - src/stock_mcp/tools/events.py
    - tests/stock_mcp/test_get_filing.py
    - tests/stock_mcp/test_get_recent_events.py
commits:
  - 36d8da5 feat(06-04): add get_filing MCP tool with sha256 id lookup
  - 25991a4 feat(06-04): add get_recent_events MCP tool with snippet two-step pattern
verification:
  - "uv run pytest tests/stock_mcp/test_get_filing.py tests/stock_mcp/test_get_recent_events.py -q → 15 passed in 37.92s"
status: complete
---

## Summary

Implemented two read-side MCP tools per UI-SPEC tool surface inventory:

- **`get_filing(id)`** — MCP-07 / D-07. Sha256 document id lookup returning full body + frontmatter. Mirrors search.py error envelope and `@mcp.tool()` registration pattern.
- **`get_recent_events(ticker, since)`** — MCP-04 / D-05. Returns `list[EventItem]` filtered by ticker and since-timestamp, using the two-step snippet pattern (cheap id list → `build_snippet` per row).

Both tools use the standard `log_tool_call` decorator and emit the canonical error envelope on miss.

## Tests

15 tests pass (5 filing + 10 events). Tests use the `mcp_vault_engine` session fixture from Plan 06-03 — no live DB seeding inside the test body.

## Notes for downstream plans

- Plan 06-08 composes `get_recent_events` for the events axis of `get_ticker_overview`.
- Plan 06-09 must register both tools in `server.py` and verify docstring 4-section contract.
