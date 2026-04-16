# Project Research Summary

**Project:** Korean-Market Stock Wiki (stock-mcp)
**Domain:** Personal/small-team Korean equity research knowledge base — Obsidian vault as source of truth, Postgres+pgvector hybrid retrieval, FastMCP server surfaced to Claude Code
**Researched:** 2026-04-16 / 2026-04-17
**Confidence:** HIGH on architecture, stack and pitfalls; MEDIUM on local LLM sizing and BM25 extension choice

---

## Executive Summary

This is an LLM-native knowledge base for the Korean equity market, built on Garry Tan's gbrain 3-layer pattern: Git-tracked Markdown (source of truth) → Postgres+pgvector (derived retrieval index) → MCP tool surface (Claude Code integration). Karpathy's "LLM Wiki" philosophy shapes the content model: documents are written and read by LLMs, not primarily by humans. The product's single metric is whether Claude Code can answer a portfolio query with citations drawn from recent DART filings, price data, news, and the user's own research memos. All other decisions are subordinate to that test.

The recommended build order is a walking skeleton first: one collector (DART) → minimal ingest (no LLM enrichment yet) → one MCP tool (search) → one Claude query with a real vault citation. Everything else — additional collectors, LLM attribute extraction, graphify, dashboards — plugs into that skeleton. This ordering is critical because the frontmatter schema and entity model (using corp_code, not the 6-digit ticker, as the stable identity key) are load-bearing decisions that must be made before any data is written. Changing the schema after ingest has begun forces a full re-ingest.

The dominant risks are cost discipline (Claude API must never appear in the ingest loop), PGLite's single-connection limit (use native Postgres 17 from day one), and scope drift (Korean daily-batch is the whole scope; US markets, real-time, and dashboards are explicitly deferred). A secondary risk class covers Korean-market specifics: ticker identity across corporate actions, amended DART filings (기재정정), prompt injection from adversarial sources such as 종목토론방, and CP949/EUC-KR encoding in legacy feeds. These are engineering problems with clear mitigations, but they must be addressed in Phase 1 before data accumulates.

---

## Unified Top Findings

1. **Frontmatter schema is the highest-leverage decision in the entire project.** Every downstream component — Dataview queries, Postgres structured filters, graphify clustering, MCP tool responses, Claude citations — depends on consistent ticker, corp_code, event_type, source, date, and ingest_status fields. Define the schema with Pydantic/Zod validation before any collector writes a file.

2. **Use corp_code (DART 8-digit), not the KRX 6-digit ticker, as the canonical entity key.** Korean market has frequent name changes, spin-offs, split-adjusted ticker recycling, and delistings. The 6-digit code is reused post-delisting; corp_code is stable across all corporate actions. Graph edges must use corp_code; ticker is a convenience field that can change.

3. **Native Postgres 17 over PGLite, from day one.** PGLite's single-connection constraint blocks concurrent ingest-batch + MCP-server access. VectorChord-BM25, needed for proper Korean hybrid search, requires native OS Postgres and does not run in WASM. The Docker setup is a single docker-compose.yml — the "no-Docker" saving is not worth the concurrency breakage.

