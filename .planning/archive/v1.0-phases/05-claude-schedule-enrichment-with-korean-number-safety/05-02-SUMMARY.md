---
phase: 05-claude-schedule-enrichment-with-korean-number-safety
plan: 02
subsystem: shared-util
tags: [numbers, units, krw, pure-function]

requires:
  - phase: 05-claude-schedule-enrichment-with-korean-number-safety
    plan: 01
    provides: NumericFact.unit Literal (KRW원/KRW백만/KRW억/KRW조/USD/EUR/JPY/pct/bps/multiplier/shares/days/other)
provides:
  - "shared.units.normalize_to_krw(value, unit) -> float | None"
  - "shared.units.KRW_MULTIPLIERS frozen Mapping"
affects:
  - 05-04-number_sanity (will call normalize_to_krw when validating KRW-family facts)
  - 05-08-routines-skill (post-LLM validation step fills NumericFact.value_krw via this util)

tech-stack:
  added: []
  patterns:
    - "Leaf pure-function module (no imports from shared.frontmatter) — avoids circular dep"
    - "MappingProxyType for compile-time-style frozen constants"
    - "Defensive .get() on Literal-narrowed str input — graceful None, never KeyError"

key-files:
  created:
    - src/shared/units.py
    - tests/test_units.py
  modified: []

key-decisions:
  - "No FX conversion: USD/EUR/JPY explicitly return None rather than looking up a rate — prevents silent fabrication of KRW amounts"
  - "MappingProxyType over frozen dict or tuple-pair: idiomatic, testable for mutation rejection, cheaper than Enum for this use case"
  - "float(value) cast inside function guards int inputs and preserves negatives (예: 손실 -5e8)"

patterns-established:
  - "Leaf util module pattern for shared/: no project-internal imports, pure function only"
  - "TDD RED commit → GREEN commit ordering, confirmed by pre-commit ruff auto-fixes between them"

requirements-completed: [INGEST-07]

duration: ~29min
completed: 2026-04-24
---

# Phase 05 Plan 02: KRW Normalization Utility Summary

**`shared.units.normalize_to_krw` — pure function that maps KRW-family (원/백만/억/조) units to won-scale floats and explicitly returns None for non-KRW units, ready for the Routines skill post-LLM validation step.**

## Performance

- **Duration:** ~29 min (mostly waiting on ruff auto-fix → re-stage → pre-commit retries)
- **Started:** 2026-04-24T15:42:27Z
- **Completed:** 2026-04-24T16:11:56Z (approx)
- **Tasks:** 2
- **Files created:** 2 (`src/shared/units.py`, `tests/test_units.py`)

## Accomplishments

- `KRW_MULTIPLIERS` exposed as `MappingProxyType` with exactly the 4 Literal KRW units from `NumericFact.unit`
- `normalize_to_krw(value, unit) -> float | None` — pure, deterministic, LLM-free
- 5 test functions, 18 parametrized assertions covering:
  - 6 KRW multiplier cases (원/백만/억/조 + zero + negative)
  - 9 non-KRW returning None (USD/EUR/JPY/pct/bps/multiplier/shares/days/other)
  - Defensive unknown str and empty str → None
  - `MappingProxyType` mutation rejection
  - Exact 4-key coverage of KRW_MULTIPLIERS
- Zero imports from `shared.frontmatter` or `ingest.*` (leaf-util constraint satisfied)
- File size 40 LOC < 60 LOC budget

## Task Commits

Two atomic TDD commits:

1. **Task 2 (tests written first, RED)** — `e312c7c` (test)
2. **Task 1 (implementation, GREEN)** — `15ee537` (feat)

## Files Created/Modified

- `src/shared/units.py` — new leaf utility, `KRW_MULTIPLIERS` + `normalize_to_krw`
- `tests/test_units.py` — 18 assertions across 5 test functions

## Decisions Made

- **No FX conversion inside the utility.** USD/EUR/JPY deliberately return None so the Routines skill records `value_krw=null` — the downstream sanity check will then skip KRW range checks for those facts instead of inventing a rate.
- **MappingProxyType over Enum/frozenset-pair.** Cheap, idiomatic for a 4-entry lookup table, testable for immutability without extra boilerplate.
- **TDD RED→GREEN ordering enforced.** Plan listed T1 (impl) before T2 (tests), but T1's verify depended on T2's test file — writing the tests first makes RED/GREEN commits clean.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `--extra dev` flag in plan verify commands not defined as a pyproject optional-dependency group**
- **Found during:** Running plan acceptance command `uv run --extra dev pytest ...`
- **Issue:** Same pattern as Plan 05-01 (already documented in 05-01 deviations) — `dev` group not declared. Plan 05-01 confirmed that default `uv run pytest ...` resolves dev deps.
- **Fix:** Used `uv run pytest tests/test_units.py -x -q` directly. 18 passed.
- **Files modified:** None (command-line deviation)
- **Committed in:** N/A

