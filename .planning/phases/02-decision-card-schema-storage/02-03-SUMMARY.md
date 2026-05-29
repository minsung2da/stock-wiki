---
phase: 02-decision-card-schema-storage
plan: 03
subsystem: storage
tags: [crud, decision_card, postgres, supersession, jsonb]

# Dependency graph
requires:
  - phase: 02-decision-card-schema-storage (plan 01)
    provides: "decision_cards table (12 locked columns + status lifecycle + self-ref supersedes/superseded_by FKs + payload JSONB + body_md TEXT), DecisionCard ORM, _LIVE_TABLES TRUNCATE hygiene"
  - phase: 02-decision-card-schema-storage (plan 02)
    provides: "DecisionCard Pydantic v2 model (+ nested Decision/KeyClaim/Contradiction), optional invalidation_reason field, src/cards barrel, tests/cards conftest (seeded_engine + decision_card_yaml)"
provides:
  - "src/cards/store.py — the SC#4 storage API: 4 typed CRUD helpers (save_card, get_active, walk_supersedes, invalidate), bind-param SQL only, no run_sql escape hatch (Veto #7)"
  - "Atomic supersession: save_card(supersedes=...) does INSERT-new + UPDATE-old in ONE with engine.begin() txn (T-02-09); AND status='active' guard makes it idempotent"
  - "invalidate() writes reason INTO payload JSONB via jsonb_set (OQ-1 — no new DB column, SC#1 column set intact)"
  - "get_active returns the FULL typed DecisionCard (payload + body_md) so Phase 3 view=payload|both is a serialize-time exclude, not a re-query (Veto #13 layering)"
  - "Optional status field on DecisionCard (DB lifecycle column merged in at reconstruct) so invalidate/get_active/walk surface .status"
  - "src/cards barrel now re-exports all four store helpers"
