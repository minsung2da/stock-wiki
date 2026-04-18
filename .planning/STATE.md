---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: verifying
stopped_at: Phase 4 context gathered
last_updated: "2026-04-18T00:33:17.223Z"
last_activity: 2026-04-17
progress:
  total_phases: 9
  completed_phases: 3
  total_plans: 12
  completed_plans: 12
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-17)

**Core value:** Claude Code에서 보유·관심 종목을 질의했을 때, 최신 공시·뉴스·가격·본인 리서치 메모를 종합한 근거 있는 매수/매도 판단을 즉시 받을 수 있다.
**Current focus:** Phase 03 — one-company-walking-skeleton

## Current Position

Phase: 4
Plan: Not started
Status: Phase complete — ready for verification
Last activity: 2026-04-17

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 12
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| — | — | — | — |
| 01 | 3 | - | - |
| 02 | 3 | - | - |
| 03 | 6 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01 P01 | 1min | 2 tasks | 11 files |
| Phase 01 P02 | 4min | 2 tasks | 12 files |
| Phase 01 P03 | 5min | 2 tasks | 5 files |
| Phase 02 P01 | 6 min | 3 tasks | 11 files |
| Phase 02-canonical-entity-identity P02 | 6 min | 2 tasks | 3 files |
| Phase 02-canonical-entity-identity P03 | 15 min | 2 tasks | 8 files |
| Phase 03 P01 | 18min | 2 tasks | 7 files |
| Phase 03 P02 | 12min | 2 tasks | 8 files |
| Phase 03-one-company-walking-skeleton P03 | 11min | 3 tasks | 11 files |
| Phase 03 P04 | 10min | 1 tasks | 3 files |
| Phase 03 P05 | 55min | 2 tasks | 12 files |
| Phase 03-one-company-walking-skeleton P06 | 35min | 3 tasks | 10 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Phase 1 enforcement: Native Postgres 17 over PGLite (concurrency + VectorChord-BM25 require native OS)
- Phase 1 enforcement: ingest venv excludes `anthropic`/`openai`; CI grep-test guards cost discipline
- Phase 2 enforcement: `corp_code` (DART 8-digit) is canonical entity PK, not KRX 6-digit ticker
- Phase 3 enforcement: Walking skeleton ships with no LLM extraction — prompt-injection defenses scaffolded before LLM is wired in (Phase 5)
- Phase 5 research flag: Korean BM25 tokenizer + bge-m3 chunking + VectorChord-BM25 Docker image need empirical spike before commit
- [Phase 01]: Named volume pgdata over bind mount to avoid WSL2 permission issues
- [Phase 01]: Postgres bound to 127.0.0.1 only (no external exposure)
- [Phase 01]: ingest dependency group excludes anthropic/openai to enforce cost discipline
- [Phase 01]: _derived alias with populate_by_name enables both Python (.derived) and YAML (_derived) conventions
- [Phase 01]: Downgraded gitleaks from v8.22.1 to v8.21.2 due to WASM panic on WSL2
- [Phase 02]: psycopg3 driver (postgresql+psycopg://) adopted; testcontainers URL normalized at fixture boundary
- [Phase 02]: Alembic target_metadata=None — hand-written migrations only (no autogenerate)
- [Phase 02]: Content-hash is a dedup primitive, not a security primitive (sha256 collision assumed for dedup only)
- [Phase 02-canonical-entity-identity]: Downgrade does NOT drop vector extension — shared infrastructure
- [Phase 02-canonical-entity-identity]: chunks.embedding via raw ALTER TABLE (pgvector type) — avoids optional type-registration
- [Phase 02-canonical-entity-identity]: D-15 UPSERT uses CASE + array_append — preserves insertion order
- [Phase 02-canonical-entity-identity]: resolve_entity is the ONLY lookup surface — downstream collectors must import, not re-implement
- [Phase 02-canonical-entity-identity]: Ticker-recycle fixture kept synthetic (Pitfall 1); real-case KRX mining deferred to v2
- [Phase 02-canonical-entity-identity]: Half-open temporal interval [valid_from, valid_to) with depth<20 recursive CTE cycle guard
- [Phase 03]: BM25 expression index ((bm25_tokens)::bm25vector) bm25_ops — opclass targets bm25vector, implicit cast materialised at index time
- [Phase 03]: Migration self-contained: CREATE EXTENSION vchord_bm25 + pg_trgm inside 0002 for testcontainer parity with live docker-compose DB
- [Phase 03]: documents.corp_code + btree index added in Plan 01 (not Plan 04) — Plan 05 hybrid_search filters without JSONB probe
- [Phase 03]: trust_level lives on ProvenanceBlock (Zone 1, collector-written, D-19 enum)
- [Phase 03]: Content-hash comparison on freshly-fetched body (not existing file hash) — guarantees correctness when remote changes
- [Phase 03]: Heartbeat sources dict lives outside FrontMatter Pydantic schema (operational telemetry != document content)
- [Phase 03-one-company-walking-skeleton]: injection_defense lives under src/ingest/ — leaf utility consumed by both worker (Plan 04) and MCP (Plan 05); DB/LLM-free
- [Phase 03-one-company-walking-skeleton]: Embedder lazy-imports SentenceTransformer; EMBEDDING_MODEL_VERSION='BAAI/bge-m3@v1' importable without torch for CI parity
- [Phase 03-one-company-walking-skeleton]: chunk_index monotonic per document; section_index resets at each new section (Q4 resolution)
- [Phase 03-one-company-walking-skeleton]: PATTERNS ID snapshot stable: EN_IGNORE_PREV/FAKE_SYSTEM_TAG/DAN_MODE/ROLEPLAY_ADMIN/KO_IGNORE_PREV/KO_ADMIN_MODE
- [Phase 03]: Phase 03-04: Per-doc transaction (engine.begin per document) — D-26 failure isolation requires N commits, not one long txn
- [Phase 03]: Phase 03-04: Delete-then-insert on content_hash change (not UPSERT) — documents.id IS the hash, so hash change is new row with FK cascade
- [Phase 03]: Phase 03-04: injection_flags UNION across runs (prior ∪ new) — security-forward default; cleanup belongs to ingest doctor
- [Phase 03]: hybrid_search uses direct d.corp_code filter (not LEFT JOIN entities) — migration 0002 added the column precisely for this
- [Phase 03]: BM25 ORDER BY is ASC NULLS LAST — vchord_bm25 returns negative scores where lower = better match (plan SQL sketch was inverted)
- [Phase 03]: NULLable filter binds require explicit CAST to column type — psycopg3 AmbiguousParameter otherwise
- [Phase 03]: FastMCP tool registered via mcp.tool()(search) call-form — preserves the callable name bound to plain function for tests + internal callers
- [Phase 03-one-company-walking-skeleton]: Phase 03-06: hatchling build-backend + tool.uv.package=true required to register stock-mcp + stock entry scripts (latent bug from Plan 01)
- [Phase 03-one-company-walking-skeleton]: Phase 03-06: Alembic URL must use engine.url.render_as_string(hide_password=False) — str(engine.url) masks password as ***
- [Phase 03-one-company-walking-skeleton]: Phase 03-06: JUDGE-04 live Claude Code query auto-approved under gsd auto_advance — automated E2 schema test discharges machine-checkable half; operator runs live 9-step procedure out-of-band

### Pending Todos

None yet.

### Blockers/Concerns

- WSL path migration (`/mnt/c/...` → `~/stock/`) must be resolved in Phase 1 before ingest runs (Pitfall 10 → documented in FOUND-04)
- Private portfolio data structure (submodule vs local-only path vs frontmatter overlay) needs a decision during Phase 1 vault layout work

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260417-q3h | Replace local LLM (Ollama/Qwen/EXAONE) stack with Claude schedule + bge-m3-only embeddings | 2026-04-17 | be8c15e | [260417-q3h-replace-local-llm-ollama-qwen-exaone-sta](./quick/260417-q3h-replace-local-llm-ollama-qwen-exaone-sta/) |
| 260418-asr | Fix Phase 3 E2E bugs: collector vault path (A), DART retry hardening (B), auto-seed entities (C) | 2026-04-17 | e23cbc1 | [260418-asr-fix-phase-3-bugs-a-collector-vault-path-](./quick/260418-asr-fix-phase-3-bugs-a-collector-vault-path-/) |
| 260418-bwv | Fix D-1: ingest worker re-seeds entities from frontmatter so `stock ingest rebuild` restores ticker resolution from vault alone | 2026-04-17 | 85efe29 | [260418-bwv-fix-d-1-ingest-worker-seeds-entities-fro](./quick/260418-bwv-fix-d-1-ingest-worker-seeds-entities-fro/) |

## Session Continuity

Last session: 2026-04-18T00:33:17.186Z
Stopped at: Phase 4 context gathered
Resume file: .planning/phases/04-multi-source-collector-coverage/04-CONTEXT.md
