---
phase: 07-graph-layer-graphify-integration
plan: 02
subsystem: graph-edge-population
tags: [wave-1, graph-01, edges, alembic, ingest-hook]
requires:
  - 07-01 (graphifyy installed; probe-findings.md DART supersedes MISSING; tests/graph stubs scaffolded)
provides:
  - "Migration 0004 with ck_edge_type_phase7 reinstating 6-value edge_type enum"
  - "src/ingest/edges.py — populate() entry point + 6 _derive_* functions + EDGE_TAG_POLICY"
  - "Worker batch-tail hook auto-invokes edges.populate() per ingest run"
  - "ingest_runs source='edges' row + heartbeat 'edges' source block"
affects:
  - tests/stock_mcp/conftest.py (fixture _seed_test_edges cutover to new enum)
  - tests/stock_mcp/test_get_related.py (Phase 7 filter for non-document neighbors)
tech_stack_added: []
patterns:
  - "Pre-validate then ALTER TABLE — migration aborts on illegal rows with descriptive RuntimeError"
  - "Synthetic event_id ({corp_code}-{event_type}-{ISO}) bypasses empty events table (RESEARCH Pitfall 1)"
  - "Soft-fail per derivation — exception in one _derive_* does not block others; truncated to 200ch"
  - "Edge population in its own engine.begin() so doc commits survive edge failures (D-04)"
key_files_created:
  - src/db/migrations/versions/0004_phase07_edge_check.py
  - src/ingest/edges.py
  - .planning/phases/07-graph-layer-graphify-integration/07-02-SUMMARY.md
key_files_modified:
  - src/ingest/worker.py
  - tests/db/test_migration_0004.py
  - tests/graph/conftest.py
  - tests/graph/test_edges_deterministic.py
  - tests/graph/test_edges_derived.py
  - tests/graph/test_edges_idempotency.py
  - tests/test_ingest_worker.py
  - tests/stock_mcp/conftest.py
  - tests/stock_mcp/test_get_related.py
key_decisions:
  - "supersedes derivation degrades to soft no-op (counters['supersedes_skipped_no_field']) — DART writer correction-of field still MISSING per probe-findings.md; deferred to follow-up quick task"
  - "Event ID = f'{corp_code}-{event_type}-{first_seen_at.isoformat()}' — synthetic, locked in this plan, lets filing_event/event_event ship without depending on empty events table"
  - "Constraint name ck_edge_type_phase7 (not phase2) — fresh constraint avoids 0003 downgrade collision"
  - "ingest_runs counters live at stats['edges_warning'] JSONB sub-key — no schema change (CONTEXT D-04 amendment 2026-05-05)"
  - "Conftest 2-hop chain reordered to ids[0]→ids[1]→ids[3] so existing depth=2 test keeps working under new edge_type enum"
metrics:
  duration_minutes: ~40
  completed_date: 2026-05-06
  tasks: 3
  commits:
    - 031bf94
    - 804235d
    - 4a28833
  files_changed: 12
---

# Phase 07 Plan 02: GRAPH-01 Typed-Edge Population Pipeline Summary

GRAPH-01 ships end-to-end: Alembic migration 0004 reinstates a 6-value edge_type CHECK with pre-validate abort, `src/ingest/edges.py` houses six derivation functions (`ticker_sector`, `mentions_ticker`, `note_ticker`, `supersedes`, `filing_event`, `event_event`) behind an idempotent `populate()` entry point, and `src/ingest/worker.py` invokes that entry point as a post-pass at every ingest batch tail with a separate transaction so document commits survive edge failures.

## What Changed

### Migration 0004 — `src/db/migrations/versions/0004_phase07_edge_check.py`
- Adds `ck_edge_type_phase7` CHECK constraining `edges.edge_type` to the 6-value Phase 7 enum.
- Pre-validates by `SELECT DISTINCT edge_type FROM edges WHERE edge_type <> ALL(:allowed)` and raises `RuntimeError("Migration 0004 blocked: ...")` on offending rows so silent corruption is impossible.
- Bind-parameterized SQL throughout (T-7-02-01 mitigation).
- Constraint name is fresh (`...phase7`) so the Phase 6 0003 downgrade cannot collide.

