---
phase: 05-briefing-renderer
plan: 02
subsystem: cards-store + briefing-models
tags: [sqlalchemy, postgres, pydantic, decision_cards, briefing, store, enumeration, jsonb, kst]

# Dependency graph
requires:
  - phase: 05-briefing-renderer (plan 01)
    provides: "live 0009 schema — report_type/report_date columns + nullable corp_code + partial CHECK ck_decision_cards_corp_or_report; the NULL-corp briefing write target"
  - phase: 02-decision-card-schema-storage
    provides: "src/cards/store.py CRUD template (save_card/get_active/walk_supersedes/invalidate) + DecisionCard model + tests/cards fixtures"
provides:
  - "BriefingRow Pydantic model (src/briefing/models.py) — a SEPARATE model, never reuses/extends DecisionCard (Veto #1/#4)"
  - "cards.store.save_briefing — NULL-corp briefing write path (separate from save_card, no supersede branch)"
  - "cards.store.get_briefing_row — active briefing SELECT (the get_briefing MCP delegate, SC#5 enabler)"
  - "cards.store.list_cards_for_briefing -> BriefingCandidates NamedTuple — date-D collect set (newly-generated/expiring/invalidated), the RESEARCH enumeration gap closed (SC#1 enabler)"
  - "cards.store.get_daily_briefings_in_range — daily rows in [start,end] ordered by report_date (weekly source, SC#4 enabler)"
  - "invalidate() invalidated_at KST-ISO payload stamp (OQ1 option a) + DecisionCard.invalidated_at optional field"
  - "tests/briefing shared fixture (>=11 seeded tickers + make_card factory) for daily/weekly plans"
affects: [briefing.daily, briefing.weekly, mcp_v2.get_briefing, cards.store, cards.models]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "A NULL-corp row kind persisted via a SEPARATE typed write path (save_briefing) rather than reusing save_card/DecisionCard — the landmine resolution"
    - "Self-describing payload: a briefing payload carries its own scalar metadata (card_id/report_type/report_date/generated_at/as_of/expires_at) so get_briefing_row reconstructs a BriefingRow from payload+body_md alone"
    - "KST ::date enumeration — (col AT TIME ZONE 'Asia/Seoul')::date = :d, never a UTC ::date (timezone footgun)"
    - "Nested jsonb_set to stamp TWO payload keys (invalidation_reason + invalidated_at) in one UPDATE"

key-files:
  created:
    - src/briefing/__init__.py
    - src/briefing/models.py
    - tests/briefing/__init__.py
    - tests/briefing/conftest.py
    - tests/briefing/test_store_briefing.py
  modified:
    - src/cards/store.py
    - src/cards/models.py

key-decisions:
  - "BriefingRow is a SEPARATE model (extra='forbid'), never extends DecisionCard — no corp_code/ticker/decision/assumptions (inventing a stance/conviction violates Veto #1/#4)"
  - "save_briefing stores json.dumps(row.payload) verbatim; the payload is self-describing so get_briefing_row can reconstruct the scalars from it (the plan's explicit reconstruction source)"
  - "invalidated-today resolved via OQ1 option (a): stamp invalidated_at into payload (no new DB column); list_cards_for_briefing scans (payload->>'invalidated_at')::timestamptz KST ::date"
  - "invalidated_at added to _PAYLOAD_EXCLUDE (mirrors invalidation_reason) so a freshly-saved payload stays §3-clean — only invalidate() writes it"

patterns-established:
  - "Pattern: a new decision_cards row KIND gets its own typed model + save_* write path + get_* read path, never a reused analysis-card helper"
  - "Pattern: enumeration helpers exclude briefing rows via AND report_type IS NULL so a briefing never enumerates itself"

requirements-completed: []

# Metrics
duration: 15min
completed: 2026-07-16
---

# Phase 5 Plan 02: Briefing Store Surface Summary

