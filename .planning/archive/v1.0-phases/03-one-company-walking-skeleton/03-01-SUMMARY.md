---
phase: 03-one-company-walking-skeleton
plan: 01
subsystem: database
tags: [alembic, pgvector, vchord_bm25, hnsw, bm25, migration, probes, dart-fss]

requires:
  - phase: 02-canonical-entity-identity
    provides: "chunks table base shape (id/document_id/ord/text/embedding_model/embedding) + documents table + resolve_entity surface"
provides:
  - "Migration 0002 applied: chunks.section_path, chunks.section_index, chunks.bm25_tokens (INT[])"
  - "documents.corp_code CHAR(8) + ix_documents_corp_code btree (RET-02 filter surface)"
  - "HNSW index ix_chunks_embedding_hnsw (vector_cosine_ops) — STORE-03"
  - "BM25 expression index ix_chunks_bm25 on ((bm25_tokens)::bm25vector) — STORE-04"
  - "Canonical vchord_bm25 SQL patterns (cast + search_bm25query) verified and recorded in probe-findings.md"
  - "Locked Phase 3 dependency set in pyproject.toml (sentence-transformers, python-mecab-ko, tenacity; no ollama, no anthropic in mcp)"
  - "pg_with_chunks_row test fixture reusable by Plan 02/04/05"
affects: [03-02, 03-03, 03-04, 03-05, 03-06]

tech-stack:
  added:
    - sentence-transformers>=3.0
    - transformers>=4.44
    - python-mecab-ko>=1.3,<2
    - tenacity>=9.0
  patterns:
    - "BM25 expression index `((bm25_tokens)::bm25_catalog.bm25vector) bm25_catalog.bm25_ops`"
    - "Migration self-contained: CREATE EXTENSION IF NOT EXISTS vchord_bm25 + pg_trgm inside 0002 for testcontainer parity"
    - "Probe-findings.md as append-only log for API-shape assumptions (A4, A5)"

key-files:
  created:
    - src/db/migrations/versions/0002_phase03_chunking_columns.py
    - tests/test_migration_0002.py
    - tests/test_api_probes.py
    - .planning/phases/03-one-company-walking-skeleton/probe-findings.md
  modified:
    - pyproject.toml
    - tests/conftest.py
    - .env.example

key-decisions:
  - "BM25 index is an EXPRESSION index on `((bm25_tokens)::bm25_catalog.bm25vector)` — bm25_ops opclass targets bm25vector, implicit cast from INT[] exists but can only be materialised inside an expression index"
  - "Migration 0002 idempotently CREATEs vchord_bm25 + pg_trgm extensions (self-contained for testcontainers)"
  - "`hnsw.iterative_scan = 'relaxed_order'` is session GUC only — migration tests verify SET works, query code sets it per session (D-13)"
  - "documents.corp_code column + btree index added now (RET-02) so Plan 04 worker writes it and Plan 05 hybrid_search filters on it without JSONB probes"
  - "DART_API_KEY added alongside OPEN_DART_API_KEY in .env.example (dart-fss accepts either via explicit set_api_key call)"

patterns-established:
  - "Migration expression indexes: `CREATE INDEX ... USING {method} ((expr)::type opclass)` pattern for vchord_bm25"
  - "Probe test template: `_record_finding(test_name, finding)` appends to phase probe-findings.md best-effort (never fails test)"
  - "INT[] → bm25vector cast via `CAST(:arr AS int[])` bind param — no f-string SQL"

requirements-completed: [STORE-03, STORE-04, INGEST-12]

duration: 18min
completed: 2026-04-17
---

# Phase 03 Plan 01: Schema Extension + API Probes Summary

**Migration 0002 live (section_path/section_index/bm25_tokens + corp_code + HNSW/BM25 indexes) and dart-fss/vchord_bm25 probes validate RESEARCH.md assumptions A4/A5 for downstream plans.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-04-17T13:10Z
- **Completed:** 2026-04-17T13:35Z
- **Tasks:** 2
- **Files created:** 4
- **Files modified:** 3

## Accomplishments

