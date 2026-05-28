---
phase: 06-full-mcp-tool-surface
plan: 07
subsystem: stock_mcp.tools.health + ingest.heartbeat
tags: [tool, health, telemetry, mcp-09, wave-2]
requires:
  - Plan 06-02 SourceHealth/HealthResponse Pydantic models
  - Plan 06-02 repo_root() public helper
  - Plan 06-03 mcp_vault_engine fixture (ingest_runs rows incl. stale macro)
  - Phase 2 ingest_runs schema (source/started_at/finished_at/error)
  - Phase 4/5 heartbeat.md format (top-level YAML sources dict)
provides:
  - "stock_mcp.tools.health.health() MCP tool registered on shared mcp instance"
  - "STALENESS_THRESHOLDS_HOURS / DOWN_AFTER_HOURS module constants (monkeypatchable)"
  - "ingest.heartbeat.read_sources() public function (renamed from _read_sources)"
  - "Backwards-compat alias _read_sources = read_sources"
affects:
  - Plan 06-08 get_ticker_overview: may surface health() as a sibling tool
  - Plan 06-09 server registration: must import stock_mcp.tools.health to register
  - Phase 9 JUDGE-05 ("근거 없음/스테일" path): health() drives Claude's refusal
    to speculate when DB down or sources stale
tech-stack:
  added: []
  patterns:
    - "Window-function SQL (ROW_NUMBER OVER PARTITION BY source) for per-source last_run/last_error in one round-trip"
    - "Three-tier fallback: ingest_runs → heartbeat.md → empty 'no telemetry available'"
    - "DB-down as signal, not failure: db.status='down' inside successful HealthResponse"
    - "Module-level constant dict (STALENESS_THRESHOLDS_HOURS) for per-source thresholds — monkeypatch.setitem swappable in tests"
    - "Naive datetime → UTC promotion at the boundary (collectors write _now_iso UTC; ingest_runs may surface naive timestamps)"
key-files:
  created:
    - src/stock_mcp/tools/health.py
    - tests/stock_mcp/test_health.py
  modified:
    - src/ingest/heartbeat.py
decisions:
  - "Plan 06-07: health() reuses tools/-package relative import convention (from ..repo_root import repo_root) matching Plan 06-05 portfolio.py — plan's literal 'from stock_mcp.repo_root import repo_root' AC was a copy-paste; relative form is project-canonical"
  - "Plan 06-07: heartbeat.read_sources kept the broader return-shape contract (full top-level YAML dict, not just the sources subdict) — record_source_run/write_disk_section both already extract meta['sources'] themselves, so narrowing the return would have required N more callsite edits without behavior gain"
  - "Plan 06-07: 'no telemetry available' is the canonical sentinel for sources missing from both ingest_runs and heartbeat.md — covered explicitly in T5 so callers can pattern-match it"
  - "Plan 06-07: heartbeat fallback also accepts last_failure as a synonym for last_error (Phase 4 heartbeat schema uses both names depending on outcome)"
metrics:
  duration_min: 25
  tasks: 2
  files_changed: 3
  completed: 2026-04-28
---

# Phase 06 Plan 07: health() MCP Tool Summary

**One-liner:** Read-only telemetry tool reporting per-source ingest staleness (ok/stale/down) + DB connectivity, with a three-tier fallback (ingest_runs → heartbeat.md → empty) so Claude always gets a deterministic signal — even when the DB is down — to drive the JUDGE-05 "근거 없음/스테일" refusal path downstream.

## Outcomes

- `health()` MCP tool registered via `mcp.tool()(health)` (search.py call-form pattern preserved).
- `STALENESS_THRESHOLDS_HOURS = {dart=26, krx=26, news=12, macro=26, kind=26}` + `DOWN_AFTER_HOURS=168` (D-14).
- Primary data: window-function aggregate over `ingest_runs` (`MAX(finished_at) FILTER (WHERE error IS NULL) AS last_success`, plus most-recent error via `ROW_NUMBER OVER (PARTITION BY source ORDER BY started_at DESC)`).
- Fallback: heartbeat.md via `read_sources()` (the renamed public helper).
- Double-fallback: every expected source filled with `status='down', last_error='no telemetry available'`.
- DB-down case returns a successful `HealthResponse` with `db.status='down'` (not an error envelope).
- T-6-07-01 mitigated: every `last_error` truncated to 200 chars before inclusion in `SourceHealth`.
- 8 tests, 8 passing. Heartbeat suite (23 tests) still green after the rename.

