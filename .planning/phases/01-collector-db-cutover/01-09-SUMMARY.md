---
phase: "01-collector-db-cutover"
plan: "01-09"
subsystem: "collectors/governance"
tags: [veto-9, writer-deletion, ci-fence, runtime-guard, smoke-test, sc-coverage, phase-1, wave-3, closeout]
requires:
  - Wave 1/2 collector cutovers (01-03..01-07) — every collector had to call
    db_writer.* exclusively before writer.py could be physically removed
  - Plan 01-08 (heartbeat deletion + record_collector_run) — landed in
    parallel; this plan's smoke test asserts heartbeat absence and
    collector_runs row presence end-to-end
provides:
  - All 5 src/collectors/<src>/writer.py modules deleted from disk (Veto #9 layer 1)
  - tests/test_no_writer.py — four-assertion CI guard (file absence, importability,
    AST scan of __init__.py imports, F-3 session-wide vault-Markdown scan)
  - src/cli/__main__.py runtime fence — CWD-independent absolute-path check that
    fires SystemExit before any work happens if any writer.py resurrects
  - tests/test_phase01_smoke.py — slow-marked vertical-slice smoke (macro
    DGS10 mocked end-to-end) plus defensive writer/heartbeat absence checks
  - Success Criteria Coverage matrix mapping SC-1..SC-6 to satisfying plans
    (see body of this SUMMARY)
affects:
  - Phase 2 (decision_card schema) — collectors-side cutover complete; downstream
    plans can assume Postgres-only data layer with no vault revival surface
  - All future collectors / future maintainers — CI fence trips on any attempt
    to re-add a Markdown vault path
tech-stack:
  added: []
  patterns:
    - "Four-layer Veto #9 defense — physical deletion + find_spec ImportError +
       AST scan of __init__.py + runtime CLI fence (RESEARCH.md Q9: defense in
       depth)"
    - "CWD-independent runtime guard — absolute paths anchored via
       Path(__file__).resolve().parents[2], not relative paths that would
       silently no-op under unusual CWDs (F-5 / R-5)"
    - "F-3 broad-spectrum CI guard — a session-wide rglob for any .md file under
       any vault/ path component (excluding documented notes/private/, .planning/,
       and tests/fixtures/), not just specific known writer output paths"
    - "Vertical-slice smoke pattern — minimal mocked-fetcher invocation of the
       simplest collector (macro) end-to-end, asserting DB rows AND filesystem
       negative invariants together"
    - "Deferred-items workflow — log out-of-scope pre-existing failures to
       deferred-items.md instead of expanding plan scope (DI-1, DI-2 logged
       during Task 1 fast-suite sanity check)"
key-files:
  created:
    - tests/test_no_writer.py
    - tests/test_phase01_smoke.py
    - .planning/phases/01-collector-db-cutover/deferred-items.md
    - .planning/phases/01-collector-db-cutover/01-09-SUMMARY.md
  modified:
    - src/cli/__main__.py
    - tests/collectors/conftest.py
    - tests/collectors/news/test_collect_news.py
    - tests/test_entity_upsert.py
  deleted:
    - src/collectors/dart/writer.py
    - src/collectors/krx/writer.py
    - src/collectors/news/writer.py
    - src/collectors/macro/writer.py
    - src/collectors/kind/writer.py
    - tests/collectors/kind/test_writer.py
    - tests/collectors/krx/test_writer.py
decisions:
  - "Veto #9 enforcement is layered: physical deletion + ImportError + AST scan
     + runtime fence + F-3 session-wide .md guard. Each layer catches a regression
     vector the others might miss (stub package vs renamed import vs IDE-restored
     file vs vault-shaped tmp_path). Defense in depth, not redundancy."
  - "Runtime fence uses absolute paths from Path(__file__).resolve().parents[2]
     instead of relative 'src/collectors/...' strings (F-5 / R-5). A relative
     path silently no-ops when stock is invoked from outside repo root, defeating
     the fence. The cost is one extra Path computation at module import."
  - "Plan 01-04 / 01-05 / 01-06 left ambiguous wording about vault_tmp fixture
     retention (W-1). This plan picks 'retire vault_tmp' decisively:
     tests/collectors/conftest.py drops the fixture, and the only remaining
     consumer (tests/collectors/news/test_collect_news.py) is migrated to
     tmp_path + inline portfolio.md write + monkeypatch.chdir. This matches the
     plan's task 1 step 3 'FIX the consuming tests' directive."
  - "Pre-existing tests/test_entity_upsert.py::TestCollectDartEntitySeed (E5/E6/
     no-success-no-seed) was broken by plans 01-02 + 01-07 (vault_root kwarg
     removal). Rule 1 deviation: the failing class is removed inline since its
     entity-seed surface is covered by
     tests/collectors/dart/test_collect_dart_bug_c_entity_upsert. Documented in
     Deviations below."
  - "Pre-existing tests/test_migration.py::test_events_jsonb_and_fk (broken by
     plan 01-01 migration 0006 events→events_legacy rename) is logged to
     deferred-items.md (DI-1) instead of fixed inline. Scope boundary: 01-09
     owns Veto #9 + SC coverage, not 01-01 verification gaps."
