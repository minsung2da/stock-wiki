---
phase: 02-decision-card-schema-storage
plan: 02
subsystem: api
tags: [pydantic, decision_card, validation, hard-veto, round-trip]

# Dependency graph
requires:
  - phase: 02-decision-card-schema-storage (plan 01)
    provides: "decision_cards table (12 locked columns + generated body_tsv), DecisionCard ORM class, seeded entities pattern, _LIVE_TABLES TRUNCATE hygiene"
provides:
  - "DecisionCard Pydantic v2 model (+ nested Decision/KeyClaim/Contradiction) — the typed card contract every downstream phase produces/consumes"
  - "SC#5 hard veto (Veto #2) enforced purely by field declarations: non-Optional expires_at + assumptions min_length=1"
  - "extra='forbid' on every model (ASVS V5 / T-02-04) — unknown card keys rejected at the model boundary"
  - "optional invalidation_reason field — keeps Plan 03 invalidate()/walk reconstruct round-trip-safe under extra='forbid' (redesign §4)"
  - "src/cards/ package barrel re-exporting DecisionCard (Plan 03 extends additively with store helpers)"
  - "tests/cards/ package: decision_card_yaml (SC#3 round-trip oracle, §3 YAML verbatim) + re-declared seeded_engine fixture for Plan 03"
