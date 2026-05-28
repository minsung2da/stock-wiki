# Phase 1 — Collector DB-Direct Cutover · Plan Index

**Phase:** `01-collector-db-cutover`
**Milestone:** v2.0 — DB-direct redesign
**Plans:** 9
**Waves:** 4 (0 → 1 → 2 → 3)
**Created:** 2026-05-29

## Wave Structure

| Wave | Plans (parallel within wave) |
|------|------------------------------|
| 0    | 01-01, 01-02 |
| 1    | 01-03, 01-04 |
| 2    | 01-05, 01-06, 01-07 |
| 3    | 01-08, 01-09 |

**Why this shape:**
- Wave 0 = schema + CLI gate. Every other plan depends on the migration head
  (`01-01`) and the new collector signatures (`01-02`).
- Wave 1 = simplest collectors (macro = pure numeric; krx = numeric + FK).
  Parallel because they touch disjoint files.
- Wave 2 = body-bearing or multi-table collectors. KIND writes filings+events;
  news writes body_md + tickers[]; DART writes the largest body. Parallel.
- Wave 3 = cross-cutting cleanup. 01-08 touches all 5 `__init__.py` (observability
  wiring); 01-09 touches all 5 `writer.py` (deletion). They share NO files,
  so they run parallel within Wave 3.

## Plan Summary

| # | Plan | Wave | Depends on | One-line objective |
|---|------|------|------------|---|
| 01-01 | Schema migration 0006 + ORM models | 0 | — | Create `filings`, `news`, `ohlcv`, `macro_series`, `events`, `collector_runs`; rename legacy `events → events_legacy`; add ORM models in `src/db/entity_models.py` |
| 01-02 | CLI cleanup + collector signature strip | 0 | — | Remove `--vault-root` from argparse and all 5 collector signatures; update `_dispatch` test fakes |
| 01-03 | macro collector cutover → `macro_series` | 1 | 01-01, 01-02 | UPSERT observations with R-06 revision detection; delete vault writer call site |
| 01-04 | krx collector cutover → `ohlcv` | 1 | 01-01, 01-02 | UPSERT OHLCV+flow+short with COALESCE T+2 short fill-in; preserve R-03 missing_entity / holiday semantics |
| 01-05 | kind collector cutover → `filings` + `events` | 2 | 01-01..04 | Paired write: DART pblntf_ty='I' filings UPSERT + events INSERT (UNIQUE ON CONFLICT DO NOTHING); FK from events.filing_rcept_no |
| 01-06 | news collector cutover → `news` | 2 | 01-01..04 | UPSERT on url_hash (full sha256); tickers TEXT[] via GIN; preserve R-09 startup guard + D-13 2-paragraph cap |
| 01-07 | dart collector cutover → `filings` | 2 | 01-01..04 | UPSERT on rcept_no with WHOLE body_md (Veto #8 — no chunking); preserve Bug C entity upsert |
| 01-08 | Observability — `record_collector_run` + delete heartbeat.py | 3 | 01-03..07 | New `shared.run_log` helper; INSERT into `collector_runs` per run (best-effort); structured stderr log; CI guard `test_no_heartbeat.py` |
| 01-09 | Writer deletion + Veto #9 fences + Success Criteria Coverage | 3 | 01-03..07 | Delete 5 writer.py files; `test_no_writer.py` + runtime guard in `cli/__main__.py`; smoke test; SC coverage matrix |

## Success Criteria Coverage

(Final matrix; full version in `01-09-SUMMARY.md` after execution.)

| ROADMAP SC # | Description | Satisfied by |
|---|---|---|
| SC-1 | DART INSERTs to filings, no vault/raw/ recreation | 01-01 (schema), 01-02 (CLI), 01-07 (collector), 01-09 (fence) |
| SC-2 | krx/news/macro/kind INSERTs + UPSERT dedup | 01-01, 01-03, 01-04, 01-05, 01-06 |
| SC-3 | `shared/heartbeat.py` deleted; structured logs | 01-08 |
| SC-4 | `--vault-root` removed from CLI | 01-02 |
| SC-5 | `tests/collectors/` validates INSERT paths | 01-03, 01-04, 01-05, 01-06, 01-07, 01-09 |
| SC-6 | `stock-enrich-daily` Routine — no action required | n/a |

## Cross-Cutting Hard Veto Enforcement

| Veto | Where enforced |
|---|---|
| #6 — no numeric embeddings | 01-01 schema: ohlcv/macro_series/events have no body/embedding cols. Tests in 01-01 assert this. |
| #8 — no DART pre-chunking | 01-01 schema: `filings.body_md TEXT NOT NULL` (whole). 01-07 asserts 200KB roundtrip + `chunks` count == 0 after dart run. |
| #9 — no vault revival | 01-09: writer files deleted; `test_no_writer.py` CI guard; runtime guard in CLI; smoke test asserts `vault/raw/` absent. |

## How to execute

After all plans are reviewed/approved by the user, run waves in order:

```bash
# Wave 0 (sequential gate)
gsd-executor 01-01-PLAN.md
gsd-executor 01-02-PLAN.md

# Wave 1 (parallel)
gsd-executor 01-03-PLAN.md &
gsd-executor 01-04-PLAN.md &
wait

# Wave 2 (parallel)
gsd-executor 01-05-PLAN.md &
gsd-executor 01-06-PLAN.md &
gsd-executor 01-07-PLAN.md &
wait

# Wave 3 (parallel)
gsd-executor 01-08-PLAN.md &
gsd-executor 01-09-PLAN.md &
wait
```

Per `/gsd-execute-phase 1` the orchestrator handles the wave-by-wave
parallelism. This index is documentary.

## Open Questions Carried Forward (from RESEARCH.md §"Open questions remaining for the planner")

| # | Question | Disposition |
|---|---|---|
| 1 | Live DB inventory — does anyone have a populated `events` table today? | Plans assume **A1** (empty). Migration 0006 docstring documents the assumption; if it fails, the rename is still safe because no FK points into the new `events` shape. Not blocking. |
| 2 | `events` → `kind_events` vs `events_legacy` + new `events` naming | Picked the latter (researcher recommendation). |
| 3 | testcontainer Korean locale | Not Phase 1 blocking; flagged for Phase 3 BM25 work. |
| 4 | `collector_runs` retention | Phase 9 concern. |
| 5 | `macro_revisions` audit table | Out of scope; revisions surface via log + `extra` JSONB. |
| 6 | News test fixture migration cost (~1/3 of churn) | Absorbed into 01-06 task 3 (port tests). |
| 7 | `_PHASE2_TABLES` → `_LIVE_TABLES` rename | Done in 01-01 task 3. |
| 8 | `# noqa: ARG001` on `collect_macro.engine` removal | Done in 01-03 task 2. |