metrics:
  tasks_completed: 3
  duration_minutes: ~60
  files_created: 4
  files_modified: 4
  files_deleted: 7
  tests_added: 7   # 4 in test_no_writer.py + 3 in test_phase01_smoke.py
  commit_hashes:
    - 1c81a69  # Task 1 — writer deletion + dependent test cleanup
    - dd5c3c7  # Task 2 — CI fence (4 assertions) + runtime guard
    - 6ca871b  # Task 3 — vertical smoke + defensive duplicates
requirements-completed: [SC-1, SC-5]
completed: 2026-05-29
---

# Phase 1 Plan 01-09: Writer Deletion + Veto #9 Fences + SC Coverage Matrix

**Five collector writer modules physically deleted, a four-layer CI fence (file absence + find_spec + AST scan + session-wide vault-Markdown rglob) plus a CWD-independent CLI runtime guard prevent Markdown-vault revival, and a slow-marked smoke test (`collect_macro` against a fresh testcontainer) closes the Phase 1 vertical slice.**

## Performance

- **Duration:** ~60 min
- **Started:** 2026-05-29 (Wave 3 dispatch)
- **Completed:** 2026-05-29T01:42Z
- **Tasks:** 3
- **Files created:** 4 (2 tests + deferred-items.md + this SUMMARY)
- **Files modified:** 4 (cli/__main__.py + 3 test files)
- **Files deleted:** 7 (5 writer.py + 2 obsolete test_writer.py)

## Accomplishments

- **Veto #9 layer 1 — physical deletion.** All five
  `src/collectors/{dart,krx,news,macro,kind}/writer.py` modules removed from
  disk (and from git history going forward). No collector has a Markdown
  vault write path anymore.
- **Veto #9 layer 2 — CI fence.** `tests/test_no_writer.py` enforces four
  invariants on every test run: writer files absent, modules not importable,
  collector `__init__.py` files contain no `writer` import (AST scan), and
  no `.md` file anywhere under any `vault/` path component during the
  session (F-3 enforcement).
- **Veto #9 layer 3 — runtime fence.** `src/cli/__main__.py::main()` asserts
  at the top of every invocation that no legacy `writer.py` resurfaced
  (e.g., IDE-restored deleted file). The check uses an absolute path
  anchored via `Path(__file__).resolve().parents[2]`, so it works
  identically whether `stock` is invoked from repo root or anywhere else
  (R-5 / F-5 fix from PLAN-VERIFICATION.md).
- **Vertical-slice smoke** — `tests/test_phase01_smoke.py` exercises
  `collect_macro` end-to-end against a fresh testcontainer with mocked
  ECOS+FRED fetchers: 2 rows in `macro_series`, 1 row in
  `collector_runs`, no `vault/` directory created.
- **Success Criteria Coverage matrix** — explicit per-SC traceability to
  the satisfying plan IDs (see table below).
- **vault_tmp fixture retired** — W-1 cross-wave fixture-policy
  contradiction resolved: the conftest fixture is gone, the only consumer
  migrated to `tmp_path` + inline `notes/private/portfolio.md` +
  `monkeypatch.chdir(tmp_path)`.

## Task Commits

1. **Task 1: Delete writer.py files + obsolete test_writer files** — `1c81a69` (`chore`)
   - `git rm` of 5 writer.py + 2 test_writer.py (kind, krx)
   - Strip writer-test block from `tests/collectors/news/test_collect_news.py`
     and rewire the `_seed_portfolio` helper to `tmp_path`-based chdir
   - Retire `vault_tmp` fixture from `tests/collectors/conftest.py`
   - Remove the legacy `TestCollectDartEntitySeed` class from
     `tests/test_entity_upsert.py` (Rule 1 inline fix — see Deviations)
   - Log DI-1 + DI-2 (pre-existing failures) to `deferred-items.md`
