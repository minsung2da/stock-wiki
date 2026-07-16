---
phase: 05-briefing-renderer
plan: 05
subsystem: briefing-weekly
tags: [briefing, weekly, net-aggregation, pre-materialize, no-recompute, coverage, sc4, d07, d08, deterministic]

# Dependency graph
requires:
  - phase: 05-briefing-renderer (plan 02)
    provides: "cards.store.get_daily_briefings_in_range (the <=7 daily source rows) + save_briefing (NULL-corp weekly write) + get_briefing_row (self-describing reconstruct) + BriefingRow model"
  - phase: 05-briefing-renderer (plan 03)
    provides: "the LOCKED flat entries[] daily schema + the DICT-keyed _priority_key + render_body_md + load_held_tickers + _kst_close_on + _MAX_ENTRIES — reused UNCHANGED over payload['entries']"
  - phase: 05-briefing-renderer (plan 04)
    provides: "the wired get_briefing(date,'weekly') read path — a pure SELECT of the stored weekly row (the SC#4 read side)"
provides:
  - "src/briefing/weekly.py — aggregate_net (per-ticker NET diff over <=7 daily payloads, flip-flop drop D-07, best-effort coverage D-08) + generate_weekly_briefing (pre-materialized weekly_briefing row + source_reports + no-recompute SC#4)"
  - "generate_weekly_briefing exported from briefing/__init__.py"
affects: [mcp_v2.get_briefing, briefing.__init__]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pre-materialized weekly digest: aggregate the week's <=7 daily payloads ONCE at generation, store the result; get_briefing(weekly) is a pure SELECT that never recomputes (SC#4 — byte-stable after source deletion)"
    - "NET-change aggregation over FLAT dicts: group payload['entries'] by ticker, diff earliest vs latest (stance flip OR conviction move >= 0.10); intra-week flip-flops net to no-change and are DROPPED (D-07)"
    - "Reuse the daily DICT-keyed _priority_key over the flat net-entry dicts — no DecisionCard object at weekly time, no .card attribute access anywhere (the SC#4 no-recompute enabler)"
    - "Best-effort coverage: roll up whatever dailies exist, record {present, expected:7, missing_dates}; a missing day is a coverage gap, NOT a no-change ticker (D-08)"

key-files:
  created:
    - src/briefing/weekly.py
    - tests/briefing/test_weekly.py
  modified:
    - src/briefing/__init__.py

key-decisions:
  - "_CONVICTION_DELTA = 0.10 module constant is the same-stance NET threshold (D-07): a same-stance drift below it nets out; a stance flip always counts. A small, decomposable, module-level number (Veto #4 spirit) — never a black-box score"
  - "net entries carry an extra intra_week_events count (# of that ticker's daily entries) on top of the LOCKED daily schema keys; _priority_key/render_body_md ignore the extra key, so the reuse contract holds"
  - "week_anchor IS week_end (the get_briefing query key, 05-RESEARCH A3); the week is the 7-day window [week_end-6d, week_end]. as_of=_kst_close_on(week_end), expires_at=_kst_close_on(week_end+7d)"
  - "the change string is the stance arrow (HOLD->SELL) when the stance flipped, else a conviction-move note (conviction 0.40->0.75) when a same-stance conviction move survived the threshold"
  - "empty week still writes a real row (entries=[], source_reports=[], coverage.present=0) so get_briefing(weekly) is found=True — never an empty page (mirrors the daily SC#6 policy)"

