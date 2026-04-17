# Roadmap: Stock Wiki — Claude-Powered Korean Market Knowledge Base

## Overview

A Korean-market stock knowledge base where Claude Code answers buy/sell judgment queries with citations drawn from an Obsidian vault. The roadmap follows a walking-skeleton-first build order: lock in the foundations (Postgres, vault, frontmatter, entity identity) before any data is written, prove the full pipeline end-to-end on a single DART company, then expand collectors, enrich with local LLM, extend the MCP surface, add graph and dashboards, and finally harden judgment UX and operations. Each phase delivers a coherent verifiable capability; no phase leaves the vault in an unusable state.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Load-Bearing Foundation** - Postgres 17 + vault layout + Pydantic frontmatter schema + secrets hygiene + cloud-LLM CI guard lock in before any data is written
- [ ] **Phase 2: Canonical Entity Identity** - corp_code-as-PK model with alias/supersession tracking survives the next rename, split, or 기재정정
- [ ] **Phase 3: One-Company Walking Skeleton** - DART → minimal ingest (no LLM) → hybrid search → FastMCP → Claude answers a real question with a vault citation
- [ ] **Phase 4: Multi-Source Collector Coverage** - KRX prices/flow, economy news, macro indicators, and KIND alerts all flow into vault/raw/ with isolated, retry-safe, idempotent collectors
- [ ] **Phase 5: Claude-Schedule Enrichment with Korean Number Safety** - Claude schedule (git round-trip) extracts _derived attributes, DART financials bypass the LLM, narrative numbers pass regex-LLM-Pydantic-checksum
- [ ] **Phase 6: Full MCP Tool Surface** - Ten-tool MCP contract (overview, events, portfolio, related, filing, add_note, health) with docstring contracts, latency and token-size CI gates
- [ ] **Phase 7: Graph Layer & graphify Integration** - Ingest-populated edges + graphify nightly snapshot + 3-5 canonical subgraph queries make "why did we conclude that?" traceable
- [ ] **Phase 8: Vault Dashboards & Research Memo Templates** - Portfolio, watchlist, events-this-week, per-ticker hubs auto-regenerate; thesis and journal templates ready for human judgments
- [ ] **Phase 9: Judgment Prompt Conventions & Operations Hardening** - Scheduled daily batch, ingest doctor, health-aware Claude responses, evidence-weighting rules turn the skeleton into a daily-use tool

## Phase Details

### Phase 1: Load-Bearing Foundation
**Goal**: Repo, database, vault, schema, and cost guardrails are in place before any data is written. Every load-bearing decision (Postgres vs PGLite, corp_code-as-PK readiness, frontmatter zones, anthropic-ban enforcement) is irrevocable post-ingest, so it happens here.
**Depends on**: Nothing (first phase)
**Requirements**: FOUND-01, FOUND-02, FOUND-03, FOUND-04, FOUND-05, FOUND-06, COLL-07, OPS-06
**Success Criteria** (what must be TRUE):
  1. `docker compose up` starts Postgres 17 with pgvector, VectorChord-BM25, and pg_trgm extensions loaded and reachable
  2. Vault has `raw/`, `notes/`, `ingested/`, `dashboards/`, `graph/` directories while preserving `.obsidian/` and `환영합니다!.md`; `.gitignore` excludes Obsidian workspace churn, caches, and portfolio overlays
  3. `uv`-managed Python 3.12 environments for collectors, ingest, and MCP exist as separate venvs, and the ingest venv provably has no `anthropic` package installed
  4. Pydantic `FrontMatter`, `ProvenanceBlock`, `IngestStateBlock`, and `DerivedBlock` models round-trip YAML fixtures in unit tests
  5. CI fails the build if any file under `ingest/` or `collectors/` imports `anthropic` or `openai`; `.env`-only secret loading is documented and a pre-commit hook blocks committed secrets
  6. A documented option (script or symlink instructions) exists to migrate the vault from `/mnt/c/.../stock` to a WSL-native path
