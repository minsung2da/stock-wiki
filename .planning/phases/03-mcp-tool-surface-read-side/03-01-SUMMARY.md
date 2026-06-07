---
phase: 03-mcp-tool-surface-read-side
plan: 01
subsystem: database
tags: [postgres, alembic, sqlalchemy, fastmcp, pgvector, vchord-bm25, halfvec, hnsw, notes, fundamentals, dependency-groups]

# Dependency graph
requires:
  - phase: 01-collector-db-cutover
    provides: "filings/news halfvec(1024) embedding columns, collector_runs.source CHECK (5 sources), run_log._ALLOWED_SOURCES, _HalfVec UserDefinedType, entities.corp_code FK target + entities.sector"
  - phase: 02-decision-card-schema-storage
    provides: "shared entity_models.Base, test_migration_000N::test_orm_round_trip metadata-set pattern, 'simple' tsvector / no-'korean' lesson"
provides:
  - "mcp + ingest dependency groups re-added (fastmcp 2.x, sentence-transformers, transformers, python-mecab-ko, pgvector) — CI uv sync group references resolve"
  - "src/mcp_v2 registered as a wheel package; .mcp.json registers the stock-mcp-v2 stdio server"
  - "Alembic migration 0008 (revises 0007): notes + fundamentals tables, bm25_tokens INT[] on filings/news/notes, VectorChord-BM25 + HNSW indexes, collector_runs.source CHECK widened to 7 sources — APPLIED to live DB (alembic current == 0008)"
  - "Note + Fundamentals ORM classes on the shared Base (column-set parity); bm25_tokens on Filing/News"
  - "run_log._ALLOWED_SOURCES extended to the full 7-source set (single owner)"
  - "tests/db/test_migration_0008.py — ORM round-trip + BM25/HNSW indexes + fundamentals-no-embedding + collector_runs source CHECK regression gate"
affects: [03-02-notes-ingest, 03-05-fundamentals-peer_view, 03-06-hybrid_search, 04-analysis-runner, 05-briefing]

# Tech tracking
tech-stack:
  added:
    - "fastmcp>=2.11,<3.0 (2.14.7 installed) — MCP server framework (2.x lock per ROADMAP SC#1)"
    - "sentence-transformers>=3.0 (5.5.1) + transformers (5.10.2) — bge-m3 query embedding (in-process)"
    - "python-mecab-ko>=1.3,<2 (1.3.7) — Korean content-POS tokenization for BM25 (import name: mecab)"
    - "pgvector>=0.4 (0.4.2) — psycopg vector adapter"
  patterns:
    - "VectorChord-BM25 expression index: ((bm25_tokens)::bm25_catalog.bm25vector) bm25_catalog.bm25_ops — ported from image-tested archive 0002"
    - "HNSW on halfvec column: USING hnsw (col halfvec_cosine_ops) — halfvec opclass (NOT the plain vector opclass; columns are halfvec(1024))"
    - "Deterministic CHECK widening: DROP CONSTRAINT <named> + ADD CONSTRAINT over a fixed literal set (no runtime \\d discovery)"

key-files:
  created:
    - "src/db/migrations/versions/0008_phase03_mcp_surface.py"
    - "tests/db/test_migration_0008.py"
    - ".mcp.json"
  modified:
    - "pyproject.toml"
    - "uv.lock"
    - "src/db/entity_models.py"
    - "src/shared/run_log.py"
    - "tests/db/test_migration_0006.py"
    - "tests/db/test_migration_0007.py"

key-decisions:
  - "fastmcp pinned to 2.x (>=2.11,<3.0) per ROADMAP SC#1 + CONTEXT lock — NOT 3.x; 2.14.7 installed"
  - "notes.content_md is whole-memo TEXT + content_emb halfvec(1024) + bm25_tokens INT[] — Veto #8 (no chunking; one note = one hybrid candidate)"
  - "fundamentals is pure-NUMERIC (per/pbr/eps/bps/roe) with NO embedding column — Veto #6 (numbers are never embedded)"
  - "HNSW uses halfvec_cosine_ops (archive 0002 used the plain vector opclass on vector(1024); Phase 1 columns are halfvec(1024))"
  - "collector_runs.source CHECK widened via deterministic DROP+ADD over the fixed 7-source literal — Plan 03-01 is the SINGLE OWNER of both the CHECK and run_log._ALLOWED_SOURCES; Plans 02/05 only CALL record_collector_run"
  - ".mcp.json passes DATABASE_URL via ${DATABASE_URL} placeholder (no hard-coded secret) — T-03-02 accept disposition"

