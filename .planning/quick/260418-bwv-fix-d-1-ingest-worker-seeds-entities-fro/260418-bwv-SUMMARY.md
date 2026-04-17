---
phase: quick-260418-bwv
plan: 01
subsystem: shared.frontmatter + collectors.dart + ingest.worker + db.entity
tags: [bugfix, phase-3-followup, deferred-d1, rebuild-integrity, vault-as-source-of-truth]
dependency_graph:
  requires: [quick-260418-asr (upsert_entity helper, collector wiring)]
  provides: [worker-driven entity reseed on rebuild]
  affects: [stock ingest rebuild CLI path, resolve_entity post-rebuild, STORE-05 invariant]
tech_stack:
  added: []
  patterns:
    - "Frontmatter as single source of truth for identity reseed (STORE-05)"
    - "Best-effort seed via contextlib.suppress — ingest never fails on seed hiccup"
    - "Triple-fallback canonical_name: fm.company_name -> existing entities row -> corp_{code}"
key_files:
  created: []
  modified:
    - src/shared/frontmatter.py
    - src/collectors/dart/writer.py
    - src/collectors/dart/__init__.py
    - src/ingest/worker.py
    - tests/test_ingest_worker.py
decisions:
  - "Option A chosen over Option B: worker-driven seed reuses the existing per-doc transaction boundary; no new CLI entry point. Keeps rebuild flow untouched and tightens vault=source-of-truth."
  - "company_name is a new ProvenanceBlock field (default None, exclude_none on dump) — legacy vault files remain schema-valid."
  - "Seed runs AFTER the doc transaction commits (not inside it). upsert_entity opens its own engine.begin(), so nesting is avoided and a doc insert is never rolled back by a seed failure."
  - "Fallback 'corp_{code}' for legacy files is NOT great (plan's own word) but it is bounded: new docs carry company_name, so the fallback only bites existing pre-bwv files and only until first re-collect."
metrics:
  duration: "~30 min"
  completed: "2026-04-17"
  tasks: 2
  commits: 2
  new_tests: 3
  total_tests_passing: 191
---

# Quick Task 260418-bwv: Fix D-1 — Ingest Worker Seeds Entities from Frontmatter Summary

One-liner: Closes Phase 3 D-1 by making the ingest worker re-seed entities/entity_aliases from frontmatter so `stock ingest rebuild` restores ticker→corp_code resolution using vault alone (STORE-05 invariant).

## Scope

Bugfix against Phase 3 walking-skeleton rebuild path. No new requirements, no schema migration. Touches four source files + one test file; adds three tests.

## Task 1: Frontmatter + DART writer company_name plumbing (b4facda)

**What changed:**
- `ProvenanceBlock.company_name: str | None = None` — backward-compatible (default None + `exclude_none=True` on YAML dump means existing vault files parse and round-trip unchanged).
- `collectors.dart.writer.write_filing` gains optional `company_name` kwarg; stored into frontmatter.
- `collect_dart` extracts `corp.corp_name` once per run into local `company_name`, passes to `write_filing` AND reuses it as `canonical_name` for `upsert_entity` (replaces the previous in-place `getattr(corp, "corp_name", None)` expression — purely a refactor).

**Tests:** No new tests for this commit; existing 37-test collector+frontmatter surface unchanged.

## Task 2: Worker seeds entity after per-doc commit (85efe29)

**What changed (`src/ingest/worker.py`):**
- Added `from db.entity import upsert_entity` at module top.
- Added `import contextlib` for the best-effort seed guard.
- `process_document` now reads `fm.provenance.ticker` and `fm.provenance.company_name` up front.
- After the per-doc `engine.begin()` transaction commits, if `corp_code` is non-None:
  1. `canonical_name = fm_company_name` if present, else
  2. `SELECT canonical_name FROM entities WHERE corp_code = :cc` (another doc may have already seeded), else
  3. fallback `f"corp_{corp_code}"`
- Call `upsert_entity(engine, corp_code, canonical_name, ticker)` inside `contextlib.suppress(Exception)` — identical defense-in-depth posture to the collector seed path.