**Plans**: 3 plans
Plans:
- [x] 01-01-PLAN.md -- Docker Postgres 17 + vault directories + gitignore + obsidianignore
- [x] 01-02-PLAN.md -- Python env (pyproject.toml) + Pydantic frontmatter schema + tests
- [x] 01-03-PLAN.md -- CI import guard + secrets hygiene + WSL migration script

### Phase 2: Canonical Entity Identity
**Goal**: The stable key for every entity is DART `corp_code` — not the reusable 6-digit KRX ticker. Schema, alias history, and supersession edges for 기재정정 chains are settled before any document is written so later re-ingest is avoided.
**Depends on**: Phase 1
**Requirements**: ENT-01, ENT-02, ENT-03, STORE-01, STORE-02
**Success Criteria** (what must be TRUE):
  1. Alembic migration creates `documents`, `chunks`, `entities`, `edges`, `events`, `ingest_runs` tables with indexes and runs cleanly on a fresh Postgres volume
  2. `documents.id` is computed as `sha256(body)` and uniqueness is enforced so content-addressed dedup works across re-fetches
  3. `entities` schema stores `corp_code` as the canonical ID, with KRX ticker, aliases, and valid-from/valid-to ranges; a fixture covering a rename, a split, and a ticker-recycling case resolves to the correct entity
  4. A `supersedes` edge type exists and a 기재정정 test fixture produces an edge linking amendment → original
  5. The canonical-entity helper (`resolve_entity(ticker_or_corp_code, as_of=...)`) returns the right row for historical queries
**Plans**: 3 plans
Plans:
- [x] 02-01-PLAN.md -- Alembic scaffold + db/dev deps + content_hash utility + testcontainers fixtures
- [x] 02-02-PLAN.md -- Phase 2 migration (7 tables) + schema/dedup tests + live DB push
- [x] 02-03-PLAN.md -- resolve_entity helper + entity fixtures + supersedes edge tests

### Phase 3: One-Company Walking Skeleton
**Goal**: End-to-end proof of architecture on one company. DART collector fetches, minimal ingest (content-hash dedup, bge-m3 embed, mecab-ko BM25 tokens — no LLM extraction), hybrid search over pgvector + VectorChord-BM25, FastMCP exposes `search`, Claude Code receives an answer with a vault-path citation. All the defenses that must exist before data accumulates (prompt-injection scaffolding, heartbeat, embedding-version tracking) are in place.
**Depends on**: Phase 2
**Requirements**: COLL-01, COLL-06, COLL-08, COLL-09, INGEST-01, INGEST-08, INGEST-09, INGEST-10, INGEST-11, INGEST-12, STORE-03, STORE-04, STORE-05, STORE-06, RET-01, RET-02, RET-03, MCP-01, MCP-02, JUDGE-04
**Success Criteria** (what must be TRUE):
  1. Running `collect_dart --corp-code=00126380 --since=2026-01-01` writes DART 4-type filings for that company to `vault/raw/dart/YYYY-MM-DD/*.md` with only minimal provenance frontmatter and no LLM calls (verified by per-run cost report = $0)
  2. Re-running the same command is idempotent: content-hash keyed upsert skips unchanged docs; a heartbeat file at `vault/ingested/_status/heartbeat.md` records success/failure for each source
  3. The ingest worker reads raw files, writes bge-m3 embeddings (with `chunks.embedding_model` column populated) and mecab-ko tokenized `chunks.bm25_tokens`, honoring the three frontmatter zones (provenance/ingest-state/_derived) without cross-contamination; an HNSW vector index and VectorChord-BM25 index exist
  4. `ingest rebuild` wipes and re-creates the DB from vault alone and reproduces the same document/chunk counts
  5. A `search(query, ticker?, date_range?, source?, mode='hybrid')` MCP tool runs dense + BM25 in parallel, fuses with RRF (k=60), applies structured SQL filters before vector scan, and returns `{vault_path, excerpt, frontmatter_ref, score}` in under 8k tokens and under 5s p95
  6. In Claude Code, "삼성전자 최근 공시 알려줘" returns an answer containing a clickable vault path citation to a real file under `vault/raw/dart/`; prompt-injection defenses (XML delimiters, pattern pre-filter) are live and adversarial-source bodies are excluded from LLM pipelines even though the LLM is not yet wired in
