---
phase: 05-briefing-renderer
plan: 03
subsystem: briefing-daily
tags: [briefing, daily, change-detection, prioritization, render, kst, pydantic, deterministic]

# Dependency graph
requires:
  - phase: 05-briefing-renderer (plan 01)
    provides: "live 0009 schema — report_type/report_date + nullable corp_code; the NULL-corp briefing write target"
  - phase: 05-briefing-renderer (plan 02)
    provides: "BriefingRow model + cards.store.{list_cards_for_briefing,get_active,walk_supersedes,save_briefing,get_briefing_row} + the ≥11-ticker briefing_engine/make_card fixtures + the self-describing-payload reconstruction contract"
  - phase: 02-decision-card-schema-storage
    provides: "DecisionCard/Decision/KeyClaim/Contradiction models — the diff + render sources"
  - phase: 04-analysis-runner
    provides: "runner.py _KST idiom + engine-defaulting entrypoint style (the daily orchestrator analog)"
provides:
  - "src/briefing/daily.py — classify_change (D-02/D-03) + build_entry (LOCKED flat entry schema) + _priority_key (dict-keyed D-01 sort) + render_body_md (6-column table) + generate_daily_briefing orchestrator"
  - "the LOCKED daily payload entries[] flat-dict schema {ticker,name,event_class,change,evidence,stance,conviction,why_now,why_not,card_id} — consumed unchanged by the weekly (05-05)"
  - "the DICT-keyed _priority_key(entry, held_tickers) callable — imported+reused unchanged by the weekly (05-05) over payload['entries'] (SC#4 no-recompute enabler)"
  - "load_held_tickers — held-first tier-1 with graceful degradation to set() when portfolio.md absent (D-01)"
  - "generate_daily_briefing exported from briefing/__init__.py"
affects: [briefing.weekly, mcp_v2.get_briefing, briefing.__init__]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Change-only digest: enumerate collect-set -> diff each vs the D-02 supersession-chain baseline -> classify into 4 event classes -> priority-sort -> truncate to 10 (never a per-ticker dump)"
    - "DICT-keyed sort over a FLAT entry schema so daily-render AND weekly-rollup sort the SAME shape with no DecisionCard object at weekly-sort time (SC#4 no-recompute)"
    - "Deterministic LLM-free render — every cell (변화/근거/제안/Why now/Why not) extracted directly from card structure (D-06); no subagents/anthropic import"
    - "Self-describing payload carries its own ISO-string scalars so store.get_briefing_row reconstructs a BriefingRow from payload+body_md alone"
    - "Graceful degradation: a missing/malformed portfolio.md collapses the held tier to set() (never raises) so the sort stays deterministic on tiers 2+3 (D-01)"

key-files:
  created:
    - src/briefing/daily.py
    - tests/briefing/test_diff.py
    - tests/briefing/test_priority.py
    - tests/briefing/test_render.py
    - tests/briefing/test_daily.py
  modified:
    - src/briefing/__init__.py

key-decisions:
  - "classify_change precedence follows D-01 event order (stance_flip > new_contradiction > new_high_conviction); expired_invalidated is assigned by the orchestrator's collect-set bucket, not the differ"
  - "_priority_key is DICT-keyed (no .card / attribute access) — the exact contract the weekly (05-05) reuses over payload['entries']; asserted directly on a plain dict in test_priority"
  - "daily payload is SELF-DESCRIBING (adds card_id/report_type/report_date/generated_at/as_of/expires_at ISO strings beyond the plan's literal {entries, generated_for}) — required for store.get_briefing_row/_row_to_briefing reconstruction (05-02 contract); Rule 2 auto-add"
  - "contradiction set-delta keyed on (bull, bear_claim) (RESEARCH A5); conviction-only drift is NOT a change (RESEARCH A4 — no conviction event class)"
  - "no-change day still writes a real row (entries=[], body '오늘 유의미한 변화 없음') so get_briefing is never found=False on a generated date (SC#6)"