- Migration 0002 applied to live `stock-postgres` container (2026-04-17 13:30Z). `information_schema` verified: 3 new chunks columns + 1 new documents column + 3 new indexes (HNSW, BM25, btree).
- 6/6 migration integration tests green (column types, index defs, session GUC, downgrade/upgrade idempotency).
- 2/3 probe tests green (BM25 cast + end-to-end scoring). DART probe cleanly SKIPPED when `DART_API_KEY` unset; full body-shape assertion wired for when key is provided.
- Canonical SQL patterns recorded in `probe-findings.md`:
  - `bm25_catalog._vchord_bm25_cast_array_to_bm25vector(CAST(:arr AS int[]), -1, true)` → `{id:freq, ...}` sparse-weighted text form
  - End-to-end scoring via `search_bm25query((c.bm25_tokens)::bm25vector, to_bm25query('ix_chunks_bm25'::regclass, CAST(:q AS int[])::bm25vector))` — scores decrease monotonically with overlap count
- Locked Phase 3 dependency set: `sentence-transformers`, `transformers`, `python-mecab-ko`, `tenacity` added to ingest group; `ollama` removed from ingest; `anthropic` removed from mcp group (COLL-07 boundary enforcement).
- `[project.scripts]` entries added for `stock-mcp` and `stock` CLI (D-20 foundation for Plan 06).

## Task Commits

1. **Task 1: Migration 0002 adds section/bm25 columns + HNSW/BM25 indexes** — `35682b2` (feat)
2. **Task 2: dart-fss + vchord_bm25 API probes de-risk A4/A5** — `7f0e769` (test)

## Files Created/Modified

- `src/db/migrations/versions/0002_phase03_chunking_columns.py` — Alembic 0002 upgrade/downgrade (including `CREATE EXTENSION IF NOT EXISTS vchord_bm25, pg_trgm`)
- `tests/test_migration_0002.py` — 6 integration tests (information_schema, pg_indexes, iterative_scan SET, downgrade/upgrade round-trip)
- `tests/test_api_probes.py` — 3 probes (dart-fss SLOW/skippable, INT[] cast, end-to-end BM25 scoring)
- `.planning/phases/03-one-company-walking-skeleton/probe-findings.md` — append-only API-shape log (A4/A5 evidence)
- `pyproject.toml` — ingest/mcp dep group updates + `[project.scripts]`
- `tests/conftest.py` — `pg_with_chunks_row` fixture
- `.env.example` — `DART_API_KEY` entry

## Decisions Made

- **Expression BM25 index** (not plain column index): `bm25_catalog.bm25_ops` targets `bm25vector`, so `CREATE INDEX ... USING bm25 (((bm25_tokens)::bm25_catalog.bm25vector) bm25_catalog.bm25_ops)` — rationale: `pg_cast integer[] -> bm25vector` with context 'i' (implicit) exists but raw `USING bm25 (bm25_tokens bm25_catalog.bm25_ops)` errors "operator class does not accept data type integer[]". The expression index forces the cast at index-maintenance time.
- **Migration self-contained for testcontainers**: `CREATE EXTENSION IF NOT EXISTS vchord_bm25, pg_trgm` lives inside the upgrade body. docker-compose's `init-extensions.sql` still works for first boot; testcontainers (which bypass the entrypoint script) now get the extensions via migration.
- **`documents.corp_code` added now, not in Plan 04**: keeps RET-02 filter surface available for Plan 05 hybrid_search without schema churn mid-phase. Plan 04 worker will populate the column during upsert.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] BM25 index required expression form**
- **Found during:** Task 1 (first `alembic upgrade head` against live container)
- **Issue:** `CREATE INDEX ix_chunks_bm25 ON chunks USING bm25 (bm25_tokens bm25_catalog.bm25_ops)` fails with `operator class "bm25_catalog.bm25_ops" does not accept data type integer[]` — the opclass operates on `bm25vector`, not `integer[]`.
- **Fix:** Rewrote to expression index `(((bm25_tokens)::bm25_catalog.bm25vector) bm25_catalog.bm25_ops)`. The `pg_cast integer[] -> bm25vector` entry handles materialization at index time.
- **Files modified:** `src/db/migrations/versions/0002_phase03_chunking_columns.py`
- **Verification:** `docker exec stock-postgres psql -U stockwiki -d stockwiki -tAc "SELECT indexdef FROM pg_indexes WHERE indexname='ix_chunks_bm25'"` returns the expression form; test 3 (end-to-end BM25 scoring) passes.
- **Committed in:** `35682b2`

