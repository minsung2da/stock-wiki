---
phase: 2
slug: canonical-entity-identity
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-17
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + testcontainers[postgres] |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/ -x -q -m "not db"` |
| **Full suite command** | `uv run pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~30-60 seconds (DB container startup dominates) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q -m "not db"` (skip DB-bound tests for speed)
- **After every plan wave:** Run full suite with DB tests
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds (DB container startup included)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | — | — | N/A | unit | `uv run alembic check` (after bootstrap) | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | — | — | N/A | unit | `uv run pytest tests/test_content_hash.py` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 2 | STORE-01 | — | N/A | integration | `uv run pytest tests/test_migration.py` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 2 | STORE-02 | — | content-hash dedup | integration | `uv run pytest tests/test_documents_dedup.py` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 3 | ENT-01, ENT-02 | — | ticker-recycling resolves correct corp_code | integration | `uv run pytest tests/test_entity_resolve.py` | ❌ W0 | ⬜ pending |
| 02-03-02 | 03 | 3 | ENT-03 | — | supersedes chain traversal | integration | `uv run pytest tests/test_supersedes_edge.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `uv add --group db alembic>=1.18` (Alembic not in current deps)
- [ ] `uv add --group dev testcontainers[postgres]>=4.9` (DB fixture)
- [ ] `src/db/alembic.ini` — Alembic config
- [ ] `src/db/alembic/env.py` — Alembic env (uses DATABASE_URL from .env)
- [ ] `src/db/alembic/versions/` — migrations directory
- [ ] `src/shared/content_hash.py` — canonical content-hash utility (reused by Phase 3 collectors)
- [ ] `tests/test_content_hash.py` — unit tests for content-hash normalization
- [ ] `tests/test_migration.py` — integration: fresh DB → alembic upgrade head → verify tables/indexes
- [ ] `tests/test_documents_dedup.py` — integration: content-hash upsert behavior
- [ ] `tests/test_entity_resolve.py` — integration: rename, split, ticker-recycling fixtures
- [ ] `tests/test_supersedes_edge.py` — integration: 기재정정 edge creation + recursive CTE chain traversal
- [ ] `tests/conftest.py` — add `db` fixture (testcontainers-based)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Fresh volume migration | STORE-01 | Requires Docker volume reset | `docker compose down -v && docker compose up -d && uv run alembic upgrade head` → verify no errors |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
