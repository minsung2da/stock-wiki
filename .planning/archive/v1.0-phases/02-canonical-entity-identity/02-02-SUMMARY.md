---
phase: 02-canonical-entity-identity
plan: 02
subsystem: db
tags: [alembic, schema, migration, pgvector, documents, dedup, upsert]

requires:
  - phase: 02-canonical-entity-identity
    provides: Alembic scaffold (src/db/alembic.ini, src/db/migrations/env.py), pg_engine/pg_clean fixtures, tensorchord/vchord-suite pg17 container
provides:
  - Alembic revision 0001 creating 7 Phase 2 tables (entities, entity_aliases, documents, chunks, edges, events, ingest_runs)
  - pgvector vector(1024) column on chunks.embedding (HNSW deferred to Phase 3 / STORE-03)
  - D-15 documents upsert semantics proven (accumulating source_urls, no duplication)
  - Live docker-compose Postgres migrated to revision 0001
affects: [02-03-resolve-entity, phase-03-collectors, phase-04-ingest]

tech-stack:
  added: []
  patterns:
    - "Single hand-written Alembic revision per phase (revision='0001', down_revision=None)"
    - "CHECK constraints pin enum-like columns (market, kind, edge_type) at schema boundary"
    - "Pitfall 5: NO UniqueConstraint on entity_aliases(kind, value) — ticker recycling preserved"
    - "op.execute('CREATE EXTENSION IF NOT EXISTS vector') keeps migration self-contained across fresh DBs"
    - "Raw ALTER TABLE for pgvector type (SQLAlchemy dialect has no native vector type mapper in this pin)"
    - "D-15 UPSERT: ON CONFLICT (id) DO UPDATE with CASE-guarded array_append for idempotent URL accumulation"

key-files:
  created:
    - src/db/migrations/versions/0001_phase02_initial_schema.py
    - tests/test_migration.py
    - tests/test_documents_dedup.py
  modified: []

key-decisions:
  - "Downgrade does NOT drop the vector extension — shared infrastructure, other schemas may depend on it"
  - "chunks.embedding added via raw ALTER TABLE (op.execute) — avoids optional pgvector-sqlalchemy type registration at migration time"
  - "D-15 UPSERT CASE statement chosen over array_cat + DISTINCT — preserves insertion order, cheaper on small arrays"

requirements-completed: [STORE-01, STORE-02, ENT-01]

metrics:
  duration: "6 min"
  completed: 2026-04-17
  tasks: 2
  files_created: 3
  files_modified: 0
  tests_added: 17
---

# Phase 02 Plan 02: Phase 2 Schema Migration Summary

**Single Alembic revision `0001` creates all 7 Phase 2 tables with full column/index/constraint shape per D-01~D-16; 17 new tests prove schema shape + D-15 dedup; live docker-compose Postgres migrated to `alembic_version=0001` with all 7 tables verified via psql.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-04-17T10:47:57Z
- **Completed:** 2026-04-17T10:53:53Z
- **Tasks:** 2
- **Tests added:** 17 (12 migration schema + 5 documents dedup)
- **Tests passing in Phase 2 suite:** 37/37 (migration 12 + dedup 5 + content_hash 8 + frontmatter 10 + pg_fixture 2)

## Accomplishments

- Authored single hand-written Alembic revision `0001_phase02_initial_schema.py` (206 LOC, 7 `op.create_table` calls + CHECK/UNIQUE/FK/index wiring + pgvector load)
- Locked all D-01~D-16 decisions in schema: `corp_code CHAR(8) PK`, `current_ticker CHAR(6)`, `kind` CHECK ('name','ticker','eng_name'), `edge_type` CHECK ('supersedes'), `(src,dst,edge_type)` UNIQUE, `documents.id CHAR(64)` sha256 PK, `source_urls TEXT[]`, `chunks.embedding vector(1024)`
- Pitfall 5 defense: 12th schema test explicitly asserts NO `UNIQUE(kind, value)` on `entity_aliases` (ticker recycling must survive delisting → new listing)
- D-15 UPSERT correctness proven: same URL → no duplicate; new URL → append; both paths update `last_seen_at`; `vault_path` UNIQUE rejects path-collision from different content hashes
- **Live docker-compose Postgres migrated:** `alembic upgrade head` produced `alembic_version=0001`; 7 Phase 2 tables + alembic_version table present; pgvector extension installed