**Tests added (tests/test_ingest_worker.py):**
- **W14** — collector-simulated frontmatter (company_name='삼성전자', ticker='005930') → one `entities` row + one `entity_aliases` row, `resolve_entity('005930')` returns the Samsung entity.
- **W15** — frontmatter has no `company_name` (simulates legacy file) → entity row still written with fallback `canonical_name='corp_00126380'`, `resolve_entity('005930')` still resolves.
- **W16** — rebuild end-to-end simulation: seed via collector → run worker → TRUNCATE entities CASCADE → re-run worker with `force_reembed=True` → `resolve_entity('005930')` works again, purely from vault-resident frontmatter.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocker] Pre-commit hook rejected `try/except/pass` (ruff SIM105)**
- **Found during:** Task 2 initial commit attempt
- **Issue:** ruff's SIM105 flagged the best-effort `try: upsert_entity(...); except Exception: pass`; repo style prefers `contextlib.suppress`.
- **Fix:** Replaced with `with contextlib.suppress(Exception):` block + top-level `import contextlib`.
- **Files modified:** src/ingest/worker.py
- **Commit:** rolled into 85efe29 (single task-2 commit)

**2. [Rule 3 - Blocker] Pre-commit hook rejected E501 line-length in test (>100 chars)**
- **Found during:** Task 2 initial commit attempt
- **Issue:** Two test spots used `__import__("shared.frontmatter", fromlist=[...])...` to dodge an import-order concern that did not actually exist — it produced 116-char lines.
- **Fix:** Added `read_frontmatter, write_frontmatter` to the existing module-top import; replaced dynamic imports with direct calls.
- **Files modified:** tests/test_ingest_worker.py
- **Commit:** rolled into 85efe29

No other deviations — the other 188 tests stayed green without further changes.

## Verification

**Scoped test run (3 new tests):** `3 passed in 12.84s`

**Related-suite run (rebuild + entity + collector + frontmatter):** `43 passed in 18.38s`

**Full fast suite (excluding `@pytest.mark.slow`):**
```
191 passed, 1 skipped, 2 deselected, 16 warnings in 294.84s (0:04:54)
```

Baseline from quick-260418-asr SUMMARY was 183 passed — this task adds 8 net (3 new D-1 tests + 5 that moved out of the `slow` marker or were deselected in that prior run; net-net the D-1 contribution is +3 tests and 0 regressions).

**Red-green trace (W16 logic):**
1. Seed + ingest → `resolve_entity('005930')` is not None ✓
2. `TRUNCATE entities CASCADE` → `resolve_entity('005930')` IS None ✓ (confirms the rebuild-wipe hypothesis D-1 named)
3. Re-run worker with `force_reembed=True` → `resolve_entity('005930')` is not None again ✓ (confirms the fix restores the invariant)

Step 2's explicit None-assertion is the D-1 canary: without the fix, step 3 would still return None and the test would fail.

## Known Stubs

None — the `corp_{code}` fallback is a documented legacy-compat canonical name, not a UI stub; it flows through `resolve_entity` unchanged and surfaces identically to a real company name in downstream MCP search.

## Deferred

- **Phase 4 collectors (KRX, news):** Same pattern applies — each new collector should populate `fm.provenance.company_name` so the rebuild path continues to work for non-DART sources. Tracked as a Phase 4 checklist item, not in this quick-fix scope.
- **Legacy vault files without company_name:** Will render with `canonical_name='corp_00126380'` until re-collected. Acceptable because (a) collector re-runs are cheap, (b) current-ticker resolution still works (alias row is accurate), and (c) canonical_name gets overwritten on the next collect run (ON CONFLICT DO UPDATE).
- **D-2 (DART 사업보고서 RemoteDisconnected):** Still deferred per deferred-items.md recommendation — Phase 3 walking skeleton consciously accepts this for 주요사항보고서-only demo.

## Commits

| Order | Hash    | Type | Description                                                             |
| ----- | ------- | ---- | ----------------------------------------------------------------------- |
| 1     | b4facda | feat | ProvenanceBlock.company_name field + DART writer/collector plumbing     |
| 2     | 85efe29 | fix  | Worker seeds entities from frontmatter + 3 tests (W14/W15/W16)          |

## Self-Check: PASSED

- src/shared/frontmatter.py contains `company_name` field ✓
- src/collectors/dart/writer.py `write_filing` accepts `company_name=` ✓
- src/ingest/worker.py imports `upsert_entity` and calls it post-commit ✓
- tests/test_ingest_worker.py has test_W14/W15/W16 ✓
- Both commits present in git log ✓
- Full fast suite (191 tests) passes ✓
- No new untracked source files ✓
