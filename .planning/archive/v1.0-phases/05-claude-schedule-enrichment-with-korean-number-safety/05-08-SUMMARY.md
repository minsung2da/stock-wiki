---
phase: 05-claude-schedule-enrichment-with-korean-number-safety
plan: 08
subsystem: routines-skill
tags: [routines, skill, agent, claude-code, enrichment]

requires:
  - phase: 05-claude-schedule-enrichment-with-korean-number-safety
    plans: [05-01, 05-02, 05-03, 05-04, 05-05, 05-06, 05-07]
    provides: DerivedBlock v2 + number_extraction + number_sanity + dart_financials + backlog + heartbeat + injection_defense
provides:
  - ".claude/routines/enrich/ Routines skill tree (SKILL.md + 4 prompts + 3 helpers + README)"
  - "facts_equal() D-16 self-consistency reference impl"
  - "find_candidates() D-19/D-21 vault scan + stick-on-failure filter"
  - "compute_zone_hash()/assert_zones_unchanged() D-07 zone-integrity guard"
  - "Operator runbook covering PAT/routine/auto-merge/branch-protection"
affects:
  - ROADMAP Phase 5 Success Criteria #1 (deploy-gated by operator following README)
  - ROADMAP Phase 5 Success Criteria #2 (zone-integrity enforced)
  - ROADMAP Phase 5 Success Criteria #4 (4-stage pipeline wired in SKILL.md)
  - ROADMAP Phase 5 Success Criteria #5 (content_hash idempotency via walk)

tech-stack:
  added: []
  patterns:
    - "Skill-as-prompt lives in-repo (D-29) — fresh Routines container clones repo + sees SKILL.md"
    - "Python helpers loaded via importlib.util spec_from_file_location — tests reach into .claude/ from tests/"
    - "Zone-hash SHA256 over yaml.safe_dump(provenance) + yaml.safe_dump(ingest_state) — deterministic across Python/libyaml version drift"

key-files:
  created:
    - .claude/routines/enrich/SKILL.md
    - .claude/routines/enrich/README.md
    - .claude/routines/enrich/prompts/derived_dart_b.md
    - .claude/routines/enrich/prompts/derived_news.md
    - .claude/routines/enrich/prompts/derived_kind.md
    - .claude/routines/enrich/prompts/derived_macro.md
    - .claude/routines/enrich/helpers/__init__.py
    - .claude/routines/enrich/helpers/facts_equal.py
    - .claude/routines/enrich/helpers/walk.py
    - .claude/routines/enrich/helpers/zone_integrity.py
    - tests/test_facts_equal.py
    - tests/test_enrich_walk.py
    - tests/test_zone_integrity.py
    - tests/test_skill_structure.py
  modified: []

key-decisions:
  - "Plan test for numeric_fact_rounding_tolerance used values that don't actually round to same 4 decimals (1.23456789/1.23454321 → 1.2346/1.2345). Fixed test value to 1.23456321 so both round to 1.2346 — preserved the test intent"
  - "helpers/__init__.py docstring originally read 'no anthropic/openai imports' which the acceptance-criterion grep for 'anthropic' would falsely flag. Rewrote to 'no LLM-SDK imports (COLL-07 spirit)' so the grep guard isolates actual imports"
  - "Structure-test imports use `# noqa: E402` on post-importlib imports from shared.frontmatter — required because the helper path loader runs before the main test imports"

patterns-established:
  - "Skill helpers testable from tests/ via importlib.util without adding .claude/ to pythonpath — keeps COLL-07 scope crisp"
  - "Structure tests validate terminology (character-level not byte-level) + presence of D-13 sentiment=null directives in KIND/macro prompts"

requirements-completed: [INGEST-02, INGEST-03, INGEST-04, INGEST-05, INGEST-07]

metrics:
  duration: ~22min
  started: 2026-04-24T15:15:59Z
  completed: 2026-04-24T15:37:30Z
  tasks: 2
  files: 14
  test_count: 30

completed: 2026-04-24
---

# Phase 05 Plan 08: Routines Skill Summary

**`.claude/routines/enrich/` Routines skill tree delivered — SKILL.md prompt + 4 source-specific sub-prompts (dart_b/news/kind/macro) + 3 Python helpers (facts_equal/walk/zone_integrity) + README operator runbook — fully testable without live Routines execution.**

## Performance

- **Duration:** ~22 min
- **Started:** 2026-04-24T15:15:59Z
- **Completed:** 2026-04-24T15:37:30Z
- **Tasks:** 2 (both TDD RED→GREEN)
- **Files created:** 14 (10 skill tree + 4 test files)

## Accomplishments

