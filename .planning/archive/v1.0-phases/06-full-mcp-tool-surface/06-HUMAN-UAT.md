---
status: partial
phase: 06-full-mcp-tool-surface
source: [06-VERIFICATION.md]
started: 2026-05-01T00:00:00Z
updated: 2026-05-01T13:35:00Z
---

## Current Test

[awaiting human (user) testing — orchestrator-side stdio probe is not a substitute for human UAT]

## Tests

### 1. Docstring rendering in MCP inspector
expected: Each of the 8 registered tools shows a coherent purpose / inputs / returns / errors contract in the MCP Inspector UI (or equivalent client surface)
result: pending
notes: |
  Orchestrator confirmed all 8 tools register over live MCP stdio
  (handshake + tools/list) and that each description carries the
  4-section contract. This proves the wire-level surface is correct
  but does NOT replace human visual confirmation in a real client.
  User must verify in their own Claude Code session once stock-mcp
  is enabled.

### 2. Live Claude Code call: get_ticker_overview('005930')
expected: Real Claude Code session shows stock-mcp connected; calling get_ticker_overview('005930') returns structured response with vault path citations and acceptable interactive latency
result: pending
notes: |
  User reports `/mcp` does not list stock-mcp yet — project-scoped
  .mcp.json requires explicit user approval. See README/CLAUDE.md
  follow-up: enable stock-mcp in user's Claude Code, then call
  get_ticker_overview('005930') from the session.

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps

### gap-01: 'from src.X' import in health.py crashed live stdio runtime
status: resolved
severity: high
discovered: 2026-05-01 during orchestrator-side stdio probe
detail: |
  src/stock_mcp/tools/health.py:113 used `from src.ingest.heartbeat import
  read_sources`. This succeeded under pytest because pyproject.toml
  configures `pythonpath = ["src"]`, but failed under live stdio
  (`uv run stock-mcp`) where `src` is not a package on sys.path. Live
  health() returned `{"error":{"code":"INTERNAL","message":"No module
  named 'src'"}}`. Fixed by switching to the canonical absolute import
  `from ingest.heartbeat import read_sources` in commit dfeede9.
why_not_caught: |
  Verifier ran `pytest tests/stock_mcp/test_health.py` — all 8 tests pass
  because pytest adds src/ to sys.path. No automated test exercised the
  live stdio entry point. Phase 6 perf gates also use direct Python
  imports (not MCP stdio), so they missed it too.
followup: |
  Add a smoke test that invokes each tool through the actual MCP stdio
  protocol (subprocess + JSON-RPC handshake) so import-path drift between
  pytest and the deployed entry point is caught in CI.
