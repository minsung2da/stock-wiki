---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 06-09-PLAN.md (Phase 6 complete)
last_updated: "2026-05-02T05:58:10.852Z"
last_activity: 2026-05-02
progress:
  total_phases: 10
  completed_phases: 6
  total_plans: 37
  completed_plans: 37
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-17)

**Core value:** Claude Code에서 보유·관심 종목을 질의했을 때, 최신 공시·뉴스·가격·본인 리서치 메모를 종합한 근거 있는 매수/매도 판단을 즉시 받을 수 있다.
**Current focus:** Phase 06 — full-mcp-tool-surface

## Current Position

Phase: 06 (full-mcp-tool-surface) — EXECUTING
Plan: 9 of 9
Status: Ready to execute
Last activity: 2026-05-02

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 28
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| — | — | — | — |
| 01 | 3 | - | - |
| 02 | 3 | - | - |
| 03 | 6 | - | - |
| 04 | 8 | - | - |
| 05 | 8 | - | - |

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
| Phase 04 P01 | 568 | 4 tasks | 10 files |
| Phase 04 P02 | 1107 | 2 tasks | 10 files |
| Phase 04 P03 | 7min | 2 tasks | 12 files |
| Phase 04-multi-source-collector-coverage P04 | 30min | 2 tasks | 12 files |
| Phase 04 P05 | 1800 | 5 tasks | 20 files |
| Phase 04 P06 | 18 | 1 tasks | 3 files |
| Phase 04 P07 | 20 min | 3 tasks | 5 files |
| Phase 04 P08 | 8m | 2 tasks | 2 files |
| Phase 05 P01 | 13min | 2 tasks | 3 files |
| Phase 05 P03 | 12min | 2 tasks | 4 files |
| Phase 05 P08 | 22min | 2 tasks | 14 files |
| Phase 05 P02 | 29min | 2 tasks | 2 files |
| Phase 05-claude-schedule-enrichment-with-korean-number-safety P04 | 7min | 2 tasks | 2 files |
| Phase 05-claude-schedule-enrichment-with-korean-number-safety P05 | 5min | 2 tasks | 4 files |
| Phase 05-claude-schedule-enrichment-with-korean-number-safety P06 | 5min | 2 tasks | 2 files |
| Phase 05-claude-schedule-enrichment-with-korean-number-safety P07 | 13min | 2 tasks | 4 files |
| Phase 06-full-mcp-tool-surface P01 | 27min | 2 tasks | 13 files |
| Phase 06-full-mcp-tool-surface P02 | 12min | 3 tasks | 14 files |
| Phase 06 P03 | 45 | 3 tasks | 109 files |
| Phase 06-full-mcp-tool-surface P05 | 11min | 2 tasks tasks | 4 files files |
| Phase 06 P06 | 18 | 2 tasks | 4 files |
| Phase 06-full-mcp-tool-surface P07 | 25min | 2 tasks tasks | 3 files files |
| Phase 06-full-mcp-tool-surface P08 | 14min | 1 tasks | 2 files |
| Phase 06 P09 | 16min | 2 tasks | 14 files |

## Accumulated Context

### Roadmap Evolution