- **Task 1** — 3 Python helpers + 3 test files (19 tests):
  - `facts_equal.py` — D-16 self-consistency: tuple-set equality on tickers/event_type/catalysts/sentiment.label + round(value,4) numeric facts; ignores summary/rationale/source_span
  - `walk.py` — D-19 idempotency (skip populated + stable hash) + D-21 F-4c (skip_reason sticky); returns `Candidate(path, source, content_hash, reason)`
  - `zone_integrity.py` — D-07 SHA256 over yaml.safe_dump(provenance) + yaml.safe_dump(ingest_state); `assert_zones_unchanged` raises `ZoneViolationError`

- **Task 2** — SKILL.md + 4 prompts + README + 11 structure tests:
  - `SKILL.md` — 16-step per-document loop (read → stash zone → oversize → injection → DART branch → regex candidates → prompt → wrap → LLM×2 → facts_equal → Pydantic → numeric validation → value_krw+sentiment → zone assert → write), plus Pre-flight / Post-loop / Git commit+PR / Failure handling
  - `prompts/derived_dart_b.md` — outcome-scope sentiment, event_type from DART 주요사항 vocabulary
  - `prompts/derived_news.md` — tone_or_outcome scope, character-level echo-back required
  - `prompts/derived_kind.md` — sentiment MUST be null (D-13)
  - `prompts/derived_macro.md` — empty tickers, sentiment MUST be null
  - `README.md` — fine-grained PAT + Contents:RW + Pull requests:RW, routine creation steps, 22:00 UTC schedule, GitHub auto-merge enable, branch protection, failure response table, rotation calendar

## Task Commits

1. **RED Task 1 tests** — `8e7f596` (test)
2. **GREEN Task 1 helpers** — `6a4ca55` (feat)
3. **RED Task 2 structure tests** — `91e5201` (test)
4. **GREEN Task 2 skill + prompts + README** — `4f949f2` (feat)

## Decisions Made

- **Fixed bad test values in plan's rounding test** — plan specified `1.23456789` and `1.23454321` as "round(_, 4) identical" but they round to 1.2346 and 1.2345 respectively. Adjusted the second value to `1.23456321` so both round to 1.2346 as the test intended.
- **Renamed `no anthropic/openai imports` docstring** in `helpers/__init__.py` to avoid tripping the acceptance-criterion grep guard for literal `anthropic`/`openai` strings. Retained COLL-07 spirit via `# no LLM-SDK imports (COLL-07 spirit)`.
- **`# noqa: E402`** on post-importlib imports — required pattern for test files that must load helper modules via `importlib.util.spec_from_file_location` before importing their own dependencies; ruff E402 otherwise blocks the commit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan test values for `test_numeric_fact_rounding_tolerance` don't actually round to same 4-decimal value**
- **Found during:** Task 1 GREEN run
- **Issue:** Plan spec used `1.23456789` vs `1.23454321`. `round(1.23456789, 4) == 1.2346`; `round(1.23454321, 4) == 1.2345`. facts_equal correctly reported them inequal, but the test asserted equal.
- **Fix:** Changed second value to `1.23456321` — both now round to `1.2346`, matching the test's stated intent ("diff in 5th decimal").
- **Files modified:** `tests/test_facts_equal.py`
- **Commit:** `6a4ca55` (part of GREEN commit)

**2. [Rule 3 - Blocking] `uv run --extra dev` fails because `dev` is not a declared extra in pyproject.toml**
- **Found during:** Running plan's exact verify command
- **Issue:** Plan spec uses `uv run --extra dev pytest ...` but dev dependencies are in `[dependency-groups]`, not `[project.optional-dependencies]`.
- **Fix:** Used `uv run pytest ...` directly (already resolved via default sync) — same resolution as Plan 05-01 documented.
- **Files modified:** None (command-level only)

**3. [Rule 2 - Critical] `__init__.py` docstring would falsely trigger acceptance `grep -q anthropic` guard**
- **Found during:** Running acceptance criteria greps
- **Issue:** Docstring contained literal substring `anthropic/openai` for documentation; acceptance criterion `grep -q "anthropic" helpers/*.py && exit 1` would treat the mention as a violation.
- **Fix:** Rewrote docstring to `"no LLM-SDK imports (COLL-07 spirit)"` — still documents the invariant, no false positives.
- **Files modified:** `.claude/routines/enrich/helpers/__init__.py`
- **Commit:** `6a4ca55`

**4. [Rule 3 - Blocking] Pre-commit ruff E402 on post-importlib imports in all 4 test files**
- **Found during:** First `git commit` of Task 1 RED tests
- **Issue:** Test files must load helper modules via `importlib.util.spec_from_file_location` before importing `shared.frontmatter` (because helper module import path depends on the spec load). Ruff E402 blocks module-level imports that are not at top-of-file.
- **Fix:** Added `# noqa: E402` on each late import line. Standard test pattern for `spec_from_file_location`-style dynamic loads.
- **Files modified:** `tests/test_facts_equal.py`, `tests/test_enrich_walk.py`, `tests/test_zone_integrity.py`
- **Commit:** `8e7f596`