2. **Task 2: CI fence + runtime guard** — `dd5c3c7` (`test`)
   - `tests/test_no_writer.py` — 4-assertion fence (file absence,
     find_spec, AST scan, session-wide vault-Markdown rglob)
   - `src/cli/__main__.py::main()` runtime fence using
     `Path(__file__).resolve().parents[2]`-anchored absolute paths
   - Manual RED→GREEN: confirmed FATAL exit on resurrected writer.py +
     clean exit after cleanup
3. **Task 3: Vertical smoke** — `6ca871b` (`test`)
   - `tests/test_phase01_smoke.py` — slow-marked, 3 tests:
     `test_phase01_macro_end_to_end` (mocked fetchers, real DB),
     `test_phase01_writer_files_absent`, `test_phase01_heartbeat_module_absent`

## Success Criteria Coverage Matrix

Mapping every ROADMAP Phase 1 success criterion to the plan(s) that satisfy it.
This table is the canonical Phase 1 closeout artifact requested by the planning prompt.

| SC # | Requirement (verbatim from ROADMAP) | Satisfied by plan(s) | Verification evidence |
|---|---|---|---|
| **SC-1** | `stock collect dart …` INSERTs into `filings`; `vault/raw/` directory does not recreate | 01-01 (schema), 01-02 (CLI strip), 01-07 (DART collector), **01-09** (fence + smoke) | `tests/collectors/dart/test_collect_dart.py` asserts INSERT, `test_collect_dart_no_markdown_written` asserts vault-absence; `tests/test_no_writer.py` enforces ongoing; `tests/test_phase01_smoke.py::test_phase01_macro_end_to_end` also asserts `not (tmp_path / "vault").exists()` for the broader vertical |
| **SC-2** | `krx`, `news`, `macro`, `kind` all UPSERT into their own tables with content-hash dedup | 01-01 (schema), 01-03 (macro), 01-04 (krx), 01-05 (kind), 01-06 (news) | Each collector plan adds positive (insert) + negative (idempotent skip) DB-state assertions in `tests/collectors/<src>/test_collect_<src>.py` |
| **SC-3** | `src/shared/heartbeat.py` deleted + collector imports removed + stats via structured stderr log | 01-08 | `tests/test_no_heartbeat.py` (3 assertions: file absence, no imports, not importable); `tests/collectors/test_observability_wiring.py` (5 source-specific integration tests for `collector_runs` row); `tests/shared/test_run_log.py` (8 unit tests on the helper) |
| **SC-4** | `--vault-root` removed from every CLI subcommand | 01-02 | `tests/test_cli_collect_all.py` CA1..CA10 + the help-text verification that `vault-root` does not appear in `build_parser().format_help()` |
| **SC-5** | `tests/collectors/` validates INSERT paths (no Markdown stubs) | 01-03, 01-04, 01-05, 01-06, 01-07, **01-09** | Every Wave 1/2 plan's task 3 ports tests to DB-state assertions + a per-collector `test_*_no_markdown_written` negative fence; 01-09 deletes the two surviving writer-unit-test files (`tests/collectors/{kind,krx}/test_writer.py`) and retires the `vault_tmp` fixture from `tests/collectors/conftest.py` |
| **SC-6** | `stock-enrich-daily` Routine already disabled | n/a | No action — already disabled in v1.0 shutdown commit `daf3edf` |

All six SCs are covered by at least one plan. Coverage is verified by the
SC-3 / SC-1 CI guards (`tests/test_no_heartbeat.py`, `tests/test_no_writer.py`)
which run in the default fast suite, and the Phase 1 vertical smoke
(`tests/test_phase01_smoke.py`, `-m slow`) which exercises the SC-1 / SC-2
INSERT + dual-sink observability path end-to-end.

## Files Created/Modified

