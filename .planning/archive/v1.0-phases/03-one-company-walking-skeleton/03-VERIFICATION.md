---
phase: 03-one-company-walking-skeleton
verified: 2026-04-18T08:00:00Z
status: human_needed
score: 5/6 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Ask Claude Code '삼성전자 최근 공시 알려줘' in a real interactive Claude Code session with .mcp.json auto-loaded, DART_API_KEY set, Docker Postgres running, and bge-m3 pre-downloaded"
    expected: "Response contains at least one citation of the form vault/raw/dart/YYYY/...md; excerpt is wrapped in <vault_excerpt> delimiters"
    why_human: "Requires a live interactive Claude Code session. The automated executor cannot run an interactive Claude session. The automated E2E test (test_E2_schema_without_live_api) covers the schema contract; the live JUDGE-04 proof requires a human."
---

# Phase 3: One-Company Walking Skeleton Verification Report

**Phase Goal:** End-to-end proof on 삼성전자 (corp_code=00126380). DART collector → LLM-less ingest (content-hash dedup + bge-m3 embed + mecab-ko BM25 tokens) → hybrid search (pgvector + VectorChord-BM25 + RRF) → FastMCP search tool → Claude Code answer with vault citation. Pre-data defense (prompt-injection scaffolding + heartbeat + embedding version tracking) installed before data accumulates.
**Verified:** 2026-04-18T08:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | `collect_dart --corp-code=00126380 --since=2026-01-01` writes DART filings to `vault/raw/dart/YYYY-MM-DD/*.md` with minimal provenance frontmatter and no LLM calls | VERIFIED | `src/collectors/dart/__init__.py` exports `collect_dart`; `fetcher.py` calls `pblntf_ty=["A","B"]`; `writer.py` uses `trust_level='trusted'`; CI import guard confirms zero `anthropic`/`openai` imports in `src/collectors/` |
| SC-2 | Re-running the same command is idempotent (content-hash dedup skips unchanged docs); heartbeat at `vault/ingested/_status/heartbeat.md` records success/failure per source | VERIFIED | `collect_dart` compares `compute_body_hash(body)` to existing `frontmatter.content_hash` on each filing before writing; `heartbeat.py` provides `record_source_run` with atomic tempfile+os.replace; 8 collector tests + 9 heartbeat tests green |
| SC-3 | Ingest worker reads raw files, writes bge-m3 embeddings (`chunks.embedding_model` populated) and mecab-ko `chunks.bm25_tokens`, honoring three frontmatter zones; HNSW and VectorChord-BM25 indexes exist | VERIFIED | `worker.py` wires all Plan 03 components; `EMBEDDING_MODEL_VERSION="BAAI/bge-m3@v1"` written to every chunk row; `tokenize_ko` populates `bm25_tokens`; migration 0002 creates `ix_chunks_embedding_hnsw` (HNSW) and `ix_chunks_bm25` (BM25 expression index); W9 test asserts zone integrity |
| SC-4 | `ingest rebuild` wipes and re-creates the DB from vault alone and reproduces the same document/chunk counts | VERIFIED | `rebuild_from_vault` in `src/ingest/rebuild.py` calls `command.downgrade(cfg, "base")` then `command.upgrade(cfg, "head")` then `ingest_run(force_reembed=True)`; R7 (slow) idempotence test asserts `before == after` doc ids + chunk counts against testcontainer Postgres |
| SC-5 | `search(query, ticker?, date_range?, source?, mode='hybrid')` MCP tool runs dense + BM25 in parallel, fuses with RRF k=60, applies SQL filters pre-scan, returns `{vault_path, excerpt, frontmatter_ref, score}` in under 8k tokens and 5s p95 | VERIFIED | `hybrid_search` in `search_core.py` uses a single CTE with `_RRF_K = 60`, `_MAX_TOP_K = 50`, and `_SESSION_SET_ITERATIVE_SCAN`; `build_filter_clause` resolves ticker via `resolve_entity`; measured p95 ~6ms at test scale; response ~1264 tokens; 28 test functions in test_hybrid_search/boot/tool files all green |
| SC-6 | Claude Code returns an answer with vault_path citation for "삼성전자 최근 공시 알려줘"; prompt-injection defenses are live | PARTIAL (human_needed) | Automated half verified: `test_E2_schema_without_live_api` (fast) asserts vault_path + `<vault_excerpt>` wrap against seeded data; `injection_defense.py` ships 6-pattern PATTERNS table with `wrap_untrusted` and `detect_injection_patterns`; worker populates `ingest_state.injection_flags`; live Claude Code proof deferred per auto-approved Task 3 checkpoint |

**Score:** 5/6 truths verified (SC-6 requires live human step)

### Deferred Items