## Tasks

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | refactor: rename `_read_sources` → `read_sources` (public) + alias | 564dbb3 | src/ingest/heartbeat.py |
| 2 | TDD RED: failing health tool tests | 7507c96 | tests/stock_mcp/test_health.py |
| 2 | TDD GREEN: implement health() | 5bb199f | src/stock_mcp/tools/health.py, tests/stock_mcp/test_health.py |

## Acceptance Criteria — Verified

**Task 1:**
- `grep -n "def read_sources" src/ingest/heartbeat.py` → 1 hit (line 43) ✓
- `grep -n "_read_sources = read_sources" src/ingest/heartbeat.py` → 1 hit (line 164) ✓
- `pytest tests/test_heartbeat*.py` → **23 passed in 2.21s** ✓

**Task 2:**
- `grep -n "def health" src/stock_mcp/tools/health.py` → 1 hit ✓
- `grep -n "STALENESS_THRESHOLDS_HOURS" src/stock_mcp/tools/health.py` → 7 hits (≥1) with values dart=26, krx=26, news=12, macro=26, kind=26 ✓
- `grep -n "from src.ingest.heartbeat import read_sources" src/stock_mcp/tools/health.py` → 1 hit ✓
- `grep -nE "^def _repo_root|^    def _repo_root" src/stock_mcp/tools/health.py` → 0 hits (no local helper) ✓
- `grep -n "_from_ingest_runs\|_from_heartbeat" src/stock_mcp/tools/health.py` → 5 hits (≥2) ✓
- `grep -n "mcp.tool()(health)" src/stock_mcp/tools/health.py` → 1 hit ✓
- `grep -nE "### Behavior contract|### Response shape|### Errors|### Performance budget"` → 4 hits ✓
- `pytest tests/stock_mcp/test_health.py -x -q` → **8 passed in 51.85s** ✓

**One AC literal-form variance documented as deviation below.**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] T4 fixture-vault test asserted exact-equality on source key set**
- **Found during:** Task 2 first GREEN run.
- **Issue:** Test 4 asserted `set(res.sources.keys()) == {"dart", "krx", "news", "macro", "kind"}` but the session fixture's heartbeat.md acquires an extra `ingest` source key as a byproduct of `worker.ingest_run()` writing its own heartbeat block during fixture setup. Plan AC text says "All 5 expected sources are present in the response" which is a superset assertion, not an exact-match.
- **Fix:** Loosened to `>=` in the test. The implementation correctly fills missing keys but does not strip extras (which would discard real heartbeat telemetry).
- **Files modified:** tests/stock_mcp/test_health.py
- **Commit:** 5bb199f

### Plan-AC Literal Form Variance (no behavior impact)

**2. Import form: relative `..repo_root` instead of absolute `stock_mcp.repo_root`**
- **Plan AC said:** `grep -n "from stock_mcp.repo_root import repo_root" src/stock_mcp/tools/health.py` → 1 hit.
- **What we wrote:** `from ..repo_root import repo_root as _resolve_repo_root`.
- **Why:** Plan 06-05 portfolio.py already uses the relative `..repo_root` form (recorded in STATE.md decision: "get_portfolio_state uses relative repo_root import (..repo_root) to match tools/ package convention"). Using the absolute `stock_mcp.repo_root` form would split the convention across sibling tool modules.
- **Behavior:** identical — both resolve to the same `stock_mcp.repo_root.repo_root` callable.
- **Files:** src/stock_mcp/tools/health.py.

## Threat Flags

None. T-6-07-01 (info-disclosure via last_error) and T-6-07-02 (DoS via DB hang → graceful fallback to heartbeat) both fully implemented per the plan threat register.

## Downstream Impact

- Plan 06-08 (get_ticker_overview) and Plan 06-09 (server registration) can now `from stock_mcp.tools.health import health` to import the registered tool callable.
- Phase 9 JUDGE-05 has a deterministic data signal: when `health()` returns `overall='stale'` or `'down'`, Claude refuses to speculate.
- Future ingest pipeline writers can keep using `record_source_run` / `write_disk_section` exactly as before; the legacy `_read_sources` symbol still resolves via the alias.

## Self-Check: PASSED

- Task 1 commit `564dbb3` present in `git log`: `git log --oneline | grep 564dbb3` → found.
- Task 2 RED commit `7507c96` present.
- Task 2 GREEN commit `5bb199f` present.
- All 3 created/modified files exist on disk:
  - `src/stock_mcp/tools/health.py` ✓
  - `tests/stock_mcp/test_health.py` ✓
  - `src/ingest/heartbeat.py` ✓
- Verification: `pytest tests/stock_mcp/test_health.py -x -q` → **8 passed**.
- Verification: `pytest tests/test_heartbeat*.py -x -q` → **23 passed**.