**Total deviations:** 4 auto-fixed (1 bug, 1 blocking command, 1 critical guard-collision, 1 blocking lint). No architectural changes.

## Acceptance Criteria Verification

All evidence run fresh at 2026-04-24T15:36Z:

- `test -f .claude/routines/enrich/helpers/facts_equal.py` ✓
- `test -f .claude/routines/enrich/helpers/walk.py` ✓
- `test -f .claude/routines/enrich/helpers/zone_integrity.py` ✓
- `test -f .claude/routines/enrich/SKILL.md` ✓
- `test -f .claude/routines/enrich/README.md` ✓
- All 4 prompt files exist ✓
- `grep -c "character-level echo-back" SKILL.md` → **1**
- `grep -c "byte-level echo-back" SKILL.md` → **0** (correct)
- `grep -c "facts_equal" SKILL.md` → **2**
- `grep -c "auto-merge" SKILL.md` → **4**
- `grep -c "fine-grained PAT" README.md` → **2**
- `grep -c "Allow auto-merge" README.md` → **1**
- `uv run pytest tests/test_facts_equal.py tests/test_enrich_walk.py tests/test_zone_integrity.py tests/test_skill_structure.py -q` → **30 passed**
- COLL-07 guard (`grep -rl -E 'import anthropic|from anthropic|import openai|from openai' src/collectors src/ingest src/shared`) → no hits (verified by `test_src_guard_still_clean`)

## Threat Model Check

Threat register dispositions satisfied:
- **T-05-08-01** (prompt injection): SKILL.md step 4 invokes `detect_injection_patterns`; flag → skip_reason=review_required
- **T-05-08-02** (numeric hallucination): 4-stage pipeline wired in SKILL.md steps 6-14
- **T-05-08-03** (zone violation): `assert_zones_unchanged` in SKILL.md step 15; `zone_integrity.py` tested with 5 cases
- **T-05-08-04** (PAT leak): README mandates single-repo + Contents:RW + PR:RW + ≤90-day rotation
- **T-05-08-05** (force-push): README branch protection section enforces linear history
- **T-05-08-06** (oversize DoS): SKILL.md step 3 length check, 200K token cap, skip_reason="oversize"
- **T-05-08-07** (COLL-07 bypass): `test_helpers_no_llm_imports` + `test_src_guard_still_clean` re-assert guards
- **T-05-08-08** (flip-flop): `facts_equal` uses tuple-set equality (not strict string), tested with 9 cases

No new threat surface introduced.

## Next Phase Readiness

- **Phase 5 coding-gate complete.** All 8 plans shipped.
- **Post-deploy manual smoke (out-of-band):** operator executes README steps, clicks "Run now" in claude.ai/code/routines, verifies PR lands with `auto-merge` label and a non-empty `_derived` block on ≥1 document. Documented as phase-gate manual verification.
- **Phase 5 ROADMAP Success Criteria:** #1, #2, #4, #5 are now code-complete (gated on deploy); #3 (ingest pipeline ingests enriched frontmatter) was completed in Phases 3-4 and needs no changes from Plan 08.

## Self-Check: PASSED

- `.claude/routines/enrich/SKILL.md` — FOUND
- `.claude/routines/enrich/README.md` — FOUND
- `.claude/routines/enrich/prompts/derived_dart_b.md` — FOUND
- `.claude/routines/enrich/prompts/derived_news.md` — FOUND
- `.claude/routines/enrich/prompts/derived_kind.md` — FOUND
- `.claude/routines/enrich/prompts/derived_macro.md` — FOUND
- `.claude/routines/enrich/helpers/facts_equal.py` — FOUND
- `.claude/routines/enrich/helpers/walk.py` — FOUND
- `.claude/routines/enrich/helpers/zone_integrity.py` — FOUND
- `tests/test_facts_equal.py` — FOUND (9 tests)
- `tests/test_enrich_walk.py` — FOUND (5 tests)
- `tests/test_zone_integrity.py` — FOUND (5 tests)
- `tests/test_skill_structure.py` — FOUND (11 tests)
- Commit `8e7f596` (RED helpers tests) — FOUND in `git log`
- Commit `6a4ca55` (GREEN helpers) — FOUND in `git log`
- Commit `91e5201` (RED structure tests) — FOUND in `git log`
- Commit `4f949f2` (GREEN skill + prompts + README) — FOUND in `git log`
- 30/30 plan-specific tests pass

---
*Phase: 05-claude-schedule-enrichment-with-korean-number-safety*
*Completed: 2026-04-24*
