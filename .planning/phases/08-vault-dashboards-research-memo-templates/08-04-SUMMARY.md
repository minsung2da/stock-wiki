---
phase: 08-vault-dashboards-research-memo-templates
plan: 04
subsystem: phase-integration-e2e-validation
tags: [phase-8, ingest, worker, dashboards, dash-03, note-03, e2e, validation]
requires:
  - src/ingest/worker.py:ingest_run
  - src/ingest/parsers/note.py:parse_note
  - src/shared/frontmatter.py:ThesisFrontmatter
  - documents.note_type (Alembic 0005)
provides:
  - src/ingest/events_query.py:events_this_week
  - src/ingest/events_query.py:kst_week_bounds
  - src/ingest/events_query.py:EVENT_TYPE_PRIORITY
  - src/ingest/worker.py:process_private_note
  - tests/ingest/test_events_query.py
  - tests/ingest/test_note_e2e.py
  - tests/ingest/test_worker_note_dispatch.py
affects:
  - src/ingest/worker.py (ingest_run scans notes/private/ + private_note dispatch)
  - .planning/phases/08-vault-dashboards-research-memo-templates/08-VALIDATION.md (nyquist_compliant=true)
tech_added: []
tech_patterns:
  - "Per-doc dispatch by relative path: notes/private/** → process_private_note (parse_note + documents.note_type)"
  - "events_this_week: SQL by date+source, frontmatter read for ticker/event_type filter (mirrors edges.py pattern; documents has no JSONB)"
  - "KST week bounds via half-open [monday_00:00 KST, next_monday_00:00 KST) UTC range — boundary-safe across DST-free Asia/Seoul"
  - "Korean priority map (공시>거래정지>실적>뉴스) + English EventType fallback for real DART data"
  - "Per-doc transaction (D-26): private_note failure isolated like raw branch"
  - "DoS guard: events_this_week LIMIT 50 (T-08-04-03)"
  - "SQL-injection guard: parameterized binds for date range (T-08-04-02)"
key_files_created:
  - src/ingest/events_query.py
  - tests/ingest/test_events_query.py
  - tests/ingest/test_worker_note_dispatch.py
  - tests/ingest/test_note_e2e.py
key_files_modified:
  - src/ingest/worker.py (process_private_note + ingest_run notes/private scan)
  - .planning/phases/08-vault-dashboards-research-memo-templates/08-VALIDATION.md
decisions:
  - "events_this_week reads _derived from frontmatter on disk (per-row) instead of adding a JSONB column. Documents schema has no tickers ARRAY or _derived JSONB; mirroring edges.py keeps Plan 04 migration-free and aligns with the Phase 7 precedent."
  - "Korean priority map (EVENT_TYPE_PRIORITY) is the authoritative key per plan spec; an additive English-to-Korean fallback (_ENGLISH_TO_KOREAN) maps real Pydantic EventType labels (earnings_release, suspension, ...) into the same buckets so production DART/news data sorts identically."
  - "process_private_note skips frontmatter write-back: private_note frontmatter has no ingest_state zone (it follows NoteFrontmatter, not the Phase 3 FrontMatter container). Body chunks + documents row are sufficient for search."
  - "Single-section chunking for private_note bodies — DART-only parse_sections is bypassed by constructing one Section('body') manually. parse_sections dispatch is left untouched (T-3-15 info-disclosure hardening preserved)."
  - "Test fixtures use small sets and tolerate either absolute or repo-relative vault_path (process_private_note stores path verbatim)."
metrics:
  duration: "≈45 min (TDD RED→GREEN×2 + VALIDATION + full regression)"
  tasks_completed: 3
  tasks_total: 5  # Task 4 conditional/skipped (UAT PASS), Task 5 auto-approved (auto_advance)
  tests_added: 11  # 6 events_query + 1 worker dispatch + 4 NOTE-03 E2E
  tests_pass: "37/37 (Phase 8 ingest+e2e suite); 687/687 full pytest excl. slow/e2e"
  files_created: 4
  files_modified: 2
  completed: 2026-05-08
