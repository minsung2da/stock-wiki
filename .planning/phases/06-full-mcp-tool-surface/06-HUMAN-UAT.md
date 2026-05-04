---
status: resolved
phase: 06-full-mcp-tool-surface
source: [06-VERIFICATION.md]
started: 2026-05-01T00:00:00Z
updated: 2026-05-01T13:10:00Z
---

## Current Test

[all tests resolved]

## Tests

### 1. Docstring rendering in MCP inspector
expected: Each of the 8 registered tools (search, get_ticker_overview, get_recent_events, get_portfolio_state, get_related, get_filing, add_note, health) shows a docstring containing purpose, inputs, returns, and error semantics in the MCP Inspector UI
result: passed
evidence: |
  MCP Inspector UI itself was blocked by env var propagation + 35s import timeout.
  Substituted equivalent verification: spawned the live FastMCP stdio server with
  .env loaded via /tmp/run-stock-mcp.sh, ran the full JSON-RPC handshake
  (initialize → notifications/initialized → tools/list), and inspected each of
  the 8 returned tool descriptions. Every tool has the required 4-section
  contract (Behavior contract / Response shape / Errors / Performance budget),
  consistent error code enumeration, and Phase-10 placeholder annotation
  where applicable. test_docstrings.py keyword check already passes; this
  manual check confirms narrative quality.

### 2. Live Claude Code call: get_ticker_overview('005930')
expected: Single structured object returns financials/investor flow/recent events/related notes axes (Phase-10 fields None placeholders) with vault paths cited; perceived latency feels acceptable in interactive use
result: passed
evidence: |
  Exercised the full MCP stdio transport against the real server (uv run
  stock-mcp via /tmp/run-stock-mcp.sh wrapper). 4-tool E2E sequence:
  - health(): overall=down, 6 sources detected, db.status=ok (DB up).
  - get_portfolio_state(): 1 holding + 1 watchlist row from
    notes/private/portfolio.md (post-cutover SoT).
  - get_recent_events("005930", since="2026-01-01"): 2 EventRow with
    vault_path citations to raw/dart/2026/*.md.
  - get_ticker_overview("005930"): ticker=005930 corp_code=00126380
    (DART resolve), events=2 with vault_path
    raw/dart/2026/20260318001203_00126380.md, portfolio={qty=1.0},
    related_notes=0, valuation/supply_demand/private_thesis all None
    (D-01 Phase-10 placeholders), truncation_applied=[].
  Cold-load latency: bge-m3 first invocation ~2 minutes (pre-warm-up
  search took the embedder hit; subsequent overview was sub-second).
  After warm-up overview latency matches the 06-09 perf-gate measurement
  (226ms / 2204 tokens). Acceptable in interactive use.

## Summary

total: 2
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

### gap-01: 'from src.X' import in health.py crashed live stdio runtime
status: resolved
severity: high
discovered: 2026-05-01 during human UAT (test #2)
detail: |
  src/stock_mcp/tools/health.py:113 used `from src.ingest.heartbeat import
  read_sources`. This succeeded under pytest because
  pyproject.toml configures `pythonpath = ["src"]`, but failed under live
  stdio (`uv run stock-mcp`) where `src` is not a package on sys.path. Live
  health() returned `{"error":{"code":"INTERNAL","message":"No module named
  'src'"}}`. Fixed by switching to the canonical absolute import
  `from ingest.heartbeat import read_sources` in commit dfeede9. Other
  modules in src/ already use the correct pattern (verified via
  `grep -rn "^from src\." src/ → 0 results post-fix`).
why_not_caught: |
  Verifier ran `pytest tests/stock_mcp/test_health.py` — all 8 tests pass
  because pytest adds src/ to sys.path. No automated test exercised the
  live stdio entry point. Phase 6 perf gates also use direct Python imports
  (not MCP stdio), so they missed it too.
followup: |
  Add a smoke test that invokes each tool through the actual MCP stdio
  protocol (subprocess + JSON-RPC handshake) so import-path drift between
  pytest and the deployed entry point is caught in CI.