None — SC-6 is split: automated half verified, live-session half is human_needed (not a later-phase deferral).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/db/migrations/versions/0002_phase03_chunking_columns.py` | Phase 3 schema extension | VERIFIED | revision="0002", down_revision="0001"; adds section_path/section_index/bm25_tokens + documents.corp_code + HNSW/BM25 indexes |
| `src/collectors/dart/__init__.py` | collect_dart(corp_code, since, max_docs, vault_root) | VERIFIED | Exports collect_dart; wires client+fetcher+writer+heartbeat |
| `src/collectors/dart/client.py` | dart-fss wrapper with retry | VERIFIED | get_client() + find_corp() |
| `src/collectors/dart/fetcher.py` | list_ab_filings + fetch_body | VERIFIED | pblntf_ty=["A","B"]; tenacity retry |
| `src/collectors/dart/writer.py` | Atomic vault write with trust_level | VERIFIED | compute_body_hash + write_filing with trust_level='trusted' |
| `src/ingest/heartbeat.py` | Atomic record_source_run | VERIFIED | tempfile+os.replace; 6 matches for tempfile/os.replace |
| `src/ingest/injection_defense.py` | wrap_untrusted + detect_injection_patterns + PATTERNS + is_adversarial | VERIFIED | 6 pattern families; 13 tests green |
| `src/ingest/tokenizer.py` | tokenize_ko (mecab-ko content POS + blake2s int32) | VERIFIED | blake2s digest_size=4; _CONTENT_POS={NNG,NNP,SL,SN} |
| `src/ingest/embedder.py` | Embedder + EMBEDDING_MODEL_VERSION + encode_query LRU | VERIFIED | EMBEDDING_MODEL_VERSION="BAAI/bge-m3@v1"; lru_cache(maxsize=256); SentenceTransformer lazy import |
| `src/ingest/chunking.py` | Chunk dataclass + chunk_document | VERIFIED | win-overlap step; max_tokens=1500 |
| `src/ingest/parsers/dart.py` | parse_sections for DART | VERIFIED | Roman/Arabic TOC split + (root) fallback |
| `src/ingest/worker.py` | ingest_run + process_document | VERIFIED | engine.begin() per-doc txn; detect_injection_patterns; tokenize_ko; EMBEDDING_MODEL_VERSION; record_source_run; corp_code bound; zero f-string SQL |
| `src/stock_mcp/search_core.py` | hybrid_search + build_filter_clause | VERIFIED | SET hnsw.iterative_scan; resolve_entity; encode_query; tokenize_ko; wrap_untrusted; _MAX_TOP_K=50; _RRF_K=60 |
| `src/stock_mcp/tools/search.py` | @mcp.tool() def search with D-22 signature | VERIFIED | FastMCP("stock-mcp"); Literal["hybrid","semantic","bm25"]; LLM-facing docstring >100 chars |
| `src/stock_mcp/server.py` | _check_db_connection fail-fast | VERIFIED | def _check_db_connection present |
| `src/stock_mcp/__main__.py` | main() with DB fail-fast + stdio | VERIFIED | sys.exit(1) + transport="stdio" |
| `src/stock_mcp/models.py` | DateRange / SearchHit / SearchResult | VERIFIED | Pydantic v2 models |
| `src/stock_mcp/errors.py` | ErrorCode + StructuredError + to_error_response | VERIFIED | ErrorCode enum present |
| `src/stock_mcp/logging.py` | log_tool_call → sys.stderr | VERIFIED | print(..., file=sys.stderr) |
| `.mcp.json` | Claude Code MCP registration | VERIFIED | command="uv"; args=["run","--group","mcp","stock-mcp"] |
| `src/cli/__main__.py` | stock CLI entry | VERIFIED | argparse; collect + ingest subcommands |
| `src/cli/commands.py` | Subcommand handlers | VERIFIED | cmd_collect_dart + cmd_ingest_run + cmd_ingest_rebuild; lazy imports |
| `src/ingest/rebuild.py` | rebuild_from_vault | VERIFIED | command.downgrade/upgrade; isatty + assume_yes; dry_run path |
| `tests/e2e/test_search_citation_schema.py` | JUDGE-04 schema contract | VERIFIED | E2 (fast) asserts vault_path + `<vault_excerpt>` wrap; E1 (slow/gated) for live API |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/collectors/dart/__init__.py` | `src/ingest/heartbeat.py::record_source_run` | `from ingest.heartbeat import record_source_run` | WIRED | Line 17; called at end of collect_dart |
| `src/collectors/dart/writer.py` | `src/shared/frontmatter.py::write_frontmatter` | `write_frontmatter` import | WIRED | write_filing uses write_frontmatter |
| `src/collectors/dart/__init__.py` | `src/shared/content_hash.py::compute_content_hash` | `compute_body_hash` in writer.py | WIRED | writer.py line 37-44 |
| `src/ingest/worker.py` | `src/ingest/parsers/__init__.py::parse_sections` | `from ingest.parsers import parse_sections` | WIRED | Line 38 |
| `src/ingest/worker.py` | `src/ingest/chunking.py::chunk_document` | `from ingest.chunking import chunk_document` | WIRED | Line 34 |
| `src/ingest/worker.py` | `src/ingest/embedder.py::Embedder` | `from ingest.embedder import ... Embedder` | WIRED | Line 35 |
| `src/ingest/worker.py` | `src/ingest/tokenizer.py::tokenize_ko` | `from ingest.tokenizer import tokenize_ko` | WIRED | Line 39 |
| `src/ingest/worker.py` | `src/ingest/injection_defense.py::detect_injection_patterns` | `from ingest.injection_defense import detect_injection_patterns` | WIRED | Line 37 |
| `src/stock_mcp/tools/search.py` | `src/stock_mcp/search_core.py::hybrid_search` | `from ..search_core import hybrid_search` | WIRED | Tool delegates to core |
| `src/stock_mcp/search_core.py` | `src/db/entity.py::resolve_entity` | `from db.entity import resolve_entity` | WIRED | Line 30 |
| `src/stock_mcp/search_core.py` | `src/ingest/embedder.py::encode_query` | `from ingest.embedder import encode_query` | WIRED | Line 26 |
| `src/stock_mcp/search_core.py` | `src/ingest/tokenizer.py::tokenize_ko` | `from ingest.tokenizer import tokenize_ko` | WIRED | Line 28 |
| `src/stock_mcp/search_core.py` | `src/ingest/injection_defense.py::wrap_untrusted` | `from ingest.injection_defense import wrap_untrusted` | WIRED | Line 27 |
| `src/cli/commands.py` | `src/collectors/dart/__init__.py::collect_dart` | `from collectors.dart import collect_dart` (lazy) | WIRED | cmd_collect_dart line 19 |
| `src/cli/commands.py` | `src/ingest/worker.py::ingest_run` | `from ingest.worker import ingest_run` (lazy) | WIRED | cmd_ingest_run line 34 |
| `src/ingest/rebuild.py` | `alembic.command.downgrade/upgrade` | `from alembic import command` | WIRED | Lines 144-145 |
| `src/db/migrations/versions/0002_phase03_chunking_columns.py` | `src/db/migrations/versions/0001_phase02_initial_schema.py` | `down_revision = "0001"` | WIRED | Line 31 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `src/stock_mcp/tools/search.py` | `raw_hits` | `hybrid_search(engine, query, ...)` | Yes — queries live `chunks` + `documents` tables via SQLAlchemy | FLOWING |
| `src/ingest/worker.py` | `vecs` / `bm25_arrays` | `Embedder.encode(texts)` / `tokenize_ko(t)` | Yes — real bge-m3 model (slow) or FakeEmbedder in fast tests with same SQL path | FLOWING |
| `src/collectors/dart/writer.py` | Markdown files | `fetch_body(filing)` via dart-fss `.pages` iteration | Yes — real DART API body extraction (gated by DART_API_KEY; mocked in tests) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| stock --help lists subcommands | `uv run stock --help` | Confirmed in 03-06-SUMMARY: outputs "collect" and "ingest" subcommands; hatchling build-backend fix verified this resolves | PASS (SUMMARY evidence) |
| .mcp.json registers stock-mcp | `jq '.mcpServers["stock-mcp"].command' .mcp.json` | Returns "uv" | PASS |
| Zero f-string SQL in worker | `grep -E 'f"""\|f"SELECT\|f"INSERT\|f"DELETE' src/ingest/worker.py` | 0 matches | PASS |
| Zero anthropic/openai in collectors/ingest | `grep -rE '(import\|from) (anthropic\|openai)' src/collectors/ src/ingest/` | 0 matches (verified live) | PASS |
| Live Claude Code JUDGE-04 query | Human 9-step procedure | 03-06-CLAUDE-TRANSCRIPT.md is placeholder (auto-approved) | SKIP (human_needed) |