## Task Commits

1. **Task 1 RED: migration schema tests** — `33d365e` (test)
2. **Task 2 GREEN: migration 0001** — `5eec664` (feat)
3. **Task 2 D-15 dedup tests** — `d83d82e` (test)

## Live DB Verification (Evidence)

```
$ docker compose up -d postgres
Network stock_default Created; Volume stock_pgdata Created; Container stock-postgres Started

$ until docker compose exec -T postgres pg_isready -U stockwiki; do sleep 1; done
pg ready

$ DATABASE_URL="postgresql+psycopg://stockwiki:***@127.0.0.1:5432/stockwiki" \
    uv run --group db alembic -c src/db/alembic.ini upgrade head
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, Phase 2 initial schema — entities, entity_aliases, documents, chunks, edges, events, ingest_runs.

$ docker compose exec -T postgres psql -U stockwiki -d stockwiki -tA -c \
    "SELECT version_num FROM alembic_version"
0001

$ docker compose exec -T postgres psql -U stockwiki -d stockwiki -tA -c \
    "SELECT string_agg(table_name, ',' ORDER BY table_name) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('entities','entity_aliases','documents','chunks','edges','events','ingest_runs','alembic_version')"
alembic_version,chunks,documents,edges,entities,entity_aliases,events,ingest_runs

$ docker compose exec -T postgres psql -U stockwiki -d stockwiki -tA -c \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('entities','entity_aliases','documents','chunks','edges','events','ingest_runs')"
7

$ docker compose exec -T postgres psql -U stockwiki -d stockwiki -tA -c \
    "SELECT extname FROM pg_extension WHERE extname='vector'"
vector
```

## Full Test Run

```
$ uv run --group db --group dev pytest tests/test_migration.py tests/test_documents_dedup.py \
    tests/test_content_hash.py tests/test_frontmatter.py tests/test_pg_fixture.py
======================= 37 passed, 4 warnings in 14.85s =======================
```

## Tables / Constraints / Indexes Created

| Table           | PK               | Notable columns / constraints                                        | Indexes                                  |
| --------------- | ---------------- | -------------------------------------------------------------------- | ---------------------------------------- |
| entities        | corp_code CHAR(8)| canonical_name, current_ticker CHAR(6), ck_entities_market           | (PK only)                                |
| entity_aliases  | id BIGSERIAL     | FK corp_code CASCADE, kind CHECK, valid_from/to, ck_alias_validity   | ix_alias_lookup(kind, value, valid_from, valid_to) |
| documents       | id CHAR(64)      | body, source, vault_path, source_urls TEXT[], first/last_seen_at     | ix_documents_source, ix_documents_vault_path UNIQUE |
| chunks          | id BIGSERIAL     | FK document_id CASCADE, ord, text, embedding vector(1024)            | ix_chunks_document_id                    |
| edges           | id BIGSERIAL     | src/dst type+id, edge_type CHECK=supersedes, uq_edge_endpoints        | ix_edges_src, ix_edges_dst, ix_edges_type |
| events          | id BIGSERIAL     | corp_code FK SET NULL, document_id FK SET NULL, payload JSONB         | ix_events_corp_code_time                 |
| ingest_runs     | id BIGSERIAL     | started_at NOT NULL, stats JSONB                                     | (PK only)                                |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Missing `.env` for live DB push**
- **Found during:** Task 2 step 4a (bring up docker-compose Postgres)
- **Issue:** Repository has `.env.example` but no local `.env`. docker-compose requires `POSTGRES_PASSWORD` from env; the live DB push step cannot proceed without it.
- **Fix:** Generated a random 24-byte URL-safe password via `python3 -c "import secrets; print(secrets.token_urlsafe(24))"`, wrote `.env` with `POSTGRES_PASSWORD=<pw>` and matching `DATABASE_URL`, `chmod 600`. `.env` is covered by `.gitignore` (verified) and never committed.
- **Files modified:** `.env` (new, gitignored)
- **Verification:** `ls .env` → present; `grep '^\.env$' .gitignore` → match; password only exists on local filesystem, never echoed or committed.

