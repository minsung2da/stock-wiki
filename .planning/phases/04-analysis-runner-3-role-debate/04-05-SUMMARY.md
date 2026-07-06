---
phase: 04-analysis-runner-3-role-debate
plan: 05
subsystem: analysis
tags: [claude-cli, subprocess, asyncio, debate-backend, cost-capture, sc7, d-01]

# Dependency graph
requires:
  - phase: 04-01
    provides: src/analysis package + CI import guard (src/analysis in GUARDED_DIRS) + tests/analysis conftest base fixtures
  - phase: 04-02
    provides: roles.py ROLE_SYSTEM_PROMPTS + ROLE_SCHEMAS the runner injects into DebateBackend.run
provides:
  - DebateBackend Protocol seam (the ONLY path to a model in the system)
  - ClaudeCliBackend — headless `claude -p` subprocess (Max OAuth, --strict-mcp-config, never --bare, stdin evidence)
  - SubAgentError (permanent) / SubAgentRetryableError (overload/rate-limit/timeout) typed split + one-retry policy
  - RoleResult (data=structured_output, cost=envelope subset)
  - run_bull_bear parallel-blind helper (prompts/schemas injected → subagents stays a leaf)
  - cost.py StageCost + capture_cost + emit_cost (SC#7 structured-stderr sink)
  - FakeDebateBackend conftest fixture (quota-free seam the whole suite uses)
affects: [04-06, analyze_ticker runner, phase-9-quota-analysis]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Patchable single-call subprocess seam (_spawn_claude) mirroring fetcher._http_get"
    - "Permanent/retryable typed exception split gated on the CLI JSON envelope is_error + error category"
    - "Injected prompts/schemas keep subagents.py a leaf (no roles.py import)"
    - "Structured-stderr cost sink separate from record_collector_run (SC#7, not collector_runs)"

key-files:
  created:
    - src/analysis/subagents.py
    - src/analysis/cost.py
    - tests/analysis/test_subagents.py
    - tests/analysis/test_cost.py
  modified:
    - tests/analysis/conftest.py
    - tests/analysis/test_gate.py

key-decisions:
  - "DebateBackend.run takes system_prompt+schema as PARAMS so subagents.py imports nothing from roles.py (leaf); the Wave-3 runner wires roles.prompt_for/schema_for"
  - "_spawn_claude returns (returncode, stdout, stderr); run() centralizes envelope classification; wall-clock timeout inside the seam raises retryable"
  - "One retry only on SubAgentRetryableError (overload/rate_limit/timeout); auth/non-zero-exit/bad-envelope are permanent and fail on attempt 1"
  - "cost.py emits structured stderr only (StageCost); does NOT reuse record_collector_run (its 7-source CHECK excludes analysis)"
  - "emit_cost extra key is cost_model (not model) and the sink is exception-swallowing so SC#7 never aborts a debate"

patterns-established:
  - "Pattern 1: quota-free FakeDebateBackend recording .calls is the seam the whole default suite uses; only 04-06 @pytest.mark.live touches the real CLI"
  - "Pattern 2: SC#6 module-isolation is asserted structurally (AST scan of gate.py imports) + a FakeDebateBackend.calls==[] runtime proof, not session-global sys.modules"

requirements-completed: [SC#2, SC#7]

# Metrics
duration: 11min
completed: 2026-07-06
---

# Phase 4 Plan 05: DebateBackend Seam + SC#7 Cost Capture Summary

**D-01 sub-agent seam — the only path to a model: a `DebateBackend` protocol with a headless `claude -p` `ClaudeCliBackend` (Max OAuth, stdin evidence, `--strict-mcp-config`, never `--bare`, structured_output-only, typed permanent/retryable errors) plus SC#7 per-stage cost capture from the CLI JSON envelope and a quota-free `FakeDebateBackend`.**

## Performance

- **Duration:** ~11 min
- **Started:** 2026-07-06T14:15:44Z
- **Completed:** 2026-07-06T14:26:09Z
- **Tasks:** 3
- **Files modified:** 6 (4 created, 2 modified)

## Accomplishments
- `DebateBackend` protocol + `ClaudeCliBackend` reaching Sonnet ONLY via the headless `claude` CLI subprocess (D-01, Max-only Veto) — evidence on stdin (T-04-13), `--strict-mcp-config`, never `--bare`, reads `structured_output` not `result`
- Typed error split (`SubAgentError` permanent vs `SubAgentRetryableError` for overload/rate-limit/timeout) with exactly one retry then fail-loudly (RESEARCH §4), and a per-call `asyncio.wait_for` wall-clock timeout (T-04-15)
- SC#7 cost/time capture (`cost.py` `StageCost` + `capture_cost` + `emit_cost`) extracting `total_cost_usd`/`duration_ms`/token subset/model from the envelope into one structured stderr line — deliberately NOT `record_collector_run` (T-04-16)
- `FakeDebateBackend` conftest fixture: canned per-role `structured_output` + synthetic cost, records `.calls`, spawns zero subprocess — the seam the whole default suite uses (deep_work_rules)
- 18 new quota-free tests (argv flags, stdin-not-argv, structured_output-not-result, error classification + retry counts, Bull/Bear parallel-blind + Judge sees both) + full `tests/analysis` suite green (123 pass), import guard green

## Task Commits

Each task was committed atomically:

1. **Task 1: subagents.py — DebateBackend seam + ClaudeCliBackend** - `6bad56e` (feat)
2. **Task 2: cost.py — SC#7 cost capture + FakeDebateBackend fixture** - `5acfbf9` (feat)
3. **Task 3: subagents + cost tests** - `03b1c7a` (test)

**Plan metadata:** (final docs commit — SUMMARY + STATE + ROADMAP + REQUIREMENTS)

## Files Created/Modified
- `src/analysis/subagents.py` - DebateBackend protocol, ClaudeCliBackend, `_spawn_claude` patchable seam, RoleResult, SubAgentError/SubAgentRetryableError, run_bull_bear
- `src/analysis/cost.py` - StageCost (extra=forbid), capture_cost (envelope subset, defensive), emit_cost (structured stderr, never raises)
- `tests/analysis/conftest.py` - added FakeDebateBackend + fake_debate_backend fixture + canned per-role outputs (existing seeded_engine/real_filing_body/card_oracle preserved)
- `tests/analysis/test_gate.py` - SC#6 refresh-path test made durable (see Deviations)
- `tests/analysis/test_subagents.py` - D-01 seam tests (patched subprocess, no live CLI)
- `tests/analysis/test_cost.py` - SC#7 capture/emit tests

## Decisions Made
- `subagents.py` stays a leaf: `run()` receives `system_prompt`/`schema` as parameters so it never imports `roles.py`; the Wave-3 runner injects `roles.prompt_for`/`schema_for` (and into `run_bull_bear`'s `prompts`/`schemas`).
- `_spawn_claude(argv, stdin_bytes, timeout_s) -> (returncode, stdout, stderr)` is a thin pure-I/O seam (mirrors `fetcher._http_get`); classification lives in `run()`. Timeout is enforced inside the seam and surfaces as a retryable error.
- SC#7 uses a dedicated structured-stderr sink (`StageCost`), never `record_collector_run` — its `_ALLOWED_SOURCES` 7-source CHECK excludes analysis (RESEARCH §6). Persistence to an `analysis_runs` table left OPTIONAL for a later phase.
- `emit_cost` uses `extra={"stage":..., "cost_model":...}` (avoids the reserved `module` LogRecord slot and keeps keys unambiguous) and swallows any logging exception so the SC#7 sink can never abort a debate.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Made the SC#6 refresh-path test durable (replaced a fragile session-global `sys.modules` assertion)**
- **Found during:** Task 2 (adding `from analysis.subagents import RoleResult` to conftest for `FakeDebateBackend`)
- **Issue:** `tests/analysis/test_gate.py::test_refresh_path_spawns_no_subagent_backend` (written in 04-04) asserted `"analysis.subagents" not in sys.modules` as an SC#6 proxy. That proxy is unreliable once `subagents.py` exists: pytest imports `analysis.subagents` while COLLECTING `test_subagents.py` (Task 3) — before any test runs — so the module is unconditionally in `sys.modules` for the whole session. The conftest import surfaced the break immediately (the assertion failed).
- **Fix:** Replaced the two `sys.modules` assertions with a durable `FakeDebateBackend.calls == []` runtime proof (the gate/refresh functions take no backend at all), removed the now-unused `import sys`. The structural SC#6 invariant (gate.py imports neither `analysis.subagents` nor `analysis.runner`) remains fully locked by the sibling `test_gate_imports_no_subagent_or_runner` AST test — no coverage lost.
- **Files modified:** tests/analysis/test_gate.py
- **Verification:** `pytest tests/analysis` → 123 pass (was 101 pass + 1 fail before the fix)
- **Committed in:** `5acfbf9` (Task 2 commit)

**2. [Rule 3 - Blocking] ruff UP041 on subagents.py**
- **Found during:** Task 2 (pre-commit ruff on the changed set)
- **Issue:** `except (asyncio.TimeoutError, TimeoutError)` — `asyncio.TimeoutError` is an alias of builtin `TimeoutError` on Python 3.11+ (UP041); the redundant tuple would block the lint gate.
- **Fix:** Simplified to `except TimeoutError` (what `asyncio.wait_for` raises on 3.11+).
- **Files modified:** src/analysis/subagents.py
- **Verification:** `ruff check` clean
- **Committed in:** `5acfbf9` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking-lint)
**Impact on plan:** Both necessary for a green, non-fragile suite. No scope creep — no production behavior changed; the gate fix strengthened an existing SC#6 test's mechanism without weakening its guarantee.

## Issues Encountered
- **Task ordering vs per-task verify commands:** the plan's Task 1/Task 2 `<verify>` reference test files created in Task 3 (and Task 1 imports `analysis.cost` created in Task 2). Verified what was verifiable at each step (Task 1: `py_compile` + import guard; Task 2: import resolution + full `tests/analysis` regression) and ran the plan's combined `test_subagents.py + test_cost.py` verify at Task 3. Each commit leaves a consistent tree.

## User Setup Required
None - no external service configuration required. (The live CLI path — real `claude` login — is exercised only by 04-06's opt-in `@pytest.mark.live` tier, out of scope here.)

## Known Stubs
None. `FakeDebateBackend` is a test fixture (not production code); `ClaudeCliBackend` is a complete, working subprocess implementation. The default suite intentionally never spawns the live CLI — that is the D-01 quota-safety contract, not a stub.

## Next Phase Readiness
- The D-01 seam, typed errors + timeout/retry, SC#7 cost capture, and the quota-free fake are all ready for 04-06's `analyze_ticker` orchestrator to wire Bull/Bear (parallel, blind) → Judge, run the D-03 checksum, save via `store`, and emit SC#7.
- 04-06 must inject `roles.prompt_for`/`schema_for` into `backend.run` / `run_bull_bear` (subagents.py deliberately does not import roles.py) and append Bull+Bear outputs to the Judge's stdin.

---
*Phase: 04-analysis-runner-3-role-debate*
*Completed: 2026-07-06*

## Self-Check: PASSED

- Created files verified on disk: `src/analysis/subagents.py`, `src/analysis/cost.py`, `tests/analysis/test_subagents.py`, `tests/analysis/test_cost.py`, `04-05-SUMMARY.md`
- Task commits verified in git log: `6bad56e`, `5acfbf9`, `03b1c7a`
- `tests/analysis` (123) + `tests/test_import_guard.py` (4) green; NO live `claude` CLI spawned (patched seam / FakeDebateBackend)
