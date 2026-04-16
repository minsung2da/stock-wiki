# Architecture Research

**Domain:** Personal/small-team Korean stock knowledge base (Obsidian-first, gbrain-style hybrid retrieval, MCP-surfaced to Claude Code)
**Researched:** 2026-04-16
**Confidence:** HIGH on component boundaries and data flow (direct gbrain/graphify prior art); MEDIUM on specific library choices for ingest and BM25 (several viable options verified).

---

## 1. High-Level Component Diagram

### System Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          USER LAYER (Obsidian + Claude Code)              │
│  ┌────────────────────────┐          ┌────────────────────────────────┐  │
│  │  Obsidian (vault UI)   │          │  Claude Code (session)         │  │
│  │  - dashboards/         │          │  - calls stock-mcp tools       │  │
│  │  - notes/              │  reads   │  - synthesizes answers         │  │
│  │  - native graph view   │ <─────── │  - appends notes back          │  │
│  └───────────┬────────────┘          └─────────────┬──────────────────┘  │
│              │ reads .md files                     │ JSON-RPC (stdio/SSE) │
├──────────────┼────────────────────────────────────┼──────────────────────┤
│              │                                     ▼                      │
│              │                         ┌──────────────────────┐           │
│              │                         │   stock_mcp/         │           │
│              │                         │   FastMCP server     │           │
│              │                         │   (tool surface)     │           │
│              │                         └──────────┬───────────┘           │
│              │                                    │ SQL + file reads      │
├──────────────▼────────────────────────────────────▼──────────────────────┤
│                        VAULT (source of truth)                            │
│  ┌────────┬────────────┬─────────────┬──────────────┬───────────────┐    │
│  │ raw/   │ ingested/  │ notes/      │ dashboards/  │ graph/        │    │
│  │ scrape │ LLM-enrich │ hand-written│ auto-gen .md │ graphify out  │    │
│  └────┬───┴──────┬─────┴──────┬──────┴──────┬───────┴──────┬────────┘    │
├───────┼──────────┼────────────┼─────────────┼──────────────┼─────────────┤
│       │          │            │             │              │             │
│       ▼          ▼            ▼             ▼              ▼             │
│  ┌────────────────────────────────────────────────────────────────┐      │
│  │                     DB (PGLite/Postgres + pgvector)            │      │
│  │   documents · chunks · embeddings · entities · edges · events  │      │
│  │   BM25 (tsvector) · HNSW cosine · RRF fusion                   │      │
│  └────────────────────────────────────────────────────────────────┘      │
├──────────────────────────────────────────────────────────────────────────┤
│                    PRODUCERS (batch, no Claude tokens)                    │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐          │
│  │ collectors │→ │ ingest     │→ │ graphify   │  │orchestration│         │
│  │ (sources)  │  │ (local LLM)│  │ (snapshot) │  │ (scheduler) │         │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘          │
└──────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Single Responsibility | Boundary / Allowed Deps |
|-----------|----------------------|-------------------------|
| `collectors/` | Fetch raw external data and write minimal-frontmatter `.md` into `vault/raw/`. One sub-module per source (`collect_dart`, `collect_naver`, `collect_news`, `collect_macro`, `collect_krx`). | May read network + `vault/raw/`. **No DB writes.** Collector never enriches — that's ingest's job. |
| `vault/` | Human- and LLM-readable source of truth. Git-tracked. Obsidian renders it. | Data only. No code. Layout: `raw/`, `ingested/`, `notes/`, `dashboards/`, `graph/`, `templates/`. |
| `ingest/` | Read unprocessed `.md` from vault, enrich frontmatter via local LLM, emit rows to DB. Idempotent on content-hash. | Reads/writes vault; writes DB. **No network fetching** (that's collectors). |
| `db/` | Store embeddings, structured facts, full-text index, graph edges. Schema migrations live here. | Owns DDL + query helpers. No LLM calls, no HTTP. |
| `stock_mcp/` | Expose a stable MCP tool surface to Claude Code. Translates tool calls → DB queries + vault reads → structured responses. | Read-mostly. Write tools (`add_note`) only touch `vault/notes/`. Never mutates `raw/` or `ingested/`. |
| `graphify/` | Snapshot the vault into an interactive knowledge graph (HTML + Obsidian-compatible side-vault). Runs periodically. | Reads vault; writes `vault/graph/` and/or external site dir. Does not touch DB. |
| `orchestration/` | Schedule collectors + ingest + graphify, handle retries, dedup, and failure isolation. | Invokes subprocesses; writes `vault/_state/` for run ledger. No domain logic. |

**Critical boundary rules:**
- Vault is the only two-way channel between producers and consumers. DB is a derived index — always reconstructible from vault.
- Ingest is the *only* writer to `vault/ingested/` and DB rows.
- stock_mcp is *read-only* for `raw/` and `ingested/`; only `notes/` is writable through it.
- Collectors never invoke LLMs (token discipline).

---

## 2. Data Flow — One Document End-to-End

**Example: DART 분기보고서 for 삼성전자 (005930) filed at 2026-04-16 16:30 KST.**

```
[1] scheduled run                (orchestration/)
      │
      ▼
[2] collect_dart fetches filing via dart-fss
      │  extracts minimal fields: rcept_no, corp_code, rcept_dt, report_nm
      │  computes sha256 of raw body
      ▼
[3] writes vault/raw/dart/2026-04-16/20260416000523_005930_quarterly.md
      │  frontmatter = {source: dart, ticker: "005930", rcept_no, content_hash, fetched_at, ingest_status: pending}
      │  body = raw HTML-stripped text (or link + excerpt for license-unclear reports)
      │  (atomic: write to .tmp → fsync → rename)
      ▼
[4] orchestration emits "new_file" events OR ingest does a scan-by-status pass
      │  (watchdog inotify fallback → cron scan of ingest_status=pending)
      ▼
[5] ingest/enrich:
      │  reads file, checks content_hash vs db.documents.content_hash
      │    - miss  → new doc  → full pipeline
      │    - match → skip (idempotent)
      │    - diff  → "update": delete-write pattern (delete chunks/embeddings for doc_id, re-extract)
      │  chunks body (section-aware, 1500-2200 chars)
      │  calls local LLM (Ollama/Qwen2.5) to extract:
      │     tickers, event_type, numeric_facts, catalysts, sentiment, entities, dates
      │  calls bge-m3 for dense embedding; generates tsvector for BM25
      │  writes transactionally to Postgres:
      │     BEGIN
      │       UPSERT documents (id=content_hash, ...)
      │       DELETE chunks WHERE document_id=...
      │       INSERT chunks, embeddings
      │       INSERT entities, edges (ON CONFLICT DO NOTHING)
      │     COMMIT
      │  rewrites file atomically with enriched frontmatter + ingest_status: done
      │  (also copies/symlinks under vault/ingested/by-ticker/005930/ for Obsidian browsing)
      ▼
[6] graphify runs nightly (or on-demand)
      │  reads vault → emits graph/index.md, graph/nodes/*.md, graph/site/index.html
      ▼
[7] user in Claude Code: "삼성전자 최근 이슈 요약"
      │
      ▼  (JSON-RPC to stock_mcp)
[8] stock_mcp.search(ticker="005930", date_range="30d", mode="hybrid")
      │  → runs dense (pgvector HNSW cosine) + BM25 (tsvector) → RRF fusion (k=60)
      │  → returns [{vault_path, excerpt, frontmatter, score}, ...]
      │
      ▼
[9] Claude synthesizes answer, cites vault paths as markdown links
      │
      ▼
[10] user: "이거 내 관심종목 노트에 남겨줘"
      │
      ▼
[11] stock_mcp.add_note(title=..., body=..., tags=["005930", "quarterly-review"])
      │  writes vault/notes/2026-04-16-005930-review.md
      │  marks ingest_status: pending → ingest picks it up on next pass
```

### Idempotency & Transactions

| Concern | Strategy |
|---------|----------|
| **Dedup at fetch** | Collector checks `vault/raw/<source>/...` for existing file with same stable ID (e.g. DART `rcept_no`, URL sha256 for news). Skip if exists and content_hash matches. |
| **Dedup at ingest** | Document primary key = `content_hash` (or stable source ID + hash). Same file twice → no-op. Modified file → delete-write pattern inside one transaction. |
| **Atomic writes to vault** | Always `write tmp → fsync → rename`. Never partial-frontmatter files. |
| **DB transactionality** | One document = one transaction covering documents + chunks + embeddings + edges. Partial failure → rollback, mark `ingest_status: error`. |
| **Backfill** | `ingest rebuild` command: reads vault recursively, re-creates DB from scratch. Required property: DB can be wiped and regenerated from vault alone. |
| **Incremental** | Watchdog (inotify) for near-real-time; fall back to cron scan every N minutes selecting `ingest_status IN (pending, error)` or `content_hash != db_content_hash`. |
| **Deletion** | Deleting a `.md` triggers soft-delete in DB (`documents.deleted_at`) but keeps edges for history. Hard delete only via explicit `ingest gc`. |

---

## 3. Storage Partitioning

### Vault Layout

```
vault/
├── raw/                                # Collector output. Read-only to humans.
│   ├── dart/<YYYY-MM-DD>/<rcept_no>_<ticker>_<report_slug>.md
│   ├── naver/<YYYY-MM-DD>/<ticker>_<slug>.md
│   ├── news/<source>/<YYYY-MM-DD>/<url_sha8>_<slug>.md
│   ├── macro/<YYYY-MM-DD>/<indicator>.md
│   └── krx/<YYYY-MM-DD>/<ticker>_ohlcv.md         # OHLCV as frontmatter + CSV-in-body or link
├── ingested/                           # Post-enrichment views. Symlinks or thin wrappers.
│   ├── by-ticker/<ticker>/<date>_<source>_<slug>.md
│   ├── by-event/<event_type>/<date>_<ticker>.md
│   └── by-date/<YYYY-MM-DD>/<ticker>_<source>.md
├── notes/                              # Human- and Claude-authored.
│   ├── tickers/<ticker>.md             # One canonical page per ticker (like gbrain "compiled truth")
│   ├── themes/<slug>.md
│   └── journal/<YYYY-MM-DD>.md
├── dashboards/                         # Auto-generated, refreshed daily.
│   ├── portfolio.md
│   ├── watchlist.md
│   └── events-this-week.md
├── graph/                              # graphify output.
│   ├── index.md
│   ├── nodes/<cluster>/<slug>.md
│   └── site/                           # static HTML (served locally)
├── templates/                          # Frontmatter templates for each doc type.
└── _state/                             # Run ledger, NOT user-visible in Obsidian (add to .obsidianignore).
    ├── runs.jsonl
    └── last_ingest.json
```

**File-naming rules:**
- Prefer **stable source-ID first** (DART `rcept_no`, news URL hash) so repeated fetches overwrite cleanly.
- Timestamp in path (`YYYY-MM-DD/`) bounds directory size and makes backfill trivially sliceable.
- Ticker in filename where relevant — Obsidian search and `ls` both work.
- `ingested/` uses **symlinks** back to `raw/` when possible (one source of truth on disk) or is a separate thin wrapper file that `![[transcludes]]` the raw one, so edits to the canonical frontmatter propagate.

### What lives where (raw vs ingested vs notes vs dashboards)

| Directory | Writer | Reader | Contains | Mutability |
|-----------|--------|--------|----------|------------|
| `raw/` | collectors | ingest, humans (rarely) | Immutable fetched documents. Minimal frontmatter. | Append-only. |
| `ingested/` | ingest | Obsidian users, stock_mcp | Enriched views of raw docs (symlinks or transclusion). | Rewritten when raw changes. |
| `notes/` | humans, Claude (via MCP) | everyone | Free-form research. One `tickers/<t>.md` per ticker is the canonical evolving page. | Freely edited. |
| `dashboards/` | orchestration | humans | Generated from DB queries. | Fully regenerated each run (idempotent: delete-write). |
| `graph/` | graphify | humans (browser + Obsidian) | Graph snapshot. | Full regen per graphify run. |

### Postgres Schema

```sql
-- Source of truth mirror: every .md file that ingest has seen.
CREATE TABLE documents (
  id              TEXT PRIMARY KEY,           -- content_hash (sha256 of body)
  vault_path      TEXT NOT NULL UNIQUE,       -- relative to vault root
  source          TEXT NOT NULL,              -- dart|naver|news|macro|krx|note
  source_id       TEXT,                       -- rcept_no, url hash, etc.
  ticker          TEXT,                       -- primary ticker if any
  published_at    TIMESTAMPTZ,
  fetched_at      TIMESTAMPTZ,
  ingested_at     TIMESTAMPTZ,
  content_hash    TEXT NOT NULL,
  frontmatter     JSONB NOT NULL,             -- full parsed frontmatter
  title           TEXT,
  lang            TEXT DEFAULT 'ko',
  deleted_at      TIMESTAMPTZ
);
CREATE INDEX ON documents (ticker, published_at DESC);
CREATE INDEX ON documents USING GIN (frontmatter);

-- Chunks: section-aware splits.
CREATE TABLE chunks (
  id              BIGSERIAL PRIMARY KEY,
  document_id     TEXT REFERENCES documents(id) ON DELETE CASCADE,
  ord             INT NOT NULL,
  text            TEXT NOT NULL,
  tsv             tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,
  embedding       vector(1024),               -- bge-m3 dim
  chunk_metadata  JSONB
);
CREATE INDEX ON chunks USING GIN (tsv);
CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);

-- Structured facts lifted out of chunks by ingest LLM.
CREATE TABLE entities (
  id              BIGSERIAL PRIMARY KEY,
  kind            TEXT NOT NULL,              -- ticker|company|person|product|sector|macro_indicator
  canonical_id    TEXT NOT NULL,              -- e.g. KRX:005930
  name            TEXT NOT NULL,
  aliases         TEXT[] DEFAULT '{}',
  metadata        JSONB,
  UNIQUE (kind, canonical_id)
);

-- Graph edges between documents/entities.
CREATE TABLE edges (
  id              BIGSERIAL PRIMARY KEY,
  src_kind        TEXT NOT NULL,              -- document|entity|event
  src_id          TEXT NOT NULL,
  dst_kind        TEXT NOT NULL,
  dst_id          TEXT NOT NULL,
  rel             TEXT NOT NULL,              -- mentions|filed_by|catalyst_for|belongs_to|related_to|cites
  weight          REAL DEFAULT 1.0,
  evidence        JSONB,                      -- {chunk_id, snippet, extracted_at}
  UNIQUE (src_kind, src_id, dst_kind, dst_id, rel)
);
CREATE INDEX ON edges (dst_kind, dst_id);
CREATE INDEX ON edges (src_kind, src_id);

-- Typed events (earnings, dividend, filing, news-event, macro print).
CREATE TABLE events (
  id              BIGSERIAL PRIMARY KEY,
  event_type      TEXT NOT NULL,
  occurred_at     TIMESTAMPTZ NOT NULL,
  ticker          TEXT,
  document_id     TEXT REFERENCES documents(id) ON DELETE SET NULL,
  payload         JSONB NOT NULL              -- event-specific structured fields
);
CREATE INDEX ON events (ticker, occurred_at DESC);
CREATE INDEX ON events (event_type, occurred_at DESC);

-- Ingestion ledger (mirrors vault/_state/runs.jsonl for queryability).
CREATE TABLE ingest_runs (
  id              BIGSERIAL PRIMARY KEY,
  started_at      TIMESTAMPTZ NOT NULL,
  finished_at     TIMESTAMPTZ,
  kind            TEXT NOT NULL,              -- collect|ingest|graphify
  source          TEXT,
  stats           JSONB,
  error           TEXT
);
```

**Structured vs derived:**
- **Structured (from source):** `source`, `source_id`, `published_at`, `ticker`, raw frontmatter keys set by the collector.
- **Derived (by ingest LLM):** `event_type`, `catalysts`, `sentiment`, extracted `entities`, `edges`.
- Rule: if a field is derived, it can be regenerated; mark it with `_derived: true` in frontmatter so humans don't hand-edit it.

### Avoiding vault↔DB drift

1. **Content hash is the contract.** Every document row stores `content_hash`; ingest refuses to write a row whose hash disagrees with the file on disk.
2. **File watcher (primary) + scheduled scan (safety net).** Watchdog catches normal edits; nightly scan catches moves, external edits, and anything the watcher missed.
3. **Reconcile command.** `ingest doctor` lists: (a) files in vault absent from DB, (b) DB rows whose file is missing, (c) hash mismatches. Fixes are explicit, not implicit.
4. **One-way rule.** Ingest writes vault files *only* for frontmatter enrichment. All other vault mutations (user notes, hand edits) are read-only from ingest's perspective.

---

## 4. Ingestion Pipeline Design

### Chunking Strategy

| Doc type | Strategy | Rationale |
|----------|----------|-----------|
| DART filings | Section-aware via heading regex (`^제[0-9]+.`, `^[IVX]+\.`) then 1500–2200 char window inside section | Filings have strong section structure; preserve it. |
| News articles | Title + lead paragraph as chunk 0 (weighted); body by sentence boundaries into ~1500 char chunks | Lead paragraph carries most of the signal. |
| Analyst reports (if full text allowed) | Heading-aware + 2000 char window | Reports are long and sectioned. |
| KRX/macro OHLCV | One chunk = one document (it's tabular). Embedding done on title + summary only. | Numbers embed poorly; queries for "price moves" go through structured `events`/`prices` tables instead. |
| User notes | Markdown heading-aware, 1500 char | Respect the author's structure. |

Target: **1500–2200 chars** (matches bge-m3 sweet spot, avoids truncation at 8k context). Sliding window with **200 char overlap** to preserve cross-boundary context.

### What Gets Extracted (LLM pass)

Per chunk (or per document for small ones):

```json
{
  "tickers": ["005930", "000660"],
  "companies": ["삼성전자", "SK하이닉스"],
  "event_type": "quarterly_earnings" | "guidance" | "m&a" | "dividend" | "rate_decision" | "regulatory" | "product_launch" | "analyst_update" | "macro_print" | "other",
  "numeric_facts": [
    {"label": "매출", "value": 74900000000000, "unit": "KRW", "period": "2026Q1"},
    {"label": "영업이익", "value": 6600000000000, "unit": "KRW", "period": "2026Q1"}
  ],
  "catalysts": ["메모리 가격 반등", "HBM3E 비중 확대"],
  "sentiment": {"score": 0.4, "label": "positive", "rationale": "..."},
  "dates": [{"date": "2026-04-16", "role": "filing"}, {"date": "2026-03-31", "role": "period_end"}],
  "entities": {
    "people": ["한종희"],
    "products": ["HBM3E"],
    "sectors": ["반도체", "메모리"]
  }
}
```

This is merged into document frontmatter (preserving keys already set by the collector) and projected into `entities`/`edges`/`events` tables.

### Graph Edges — How They Form

| Edge (rel) | Source | Destination | When created |
|------------|--------|-------------|--------------|
| `mentions` | document | entity (ticker/company/person/product) | NER pass on every chunk |
| `filed_by` | document (DART) | entity (company/ticker) | From DART metadata |
| `catalyst_for` | event | entity (ticker) | LLM extracts catalyst + target |
| `belongs_to` | entity (ticker) | entity (sector) | From KRX sector mapping (static) |
| `cites` | document (note) | document (any) | From wiki-links `[[...]]` parsed in note body |
| `related_to` | document | document | From shared-ticker + time-proximity heuristic; weight = cosine similarity |
| `affects` | entity (macro_indicator) | entity (sector) | Curated mapping (FX → exporters, rates → banks/REITs) |

### Frontmatter Schema (concrete YAML)

**Collector-emitted minimum** (`vault/raw/dart/...`):

```yaml
---
id: dart_20260416000523
source: dart
source_id: "20260416000523"
source_url: "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260416000523"
ticker: "005930"
corp_code: "00126380"
report_type: "분기보고서"
published_at: 2026-04-16T16:30:00+09:00
fetched_at: 2026-04-16T17:02:11+09:00
content_hash: "sha256:8a9c..."
ingest_status: pending
lang: ko
---
```

**After ingest enrichment**:

```yaml
---
# ── provenance (from collector, never overwritten) ──
id: dart_20260416000523
source: dart
source_id: "20260416000523"
source_url: "https://dart.fss.or.kr/..."
ticker: "005930"
corp_code: "00126380"
report_type: "분기보고서"
published_at: 2026-04-16T16:30:00+09:00
fetched_at: 2026-04-16T17:02:11+09:00
content_hash: "sha256:8a9c..."
lang: ko

# ── ingest state ──
ingest_status: done
ingested_at: 2026-04-16T17:05:44+09:00
ingest_model: "qwen2.5:14b-instruct"
ingest_version: 3
embedding_model: "bge-m3"

# ── derived facts (can be regenerated; do not hand-edit) ──
_derived: true
tickers: ["005930"]
companies: ["삼성전자"]
sectors: ["반도체", "메모리"]
event_type: "quarterly_earnings"
period: "2026Q1"
numeric_facts:
  - {label: "매출", value: 74900000000000, unit: "KRW", period: "2026Q1"}
  - {label: "영업이익", value: 6600000000000, unit: "KRW", period: "2026Q1"}
  - {label: "YoY 영업이익 증가율", value: 0.932, unit: "ratio", period: "2026Q1"}
catalysts:
  - "메모리 가격 반등"
  - "HBM3E 비중 확대"
sentiment: {score: 0.4, label: positive}
entities:
  people: ["한종희"]
  products: ["HBM3E", "DRAM"]
dates:
  - {date: 2026-04-16, role: filing}
  - {date: 2026-03-31, role: period_end}

# ── links (Obsidian-native; also parsed into edges) ──
aliases: ["삼성전자 2026 1분기 실적"]
tags: [source/dart, event/earnings, ticker/005930, sector/반도체]
related:
  - "[[notes/tickers/005930]]"
  - "[[ingested/by-event/quarterly_earnings/2026-04-16_005930]]"
---
```

**Key conventions:**
- `_derived: true` flags that the block below is regenerable; hand-edits will be overwritten on reingest.
- `tags` use hierarchical Obsidian syntax (`ticker/005930`) so Dataview and native search work out of the box.
- `related` uses wiki-link syntax so Obsidian's graph and backlinks panel light up for free.
- `ingest_version` bumps force reingest when the pipeline changes.

---

## 5. stock-mcp Tool Surface

All tools are Python FastMCP decorators. Parameters are typed; docstrings are the contract the LLM reads. Returns are JSON-serializable dicts.

```python
from typing import Literal, Optional
from datetime import date

@mcp.tool()
def search(
    query: str,
    ticker: Optional[str] = None,
    date_range: Optional[str] = None,   # "7d", "30d", "2026-01-01:2026-03-31"
    source: Optional[Literal["dart","naver","news","macro","krx","note"]] = None,
    event_type: Optional[str] = None,
    mode: Literal["hybrid","semantic","bm25"] = "hybrid",
    limit: int = 10,
) -> list[dict]:
    """Hybrid search over vault. Returns [{vault_path, title, excerpt, score, frontmatter, chunk_ord}]."""

@mcp.tool()
def get_ticker(ticker: str) -> dict:
    """Aggregated view for a ticker: canonical note, latest filings, recent events, price summary,
    top catalysts from last 90d, related sectors, top related tickers.
    Returns {ticker, name, sector, canonical_note_path, latest_price, events_30d, catalysts, related_tickers}."""

@mcp.tool()
def list_disclosures(
    ticker: str,
    since: Optional[str] = None,          # ISO date or "30d"
    report_types: Optional[list[str]] = None,
    limit: int = 20,
) -> list[dict]:
    """Chronological DART filings for a ticker. [{rcept_no, report_type, published_at, vault_path, summary}]."""

@mcp.tool()
def list_events(
    ticker: Optional[str] = None,
    event_type: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Typed events timeline. [{event_type, occurred_at, ticker, payload, document_id, vault_path}]."""

@mcp.tool()
def get_prices(
    ticker: str,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> dict:
    """OHLCV from KRX cache. {ticker, rows: [{date, open, high, low, close, volume}], summary}."""

@mcp.tool()
def get_portfolio() -> dict:
    """Parse portfolio dashboard note. {holdings: [{ticker, weight, cost_basis, notes_path}], updated_at}."""

@mcp.tool()
def get_watchlist() -> list[dict]:
    """Parse watchlist dashboard. [{ticker, reason, added_at, last_reviewed}]."""

@mcp.tool()
def related(
    document_id: Optional[str] = None,
    ticker: Optional[str] = None,
    rel: Optional[str] = None,          # "mentions"|"catalyst_for"|"cites"|...
    depth: int = 1,
    limit: int = 20,
) -> list[dict]:
    """Graph traversal. Returns [{src, dst, rel, weight, evidence, vault_path}]."""

@mcp.tool()
def get_document(path_or_id: str) -> dict:
    """Full document with frontmatter and body. {frontmatter, body, vault_path, chunks}."""

@mcp.tool()
def get_macro(
    indicator: Optional[str] = None,     # "KR_BASE_RATE","USDKRW","WTI",...
    since: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Macro indicator time series. [{indicator, date, value, source, vault_path}]."""

@mcp.tool()
def add_note(
    title: str,
    body: str,
    tags: list[str] = [],
    tickers: list[str] = [],
    links: list[str] = [],               # ["[[notes/tickers/005930]]", ...]
    folder: Literal["notes","notes/journal","notes/tickers","notes/themes"] = "notes",
) -> dict:
    """Append a new note to vault. Returns {vault_path, id}. Triggers reingest on next pass."""

@mcp.tool()
def update_ticker_note(
    ticker: str,
    section: str,                        # heading to update or append under
    body: str,
    mode: Literal["append","replace"] = "append",
) -> dict:
    """Structured update to notes/tickers/<ticker>.md. Returns {vault_path, section}."""

@mcp.resource("vault://dashboards/portfolio")
def portfolio_resource() -> str:
    """Live-rendered portfolio dashboard."""

@mcp.resource("vault://graph/index")
def graph_resource() -> str:
    """Current graph snapshot index."""
```

**Design rules followed:**
- One responsibility per tool, typed parameters, descriptive docstrings (FastMCP best practice: the docstring is the LLM contract).
- Write tools limited to `notes/` (and `dashboards/` via orchestration, not MCP).
- Read tools return structured data + `vault_path` so Claude can cite sources.
- Hybrid as default (RRF with k=60), with explicit escape hatches for pure modes.
- Resources (read-only) for things Claude should reference but not call as actions.

---

## 6. Build Order & Phase Boundaries

### Walking Skeleton (smallest proof the architecture works)

**End-to-end thin slice:**
1. One collector (`collect_dart`) fetching one day of 삼성전자 filings.
2. Minimal ingest: hash-check, chunk, bge-m3 embed, tsvector, no LLM enrichment yet.
3. PGLite with the 4 core tables (documents, chunks, entities, edges).
4. FastMCP server with *one* tool: `search(query, mode='hybrid')`.
5. Claude Code query: "What did 삼성전자 disclose this week?" returns a vault_path and excerpt.

Everything else (other collectors, LLM enrichment, graphify, dashboards) plugs into this skeleton.

### Phases

| # | Phase | Entry criteria | Exit criteria | Parallelizable? |
|---|-------|----------------|---------------|-----------------|
| 1 | **Foundations** — repo layout, PGLite bootstrap, vault folders, frontmatter templates, `.obsidianignore` for `_state/` | Project init done | `pytest` green on schema migration + frontmatter parse; `ingest doctor` runs clean on empty vault | No — blocks all others |
| 2 | **Walking skeleton** — `collect_dart`, minimal ingest (no LLM), 1-tool MCP (`search`), RRF hybrid | Phase 1 done | Claude Code can answer "삼성전자 최근 공시" with a real vault citation | No — blocks 3+ |
| 3a | **Collector expansion** — naver, news, macro, krx | Skeleton proves interface | Each collector writes valid frontmatter into `raw/`; idempotent on reruns | **Yes** — parallel per source |
| 3b | **LLM enrichment** — local Ollama+Qwen, entity/event/numeric extraction, `_derived` frontmatter | Skeleton ingest works | Golden-set docs have ≥80% correct structured facts | **Yes** — parallel with 3a |
| 3c | **MCP tool surface** — the full tool list from §5 minus `graph` traversal | Skeleton search works | Each tool has smoke test + Claude Code can invoke it | **Yes** — parallel with 3a/3b |
| 4 | **Graph layer** — edges populated by ingest, `related()` tool, `list_events()` | 3b done (enrichment produces entities) | Graph traversal returns connected docs for a seed ticker | Sequential after 3b |
| 5 | **Dashboards** — portfolio.md, watchlist.md, events-this-week.md auto-gen | 3a + 3c done | Dashboards regenerate deterministically from DB | Parallel with 4 |
| 6 | **graphify integration** — nightly snapshot → `vault/graph/`, static site | 4 done (edges exist) | `graphify` output is Obsidian-browseable + HTML opens in browser | Can defer — not v1-critical |
| 7 | **Orchestration hardening** — retries, failure isolation per source, `ingest doctor`, model-upgrade reingest | 3a/3b done | One dead source doesn't block others; `ingest rebuild` restores DB from vault | Parallel with 5/6 |
| 8 | **Polish** — Dataview queries, better chunking for filings, reranking, cost/latency telemetry | Everything above | Judgment-support queries feel fast and grounded | Defer-friendly |

**Critical path:** 1 → 2 → (3a, 3b, 3c in parallel) → 4 → 5/6/7 in parallel → 8.

**Deferrable without breaking v1:**
- 6 (graphify) — Obsidian's native graph works as a stopgap.
- Part of 8 (rerank, Dataview) — only needed once retrieval quality plateaus.
- `collect_macro` specifics beyond BOK rate + USDKRW — add indicators as they're needed.

---

## 7. Failure Modes & Resilience

| Failure | Detection | Mitigation |
|---------|-----------|------------|
| **Scraper breakage** (site HTML changed) | Collector unit tests with pinned fixtures; production canary check asserts N docs/day; `ingest_runs.stats.count == 0` alert | Isolate per-source failure (orchestration continues other sources). Collector emits `ingest_status: collector_error` stub into `raw/` with raw HTML attached for debugging. |
| **LLM ingest error** (timeout, bad JSON) | Validator on extractor output (pydantic); bad output sets `ingest_status: error` with `ingest_error: {stage, message}` in frontmatter | Retry with backoff (3 tries), then move to error bucket. Nightly retry sweep picks up `ingest_status: error` where `ingest_retry_after < now`. |
| **Embedding drift** (model upgrade) | `embedding_model` + `ingest_version` in frontmatter. Migration script detects mismatch. | `ingest reindex --embedding-model=bge-m3-v2`: re-embed chunks without re-running LLM extraction (separately versioned). |
| **Vault ↔ DB divergence** | `ingest doctor`: set-diff file list vs `documents.vault_path`; hash mismatch check | Three explicit fixes: `--ingest-missing`, `--purge-orphans`, `--reingest-stale`. Dry-run default. |
| **Disk full / atomic write fails** | Collector/ingest catches `OSError`, logs to `_state/runs.jsonl` | Tmp file cleanup on startup; atomic rename only after fsync. |
| **Claude query against empty DB** | MCP tool returns `{results: [], message: "no ingested data — run collectors"}` | Explicit empty-result contract; never silently return stale results. |
| **Concurrent ingest runs** | Advisory lock in PGLite (`pg_advisory_lock`) keyed by `ingest:<source>` | Second run waits or exits with "already running". |
| **robots.txt / rate-limit violation** | Collector respects per-source rate limits; DART has daily quota, KRX has IP-throttle signal | Exponential backoff, daily budget counter in `_state/quotas.json`, hard stop at budget. |

---

## 8. Integration Surfaces with Obsidian

Users consume the system three ways — choose depending on task.

### 8.1 Direct file reading (raw data)

- Users open `vault/raw/dart/2026-04-16/...md` in Obsidian when they want the source text.
- Frontmatter renders as a properties panel.
- Obsidian's native graph view works from day one because collectors emit `[[wiki-links]]` in `related:` and use hierarchical `tags:`.

### 8.2 Auto-generated dashboards (primary daily workflow)

- `vault/dashboards/portfolio.md`, `watchlist.md`, `events-this-week.md` are **fully regenerated** by orchestration from DB queries.
- Start with **plain markdown tables** (works without Dataview, survives the orchestration delete-write cycle).
- Optionally layer **Dataview** queries on top of frontmatter for live filtering ("show me all ticker/005930 notes from last 7d with sentiment=negative") — Dataview reads frontmatter so it composes with the schema in §4.
- Dashboards link to `notes/tickers/<ticker>.md` canonical pages which accrete manual research.

### 8.3 Claude Code + stock-mcp (analytical workflow)

- User asks a question in Claude Code.
- Claude calls `search`, `get_ticker`, `list_events`, `related` and composes an answer with vault citations.
- Claude writes outcomes back via `add_note` / `update_ticker_note` — those land in `notes/` and ingest picks them up.

### llm-wiki plugin fit

- llm-wiki-style "compiled truth above fold / evidence timeline below" is the pattern for `notes/tickers/<ticker>.md`:
  - Top section: LLM-rewritable summary ("compiled truth").
  - Separator (`---` or `<!-- evidence -->`).
  - Append-only timeline of events, filings, and research entries Claude adds.
- If the llm-wiki Obsidian plugin is installed it can read the vault via its own MCP or local API; our stock-mcp is the primary integration point for market-specific queries, so treat llm-wiki as **optional and additive**, not required.

---

## 9. Where graphify Fits

graphify is a **periodic snapshot**, not part of the hot path.

| Question | Decision |
|----------|----------|
| When does it run? | Nightly via orchestration, plus on-demand (`make graphify`). |
| What's the input? | The entire vault (`raw/`, `ingested/`, `notes/`, `dashboards/`). Not the DB — graphify operates on markdown. |
| What's the output? | (a) `vault/graph/` — markdown node pages + `index.md`, Obsidian-readable via `--obsidian`. (b) A static HTML site under `vault/graph/site/` for browser viewing. |
| How does it relate to DB edges? | **Complementary, not duplicate.** DB edges are fine-grained, typed, transactional (for query). graphify clusters/summarizes (for overview). Both draw from the same vault. |
| Does it replace Obsidian's native graph? | No — it augments. Obsidian's graph is link-based; graphify adds LLM-derived semantic clusters (Leiden communities) and summaries. |
| Does ingest depend on graphify? | No. graphify is purely downstream. The system fully works without it — it's Phase 6, deferrable. |
| Is its output committed to git? | The `graph/` markdown pages yes (diff-able). The `graph/site/` HTML: gitignored or committed depending on team preference (small teams: commit; larger: ignore). |

Graphify's `--wiki` mode produces Wikipedia-style articles per cluster, which makes a natural sector-level overview ("반도체 클러스터") while the DB + MCP handle ticker-level precision.

---

## Scaling Considerations

| Scale | Architecture adjustments |
|-------|--------------------------|
| **Solo, dozens of tickers** (today) | PGLite in-process, single-machine cron, Ollama on the same box. No changes needed. |
| **2–5 users, hundreds of tickers** (v1 target) | Move PGLite → Postgres container (shared), keep ingest/collectors per-user or shared. Git-sync the vault. No other changes. |
| **If someone asks to scale further** | Don't. This project's `Out of Scope` explicitly excludes public deployment. If scale is needed, the gbrain 3-layer pattern cleanly splits at the DB boundary — but that's a v3 conversation, not v1. |

### First bottleneck to expect

**Ingest LLM throughput**, not retrieval. bge-m3 embeddings are fast; local 14B extraction model is the slow step. Mitigations in order: (1) batch per day, not per file; (2) skip extraction for doc types where structured metadata is already sufficient (KRX OHLCV, macro prints); (3) fall back to Haiku for overflow days.

---

## Anti-Patterns

### Anti-Pattern 1: Treating the DB as source of truth

**What people do:** Start editing data in DB directly because it's fast.
**Why wrong:** Vault diverges, reconstruction breaks, Obsidian users see stale data, git history lies.
**Do instead:** DB is a cache. Every DB write must originate from a vault file. `ingest rebuild` must fully restore DB from vault.

### Anti-Pattern 2: Collectors that enrich

**What people do:** Have the DART collector also extract numeric facts "while we're at it."
**Why wrong:** Blurs the token-free boundary, couples scraping to extraction, breaks idempotency on model changes.
**Do instead:** Collectors only fetch + write minimal-frontmatter markdown. Ingest is the only enricher.

### Anti-Pattern 3: One monolithic frontmatter block

**What people do:** Mix provenance, derived facts, and user tags in a flat frontmatter.
**Why wrong:** User edits get overwritten on reingest; reingest can't tell what's safe to regenerate.
**Do instead:** Three blocks — provenance (never overwritten), ingest state, `_derived: true` block (regenerable). Keep user-authored tags in `notes/`, not in `raw/` or `ingested/`.

### Anti-Pattern 4: Letting MCP write into `raw/` or `ingested/`

**What people do:** Add a `fix_document` MCP tool that rewrites scraped docs.
**Why wrong:** Makes the vault unreconstructable; next scrape overwrites the fix.
**Do instead:** MCP write tools only touch `notes/`. Corrections to scraped docs happen via separate `corrections/<id>.md` overlays linked in frontmatter.

### Anti-Pattern 5: Real-time hot-path scraping on query

**What people do:** Claude asks "latest on 삼성전자" and the MCP tool scrapes DART live.
**Why wrong:** Expensive, slow, bypasses the vault, defeats the "collection is a batch" architectural boundary.
**Do instead:** Queries hit only the vault/DB. If data is stale, the user runs collectors — or orchestration runs them on schedule.

---

## Integration Points

### External services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| DART (금감원) | `dart-fss` / `OpenDartReader` over REST API | Requires API key; daily quota; respect `rcept_no` as stable ID. |
| KRX | `pykrx` scraper | IP-throttled; add backoff; cache aggressively (market data doesn't change intraday after close). |
| Naver/Daum 증권 | BeautifulSoup scrapers | Brittle — pin fixtures, unit-test per-source parsers, canary check on daily counts. |
| News outlets | RSS first, scrape fallback | Store `source_url`, never mirror full text when license is unclear — summary + link pattern. |
| FRED / ECOS / BOK | Official API clients | Structured data; collector writes one file per indicator per day. |
| Ollama (local LLM) | HTTP `/api/generate`, `/api/embeddings` | In-process; no network dep. Version-pin the model tag. |
| Claude Code | MCP over stdio (local) or SSE (remote) | FastMCP handles transport; stdio simplest for personal setup. |
| graphify | Invoked as subprocess by orchestration | Runs against vault path; no runtime API coupling. |

### Internal boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `collectors/` ↔ `vault/` | Filesystem writes (atomic rename) | Collectors never import ingest; ingest never imports collectors. |
| `ingest/` ↔ `db/` | Parameterized SQL via a thin repo layer | One transaction per document. |
| `ingest/` ↔ `vault/` | File reads + atomic frontmatter rewrites | Ingest reads body, rewrites frontmatter only; body is never mutated. |
| `stock_mcp/` ↔ `db/` | Read-only SQL | No schema changes allowed from MCP. |
| `stock_mcp/` ↔ `vault/` | Reads everywhere; writes only under `notes/` | Enforced by a path-whitelist guard. |
| `orchestration/` ↔ all | Subprocess invocation + `_state/runs.jsonl` ledger | Orchestration does not import domain logic — it calls CLIs. |

---

## Sources

- [GBrain: Garry Tan's Opinionated Knowledge Brain for AI Agents — Vibe Sparking AI](https://www.vibesparking.com/en/blog/ai/openclaw/2026-04-11-gbrain-garry-tan-opinionated-knowledge-brain/)
- [GBrain: Long-term memory for AI agents — Agent Wars](https://agent-wars.com/news/2026-04-11-gbrain-the-memex-built-for-people-who-think-for-a-living)
- [garrytan/gbrain on GitHub](https://github.com/garrytan/gbrain)
- [FastMCP advanced patterns and best practices — DeepWiki](https://deepwiki.com/jlowin/fastmcp/13-advanced-patterns-and-best-practices)
- [How to Build MCP Servers in Python — Firecrawl / FastMCP tutorial](https://www.firecrawl.dev/blog/fastmcp-tutorial-building-mcp-servers-python)
- [PrefectHQ/fastmcp on GitHub](https://github.com/prefecthq/fastmcp)
- [obsidian-graph: Semantic knowledge graph for Obsidian with PostgreSQL+pgvector](https://github.com/drewburchfield/obsidian-graph)
- [Building a retrieval API to search my Obsidian vault](https://laurentcazanove.com/blog/obsidian-rag-api)
- [Building a Hybrid Retriever for 16,894 Obsidian Files — Blake Crosley](https://blakecrosley.com/blog/hybrid-retriever-obsidian)
- [Hybrid Search in PostgreSQL: The Missing Manual — ParadeDB](https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual)
- [Hybrid search with Postgres Native BM25 and VectorChord](https://blog.vectorchord.ai/hybrid-search-with-postgres-native-bm25-and-vectorchord)
- [BAAI/bge-m3 — Hugging Face](https://huggingface.co/BAAI/bge-m3)
- [Graphify on GitHub (safishamsi/graphify)](https://github.com/safishamsi/graphify)
- [Graphify — knowledge graph builder overview](https://graphify.net/)
- [From Karpathy's LLM Wiki to Graphify — Analytics Vidhya](https://www.analyticsvidhya.com/blog/2026/04/graphify-guide/)
- [obsidian-claude-code-mcp on GitHub](https://github.com/iansinnott/obsidian-claude-code-mcp)
- [Obsidian MCP tools — jacksteamdev/obsidian-mcp-tools](https://github.com/jacksteamdev/obsidian-mcp-tools)
- [Korean Stock Market DART & KRX MCP Server — FastMCP listing](https://fastmcp.me/MCP/Details/1279/korean-stock-market-dart-krx)
- [sharebook-kr/pykrx on GitHub](https://github.com/sharebook-kr/pykrx)
- [Idempotent Data Pipeline — Start Data Engineering](https://www.startdataengineering.com/post/why-how-idempotent-data-pipeline/)
- [DocMine — content-hash-based reingest pattern](https://github.com/bcfeen/DocMine)

---
*Architecture research for: Korean stock knowledge base (Obsidian + gbrain + graphify + stock-mcp)*
*Researched: 2026-04-16*
