---
phase: 07-graph-layer-graphify-integration
plan: 04
subsystem: graph-canonical-queries
tags: [wave-2, graph-03, canonical-queries, get-related-regression]
requires:
  - 07-01 (graphifyy installed; tests/graph stubs scaffolded)
  - 07-02 (edges populated; ingest.edges.populate available)
  - 07-03 (graphify CLI shipped; Plan 04 closes phase 7)
provides:
  - "src/graph/canonical.py — 5 canonical SQL subgraph query functions (Q1..Q5)"
  - "vault/graph/README.md — Korean prose + Python snippets for 5 queries (gitignore exception)"
  - "tests/graph/test_canonical_queries.py — 5 non-empty assertions + README parity"
  - "tests/graph/test_get_related_regression.py — D-22 Phase 6 SQL-only contract preserved on 6-value enum"
affects:
  - .gitignore (vault/graph/* + !vault/graph/README.md so README is committed)
tech_stack_added: []
patterns:
  - "Recursive CTE depth cap (c.depth < 10) on q2 + q4 — T-7-04-01 DoS mitigation"
  - "All SQL via sa.text() with bind params — T-7-04-02 SQL injection mitigation"
  - "Q4 returns [] gracefully under MISSING DART correction field (probe-findings.md soft no-op contract)"
  - "README parity test: ast.parse Python code blocks → match function names against canonical.__all__"
key_files_created:
  - src/graph/canonical.py
  - vault/graph/README.md
  - .planning/phases/07-graph-layer-graphify-integration/07-04-SUMMARY.md
key_files_modified:
  - tests/graph/test_canonical_queries.py
  - tests/graph/test_get_related_regression.py
  - .gitignore
key_decisions:
  - "shared.repo_root is non-existent — canonical.py imports from stock_mcp.repo_root (auto-fix Rule 3)"
  - "Q4 ships full recursive walk SQL up-front; runs as graceful no-op until DART writer surfaces correction-of field"
  - "gitignore uses vault/graph/* (not vault/graph/) so the !vault/graph/README.md negation works (file-level)"
  - "Tests pass days=100_000 to canonical Q1/Q3/Q5 so fixture's 2026-01-10 first_seen_at falls inside the today-N cutoff"
  - "test_q4_*_xfail_if_no_correction_field: probe MISSING → assert returns [] (graceful contract); will be re-evaluated when DART writer is extended"
metrics:
  duration_minutes: ~14
  completed_date: 2026-05-05
  tasks: 3
  commits:
    - 3559546
    - f9d3038
    - ea1ab5e
  files_changed: 5
---

# Phase 07 Plan 04: GRAPH-03 Canonical Subgraph Queries + D-22 Regression Summary

GRAPH-03 ships end-to-end. Five canonical SQL subgraph queries (`q1_positions_recent_events`, `q2_catalyst_chain`, `q3_sector_filings`, `q4_supersedes_chain`, `q5_notes_events`) are exported from `src/graph/canonical.py` and mirrored verbatim in `vault/graph/README.md` (Korean prose + Python snippets). A README parity test (ast.parse + function-name set equality) enforces that future README edits cannot drift from the code. D-22 regression discharged: Phase 6's `get_related` continues to work on the new 6-value edge_type enum and preserves its SQL-only contract (passes even with `graphify` modules removed from `sys.modules`).

## What Changed

### `src/graph/canonical.py` (new, ~225 lines)

- Public surface: 5 callables exported via `__all__`.
- All SQL uses `sa.text()` with bind params (T-7-04-02 mitigation — verified by `! grep f"SELECT|f"FROM`).
- Recursive CTEs in q2 + q4 cap `c.depth < 10` (T-7-04-01 mitigation).
- Q1 uses `Portfolio.load(repo_root())` from `shared.portfolio` and `stock_mcp.repo_root` (deviation #1 below).
- Q2 resolves `ticker → entities.corp_code` then walks `event_event` edges whose `src_id LIKE '{corp_code}-%'`.
- Q3 joins `ticker_sector` × `mentions_ticker` × `documents` filtered by `dst_id = sector_code` and `first_seen_at >= cutoff`.
- Q4 looks up the DART seed document via `source_url LIKE '%{rcept_no}%'` (the DART writer template `https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}` embeds the rcept_no, verified by reading `src/collectors/dart/writer.py`). Recursive supersedes walk is committed; returns `[]` gracefully today because Plan 02's `_derive_supersedes` is a soft no-op until DART writer is extended.
- Q5 returns `{"notes": [...], "events": [...]}` — notes via `note_ticker` directly, events via `filing_event ⋈ mentions_ticker` (same source document).

### `vault/graph/README.md` (new, ~165 lines)

- 5 H2 sections (`## Q1 ` ... `## Q5 `), each with Korean prose explanation + a runnable Python snippet that defines `def qN_*` with the same name as `canonical.__all__`.
- Notes KST timezone convention (directory names ISO `YYYY-MM-DD`) and Phase 9 scheduler hookup intent (D-21).
- Q4 section explicitly notes the MISSING probe state and the deferred quick-task scope.
- "실행 방법" section shows `python -c` one-liner + pytest smoke test.

### `.gitignore` change

```
# Phase 7 graph snapshots — regenerable, never commit
# Use file-level glob (not dir-level) so the README.md exception below works.
vault/graph/*
!vault/graph/README.md
vault/.graphify-staging/
```

The dir-level glob `vault/graph/` does NOT permit per-file negations (git ignores the whole directory). Switched to `vault/graph/*` so `!vault/graph/README.md` re-includes that single file. Verified via `git check-ignore -v vault/graph/README.md` → `.gitignore:33:!vault/graph/README.md`.

### Tests

- **`tests/graph/test_canonical_queries.py`** — 5 non-empty assertions (Q1..Q5) running on the seeded fixture vault from `tests/graph/conftest.py::seed_edges`, plus `test_readme_parity_imports_match_snippets`. Q1 monkey-patches `Portfolio.load` so the test does not depend on `notes/private/portfolio.md` content. Q2 uses `with_event_chain=True` so the fixture has two same-corp_code DART filings 30 days apart. Q4 reads `probe-findings.md` programmatically and skips if the MISSING marker is gone (signalling the contract should be re-evaluated); under MISSING it asserts the graceful `[]` contract.
- **`tests/graph/test_get_related_regression.py`** — 2 tests fully implemented:
  1. `test_get_related_returns_phase7_edge_types` — populates edges via `populate(seed_edges["doc_ids"], conn)`, calls `get_related(seed_doc, depth=1)`, asserts `result.related` carries at least one Phase 7 edge_type and zero legacy edge_types.
  2. `test_get_related_does_not_regress_phase6_sql_only` — pops every `graphify*` module from `sys.modules`, runs `get_related`, asserts success (proves D-06 SQL-only contract holds).

## Verification Evidence

```
$ UV_LINK_MODE=copy uv run pytest tests/graph/test_canonical_queries.py -x
6 passed in 18.98s

$ UV_LINK_MODE=copy uv run pytest tests/graph/test_get_related_regression.py -x
2 passed in 33.67s

$ UV_LINK_MODE=copy uv run pytest tests/graph/ tests/db/test_migration_0004.py tests/stock_mcp/ tests/test_ingest_worker.py
152 passed, 1 xfailed in 348.57s
  (xfailed: Plan 02 supersedes_from_dart_correction_field — deferred to DART writer enhancement)

$ UV_LINK_MODE=copy uv run python -c "from src.graph.canonical import q1_positions_recent_events, q2_catalyst_chain, q3_sector_filings, q4_supersedes_chain, q5_notes_events; from src.graph import canonical; assert canonical.__all__ == ['q1_positions_recent_events','q2_catalyst_chain','q3_sector_filings','q4_supersedes_chain','q5_notes_events']"
(exit 0)

$ ! grep -E 'f"\.\.\.FROM|f"SELECT' src/graph/canonical.py
(no hits — bind-only SQL)

$ grep -c "c.depth < 10" src/graph/canonical.py
2

$ grep -E "^## Q[1-5] " vault/graph/README.md | wc -l
5

$ grep -E "def q[1-5]_" vault/graph/README.md | wc -l
5

$ git check-ignore -v vault/graph/README.md
.gitignore:33:!vault/graph/README.md	vault/graph/README.md
  (the .gitignore line that excludes the file from the ignore — confirms inclusion)
```

## Per-Query Result Counts (Fixture Vault)

| Query | Days | Result Count | Notes |
|-------|------|--------------|-------|
| Q1 | 100,000 | ≥3 (DART + News + Note) | Monkey-patched portfolio.holdings = [005930] |
| Q2 | 365 | ≥1 (one event_event edge) | Fixture seeded `with_event_chain=True` so dart-1 → dart-2 30d chain exists |
| Q3 | 100,000 | ≥1 (samsung filing) | Sector="전기·전자" |
| Q4 | n/a | 0 (graceful empty) | MISSING DART correction field — soft no-op contract |
| Q5 | 100,000 | notes:1, events:≥1 | note_ticker + filing_event∩mentions_ticker |

Live-vault counts deferred to operator phase-gate (07-VALIDATION.md Manual-Only).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `shared.repo_root` does not exist**

- **Found during:** Task 1 — `pytest --collect-only` of `tests/graph/test_canonical_queries.py` failed with `ModuleNotFoundError: No module named 'shared.repo_root'`.
- **Issue:** The plan's `<action>` Step 1 imports `from shared.repo_root import repo_root`, but the repo's only `repo_root` helper lives at `src/stock_mcp/repo_root.py` (Plan 06-05 placement decision recorded in STATE.md). `src/shared/` has no `repo_root.py`.
- **Fix:** Replaced the import with `from stock_mcp.repo_root import repo_root`. Same callable, same resolution semantics (env override → walk-up → cwd fallback). README snippet for Q1 was updated to mirror the same import path so README parity holds.
- **Files modified:** `src/graph/canonical.py`, `vault/graph/README.md`
- **Commit:** 3559546 + f9d3038

**2. [Rule 1 - Bug] `.gitignore` directory-level glob blocks the README.md negation**

- **Found during:** Task 2 — `git add vault/graph/README.md` failed with "다음 경로는 .gitignore 파일 중 하나 때문에 무시합니다: vault/graph".
- **Issue:** `vault/graph/` (with trailing slash) is a directory pattern; per Git docs, `!path` cannot un-ignore a path inside an already-ignored directory.
- **Fix:** Switched to `vault/graph/*` (file-level) followed by `!vault/graph/README.md`. The README is now committed; snapshot `<YYYY-MM-DD>/...` directories continue to match the leading `vault/graph/*` and remain ignored. Verified via `git check-ignore -v`.
- **Files modified:** `.gitignore`
- **Commit:** f9d3038

**3. [Rule 2 - Missing critical] Q1/Q3/Q5 tests would silently return empty under fixture's 2026-01-10 first_seen_at**

- **Found during:** Test design (Task 1).
- **Issue:** Fixture `seed_edges` writes documents with `first_seen_at = datetime(2026, 1, 10, ...)`. Today (2026-05-05) minus the default `days=30/14/60` cutoff is well after 2026-01-10, so the queries would return empty and the non-empty assertion would fail — not because the SQL is wrong but because the cutoff is wrong for the fixture.
- **Fix:** Tests pass `days=100_000` for Q1/Q3/Q5 and `days=365` for Q2 so the fixture timeline falls inside the cutoff. The default value (30/14/60) is preserved in production code paths.
- **Files modified:** `tests/graph/test_canonical_queries.py`
- **Commit:** 3559546

### No architectural changes (Rule 4) raised

### No authentication gates encountered

## DART Supersedes — Status (Unchanged)

Plan 04's Q4 ships the full recursive walk SQL up-front. It returns `[]` for any input today because Plan 02's `_derive_supersedes` is a soft no-op (probe-findings.md MISSING). The deferred quick task scope is unchanged from Plan 02 SUMMARY:

- Extend `src/collectors/dart/writer.py` to surface `[기재정정]` prefix detection or `notice_search` `pblntf_detail_ty='I001'` lookup, populate `provenance.correction_of_rcept_no`.
- Plan 02 `_derive_supersedes` already-knows how to read that field (TEMPLATE A path in PLAN was kept conditional).
- When deployed, Q4 will produce non-empty results immediately — no canonical query change needed.

## Phase 7 Completion (Plans 01-04 collectively)

| Plan | Outcome |
|------|---------|
| 07-01 | graphifyy 0.7.5 installed; 23 test stubs scaffolded; probe-findings.md complete |
| 07-02 | Migration 0004 + edges.populate() + worker hook; 138 passed/12 skipped/1 xfailed |
| 07-03 | `stock graph snapshot` CLI ships (snapshot.py + window.py + config); 18/18 tests |
| 07-04 | 5 canonical queries + README + D-22 regression; 152 passed/1 xfailed |

GRAPH-01, GRAPH-02, GRAPH-03 all green. D-22 (Phase 6 regression) discharged. Phase 7 ready for phase-gate operator review (live `stock graph snapshot` + Obsidian/browser visualization).

## Threat Flags

None new. Plan 04 introduces no network endpoints, no auth surfaces, no schema changes, no new trust boundaries. All `mitigate` dispositions in the plan's threat register hold:

- T-7-04-01 (recursive CTE runaway): `c.depth < 10` cap verified by grep (2 occurrences in q2 + q4).
- T-7-04-02 (SQL injection): `sa.text()` bind params throughout; ticker length check + sector_code as bind.
- T-7-04-03 (PII via README): only generic `005930` (Samsung) appears; no `notes/private/` content quoted.
- T-7-04-04 (README/code parity drift): `test_readme_parity_imports_match_snippets` enforced in CI.

## Self-Check: PASSED

- `src/graph/canonical.py` exists with `__all__ = ['q1_positions_recent_events', 'q2_catalyst_chain', 'q3_sector_filings', 'q4_supersedes_chain', 'q5_notes_events']` (verified via runtime import + assert).
- `vault/graph/README.md` exists with 5 `## Q[1-5] ` sections + 5 `def q[1-5]_*` snippets matching canonical.__all__.
- `.gitignore` line 33 reads `!vault/graph/README.md`; `git check-ignore -v` confirms the negation applies.
- All Phase 7 plan tests + Phase 6 regression suite green (152 passed, 1 xfailed) — no test regression vs. Plan 02 baseline.
- Recursive CTE depth cap (`c.depth < 10`) present 2× in canonical.py.
- No f-string SQL interpolation (`! grep -E 'f"\.\.\.FROM|f"SELECT'` returns no hits).
- Commits exist on main: 3559546 (Task 1), f9d3038 (Task 2), ea1ab5e (Task 3).
