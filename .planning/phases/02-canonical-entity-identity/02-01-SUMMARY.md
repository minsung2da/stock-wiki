---
phase: 02-canonical-entity-identity
plan: 01
subsystem: infra
tags: [alembic, sqlalchemy, psycopg3, pgvector, testcontainers, content-hash, sha256]

requires:
  - phase: 01-foundation
    provides: docker-compose Postgres + vchord image, pyproject.toml dependency groups, tests/conftest.py tmp_vault fixture
provides:
  - db dependency group with alembic + sqlalchemy + psycopg[binary] + pgvector
  - testcontainers[postgres] in dev group
  - DATABASE_URL example using postgresql+psycopg:// (psycopg3) scheme
  - Alembic scaffold under src/db/ (alembic.ini, migrations/env.py, script template, empty versions dir)
  - src/db/engine.py exporting get_engine() with fail-fast env var read
  - src/shared/content_hash.py (D-13/D-14 canonical hash) with 8 passing determinism tests
  - tests/conftest.py pg_engine (session) and pg_clean (function) fixtures
affects: [02-02-schema-migration, 02-03-resolve-entity, phase-03-collectors, phase-04-ingest]

tech-stack:
  added: [alembic>=1.18, sqlalchemy>=2.0, psycopg[binary]>=3.2, pgvector>=0.4, testcontainers[postgres]>=4.8]
  patterns:
    - "Alembic: hand-written migrations only, target_metadata=None, DATABASE_URL via env (fail-fast KeyError)"
    - "Content-hash: frontmatter-stripped + CRLF->LF + rstrip + single trailing newline (D-13/D-14)"
    - "Testcontainers: session-scoped Postgres container reuses docker-compose image for extension parity"
    - "URL normalization: postgresql+psycopg2:// or postgresql:// -> postgresql+psycopg:// for psycopg3"

key-files:
  created:
    - src/db/alembic.ini
    - src/db/engine.py
    - src/db/migrations/env.py
    - src/db/migrations/script.py.mako
    - src/db/migrations/versions/.keep
    - src/shared/content_hash.py
    - tests/test_content_hash.py
    - tests/test_pg_fixture.py
  modified:
    - pyproject.toml
    - .env.example
    - tests/conftest.py

key-decisions:
  - "psycopg3 driver over psycopg2 — postgresql+psycopg:// scheme throughout; testcontainers URL normalized at fixture boundary"
  - "Alembic target_metadata=None — hand-written migrations only; no autogenerate drift risk"
  - "Content-hash = sha256 of frontmatter-stripped normalized body — dedup primitive, NOT security"
  - "Truncate-list constant _PHASE2_TABLES in conftest — avoids schema coupling while supporting future plans"

patterns-established:
  - "Migration env reads DATABASE_URL via os.environ[...] (raises KeyError if unset) — no silent defaults"
  - "Session-scoped pg fixture mirrors prod image (tensorchord/vchord-suite:pg17-latest) for extension parity"
  - "Per-test pg_clean guards TRUNCATE with information_schema.tables existence check"

requirements-completed: [STORE-02]

duration: 6 min
completed: 2026-04-17
---

# Phase 02 Plan 01: Alembic + content_hash + testcontainers fixtures Summary

**Wave-0 infrastructure locked: psycopg3 + Alembic scaffold, D-13/D-14 canonical content-hash utility, and testcontainers pg_engine/pg_clean fixtures — Wave 2 (migration) and Wave 3 (resolve_entity) can start with zero additional bootstrap.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-17T10:39:20Z
- **Completed:** 2026-04-17T10:45:35Z
- **Tasks:** 3
- **Files created:** 8
- **Files modified:** 3
- **Tests:** 20 passing (10 existing frontmatter + 8 new content-hash + 2 new pg-fixture)

## Accomplishments

- Added `db` dependency group (alembic 1.18.4, sqlalchemy 2.0.49, psycopg 3.3.3, pgvector 0.4.2) and extended `dev` with testcontainers 4.14.2
- Migrated `.env.example` DATABASE_URL from bare `postgresql://` to `postgresql+psycopg://` (psycopg3) with `${POSTGRES_PASSWORD}` expansion
- Scaffolded Alembic at `src/db/` with hand-written-only migrations policy (target_metadata=None, DATABASE_URL via env.KeyError fail-fast)
- Shipped `src/shared/content_hash.py` with 8 TDD-driven tests proving D-13 (frontmatter independence) and D-14 (CRLF/whitespace/newline normalization) determinism
- Added session-scoped `pg_engine` and function-scoped `pg_clean` fixtures that spin up the same `tensorchord/vchord-suite:pg17-latest` image as docker-compose and run `alembic upgrade head` once per session

## Task Commits

1. **Task 1: db group + DATABASE_URL + Alembic scaffold** — `c4374b9` (feat)
2. **Task 2 RED: failing content-hash tests** — `4718f84` (test)
3. **Task 2 GREEN: content-hash implementation** — `5672e95` (feat)
4. **Task 3: testcontainers pg_engine/pg_clean fixtures** — `4b72a76` (test)