### `src/ingest/edges.py` — single-module pipeline
- Public surface: `populate(doc_ids, conn) -> dict` and `EDGE_TAG_POLICY`.
- Six derivations wired in `_DERIVATIONS` tuple; the dispatch loop catches per-derivation exceptions and writes `counters['failed_per_type'][edge_type] = str(exc)[:200]` (V7 ASVS — no PII to ingest_runs).
- Endpoint conventions locked verbatim from PLAN `<interfaces>`:
  - `mentions_ticker`: document → ticker (news ProvenanceBlock.tickers OR DART corp_code→entities.current_ticker fallback)
  - `note_ticker`: note(document) → ticker (only frontmatter `_derived.tickers`; body 6-digit hits land in `counters['unmatched_body_tickers']` per D-08)
  - `ticker_sector`: ticker → sector (corpus-wide; idempotent)
  - `supersedes`: amendment(document) → original(document) **— soft no-op today**; probe-findings.md MISSING means the function only increments `counters['supersedes_skipped_no_field']` and returns. The PLAN template B path was kept; the FOUND template was deleted, so exactly one `def _derive_supersedes(...)` definition exists.
  - `filing_event`: document → event (synthetic `{corp_code}-{event_type}-{first_seen_at.isoformat()}`)
  - `event_event`: event(prev) → event(curr) for same-corp_code pairs within `0 < delta_days <= 90` (D-09 boundary inclusive of 90)
- All endpoint values pass through `_TICKER_RE` (`^[0-9]{6}$`) or `_CORP_CODE_RE` (`^[0-9]{8}$`) before insertion (T-7-02-03).
- `_INSERT_EDGE_SQL` uses `ON CONFLICT ON CONSTRAINT uq_edge_endpoints DO NOTHING` (D-02 idempotency).

### `src/ingest/worker.py` — batch-tail hook
- After the per-doc `process_document` loop, `engine.begin() as conn:` opens a new transaction and calls `edges_populate(committed_doc_ids, conn)`. A top-level `try/except` writes `edges_counters = {"error": str(exc)[:200]}` on failure so doc commits remain (D-04 + T-7-02-06 mitigation).
- Inserts one `ingest_runs` row per ingest with `kind='edges'`, `source='edges'`, and `stats['edges_warning'] = full_counters` (per CONTEXT D-04 amendment 2026-05-05 — no schema change).
- Calls `record_source_run('edges', ..., extra=edges_counters)` so heartbeat has an `edges` source block; the `extra=` kwarg is the heartbeat helper's merging key, NOT a DB column.
- `process_document` return shape now includes both `doc_id` and `document_id` (alias) so the worker loop can collect committed ids without breaking older callers that read `doc_id`.