**2. [Rule 1 - Bug] Pre-commit ruff auto-fix of `typing.Mapping` → `collections.abc.Mapping`**
- **Found during:** First `git commit` of Task 1 implementation
- **Issue:** Project's ruff config flags `from typing import Mapping` as `UP035` (deprecated import) and auto-fixes to `from collections.abc import Mapping`.
- **Fix:** Accepted ruff's auto-fix (import source change only, same type), re-ran tests (18 passed), re-staged and committed.
- **Files modified:** `src/shared/units.py`
- **Verification:** `uv run pytest tests/test_units.py -x -q` → 18 passed
- **Committed in:** `15ee537` (GREEN commit absorbs the fix)

**3. [Rule 1 - Bug] Transient `.git/index.lock` race between TodoWrite-less sequential commits and background pre-commit stash**
- **Found during:** First attempt to commit the RED test file
- **Issue:** An earlier `git commit` left `.git/index.lock` present (pre-commit was mid-stash). `fatal: ... index.lock: 파일이 있습니다`.
- **Fix:** `rm -f .git/index.lock` and retry — the prior pre-commit had exited already.
- **Files modified:** None
- **Committed in:** N/A (cleared before commit succeeded)

---

**Total deviations:** 3 auto-fixed (2 bug / environmental, 1 blocking)
**Impact on plan:** Zero scope drift. All deviations are tooling-layer; behavior, shape, and test count exactly match the plan.

## Acceptance Criteria Verification

- `grep -q "def normalize_to_krw" src/shared/units.py` → **found**
- `grep -q "KRW_MULTIPLIERS" src/shared/units.py` → **found**
- `grep -q "MappingProxyType" src/shared/units.py` → **found**
- `uv run python -c "from shared.units import normalize_to_krw; assert normalize_to_krw(4.2, 'KRW조') == 4.2e12; assert normalize_to_krw(100, 'USD') is None"` → **exit 0**
- `uv run pytest tests/test_units.py -x -q` → **18 passed in 0.52s** (≥15 parametrized cases threshold)
- `grep -q "test_multipliers_frozen" tests/test_units.py` → **found**
- `wc -l src/shared/units.py` → **40** (< 60)

## Verification Results

- **Tests:** 18 passed, 0 failed (`tests/test_units.py`)
- **File size:** 40 LOC (plan budget < 60) 
- **Leaf purity:** `grep -E "from (shared\.frontmatter|ingest)" src/shared/units.py` → 0 matches
- **Python compile-import smoke:** `python -c "from shared.units import normalize_to_krw, KRW_MULTIPLIERS"` → success

## Threat Model Check

Threat register dispositions satisfied:
- **T-05-02-01 (Tampering — unknown unit):** `.get(unit)` returns None for bogus strings — verified by `test_unknown_unit_returns_none`
- **T-05-02-02 (Integrity — phantom FX):** USD/EUR/JPY → None verified by `test_non_krw_returns_none` parametrized cases
- **T-05-02-03 (Tampering — frozen multipliers):** `MappingProxyType` blocks mutation — verified by `test_multipliers_frozen`

No new threat surface beyond the plan.

## Next Phase Readiness

- Wave 2 downstream plans (05-04 sanity, 05-08 Routines skill) can `from shared.units import normalize_to_krw` without further setup.
- Frozen surface: KRW_MULTIPLIERS keys exactly match `NumericFact.unit` Literal KRW prefix — any future addition (e.g., "KRW천") would require coordinated change in `frontmatter.NumericFact` + `units.KRW_MULTIPLIERS`.

## Self-Check: PASSED

- `src/shared/units.py` exists with `normalize_to_krw` + `KRW_MULTIPLIERS` — FOUND
- `tests/test_units.py` exists with 5 `def test_` functions → 18 assertions — FOUND
- Commit `e312c7c` (RED test) — FOUND in `git log`
- Commit `15ee537` (GREEN impl) — FOUND in `git log`
- `pytest tests/test_units.py` → 18 passed

---
*Phase: 05-claude-schedule-enrichment-with-korean-number-safety*
*Completed: 2026-04-24*
