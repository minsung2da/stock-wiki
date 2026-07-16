---
phase: 05-briefing-renderer
plan: 04
subsystem: mcp_v2-get_briefing
tags: [mcp, get_briefing, delegate-to-store, veto13, sc3-ast-guard, asvs-v5, pydantic]

# Dependency graph
requires:
  - phase: 05-briefing-renderer (plan 01)
    provides: "live 0009 schema — report_type/report_date DATE columns the get_briefing lookup matches by equality"
  - phase: 05-briefing-renderer (plan 02)
    provides: "cards.store.get_briefing_row(engine, report_type, report_date) -> BriefingRow | None + BriefingRow self-describing-payload reconstruction contract"
  - phase: 05-briefing-renderer (plan 03)
    provides: "the daily_briefing self-describing payload shape (entries[] + scalar metadata) get_briefing reads back"
  - phase: 03-mcp-tool-surface
    provides: "the honest-empty get_briefing scaffold + Briefing model (no body_md field) + card.py delegate-to-store pattern + the SC#3 no-run-sql AST guard / 10-tool registry"
provides:
  - "wired src/mcp_v2/tools/briefing.py — get_briefing delegates the SELECT to cards.store.get_briefing_row (no inline text()), maps public type daily/weekly -> stored report_type daily_briefing/weekly_briefing, validates the date as ISO-8601 (ASVS V5), returns entries only (Veto #13)"
  - "tests/mcp_v2/test_briefing_wired.py — DB-backed wired tests (found=True + entries; empty DB -> found=False; type->report_type mapping; bad type/date -> InvalidArgument; test_no_body_leak)"