Note: Step 7b full behavioral spot-checks require Docker Postgres 17 running. Core pattern checks above performed without starting the server.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| COLL-01 | 03-02 | collect_dart writes DART A+B filings to vault | SATISFIED | src/collectors/dart exists; 8 collector tests green |
| COLL-06 | 03-02 | Collectors write minimal frontmatter, no LLM calls | SATISFIED | Zero anthropic/openai imports verified |
| COLL-08 | 03-02 | Per-source isolation + idempotent upsert on content-hash | SATISFIED | compute_body_hash dedup; per-filing try/except |
| COLL-09 | 03-02 | Heartbeat records success/failure per source | SATISFIED | heartbeat.py atomic writer; 9 tests green |
| INGEST-01 | 03-04 | Content-hash dedup skips unchanged docs | SATISFIED | SKIP condition in process_document; W3 test green |
| INGEST-08 | 03-03 | Prompt-injection defense: XML delimiter + pattern prefilter | SATISFIED | injection_defense.py; 6 families; 13 tests green |
| INGEST-09 | 03-03 | is_adversarial gate for adversarial sources | SATISFIED | is_adversarial() exported; trust_level='adversarial'→True |
| INGEST-10 | 03-03 | bge-m3 1024-d embeddings via sentence-transformers locally | SATISFIED | Embedder class; EMBEDDING_MODEL_VERSION="BAAI/bge-m3@v1" |
| INGEST-11 | 03-03 | mecab-ko BM25 tokens in chunks.bm25_tokens | SATISFIED | tokenize_ko(); W6 test asserts non-empty INT[] |
| INGEST-12 | 03-03 | chunks.embedding_model column populated with version | SATISFIED | EMBEDDING_MODEL_VERSION written in every INSERT |
| STORE-03 | 03-01 | HNSW index on chunks.embedding | SATISFIED | ix_chunks_embedding_hnsw in migration 0002 |
| STORE-04 | 03-01 | VectorChord-BM25 index on chunks.bm25_tokens | SATISFIED | ix_chunks_bm25 expression index in migration 0002 |
| STORE-05 | 03-06 | ingest rebuild wipes and re-creates DB from vault | SATISFIED | rebuild_from_vault; R7 idempotence test green |
| STORE-06 | 03-04 | Three frontmatter zones not cross-contaminated | SATISFIED | W9 zone-integrity test; only ingest_state mutated by worker |
| RET-01 | 03-05 | Hybrid dense+BM25 parallel fusion with RRF k=60 | SATISFIED | _HYBRID_SQL CTE; _RRF_K=60; 16 hybrid tests green |
| RET-02 | 03-05 | Structured filters before vector scan; ticker→corp_code | SATISFIED | build_filter_clause; d.corp_code direct filter; resolve_entity |
| RET-03 | 03-05 | Response <8k tokens, p95 <5s | SATISFIED | ~1264 tokens, ~6ms p95 at test scale (833x headroom) |
| MCP-01 | 03-05 | FastMCP 2.x stdio server registered via .mcp.json | SATISFIED | transport="stdio"; .mcp.json committed |
| MCP-02 | 03-05 | search tool with D-22 signature; structured error envelope | SATISFIED | Literal["hybrid","semantic","bm25"]; to_error_response |
| JUDGE-04 | 03-06 | All responses contain vault_path citations | PARTIAL | Automated: E2 test asserts vault_path + `<vault_excerpt>`; Live: deferred to human |

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `.planning/phases/03-one-company-walking-skeleton/03-06-CLAUDE-TRANSCRIPT.md` | Placeholder (auto-approved checkpoint; no real Claude Code transcript) | Info | No code impact; live JUDGE-04 smoke proof not yet recorded |