requirements-completed: [SC#1, SC#2, SC#3, SC#6]

# Metrics
duration: 20min
completed: 2026-07-16
---

# Phase 5 Plan 03: Daily Briefing Generator Summary

**`src/briefing/daily.py` is the deterministic, LLM-free heart of Phase 5 — it collects ONLY what changed across `decision_cards` (stance flip / new contradiction / expired-invalidated / new high-conviction), diffs each card against its D-02 supersession-chain baseline, ranks by urgency-of-human-review via a DICT-keyed sort the weekly reuses unchanged, renders the ROADMAP-locked 6-column table (제안 = stance+conviction only, Veto #1), and persists a `report_type='daily_briefing'` row — writing a short real row even on a no-change day (SC#6).**

## Performance

- **Duration:** ~20 min
- **Tasks:** 3 (all TDD: RED test → GREEN implementation → atomic commit)
- **Files:** 6 (5 created, 1 modified)

## Accomplishments

- **`classify_change(active, prior)`** (Task 1) — the D-02/D-03 change differ over two `DecisionCard`s. `stance_flip` (`PRIOR→NEW`) > `new_contradiction` (`+N contradictions`, set-delta keyed on `(bull, bear_claim)`) > `new_high_conviction` (first card, conviction ≥ 0.8, `new (conv 0.83)`). A conviction-only drift and a first card < 0.8 both return `None` (noise). `ChangeEvent` is an internal-only NamedTuple (NOT persisted, NOT the sort shape).
- **`build_entry(event)`** (Task 2) — maps a `ChangeEvent` to the **LOCKED FLAT entry-dict** `{ticker, name, event_class, change, evidence, stance, conviction, why_now, why_not, card_id}`. `evidence`/`why_now` = the top-weighted `key_claim.text` (weight HIGH>MEDIUM>LOW>CONTEXT then confidence desc, D-06); `why_not` = the top `contradiction.bear_claim` or `—` (Veto #3).
- **`_priority_key(entry, held_tickers)`** (Task 2) — the D-01 3-level key `(held_rank, event_class_rank, -conviction)` operating on a **plain flat dict** with NO attribute access. This is the exact callable the weekly (05-05) imports and reuses over `payload['entries']` — asserted in `test_priority_key_is_dict_keyed` by calling it directly on `{"ticker","event_class","conviction"}`.
- **`load_held_tickers`** (Task 2) — resolves the held-first tier-1 set; an injected set for tests, else `Portfolio.load`; a missing/malformed `portfolio.md` (`PortfolioLoadError`/`ValidationError`) collapses to `set()` and **never raises** (D-01 degradation — the file is absent until Phase 6).
- **`render_body_md(entries)`** (Task 2) — the ROADMAP-locked table with header EXACTLY `종목 | 변화 | 근거 | 제안 | Why now | Why not`; the 제안 cell is `f"{stance} ({conviction:.2f})"` (bare stance + conviction, Veto #1). Empty entries render the one-line SC#6 no-change message.
- **`prioritize(events, held_tickers)`** (Task 2) — `build_entry` FIRST → sort by `_priority_key` → truncate to ≤10, so the same dict-keyed sort orders both daily and weekly.
- **`generate_daily_briefing(on_date, *, engine=None, held_tickers=None)`** (Task 3) — the orchestrator: `store.list_cards_for_briefing` → diff each newly-generated card via `get_active` + `walk_supersedes(...)[1]` → bucket expiring/invalidated as `expired_invalidated` → dedupe per corp (highest-priority class) → `prioritize` → persist a self-describing `daily_briefing` row via `store.save_briefing`. SC#6: an empty collect-set STILL writes a real row.

## Task Commits

1. **Task 1: change detection — classify_change (D-02/D-03)** — `a6198fd` (feat)
2. **Task 2: build_entry + dict-keyed prioritize (D-01) + 6-column render (D-04/05/06)** — `f69b25a` (feat)
3. **Task 3: generate_daily_briefing orchestrator + no-change short row (SC#6)** — `395636e` (feat)

## Files Created/Modified

- `src/briefing/daily.py` — the full daily generator (classify_change + build_entry + _priority_key + load_held_tickers + render_body_md + prioritize + generate_daily_briefing); 363 lines, LLM-free.
- `src/briefing/__init__.py` — exports `generate_daily_briefing` (`__all__`).
- `tests/briefing/test_diff.py` — 5 tests: stance flip, +N contradictions (set-delta / only-new), first-card rule (≥0.8 in, <0.8 out), no-change.
- `tests/briefing/test_priority.py` — 7 tests: dict-keyed key on a plain dict, held-first, event-class order, conviction desc, truncation to 10, no-portfolio degradation, deterministic sort.
- `tests/briefing/test_render.py` — 7 tests: exact header, 제안 regex `[A-Z]+ \(\d\.\d{2}\)`, why_not dash/top-contradiction, why_now top-weighted key_claim, empty short message, flat-key set.
- `tests/briefing/test_daily.py` — 6 tests (5 db): truncation to 10, no-change short row + get_briefing_row round-trip, report_type/date, stance-flip over a superseded prior, package export.

## Deviations from Plan

### Auto-added (Rule 2 — missing critical functionality for the round-trip contract)

**1. [Rule 2] Daily payload made SELF-DESCRIBING (scalar metadata keys added)**
- **Found during:** Task 3
- **Issue:** the plan's literal Task-3 action specified `payload={'entries': entries, 'generated_for': on_date.isoformat()}`. But `store.get_briefing_row` → `_row_to_briefing` (05-02) reconstructs a `BriefingRow` by reading `payload["card_id"]`, `["report_type"]`, `["report_date"]`, `["generated_at"]`, `["as_of"]`, `["expires_at"]` — the literal payload would raise `KeyError` on read-back. The 05-02 SUMMARY explicitly locked "the daily payload schema (05-03) will honor" the self-describing contract.
- **Fix:** the payload now carries those six scalars as ISO strings alongside `entries[]` + `generated_for`. `test_no_change_writes_short_row` and `test_persisted_row_is_daily_briefing` assert the `get_briefing_row` round-trip succeeds.
- **Files modified:** src/briefing/daily.py
- **Commit:** 395636e

### Auto-added (Rule 2 — render/robustness completeness, within plan intent)

**2. [Rule 2] `render_body_md([])` returns the SC#6 no-change line directly**
- **Found during:** Task 2
- **Issue:** the plan sets the no-change `body_md` in the orchestrator, but `render_body_md` over `entries=[]` would otherwise emit a header-only table.
- **Fix:** `render_body_md([])` returns `'오늘 유의미한 변화 없음'`, so `body_md=render_body_md(entries)` is uniform in the orchestrator and an empty page is impossible. Covered by `test_empty_entries_render_short_message`.
- **Files modified:** src/briefing/daily.py
- **Commit:** f69b25a

No architectural deviations (no Rule 4). No authentication gates.

## Verification

- `pytest tests/briefing -x` — **all green** (test_diff 5 + test_priority 7 + test_render 7 + test_daily 6 + the 05-02 store_briefing 8).
- `pytest tests/briefing tests/mcp_v2/test_no_run_sql_guard.py tests/cards` — **61 passed** (no regressions; the run-sql AST guard + 10-tool registry intact — all briefing SQL still lives in `cards.store`, `daily.py` emits no `text()`).
- `ruff check src/briefing tests/briefing` — **All checks passed** (line-length 100, import order, B/SIM).
- **LLM-free (D-06):** `daily.py` imports no `anthropic`/`openai`/`subagents` (only the docstring references the absence). Verified by grep.
- **`_priority_key` is dict-keyed:** asserted directly on `{"ticker","event_class","conviction"}` (no attribute access) so 05-05 imports it unchanged.
- **Body_md header matches SC#3 exactly:** `종목 | 변화 | 근거 | 제안 | Why now | Why not`.
- **Two pre-existing deprecation warnings** (alembic `path_separator`, authlib `jose`) are unrelated to this plan (out of scope).

## Known Stubs

- **`entry['name']` is always `None`** — a `DecisionCard` carries no entity name, so the 종목 cell renders the bare ticker. This is intentional and per the locked schema (`name` is optional); wiring an `entities.canonical_name` lookup is a render nicety deferred (not required by SC#3, which locks only the column set). `render_body_md` already handles a non-null `name` (`ticker name`) for when a future plan populates it. This does NOT block the plan goal — the digest is fully functional with tickers.

## Next Phase Readiness

- **05-04 (get_briefing wiring)** can delegate to `store.get_briefing_row` for the daily read; the self-describing payload guarantees a full `BriefingRow` round-trip, and `entries[]` is the `Briefing.entries` payload (Veto #13 — body_md stays in the row).
- **05-05 (weekly roll-up)** imports `_priority_key` and the flat `entries[]` schema **unchanged** — the dict-keyed sort operates on `payload['entries']` read back via `store.get_daily_briefings_in_range` with no `DecisionCard` object at weekly-sort time (SC#4 no-recompute). The event-class ranks + `build_entry` shape are the locked reuse contract.
- No blockers. Live DB at 0009; testcontainers apply 0009 via `alembic upgrade head`.

## Self-Check: PASSED

- Created files exist: `src/briefing/daily.py`, `tests/briefing/test_diff.py`, `tests/briefing/test_priority.py`, `tests/briefing/test_render.py`, `tests/briefing/test_daily.py` (all FOUND).
- Modified file present: `src/briefing/__init__.py` (FOUND).
- Task commits exist: `a6198fd` (Task 1), `f69b25a` (Task 2), `395636e` (Task 3) — all FOUND in git log.

---
*Phase: 05-briefing-renderer*
*Completed: 2026-07-16*