requirements-completed: [SC#4]

# Metrics
duration: 22min
completed: 2026-07-16
---

# Phase 5 Plan 05: Weekly Roll-Up Summary

**`src/briefing/weekly.py` closes Phase 5: it aggregates the week's <=7 daily briefings into a per-ticker NET-change digest (start-of-week vs end-of-week stance+conviction), DROPS intra-week flip-flops that net to no-change (D-07), rolls up whatever dailies exist with a best-effort `coverage: N/7` (D-08), and PRE-MATERIALIZES the result into a `report_type='weekly_briefing'` row with `source_reports` pointers. The read path (`get_briefing(weekly)`, wired in 05-04) is a pure SELECT of the stored row — `test_no_recompute` deletes every source daily AFTER generation and proves the weekly's entries are returned byte-identical, so the read NEVER recomputes (SC#4). All aggregation and sorting operate on FLAT dicts, reusing the daily's DICT-keyed `_priority_key` unchanged over `payload['entries']` — there is no `DecisionCard` object and no `.card` access anywhere.**

## Performance

- **Duration:** ~22 min
- **Tasks:** 2 (both TDD: RED test → GREEN implementation → atomic commit)
- **Files:** 3 (2 created, 1 modified)

## Accomplishments

- **`aggregate_net(daily_rows, *, week_start, week_end) -> (list[dict], dict)`** (Task 1) — groups every `payload["entries"]` across the <=7 daily rows by ticker (report_date order preserved, since `get_daily_briefings_in_range` returns rows ordered by `report_date`). For each ticker: `start_state` = earliest entry's (stance, conviction), `end_state` = latest entry's. NET change = `start_stance != end_stance` OR `abs(end_conv - start_conv) >= _CONVICTION_DELTA` (0.10). Tickers with no net change are DROPPED (intra-week flip-flops net out — D-07; the daily rows keep the detail). Each surviving entry is a FLAT dict in the LOCKED daily schema (`ticker/name/event_class/change/evidence/stance/conviction/why_now/why_not/card_id`) carrying the end-of-week state, plus an `intra_week_events` count. Coverage (D-08) = `{present: len(rows), expected: 7, missing_dates: [...]}` over the 7-day window — a missing day is a coverage gap, never a no-change ticker.
- **`generate_weekly_briefing(week_anchor, *, engine=None, held_tickers=None) -> BriefingRow`** (Task 2) — the orchestrator: `week_end = week_anchor`, `week_start = week_end - 6d`; loads `store.get_daily_briefings_in_range(engine, week_start, week_end)`; calls `aggregate_net`; priority-sorts the flat net entries by reusing the daily DICT-keyed `_priority_key` (`sorted(net_entries, key=lambda e: _priority_key(e, held))`) and truncates to `_MAX_ENTRIES` (10); builds a self-describing payload = `{card_id/report_type/report_date/generated_at/as_of/expires_at (ISO scalars), entries, source_reports:[{date, card_id} × <=7], coverage}`; persists a `weekly_briefing` `BriefingRow` (`report_date=week_end`, `expires_at=week_end+7d`) via `store.save_briefing`. `body_md = render_body_md(net_entries)` (reuses the daily 6-column table; empty week → the one-line no-change body). Even an empty week writes a real row so `get_briefing` is `found=True`.
- **Package export** — `from .weekly import generate_weekly_briefing` appended to `src/briefing/__init__.py`; `__all__` now `["generate_daily_briefing", "generate_weekly_briefing"]`.

## Task Commits

1. **Task 1: weekly NET aggregation — per-ticker start/end diff, flip-flop drop, coverage (D-07/D-08)** — `a04a7ca` (feat)
2. **Task 2: generate_weekly_briefing orchestrator + pre-materialize + no-recompute (SC#4)** — `225ff42` (feat)

## Files Created/Modified

- `src/briefing/weekly.py` — `aggregate_net` + `generate_weekly_briefing`; ~215 lines, deterministic, LLM-free. Reuses `_priority_key`/`render_body_md`/`load_held_tickers`/`_kst_close_on`/`_MAX_ENTRIES` from `daily.py` (no reimplementation).
- `src/briefing/__init__.py` — exports `generate_weekly_briefing`.
- `tests/briefing/test_weekly.py` — 8 tests: `test_net_change` (flip-flop dropped / genuine HOLD→SELL retained + intra_week_events), `test_net_change_conviction_move_retained_within_threshold_dropped`, `test_coverage` (5/7 present → 2 missing dates), `test_no_recompute` (SC#4 — delete source dailies → get_briefing weekly returns stored entries unchanged), `test_source_reports_and_coverage_pre_materialized`, `test_priority_sorted_and_truncated_to_ten` (held-first + <=10), `test_empty_week_writes_real_row`, `test_generate_weekly_briefing_exported`.

## Deviations from Plan

None — the plan executed as written. `aggregate_net` returns flat entry-dicts (not `ChangeEvent` objects) and the reused `_priority_key` sorts them directly, exactly as the plan and critical reminders specified. No Rule 1/2/3 auto-fixes were required; no Rule 4 architectural changes; no authentication gates.

## Verification

- `pytest tests/briefing/test_weekly.py` — **8 passed** (net_change + conviction-threshold + coverage + no_recompute + source_reports/coverage + priority/truncate + empty-week + export).
- `pytest tests/briefing` — **40 passed** (weekly 8 + daily 6 + diff 5 + priority 7 + render 7 + store_briefing 7; no regression across the phase).
- `ruff check src/briefing/weekly.py src/briefing/__init__.py tests/briefing/test_weekly.py` — **All checks passed** (line-length 100, import order, F/B/SIM).
- **SC#4 no-recompute proven:** `test_no_recompute` generates a weekly, then `DELETE FROM decision_cards WHERE report_type='daily_briefing'`, then calls the 05-04-wired `get_briefing(week_end,'weekly')` and asserts the returned entries equal the stored entries — the read is a pure SELECT of the pre-materialized row.
- **No `.card` access at weekly time:** all aggregation/sort operates on `payload['entries']` flat dicts; the daily DICT-keyed `_priority_key` is imported and reused unchanged.
- **Full suite:** `pytest` → **859 passed, 4 failed, 2 skipped** (17m10s). The 4 failures are pre-existing full-suite test-ordering/state pollution (torch-import order in `test_tokenizer`, alembic session-engine state in two migration downgrade tests) plus one live external DART API probe (`test_dart_fss_report_body_shape`). **All 4 are unrelated to this plan** — each passes in isolation and passes alongside the new `test_weekly.py` (verified: the 3 non-live tests → 3 passed isolated, 11 passed alongside weekly). Logged to `deferred-items.md`; NOT fixed (SCOPE BOUNDARY).
- Two pre-existing deprecation warnings (alembic `path_separator`, authlib `jose`) are unrelated to this plan (out of scope).

## Deferred Issues

Out-of-scope full-suite failures logged to `.planning/phases/05-briefing-renderer/deferred-items.md` (torch import test isolation + alembic migration-downgrade session-state pollution + a live DART API probe). Recommend a dedicated test-isolation cleanup pass; not a Phase-5 correctness issue.

## Known Stubs

- **`entry['name']` is carried from the daily entry (currently always `None`)** — a `DecisionCard` carries no entity name, so the 종목 cell renders the bare ticker (inherited 05-03 known-stub; `render_body_md` already handles a non-null name). Does NOT block the weekly goal — the digest is fully functional with tickers.

## Next Phase Readiness

- **Phase 5 is COMPLETE** — all 6 SCs delivered across 05-01..05-05: migration 0009 (SC#2), the store surface (SC#1/2), the daily generator (SC#1/2/3/6), wired `get_briefing` (SC#5), and now the weekly roll-up (SC#4). The read side was already satisfied by construction in 05-04; this plan adds the pre-materialized write.
- **Scheduling** (which day the weekly covers, kickoff cadence) is deferred to Phase 9 ops (systemd.timer / Claude Schedule) per 05-CONTEXT — out of Phase 5 scope.
- No blockers. Live DB at 0009; testcontainers apply 0009 via `alembic upgrade head`.

## Self-Check: PASSED

- Created files exist: `src/briefing/weekly.py`, `tests/briefing/test_weekly.py` (FOUND).
- Modified file present: `src/briefing/__init__.py` (FOUND).
- Task commits exist: `a04a7ca` (Task 1), `225ff42` (Task 2) — both FOUND in git log.

---
*Phase: 05-briefing-renderer*
*Completed: 2026-07-16*
