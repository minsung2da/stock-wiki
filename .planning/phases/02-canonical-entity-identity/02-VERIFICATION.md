---
phase: 02-canonical-entity-identity
verified: 2026-04-17T12:00:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Run full Phase 2 test suite against a live testcontainers instance"
    expected: "~47+ tests pass (10 frontmatter + 8 content_hash + 2 pg_fixture + 12 migration + 5 dedup + 9 entity_resolve + 3 supersedes)"
    why_human: "Docker daemon must be running; testcontainers spins up a real Postgres container — cannot execute in this verification session"
  - test: "Verify live docker-compose Postgres has alembic_version=0001 and all 7 tables"
    expected: "SELECT version_num FROM alembic_version returns 0001; 7 Phase 2 tables present"
    why_human: "Requires running Docker daemon and docker compose exec — external service"
---

# Phase 2: Canonical Entity Identity Verification Report

**Phase Goal:** The stable key for every entity is DART `corp_code` — not the reusable 6-digit KRX ticker. Schema, alias history, and supersession edges for 기재정정 chains are settled before any document is written so later re-ingest is avoided.
**Verified:** 2026-04-17T12:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Alembic migration creates 7 tables (documents, chunks, entities, edges, events, ingest_runs, entity_aliases) with indexes and runs cleanly on a fresh Postgres volume | VERIFIED | `0001_phase02_initial_schema.py` (206 LOC, 7 `op.create_table` calls); live DB migration evidence in 02-02-SUMMARY.md; commits `5eec664`, `33d365e` |
| 2 | `documents.id` is computed as `sha256(body)` and uniqueness is enforced so content-addressed dedup works across re-fetches | VERIFIED | `src/shared/content_hash.py` exports `compute_content_hash` using `hashlib.sha256`; 8 determinism tests pass; `documents.id CHAR(64) PK` in migration; D-15 UPSERT dedup tests (5 passing) |
| 3 | `entities` schema stores `corp_code` as the canonical ID, with KRX ticker, aliases, and valid-from/valid-to ranges; rename/split/ticker-recycling fixtures resolve to correct entity | VERIFIED | `entities.corp_code CHAR(8) PK`; `entity_aliases(kind, value, valid_from, valid_to)`; 4 YAML fixtures (rename, split, ticker_recycle synthetic, amendment); 9 `test_entity_resolve.py` tests cover all fixture cases |
| 4 | A `supersedes` edge type exists and a 기재정정 test fixture produces an edge linking amendment → original | VERIFIED | `edges.edge_type CHECK IN ('supersedes')`; `amendment_case.yaml` fixture with edges.src_id → dst_id; `test_amendment_returns_latest_doc` passes via recursive CTE |
| 5 | `resolve_entity(ticker_or_corp_code, as_of=...)` returns the right row for historical queries | VERIFIED | `src/db/entity.py` (94 LOC) with D-12 digit-length auto-branch; D-10/D-11 half-open temporal interval; zero f-string SQL; 9 tests cover corp_code direct, current ticker, historical ticker, split boundary, ticker recycling, gap-returns-None, mismatch-returns-None |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/shared/content_hash.py` | compute_content_hash + normalize_body per D-13/D-14, min 20 lines | VERIFIED | 33 LOC; exports both functions; CRLF normalization present; hashlib.sha256 used |
| `src/db/alembic.ini` | Alembic config pointing at src/db/migrations | VERIFIED | `script_location = %(here)s/migrations` confirmed |
| `src/db/migrations/env.py` | Online migration runner reading DATABASE_URL from env; target_metadata=None | VERIFIED | `target_metadata = None`; `os.environ["DATABASE_URL"]` (fail-fast KeyError); `run_migrations_online()` present |
| `src/db/engine.py` | SQLAlchemy 2.0 Engine factory reading DATABASE_URL | VERIFIED | `def get_engine()` reads `os.environ["DATABASE_URL"]`; `future=True` flag |
| `src/db/migrations/versions/0001_phase02_initial_schema.py` | Single revision creating 7 tables + constraints, min 80 lines | VERIFIED | 206 LOC; 7 `op.create_table`; CREATE EXTENSION vector; vector(1024); ck_alias_kind; uq_edge_endpoints; ck_edge_type_phase2; NO UniqueConstraint(kind, value) |
| `tests/test_content_hash.py` | D-13/D-14 determinism tests, min 8 tests | VERIFIED | 8 tests |
| `tests/conftest.py` | pg_engine (session) + pg_clean (function) fixtures | VERIFIED | Both fixtures present; tensorchord/vchord-suite:pg17-latest; postgresql+psycopg:// URL normalization |
| `tests/test_migration.py` | upgrade/downgrade/idempotent/schema assertions | VERIFIED | 12 tests; no_kind_value_unique guard; downgrade_then_upgrade_idempotent present |
| `tests/test_documents_dedup.py` | D-15 UPSERT behavior tests | VERIFIED | 5 tests covering first insert, duplicate URL no-op, new URL accumulation, last_seen_at update, vault_path unique constraint |
| `src/db/entity.py` | resolve_entity(engine, value, as_of=None) -> Entity \| None, min 40 lines | VERIFIED | 94 LOC; `def resolve_entity`; `_is_digits` D-12 auto-branch; valid_to IS NULL (2 occurrences); valid_from <= :asof |
| `fixtures/entities/rename_case.yaml` | Samsung-style rename fixture | VERIFIED | corp_code 00126380; valid_to: null on current aliases |
| `fixtures/entities/split_case.yaml` | Split case fixture | VERIFIED | corp_code 00126381; ticker 099001 stable across split date |
| `fixtures/entities/ticker_recycle.yaml` | Synthetic ticker recycling fixture | VERIFIED | corp_codes 99999991 and 99999992 both present; ticker 099999 with non-overlapping valid ranges |
| `fixtures/entities/amendment_case.yaml` | DART 기재정정 fixture with supersedes edge | VERIFIED | entities + documents + edges sections present |
| `tests/fixtures_loader.py` | Parameterized INSERT helper | VERIFIED | `def load_entity_fixture`; uses `sa.text(...)` for all 4 INSERT branches |
| `tests/test_entity_resolve.py` | resolve_entity integration tests, min 8 tests | VERIFIED | 9 tests |
| `tests/test_supersedes_edge.py` | Recursive CTE tests, min 3 tests | VERIFIED | 3 tests; WITH RECURSIVE present |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/db/migrations/env.py` | `os.environ['DATABASE_URL']` | engine_from_config + sqlalchemy.url override | VERIFIED | `os.environ["DATABASE_URL"]` present; KeyError if unset |
| `src/shared/content_hash.py` | python-frontmatter (fm.load) | strip frontmatter before sha256 | VERIFIED | `fm.load(path)` then `post.content` then sha256 |
| `tests/conftest.py` | testcontainers.postgres.PostgresContainer | session-scoped fixture with alembic upgrade head | VERIFIED | Both import and usage present; URL normalization handles psycopg2→psycopg3 |
| `src/db/migrations/versions/0001_phase02_initial_schema.py` | pgvector extension | `op.execute('CREATE EXTENSION IF NOT EXISTS vector')` | VERIFIED | Present in migration upgrade() |
| `src/db/migrations/versions/0001_phase02_initial_schema.py` | entity_aliases.corp_code | FOREIGN KEY REFERENCES entities(corp_code) ON DELETE CASCADE | VERIFIED | ForeignKey wiring confirmed in migration |
| `src/db/entity.py` | entity_aliases table | SQLAlchemy text() with bind params for temporal query | VERIFIED | `text(...)` + `:v`, `:asof` bind parameters; zero f-string SQL |
| `tests/test_supersedes_edge.py` | edges table | WITH RECURSIVE chain CTE | VERIFIED | Recursive CTE with depth < 20 cycle guard present |