affects: [03-mcp-tools, 04-analysis-runner, 05-briefing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single with engine.begin() block for INSERT-new-then-UPDATE-old supersession (atomic; mirrors krx/db_writer.py:196-207)"
    - "jsonb_set(payload, '{invalidation_reason}', to_jsonb(:reason)) — reason in payload JSONB, never a new column (OQ-1)"
    - "DB lifecycle column (status) merged into the payload dict at reconstruct so the typed model surfaces it; optional model field defaults None to keep SC#3 round-trip intact"
    - "CAST(:payload AS jsonb) bind of json.dumps(model_dump(mode='json')) — ISO datetimes never corrupt the payload (Pitfall #3)"

key-files:
  created:
    - "src/cards/store.py"
    - "tests/cards/test_store.py"
  modified:
    - "src/cards/__init__.py"
    - "src/cards/models.py"

key-decisions:
  - "save_card resolves the supersede id from the `supersedes` keyword arg only (the locked DecisionCard model has no supersedes field); a getattr fallback is defensive only"
  - "Added optional status: str|None=None to DecisionCard (Rule 2): plan acceptance criteria require invalidate() to return a card with .status=='invalidated'. status is a DB lifecycle column, not §3 payload, merged in at reconstruct; defaults None so SC#3 round-trip of the §3 YAML is unaffected and adds NO new DB column (already exists, SC#1 intact)"
  - "get_active/walk_supersedes/invalidate all return reconstructed DecisionCard instances (Discretion #4) — body_md is a field, view selection is a downstream serialize concern (Veto #13)"
  - "walk_supersedes returns the chain newest→oldest (documented), following each card's supersedes pointer, with a depth-100 cycle guard"

patterns-established:
  - "src/cards/store.py: module-level text() SQL constants + __all__, all bind params, atomic engine.begin() write boundary"
  - "DB-only lifecycle column reconstructed into the typed model via an optional field + store-layer merge"

requirements-completed: [SC#4]

# Metrics
duration: 8 min
completed: 2026-05-30
---

# Phase 2 Plan 03: Decision Card CRUD Store Summary

**`src/cards/store.py` — the four locked SC#4 CRUD helpers (`save_card`, `get_active`, `walk_supersedes`, `invalidate`) over the `decision_cards` table: atomic single-transaction supersession (INSERT-new + UPDATE-old with an `AND status='active'` idempotency guard), full typed `DecisionCard` reconstruction from `payload` JSONB + `body_md`, and invalidation reason stamped into the payload via `jsonb_set` (no new column), all in bind-param SQL with no `run_sql` escape hatch — proven by 8 integration tests against a live Postgres 17 + vchord container covering CRUD, supersession atomicity (fresh-connection verify), an invalidated card in the walk chain, and the `payload->'decision'->>'stance'` JSONB round-trip.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-05-29
- **Completed:** 2026-05-30
- **Tasks:** 2
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `src/cards/store.py` is the SC#4 storage API Phase 3 MCP `get_decision_card` and Phase 4 `analyze_ticker` will call. It exposes ONLY the four typed helpers — no generic `run_sql` / arbitrary-SQL function (Veto #7 / T-02-08). Every statement is a module-level `text()` constant bound with parameters; identifiers and the invalidation `reason` never reach SQL via f-string (T-02-07).
- `save_card(engine, card, *, supersedes=None)` does the INSERT of the new card and the conditional UPDATE of the prior card's `status='superseded'` + `superseded_by` in ONE `with engine.begin()` transaction — a crash leaves no dangling chain (T-02-09 / Discretion #2). The `AND status='active'` guard makes the supersede idempotent and refuses to clobber an already-invalidated prior card.
- `get_active(corp_code)` returns the latest active, non-superseded card reconstructed as a full typed `DecisionCard` (payload + body_md) — so Phase 3's `view=payload|both` is a serialize-time `exclude`, not a second query (Veto #13 clean layering / Discretion #4). Returns `None` for an unseeded corp.
- `walk_supersedes(card_id)` returns the supersession chain newest→oldest with a depth-100 cycle guard; an invalidated card anywhere in the chain reconstructs cleanly.
- `invalidate(card_id, reason)` sets `status='invalidated'` and writes `reason` INTO the `payload` JSONB via `jsonb_set(payload, '{invalidation_reason}', to_jsonb(:reason))` (OQ-1 — reason in payload, NO new column, SC#1 column set untouched), then re-selects and returns the updated card; returns `None` if the id did not exist.
- 8 integration tests green against a real Postgres 17 + vchord testcontainer; full non-slow/non-e2e suite 374 passed (up from 366 in Plan 02, +8 new); mypy strict clean on `store.py` + `models.py`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement the 4 CRUD helpers + complete the barrel** - `103e48e` (feat)
2. **Task 2: Integration tests — CRUD + supersession atomicity + JSONB round-trip (SC#4)** - `1494ee5` (test)

**Plan metadata:** committed with this SUMMARY (docs).

_Note: both tasks (tdd="true") landed GREEN immediately — Task 1's helpers were written against the already-locked Plan-01 schema + Plan-02 model, and Task 1's `<verify>` is import + mypy (the helpers are the deliverable; the behavioral tests are Task 2). The Rule-2 model change (optional `status` field) needed to satisfy the plan's `.status` acceptance criteria was made during Task 2 and committed with it._

## Files Created/Modified
- `src/cards/store.py` - The four SC#4 CRUD helpers + 5 module-level `text()` SQL constants + `_row_to_card` reconstructor; single `with engine.begin()` atomic write boundary; `Engine` under `TYPE_CHECKING`; `__all__` lists the four helpers.
- `tests/cards/test_store.py` - 8 integration tests (`test_save_and_get_active`, `test_get_active_none`, `test_supersession_atomic`, `test_walk_supersedes`, `test_invalidate`, `test_invalidate_missing_returns_none`, `test_walk_includes_invalidated`, `test_jsonb_payload_roundtrip`) using `seeded_engine` + `decision_card_yaml`; all test SQL bind-param.
- `src/cards/__init__.py` - Barrel extended additively: `from .store import ...` + `__all__ = ["DecisionCard", "save_card", "get_active", "walk_supersedes", "invalidate"]`.
- `src/cards/models.py` - Added optional `status: str | None = None` (Rule 2 — see Deviations). DB lifecycle column merged in at reconstruct; default None keeps the SC#3 round-trip of the §3 YAML unaffected.

## Decisions Made
- **Supersede id from the keyword arg only:** the locked `DecisionCard` model (Plan 02) has no `supersedes` field, so `save_card` resolves the effective supersede id from the `supersedes` keyword. The `getattr(card, "supersedes", None)` fallback is defensive only (the RESEARCH §Discretion #2 example referenced `card.supersedes`, which predates the final locked model).
- **Optional `status` field on `DecisionCard`:** required so `invalidate()`/`get_active()`/`walk_supersedes()` can return a card whose `.status` reflects the DB lifecycle column (the plan's acceptance criteria assert `.status == "invalidated"`). It defaults to `None` (a freshly-built, not-yet-persisted card has no DB status), mirroring exactly the precedent of the optional `invalidation_reason` field, and adds NO new DB column (the `status` column already exists from Plan 01, SC#1 intact). The SC#3 round-trip of the §3 YAML is unaffected (status absent → None → null → None).
- **Return full typed `DecisionCard` (not a projection):** `body_md` is a model field; payload-only vs both is a Phase-3 serialize-time `exclude`, not a re-query — keeps `store.py` ignorant of the MCP view API (Veto #13 / Discretion #4).
- **`walk_supersedes` order = newest→oldest** with a depth-100 cycle guard (documented in the docstring), following each card's `supersedes` pointer.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Added optional `status` field to `DecisionCard` so reconstructed cards surface their DB lifecycle status**
- **Found during:** Task 2 (writing `test_invalidate` against the plan's acceptance criteria)
- **Issue:** The plan's Task 1/Task 2 acceptance criteria require `invalidate(card_id, reason)` to return a `DecisionCard` whose `.status == "invalidated"` (and the supersession/walk behavior implicitly surfaces status). But the Plan-02-locked `DecisionCard` model has NO `status` field — `status` is a `decision_cards` DB lifecycle column (active/superseded/invalidated), not part of the §3 YAML payload. Without a `status` field on the model, `updated.status` raises `AttributeError` and the criteria cannot be met.
- **Fix:** Added `status: str | None = None` to `DecisionCard` (additive, optional, default None — exactly mirroring the existing optional `invalidation_reason` precedent the model already established for the same reconstruct-round-trip reason). The store's `_row_to_card` merges the DB `status` column value into the validation dict so the returned card surfaces it. This adds NO new DB column (the `status` column already exists from Plan 01) — SC#1's locked column set is untouched.
- **Files modified:** `src/cards/models.py`, `src/cards/store.py`
- **Verification:** `tests/cards/test_store.py::test_invalidate` (asserts the RETURNED card `.status == "invalidated"` AND `.invalidation_reason == reason`) green; Plan-02's `tests/cards/test_models.py::test_round_trip` (SC#3) still green (status defaults None, round-trips); full cards suite 14 passed; full non-slow suite 374 passed; mypy strict clean.
- **Committed in:** `1494ee5` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing-critical — optional `status` field to satisfy the plan's `.status` acceptance criteria)
**Impact on plan:** Necessary to meet the plan's own acceptance criteria; additive and consistent with the model's existing optional-field pattern. No scope creep — the four helpers, their signatures, the atomic supersession, the `jsonb_set` invalidation, and the test set match the plan exactly.

## Known Stubs
None — all four helpers are full, working, mypy-clean implementations exercised end-to-end against live Postgres. No placeholders or TODOs.

## Threat Flags
None — no new security surface beyond the plan's threat model.
- **T-02-07 (SQL injection via card_id/corp_code/reason):** mitigated — every statement is a `text()` constant with bind params; `reason` crosses as `to_jsonb(CAST(:reason AS text))`. Verified by absence of f-string SQL in `store.py`.
- **T-02-08 (arbitrary-SQL escape hatch):** mitigated — `store.py` exposes ONLY the four typed helpers; no `run_sql`/generic query (Veto #7).
- **T-02-09 (non-atomic supersession):** mitigated — single `with engine.begin()` block for INSERT+UPDATE; `AND status='active'` guard. Verified by `test_supersession_atomic` reading committed state in a fresh connection.
- **T-02-10 (JSONB/datetime corruption):** mitigated — `model_dump(mode="json")` → `json.dumps` → `CAST(... AS jsonb)`; verified by `test_jsonb_payload_roundtrip`.
- **T-02-SC (package installs):** N/A — no packages installed.

## Issues Encountered
- `uv` is not on the Bash PATH in this environment (same as Plans 01/02). Ran all verifies/tests via the project `.venv\Scripts\python.exe` (with `PYTHONPATH=src` for the standalone import check). The venv interpreter is Python 3.13.5 while the project targets 3.12 — no impact: `store.py` uses only 3.12-compatible syntax (`X | Y` unions, `list[...]`/`dict[...]`, `from __future__ import annotations`) and mypy ran with `python_version = "3.12"` (strict) and passed; all 8 store tests + the full 374-test non-slow suite are green.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The SC#4 storage API is locked, mypy-clean, and integration-verified against live Postgres — ready for Phase 3 (MCP tool surface) where `get_decision_card` wraps `get_active`/reconstruct and applies the `view=payload|both` serialize-time `exclude` (Veto #13), and for Phase 4 (`analyze_ticker`) which calls `save_card`/`invalidate`.
- Supersession is atomic and idempotent; invalidation reason lives in payload JSONB (no schema change needed downstream).
- Phase 2 (decision-card-schema-storage) is now complete: all three plans (01 schema/ORM, 02 Pydantic model, 03 CRUD store) have SUMMARYs.
- No blockers.

## Self-Check: PASSED

All created/modified files exist on disk (`src/cards/store.py`, `tests/cards/test_store.py`, `src/cards/__init__.py`, `src/cards/models.py`); both task commits (`103e48e`, `1494ee5`) present in git log; all 6 named acceptance tests + the full cards suite (14 passed) + full non-slow/non-e2e suite (374 passed) green; mypy strict clean on `store.py` + `models.py`. All Task-1 and Task-2 `<acceptance_criteria>` re-verified (with engine.begin in save_card; jsonb_set + invalidation_reason in invalidate; NO f-string SQL; four helpers + DecisionCard in barrel `__all__`; returned card `.status == 'invalidated'` and `.invalidation_reason == reason`; walk tolerates invalidated card; JSONB stance round-trip).

---
*Phase: 02-decision-card-schema-storage*
*Completed: 2026-05-30*