patterns-established:
  - "BM25 + HNSW dual narrative-retrieval index pair on filings/news/notes"
  - "ORM parity for a raw-SQL halfvec column via _HalfVec UserDefinedType (DDL authority stays in the migration)"

requirements-completed: [SC#1, SC#4, D-05, D-06]

# Metrics
duration: 22 min
completed: 2026-06-07
---

# Phase 3 Plan 01: MCP Read-Side Wave-0 Infrastructure Summary

**Re-added the deleted `mcp` + `ingest` dependency groups (fastmcp 2.x + sentence-transformers + python-mecab-ko), registered `src/mcp_v2` for the wheel + `.mcp.json` stdio server, authored and APPLIED Alembic migration 0008 (the `notes` + `fundamentals` tables, `bm25_tokens INT[]` columns, VectorChord-BM25 + HNSW indexes on filings/news/notes, and the deterministic widening of the `collector_runs.source` CHECK to the full 7-source set), added the `Note` + `Fundamentals` ORM classes, and extended `run_log._ALLOWED_SOURCES` — the single source-set owner that Plans 02/05 build on.**

## Performance

- **Duration:** 22 min
- **Started:** 2026-06-07
- **Completed:** 2026-06-07
- **Tasks:** 3
- **Files modified:** 9 (3 created, 6 modified)

## Accomplishments
- The `mcp` group (`fastmcp>=2.11,<3.0`, psycopg, pgvector, sqlalchemy) and `ingest` group (sentence-transformers, transformers, python-mecab-ko, pgvector) are back in `pyproject.toml`; `uv sync --group mcp --group ingest ...` installs cleanly and `import fastmcp` (2.14.7) / `import sentence_transformers` (5.5.1) / `import mecab` (1.3.7) all work in `.venv`. This closes the CI `uv sync` gap that referenced the deleted groups (Pitfall 6).
- `src/mcp_v2` is registered in `[tool.hatch.build.targets.wheel].packages` and `.mcp.json` registers a Claude Code stdio server `stock-mcp-v2` spawning `.venv/Scripts/python.exe -m mcp_v2` with `DATABASE_URL` passed through `env`.
- Migration 0008 creates the `notes` table (whole `content_md` TEXT + `content_emb halfvec(1024)` + `bm25_tokens INT[]`, Veto #8) and the `fundamentals` table (pure-numeric per/pbr/eps/bps/roe + PK `(ticker, fdate)`, Veto #6 — NO embedding), adds `bm25_tokens INT[]` to filings/news, builds VectorChord-BM25 indexes (`bm25_catalog.bm25vector` + `bm25_catalog.bm25_ops`) and HNSW indexes (`halfvec_cosine_ops`) on all three narrative tables, and widens the `collector_runs.source` CHECK to the 7-source set via a deterministic DROP+ADD of `ck_collector_runs_source`. A complete `downgrade()` reverses CHECK → indexes → columns → tables.
- `Note` and `Fundamentals` ORM classes were added on the shared `entity_models.Base` with column-set parity; `bm25_tokens` was added to `Filing` and `News`; `__all__` widened.
- `run_log._ALLOWED_SOURCES` is now `{dart, krx, news, macro, kind, fundamentals, notes_ingest}` — the single owner of the source set; Plans 02 (notes_ingest) and 05 (fundamentals) only CALL `record_collector_run`.
- **[BLOCKING] migration applied:** `alembic upgrade head` ran 0001→0008 against the live dev Postgres; `alembic current` reports `0008 (head)`.
- `tests/db/test_migration_0008.py` (4 tests, `db`-marked) green against a Postgres 17 + vchord testcontainer.

## Task Commits

Each task was committed atomically:

1. **Task 1: Re-add mcp + ingest groups, register mcp_v2, create .mcp.json** - `6ebb756` (chore)
2. **Task 2: Migration 0008 — notes + fundamentals, bm25/hnsw indexes, collector_runs CHECK widening** - `6fb6bca` (feat)
3. **Task 3: Note + Fundamentals ORM, run_log 7-source allow-list, migration 0008 tests + [BLOCKING] apply** - `bae571f` (feat)

**Plan metadata:** committed with this SUMMARY (docs).

## Files Created/Modified
- `pyproject.toml` - Re-added `[dependency-groups].mcp` + `.ingest`; added `src/mcp_v2` to wheel packages.
- `uv.lock` - Regenerated to match the re-added groups (also reflecting the pre-staged v1.0-dep removal).
- `.mcp.json` - Claude Code stdio MCP server `stock-mcp-v2` (`.venv` python `-m mcp_v2`, `DATABASE_URL` env). No in-tree analog existed.
- `src/db/migrations/versions/0008_phase03_mcp_surface.py` - Migration 0008: notes + fundamentals tables, bm25_tokens columns, BM25/HNSW indexes, collector_runs.source CHECK widening; reversible downgrade.
- `src/db/entity_models.py` - Added `Note(Base)` (whole content_md TEXT + content_emb _HalfVec(1024) + bm25_tokens, Veto #8) and `Fundamentals(Base)` (pure numeric, NO embedding, Veto #6); added `bm25_tokens` to `Filing`/`News`; widened `__all__`.
- `src/shared/run_log.py` - Extended `_ALLOWED_SOURCES` to the 7-source set; updated the docstring source enumeration.
- `tests/db/test_migration_0008.py` - 4 tests: `test_orm_round_trip` (9-table metadata + bm25_tokens on all narrative tables), `test_indexes_present` (BM25 + HNSW on filings/news/notes), `test_fundamentals_no_embedding` (Veto #6), `test_collector_runs_source_check` (widened CHECK + allow-list, both directions).
- `tests/db/test_migration_0006.py` / `tests/db/test_migration_0007.py` - Deviation fix (Rule 1): widened the `Base.metadata.tables` exact-set assertion to 9 tables (shared Base now registers notes + fundamentals).

## Decisions Made
- **fastmcp 2.x lock:** pinned `>=2.11,<3.0` per ROADMAP SC#1 + CONTEXT; 2.14.7 installed. 3.x deferred to a future explicit decision.
- **Veto #8 for notes:** `content_md` is whole-memo TEXT, no chunk column; the hybrid candidate is one whole note row, exactly like filings/news.
- **Veto #6 for fundamentals:** pure-numeric typed columns only, NO embedding; `peer_view` (Plan 05) computes `entities.sector` `percentile_cont(0.5)` medians over this table.
- **halfvec_cosine_ops:** the Phase 1 embedding columns are `halfvec(1024)` (not the plain `vector(1024)` archive 0002 used), so the HNSW indexes use the halfvec opclass.
- **Single CHECK/allow-list owner:** the `collector_runs.source` CHECK widening and `run_log._ALLOWED_SOURCES` extension are both authored here (lockstep), so the notes-ingest (Plan 02) and fundamentals (Plan 05) collectors can `record_collector_run` without touching either edit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Stale `Base.metadata.tables` exact-set assertions in test_migration_0006 + test_migration_0007**
- **Found during:** Task 3 (regression run after adding the `Note`/`Fundamentals` ORM classes).
- **Issue:** Both `test_migration_0006.py::test_orm_round_trip` and `test_migration_0007.py::test_orm_round_trip` assert `set(Base.metadata.tables) == {N tables}` (6+1 and 7 respectively). The new ORM classes register on the SAME shared declarative `Base` (the project's locked single-Base design, RESEARCH A3), so the metadata now lists 9 tables and both exact-equality assertions failed (`Extra items: 'notes', 'fundamentals'`). This is the same pattern Plan 02-01 hit when it added `DecisionCard`.
- **Fix:** Added `"notes"` and `"fundamentals"` to the expected set in both assertions only. The per-model column-parity loops were left untouched (they iterate only their own phase's models, which are unaffected).
- **Files modified:** `tests/db/test_migration_0006.py`, `tests/db/test_migration_0007.py`
- **Verification:** `pytest tests/db/test_migration_0006.py::test_orm_round_trip tests/db/test_migration_0007.py::test_orm_round_trip` green.
- **Committed in:** `bae571f` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug — stale shared-metadata assertions in two prior-phase tests).
**Impact on plan:** Necessary for suite correctness; a direct, expected consequence of the locked single-Base design. No scope creep — the migration, ORM, run_log edit, `.mcp.json`, and dependency groups match the plan exactly.

## Deferred / Out of Scope
- The actual `src/mcp_v2/` server code (server.py, tools/*, retrieval.py, injection.py, embedding.py, tokenizer.py, paths.py, models.py, errors.py) is NOT in this plan — Plans 03-03/04/06 build it. This plan only registers the package + `.mcp.json` so the wheel build / pytest import path / Claude Code registration are ready.
- The notes-ingest job (Plan 02) and the embedding/tsv/bm25 backfill of existing filings/news rows are NOT in this plan — they populate the columns/indexes this plan creates.
- The fundamentals collector (Plan 05) is NOT in this plan — it writes the `fundamentals` table this plan creates.

## Known Stubs
None. The migration creates real tables/columns/indexes (all verified applied to the live DB and against a testcontainer). `.mcp.json` points at `-m mcp_v2`, which does not exist as runnable code yet — but that is by design (the server is built in later plans); it is a registration artifact, not a stub returning fake data. No hardcoded empty values or placeholder UI data introduced.

## Threat Flags
None beyond the plan's threat model.
- T-03-SC (re-added pip installs): all three packages are slopcheck-OK + prior project use (RESEARCH § Package Legitimacy Audit, no [ASSUMED]/[SUS]/[SLOP]); pins are exact ranges; install succeeded — mitigated.
- T-03-01 (migration raw SQL): DDL is static module-level strings; CHECK widening is a deterministic DROP+ADD over a fixed 7-source literal; `downgrade()` reverses cleanly — mitigated.
- T-03-02 (`.mcp.json` DATABASE_URL): passed via `${DATABASE_URL}` placeholder, not hard-coded; local single-user — accept.
- T-veto6 (fundamentals shape): pure-numeric, no embedding column; `test_fundamentals_no_embedding` asserts it at both the column-name and pg_attribute catalog level — mitigated.

## Issues Encountered
- `uv` is not on the Bash PATH; used the absolute uv path for `uv sync` and the project `.venv/Scripts/python.exe` for all tests/alembic/lint. No impact on results.
- mypy strict reports `var-annotated` on the new `bm25_tokens` columns — this is the IDENTICAL pattern as the pre-existing `News.tickers` column (and `_HalfVec`'s generic), which already fails mypy on the committed baseline. mypy is not a pre-commit/CI green gate here (pre-commit = gitleaks + ruff only); the new code matches the established `sa.Column(postgresql.ARRAY(...))` convention. Not a regression of any passing gate.
- SQLAlchemy reflection emits `SAWarning: Did not recognize type 'halfvec'` during ORM round-trip — benign; the test compares column NAMES, not types, and `_HalfVec` is the project's established adapter.

## User Setup Required
None. Postgres is running and at 0008; `.env` already carries `DATABASE_URL`. The `.mcp.json` server entry will only function once `src/mcp_v2/` is implemented in later plans.

## Next Phase Readiness
- Schema prerequisites for `hybrid_search` (Plan 06: `bm25_tokens` + BM25/HNSW indexes + `notes` table) and `peer_view` (Plan 05: `fundamentals` table) exist and are applied.
- `record_collector_run` accepts `fundamentals` + `notes_ingest`, unblocking the Plan 02 notes-ingest and Plan 05 fundamentals collectors.
- Dependency groups + wheel package + `.mcp.json` are ready for the `src/mcp_v2/` server build (Plans 03-03/04/06).
- No blockers.

## Self-Check: PASSED

All created/modified files exist on disk (pyproject.toml, .mcp.json, migration 0008, entity_models.py, run_log.py, test_migration_0008.py — all FOUND). All three task commits (`6ebb756`, `6fb6bca`, `bae571f`) present in git log. `alembic current` == `0008 (head)`. `tests/db/test_migration_0008.py` — 4 passed (`-m db`); `test_migration_0006/0007::test_orm_round_trip` green after the deviation fix. ruff check + ruff format clean on all changed files.

---
*Phase: 03-mcp-tool-surface-read-side*
*Completed: 2026-06-07*
