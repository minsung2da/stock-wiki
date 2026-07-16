---
phase: 05-briefing-renderer
verified: 2026-07-16T14:15:40Z
status: passed
score: 6/6 must-haves verified (SC#1-6) + 8/8 CONTEXT decisions (D-01..D-08) + 6/6 relevant Hard Vetoes
overrides_applied: 0
---

# Phase 5: Briefing Renderer Verification Report

**Phase Goal:** 일/주 top-N 변화 요약. "바뀐 종목만" — per-ticker dump 금지. (Daily/weekly top-N
CHANGE digest across `decision_cards`, ≤10 entries, prioritized; deterministic, NO LLM call in
the render path.)

**Verified:** 2026-07-16T14:15:40Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP SC#1-6)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC#1 | `generate_daily_briefing(date)` collects stance-changed / new-contradiction / expired-invalidated / new-high-conviction(≥0.8) cards, ≤10 entries, priority-sorted | ✓ VERIFIED | `src/briefing/daily.py:266-363` orchestrator: `store.list_cards_for_briefing` → `classify_change` (stance_flip/new_contradiction/new_high_conviction, `daily.py:101-135`) + expiring/invalidated buckets (`daily.py:312-325`) → `prioritize` truncates to `_MAX_ENTRIES=10` (`daily.py:67,234-243`). `tests/briefing/test_daily.py::test_truncates_to_ten` (12→10), `test_priority.py` (7 tests: held-first, event-class order, conviction-desc, truncation), `test_diff.py` (5 tests: stance flip, +N contradictions, first-card rule) — all PASS. |
| SC#2 | Result stored as `decision_cards` row `report_type='daily_briefing'` (payload JSONB + body_md) | ✓ VERIFIED | Migration `0009_briefing_report_type.py`: adds `report_type`/`report_date`, drops `corp_code NOT NULL`, adds two partial CHECKs (`ck_decision_cards_report_type`, `ck_decision_cards_corp_or_report`) + partial index. **Not a `DecisionCard`**: `src/briefing/models.py::BriefingRow` is a SEPARATE Pydantic model (`extra='forbid'`, no `corp_code`/`ticker`/`decision`/`assumptions`); `save_briefing` (`store.py:332-366`) is a separate write path (`_INSERT_BRIEFING_SQL` binds `corp_code=NULL`). Live DB confirmed at `alembic current == 0009 (head)`. `tests/db/test_migration_0009.py` (5 tests: roundtrip, both CHECKs, partial index, NULL-corp briefing insert OK, NULL-corp analysis card REJECTED) + `tests/briefing/test_store_briefing.py` (8 tests) — all PASS. |
| SC#3 | `body_md` = table `종목 \| 변화 \| 근거 \| 제안 \| Why now \| Why not` | ✓ VERIFIED | `render_body_md` (`daily.py:212-231`) header constant `_TABLE_HEADER = "종목 \| 변화 \| 근거 \| 제안 \| Why now \| Why not"` (`daily.py:62`). 제안 cell = `f"{stance} ({conviction:.2f})"` — bare stance+conviction, no forecast/target text (D-05/Veto#1). `tests/briefing/test_render.py::test_header_is_exact` + `test_jean_is_stance_plus_conviction_only` (regex `[A-Z]+ \(\d\.\d{2}\)`) — PASS. |
| SC#4 | Weekly = `weekly_briefing` row + `source_reports:[daily×7]`, pre-materialized, NO recompute on read | ✓ VERIFIED | `generate_weekly_briefing` (`weekly.py:144-233`) computes `aggregate_net` ONCE and persists `entries`+`source_reports`+`coverage` into the row. `tests/briefing/test_weekly.py::test_no_recompute` explicitly `DELETE FROM decision_cards WHERE report_type='daily_briefing'` AFTER generation, then calls the wired `get_briefing(week_end,'weekly')` and asserts `result.entries == stored_entries` (byte-identical) — proves the read is a pure SELECT with no re-aggregation. PASS. |
| SC#5 | MCP `get_briefing(date, type)` tool reads real rows | ✓ VERIFIED | `src/mcp_v2/tools/briefing.py::get_briefing` delegates the SELECT to `cards.store.get_briefing_row` — no inline `text()` in the tool (confirmed: only docstring mentions `text()`). AST guard `tests/mcp_v2/test_no_run_sql_guard.py` (4 tests) confirms `get_briefing` is one of exactly 10 locked tools and no non-constant `text()` call exists anywhere in `src/mcp_v2`. `tests/mcp_v2/test_briefing_wired.py` (7 tests: found=True+entries, empty→found=False, weekly-maps-correctly, daily-does-not-read-weekly-row, bad type/date→InvalidArgument, no-body-leak) — all PASS. |
| SC#6 | No-change day writes a short row so `get_briefing` returns `found=True` (never `found=False`/empty page) | ✓ VERIFIED | `render_body_md([])` returns `"오늘 유의미한 변화 없음"` (`daily.py:65,220-221`); `generate_daily_briefing` ALWAYS calls `store.save_briefing` even with `entries=[]` (no early-return branch). `tests/briefing/test_daily.py::test_no_change_writes_short_row` seeds an empty-collect-set date, asserts `row.payload["entries"] == []`, `row.body_md == "오늘 유의미한 변화 없음"`, and that `get_briefing_row` finds it. `tests/briefing/test_weekly.py::test_empty_week_writes_real_row` mirrors this for weekly. PASS. |

**Score:** 6/6 truths verified

### CONTEXT Decisions (D-01..D-08)

| Decision | Status | Evidence |
|---|---|---|
| D-01 (3-level sort: held→event-class→conviction-desc, truncate 10) | ✓ VERIFIED | `_priority_key` (`daily.py:179-191`) returns `(held_rank, event_class_rank, -conviction)`; `_EVENT_CLASS_RANK` order `stance_flip=0<new_contradiction=1<expired_invalidated=2<new_high_conviction=3` (`daily.py:51-56`). `test_priority.py::test_event_class_order`, `test_conviction_desc_within_class`, `test_held_first` — PASS. Reused unchanged by weekly (`weekly.py:32-38,191`). |
| D-02 (diff baseline = prior active card via supersession chain) | ✓ VERIFIED | `generate_daily_briefing` calls `store.get_active` + `store.walk_supersedes(...)[1]` (`daily.py:303-308`) — no separate snapshot store. `test_daily.py::test_stance_flip_over_superseded_prior` builds a real `supersedes` chain and asserts the diff fires. PASS. |
| D-03 (first-card counts only if conviction≥0.8) | ✓ VERIFIED | `classify_change` (`daily.py:129-135`): `prior is None` branch returns `new_high_conviction` iff `conviction>=0.8`, else `None`. `test_diff.py` first-card-rule test — PASS. |
| D-04 (locked 6-column table) | ✓ VERIFIED | See SC#3. |
| D-05 (제안 = stance+conviction only, no forecast) | ✓ VERIFIED | See SC#3; also Veto #1 below. |
| D-06 (Why now = top key_claim, Why not = top contradiction, NO extra LLM call) | ✓ VERIFIED | `_top_key_claim` sorts by weight then confidence (`daily.py:141-148`); `why_not` = `card.contradictions[0].bear_claim` or `—` (`daily.py:164`). `daily.py`/`weekly.py` import no `anthropic`/`openai`/`subagents` (grep confirmed empty). `test_render.py::test_why_now_is_top_weighted_key_claim`, `test_why_not_is_top_contradiction_bear_claim` — PASS. |
| D-07 (weekly NET: start vs end state; flip-flops dropped) | ✓ VERIFIED | `aggregate_net` (`weekly.py:59-141`): per-ticker `start`/`end` from earliest/latest daily entry; drops when `not stance_flipped and not conviction_moved` (`weekly.py:101-106`). `test_weekly.py::test_net_change` explicitly proves a BUY→HOLD→BUY flip-flop is dropped while a genuine HOLD→SELL survives with correct `intra_week_events` count. PASS. |
| D-08 (best-effort coverage, missing≠no-change) | ✓ VERIFIED | `coverage = {"present","expected":7,"missing_dates"}` computed independently of the NET drop logic (`weekly.py:133-140`). `test_weekly.py::test_coverage` (5/7 present → 2 missing dates) — PASS. |

**Score:** 8/8 decisions verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/db/migrations/versions/0009_briefing_report_type.py` | migration adding report_type/report_date + CHECKs + partial index | ✓ VERIFIED | Read in full; matches RESEARCH recommendation exactly; roundtrip tested; live DB confirmed at head (0009). |
| `src/briefing/models.py` (`BriefingRow`) | separate typed model, not `DecisionCard` | ✓ VERIFIED | `extra='forbid'`, only row-identity + payload/body_md fields; imports nothing from `cards.models`. |
| `src/briefing/daily.py` | `generate_daily_briefing` + change detection + priority + render | ✓ VERIFIED | 364 lines; full orchestrator wired to `cards.store`; LLM-free (no anthropic/openai imports). |
| `src/briefing/weekly.py` | `generate_weekly_briefing` + `aggregate_net` | ✓ VERIFIED | 234 lines; reuses `daily.py`'s `_priority_key`/`render_body_md`/`load_held_tickers`/`_kst_close_on` unchanged (no reimplementation, no `.card` attribute access). |
| `src/cards/store.py` briefing trio (`save_briefing`/`get_briefing_row`/`list_cards_for_briefing`/`get_daily_briefings_in_range`) | typed store surface, no run_sql | ✓ VERIFIED | All parameterized `text()` module constants; `__all__` exports all four + `BriefingCandidates`. |
| `src/mcp_v2/tools/briefing.py` | `get_briefing` wired to store, no inline SQL | ✓ VERIFIED | Delegates 100% of DB access to `store.get_briefing_row`; ISO-8601 date validated before DB (ASVS V5). |
| `src/mcp_v2/models.py` (`Briefing`) | entries-only, no body_md field | ✓ VERIFIED | `model_fields` confirmed to NOT contain `body_md` (Veto #13 by construction). |
| `src/db/entity_models.py` (`DecisionCard` ORM) | column-set parity with migration 0009 | ✓ VERIFIED | `report_type`/`report_date` columns added, `corp_code` nullable — grep-confirmed at `entity_models.py:397-411`. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `daily.py::generate_daily_briefing` | `cards.store.save_briefing` | direct call | ✓ WIRED | `daily.py:358`. |
| `daily.py::generate_daily_briefing` | `cards.store.list_cards_for_briefing` / `get_active` / `walk_supersedes` | direct calls | ✓ WIRED | `daily.py:299,303,306`. |
| `weekly.py::generate_weekly_briefing` | `cards.store.get_daily_briefings_in_range` | direct call | ✓ WIRED | `weekly.py:186`. |
| `weekly.py::generate_weekly_briefing` | `cards.store.save_briefing` | direct call | ✓ WIRED | `weekly.py:224`. |
| `weekly.py::aggregate_net` / sort | `daily.py::_priority_key` (reuse, not reimplementation) | import | ✓ WIRED | `weekly.py:32-38,191` — imports the exact callable; `test_priority_key_is_dict_keyed` proves plain-dict operation. |
| `mcp_v2/tools/briefing.py::get_briefing` | `cards.store.get_briefing_row` | direct call | ✓ WIRED | `briefing.py:74`; no inline `text()` (AST-guard enforced). |
| `mcp_v2/tools/briefing.py::get_briefing` | `mcp_v2/models.py::Briefing` | constructs return value | ✓ WIRED | `briefing.py:77-82`; `entries` only, `payload["entries"]` — no `body_md` leak. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `get_briefing` MCP tool | `row.payload["entries"]` | `cards.store.get_briefing_row` → real `SELECT ... FROM decision_cards WHERE report_type=:rt AND report_date=:d` | Yes — DB-backed, confirmed empty-DB→`found=False` and seeded-row→`found=True` with real entries in `test_briefing_wired.py` | ✓ FLOWING |
| daily `entries[]` | `build_entry(event)` output | `classify_change` diff over real `DecisionCard` rows fetched via `get_active`/`walk_supersedes` | Yes — `test_stance_flip_over_superseded_prior` builds real superseded chain in Postgres and asserts the diff surfaces | ✓ FLOWING |
| weekly `entries[]` | `aggregate_net(daily_rows,...)` | `get_daily_briefings_in_range` → real persisted daily rows | Yes — `test_no_recompute` proves entries survive source deletion (pre-materialized, not a live join) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Phase 5 test suites (briefing + wired MCP + migration 0009) | `.venv/Scripts/python.exe -m pytest tests/briefing tests/mcp_v2/test_briefing_wired.py tests/db/test_migration_0009.py -q` | `52 passed` | ✓ PASS |
| mcp_v2 + cards regression (no breakage from Phase 5 wiring) | `.venv/Scripts/python.exe -m pytest tests/mcp_v2 tests/cards -q` | `164 passed, 2 skipped` (skips pre-existing hybrid_search conditionals, unrelated) | ✓ PASS |
| run_sql / AST no-inline-SQL guard (Veto #7) | `.venv/Scripts/python.exe -m pytest tests/mcp_v2/test_no_run_sql_guard.py -q` | `4 passed` | ✓ PASS |
| Live DB at migration head | `.venv/Scripts/python.exe -m alembic -c src/db/alembic.ini current` | `0009 (head)` | ✓ PASS |
| Debt-marker scan (TODO/FIXME/XXX/HACK/PLACEHOLDER) on all Phase 5 files | `grep -in "TODO\|FIXME\|XXX\|TBD\|HACK\|PLACEHOLDER"` on daily.py/weekly.py/models.py/store.py/briefing.py/0009 migration | no matches | ✓ PASS |
| No LLM import in render path (D-06) | `grep -rn "anthropic\|openai\|subagents\|Task(" src/briefing/` | no matches (only a docstring mention of "no anthropic/openai") | ✓ PASS |
| Task commits exist (all 12 across 05-01..05-05) | `git cat-file -e <hash>` for each of 892e780,10038f8,70d58d6,631878b,38bb974,a6198fd,f69b25a,395636e,93c5bcd,eafb105,a04a7ca,225ff42 | all FOUND | ✓ PASS |
| Pre-existing full-suite-only failures (SUMMARY claim of "unrelated") independently re-run in isolation | `pytest tests/mcp_v2/test_tokenizer.py::test_embedder_version_constant_imports_without_torch tests/test_migration.py::test_downgrade_then_upgrade_idempotent tests/test_migration_0002.py::test_downgrade_reverses_migration` | `3 passed` | ✓ PASS (confirms deferred-items.md claim — not attributable to Phase 5) |

### Probe Execution

No `scripts/*/tests/probe-*.sh` convention or explicit probe declarations found for this phase (Phase 5 verification is DB-backed pytest, not shell probes). N/A — SKIPPED (no probe convention used by this project).

### Requirements Coverage

This phase has no `REQUIREMENTS.md` REQ-ID mapping (confirmed absent, as stated in the phase brief). The requirements ARE the ROADMAP Success Criteria SC#1-6, covered in full above (6/6 verified) and cross-referenced against `requirements-completed` frontmatter across the 5 plan SUMMARYs: SC#2 (05-01), SC#1/#2/#3/#6 (05-03), SC#5 (05-04), SC#4 (05-05) — union covers SC#1-6 exactly once each, no orphans, no gaps.

### Hard Vetoes Cross-Check (CLAUDE.md)

| Veto | Status | Evidence |
|---|---|---|
| #1 (no price prediction; 제안 is stance, not forecast) | ✓ HELD | 제안 cell is exactly `f"{stance} ({conviction:.2f})"` — no target price, no return forecast anywhere in `render_body_md` or the entry-dict schema. |
| #3 (contradictions first-class, not hidden) | ✓ HELD | `why_not` column is the top contradiction's `bear_claim`, rendered `—` only when genuinely empty (never silently dropped). |
| #4 (no black-box score; deterministic decomposable sort) | ✓ HELD | `_priority_key` is a pure, inspectable 3-tuple over typed fields; `_CONVICTION_DELTA=0.10` is an explicit module constant, not a hidden weight. |
| #6 (no numeric embedding) | ✓ HELD | Phase 5 adds zero embedding code; `body_md`'s FTS coverage is the pre-existing GENERATED `body_tsv` column (untouched). |
| #7 (no run_sql escape hatch) | ✓ HELD | AST guard (`test_no_run_sql_guard.py`) passes; all briefing SQL lives in `cards.store` as parameterized `text()` constants. |
| #13 (filter-before-context; payload-only default) | ✓ HELD | `Briefing` model has no `body_md` field — `get_briefing` structurally cannot leak the full table to context. |

### Anti-Patterns Found

None. Scanned all Phase 5 source files (`src/briefing/{daily,weekly,models}.py`, `src/cards/store.py` briefing additions, `src/mcp_v2/tools/briefing.py`, `src/db/migrations/versions/0009_briefing_report_type.py`) for TODO/FIXME/XXX/TBD/HACK/PLACEHOLDER/"not implemented"/hardcoded-empty-return patterns — zero matches. One documented, non-blocking known-stub: `entry['name']` always renders `None` (a `DecisionCard` carries no entity-name field), so the 종목 cell falls back to the bare ticker — this is explicitly within SC#3's locked column-set scope (`name` is an optional convenience field, not a required column) and does not block the phase goal.

### Human Verification Required

None. Phase 5 is a fully deterministic, DB-backed backend feature (no UI, no real-time behavior, no external service integration) with 100% automated test coverage per the phase's own Validation Architecture (`05-VALIDATION.md` explicitly declares "All phase behaviors have automated verification" — confirmed true by this verification).

### Gaps Summary

No gaps. All 6 ROADMAP Success Criteria, all 8 CONTEXT decisions (D-01..D-08), and all 6 relevant Hard Vetoes are independently verified against the actual source code and a live, DB-backed test run (52 phase-specific tests + 164 regression tests + 4 AST-guard tests, all green; live DB confirmed at alembic head 0009). The SUMMARY.md claims of "pre-existing unrelated full-suite failures" were independently re-verified by running the 3 non-live failing tests in isolation — they pass, corroborating the claim rather than merely trusting it.

---

*Verified: 2026-07-16T14:15:40Z*
*Verifier: Claude (gsd-verifier)*
