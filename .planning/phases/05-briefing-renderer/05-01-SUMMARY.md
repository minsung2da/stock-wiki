---
phase: 05-briefing-renderer
plan: 01
subsystem: database
tags: [alembic, postgres, sqlalchemy, migration, decision_cards, briefing, check-constraint, partial-index]

# Dependency graph
requires:
  - phase: 02-decision-card-schema-storage
    provides: "decision_cards table (migration 0007) — the 12 locked columns + corp_code NOT NULL FK that 0009 relaxes"
  - phase: 03-mcp-tool-surface
    provides: "migration 0008 (head before 0009) + the partial-index idiom (ix_notes_corp) 0009 copies"
provides:
  - "migration 0009: report_type TEXT NULL + report_date DATE NULL on decision_cards"
  - "corp_code DROP NOT NULL guarded by partial CHECK ck_decision_cards_corp_or_report (analysis-card FK invariant preserved)"
  - "ck_decision_cards_report_type (kinds: daily_briefing/weekly_briefing) + partial ix_decision_cards_report"
  - "ORM DecisionCard column-set parity (report_type/report_date + corp_code nullable)"
  - "live DB migrated to 0009 (alembic current == 0009)"
affects: [briefing, store.save_briefing, store.get_briefing_row, daily.py, weekly.py, get_briefing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "op.create_check_constraint (ALTER-time CHECK) — first use in this repo; 0007/0008 used inline sa.CheckConstraint at create-table"
    - "partial CHECK to relax a NOT NULL without losing an invariant (report_type IS NOT NULL OR corp_code IS NOT NULL)"
    - "downgrade DELETEs relaxed-nullable rows before restoring NOT NULL (downgrade footgun)"

key-files:
  created:
    - src/db/migrations/versions/0009_briefing_report_type.py
    - tests/db/test_migration_0009.py
  modified:
    - src/db/entity_models.py
    - tests/db/test_migration_0007.py

key-decisions:
  - "Two dedicated columns (report_type + report_date DATE) over a single KST-expression index — timezone-safe equality match (RESEARCH OQ2 RESOLVED)"
  - "corp_code nullability relaxed at DB level; analysis-card invariant preserved by partial CHECK, not column NOT NULL"
  - "ORM DecisionCard tracks column-set parity only; the CHECKs + partial index are DB-only (parity test compares column names)"

patterns-established:
  - "Pattern: partial CHECK ck_decision_cards_corp_or_report keeps an FK invariant while relaxing a NOT NULL for a new row kind"
  - "Pattern: 0009 downgrade DELETEs report_type IS NOT NULL rows before ALTER corp_code SET NOT NULL"

requirements-completed: [SC#2]

# Metrics
duration: 5min
completed: 2026-07-16
---

# Phase 5 Plan 01: Briefing report_type Migration Summary

**Migration 0009 lets `decision_cards` hold NULL-corp briefing rows (SC#2) while a partial CHECK keeps single-ticker analysis cards' corp_code FK invariant intact.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-07-16T12:30:06Z
- **Completed:** 2026-07-16T12:34:54Z
- **Tasks:** 3 (2 with repo artifacts + 1 blocking DB-state gate)
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments

- **Migration 0009** (`down_revision = "0008"`): `report_type TEXT NULL` + `report_date DATE NULL`, `corp_code` DROP NOT NULL, two partial CHECKs (`ck_decision_cards_report_type`, `ck_decision_cards_corp_or_report`), partial index `ix_decision_cards_report (report_type, report_date) WHERE report_type IS NOT NULL`.
- **Analysis-card invariant preserved** (T-05-01-01): a NULL-corp analysis card (`report_type IS NULL`) is rejected by `ck_decision_cards_corp_or_report`; a NULL-corp briefing row is accepted.
- **Downgrade footgun handled** (T-05-01-02): downgrade `DELETE`s `report_type IS NOT NULL` rows before restoring `corp_code NOT NULL`; up→down→up roundtrip verified.
- **Live DB migrated to 0009** (blocking gate) — `alembic current == 0009`, new columns + partial index present in the live schema.
- **ORM parity + drift guard green**: `DecisionCard` gains `report_type`/`report_date` + `corp_code nullable=True`; `test_orm_round_trip` passes.

## Task Commits

1. **Task 1: Migration 0009 + ORM DecisionCard parity** - `892e780` (feat)
2. **Task 2: [BLOCKING] Apply migration 0009 to live DB** - no repo artifact (DB-state gate; `alembic upgrade head` → live DB 0008→0009)
3. **Task 3: Migration 0009 roundtrip test + 0007 corp_code assertion flip** - `10038f8` (test)

**Plan metadata:** committed with SUMMARY/STATE/ROADMAP (docs: complete plan)

## Files Created/Modified

- `src/db/migrations/versions/0009_briefing_report_type.py` - migration 0009 (report_type/report_date columns, corp_code DROP NOT NULL, 2 partial CHECKs, partial index; downgrade DELETEs briefing rows before restoring NOT NULL)
- `src/db/entity_models.py` - `DecisionCard` ORM: added `report_type`/`report_date`, `corp_code` → `nullable=True` (column-set parity for `test_orm_round_trip`)
- `tests/db/test_migration_0009.py` - up/down/up roundtrip, both CHECK constraints, partial-index-is-partial assertion, behavior: NULL-corp briefing INSERT succeeds / NULL-corp analysis card rejected
- `tests/db/test_migration_0007.py` - `corp_code` nullable assertion `is False` → `is True` (0009 legitimately relaxes it — expected change, not drift)

## Decisions Made

- **Two columns (report_type + report_date DATE)** over a single KST-expression index — the `get_briefing` lookup is `WHERE report_type=? AND report_date=?`, and a dedicated DATE column is equality-matchable and timezone-safe (a `generated_at::date` under UTC drifts for late-KST rows). RESOLVES RESEARCH OQ2.
- **corp_code relaxed at DB level, invariant kept by partial CHECK.** The ORM class tracks column-set parity only; the CHECKs + partial index are DB-only (the parity test compares column names). No `__table_args__` change was needed.
- **`op.create_check_constraint`** is the correct ALTER-time helper (0007/0008 used inline `sa.CheckConstraint` at create-table) — first use of the ALTER-time form in this repo.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- **Windows cp949 default encoding** broke the plan's Task-1 verify one-liner (`open(...).read()` hit `UnicodeDecodeError` on the migration's em-dash/box-drawing chars). Re-ran the identical AST/shape check with `open(..., encoding='utf-8')` — a shell-encoding workaround, not a code change. The migration file itself is valid UTF-8 and Alembic parsed it cleanly.
- Per the environment notes, all `uv run ...` commands in the plan were executed via `.venv/Scripts/python.exe -m {pytest,alembic}` (uv unavailable in this session).

## Verification

- `pytest tests/db` — **30 passed** (full migration suite; includes the new 0009 tests + the 0007 parity/relaxed-corp assertion).
- `pytest tests/db/test_migration_0009.py tests/db/test_migration_0007.py` — **9 passed**.
- `alembic current` — **0009 (head)** on the live DB.
- `test_orm_round_trip` — ORM↔DB column-set parity for `decision_cards` green.

## Known Stubs

None. This plan is a schema migration + tests; no UI or data-source wiring. The downstream write/read paths (`save_briefing`, `get_briefing_row`, `list_cards_for_briefing`, `src/briefing/`, `get_briefing` wiring) are later plans (05-02..05-05) and out of scope here.

## Next Phase Readiness

- Schema foundation for SC#2 is applied and roundtrip-tested. Plans 05-02+ can now add the `save_briefing`/`get_briefing_row`/`list_cards_for_briefing` store trio and the `src/briefing/` render logic against the live 0009 schema.
- No blockers. Docker Postgres is at 0009; testcontainers apply 0009 via `alembic upgrade head`.

## Self-Check: PASSED

- Created files exist: `0009_briefing_report_type.py`, `test_migration_0009.py` (FOUND); modified `entity_models.py`, `test_migration_0007.py` (FOUND).
- Task commits exist: `892e780` (Task 1, FOUND), `10038f8` (Task 3, FOUND).
- Live DB gate: `alembic current == 0009` (Task 2, DB-state gate — no repo artifact by design).

---
*Phase: 05-briefing-renderer*
*Completed: 2026-07-16*