- Phase 10 added: Decision-context coverage: peer/historical valuation + supply-demand + private notes scaffold

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
- [Phase 04]: Use entity_aliases kind='eng_name' (not 'english_name') — CHECK constraint already permits it, no migration
- [Phase 04]: TickerRef + Observation typed Pydantic nested models (R-07) for news/macro frontmatter
- [Phase 04]: KRX Plan 02: bundled orchestrator into writer T1 commit; promoted tenacity to collectors dep group
- [Phase 04]: Phase 04 Plan 03: ECOS StatisticSearch needs ITEM_CODE1 filter; macro_series.yaml schema extended with item_code field
- [Phase 04]: Phase 04 Plan 03: Append-merge reads prior observations from ProvenanceBlock.observations (D-07 structured), not body markdown — structured is source of truth
- [Phase 04]: Phase 04 Plan 03: R-06 revisions propagate as extra={'revisions': [...]} through record_source_run — structured, not log lines
- [Phase 04-multi-source-collector-coverage]: News collector: pre-load scoped alias inventory once (R-01), substring scan over regex tokens for better Korean recall
- [Phase 04-multi-source-collector-coverage]: trafilatura deduplicate=False in news fetcher: the LRU cache breaks R-11 cross-URL dedup behavior
- [Phase 04-multi-source-collector-coverage]: edaily RSS stays http:// — HTTPS fails upstream (Microsoft-IIS without SNI)
- [Phase 04]: Plan 05 Option D: DART pblntf_ty='I' supersedes pykrx for exchange status events (pykrx has no get_market_status function)
- [Phase 04]: CLI _dispatch() helper: single lazy-import boundary for collector orchestration, enables monkeypatch-based testing without DB/network
- [Phase 04]: Exit codes: 0=all ok, 1=any source error/partial (D-20), 2=CLI misuse/unknown --sources (D-21). Report emitted on stderr to keep stdout composable
- [Phase 05]: extra=forbid on v2 models only (ReviewFlag/SentimentBlock/NumericFact/DerivedBlock) — legacy zones preserved for Phase 3/4 compat
- [Phase 05]: EventType exported as top-level Literal alias for downstream Wave 2+ modules to annotate without re-defining
- [Phase 05]: Regex number_extraction: removed \b after Hangul (ASCII-only boundary breaks between 원을/주가 etc.), wrapped _NUM in non-capturing group for safe compound composition
- [Phase 05]: Plan 05-08: Routines skill lives in-repo at .claude/routines/enrich/ (D-29); helpers load via importlib.util so tests reach into .claude/ without polluting pythonpath
- [Phase 05]: Plan 05-08: Zone-integrity SHA256 over yaml.safe_dump(provenance)+yaml.safe_dump(ingest_state) — deterministic sort_keys=True payload; _derived changes correctly ignored
- [Phase 05]: Plan 05-02: Leaf pure-util pattern for shared/units.py — no imports from shared.frontmatter or ingest.*, MappingProxyType frozen constants, defensive .get() on Literal-narrowed str input
- [Phase 05]: Plan 05-02: normalize_to_krw explicitly returns None for non-KRW currencies (USD/EUR/JPY) — no silent FX conversion, downstream sees value_krw=None and skips KRW range checks
- [Phase 05-claude-schedule-enrichment-with-korean-number-safety]: Plan 05-04: KOSPI/KOSDAQ sanity rules use unit='other' — NumericFact.unit Literal excludes 'index_pt'; promotion to Literal deferred to Phase 9
- [Phase 05-claude-schedule-enrichment-with-korean-number-safety]: Plan 05-05: LINE_ITEM_SYNONYMS covers 22 canonical KR line items; new labels graduate via explicit synonym addition (no fabricated mapping)
- [Phase 05-claude-schedule-enrichment-with-korean-number-safety]: Plan 05-05: _fs_extract is a monkeypatchable wrapper — cassette-driven tests avoid live DART API in CI
- [Phase 05-claude-schedule-enrichment-with-korean-number-safety]: Plan 05-06: BacklogItem compound key (path::flag) — two flags on same document track first_seen independently; tolerant regex parse over YAML load for prior file robustness
- [Phase 05-claude-schedule-enrichment-with-korean-number-safety]: Plan 05-07: alert_level auto-populated only when source=='enrich' (COLL-08 per-source isolation preserved for dart/krx/news/macro)
- [Phase 05-claude-schedule-enrichment-with-korean-number-safety]: Plan 05-07: disk_metrics module has zero DB deps — Routines skill injects db_size_mb via pg_database_size query
- [Phase 06-full-mcp-tool-surface]: Phase 6 P-01: Portfolio.load signature cutover (vault_root -> repo_root); SoT moved to notes/private/portfolio.md (gitignored, local-only)
- [Phase 06-full-mcp-tool-surface]: Plan 06-02: build_snippet uses inline <vault_excerpt> wrap (not wrap_untrusted) — wrap_untrusted requires source/trust/doc_id triple unavailable for portfolio rows; existing E2E test accepts both forms
- [Phase 06-full-mcp-tool-surface]: Plan 06-02: ErrorCode additions are append-only — Phase 3 ordering preserved verbatim, six new Phase 6 codes appended
- [Phase 06]: Migration 0003 drops ck_edge_type_phase2 entirely (Phase 7 GRAPH-01 will redefine taxonomy)
- [Phase 06]: Fixture corpus uses Random(seed=42) for byte-deterministic regeneration
- [Phase 06]: Stub embedder + tokenizer in tests/stock_mcp/conftest.py — bge-m3 / mecab-ko never load in CI
- [Phase 06-full-mcp-tool-surface]: Plan 06-05: get_related uses recursive CTE with UNION (cycle dedupe) + hard depth cap of 2 (T-6-05-01 DoS mitigation)
- [Phase 06-full-mcp-tool-surface]: Plan 06-05: get_portfolio_state uses relative repo_root import (..repo_root) to match tools/ package convention; PortfolioLoadError + ValidationError both map to INVALID_FRONTMATTER (PATH_NOT_FOUND reserved for missing file)
- [Phase 06-full-mcp-tool-surface]: Plan 06-07: health() reports DB-down as signal (db.status='down' in successful HealthResponse), not as error envelope — drives Phase 9 JUDGE-05 refusal path
- [Phase 06-full-mcp-tool-surface]: Plan 06-07: heartbeat._read_sources renamed to public read_sources with backwards-compat alias for legacy ingest callers
- [Phase 06-full-mcp-tool-surface]: Plan 06-08: get_ticker_overview composes 3 axes defensively (events/portfolio/related_notes) — each axis fails open so any one backend can't sink the bundle; events:error sentinel + None portfolio + [] related_notes
- [Phase 06-full-mcp-tool-surface]: Plan 06-08: _apply_truncation extracted as pure function (OverviewResponse + target → OverviewResponse) — directly unit-testable on crafted oversize inputs without DB; priority order private_thesis<valuation<supply_demand<portfolio<related_notes<events
- [Phase 06-full-mcp-tool-surface]: Plan 06-08: 4-char-per-token heuristic (matches logging.py); TARGET_TOKENS=7000 leaves 1000-token margin under D-19 8k ceiling; no tiktoken runtime dep
- [Phase 06]: Plan 06-09: server.py side-effect import block registers all 7 new tools onto shared mcp instance; smoke test walks _tool_manager._tools dict (sync); docstring contract enforced via parametrized test (D-24)
- [Phase 06]: Plan 06-09: tiktoken cl100k_base measure() uses N=20 reps + 1 warmup to absorb bge-m3 cold-load (process-startup cost, not per-request); per-tool perf JSONs committed for PR-diff visibility

