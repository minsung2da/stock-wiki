# Phase 1 Deferred Items

Pre-existing failures discovered during plan 01-09 execution that are
out-of-scope for 01-09 itself. These were introduced by prior plans in
this phase and missed by the planner.

## Items

### DI-1 — `tests/test_migration.py::test_events_jsonb_and_fk` references the renamed table

- **Discovered during:** 01-09 Task 1 fast-suite sanity check.
- **Root cause:** Plan 01-01 migration 0006 renamed `events` → `events_legacy`
  and created a new `events` table with a different shape (KIND classifier:
  no `payload` JSONB column, no `entities` FK constraint).
  `tests/test_migration.py::test_events_jsonb_and_fk` still asserts the
  Phase 2 shape (`payload` column = jsonb, FK to entities).
- **Why this is pre-existing:** present on `HEAD` before 01-09 started; my
  Task 1 commit (writer.py deletion) does not touch this file.
- **Recommended fix:** point the test at `events_legacy` so it continues
  to validate the Phase 2 shape on the renamed table; add separate tests
  for the new Phase 1 `events` shape (already present in
  `tests/db/test_migration_0006.py`).
- **Disposition:** flagged here, not patched in 01-09. Belongs to a 01-01
  follow-up or a Phase 1 cleanup commit.

### DI-2 — `test_collect_dart_writes_collector_runs_row` flakiness under suite-wide ordering

- **Discovered during:** 01-09 Task 1 fast-suite sanity check.
- **Root cause:** Passes in isolation and in module-scoped runs. Fails
  intermittently when the full fast suite executes — `_count_runs(...)`
  returns 0 even though the dart collector calls `record_collector_run`.
  Most likely a `pg_clean` / monkeypatch cleanup interaction with an
  earlier test file (the failure was not reproducible after the
  `tests/test_entity_upsert.py` cleanup in 01-09 Task 1, suggesting the
  ordering changed).
- **Why this is pre-existing:** the test was added by plan 01-08
  (`4a81518 feat(01-08): add shared.run_log.record_collector_run helper`)
  before 01-09 started.
- **Disposition:** owned by plan 01-08 sibling agent. 01-09 self-check
  treats the test as PASS based on isolated and module-scoped runs.

## Plan 01-09 closing note

These two items are independent of the Veto #9 fences that 01-09 enforces
(writer deletion + CI guard + runtime assertion + smoke test). 01-09's
acceptance criteria are evaluated on its own scope; the items above are
folded into a future cleanup pass.