**Plans**: 6 plans
Plans:
- [x] 03-01-PLAN.md — Migration 0002 (section_path/section_index/bm25_tokens + HNSW + BM25 indexes) + dart-fss/vchord_bm25 API probes
- [x] 03-02-PLAN.md — DART collector (client/fetcher/writer) + heartbeat + ProvenanceBlock.trust_level
- [x] 03-03-PLAN.md — Injection defense scaffolding + mecab-ko tokenizer + bge-m3 embedder + section chunker + DART parser
- [x] 03-04-PLAN.md — Ingest worker (scan → parse → chunk → embed → tokenize → upsert) with per-doc transaction + content-hash dedup
- [x] 03-05-PLAN.md — FastMCP 2.x stdio server + hybrid RRF search tool + .mcp.json registration
- [ ] 03-06-PLAN.md — stock CLI + ingest rebuild (idempotent) + E2E schema test + human-verify JUDGE-04 checkpoint

### Phase 4: Multi-Source Collector Coverage
**Goal**: Beyond DART, the vault receives KRX prices + investor flow + short balance, Korean economy news from at least two outlets, macro indicators from ECOS and FRED, and KIND trading-halt/관리종목/불성실공시 events. Each collector is an isolated module: one source failing does not block the others, and reruns are idempotent.
**Depends on**: Phase 3
**Requirements**: COLL-02, COLL-03, COLL-04, COLL-05
**Success Criteria** (what must be TRUE):
  1. `collect_krx` writes daily OHLCV, investor flow (외국인/기관/개인 순매수), and short-position balance for every watchlist and portfolio ticker to `vault/raw/krx/YYYY-MM-DD/*.md`
  2. `collect_news` uses trafilatura + RSS to pull economy-and-finance articles from at least two of {한경, 이데일리, 서울경제}, writing summary + URL (not full body) to `vault/raw/news/...` and respecting the copyright policy
  3. `collect_macro` writes daily ECOS (기준금리, USD/KRW) and FRED (US 10Y, WTI) rows; schema matches what search-filters can later key on
  4. `collect_kind` captures 거래정지, 관리종목, 불성실공시 events into `vault/raw/kind/...` with structured event-type tags
  5. Orchestrated run with one source set to force-fail shows the other three complete successfully and the heartbeat file records per-source status
**Plans**: TBD

### Phase 5: Claude-Schedule Enrichment with Korean Number Safety
**Goal**: The ingest worker extracts `_derived` attributes (tickers, event_type, catalysts, sentiment, numeric_facts, summary) via a Claude Schedule agent that runs outside the ingest venv and commits enriched frontmatter back through git — not via a local model runner. The ingest venv's `anthropic` ban is preserved because the schedule agent is a separate process. Korean financial numbers are kept out of free-form LLM extraction — DART financials go through `dart-fss` structured accessors; narrative numbers go through regex-LLM-Pydantic-checksum. Embeddings (bge-m3, 1024-d) are computed locally via sentence-transformers directly, with no separate embedding-server dependency.
**Depends on**: Phase 4
**Requirements**: INGEST-02, INGEST-03, INGEST-04, INGEST-05, INGEST-06, INGEST-07
**Success Criteria** (what must be TRUE):
  1. A Claude Schedule agent (defined outside the ingest venv) polls `vault/raw/` for documents missing a `_derived` block, extracts attributes, and commits the enriched frontmatter back via git; the ingest venv itself contains no `anthropic`/`openai` imports and the CI guard (COLL-07) still passes
  2. The schedule agent writes only the `_derived` zone of frontmatter (provenance and ingest-state zones are write-protected against schedule writes)
  3. DART financial-statement numbers appearing in `_derived.numeric_facts` match values pulled directly from dart-fss structured accessors (no LLM involvement in those specific fields) on a 10-filing golden set
  4. News/report narrative numbers pass the four-stage pipeline (regex candidate extraction → Claude picks → Pydantic validates → digit-checksum compares to source); disagreements flag the doc for review instead of silent acceptance
  5. Re-running the schedule on the same unchanged document produces byte-identical `_derived` blocks; the three frontmatter zones remain non-overlapping
