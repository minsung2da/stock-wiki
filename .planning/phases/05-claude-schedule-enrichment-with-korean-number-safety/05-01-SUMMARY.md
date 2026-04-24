---
phase: 05-claude-schedule-enrichment-with-korean-number-safety
plan: 01
subsystem: schema
tags: [pydantic, frontmatter, literal-enum, schema, phase5]

requires:
  - phase: 03-one-company-walking-skeleton
    provides: base FrontMatter / DerivedBlock / NumericFact / SentimentBlock (Phase 3 shape)
provides:
  - DerivedBlock v2 with Literal-narrowed event_type (17+other+null)
  - ReviewFlag model with 9 Literal flag values
  - SentimentBlock with Literal label (6), rationale, scope
  - NumericFact with Literal unit (13), value_krw, source_span, offset
  - DerivedBlock.review_flags + DerivedBlock.skip_reason additive fields
  - EventType Literal alias exported for downstream modules
affects:
  - 05-02-units (consumes NumericFact.unit / value_krw)
  - 05-03-number_extraction (produces NumericFact v2 tuples)
  - 05-04-number_sanity (reads review_flags, writes sanity violations)
  - 05-05-dart-financials (writes DART-structured NumericFact)
  - 05-06-backlog (skip_reason oversize path)
  - 05-07-heartbeat-enrich (counts review_flags)
  - 05-08-routines-skill (Sonnet JSON → DerivedBlock model_validate boundary)

tech-stack:
  added: []
  patterns:
    - "Additive Pydantic schema migration — legacy YAML validates without change"
    - "Literal-enum narrowing as LLM output validation boundary (extra=forbid)"

key-files:
  created:
    - tests/test_frontmatter_v2.py
  modified:
    - src/shared/frontmatter.py
    - tests/test_frontmatter.py

key-decisions:
  - "extra=forbid on v2 models (ReviewFlag/SentimentBlock/NumericFact/DerivedBlock) rejects LLM-hallucinated keys at Pydantic boundary"
  - "Legacy ProvenanceBlock / IngestStateBlock left as-is (no extra=forbid) to preserve Phase 3/4 YAML compat"
  - "EventType Literal exported as type alias so Wave 2+ modules can annotate without re-defining"
  - "Legacy test using event_type='earnings' (free string) updated to 'earnings_release' (valid Literal) — schema narrowing is the feature"

patterns-established:
  - "Additive Pydantic v2 migration: new fields get defaults (None / default_factory=list); legacy YAML continues to validate"
  - "Literal enum for LLM-facing string fields: hallucinated values raise ValidationError instead of silently passing"

requirements-completed: [INGEST-05]

duration: ~13min
completed: 2026-04-24
---

# Phase 05 Plan 01: DerivedBlock v2 Schema Summary

**DerivedBlock v2 with Literal-narrowed event_type/unit/label, ReviewFlag model, and review_flags/skip_reason additive fields — all Wave 1 downstream plans can now import the frozen schema.**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-04-24T14:42:31Z
- **Completed:** 2026-04-24T14:55:00Z
- **Tasks:** 2
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- `ReviewFlag` model with 9 Literal flag values (numeric_echo_mismatch, numeric_sanity_violation, dart_structured_disagreement, self_inconsistent, oversize_skipped, prompt_injection_suspected, sentiment_score_label_mismatch, agent_zone_violation, merge_conflict) per D-11
- `SentimentBlock` extended: Literal label (strongly_bullish, bullish, neutral, bearish, strongly_bearish, unclear) + rationale + scope (tone/outcome) per D-10
- `NumericFact` extended: Literal unit (KRW원/백만/억/조, USD/EUR/JPY, pct, bps, multiplier, shares, days, other), value_krw, source_span, offset per D-09
- `EventType` Literal alias (17 events + "other") exported for downstream modules per D-08
- `DerivedBlock.review_flags` (default []) + `skip_reason` (Literal oversize/review_required/merge_conflict) additive
- `extra="forbid"` on all v2 models rejects LLM-hallucinated keys
- 8 new tests in `tests/test_frontmatter_v2.py` — round-trip, legacy compat, Literal enforcement (8/8 pass)
- 17 legacy frontmatter tests continue to pass unchanged

## Task Commits

Each task was committed atomically (TDD cycle):

1. **Task 2 (tests written first, RED)** — `ab7da44` (test)
2. **Task 1 (schema + legacy test fixup, GREEN)** — `45bb62f` (feat)

## Files Created/Modified

- `src/shared/frontmatter.py` — added ReviewFlag, EventType alias; extended SentimentBlock/NumericFact/DerivedBlock with Literal-narrowed fields and extra=forbid
- `tests/test_frontmatter_v2.py` — 8 tests (round-trip, legacy compat, all Literal rejection paths)
- `tests/test_frontmatter.py` — updated legacy test to use valid Literal value `earnings_release` (previously used free-string `earnings` which schema narrowing now correctly rejects)