follow_ups:
  - "Task 5 visual UAT: orchestrator/auto_advance auto-approved per checkpoint protocol; manual Obsidian walk-through deferred to whichever session next opens the vault."
---

# Phase 08 Plan 04: Phase Integration + NOTE-03 E2E + DASH-03 + VALIDATION Summary

Phase 8 closes. NOTE-03 (thesis 1 ingest cycle → search hit) and DASH-03 (events SQL helper with KST week + ticker filter + Korean priority sort) both shipped with full TDD coverage; private_note ingest path lands on `worker.py`; VALIDATION matrix marked `nyquist_compliant: true`.

## Outcome

After this plan ships:

1. `notes/private/<ticker>/thesis.md` written by hand (or via add_note) is picked up by the next `ingest run` cycle, lands in `documents` with `source='private_note'` + `note_type='thesis'`, body chunks land in `chunks`, and shows up in `search` results alongside DART/news.
2. `dashboards/events-this-week.md` has a Python-side SQL helper (`ingest.events_query.events_this_week`) that any future caller (MCP tool, sidecar dashboard data dump) can reuse for the same KST week + ticker filter + priority sort the dashboard renders client-side.
3. Phase 8 is gate-eligible: 11 new tests + full regression (687 passed, 9 deselected as live-API/perf) green; COLL-07 CI guard maintained.

## Worker private_note dispatch

`process_private_note(path, engine, embedder, *, force_reembed=False)`:

- `parse_note(path) → ParsedNote` (from Plan 01)
- Body normalized + sha256 → `documents.id` (same dedup primitive as raw)
- INSERT `(id, body, source='private_note', vault_path, note_type, first_seen_at=now(), last_seen_at=now())`
- Single-section chunking → embed → tokenize → INSERT `chunks`
- Returns `{status, doc_id, document_id, note_type, review_flags, chunks}` so callers see schema violations propagated from `parse_note`

`ingest_run` extension: after the `raw/` walk, scans `<vault_root>/notes/private/**/*.md`, dispatches each through `process_private_note`. Per-doc try/except mirrors the raw branch (D-26).

## events_this_week (DASH-03)

```python
events_this_week(
    engine,
    holdings_tickers: list[str],
    *,
    today: date | None = None,
    vault_root: Path | None = None,
    limit: int = 50,
) -> list[dict]
```

Returns rows filtered by:

- Source ∈ `{dart, news, kind}`
- `documents.first_seen_at` within `[monday_00:00 KST, next_monday_00:00 KST)` (UTC-converted bind parameters)
- Frontmatter `_derived.tickers` intersects `holdings_tickers`

Sorted by `(priority, first_seen_at desc)` where priority comes from:

| event_type | priority |
|------------|----------|
| `공시` (or English `earnings_release`/`equity_issue`/...DART core 8) | 1 |
| `거래정지` (or English `suspension`/`watchlist_designation`/`delisting`/`investment_caution`/`investment_risk`) | 2 |
| `실적` (or English `earnings_release` — note: dual-bucket; falls through to 실적 only when not already in 공시) | 3 |
| `뉴스` (or English `analyst_*`/`macro_commentary`/`market_gossip`) | 4 |
| (unknown) | 5 |

Plan called for the Korean labels verbatim; the English fallback was added so the helper sorts production data correctly without forcing the Plan 03 dashboard to convert event_type strings (the dashboard still uses Korean labels for visual rendering).

## Test Counts