**Plans**: TBD
**Research flag**: NEEDS RESEARCH — Korean BM25 tokenizer benchmark on equity vocabulary (mecab-ko vs soynlp vs kiwipiepy), bge-m3 chunking strategy for long DART 사업보고서, VectorChord-BM25 Docker image availability (composite vs custom Dockerfile), Claude Schedule RemoteTrigger git round-trip latency for daily batch volumes

### Phase 6: Full MCP Tool Surface
**Goal**: Claude Code has the full FastMCP toolbox needed for the judgment workflow: `get_ticker_overview`, `get_recent_events`, `get_portfolio_state`, `get_related`, `get_filing`, `add_note`, `health`. Each tool has a docstring written as an LLM-facing behavioral contract, enforces the write-scope rules (only `vault/notes/` is writable), and passes CI gates on response latency and token size.
**Depends on**: Phase 5
**Requirements**: MCP-03, MCP-04, MCP-05, MCP-06, MCP-07, MCP-08, MCP-09, MCP-10
**Success Criteria** (what must be TRUE):
  1. Calling `get_ticker_overview("005930")` from Claude Code returns a single structured object combining financials, investor flow, recent events, and related notes — all cited with vault paths — in under 8k tokens p95
  2. `get_recent_events`, `get_portfolio_state`, `get_related`, and `get_filing` each return correct data against a fixture vault and enforce the ID-based two-step pattern (list returns IDs + snippets, `get_filing(id)` returns full body)
  3. `add_note` writes only under `vault/notes/` and is rejected with a clear error if the caller passes a `raw/` or `ingested/` target path
  4. `health()` reports last batch success per source, DB connectivity, and staleness indicators derived from the heartbeat file
  5. CI tests assert every tool's p95 latency < 5s and p95 response size < 8k tokens on the fixture corpus; docstrings render as coherent LLM-facing contracts in the MCP inspector
**Plans**: TBD
**UI hint**: yes

### Phase 7: Graph Layer & graphify Integration
**Goal**: The edges that ingest populates (`ticker→filing`, `filing→event`, `note→ticker`, `event→event`, `ticker→sector`, `supersedes`) become queryable through `get_related`, and graphify produces a periodic vault-wide interactive snapshot. Before any graphify run, 3–5 canonical subgraph queries are defined so the output answers real questions instead of producing a supernova.
**Depends on**: Phase 6
**Requirements**: GRAPH-01, GRAPH-02, GRAPH-03
**Success Criteria** (what must be TRUE):
  1. A full ingest run populates the `edges` table with typed edges; `get_related(document_id, depth=1)` returns the expected neighbor set on a labeled fixture
  2. `graphify` run (daily or manual) writes `vault/graph/{YYYY-MM-DD}/` containing `index.html`, `graph.json`, and `GRAPH_REPORT.md` that Obsidian and a browser can open
  3. 3–5 canonical subgraph queries (e.g. "last-30-day events for my positions", "filing clusters in a sector", "catalyst chain for ticker X") are documented in `vault/graph/README.md` and each returns a non-empty, legible subgraph on the current corpus
  4. graphify edges are tagged EXTRACTED / INFERRED / AMBIGUOUS so Claude can differentiate provenance when citing graph evidence
**Plans**: TBD
**UI hint**: yes

