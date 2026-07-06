---
phase: 04-analysis-runner-3-role-debate
plan: 01
subsystem: analysis
tags: [decision-card, numeric-checksum, pydantic, pytest, ci-guard, korean-units]

# Dependency graph
requires:
  - phase: 02-decision-card-schema-storage
    provides: "DecisionCard contract (optional-payload-field precedent) + store payload round-trip"
  - phase: 01-collector-db-cutover
    provides: "shared/units.normalize_to_krw + shared/number_extraction.extract_numeric_candidates (v1.0 numeric primitives)"
provides:
  - "DecisionCard.warnings optional payload field (D-03 dropped-fact home; no DB column)"
  - "src/analysis/checksum.py — fact_supported + checksum_facts (Korean-unit value-equivalence, SC#3)"
  - "src/analysis/ package + tests/analysis/ base fixtures (seeded_engine, real_filing_body, card_oracle) — Wave 0 scaffold"
  - "CI import guard extended to src/analysis (Max-only Veto, D-01)"
  - "pytest 'live' marker (opt-in real claude CLI, deselect by default)"
affects: [04-02, 04-03, 04-04, 04-05, 04-06, phase-5-briefing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Reuse v1.0 numeric primitives (units + number_extraction) instead of re-implementing 억/조 parsing"
    - "Value-equivalence checksum (relative tol) over v1.0 exact at-offset echo-back"
    - "Optional payload field = no DB migration (warnings rides payload JSONB like invalidation_reason/status)"

key-files:
  created:
    - src/analysis/__init__.py
    - src/analysis/checksum.py
    - tests/analysis/__init__.py
    - tests/analysis/conftest.py
    - tests/analysis/test_checksum.py
  modified:
    - src/cards/models.py
    - tests/test_import_guard.py
    - pyproject.toml

key-decisions:
  - "warnings: list[str] added to DecisionCard as optional payload field (Field(default_factory=list)); NOT in _PAYLOAD_EXCLUDE so it persists in payload JSONB — zero DB migration, §3 round-trip unaffected"
  - "checksum reuses shared.units.normalize_to_krw + shared.number_extraction.extract_numeric_candidates; KRW-family → KRW원 canonical, all other units keep raw scalar; relative tolerance default 0.5% (Discretion #4, ASSUMED)"
  - "Deliberately skipped the OPTIONAL number_sanity.SANITY_RULES second gate — its keys are Korean financial line-items (매출액/영업이익률/…) that will not match the Judge's English fact keys, so it would be dead code (YAGNI)"
  - "checksum_facts preserves each value's int/float type when projecting to the stored dict[str, float|int] shape"

patterns-established:
  - "Pure-function checksum module (no LLM, no I/O) with a single relative-tolerance match loop"
  - "Per-directory conftest re-declares inherited-only fixtures (seeded_engine copied from mcp_v2/cards conftests)"

requirements-completed: ["SC#3"]

# Metrics
duration: ~12min
completed: 2026-07-06
---

# Phase 4 Plan 01: SC#3 Numeric Checksum + Analysis Package Scaffold Summary

**D-03 Korean-unit value-equivalence numeric checksum (drops any LLM-emitted number not derivable from source into DecisionCard.warnings) plus the src/analysis package, base test fixtures, CI cloud-LLM import guard, and the opt-in `live` pytest marker.**

## Performance

- **Duration:** ~12 min (first task commit 21:40:39 → last task commit 21:44:59 KST + scaffolding/setup)
- **Started:** 2026-07-06 (KST evening session)
- **Completed:** 2026-07-06
- **Tasks:** 3 (Task 2 was TDD → RED + GREEN commits)
- **Files modified:** 8 (5 created, 3 modified)

## Accomplishments
- `DecisionCard.warnings` optional payload field — the typed home for D-03 dropped facts, rides payload JSONB with no DB column (round-trip verified with a populated warnings list).
- `src/analysis/checksum.py`: `fact_supported()` + `checksum_facts()` — Korean-unit value-equivalence over the whole `body_md` (Veto #8), reusing the v1.0 numeric primitives; drops unverifiable facts into `warnings` naming the key (Veto #1/#4).
- CI import guard now covers `src/analysis` (D-01 Max-only Veto enforced in CI); `live` pytest marker registered (deselect by default so the default suite never spends Max quota).
- `tests/analysis/` package + base fixtures (`seeded_engine`, `real_filing_body`, `card_oracle`) — the Wave 0 scaffold every later Phase-4 plan reuses.

## Task Commits

Each task was committed atomically:

1. **Task 1: Package + card.warnings + CI guards + live marker** - `1193f2d` (feat)
2. **Task 2 (RED): failing D-03 checksum tests** - `4fe6639` (test)
3. **Task 2 (GREEN): implement D-03 checksum** - `c92ee7f` (feat)
4. **Task 3: full SC#3 checksum coverage** - `2342154` (test)

**Plan metadata:** _(final docs commit — this SUMMARY + STATE + ROADMAP)_

## Files Created/Modified
- `src/analysis/__init__.py` - package barrel (docstring only; later plan re-exports analyze_ticker)
- `src/analysis/checksum.py` - D-03 numeric checksum (fact_supported, checksum_facts); pure, mypy-strict clean
- `tests/analysis/__init__.py` - empty package marker
- `tests/analysis/conftest.py` - base fixtures: seeded_engine (entities + 2 filings), real_filing_body, card_oracle
- `tests/analysis/test_checksum.py` - 21 SC#3 tests (3×3 value-equivalence, tolerance boundary, drop→warnings)
- `src/cards/models.py` - added `warnings: list[str] = Field(default_factory=list)`
- `tests/test_import_guard.py` - `GUARDED_DIRS += "src/analysis"`; docstring updated
- `pyproject.toml` - registered `live` marker; added `src/analysis` to wheel packages

## Decisions Made
- **warnings as payload field, not DB column** — mirrors the Phase-2 invalidation_reason/status precedent; `store._PAYLOAD_EXCLUDE` unchanged, so it persists in payload and reconstructs under `extra="forbid"`.
- **Value-equivalence, not exact echo-back** — D-03 chose relative-tolerance match (default 0.5%) so re-formatted KR magnitudes (42.5조원 ≡ 42,500,000,000,000 ≡ 425000억) all verify; v1.0 `check_echo_back` deliberately NOT reused.
- **Skipped the optional SANITY_RULES second gate** — the table keys are Korean financial line-items that won't match English fact keys; adding it would be dead code (YAGNI). Documented so a later plan can add it if fact keys ever become Korean.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added `src/analysis` to pyproject.toml wheel packages**
- **Found during:** Task 1 (package scaffold)
- **Issue:** Plan modified `pyproject.toml` only for the `live` marker; the new `src/analysis` package was absent from `[tool.hatch.build.targets.wheel].packages`, so an installed (non-editable) deployment would ship without the analysis module.
- **Fix:** Added `"src/analysis"` to the wheel packages list (matches the existing cli/collectors/db/mcp_v2/orchestration/shared entries).
- **Files modified:** pyproject.toml
- **Verification:** ruff clean; package imports under `pythonpath=["src"]` in tests.
- **Committed in:** `1193f2d` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 missing-critical / packaging).
**Impact on plan:** Packaging completeness only. No behavior change, no scope creep.

## Issues Encountered
- **ruff E501 + mypy `type-arg`** on my own new code (long filing-seed tuples in conftest; `list[dict]` on `checksum_facts`). Fixed inline to satisfy repo conventions (strict mypy + ruff): split the tuples and annotated `list[dict[str, Any]]`. Verified `ruff check` + `mypy src/analysis/checksum.py` both clean.
- **requirements mark-complete:** the plan's requirement `SC#3` is a phase success-criterion (ROADMAP), not a `REQUIREMENTS.md` ID (that file holds v1 FOUND-/COLL-/… IDs only). No REQUIREMENTS.md checkbox to flip; recorded `requirements-completed: ["SC#3"]` in this SUMMARY's frontmatter instead.

## Test Results
- `pytest tests/analysis -q` → **21 passed** in 0.05s (pure-function; NO Docker container, NO live claude CLI spawned — success criterion met).
- `pytest tests/analysis tests/test_import_guard.py -q` → **25 passed** in 0.13s.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Wave 0 scaffold ready for the Wave 2 parallel plans (04-02 roles/rubric, 04-03 EvidenceBundle, 04-04 stance gate, 04-05 DebateBackend seam).
- `DecisionCard.warnings` and `checksum_facts` are the SC#3 primitives 04-06's `analyze_ticker` will call post-Judge.
- The `seeded_engine` / `card_oracle` fixtures are in place; the FakeDebateBackend fixture is intentionally deferred to the subagents plan (04-05) per plan.

## Self-Check: PASSED

- Files verified present: src/analysis/__init__.py, src/analysis/checksum.py, tests/analysis/{__init__,conftest,test_checksum}.py.
- Commits verified in git log: 1193f2d, 4fe6639, c92ee7f, 2342154.

---
*Phase: 04-analysis-runner-3-role-debate*
*Completed: 2026-07-06*
