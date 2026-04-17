---
phase: 3
slug: one-company-walking-skeleton
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-17
updated: 2026-04-17
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + testcontainers[postgres] |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/ -x -q -m "not db and not e2e"` |
| **Full suite command** | `uv run pytest tests/ -v --tb=short` |
| **E2E smoke command** | `uv run pytest tests/e2e/ -v` (opt-in, uses live docker-compose) |
| **Estimated runtime** | ~60-120 seconds (full incl. DB); ~10s for quick |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q -m "not db and not e2e"`
- **After every plan wave:** Run full suite incl. DB tests
- **Before `/gsd-verify-work`:** Full suite green + manual E2E smoke (Claude Code → MCP → citation)
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map (indicative)

> Task ID format: `{phase}-{plan}-{task}`; Wave column matches the plan's `wave` frontmatter value.

| Task ID | Wave | Plan | Requirement | Threat Ref | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 1 | 03-01 | STORE-03, STORE-04, STORE-06, RET-02 (corp_code) | — | integration | `uv run alembic upgrade head && pytest tests/test_migration_0002.py` | ❌ W0 | ⬜ pending |
| 03-01-02 | 1 | 03-01 | INGEST-12 (probes) | — | integration | `uv run pytest tests/test_api_probes.py` (dart-fss + vchord_bm25) | ❌ W0 | ⬜ pending |
| 03-02-01 | 2 | 03-02 | COLL-01, COLL-06, COLL-08 | — | unit+integration | `uv run pytest tests/test_collect_dart.py` | ❌ W0 | ⬜ pending |
| 03-02-02 | 2 | 03-02 | COLL-09 | — | unit | `uv run pytest tests/test_heartbeat.py` | ❌ W0 | ⬜ pending |
| 03-03-01 | 2 | 03-03 | INGEST-08, INGEST-09 | T-3-01 | unit | `uv run pytest tests/test_injection_defense.py` | ❌ W0 | ⬜ pending |
| 03-03-02 | 2 | 03-03 | INGEST-11 | — | unit | `uv run pytest tests/test_bm25_tokenizer.py` | ❌ W0 | ⬜ pending |
| 03-03-03 | 2 | 03-03 | INGEST-10, INGEST-12 | — | unit+integration | `uv run pytest tests/test_embedder.py` | ❌ W0 | ⬜ pending |
| 03-03-04 | 2 | 03-03 | (chunking) | — | unit | `uv run pytest tests/test_parsers.py` | ❌ W0 | ⬜ pending |
| 03-04-01 | 3 | 03-04 | INGEST-01, STORE-03, STORE-04, STORE-06, RET-02 (corp_code writeback) | — | integration | `uv run pytest tests/test_ingest_worker.py` | ❌ W0 | ⬜ pending |
| 03-05-01 | 4 | 03-05 | RET-01, RET-02, JUDGE-04 | — | integration | `uv run pytest tests/test_hybrid_search.py` | ❌ W0 | ⬜ pending |
| 03-05-02 | 4 | 03-05 | RET-03, MCP-01, MCP-02 | T-3-02, T-3-21 | integration | `uv run pytest tests/test_mcp_server_boot.py tests/test_mcp_search_tool.py` | ❌ W0 | ⬜ pending |
| 03-06-01 | 5 | 03-06 | STORE-05, (CLI) | — | integration | `uv run stock --help && uv run pytest tests/test_cli.py tests/test_ingest_rebuild.py` | ❌ W0 | ⬜ pending |
| 03-06-02 | 5 | 03-06 | JUDGE-04 (schema) | — | e2e | `uv run pytest tests/e2e/test_search_citation_schema.py` | ❌ W0 | ⬜ pending |
| 03-06-03 | 5 | 03-06 | JUDGE-04 (human) | — | manual | Human query in Claude Code → vault citation verified | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Note: Wave numbers above reconcile with each plan's `wave:` frontmatter. 6 plans total (03-01 through 03-06). Plan 03-06 contains 3 tasks: CLI+rebuild (auto), E2E schema test (auto), and JUDGE-04 human checkpoint.*

---

## Wave 0 Requirements

- [ ] `uv add --group ingest sentence-transformers>=3.0 python-mecab-ko` (embedder + tokenizer)
- [ ] `uv add --group collectors dart-fss>=0.4 requests>=2.32 tenacity>=9.0` (DART + retry)
- [ ] `uv add --group mcp fastmcp>=2.14,<3.0` (MCP server, pinned <3.0 per D-20)
- [ ] `uv add --group ingest numpy>=2.0 pgvector>=0.4` (already present but confirm)
- [ ] `src/db/migrations/versions/0002_phase03_chunking_columns.py` — add `chunks.section_path`, `section_index`, `bm25_tokens` AND `documents.corp_code` + `ix_documents_corp_code`
- [ ] `src/shared/injection_defense.py` — wrap_untrusted + detect_injection_patterns + pattern table
- [ ] `src/shared/frontmatter.py` — extend IngestStateBlock with `injection_flags: list[str]` (Plan 03-04) and ProvenanceBlock with `trust_level` (Plan 03-02)
- [ ] `src/ingest/parsers/__init__.py`, `parsers/dart.py` — section parsers
- [ ] `src/ingest/embedder.py` — bge-m3 wrapper with model version constant
- [ ] `src/ingest/tokenizer.py` — mecab-ko + hash-to-int32 for BM25
- [ ] `src/ingest/worker.py` — orchestration; writes `documents.corp_code` from `fm.provenance.corp_code`
- [ ] `src/ingest/heartbeat.py` — atomic write
- [ ] `src/collectors/dart/__init__.py`, `client.py`, `fetcher.py`
- [ ] `src/stock_mcp/__main__.py`, `server.py`, `tools/search.py`, `errors.py`, `models.py`, `search_core.py` — hybrid SQL uses `d.corp_code = :corp_code` direct filter
- [ ] `src/cli/__init__.py`, `main.py` — `stock` entry (collect, ingest run, ingest rebuild)
- [ ] `.mcp.json` — Claude Code MCP registration
- [ ] `tests/conftest.py` — extend with `embedder_fixture`, `sample_dart_filing` fixtures
- [ ] 14+ test files (see Per-Task Verification Map)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Claude Code answers "삼성전자 최근 공시" with vault citation | JUDGE-04 | Requires Claude Code session interaction | 1. `uv run stock collect dart --corp-code=00126380 --since=2025-04-17 --max-docs=100`<br>2. `uv run stock ingest run`<br>3. Ensure `.mcp.json` registered (restart Claude Code if needed)<br>4. Query: "삼성전자 최근 공시 알려줘"<br>5. Verify response contains `see: vault/raw/dart/YYYY-MM-DD/...md` path |
| DART API rate limit handling | COLL-08 | Requires real API key + sufficient volume | Run collector on full 삼성전자 since=2024-01-01 and confirm no 429 errors; backoff behavior observed |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 120s
- [x] `nyquist_compliant: true` set in frontmatter
- [x] Per-Task Verification Map wave numbers reconciled with plan frontmatter wave assignments (2026-04-17 revision)

**Approval:** pending