## Decisions Made

- **extra="forbid" on v2 models only, not legacy ProvenanceBlock/IngestStateBlock.** Legacy zones may carry extra keys from Phase 3/4 fields; v2 zones are the LLM boundary that must reject hallucinations.
- **EventType exported as top-level `Literal` type alias, not Enum.** Matches Pydantic idiomatic Literal usage and keeps YAML serialization as plain strings.
- **TDD RED-then-GREEN ordering preferred over plan's T1/T2 ordering.** Plan listed schema (T1) before tests (T2), but T1's verify step runs the T2 test file. Wrote tests first (RED commit), then schema (GREEN commit) — both tasks now present and committed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Legacy test used invalid Literal value**
- **Found during:** Running verify after Task 1 implementation
- **Issue:** `tests/test_frontmatter.py::test_derived_update_isolation` constructed `DerivedBlock(event_type="earnings", ...)` — which was valid under the Phase 3 free-string shape but is rejected by the new D-08 Literal. The plan mandates narrowing event_type; keeping the test broken would be inconsistent.
- **Fix:** Updated test to use `event_type="earnings_release"` (a valid Literal) and asserted the same.
- **Files modified:** `tests/test_frontmatter.py`
- **Verification:** `uv run pytest tests/test_frontmatter.py tests/test_frontmatter_news_fields.py tests/test_frontmatter_v2.py -q` → 25 passed
- **Committed in:** `45bb62f` (Task 1 GREEN commit)

**2. [Rule 3 - Blocking] `--extra dev` flag in plan acceptance not defined in pyproject.toml**
- **Found during:** Running plan's exact verify command
- **Issue:** Plan specifies `uv run --extra dev pytest ...` but `dev` is not an optional-dependency group in this project (deps are in their own groups but `dev` is not declared as an extra under `[project.optional-dependencies]`).
- **Fix:** Used `uv run pytest ...` directly — the dev test deps (pytest, etc.) are already resolved in the default sync.
- **Files modified:** None (documentation-only deviation in execution commands)
- **Verification:** `uv run pytest tests/test_frontmatter_v2.py -x -q` → 8 passed
- **Committed in:** N/A (no file change)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both auto-fixes preserve the plan's intent. No scope creep. Narrowing is the feature; the legacy test had to adapt.

## Issues Encountered

- One transient `.git/index.lock` race during `git commit` (pre-commit hook stash interacting with ruff-format rewrite). Retry after the hook rewrote the test file succeeded. Not a plan issue.

## Acceptance Criteria Verification

- `grep -c 'extra="forbid"' src/shared/frontmatter.py` → **6** (ReviewFlag + SentimentBlock + NumericFact + DerivedBlock + pre-existing TickerRef + Observation — well above plan's ≥4 threshold)
- `grep -q "class ReviewFlag"` → found
- `grep -q "numeric_echo_mismatch"` → found
- `grep -q "strongly_bullish"` → found
- `grep -q "KRW조"` → found
- `grep -q "review_flags: list\[ReviewFlag\]"` → found
- `grep -q "skip_reason: Literal"` → found
- `pytest tests/test_frontmatter_v2.py -x -q` → **8 passed**
- `grep -c '^def test_' tests/test_frontmatter_v2.py` → **8**
- Legacy tests (`test_frontmatter.py`, `test_frontmatter_news_fields.py`) → **17 passed** post-fixup

## Threat Model Check

Threat register dispositions satisfied:
- **T-05-01-01 (Tampering — LLM JSON):** `extra="forbid"` on ReviewFlag/SentimentBlock/NumericFact/DerivedBlock — verified via tests
- **T-05-01-02 (Tampering — event_type):** Literal rejection verified by `test_unknown_event_type_rejected`
- **T-05-01-03 (Integrity — legacy compat):** verified by `test_legacy_phase3_shape_still_validates` (legacy YAML without review_flags / skip_reason / value_krw loads cleanly)
- **T-05-01-04 (DoS — oversize):** upstream, out of scope for this plan (05-08 Routines skill)

No new threat surface introduced beyond the plan's threat_model.

## Next Phase Readiness

- Wave 2 plans (05-02 through 05-08) can now `from shared.frontmatter import ReviewFlag, NumericFact, DerivedBlock, EventType, SentimentBlock` without further schema changes.
- Frozen surface: DerivedBlock v2 is the LLM output contract; downstream plans consume, not modify.
- No blockers for Wave 2 kickoff.

## Self-Check: PASSED

- `src/shared/frontmatter.py` contains ReviewFlag, EventType, review_flags, skip_reason — FOUND
- `tests/test_frontmatter_v2.py` exists with 8 `def test_` — FOUND
- Commit `ab7da44` (test RED) — FOUND in `git log`
- Commit `45bb62f` (feat GREEN) — FOUND in `git log`
- All 25 frontmatter tests pass

---
*Phase: 05-claude-schedule-enrichment-with-korean-number-safety*
*Completed: 2026-04-24*