**The typed store surface for briefing rows — a SEPARATE `BriefingRow` model + a `save_briefing`/`get_briefing_row`/`list_cards_for_briefing`/`get_daily_briefings_in_range` trio + an `invalidate()` `invalidated_at` stamp — is the ONLY way app code touches the new `report_type` rows (Veto #7), and closes the two store gaps 05-RESEARCH flagged (no enumeration helper, no invalidation timestamp).**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-16T12:42Z
- **Completed:** 2026-07-16T12:57Z
- **Tasks:** 3 (2 store/model + 1 test)
- **Files:** 7 (5 created, 2 modified)

## Accomplishments

- **`BriefingRow`** (`src/briefing/models.py`, `extra='forbid'`) — a SEPARATE model that declares only what a digest legitimately has (`card_id`/`report_type`/`report_date`/`generated_at`/`as_of`/`expires_at`/`payload`/`body_md`). It imports nothing from `cards.models` and carries NO `corp_code`/`ticker`/`decision`/`assumptions` (Veto #1/#4 / Pitfall #1). `report_type` is a `Literal['daily_briefing','weekly_briefing']`.
- **`save_briefing`** — a NULL-corp write path separate from `save_card`: `_INSERT_BRIEFING_SQL` binds `corp_code`/`ticker=NULL`, `report_type`/`report_date` from the row, `status='active'`, and the payload via `json.dumps` → `CAST(:payload AS jsonb)` (Pitfall #3). No supersede branch. `schema_version` left to the column server_default.
- **`get_briefing_row`** — the future `get_briefing` MCP delegate (SC#5): `SELECT payload, body_md ... ORDER BY generated_at DESC LIMIT 1`, reconstructed into a `BriefingRow` from the self-describing payload.
- **`list_cards_for_briefing`** — returns a `BriefingCandidates` NamedTuple `(newly_generated, expiring, invalidated)`; three KST-bounded parameterized SELECTs, each `AND report_type IS NULL` so a briefing never enumerates itself. Closes the RESEARCH enumeration gap (SC#1 enabler).
- **`get_daily_briefings_in_range`** — `daily_briefing` rows in `[start,end]` ordered by `report_date` (the weekly's pre-materialized source, SC#4 enabler).
- **`invalidate()` `invalidated_at` stamp** — nested `jsonb_set` now writes a KST-ISO `invalidated_at` alongside `invalidation_reason` (OQ1 option a — no new column) so "invalidated on date D" is queryable. `DecisionCard` gains an optional `invalidated_at: str | None` (payload-only) + a `_PAYLOAD_EXCLUDE` entry so a post-stamp reconstruct does not trip `extra='forbid'`.
- **Shared test fixture** — `tests/briefing/conftest.py` seeds 11 distinct entities + ticker/name aliases (`briefing_engine`) and a `make_card` factory, so the daily truncation (>10) / priority / diff plans (05-03) can stand up ≥11 active cards without a real `portfolio.md`.

## Task Commits

1. **Task 1: BriefingRow model + save_briefing write path** — `70d58d6` (feat)
2. **Task 2: read/enum store helpers + invalidate() invalidated_at stamp** — `631878b` (feat)
3. **Task 3: multi-entity conftest + store_briefing DB tests** — `38bb974` (test)

**Plan metadata:** committed with SUMMARY/STATE/ROADMAP (docs: complete plan)

## Files Created/Modified

- `src/briefing/__init__.py` — briefing package docstring (later plans append daily/weekly exports)
- `src/briefing/models.py` — `BriefingRow` (extra='forbid'), SEPARATE from `DecisionCard`
- `src/cards/store.py` — `_INSERT_BRIEFING_SQL` + `save_briefing`; `_SELECT_BRIEFING_ROW_SQL` + `get_briefing_row`; 3 enumeration SELECTs + `BriefingCandidates` + `list_cards_for_briefing`; `_SELECT_DAILIES_IN_RANGE_SQL` + `get_daily_briefings_in_range`; `_INVALIDATE_SQL` nested `jsonb_set` invalidated_at stamp; `_KST` module const; `__all__` + `_PAYLOAD_EXCLUDE` extended
- `src/cards/models.py` — `DecisionCard.invalidated_at: str | None = None` (payload-only, no DB column; mirrors invalidation_reason)
- `tests/briefing/__init__.py` — empty package marker
- `tests/briefing/conftest.py` — `briefing_engine` (11-ticker seed) + `seeded_entities` + `make_card` factory
- `tests/briefing/test_store_briefing.py` — 8 db-marked tests (NULL-corp save+read round-trip, newest-per-date, analysis-card rejection, enumeration buckets + briefing-row exclusion, range fetch)

## Decisions Made

- **BriefingRow is a separate model.** The five `DecisionCard` required fields (`corp_code`/`ticker`/`decision`/`assumptions`/a per-ticker thesis) have no honest digest value; inventing a stance/conviction violates Veto #1/#4. The landmine resolution (05-RESEARCH §THE LANDMINE) is a separate typed model + a separate `save_briefing` write path.
- **Self-describing payload.** `save_briefing` stores `json.dumps(row.payload)` verbatim (the plan's explicit instruction), and `get_briefing_row`/`get_daily_briefings_in_range` reconstruct the `BriefingRow` scalars FROM the payload — so the payload must carry `card_id`/`report_type`/`report_date`/`generated_at`/`as_of`/`expires_at`. Documented on `BriefingRow.payload` and `_row_to_briefing`; the daily payload schema (05-03) will honor it.
- **Invalidated-today = OQ1 option (a).** Stamp `invalidated_at` (KST ISO) into payload, no new column; the enumeration scans `(payload->>'invalidated_at')::timestamptz AT TIME ZONE 'Asia/Seoul' ::date = :d`. Card volume is low, so a scan is fine (RESEARCH A2).
- **`get_daily_briefings_in_range` has no `status='active'` filter** — followed the plan's literal WHERE (report_type + report_date BETWEEN + ORDER BY). De-duplication of same-date dailies is a 05-05 (weekly) concern.

## Deviations from Plan

### Auto-added (Rule 2 — consistency/correctness)

**1. [Rule 2] Added `invalidated_at` to `_PAYLOAD_EXCLUDE`**
- **Found during:** Task 2
- **Issue:** the plan says the new `DecisionCard.invalidated_at` field "mirrors invalidation_reason". `invalidation_reason` is in `_PAYLOAD_EXCLUDE` (so a freshly-saved payload does not carry a null value and stays exactly the §3 schema). Omitting `invalidated_at` from the exclude set would leave `"invalidated_at": null` in every freshly-saved analysis card's payload.
- **Fix:** added `invalidated_at` to `_PAYLOAD_EXCLUDE` so only `invalidate()` writes it (full mirror of `invalidation_reason`). Functionally the enumeration works either way (a null `invalidated_at` never matches the date cast), but this keeps saved payloads §3-clean.
- **Files modified:** src/cards/store.py
- **Commit:** 631878b

## Issues Encountered

- **`uv` unavailable in this session** (per environment notes) — all `uv run python`/`uv run pytest` in the plan were executed via `.venv/Scripts/python.exe -m {pytest}` (and `PYTHONPATH=src .venv/Scripts/python.exe -c ...` for the import smoke checks, since `src` is on `sys.path` only under pytest).
- **Two ruff findings in the new test file** (`SIM117` nested `with`, one `E501`) were pre-fixed before the Task-3 commit so the `ruff --fix` pre-commit hook had nothing to change. A pre-existing `E501` at `src/cards/models.py:88` (the untouched `numeric_facts` line) was left as-is — out of scope (SCOPE BOUNDARY).

## Verification

- `pytest tests/briefing -x` — **8 passed** (store_briefing DB tests + the ≥11-ticker seed assertion).
- `pytest tests/cards -x` — **25 passed** (the `invalidate()` nested-`jsonb_set` change did not break the Phase-2 store tests; the returned card still round-trips under `extra='forbid'`).
- `pytest tests/mcp_v2/test_no_run_sql_guard.py` — **passed** (all briefing SQL stays in `cards.store`; nothing leaked into `src/mcp_v2`).
- `ruff check src/briefing tests/briefing` — **All checks passed**.
- Import smoke: `from briefing.models import BriefingRow`, `cards.store.{save_briefing,get_briefing_row,list_cards_for_briefing,get_daily_briefings_in_range}` present in `__all__` + callable; `DecisionCard.invalidated_at` in model_fields; `BriefingRow` round-trips and rejects `corp_code` (extra='forbid').

## Known Stubs

None. This plan is a store surface + model + tests. The consumers — `src/briefing/daily.py` (05-03), `src/briefing/weekly.py` (05-05), and the `get_briefing` MCP wiring (05-04) — are later plans and out of scope here. `src/briefing/__init__.py` intentionally exports nothing yet (daily/weekly export lines are appended by 05-03/05-05).

## Next Phase Readiness

- The daily plan (05-03) can now enumerate via `list_cards_for_briefing`, diff via the existing `get_active`+`walk_supersedes`, and persist via `save_briefing`; the ≥11-ticker `briefing_engine` fixture + `make_card` factory are ready for its truncation/priority/diff tests.
- The wiring plan (05-04) has `get_briefing_row` as the store delegate for the `get_briefing` MCP tool (keeps SC#3's no-`text()`-in-mcp_v2 guard intact).
- The weekly plan (05-05) has `get_daily_briefings_in_range` as its pre-materialized source.
- No blockers. Live DB at 0009; testcontainers apply 0009 via `alembic upgrade head`.

## Self-Check: PASSED

- Created files exist: `src/briefing/__init__.py`, `src/briefing/models.py`, `tests/briefing/__init__.py`, `tests/briefing/conftest.py`, `tests/briefing/test_store_briefing.py` (all FOUND).
- Modified files present: `src/cards/store.py`, `src/cards/models.py` (FOUND).
- Task commits exist: `70d58d6` (Task 1, FOUND), `631878b` (Task 2, FOUND), `38bb974` (Task 3, FOUND).

---
*Phase: 05-briefing-renderer*
*Completed: 2026-07-16*