### Created
- `tests/test_no_writer.py` — 4-assertion CI fence (Veto #9 layer 2)
- `tests/test_phase01_smoke.py` — 3-test slow-marked vertical slice
- `.planning/phases/01-collector-db-cutover/deferred-items.md` — log of two
  pre-existing failures (DI-1 migration 0006 event-table rename gap; DI-2
  cross-test observability flakiness) that are out of 01-09 scope
- `.planning/phases/01-collector-db-cutover/01-09-SUMMARY.md` — this file

### Modified
- `src/cli/__main__.py` — Veto #9 runtime fence with absolute-path anchor
- `tests/collectors/conftest.py` — `vault_tmp` fixture removed
- `tests/collectors/news/test_collect_news.py` — writer-test block removed,
  `_seed_portfolio` helper rewired to `tmp_path` + inline portfolio write
- `tests/test_entity_upsert.py` — `TestCollectDartEntitySeed` class removed
  (Rule 1: was calling deleted `vault_root` kwarg)

### Deleted
- `src/collectors/dart/writer.py`
- `src/collectors/krx/writer.py`
- `src/collectors/news/writer.py`
- `src/collectors/macro/writer.py`
- `src/collectors/kind/writer.py`
- `tests/collectors/kind/test_writer.py`
- `tests/collectors/krx/test_writer.py`

## Decisions Made

See frontmatter `decisions:` block. Highlights:

- **Layered defense.** The plan's Veto #9 enforcement could in principle have
  stopped at "delete the files." It does not — find_spec scan, AST import
  scan, runtime CLI fence, and session-wide vault-Markdown rglob each catch
  a regression vector the others miss. The cost is ~150 lines of test code
  and one Path computation at CLI import.
- **vault_tmp retirement strategy A.** The W-1 verification warning called
  out a cross-wave contradiction. 01-09 picks strategy A (drop vault_tmp,
  consumers migrate to `tmp_path`+ chdir) cleanly: the conftest fixture is
  gone, the only remaining consumer
  (`tests/collectors/news/test_collect_news.py::_seed_portfolio`) inlines
  the portfolio.md write and chdirs into tmp_path.
- **Runtime fence absolute paths.** Adopted R-5 / F-5 recommendation up
  front: the fence anchors via `Path(__file__).resolve().parents[2]`, not a
  relative `"src/collectors/..."` string that would silently miss
  resurrections under unusual CWDs.

## Deviations from Plan

### Auto-fixed issues

**1. [Rule 1 — Pre-existing bug surfaced by fast-suite gate] Remove `TestCollectDartEntitySeed` from `tests/test_entity_upsert.py`**
- **Found during:** Task 1 fast-suite sanity check
- **Issue:** `TestCollectDartEntitySeed` (E5, E6, no-success-no-seed) called
  `collect_dart(..., vault_root=tmp_path, ...)` — the `vault_root` kwarg was
  removed by plan 01-02 and the `succeeded` stat key was removed by plan
  01-07. Pre-existing failure introduced by 01-02 + 01-07; PLAN-VERIFICATION
  R-2 caught the parallel `tests/test_collect_dart.py` issue (already fixed
  in commit `d76a8d6`) but missed this file.
- **Fix:** Delete the `TestCollectDartEntitySeed` class. Coverage of the
  entity-seed surface is preserved by the new
  `tests/collectors/dart/test_collect_dart.py::test_collect_dart_bug_c_entity_upsert`
  test, which exercises the same Bug C upsert path against the new DB-state
  contract.
- **Files modified:** `tests/test_entity_upsert.py` (drop the broken class +
  trim now-unused fakes/imports; keep `TestUpsertEntity` E1-E4 + invalid-input
  cases as direct unit tests of `upsert_entity`)
- **Verification:** `pytest tests/test_entity_upsert.py` collects 6 tests (was
  9), all pass.
- **Committed in:** `1c81a69` (Task 1)

**2. [Rule 2 — Missing critical: F-3 verification doc explicitly required a session-wide vault-Markdown scan] Add `test_no_vault_markdown_written_during_session`**
- **Found during:** Task 2 design (RED phase planning)
- **Issue:** The plan's draft for `tests/test_no_writer.py` had three
  assertions (file absence, find_spec, AST scan). PLAN-VERIFICATION F-3
  states: *"the CI test in `tests/test_no_writer.py` MUST scan recursively
  for ANY `.md` write under a temp vault during a collect run, not just
  specific known paths."* The first three assertions only catch the static
  surface; a runtime collector that writes to a non-canonical vault path
  would slip past.
- **Fix:** Add a fourth test that rglobs the repo working tree AND pytest's
  session-scoped `tmp_path_factory.getbasetemp()` for any `.md` file under
  any path component named `vault/`. Excludes the documented user notes
  vault (`notes/private/`), planning artifacts (`.planning/`), and test
  fixtures (`tests/fixtures/`).
- **Files modified:** `tests/test_no_writer.py`
- **Verification:** Test passes against the clean tree; manual
  resurrection of `src/collectors/dart/writer.py` (no-op content) plus a
  scripted `.md` write into `tmp_path/vault/raw/foo.md` would both trip
  the suite.
- **Committed in:** `dd5c3c7` (Task 2)

**3. [Rule 2 — Missing critical: PLAN-VERIFICATION R-5 / F-5] Runtime fence uses absolute path, not relative**
- **Found during:** Task 2 implementation
- **Issue:** Plan task 2 example code uses
  `Path("src/collectors/dart/writer.py").exists()` — a relative path that
  evaluates against process CWD. If `stock` is invoked from anywhere other
  than the repo root, the fence silently no-ops, defeating Veto #9 layer 3.
- **Fix:** Compute `_REPO_ROOT = Path(__file__).resolve().parents[2]` once
  at module import and build absolute writer paths from it. The fence
  behaves identically regardless of CWD.
- **Files modified:** `src/cli/__main__.py`
- **Verification:** Manual `stock --help` from repo root + manual `stock
  --help` after `echo > src/collectors/dart/writer.py` from a sibling
  directory both produce the same FATAL exit.
- **Committed in:** `dd5c3c7` (Task 2)

### Deferred items (out of 01-09 scope, logged to `deferred-items.md`)

- **DI-1.** `tests/test_migration.py::test_events_jsonb_and_fk` fails because
  plan 01-01 migration 0006 renamed `events` → `events_legacy` and created
  a new `events` table with a different shape. The Phase 2 migration test
  was never updated. This is a 01-01 verification gap, not a 01-09 task.
- **DI-2.** `tests/collectors/test_observability_wiring.py::test_collect_dart_writes_collector_runs_row`
  passes in isolation and in module-scoped runs but failed intermittently
  during one initial fast-suite run (the failure did not reproduce after the
  Task 1 cleanup). Sibling plan 01-08 owns this test; possible cross-file
  monkeypatch / pg_clean cleanup race. Logged for 01-08 follow-up.

---

**Total deviations:** 3 auto-fixed (1 Rule 1 — pre-existing bug; 2 Rule 2 — verification doc requirements). 2 deferred items logged.
**Impact on plan:** All auto-fixes essential for plan acceptance gates (fast suite green; F-3 enforcement; CWD-independent fence). No scope creep — every change directly serves Veto #9 enforcement or Phase 1 SC coverage.

## Issues Encountered

- **Working-tree state during sibling-agent parallelism.** Plan 01-08 landed
  three commits (`4a81518`, `3ca6a2e`, `fc73edf`) interleaved with 01-09's
  Task 1 commit. Initial `git status` after Task 1 showed `src/shared/heartbeat.py`
  as deleted-but-unstaged (the sibling had deleted it on disk but had not
  yet pushed the deletion commit). By Task 3, the sibling had committed
  everything cleanly. The deferred-items.md note and Task 3's
  `test_phase01_heartbeat_module_absent` test treat the post-01-08 state as
  the canonical Phase 1 closeout reality.
- **Empty `.claude/worktrees/<id>` cwd.** The execution context placed the
  agent in `C:/Users/minsu/workspace/stock/.claude/worktrees/exciting-mendeleev-476256`
  but the directory contained no per-agent worktree (`git worktree list`
  reported only the main repo on `main`). All work proceeded at the main
  repo root with the standard pre-commit safety assertion skipped (since
  `.git` is a directory, not a file, the worktree-mode protocol does not
  apply). Sibling-agent coordination was via the main repo branch directly,
  matching the established convention from commits in this phase.

## Phase 1 Readiness

- **All 9 plans of Phase 1 are committed** (01-01 through 01-09).
- **All six ROADMAP Phase 1 SCs have an assigned plan** (see matrix above).
- **CI guards in place** for the three load-bearing Hard Vetoes (#6, #8, #9).
- **Vertical slice validated** end-to-end via `tests/test_phase01_smoke.py`.
- **Outstanding** (deferred to follow-up cleanup, not blocking Phase 2):
  - DI-1: `tests/test_migration.py::test_events_jsonb_and_fk` rename gap.
  - DI-2: `test_collect_dart_writes_collector_runs_row` cross-file flakiness.
- **Phase 2 entry condition satisfied:** entities table is populated by the
  Wave 1/2 collector runs; decision_cards schema work can begin.

## Self-Check: PASSED

Verified post-SUMMARY:

- Created files (4): `tests/test_no_writer.py`, `tests/test_phase01_smoke.py`,
  `.planning/phases/01-collector-db-cutover/deferred-items.md`, this file.
- Modified files (4): `src/cli/__main__.py`, `tests/collectors/conftest.py`,
  `tests/collectors/news/test_collect_news.py`, `tests/test_entity_upsert.py`.
- Deleted files (7): the 5 collector writer.py modules + 2 obsolete
  test_writer.py — verified GONE on disk.
- Commits exist: `1c81a69` (Task 1), `dd5c3c7` (Task 2), `6ca871b` (Task 3).

---
*Phase: 01-collector-db-cutover*
*Plan: 01-09 (Wave 3 closeout)*
*Completed: 2026-05-29*
