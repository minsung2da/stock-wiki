---
phase: 04-analysis-runner-3-role-debate
plan: 06
subsystem: analysis
tags: [decision-card, orchestrator, asyncio, pydantic, rubric, checksum, claude-cli, sqlalchemy]

# Dependency graph
requires:
  - phase: 04-01
    provides: checksum_facts (D-03 numeric value-equivalence gate) + 'live' pytest marker + import guard on src/analysis
  - phase: 04-02
    provides: roles.prompt_for/schema_for (Bull/Bear/Judge prompts + JSON schemas) + rubric.score_to_conviction/derive_stance
  - phase: 04-03
    provides: bundle.build_bundle + EvidenceBundle.to_stdin (D-02 fixed pre-fetch)
  - phase: 04-04
    provides: gate.decide + gate.lightweight_refresh (D-04 no-LLM stance gate, SC#6)
  - phase: 04-05
    provides: subagents.DebateBackend/ClaudeCliBackend/run_bull_bear + cost.StageCost/emit_cost (D-01 seam, SC#7)
  - phase: 02
    provides: cards.models.DecisionCard (Veto #2) + cards.store.get_active/save_card (atomic supersession)
provides:
  - analyze_ticker(corp_code, as_of) — the composite Phase-4 deliverable (SC#1-7 wiring)
  - gate → (3-role debate | lightweight refresh) → checksum → rubric → store composition
  - the injected-backend seam wired end-to-end (default suite quota-free; live proof gated)
affects: [08-eval-harness, 09-ops-hardening, briefing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sync orchestrator wraps the ONE async region (bull/bear/judge) via asyncio.run; all gate/checksum/rubric/store stay sync"
    - "Stance + conviction are DERIVED (rubric), never self-scored by the Judge (Veto #4 decomposable)"
    - "Judge output re-validated through DecisionCard; ValidationError → retry judge once → fail loudly (Disc #2)"

key-files:
  created:
    - src/analysis/runner.py
    - tests/analysis/test_runner.py
    - tests/analysis/test_live.py
  modified:
    - src/analysis/__init__.py
    - tests/analysis/conftest.py

key-decisions:
  - "Stance is derived via rubric.derive_stance (net mean-claim-confidence + fundamentals/catalyst rubric signs + currently_held), NOT taken from the Judge's decision.stance — keeps stance decomposable (Veto #4); the Judge schema still carries stance as an advisory lean."
  - "Conviction comes ONLY from rubric.score_to_conviction over the Judge's 5 rubric subscores (the Judge schema deliberately OMITS conviction); Veto #5 multi-source cap applied in Python."
  - "checksum source = concatenated narrative bodies (filings + hybrid re-fetches + portfolio note) from the bundle; the <untrusted> wrapper only adds delimiter lines so scanning is safe (Veto #8)."
  - "currently_held / portfolio_note_path = None [ASSUMED] until Phase 6 wires portfolio membership; the ticker is treated as not-held for the stance table."
  - "The runner emits SC#7 cost by reconstructing StageCost(**role_result.cost) for uniform coverage across the fake and real backends, plus a synthetic 'bundle' stage timed with perf_counter."

patterns-established:
  - "Per-role debate appendix: Judge stdin = bundle_stdin + '## BULL OUTPUT' + '## BEAR OUTPUT' JSON blocks; Bull/Bear never receive it (blind, SC#2)."
  - "make_fake_backend factory fixture + canned_judge fixture for per-role canned-output variants in tests."

requirements-completed: []  # SC#1-7 are WIRED + quota-free-verified, but final closure awaits Task 3 (blocking live-CLI checkpoint). Orchestrator marks SC#1-7 complete after the live run passes.

# Metrics
duration: ~22min
completed: 2026-07-06  # Tasks 1-2 only; Task 3 (live checkpoint) PENDING
---

# Phase 4 Plan 06: analyze_ticker Orchestrator Summary

**`analyze_ticker` composes the D-04 gate → (3-role Bull/Bear/Judge debate | cheap refresh) → D-03 numeric checksum → rubric conviction/stance → atomic card save, closing SC#1-7 wiring in a fully quota-free suite; the one live-CLI proof remains a blocking, orchestrator-owned checkpoint.**

> STATUS: Tasks 1-2 complete and committed. **Task 3 is a `checkpoint:human-verify gate="blocking"` that runs the REAL headless `claude` CLI and spends live Max quota — it was intentionally NOT executed by this agent.** The orchestrator + human own that run. This plan is therefore **NOT fully complete**; ROADMAP is left in-progress on purpose.

## Performance

- **Duration:** ~22 min (executor session, Tasks 1-2)
- **Completed (Tasks 1-2):** 2026-07-06
- **Tasks:** 2 of 3 (Task 3 pending — blocking live checkpoint)
- **Files created:** 3 · **Files modified:** 2

## Accomplishments

- **`analyze_ticker(corp_code, as_of, *, engine=None, backend=None, timeout_s=180)`** — the composite orchestrator (`src/analysis/runner.py`). Resolves engine/backend/as_of, loads the prior active card, runs the D-04 gate, then either:
  - **REFRESH (SC#6):** `gate.lightweight_refresh` → save (supersede prior). The `backend` is **never** touched on this path (proved by an empty `.calls`).
  - **FULL (SC#2):** `build_bundle` → `run_bull_bear` (parallel-blind, identical stdin) → Judge over `bundle + bull + bear` → `checksum_facts` (SC#3) → `score_to_conviction` + `derive_stance` (Veto #4/#5) → `DecisionCard` (Veto #2 = SC#4) → `save_card(supersedes=…)` (SC#1).
- **SC#5** empty-`contradictions[]` warning; **SC#7** per-stage cost lines for bundle + bull + bear + judge.
- **`from analysis import analyze_ticker`** re-export (`src/analysis/__init__.py`); the runner imports NO cloud-LLM SDK (D-01, import guard green).
- **SC#1-7 integration tests** (`tests/analysis/test_runner.py`) — one named, quota-free test per criterion, all green (`FakeDebateBackend` + `seeded_engine`, no real `claude` process).
- **Opt-in live smoke** (`tests/analysis/test_live.py`) created as `@pytest.mark.live`, deselected by default (zero quota) — the file for Task 3’s checkpoint run.

## Task Commits

1. **Task 1: runner.py orchestrator + `__init__` export** — `ddb6dcf` (feat)
2. **Task 2: SC#1-7 integration tests + opt-in live smoke file + conftest fixtures** — `bf331fc` (test)
3. **Task 3: live-CLI end-to-end via real `claude` (Max OAuth)** — **PENDING** — `checkpoint:human-verify` `gate="blocking"`, orchestrator-owned. NOT executed (spends live Max quota).

**Plan metadata:** committed with this SUMMARY + STATE (this plan is NOT marked complete in ROADMAP).

## Files Created/Modified

- `src/analysis/runner.py` (created) — `analyze_ticker` + debate orchestration (`_run_debate`/`_debate_async`/`_rerun_judge`), card assembly (`_assemble_card`), and pure helpers (`_default_as_of`, `_source_bodies`, `_side_strength`, `_axis_score`, `_conviction_evidence_refs`, `_ref_family`).
- `src/analysis/__init__.py` (modified) — `from .runner import analyze_ticker` + `__all__`.
- `tests/analysis/test_runner.py` (created) — SC#1-7, one named test each.
- `tests/analysis/test_live.py` (created) — single `@pytest.mark.live` real-CLI smoke (deselected by default).
- `tests/analysis/conftest.py` (modified) — `make_fake_backend` factory + `canned_judge` fixture.

## Verification

- `.venv/Scripts/python.exe -m pytest tests/analysis -q -m "not live"` → **126 passed, 1 deselected** (the live test) — NO real `claude` process spawned.
- `.venv/Scripts/python.exe -m pytest tests/analysis/test_runner.py -x -q` → **7 passed**.
- `.venv/Scripts/python.exe -m pytest tests/test_import_guard.py -q` → **4 passed** (runner has no anthropic/openai import).
- `ruff check` on all changed files → clean.
- Live gating confirmed: `-m "not live"` deselects `test_live.py` (1 deselected); `-m live --collect-only` collects it (1 test) — **collect-only, never executed** by this agent.

## Decisions Made

See `key-decisions` in the frontmatter. The load-bearing one: **stance is a deterministic rubric derivation, not the Judge’s self-reported stance** — this keeps both stance and conviction decomposable from cited inputs (Veto #4), consistent with RESEARCH Discretion #1. The Judge schema’s `decision.stance` is retained as an advisory lean but is not authoritative.

## Deviations from Plan

None requiring auto-fix rules. Two plan-faithful clarifications worth recording (no scope creep):

1. **Stance/Judge-stance reconciliation.** The plan step 7 says `stance = derive_stance(...)` while the implemented Judge schema (04-02) also carries `decision.stance`. RESEARCH Discretion #1 is authoritative ("stance from a deterministic table"), so the runner DERIVES stance via `rubric.derive_stance` fed by mean-claim-confidence strengths (Bull vs Bear) + rubric fundamentals/catalyst signs + `currently_held`. No test asserts a specific stance, so this is behavior-preserving; documented as `[ASSUMED]` reducers to tune in Phase 8.
2. **`currently_held` / portfolio note deferred.** Phase 4 has no portfolio-membership wiring (that is Phase 6). `portfolio_note_path=None` and `currently_held=False`, documented in-code as deferred. This is the "only-if-held" hook the 04-03 note lifted to the runner; it is a no-op until Phase 6.

**Total deviations:** 0 auto-fixed. **Impact:** none — all behavior matches the plan + RESEARCH discretions.

## Issues Encountered

- `build_bundle` invokes `hybrid_search` → `encode_query` (bge-m3). The runner tests stub `mcp_v2.retrieval.encode_query` to the seeded constant vector (autouse fixture), exactly as `test_bundle.py` does, so no ~2GB model download and the DB tools reach the same testcontainer via `DATABASE_URL`.

## Known Stubs

- `portfolio_note_path` / `currently_held` are hardcoded to the not-held case in the FULL path (see Deviation #2). This is an intentional, documented deferral to Phase 6 (portfolio membership), not a data-wiring gap that blocks the plan goal — the card is fully produced and saved without it.

## Next Phase Readiness

- **BLOCKING:** Task 3 live checkpoint must pass before 04-06 (and thus SC#1-7 final closure) is complete. Run:
  `.venv/Scripts/python.exe -m pytest tests/analysis/test_live.py -m live -x -q -s`
  with a Max-logged-in `claude` and `ANTHROPIC_API_KEY` unset. Expect a saved active card for corp `00126380` with non-empty `assumptions[]`, an `expires_at`, checksummed `numeric_facts`, and captured per-call cost/time (printed).
- After the checkpoint passes, the orchestrator: (a) marks 04-06 done in ROADMAP, (b) closes SC#1-7 requirements, (c) records the observed live cost/time as the Phase 9 Open-Q4 quota input.

---
*Phase: 04-analysis-runner-3-role-debate · Plan: 06*
*Tasks 1-2 completed: 2026-07-06 · Task 3 (live checkpoint): PENDING (orchestrator-owned)*

## Self-Check: PASSED

All created/modified files exist on disk (`src/analysis/runner.py`, `src/analysis/__init__.py`, `tests/analysis/test_runner.py`, `tests/analysis/test_live.py`, `tests/analysis/conftest.py`, this SUMMARY) and both task commits are in git history: `ddb6dcf` (Task 1, feat), `bf331fc` (Task 2, test). Task 3 (live checkpoint) is intentionally NOT committed by this agent — it is orchestrator-owned.
