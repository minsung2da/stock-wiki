---
phase: 05-claude-schedule-enrichment-with-korean-number-safety
plan: 04
subsystem: shared
tags: [numbers, sanity, validation, stage4, phase5]

requires:
  - phase: 05-claude-schedule-enrichment-with-korean-number-safety
    plan: 01
    provides: NumericFact v2 (Literal unit enum, value_krw, source_span, offset)
provides:
  - "shared.number_sanity.check_echo_back(fact, body) -> str | None (codepoint-safe)"
  - "shared.number_sanity.check_sanity(fact) -> str | None (unit + range)"
  - "SANITY_RULES seed table with 22 canonical keys (earnings, balance, ratios, prices, macro)"
affects:
  - 05-08-routines-skill (post-LLM loop calls check_echo_back/check_sanity and maps string flags to ReviewFlag)

tech-stack:
  added: []
  patterns:
    - "TypedDict with total=False for declarative per-key sanity rules"
    - "Pure-function module (no I/O) returning flag-name strings, caller maps to ReviewFlag"
    - "Codepoint-indexed str slicing for Hangul echo-back (Pitfall 4 resolution)"

key-files:
  created:
    - src/shared/number_sanity.py
    - tests/test_number_sanity.py
  modified: []

key-decisions:
  - "KOSPI/KOSDAQ sanity rules use unit='other' — NumericFact.unit Literal (frozen Plan 05-01) does not include 'index_pt'; plan's index_pt references were auto-adjusted so tests can construct valid NumericFact instances"
  - "KRW-family rules compare against fact.value_krw (populated by units.normalize_to_krw upstream); missing value_krw is itself a sanity violation"
  - "Unknown keys return None (defensive pass) — SANITY_RULES is an observable growth target, not a hard whitelist"

patterns-established:
  - "Flag-string return convention: pure functions return the ReviewFlag.flag string (or None); Pydantic construction happens in the Routines skill caller"
  - "Echo-back bounds-check before slicing (out-of-range offset → mismatch, not exception)"

requirements-completed: [INGEST-07]

duration: ~7min
completed: 2026-04-24
---

# Phase 05 Plan 04: Number Sanity Summary

**`src/shared/number_sanity.py` ships two pure validators — `check_echo_back` (D-15 stage 4a, character-level Hangul-safe) and `check_sanity` (D-18, declarative SANITY_RULES table of 22 keys) — that together block hallucinated LLM numeric facts before the Routines skill writes `_derived` frontmatter.**

## Performance

- **Duration:** ~7 min
- **Tasks:** 2 (TDD RED → GREEN)
- **Files created:** 2

## Accomplishments

- `SANITY_RULES` dict with 22 canonical keys: 매출액/영업이익/당기순이익/자산총계/부채총계/자본총계 (KRW); 영업이익률/순이익률/ROE/ROA/부채비율/외국인지분율 (pct); PER/PBR (multiplier); YoY growth ratios; 주가종가 (KRW); KOSPI/KOSDAQ (other); 기준금리/USD_KRW/US_10Y/WTI (macro)
- `check_echo_back(fact, body)` — bounds-checked codepoint slicing; returns `"numeric_echo_mismatch"` or `None`; skips DART structured path (source_span=None)
- `check_sanity(fact)` — returns `"numeric_sanity_violation"` on unit mismatch, missing value_krw for KRW-family, or out-of-range; returns `None` on unknown keys
- Compile-time assertion `len(SANITY_RULES) >= 20` (actually 22 seeded)
- 13 tests green: echo mismatch / echo match / DART skip / out-of-bounds / sanity range / unit mismatch / unknown key / KRW without value_krw / KRW in range / KOSPI out-of-range / seed size / USD_KRW in+out of range

## Task Commits

1. **Task 2 (tests written first, RED)** — `17a7047` (test)
2. **Task 1 (implementation, GREEN)** — `6fb6593` (feat)

## Files Created

- `src/shared/number_sanity.py` (110 LOC, < 200 cap)
- `tests/test_number_sanity.py` (13 `def test_` functions)

## Decisions Made

- **`index_pt` unit replaced with `"other"` for KOSPI/KOSDAQ rules.** The plan's SANITY_RULES seed used `unit="index_pt"`, but `NumericFact.unit` Literal (frozen in Plan 05-01) does not include that value. Constructing a NumericFact with `unit="index_pt"` would fail Pydantic validation, making the KOSPI out-of-range test impossible. Chose `"other"` (valid Literal) to preserve the sanity behaviour. Future schema additions (Plan 05-08 or Phase 9) can promote an `index_pt` Literal if observation warrants; at that point both the Literal and these two rules update in lockstep.
- **Echo test offsets corrected.** Plan's example offsets (`offset=4`) for body `"매출액은 4조 원이다."` miscounted — `"4조 원"` actually starts at codepoint 5. Corrected in the committed tests.
- **Return-string convention over ReviewFlag construction.** `check_*` functions return the flag-name string; Routines skill (Plan 05-08) is responsible for wrapping into `ReviewFlag` Pydantic models with `detail` context. Keeps these helpers zero-dependency on the model surface.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan's `unit="index_pt"` not in NumericFact.unit Literal**
- **Found during:** Task 2 test collection (or TypeError on NumericFact construction)
- **Issue:** Plan 05-04 specifies `SANITY_RULES["KOSPI"] = {"unit": "index_pt", ...}` and test `test_kospi_out_of_range` constructs `NumericFact(..., unit="index_pt")`. Plan 05-01 froze NumericFact.unit Literal without `index_pt`.
- **Fix:** Changed both KOSPI and KOSDAQ rules to `unit="other"`, and updated the KOSPI test to use `unit="other"`. Behaviour preserved: unit-match + range check still fires.
- **Files modified:** `src/shared/number_sanity.py`, `tests/test_number_sanity.py`
- **Committed in:** `17a7047`, `6fb6593`