### Test wiring
- **`tests/db/test_migration_0004.py`** — three real tests (clean upgrade / pre-validate abort / downgrade) using `alembic.command.upgrade`/`downgrade` against the session pg_engine. Local `at_head` fixture restores head after each test so cross-file state cannot leak.
- **`tests/graph/conftest.py` `seed_edges`** — implemented. Truncates edges/chunks/documents/entity_aliases/entities, seeds Samsung entity (with sector for ticker_sector), then writes 3 throwaway markdown files under `tmp_path` (DART filing with event_type, news with ProvenanceBlock.tickers, note with `_derived.tickers`). Optional `with_event_chain=True` adds a second DART filing 30 days later for `event_event` test.
- **`tests/graph/test_edges_deterministic.py`** — 4 real tests + 1 xfail (`test_supersedes_from_dart_correction_field`, strict=True, deferred to DART writer fix) + 1 companion (`test_supersedes_soft_noop_increments_counter`).
- **`tests/graph/test_edges_derived.py`** — 2 real tests (filing_event single-field, event_event 30-day chain).
- **`tests/graph/test_edges_idempotency.py`** — populate-twice idempotent + soft-fail proven by monkeypatching `_derive_event_event` to raise; counter truncation ≤ 200 chars asserted.
- **`tests/test_ingest_worker.py::test_W17`** — end-to-end: seed Samsung entity with sector, ingest one DART doc, assert `edges` table has ≥1 ticker_sector row, assert `ingest_runs` has `source='edges'` row with `edges_warning` JSONB sub-key, assert heartbeat has `edges` source block.
- **`tests/stock_mcp/conftest.py`** — `_seed_test_edges` cutover to the new 6-value enum (mentions_ticker / filing_event / supersedes), preserving the 2-hop chain `ids[0] → ids[1] → ids[3]` that `test_get_related_depth2_includes_two_hop` requires. Tag column written for every edge.
- **`tests/stock_mcp/test_get_related.py`** — depth=1 enum assertion updated; cycle test insert uses `filing_event` (now in enum); snippet/vault_path test filters to document-typed neighbors (event neighbors legitimately have no vault_path).

## Verification Evidence

