---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 3 context gathered
last_updated: "2026-04-17T13:06:41.697Z"
last_activity: 2026-04-17 -- Phase 3 planning complete
progress:
  total_phases: 9
  completed_phases: 2
  total_plans: 12
  completed_plans: 6
  percent: 50
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-17)

**Core value:** Claude Code에서 보유·관심 종목을 질의했을 때, 최신 공시·뉴스·가격·본인 리서치 메모를 종합한 근거 있는 매수/매도 판단을 즉시 받을 수 있다.
**Current focus:** Phase 02 — canonical-entity-identity

## Current Position

Phase: 3
Plan: Not started
Status: Ready to execute
Last activity: 2026-04-17 -- Phase 3 planning complete

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 6
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| — | — | — | — |
| 01 | 3 | - | - |
| 02 | 3 | - | - |

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

### Pending Todos

None yet.

### Blockers/Concerns

- WSL path migration (`/mnt/c/...` → `~/stock/`) must be resolved in Phase 1 before ingest runs (Pitfall 10 → documented in FOUND-04)
- Private portfolio data structure (submodule vs local-only path vs frontmatter overlay) needs a decision during Phase 1 vault layout work

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260417-q3h | Replace local LLM (Ollama/Qwen/EXAONE) stack with Claude schedule + bge-m3-only embeddings | 2026-04-17 | be8c15e | [260417-q3h-replace-local-llm-ollama-qwen-exaone-sta](./quick/260417-q3h-replace-local-llm-ollama-qwen-exaone-sta/) |

## Session Continuity

Last session: 2026-04-17T12:30:29.148Z
Stopped at: Phase 3 context gathered
Resume file: .planning/phases/03-one-company-walking-skeleton/03-CONTEXT.md