**Plan metadata:** (to be committed next)

## Files Created/Modified

- `pyproject.toml` — added `db` group, added testcontainers to `dev`
- `.env.example` — DATABASE_URL updated to psycopg3 scheme with env expansion
- `src/db/alembic.ini` — Alembic config, script_location `%(here)s/migrations`
- `src/db/engine.py` — `get_engine()` reading DATABASE_URL (fail-fast KeyError)
- `src/db/migrations/env.py` — online runner, target_metadata=None, NullPool
- `src/db/migrations/script.py.mako` — standard Alembic revision template
- `src/db/migrations/versions/.keep` — empty placeholder for git tracking
- `src/shared/content_hash.py` — `normalize_body` + `compute_content_hash`, 33 LOC
- `tests/test_content_hash.py` — 8 determinism tests (D-13/D-14)
- `tests/test_pg_fixture.py` — 2 smoke tests (SELECT 1 via engine and pg_clean)
- `tests/conftest.py` — added `pg_engine`, `pg_clean` fixtures and `_PHASE2_TABLES` constant

## Decisions Made

- **psycopg3 driver (not psycopg2).** Uses `postgresql+psycopg://` scheme throughout; `.env.example`, Alembic env, and the testcontainers fixture all normalize to this.
- **Alembic `target_metadata = None`.** Hand-written migrations only per RESEARCH Pattern 1 — eliminates autogenerate drift risk on a schema we want to keep simple and auditable.
- **Content-hash is a dedup primitive, not a security primitive.** sha256 collision resistance is assumed for the dedup use case only; documented in the module docstring.
- **Truncate-list constant (`_PHASE2_TABLES`).** Listed all Phase 2 tables in conftest ahead of migration (Plan 02) — existence-guarded TRUNCATE means this plan's tests pass today, and Plan 02/03 tests get a clean DB per test with zero conftest churn.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Testcontainers URL scheme normalization**
- **Found during:** Task 3 (pg_engine smoke test)
- **Issue:** `testcontainers 4.14.2` emits `postgresql+psycopg2://...` URLs by default, not `postgresql://...`. The plan-specified replacement `raw_url.replace("postgresql://", "postgresql+psycopg://", 1)` did not match, so Alembic fell back to psycopg2 dialect and failed with `ModuleNotFoundError: No module named 'psycopg2'`.
- **Fix:** Added branch handling for both `postgresql+psycopg2://` and bare `postgresql://` prefixes; normalize both to `postgresql+psycopg://` so the psycopg3 dbapi is resolved.
- **Files modified:** `tests/conftest.py`
- **Verification:** `pytest tests/test_pg_fixture.py -x -v` — both tests pass.
- **Committed in:** `4b72a76` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary for fixture functionality. No scope creep — matches the plan's intent of forcing psycopg3 at the fixture boundary.

## Issues Encountered

None. Ruff-format auto-reformatted two files during pre-commit; commits re-staged and succeeded on retry without manual intervention.

## User Setup Required

None — no external service configuration required. Docker daemon must be running for `tests/test_pg_fixture.py` (already a repo assumption from Phase 1).

## Next Phase Readiness

- **Plan 02-02** can now author the single Phase-2 Alembic migration (`entities`, `entity_aliases`, `documents`, `chunks`, `edges`, `events`, `ingest_runs`) against the scaffold. Tests will pick up the migration automatically via `pg_engine`'s `alembic upgrade head`; `pg_clean` will TRUNCATE the new tables as they appear in `information_schema`.
- **Plan 02-03** can import `compute_content_hash` from `src.shared.content_hash` to populate `documents.content_hash`.
- **Phase 3+ collectors** can also import the same canonical hash utility — single source of truth established.

## Self-Check: PASSED

Verified on disk and in git:

- `[ -f src/db/alembic.ini ]` — present
- `[ -f src/db/engine.py ]` — present (`def get_engine()`)
- `[ -f src/db/migrations/env.py ]` — present (`target_metadata = None`, `os.environ["DATABASE_URL"]`)
- `[ -f src/db/migrations/script.py.mako ]` — present (`${upgrade}` template)
- `[ -f src/db/migrations/versions/.keep ]` — present
- `[ -f src/shared/content_hash.py ]` — present (exports `normalize_body`, `compute_content_hash`)
- `[ -f tests/test_content_hash.py ]` — present (8 tests)
- `[ -f tests/test_pg_fixture.py ]` — present (2 tests)
- `grep 'alembic>=1.18' pyproject.toml` — match
- `grep 'testcontainers\[postgres\]' pyproject.toml` — match
- `grep '^DATABASE_URL=postgresql+psycopg://' .env.example` — match
- Commits `c4374b9`, `4718f84`, `5672e95`, `4b72a76` all present in `git log`
- Full verification: `uv run --group db --group dev pytest tests/test_pg_fixture.py tests/test_frontmatter.py tests/test_content_hash.py -x` → **20 passed**

---
*Phase: 02-canonical-entity-identity*
*Completed: 2026-04-17*