```
$ uv run pytest tests/db/test_migration_0004.py -x
3 passed in 54.44s

$ uv run pytest tests/graph/test_edges_deterministic.py tests/graph/test_edges_derived.py tests/graph/test_edges_idempotency.py -x
8 passed, 1 xfailed in 19.47s
  (xfail: test_supersedes_from_dart_correction_field — probe MISSING)

$ uv run pytest tests/test_ingest_worker.py::test_W17_worker_runs_edges_populate_at_batch_end -x
1 passed in 14.90s

$ uv run pytest tests/graph/ tests/db/test_migration_0004.py tests/test_ingest_worker.py tests/stock_mcp/
138 passed, 12 skipped, 1 xfailed in 520.02s
  (after Rule-1 test-fix; see Deviations)

$ grep -c "_derive_" src/ingest/edges.py
15
$ grep -c "^def _derive_supersedes" src/ingest/edges.py
1
$ ! grep -E "import (anthropic|openai)" src/ingest/edges.py
(no hits — COLL-07 OK)

$ uv run python -c "from ingest import edges; assert callable(edges.populate); print(sorted(edges.EDGE_TAG_POLICY.keys()))"
['event_event', 'filing_event', 'mentions_ticker', 'note_ticker', 'supersedes', 'ticker_sector']
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `test_get_related_includes_snippet_and_vault_path_for_documents` assumed all neighbors are documents**

- **Found during:** Task 3 full regression sweep on `tests/stock_mcp/`.
- **Issue:** Phase 6 fixture corpus DART markdown files have `_derived.event_type` populated (Phase 5 enrichment artefacts). Plan 02 wires `edges.populate()` into the ingest worker, so when `mcp_vault_engine` ingests the fixture, `_derive_filing_event` legitimately emits `document → event(synthetic id)` edges. `get_related` then surfaces those event neighbors, which have no `vault_path` / no `snippet_200ch` by design.
- **Fix:** Replaced the loop's "all neighbors are documents" assumption with a filter to document-typed neighbors (id length 64, hex). The Phase 7 contract is intentionally heterogeneous — events and tickers are first-class neighbors now — so only document neighbors should be checked for vault_path/snippet.
- **Files modified:** `tests/stock_mcp/test_get_related.py`
- **Commit:** 4a28833

**2. [Rule 3 - Blocking] sqlalchemy / beartype / authlib partial venv reinstall**

- **Found during:** Task 1 verification — pytest collection failed with cascading `ModuleNotFoundError`s (`beartype.meta`, `authlib.consts`).
- **Issue:** Same pattern as Plan 01 deviation #3 — partial-install race after a prior `uv sync` left dependent packages in inconsistent states.
- **Fix:** `UV_LINK_MODE=copy uv sync --all-groups --reinstall` restored every package in one atomic pass.
- **Files modified:** none (env-only)
- **Commit:** none (env state only)

**3. [Rule 1 - Bug] Conftest 2-hop chain reorder to keep `test_get_related_depth2_includes_two_hop` passing**

- **Found during:** Task 1 acceptance grep planning.
- **Issue:** PLAN `<action>` Step 2 substitution table mapped the conftest seed to `ids[0]→ticker '005930'`, `ids[0]→ids[2]`, `ids[1]→ids[3]`. That breaks the 2-hop chain from `ids[0]` (no path reaches depth 2) and would silently fail `test_get_related_depth2_includes_two_hop`.
- **Fix:** Replaced the substitution with `ids[0]→ids[1] (filing_event)`, `ids[0]→ids[2] (mentions_ticker)`, `ids[1]→ids[3] (supersedes)` — same 6-tuple shape, same enum values, but preserves the `ids[0]→ids[1]→ids[3]` chain the depth=2 test depends on. Documented inline.
- **Files modified:** `tests/stock_mcp/conftest.py`
- **Commit:** 031bf94

## DART Supersedes — Status Unchanged from Plan 01

`_derive_supersedes` ships as a soft no-op per Plan 01 SUMMARY guidance:
- `counters['supersedes_skipped_no_field'] += len(doc_ids)` per call.
- Zero `supersedes` rows inserted in tests; `test_supersedes_soft_noop_increments_counter` asserts this contract holds today.
- Companion `test_supersedes_from_dart_correction_field` is `pytest.mark.xfail(strict=True, reason="probe-findings.md MISSING ...")` — auto-flips to fail when the DART writer is enhanced (signaling that the no-op should be replaced).
- Follow-up quick task scope: extend `src/collectors/dart/writer.py` to surface `[기재정정]` prefix detection or `notice_search` / `pblntf_detail_ty='I001'` lookup, populate `provenance.correction_of_rcept_no`, then swap `_derive_supersedes` from no-op to TEMPLATE A path documented in PLAN.

## Threat Flags

None. Plan 02 introduces no new network endpoints, no new auth surfaces, no new schema beyond a single CHECK constraint. All SQL uses `sa.text()` with bind parameters; ticker/corp_code regex pre-filters; counter truncation at 200 chars; edges.populate() in its own transaction so doc commits cannot be rolled back by edge failures (T-7-02-06 explicitly mitigated). Threat register entries from PLAN `<threat_model>` are all `mitigate` and verified.

## Self-Check: PASSED

- `src/db/migrations/versions/0004_phase07_edge_check.py` exists with `revision = "0004"`, `down_revision = "0003"`, literal `ck_edge_type_phase7`, all 6 enum names, and `Migration 0004 blocked:` text.
- `src/ingest/edges.py` exists at 395 lines (well under 800), exports `populate` and `EDGE_TAG_POLICY` with exactly 6 keys; contains exactly one `def _derive_supersedes(`; no `anthropic`/`openai` imports.
- `src/ingest/worker.py` imports `from ingest.edges import populate as edges_populate`, calls it at batch tail, writes `ingest_runs` row with `kind='edges'`/`source='edges'` and `stats['edges_warning']` JSONB sub-key, calls `record_source_run("edges", ...)` with `extra=edges_counters`.
- All 3 migration tests, 8 graph edge tests + 1 xfail, and `test_W17` pass in CI-equivalent runs above.
- `tests/stock_mcp/test_get_related.py` and `tests/stock_mcp/conftest.py` carry no occurrence of the old `'mentions'` / `'references'` / `'precedes'` / `'same_sector'` literals (only legitimate `mentions_ticker` substring).
- Commits exist: `031bf94` (Task 1), `804235d` (Task 2), `4a28833` (Task 3).