4. **Cost discipline must be architectural, not behavioral.** The ingest process must not import the anthropic SDK at all. Enforce via a CI grep-test that fails if anthropic or openai appears in ingest/*. All LLM calls in ingest go through a single llm_client.py wrapper that accepts only OLLAMA_HOST. A MAX_CLOUD_USD budget cap gates any Haiku fallback. Local-first with Haiku fallback is the economic model.

5. **Walking skeleton before any feature expansion.** The minimal proof-of-architecture is: collect_dart fetching one company's filings → minimal ingest (content-hash dedup, bge-m3 embed, tsvector, no LLM extraction) → FastMCP search tool → Claude answers with a vault path citation. Phases 3a/3b/3c (additional collectors, LLM enrichment, full MCP surface) all run in parallel after the skeleton is green.

6. **Three frontmatter zones must be kept separate and enforced.** (1) Provenance block: written by collectors, never overwritten by ingest. (2) Ingest-state block: written and updated by ingest only. (3) _derived: true block: regenerable LLM output; users are warned not to hand-edit. User-authored content belongs only in vault/notes/, never in vault/raw/ or vault/ingested/.

7. **The MCP tool surface is a contract, not an implementation detail.** The six core tools (get_ticker_overview, search, get_recent_events, get_portfolio_state, get_related, get_filing) each need a typed signature and an LLM-facing docstring that is the behavioral contract. Hard limits: fewer than 10 tools total, all responses under 8k tokens p95, all latencies under 5s p95. The ID-based two-step pattern (search returns snippets; get_document(id) returns full text on demand) is mandatory to prevent context floods.

8. **Korean BM25 requires pre-tokenization, not just a Postgres extension.** Neither VectorChord-BM25 nor pg_search ships a proven Korean morphological analyzer by default. The safe path is to pre-tokenize with mecab-ko (via python-mecab-ko) in the ingest pipeline, store the tokenized form in a separate column, and let BM25 operate on whitespace-split tokens. This isolates the Korean NLP dependency from the Postgres extension choice.

9. **graphify is Phase 6 in the architecture, not Phase 1.** It depends on graph edges already populated by the ingest enrichment pipeline. Obsidian's native graph (link-based) works as a functional stopgap. When graphify does run, define the 3-5 graph queries it must answer before running it — otherwise the output is a "pretty supernova" that no one uses.

10. **The vault is on the Windows filesystem (/mnt/c/) via WSL, which has documented performance and case-sensitivity issues.** This should be migrated to a WSL-native path (~/stock/) before the vault scales beyond a few thousand files. Address in Phase 0 before any ingest runs.

---

## Key Findings

### Recommended Stack

| Layer | Choice | Version | Why |
|-------|--------|---------|-----|
| DART collection | dart-fss | latest (0.4.x) | Only actively maintained DART wrapper; OpenDartReader is dormant |
| KRX price/financial | pykrx + FinanceDataReader | pykrx >=1.0.50, FDR >=0.9.94 | Complementary coverage; cross-checking on edge cases |
| News extraction | trafilatura | >=1.12 | #1 F1 on multilingual news benchmarks; built-in RSS; no ML dependency |
| Naver scraping | requests + pandas.read_html + BeautifulSoup4 | standard | No maintained library; thin bespoke scrapers per page type |
| Scheduler | systemd.timer (WSL/Linux) | OS-native | Survives reboots, structured logs, no always-on host process |
| Database | Native Postgres 17 via Docker | pgvector/pgvector:pg17 | Concurrent ingest+MCP, full pgvector features, VectorChord-BM25 support |
| Vector index | pgvector | 0.8.0 | HNSW iterative scan, halfvec, binary quantization all in 0.8 |
| BM25 | VectorChord-BM25 | latest (2026) | Native Postgres extension, composable with RRF fusion |
| Korean tokenizer | python-mecab-ko (pre-ingest) | latest | No Postgres extension ships a proven Korean analyzer |
| Embeddings | bge-m3 via Ollama | bge-m3:latest | MIRACL #1 multilingual; 8192-token context; Korean native coverage |
| Local LLM (ingest primary) | qwen2.5:14b-instruct-q4_K_M | Ollama | Structured JSON output, multilingual, fits 16GB VRAM |
| Local LLM (Korean specialist) | exaone3.5:7.8b | Ollama | KoMT-Bench highest at 7.8B; 50% Korean vocabulary |
| Cloud LLM fallback | Claude Haiku 4.5 | Anthropic SDK | Graceful degradation; ~$0.0035/doc; gated by ALLOW_CLOUD_LLM env var |
| MCP server | FastMCP | 2.x (>=2.11, <3.0) | Decorator API; 3.x not yet ecosystem-stable |
| Obsidian dashboards | Dataview plugin | >=0.5 | Frontmatter-query dashboards; required from day one |
| Graph | graphifyy (safishamsi/graphify) | v4 | Confirmed outputs: graph.json, index.html, GRAPH_REPORT.md, Obsidian backlinks |
| Python runtime | CPython 3.12 | 3.12.x | ML deps not yet tested on 3.13 |
| Env manager | uv | >=0.4 | Fast, modern; replaces pip+venv |

### Expected Features

**Must have (v1 table stakes):**
- DART 4-type collection (정기A/주요사항B/발행C/지분D) — event-driven judgment is blind without it
- KOSPI/KOSDAQ daily OHLCV + investor flow (외국인/기관 순매수) + short position data via pykrx
- Economic news collection scoped to watchlist tickers, RSS-first, 2-3 sources
- Macro indicators (ECOS 기준금리/환율 + FRED 미10년물/WTI) — minimum macro context
- Markdown + frontmatter schema with validated mandatory fields (ticker, corp_code, event_type, source, date, id)
- Per-ticker hub notes auto-generated; portfolio/watchlist dashboard notes as user entry point
- User research memo folder with templates — human-authored judgments as first-class vault content
- Postgres + pgvector hybrid search (BM25 + dense embedding via bge-m3)
- Daily batch schedule + manual trigger + deduplication (source-ID-keyed idempotent upsert)
- 6 core MCP tools: get_ticker_overview, search, get_recent_events, get_portfolio_state, get_related, get_filing
- Vault path citations mandatory in every MCP response — the entire value proposition depends on provenance
- 4-axis evidence bundle in judgment responses: disclosures + price + user memo + macro context

**Should have (v1.x differentiators, add after v1 validation):**
- graphify vault snapshot → interactive graph + get_related MCP tool
- Trading halt / 관리종목 / 불성실공시 monitoring via KIND
- Thesis / decision log note template with kill criteria
- Weekly digest note auto-generation
- Local LLM ingest fully activated (Ollama + Qwen2.5 + bge-m3) — trigger: Haiku costs become material
- Self-healing lint pass — trigger: vault exceeds a few thousand files

**Defer to v2+:**
- US individual stock support (different data model entirely)
- Slack/Discord frontend
- Whole-market screener
- PDF report OCR (copyright resolution required)
- Portfolio backtest / simulation

**Anti-features (never build):**
- Autotrading (legal/risk, core scope violation)
- Real-time tick streaming (destroys vault-as-SoT model)
- Per-query live web crawling (token cost, latency, cache defeat)
- Public web deployment
- Push notifications / mobile app

### Architecture Approach

The system follows a strict 3-layer separation: batch producers (collectors + ingest + graphify) write to the vault; the vault (Markdown + YAML frontmatter in git) is the sole source of truth; consumers (stock-mcp, Obsidian) read the vault and its derived DB index. The DB is always reconstructible from the vault via ingest rebuild. Component boundaries are enforced: collectors never call LLMs; ingest never fetches from the network; stock-mcp never writes to raw/ or ingested/.

**Major components:**

| Component | Responsibility | Key constraint |
|-----------|---------------|----------------|
| collectors/ | Fetch external data; write minimal-frontmatter .md to vault/raw/ | No LLM calls, no DB writes; one sub-module per source |
| ingest/ | Read pending vault files; LLM-extract attributes; write embeddings + rows to DB; rewrite frontmatter | No network fetching; idempotent on content-hash; single DB transaction per document |
| db/ | DDL, Alembic migrations, query helpers | No LLM calls, no HTTP; write-owned by ingest, read-owned by stock-mcp |
| stock_mcp/ | FastMCP tool surface for Claude Code | Read-mostly; write tools limited to vault/notes/ only |
| graphify/ | Periodic vault snapshot to vault/graph/ + static HTML | Reads vault only; does not touch DB |
| orchestration/ | Schedule producers; retry/failure isolation; run ledger | Invokes CLIs only; no domain logic imports |

**Core DB tables:** documents (content-hash PK, one row per vault file), chunks (section-aware splits with tsvector + vector(1024) columns), entities (corp_code-keyed), edges (typed graph relationships), events (structured typed events with JSONB payload), ingest_runs (operational ledger).

**Hybrid search pattern:** search tool runs dense HNSW cosine + BM25 in parallel, fuses with RRF (k=60), returns ranked {vault_path, excerpt, frontmatter, score}. Structured filters applied as SQL WHERE before vector scan; pgvector 0.8 iterative HNSW scan prevents recall collapse under selective filters.

### High-Risk Pitfalls (5 most load-bearing of 28 catalogued)

1. **Claude API in the ingest loop (Pitfall 1)** — Cost blow-up and core constraint violation. Prevent architecturally: ingest venv must not contain the anthropic package; CI grep-test fails the build if it appears in ingest/*; all LLM calls routed through llm_client.py accepting only Ollama endpoints. Address in Phase 1 before any extraction prompt is written.

2. **PGLite for concurrent workloads (Pitfall 2)** — PGLite v0.4 single-connection mode cannot support simultaneous ingest writes + MCP reads. Migration after data is indexed is costly. Use native Postgres 17 via Docker from day zero. Address in Phase 0.

3. **Ticker identity loss across corporate actions (Pitfall 3)** — KRX 6-digit codes are reused post-delisting; name changes and splits invalidate historical frontmatter using ticker as PK. Use corp_code (DART 8-digit, stable) as the canonical entity ID. Changing this after ingest requires a full re-ingest. Address in Phase 1 entity model.

4. **Prompt injection from adversarial sources (Pitfall 4)** — 종목토론방 and some news sources contain deliberate LLM instruction injection. Wrap all document bodies in untrusted-content XML delimiters in ingest prompts; run a pre-filter stripping injection patterns; do not ingest individual 토론방 post bodies through the LLM extractor. Address in Phase 1 before the first news source is connected.

5. **Local LLM hallucination on Korean financial numbers (Pitfall 5)** — Qwen2.5-14B misreads 조/억/만 unit combinations; errors are silent and get cited as facts. For DART 재무제표, bypass the LLM entirely and use dart-fss structured accessors. For narrative sections: regex pre-extract candidate numeric spans → LLM picks among candidates → Pydantic validation → digit-level checksum. Address in Phase 2.

---

## Implications for Roadmap

### Suggested Phase Structure

**Phase 0: Foundations**
Goal: repo layout, Postgres 17 container, vault folder structure, frontmatter schema + Pydantic validators, .gitignore / .obsidianignore, entity model with corp_code as PK, WSL path migration to ~/stock/ if feasible.
Avoids: PGLite concurrency (P2), ticker identity loss setup (P3), Obsidian write-conflict setup (P7), personal portfolio in git (P26).
Exit: pytest green on schema migration + frontmatter parse/validate; Postgres container starts with vector, vchord_bm25, pg_trgm extensions loaded.
Research flag: SKIP — well-documented patterns; standard Docker + Alembic + Obsidian gitignore setup.

**Phase 1: Walking Skeleton**
Goal: collect_dart for one company → minimal ingest (no LLM: dedup by content-hash, bge-m3 embed, tsvector) → FastMCP search tool → Claude Code answers with a real vault path citation.
Must establish: Claude API ban in ingest (P1), prompt injection defenses scaffolded (P4), news copyright policy (P14), DART key hygiene (P15), CP949 encoding CI fixture (P16), silent batch failure heartbeat (P18).
Exit: end-to-end slice works; ingest CI grep-test passes; heartbeat file written; no anthropic import in ingest/.
Research flag: SKIP — DART API patterns and FastMCP stdio transport are well-documented.

**Phase 2: Collector Expansion + Enrichment + MCP Surface (parallel tracks)**
Track 2a: collect_naver, collect_news (RSS + trafilatura), collect_macro (ECOS + FRED), collect_krx (pykrx OHLCV + investor flow + short positions).
Track 2b: Ollama + Qwen2.5 attribute extraction; DART 기재정정 supersedes linking; Korean number extraction safety (regex + Pydantic + golden test set); mecab-ko pre-tokenization for BM25; embedding model version tracking.
Track 2c: Full 6-tool MCP surface; typed signatures; docstrings as LLM contracts; latency + token-size CI tests; ID-based two-step pattern enforced.
Avoids: pgvector HNSW not ivfflat (P8, P10); real BM25 extension not pg_trgm (P9); number hallucination (P5); 기재정정 linking (P17); scope drift (P6).
Research flag: NEEDS RESEARCH on Korean BM25 tokenizer choice (mecab-ko vs soynlp vs kiwipieki on equity vocabulary); VectorChord-BM25 Docker image availability; bge-m3 chunking strategy on long DART reports.

**Phase 3: Graph Layer**
Goal: edges populated by ingest enrichment → related() MCP tool → list_events() tool → graphify nightly snapshot → vault/graph/ Obsidian-browsable output + static HTML.
Entry: Phase 2b enrichment producing entities and edges.
Avoids: graph supernova (P19) — define 3-5 canonical subgraph queries before running graphify.
Research flag: SKIP — graphify SKILL.md confirms capabilities; architecture is fully defined.

**Phase 4: Dashboards + Orchestration Hardening**
Goal: auto-generated portfolio.md, watchlist.md, events-this-week.md from DB queries; retry/failure isolation per source; ingest rebuild command; Dataview queries; MCP health() tool surfacing staleness; provenance-weighted Claude prompt conventions.
Avoids: silent batch failure (P18); MCP response verbosity (P11); bias from user memos (P13); Obsidian file-count scaling (P12) via tiered live/ vs archive/ layout.
Research flag: SKIP — standard orchestration patterns; Dataview is well-documented.

**Phase 5: Polish + Telemetry**
Goal: recall@10 eval suite on hand-labeled queries; local LLM ingest benchmarked against Haiku fallback; per-run cost telemetry; Obsidian vault tiering if file count warrants; reranking experiments.
Research flag: SKIP — iterative improvement on established patterns.

### Phase Ordering Rationale

- Phase 0 before any data: frontmatter schema and entity model are effectively write-once; changing them post-ingest requires full re-ingest.
- Phase 1 skeleton before parallel expansion: establishes interface contracts that all modules must satisfy; parallel development against a defined interface is feasible, against an undefined one is not.
- Phase 2 tracks in parallel: ARCHITECTURE.md explicitly marks 3a/3b/3c as parallelizable; each track has distinct domain ownership.
- Graph (Phase 3) after LLM enrichment (Phase 2b): graph edges only exist after the enrichment pipeline runs; earlier graphify produces a shallow link-only graph.
- Dashboards (Phase 4) after collectors and MCP tools: dashboards are DB queries; the DB must have multi-source data and the tool surface must exist before dashboard quality is evaluable.

### Research Flags

Phases needing gsd-research-phase during planning:
- Phase 2 (BM25 tokenization): Korean morphological analyzer choice on equity-research vocabulary needs empirical benchmarking on the actual corpus. No single authoritative source covers this specific domain.
- Phase 2 (chunking strategy): Optimal chunk size for DART 사업보고서 (which can exceed 100k tokens) with bge-m3's 8192-token context needs benchmarking on retrieval quality.
- Phase 2 (VectorChord-BM25 Docker): Verify whether pgvector/pgvector:pg17 needs a custom Dockerfile extension or a tensorchord/vchord composite image is available.

Phases with standard patterns (skip research):
- Phase 0: Docker + Alembic + Obsidian gitignore patterns are fully documented.
- Phase 1: DART API + dart-fss + FastMCP stdio transport have working examples.
- Phase 3: graphify pipeline confirmed via local SKILL.md.
- Phase 4: systemd.timer + Dataview orchestration patterns are well-established.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Korean data libraries verified via Snyk maintenance status; pgvector features confirmed via changelog; FastMCP version verified via PyPI. One MEDIUM item: VectorChord-BM25 Docker availability needs a Phase 2 spike. |
| Features | HIGH (Korean market); MEDIUM (LLM-wiki patterns) | DART 공시 types, KRX data, ECOS/FRED sources confirmed via official APIs. LLM-wiki integration patterns are community-validated but less formally specified. |
| Architecture | HIGH | gbrain 3-layer pattern is direct prior art with a live reference implementation. Component boundaries and data flow are unambiguous. |
| Pitfalls | HIGH (technical); MEDIUM (legal/Korean market) | pgvector, PGLite, MCP pitfalls verified against official docs. Korean copyright law precedent (2022Do1533) verified; DART rate limits change and should be re-verified at Phase 1. |

**Overall confidence:** HIGH — four research dimensions converged on compatible recommendations with no significant conflicts. The walking-skeleton → parallel expansion build order is endorsed by all four agents independently.

### Gaps to Address During Planning

- **Korean BM25 tokenizer benchmark:** mecab-ko vs soynlp vs kiwipieki on equity vocabulary. Plan a Phase 2 empirical spike on 200-500 real documents before committing to the pre-tokenization column schema.
- **VectorChord-BM25 Docker image:** Confirm whether a composite image from tensorchord is available or a custom Dockerfile is required before Phase 0 Docker setup.
- **bge-m3-ko vs vanilla bge-m3:** Default to vanilla; switch only if Phase 2 retrieval benchmarks show measurable lift on the actual corpus.
- **Private portfolio data structure:** Decide before Phase 1 vault layout is finalized — options are git submodule, local ~/.stock-private/ path resolved by stock-mcp at query time, or per-user frontmatter overlay.
- **FastMCP 2.x to 3.x migration timeline:** Re-evaluate Q3 2026 before Phase 3 MCP surface work; adopt 3.x if stable, otherwise accept migration debt.
- **WSL filesystem location:** Plan migration from /mnt/c/ to ~/stock/ in Phase 0 and confirm all tooling (git, Obsidian, systemd) works from the new path.

---

## Sources

### Primary (HIGH confidence)
- garrytan/gbrain GitHub — 3-layer architecture reference implementation
- pgvector/pgvector GitHub CHANGELOG — 0.8 features confirmed
- PGLite v0.4 announcement (ElectricSQL, 2026-03-25) — single-user mode limits
- FastMCP PyPI — 2.x vs 3.x version state (2026-04)
- safishamsi/graphify GitHub + local ~/.claude/skills/graphify/SKILL.md — pipeline and outputs confirmed
- BAAI/bge-m3 HuggingFace — MIRACL scores, 8192-token context
- LG AI Research EXAONE 3.5 technical report — KoMT-Bench benchmark
- Anthropic platform pricing (2026-04) — Haiku 4.5 $1.00/$5.00 per M tokens
- DART 전자공시시스템 official — 공시 유형 A/B/C/D classification
- Claude Code MCP docs + issue #22542 — 60s timeout, MAX_MCP_OUTPUT_TOKENS

### Secondary (MEDIUM confidence)
- dart-fss Snyk advisor — maintenance status (Healthy, recent release)
- trafilatura comparative analysis — F1 ~0.94, ranked #1 multilingual
- VectorChord-BM25 GitHub + blog — BlockMax WeakAnd, RRF fusion pattern
- ParadeDB hybrid search blog — RRF normalization, BM25 + pgvector pattern
- Obsidian forum threads — large-vault performance at 10k+ files
- Korean Copyright Act 2022Do1533 Supreme Court decision (Lexology)
- OWASP LLM Top 10 + Simon Willison on prompt injection (2026)

### Tertiary (LOW confidence, single-source or vendor-reported)
- VectorChord-BM25 vs Elasticsearch 3x benchmark — vendor self-reported, treat as directional
- bge-m3-ko vs vanilla quality gap on Korean equity corpus — unverified; needs Phase 2 test
- Haiku cost crossover math — rough estimate; dependent on actual document volume

---

*Research completed: 2026-04-16 / 2026-04-17*
*Ready for roadmap: yes*