**2. [Lint - Ruff SIM117/B017] Adjusted vault_path unique test exception-handling**
- **Found during:** Task 2 pre-commit hook for `tests/test_documents_dedup.py`
- **Issue:** Ruff flagged `pytest.raises(Exception)` (B017, blind exception) and nested `with` statements (SIM117).
- **Fix:** Imported `sqlalchemy.exc.IntegrityError` explicitly, replaced `Exception` with `IntegrityError`, collapsed nested `with` into a single `with pytest.raises(...), pg_clean.begin() as conn:` context.
- **Files modified:** `tests/test_documents_dedup.py`
- **Verification:** `pytest tests/test_documents_dedup.py -x -v` — 5/5 passing; pre-commit `ruff` now passes.
- **Committed in:** `d83d82e` (same Task 2 dedup commit, fixed before push)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 lint)
**Impact on plan:** None — both are within scope of "make the live DB push and commits succeed". No scope creep.

## Issues Encountered

- Pre-commit `ruff-format` reformatted `tests/test_migration.py` on first commit attempt; standard re-stage → commit pattern succeeded on retry.

## User Setup Required

- **`.env` was generated locally with a random POSTGRES_PASSWORD.** Users who already have a `.env` with a different password would use their existing value. The `.env` file remains gitignored and on-disk only.
- Docker daemon must be running for the live DB push step (already a Phase 1 assumption).

## Deferred Issues

None — all acceptance criteria met; verification evidence captured above.

## Self-Check: PASSED

Verified on disk and in git:

- `[ -f src/db/migrations/versions/0001_phase02_initial_schema.py ]` — present
- `grep -c 'op.create_table' src/db/migrations/versions/0001_phase02_initial_schema.py` → **7**
- `grep 'CREATE EXTENSION IF NOT EXISTS vector' src/db/migrations/versions/0001_phase02_initial_schema.py` → match
- `grep 'vector(1024)' src/db/migrations/versions/0001_phase02_initial_schema.py` → match
- `grep 'ck_alias_kind' src/db/migrations/versions/0001_phase02_initial_schema.py` → match
- `grep 'uq_edge_endpoints' src/db/migrations/versions/0001_phase02_initial_schema.py` → match
- `grep 'ck_edge_type_phase2' src/db/migrations/versions/0001_phase02_initial_schema.py` → match
- `grep -E 'UniqueConstraint\(["'"'"']kind["'"'"'],\s*["'"'"']value["'"'"']' src/db/migrations/versions/0001_phase02_initial_schema.py` → **NO match** (Pitfall 5 verified)
- `[ -f tests/test_migration.py ]` — present; `grep -c '^def test_' tests/test_migration.py` → **12**
- `[ -f tests/test_documents_dedup.py ]` — present; `grep -c '^def test_' tests/test_documents_dedup.py` → **5**
- Commits `33d365e`, `5eec664`, `d83d82e` present in `git log`
- Full verification: `uv run --group db --group dev pytest tests/test_migration.py tests/test_documents_dedup.py tests/test_content_hash.py tests/test_frontmatter.py tests/test_pg_fixture.py` → **37 passed**
- Live DB: `SELECT version_num FROM alembic_version` on docker-compose postgres → `0001`; 7 Phase 2 tables present

## Next Phase Readiness

- **Plan 02-03** can now author `src/shared/entity.py` with `resolve_entity(value, as_of)` per D-09~D-12, using live schema.
- **Phase 3 collectors** can insert into `documents` via the D-15 UPSERT pattern documented here.
- **Phase 3 ingest** can INSERT `chunks` rows with `embedding` populated by sentence-transformers bge-m3.

---
*Phase: 02-canonical-entity-identity*
*Completed: 2026-04-17*