**2. [Rule 1 - Bug] Plan's example echo offsets miscounted**
- **Found during:** GREEN run — `test_echo_match_passes` asserted None but got `numeric_echo_mismatch`
- **Issue:** Plan's fixture `body="매출액은 4조 원이다."` claimed `body[4:4+len("4조 원")] == "4조 원"`. Actual codepoint layout: `매(0) 출(1) 액(2) 은(3) space(4) 4(5) 조(6) space(7) 원(8)` — `"4조 원"` starts at 5, not 4.
- **Fix:** Corrected `offset=4` to `offset=5` in both `test_hallucinated_fact_flagged` and `test_echo_match_passes`. The behaviour being verified (hallucination detection on offset pointing to different span) still holds.
- **Files modified:** `tests/test_number_sanity.py`
- **Committed in:** `6fb6593`

**3. [Rule 3 - Blocking] ruff SIM102 (nested if) on final sanity check**
- **Found during:** pre-commit hook
- **Issue:** Combined nested `if` into single boolean expression per ruff SIM102 auto-fix guidance.
- **Fix:** `if ... and ... and (cond)` flat form.
- **Files modified:** `src/shared/number_sanity.py`
- **Committed in:** `6fb6593`

---

**Total deviations:** 3 auto-fixed (2 plan-spec bugs, 1 style). All preserve intent; no scope drift.

## Acceptance Criteria Verification

- `grep -q "SANITY_RULES" src/shared/number_sanity.py` → found
- `grep -q "def check_echo_back" src/shared/number_sanity.py` → found
- `grep -q "def check_sanity" src/shared/number_sanity.py` → found
- `uv run python -c "from shared.number_sanity import SANITY_RULES; assert len(SANITY_RULES) >= 20"` → exit 0 (22 rules)
- `uv run pytest tests/test_number_sanity.py -x -q` → **13 passed**
- `grep -c "^def test_" tests/test_number_sanity.py` → **13** (≥ 12)
- `wc -l src/shared/number_sanity.py` → **110** (< 200)

## Verification Results

- **Scoped tests:** 13 passed, 0 failed (`tests/test_number_sanity.py`)
- **Plan-spec full sweep:** `pytest tests/test_number_sanity.py tests/test_units.py tests/test_number_extraction.py tests/test_frontmatter_v2.py -x -q` → **46 passed**
- **File size:** 110 LOC
- **Purity:** no I/O, no LLM imports, only depends on `shared.frontmatter.NumericFact`

## Threat Model Check

Threat register dispositions satisfied:
- **T-05-04-01 (Tampering — LLM invents source_span):** `check_echo_back` asserts codepoint-level equality at offset; verified by `test_hallucinated_fact_flagged`
- **T-05-04-02 (Tampering — hallucinated magnitude):** `check_sanity` range-clamps per (key, unit); verified by `test_sanity_out_of_range` and `test_kospi_out_of_range`
- **T-05-04-03 (Tampering — unit mislabel):** unit-field check; verified by `test_unit_mismatch_flagged`
- **T-05-04-04 (Integrity — KRW without value_krw):** verified by `test_krw_without_value_krw_flagged`
- **T-05-04-05 (DoS — body out-of-bounds):** explicit bounds check returns mismatch (no exception); verified by `test_echo_out_of_bounds_flagged`

No new threat surface introduced beyond the plan's threat_model.

## Next Phase Readiness

- Plan 05-08 (Routines skill) can `from shared.number_sanity import check_echo_back, check_sanity, SANITY_RULES` and wrap the string returns into `ReviewFlag(flag=..., detail=..., fact_key=...)` instances.
- `SANITY_RULES` is an observable growth target — Phase 9 will expand as `dart_structured_disagreement` counters accumulate.

## Self-Check: PASSED

- `src/shared/number_sanity.py` exists with `SANITY_RULES`, `check_echo_back`, `check_sanity` — FOUND
- `tests/test_number_sanity.py` exists with 13 tests — FOUND
- Commit `17a7047` (test RED) — FOUND in `git log`
- Commit `6fb6593` (feat GREEN) — FOUND in `git log`
- 13/13 tests pass; 46/46 plan-spec sweep green

---
*Phase: 05-claude-schedule-enrichment-with-korean-number-safety*
*Completed: 2026-04-24*