affects: [briefing.weekly, mcp_v2.get_briefing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "MCP read tool delegates ALL SQL to cards.store (no inline text() in src/mcp_v2) — the SC#3 AST guard stays green; mirrors get_decision_card->store.get_active"
    - "Public param -> stored enum mapping (daily/weekly -> daily_briefing/weekly_briefing) done in the tool; the store SELECT is a parameterized constant"
    - "ASVS V5 input validation BEFORE the DB bind: date.fromisoformat parse gates the report_date bind; a bad date raises InvalidArgument before get_engine() is reached"
    - "Filter-before-context by construction: the Briefing model has NO body_md field, so entries-only is enforced at the type layer, not by a runtime projection (Veto #13)"

key-files:
  created:
    - tests/mcp_v2/test_briefing_wired.py
  modified:
    - src/mcp_v2/tools/briefing.py
    - tests/mcp_v2/test_portfolio_briefing.py

key-decisions:
  - "date param shadows datetime.date, so the class is imported as `from datetime import date as _date` and validation is `_date.fromisoformat(date)` — the plan's literal `date.fromisoformat(date)` would call str.fromisoformat (AttributeError). Same intent, correct binding (Rule 3 blocking fix)."
  - "The wired test follows the test_card.py idiom (pytestmark=pytest.mark.db + pg_clean seed): get_engine() reads DATABASE_URL which the session pg_engine fixture points at the same testcontainer pg_clean seeds — no get_engine monkeypatch needed (the plan's fallback was only 'if the engine cannot be injected via a fixture')."
  - "Added two mapping-integrity tests beyond the plan's minimum (weekly row read + daily-query-does-not-read-weekly-row) to prove the type->report_type mapping is real, not just that a daily row round-trips."

requirements-completed: [SC#5]

# Metrics
duration: 12min
completed: 2026-07-16
---

# Phase 5 Plan 04: get_briefing Wiring Summary

**`get_briefing` is now wired to actually read daily/weekly briefing rows (SC#5): it maps the public `type` to the stored `report_type`, validates the `date` as ISO-8601 before any DB access (ASVS V5), delegates the SELECT to `cards.store.get_briefing_row` (no inline `text()` — the SC#3 AST guard stays green), and returns the structured `entries` ONLY — the `Briefing` model still has no `body_md` field, so the full 6-column table never reaches context (Veto #13). The Phase-3 honest-empty guard is retired in favor of DB-backed wired tests — an EXPECTED replacement, not a regression.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 2 (Task 1 tool wiring, Task 2 DB-backed tests)
- **Files:** 3 (1 created, 2 modified)

## Accomplishments

- **`get_briefing` wired (Task 1)** — the honest-empty scaffold is replaced with a real delegate. Order: the `_VALID_TYPES` guard FIRST (unknown type → `InvalidArgument`), then `date` is validated via `_date.fromisoformat(date)` inside try/except (bad date → `InvalidArgument`, ASVS V5 — before `get_engine()` is reached), then `report_type = _REPORT_TYPE[type]` (`daily → daily_briefing`, `weekly → weekly_briefing`), then `store.get_briefing_row(get_engine(), report_type, parsed_date)`. Returns `Briefing(date, type, found=row is not None, entries=(row.payload["entries"] if row else []))`.
- **No inline SQL** — all DB access is the single `store.get_briefing_row` call; `briefing.py` contains no `text(` Call node (the `text()` mentions are docstring prose only). The SC#3 AST guard + 10-tool registry (`get_briefing` still registered via the `mcp.tool(...)` call form) stay green.
- **Veto #13 by construction** — no `body_md` field was added to `Briefing`; `entries` is the only payload projection. `test_no_body_leak` asserts `'body_md' not in Briefing.model_fields`.
- **DB-backed wired tests (Task 2)** — `tests/mcp_v2/test_briefing_wired.py` seeds a `daily_briefing` (and a `weekly_briefing`) row via `store.save_briefing` with a self-describing payload, then asserts: a seeded row → `found=True` with the stored `entries` (SC#5); an empty DB → `found=False, entries=[]`; a weekly row does NOT answer a daily query (the `type→report_type` mapping is real); bad `type`/non-ISO `date` → `InvalidArgument`; and `test_no_body_leak` (Veto #13).
- **Honest-empty guard retired** — `test_portfolio_briefing.py` lost the three Phase-3 tests (`test_get_briefing_positively_returns_empty_model`, `test_get_briefing_weekly_also_empty`, and the `report_type`-absence AST guard `test_get_briefing_does_not_reference_report_type`) that asserted the no-data phase; the DB-backed wired tests supersede them (EXPECTED change per 05-RESEARCH §State of the Art / step 5). The no-DB `test_get_briefing_bad_type_raises_invalid_argument` was KEPT (it needs no engine and still holds).

## Task Commits

1. **Task 1: wire get_briefing to delegate to store.get_briefing_row** — `93c5bcd` (feat)
2. **Task 2: DB-backed wired tests; retire the honest-empty guard** — `eafb105` (test)

## Files Created/Modified

- `src/mcp_v2/tools/briefing.py` — the wired `get_briefing` (type guard → ISO-8601 date validation → `type→report_type` map → `store.get_briefing_row` delegate → entries-only `Briefing`); module docstring updated to describe the Phase-5 delegate (dropped the misleading "honest empty" prose); registration line preserved (tool count stays 10).
- `tests/mcp_v2/test_briefing_wired.py` — 7 tests: daily found=True+entries, empty DB found=False, weekly found=True, daily-does-not-read-weekly, bad type, bad date, no-body-leak. `pytestmark = pytest.mark.db`; seeds via `store.save_briefing` on `pg_clean`.
- `tests/mcp_v2/test_portfolio_briefing.py` — removed the three obsolete honest-empty `get_briefing` tests + updated the module docstring to point at `test_briefing_wired.py`; kept `list_portfolio` tests and the no-DB bad-type guard.

## Deviations from Plan

### Auto-fixed (Rule 3 — blocking: the plan's literal validation code would not run)

**1. [Rule 3 - Blocking] `date.fromisoformat(date)` corrected to `_date.fromisoformat(date)`**
- **Found during:** Task 1
- **Issue:** the `date` parameter (a `str`) shadows `datetime.date`. The plan's literal `date.fromisoformat(date)` resolves to `str.fromisoformat` → `AttributeError`, so it would never perform the intended ISO-8601 validation.
- **Fix:** imported the class as `from datetime import date as _date` and validate with `_date.fromisoformat(date)`. Same intent (ASVS V5 date validation before the bind), correct name binding.
- **Files modified:** src/mcp_v2/tools/briefing.py
- **Commit:** 93c5bcd

### Auto-added (Rule 2 — mapping-integrity coverage)

**2. [Rule 2] Two extra wired tests proving the `type→report_type` mapping is real**
- **Found during:** Task 2
- **Issue:** the plan's minimum (found=True daily + empty found=False + bad type/date + no-body-leak) proves a daily row round-trips but does NOT prove that `weekly` maps to a distinct `report_type` — a bug that ignored `type` and always queried `daily_briefing` would pass the minimum.
- **Fix:** added `test_get_briefing_weekly_reads_weekly_row` (weekly row → found=True) and `test_get_briefing_daily_does_not_read_weekly_row` (a `weekly_briefing` row must NOT satisfy a daily query → found=False). These lock the mapping's correctness.
- **Files modified:** tests/mcp_v2/test_briefing_wired.py
- **Commit:** eafb105

No architectural deviations (no Rule 4). No authentication gates.

## Verification

- `pytest tests/mcp_v2/test_no_run_sql_guard.py -x` — **4 passed** (no `text()` in `briefing.py`; registry still EXACTLY the 10 locked names incl `get_briefing`).
- `pytest tests/mcp_v2/test_briefing_wired.py tests/mcp_v2/test_portfolio_briefing.py -q` — **11 passed** (found=True + entries; empty → found=False; type-mapping; bad type/date → InvalidArgument; no body leak; list_portfolio intact).
- `pytest tests/mcp_v2 -q` — **139 passed, 2 skipped** (no regression across the 10-tool surface; the 2 skips are pre-existing hybrid_search conditionals).
- `ruff check src/mcp_v2/tools/briefing.py tests/mcp_v2/test_briefing_wired.py tests/mcp_v2/test_portfolio_briefing.py` — **All checks passed**.
- `briefing.py` contains no `text(` Call node (SQL stays in `cards.store`); `Briefing` model unchanged (no `body_md` field added).
- Two pre-existing deprecation warnings (authlib `jose`, alembic `path_separator`) are unrelated to this plan (out of scope).

## Known Stubs

None. The tool is fully wired; the daily/weekly rows it reads are produced by 05-03 (daily) and 05-05 (weekly, next plan). `entry['name']` renders as `None` in the underlying daily payload (a 05-03 known-stub, the `name` field is optional) — that is upstream render nicety, not a `get_briefing` concern; the tool returns whatever `entries` the row carries verbatim.

## Next Phase Readiness

- **05-05 (weekly roll-up)** is the last Phase-5 plan: `get_briefing(date, type='weekly')` is already wired to read a `weekly_briefing` row (the mapping + delegate are proven), so 05-05 only needs to WRITE the pre-materialized weekly row (`source_reports` + NET entries) — the read path is done (SC#4 read side satisfied by construction: `get_briefing` SELECTs the stored row and returns `payload['entries']`, never recomputing).
- No blockers. Live DB at 0009; testcontainers apply 0009 via `alembic upgrade head`.

## Self-Check: PASSED

- Created file exists: `tests/mcp_v2/test_briefing_wired.py` (FOUND).
- Modified files present: `src/mcp_v2/tools/briefing.py`, `tests/mcp_v2/test_portfolio_briefing.py` (FOUND).
- Task commits exist: `93c5bcd` (Task 1, FOUND), `eafb105` (Task 2, FOUND).

---
*Phase: 05-briefing-renderer*
*Completed: 2026-07-16*