### Data-Flow Trace (Level 4)

Not applicable — no frontend components or dynamic rendering artifacts. All artifacts are Python modules, SQL migrations, and test fixtures with well-traced data flows through parameterized SQL.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| alembic deps importable | `uv run --group db python -c "import alembic, sqlalchemy, psycopg, pgvector; print('ok')"` | Confirmed in 02-01-SUMMARY.md | SKIP (requires Docker) |
| content_hash is deterministic | 8 TDD tests in test_content_hash.py cover D-13/D-14 | Commits `4718f84` (RED), `5672e95` (GREEN) confirm TDD cycle | PASS (evidence-based) |
| resolve_entity f-string SQL absent | `grep -E 'f"""\|f"SELECT\|f'"'"'SELECT' src/db/entity.py` | No output (zero f-string SQL) | PASS |
| Pitfall 5 guard: no UNIQUE(kind,value) | UniqueConstraint on entity_aliases checked | Only comment line found; actual UniqueConstraint is on edges (uq_edge_endpoints) | PASS |
| All 9 commit hashes present | `git log --oneline` | All 9 documented hashes confirmed (c4374b9..105990e) | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ENT-01 | 02-02, 02-03 | corp_code (DART 8자리) as canonical entity ID | SATISFIED | `entities.corp_code CHAR(8) PK`; `resolve_entity` D-12 digit-length auto-branch; marked [x] in REQUIREMENTS.md |
| ENT-02 | 02-03 | Temporal alias tracking for rename/split/ticker recycling | SATISFIED | `entity_aliases(valid_from, valid_to)`; 4 fixtures; 9 tests covering all cases; marked [x] in REQUIREMENTS.md |
| ENT-03 | 02-03 | DART 기재정정 supersedes chain stored as edges | SATISFIED | `edges.edge_type CHECK IN ('supersedes')`; amendment_case.yaml fixture; recursive CTE test; marked [x] in REQUIREMENTS.md |
| STORE-01 | 02-02 | Alembic migration creates tables with indexes | SATISFIED | 7 tables created; all indexes confirmed (ix_alias_lookup, ix_documents_vault_path, ix_chunks_document_id, ix_edges_src/dst/type, ix_events_corp_code_time); marked [x] in REQUIREMENTS.md |
| STORE-02 | 02-01, 02-02 | documents.id = sha256(body) content-addressed | SATISFIED | `compute_content_hash` returns sha256; `documents.id CHAR(64) PK`; 8 determinism tests; 5 D-15 dedup tests; marked [x] in REQUIREMENTS.md |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/db/migrations/script.py.mako` | 20 | Template uses `${upgrades if upgrades else "pass"}` (not `${upgrade}` as plan specified) | Info | No functional impact — `upgrades` is the correct Alembic Mako variable; `upgrade` would be wrong. Plan acceptance criteria used incorrect variable name. Future `alembic revision` commands will generate valid files. |

No blockers, no warnings.

### Human Verification Required

#### 1. Full Test Suite Execution

**Test:** Run `uv run --group db --group dev pytest tests/ --ignore=tests/test_secrets.py -v`
**Expected:** ~53 tests pass (all Phase 2 test files). Summary from 02-03-SUMMARY.md shows 53 passed when run on 2026-04-17.
**Why human:** Requires Docker daemon running to spin up testcontainers PostgreSQL container (tensorchord/vchord-suite:pg17-latest). Cannot execute without running container infrastructure.

#### 2. Live Docker-Compose DB Verification

**Test:** `docker compose exec -T postgres psql -U stockwiki -d stockwiki -tA -c "SELECT version_num FROM alembic_version"` and table count query
**Expected:** `version_num = 0001`; 7 Phase 2 tables present
**Why human:** Requires Docker daemon and docker-compose running locally. Evidence in 02-02-SUMMARY.md shows this was verified during plan execution (output captured verbatim).

### Gaps Summary

No gaps found. All 5 must-haves are verified against the actual codebase. All 17 artifacts exist and are substantive. All key links are wired. The one anti-pattern (script.py.mako template variable name) is informational only with no functional impact.

Human verification is required only because the full test suite needs Docker/testcontainers infrastructure that cannot be executed in this verification session. The static analysis of all artifacts, wiring, constraints, and commit history provides high confidence in phase goal achievement.

---

_Verified: 2026-04-17T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