affects: [02-03-decision-card-crud-store, 03-mcp-tools, 04-analysis-runner, 05-briefing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Hard veto via field declarations only (non-Optional + min_length), NOT @model_validator — matches CONTEXT 'leave shape to the type system'"
    - "Round-trip oracle = semantic equality through model_dump(mode='json'), NOT byte-identical YAML (tz-offset + int-vs-float survive)"
    - "Per-directory conftest scoping: seeded_engine re-declared under tests/cards/ (copy, not import)"

key-files:
  created:
    - "src/cards/models.py"
    - "src/cards/__init__.py"
    - "tests/cards/__init__.py"
    - "tests/cards/conftest.py"
    - "tests/cards/test_models.py"
  modified: []

key-decisions:
  - "SC#5 enforced by field declarations only (expires_at non-Optional no-default; assumptions Field(min_length=1)) — no @model_validator, per CONTEXT 'leave shape to the type system'"
  - "numeric_facts typed dict[str, float | int] (permissive) — Phase 2 validates shape only; digit-verbatim checksum is Phase 4's job (CONTEXT lock, T-02-06)"
  - "invalidation_reason: str | None = None added to the model (NOT in §3 YAML) — redesign §4 payload field; Plan 03 invalidate() writes it into payload JSONB, so extra='forbid' reconstruct must accept it; adds NO DB column (SC#1 column set untouched)"
  - "Round-trip semantics = model_validate(card.model_dump(mode='json')) == card (OQ-3 / Pitfall #4), not byte-identical YAML"

patterns-established:
  - "Field-declaration-only hard veto: non-Optional + min_length express the business rule, ValidationError fires at the model boundary"
  - "Inline dict fixture as round-trip oracle (mirrors tests/conftest.py SAMPLE_YAML pattern)"

requirements-completed: [SC#3, SC#5]

# Metrics
duration: 11 min
completed: 2026-05-30
---

# Phase 2 Plan 02: Decision Card Pydantic Model Summary

**`DecisionCard` Pydantic v2 model (with nested `Decision`/`KeyClaim`/`Contradiction`) matching the redesign §3 YAML field names exactly so it round-trips, enforcing the SC#5 hard veto (no untimed thesis, no empty assumptions) purely through field declarations, plus the `tests/cards/` package with the §3 round-trip oracle fixture and 6 unit tests covering SC#3 round-trip, both SC#5 rejections, ASVS V5 extra-key rejection, int/float preservation, and the Plan-03 invalidation_reason reconstruct path.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-05-30
- **Completed:** 2026-05-30
- **Tasks:** 3
- **Files modified:** 5 (5 created, 0 modified)

## Accomplishments
- `DecisionCard` is the typed contract for the whole card pipeline (Veto #7 — typed Pydantic, never raw dicts), with field names locked to the redesign §3 YAML so `DecisionCard.model_validate(card.model_dump(mode="json")) == card` holds (SC#3).
- SC#5 hard veto (Veto #2) is enforced at the model boundary purely by field declarations: `expires_at: datetime` (no default, no `| None`) and `assumptions: list[str] = Field(min_length=1)` — a card with a missing expiry or empty assumptions raises `ValidationError`. No `@model_validator` needed.
- Every model declares `model_config = ConfigDict(extra="forbid")` (ASVS V5 / T-02-04) — unknown payload keys are rejected before a malformed card could reach storage. Veto #3 contradictions[] is a first-class declared field.
- `invalidation_reason: str | None = None` added (not in §3 YAML; redesign §4 payload field) so Plan 03's `invalidate()`/`walk_supersedes` reconstruct of a post-`jsonb_set` payload validates cleanly under `extra="forbid"` — adds no DB column, leaving the SC#1 locked column set untouched.
- `tests/cards/` package created with `decision_card_yaml` (the SC#3 round-trip oracle, §3 YAML transcribed verbatim with mixed int/float `numeric_facts`) and a re-declared `seeded_engine` fixture ready for Plan 03's `test_store.py`.
- 6 model tests green; mypy strict clean; full non-slow/non-e2e suite 366 passed (up from 360 in Plan 01, +6 new).

## Task Commits

Each task was committed atomically:

1. **Task 1: Define DecisionCard Pydantic models + package barrel** - `f530c91` (feat)
2. **Task 2: Create tests/cards package + conftest fixtures** - `02ae10c` (test)
3. **Task 3: Round-trip + hard-veto rejection tests (SC#3, SC#5)** - `214a952` (test)

**Plan metadata:** committed with this SUMMARY (docs).

_Note: Task 1 (tdd="true") landed as a single feat commit — its `<verify>` is import + mypy (the model itself is the deliverable; the round-trip/rejection tests are Task 3). Task 3 (tdd="true") landed GREEN immediately because Task 1 already authored the correct contract; the six tests verify the locked §3 schema, so there was no separate RED commit (writing a failing test against an already-correct model would be a no-op — fail-fast rule: a test passing against an existing correct contract is expected, not a skipped RED)._

## Files Created/Modified
- `src/cards/models.py` - `DecisionCard` + nested `Decision`/`KeyClaim`/`Contradiction` Pydantic v2 models; SC#5 hard veto via field declarations; `extra="forbid"` on all four classes; optional `invalidation_reason`.
- `src/cards/__init__.py` - Package barrel re-exporting `DecisionCard` with `__all__ = ["DecisionCard"]` (Plan 03 extends additively with store helpers).
- `tests/cards/__init__.py` - Package marker (mirrors other tests subpackages).
- `tests/cards/conftest.py` - `decision_card_yaml` (SC#3 round-trip oracle, §3 YAML verbatim, mixed int/float `numeric_facts`) + re-declared `seeded_engine` (per-directory conftest scoping) for Plan 03.
- `tests/cards/test_models.py` - 6 tests: `test_round_trip` (SC#3), `test_missing_expiry_rejected` + `test_empty_assumptions_rejected` (SC#5 / Veto #2), `test_extra_key_rejected` (ASVS V5), `test_numeric_facts_types_preserved` (Pitfall #4), `test_invalidation_reason_optional` (Plan 03 reconstruct path).

## Decisions Made
- **Field-declaration-only hard veto:** `expires_at: datetime` (no default/no Optional) and `assumptions = Field(min_length=1)` express SC#5 (Veto #2) directly — no `@model_validator`. Matches CONTEXT "leave shape to the type system" and RESEARCH §Code Examples.
- **`numeric_facts: dict[str, float | int]` (permissive):** Phase 2 validates shape only; the digit-verbatim checksum against source narrative is Phase 4's responsibility (CONTEXT lock, T-02-06). The fixture mixes `market_cap_krw` (int) and `pe_ttm`/`foreign_ownership_pct` (float) and a test asserts neither drifts across the round-trip.
- **`invalidation_reason` on the model:** not in the §3 YAML, but redesign §4 lists it as a payload field. Plan 03's `invalidate()` writes it into the payload JSONB via `jsonb_set`, so the model MUST accept it or `extra="forbid"` reconstruction would raise. It stays inside payload — no new DB column, SC#1 column set unchanged.
- **Round-trip = semantic equality through `model_dump(mode="json")`:** tz offsets (`+09:00`) and int-vs-float survive the JSON dump/reparse; the test compares model instances, not byte-identical YAML (OQ-3 / Pitfall #4).

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0
**Impact on plan:** The model, fixtures, and tests match the plan's `<interfaces>` block and acceptance criteria exactly. No scope creep; store.py (Plan 02-03) was correctly left out of scope.

## Known Stubs
None — no stubs introduced. `DecisionCard` is the full, mypy-clean typed contract. The CRUD store layer (`src/cards/store.py`, the four SC#4 helpers) is out of scope for this plan — it is Plan 02-03, which extends the `src/cards/__init__.py` barrel additively (the barrel was authored so adding store imports is purely additive).

## Threat Flags
None — no new security surface beyond the plan's threat model. T-02-04 (extra-key tampering) is mitigated by `extra="forbid"` on every model (verified by `test_extra_key_rejected`); T-02-05 (untimed thesis) is mitigated by the SC#5 field declarations (verified by `test_missing_expiry_rejected` / `test_empty_assumptions_rejected`); T-02-06 (numeric coercion drift) is accepted-by-design and shape-guarded by `dict[str, float | int]` (verified by `test_numeric_facts_types_preserved`); no packages installed (T-02-SC N/A).

## Issues Encountered
- `uv` is not on the Bash PATH in this environment (same as Plan 01). Ran all verifies/tests via the project `.venv\Scripts\python.exe` (with `PYTHONPATH=src` for the standalone `python -c` import/fixture checks). The venv interpreter is Python 3.13.5 while the project targets 3.12 — no impact: the model uses only 3.12-compatible syntax (`X | Y` unions, `list[...]`/`dict[...]`) and mypy was run with `python_version = "3.12"` (strict) and passed; all 6 tests + the full 366-test non-slow suite are green.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `DecisionCard` typed contract is locked, mypy-clean, and round-trip-verified against the §3 YAML — ready for plan 02-03 (the four `src/cards/store.py` CRUD helpers `save_card`/`get_active`/`walk_supersedes`/`invalidate`).
- `tests/cards/conftest.py` already provides `seeded_engine` (FK-satisfiable entities) and the `decision_card_yaml` oracle Plan 03's `test_store.py` will consume.
- The `src/cards/__init__.py` barrel is authored so Plan 03 store imports are additive; the optional `invalidation_reason` field unblocks Plan 03's `invalidate()`/`walk_supersedes` payload reconstruct under `extra="forbid"`.
- No blockers.

## Self-Check: PASSED

All 5 created files exist on disk; all three task commits (`f530c91`, `02ae10c`, `214a952`) present in git log; all 6 model tests + the full non-slow/non-e2e suite (366 passed) green; mypy strict clean on `src/cards/models.py`. All plan `<acceptance_criteria>` re-verified (assumptions min_length, non-Optional expires_at, 4× extra=forbid, numeric_facts type, invalidation_reason, barrel re-export, fixture literals).

---
*Phase: 02-decision-card-schema-storage*
*Completed: 2026-05-30*