**2. [Rule 3 - Blocking] vchord_bm25 + pg_trgm extensions missing in testcontainer**
- **Found during:** Task 1 (first `uv run pytest tests/test_migration_0002.py`)
- **Issue:** Testcontainers boot of `tensorchord/vchord-suite:pg17-latest` doesn't auto-run `scripts/init-extensions.sql` (the docker-entrypoint-initdb.d script is bypassed). Migration failed with `schema "bm25_catalog" does not exist`.
- **Fix:** Added `op.execute("CREATE EXTENSION IF NOT EXISTS vchord_bm25")` + `op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")` at the top of the 0002 upgrade. Idempotent against live compose DB (extensions already present, IF NOT EXISTS short-circuits).
- **Files modified:** `src/db/migrations/versions/0002_phase03_chunking_columns.py`
- **Verification:** Live docker-compose DB already had extensions → re-running migration is no-op. Testcontainers runs now pass all 6 tests.
- **Committed in:** `35682b2`

---

**Total deviations:** 2 auto-fixed (both Rule 3 blocking)
**Impact on plan:** Both deviations essential. Neither changes plan intent; both preserve test parity between testcontainer and live DB.

## Issues Encountered

- Pre-commit `ruff` line-length (E501) flagged the migration module docstring one-liner (108 chars). Split into short opening line + paragraph — no code change, pre-commit re-ran clean.
- Pre-commit `ruff-format` auto-reformatted `tests/test_migration_0002.py` and `tests/test_api_probes.py` once each; re-staged and committed successfully.

## Canonical SQL Patterns (for Plans 04 + 05)

### BM25 token cast

```sql
-- Inside SELECT / ORDER BY or anywhere a bm25vector is expected:
(c.bm25_tokens)::bm25_catalog.bm25vector
-- or, for a Python-provided literal array:
CAST(:tokens AS int[])::bm25_catalog.bm25vector
```

### End-to-end BM25 ranking (Plan 05 hybrid_search ORDER BY clause)

```sql
ORDER BY bm25_catalog.search_bm25query(
    (c.bm25_tokens)::bm25_catalog.bm25vector,
    bm25_catalog.to_bm25query(
        'ix_chunks_bm25'::regclass,
        CAST(:q_tokens AS int[])::bm25_catalog.bm25vector
    )
) DESC NULLS LAST
```

Verified ranking in probe test 3: chunks with overlapping tokens score above non-overlapping chunk (observed scores `[-0.0, -0.47, -1.45]` across 3-chunk fixture with query tokens `[101, 202]`).

## User Setup Required

None — no external service configuration required for Plan 01. `DART_API_KEY` is optional (Plan 04 will surface it again when the real DART collector is wired).

## Next Phase Readiness

- **Plan 02 (collectors/dart walking skeleton)** unblocked: schema in place, dart-fss installed, probe-findings.md has DART API access pattern documented (even though probe SKIPPED — key set locally will run it).
- **Plan 04 (ingest worker)** unblocked: `chunks.section_path/section_index/bm25_tokens` ready; `documents.corp_code` ready for worker INSERT.
- **Plan 05 (hybrid_search)** unblocked: both HNSW and BM25 indexes present; canonical SQL template validated end-to-end.

---
*Phase: 03-one-company-walking-skeleton*
*Completed: 2026-04-17*

## Self-Check: PASSED

- `src/db/migrations/versions/0002_phase03_chunking_columns.py`: FOUND
- `tests/test_migration_0002.py`: FOUND
- `tests/test_api_probes.py`: FOUND
- `.planning/phases/03-one-company-walking-skeleton/probe-findings.md`: FOUND
- Commit `35682b2`: FOUND in git log
- Commit `7f0e769`: FOUND in git log
- Live DB verified: 3 chunks columns + 1 documents column + 3 indexes present via `information_schema` / `pg_indexes`