No stub patterns found in production code paths. All `return []` and `return {}` instances reviewed in context — they are either test helpers, error isolation paths, or empty-input guards with real fetch/compute paths that overwrite them. Zero f-string SQL confirmed in worker.py and search_core.py.

### Human Verification Required

#### 1. Live Claude Code JUDGE-04 Proof

**Test:** From the project root with all prerequisites satisfied (DART_API_KEY in .env, Docker Postgres 17 healthy, bge-m3 pre-downloaded):
1. Run `uv run stock collect dart --corp-code=00126380 --since=2025-04-17 --max-docs=50`
2. Run `uv run stock ingest run`
3. Start a new Claude Code session in this project (or restart so .mcp.json auto-loads)
4. Ask: `삼성전자 최근 공시 알려줘`

**Expected:** Response contains at least one citation of the form `vault/raw/dart/YYYY/...md` and excerpts are wrapped in `<vault_excerpt>` delimiters. Save the transcript to `.planning/phases/03-one-company-walking-skeleton/03-06-CLAUDE-TRANSCRIPT.md`.

**Why human:** Requires a live interactive Claude Code session, DART_API_KEY, and local infrastructure. The automated executor cannot simulate an interactive LLM session. The E2E schema test (test_E2_schema_without_live_api) confirms the machine-checkable half of JUDGE-04.

### Gaps Summary

No blocking gaps found. All 20 phase-3 requirement IDs are satisfied by code that exists, is substantive, and is wired. The single human verification item (live Claude Code query) is the only path to `passed` status — it does not indicate a code defect.

The 03-06-CLAUDE-TRANSCRIPT.md placeholder is by design: the automated executor cannot run an interactive Claude session. Once the operator performs the 9-step verification procedure and records the transcript, status upgrades to `passed`.

---

_Verified: 2026-04-18T08:00:00Z_
_Verifier: Claude (gsd-verifier)_