### Pending Todos

None yet.

### Blockers/Concerns

- WSL path migration (`/mnt/c/...` → `~/stock/`) must be resolved in Phase 1 before ingest runs (Pitfall 10 → documented in FOUND-04)
- Private portfolio data structure (submodule vs local-only path vs frontmatter overlay) needs a decision during Phase 1 vault layout work

### Quick Tasks Completed

| # | Description | Date | Commit | Status | Directory |
|---|-------------|------|--------|--------|-----------|
| 260417-q3h | Replace local LLM (Ollama/Qwen/EXAONE) stack with Claude schedule + bge-m3-only embeddings | 2026-04-17 | be8c15e | | [260417-q3h-replace-local-llm-ollama-qwen-exaone-sta](./quick/260417-q3h-replace-local-llm-ollama-qwen-exaone-sta/) |
| 260418-asr | Fix Phase 3 E2E bugs: collector vault path (A), DART retry hardening (B), auto-seed entities (C) | 2026-04-17 | e23cbc1 | | [260418-asr-fix-phase-3-bugs-a-collector-vault-path-](./quick/260418-asr-fix-phase-3-bugs-a-collector-vault-path-/) |
| 260418-bwv | Fix D-1: ingest worker re-seeds entities from frontmatter so `stock ingest rebuild` restores ticker resolution from vault alone | 2026-04-17 | 85efe29 | | [260418-bwv-fix-d-1-ingest-worker-seeds-entities-fro](./quick/260418-bwv-fix-d-1-ingest-worker-seeds-entities-fro/) |
| 260424-asr | Seed `entities` from portfolio.md so `stock collect krx` no longer fails_soft on watchlist tickers (e.g., 000660 SK하이닉스). New `src/db/seed_entities.py` CLI + 3 unit tests + CLAUDE.md setup step. | 2026-04-24 | pending | | [260424-asr-entities-seed-expansion](./quick/260424-asr-entities-seed-expansion/) |
| 260426-k8h | Preserve `_derived` block when collectors re-write a doc with new observations. New `read_existing_derived()` helper in src/shared/frontmatter.py + wired into all 5 collector writers (macro/krx/news/dart/kind). | 2026-04-26 | 5eb3a79 | Verified | [260426-k8h-preserve-derived-block-when-collectors-r](./quick/260426-k8h-preserve-derived-block-when-collectors-r/) |
| 260426-mic | Preserve `ingest_state.injection_flags` (D-18 prompt-injection markers) on collector rewrite. New `read_existing_injection_flags()` helper + wired into all 5 collector writers. Scope-locked to injection_flags only; other ingest_state fields still reset (pipeline-state markers). | 2026-04-26 | 45cbf36 |  | [260426-mic-preserve-injection-flags-in-ingest-state](./quick/260426-mic-preserve-injection-flags-in-ingest-state/) |

## Session Continuity

Last session: 2026-05-02T05:58:04.532Z
Stopped at: Completed 06-09-PLAN.md (Phase 6 complete)
Resume file: None