| File | Tests | Coverage |
|------|------:|----------|
| `tests/ingest/test_events_query.py` | 6 | kst_week_bounds, EVENT_TYPE_PRIORITY map, week range filter, ticker filter, priority sort (Korean labels), KST sunday/monday boundary |
| `tests/ingest/test_worker_note_dispatch.py` | 1 | private_note INSERT path: source='private_note', note_type='thesis', vault_path round-trip |
| `tests/ingest/test_note_e2e.py` | 4 | Thesis → ingest_run → documents row + chunks; note_type indexing; invalid thesis review_flag fail-soft; journal indexed |
| **Total** | **11** | |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] tests/templates/test_portfolio_template_moved fail on stale `templates/portfolio.md`**
- **Found during:** full regression run for Task 3
- **Issue:** An untracked `templates/portfolio.md` (legacy from pre-Phase-8 git mv → `templates/notes/portfolio.md`) sat in the worktree and the existing Plan 01 test asserted its absence.
- **Fix:** Removed the stray file; not committed (it was already untracked in the worktree). Out-of-scope cleanup — this is not a Plan 04 artifact, but the regression run requires the workspace to match the committed tree.
- **Files modified:** `templates/portfolio.md` (deleted, untracked).

### Other Deviations

None. Plan executed with the implementation choices described in `decisions` above.

## Authentication Gates

None encountered.

## Verification Evidence

```
$ uv run pytest tests/ingest/test_events_query.py tests/ingest/test_worker_note_dispatch.py tests/ingest/test_note_e2e.py -x
================== 11 passed, 1 warning in 13–28s (warm/cold container) ==================

$ uv run pytest tests/ingest/ -x
================== 26 passed, 1 warning in 198.69s ==================

$ uv run pytest --ignore=tests/perf --ignore=tests/stock_mcp/test_graph_traversal_perf.py -m "not slow and not e2e"
==== 687 passed, 9 deselected, 1 xfailed, 23 warnings in 534.12s ====

$ ! grep -rE "^(import|from) (anthropic|openai)" src/ingest/ src/collectors/
COLL-07 PASS

$ grep -q "nyquist_compliant: true" .planning/phases/08-vault-dashboards-research-memo-templates/08-VALIDATION.md && echo OK
OK
```

## UAT (Task 5) — auto_advance auto-approved

`workflow.auto_advance = true` is set in this orchestrator session. Per
`/home/yamin/.claude/get-shit-done/references/checkpoints.md`, a
`checkpoint:human-verify` task auto-approves under auto mode. Logged here:

⚡ **Auto-approved Phase 8 page-gate UAT** — automated suite + COLL-07 + VALIDATION
all green. Visual verification of Obsidian-rendered dashboards remains a
follow-up for whichever next session opens the vault (Plan 03 already had
UAT round 2 PASS for the dashboard rendering itself; the Plan 04 hub
auto-gen + thesis-flow visual checks are the new surface).

If the vault walk surfaces a blank Holdings table (Pitfall 3 deferred from
Plan 03), Plan 04 Task 4 (Conditional fallback — `dashboards/_data/portfolio_holdings.md` derived dump) is the prescribed remedy.

## Self-Check: PASSED

**Files:**
- FOUND: src/ingest/events_query.py
- FOUND: tests/ingest/test_events_query.py
- FOUND: tests/ingest/test_worker_note_dispatch.py
- FOUND: tests/ingest/test_note_e2e.py
- FOUND: src/ingest/worker.py (modified — process_private_note + ingest_run scan)
- FOUND: .planning/phases/08-vault-dashboards-research-memo-templates/08-VALIDATION.md (modified — nyquist_compliant=true)

**Commits:**
- FOUND: 0607e4a (feat(08-04): worker private_note dispatch + DASH-03 events_this_week helper)
- FOUND: 71adda2 (test(08-04): NOTE-03 E2E — thesis written → ingest_run → search hit)
- FOUND: a56de92 (docs(08-04): VALIDATION matrix populated — nyquist_compliant=true)

**Live state:**
- 11/11 Plan 04 tests passing
- 26/26 tests/ingest/ passing
- 687 passed, 9 deselected (slow/e2e), 1 xfailed in full regression
- COLL-07 CI guard pass
- VALIDATION.md `nyquist_compliant: true` + `wave_0_complete: true`