### Phase 8: Vault Dashboards & Research Memo Templates
**Goal**: The user's daily entry points inside Obsidian — portfolio state, watchlist, this-week events, per-ticker hub pages — regenerate automatically from the DB using Dataview. Thesis and journal templates let the user record investment logic (with kill criteria) and decision logs that are indexed alongside raw data.
**Depends on**: Phase 7
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04, NOTE-01, NOTE-02, NOTE-03
**Success Criteria** (what must be TRUE):
  1. `dashboards/portfolio.md` shows holdings, evaluation values, and recent events via Dataview queries that survive vault rebuilds
  2. `dashboards/watchlist.md` and `dashboards/events-this-week.md` render correct, current data and remain human-editable where intended without being clobbered by orchestration
  3. A ticker hub note at `ingested/by-ticker/{corp_code}.md` exists per covered company, auto-linking related raw docs, memos, and price trends
  4. `notes/theses/` and `notes/journal/` contain templates; creating a new thesis from the template yields a note with `tickers[]`, `tags[]`, `created`, `author` frontmatter that shows up in Postgres indexes within one ingest cycle
  5. Memo frontmatter fields are queryable alongside raw documents through the same `search` tool, confirming notes are first-class LLM-readable content
**Plans**: TBD
**UI hint**: yes

### Phase 9: Judgment Prompt Conventions & Operations Hardening
**Goal**: The scheduled daily batch, health awareness, and evidence-weighted answering turn the skeleton into a daily tool. Claude's responses follow explicit conventions: cite vault paths, refuse to speculate when evidence is absent or stale, and weight user memos against raw sources transparently. Operations surfaces everything that could silently break.
**Depends on**: Phase 8
**Requirements**: JUDGE-01, JUDGE-02, JUDGE-03, JUDGE-05, JUDGE-06, OPS-01, OPS-02, OPS-03, OPS-04, OPS-05
**Success Criteria** (what must be TRUE):
  1. A systemd.timer (WSL) or Windows Task Scheduler entry runs `daily-batch` after Korean market close and logs success/failure; `stock batch run --source=...` lets the user trigger a single source manually
  2. Asking Claude Code "종목 X 리서치해줘" produces an answer citing DART + price + user-memo + macro evidence (4-axis bundle) with every claim traceable to a vault path; "포트폴리오 오늘 어때?" and "매도 후보 3개 제안" follow the same evidence contract
  3. When vault has no recent data for a ticker (or `health()` reports staleness), Claude returns a "근거 없음 / 스테일" response instead of speculating; tested with a fixture where the heartbeat is artificially old
  4. The prompt convention explicitly documents how user memos (`notes/`) are weighted versus raw sources (`raw/`), and a sample audit confirms answers do not confuse opinion for fact
  5. `ingest_runs` rows appear for every scheduled run; `ingest doctor` detects and reports missing-in-DB files, orphan chunks, and content-hash mismatches; failure modes are visible via heartbeat, logs, and `health()` simultaneously
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Load-Bearing Foundation | 0/3 | Planning complete | - |
| 2. Canonical Entity Identity | 0/3 | Planning complete | - |
| 3. One-Company Walking Skeleton | 0/6 | Planning complete | - |
| 4. Multi-Source Collector Coverage | 0/TBD | Not started | - |
| 5. Claude-Schedule Enrichment with Korean Number Safety | 0/TBD | Not started | - |
| 6. Full MCP Tool Surface | 0/TBD | Not started | - |
| 7. Graph Layer & graphify Integration | 0/TBD | Not started | - |
| 8. Vault Dashboards & Research Memo Templates | 0/TBD | Not started | - |
| 9. Judgment Prompt Conventions & Operations Hardening | 0/TBD | Not started | - |

---
*Roadmap created: 2026-04-17*
*Granularity: fine (9 phases, derived from walking-skeleton-first research skeleton)*
*Coverage: 71/71 v1 requirements mapped to exactly one phase*
