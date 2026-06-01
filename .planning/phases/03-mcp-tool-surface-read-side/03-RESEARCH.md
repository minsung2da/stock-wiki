# Phase 3: MCP Tool Surface (Read-Side) - Research

**Researched:** 2026-06-01
**Domain:** FastMCP 2.x stdio server + typed Pydantic read tools over Postgres 17 (pgvector + VectorChord-BM25), prompt-injection defense, hybrid RRF retrieval
**Confidence:** HIGH (stack, module structure, error model, path defense, injection defense, get_decision_card, peer_view) / MEDIUM (hybrid_search RRF — depends on infra prerequisites NOT yet built; see Wave 0 Gaps)

## Summary

Phase 3 builds `src/mcp_v2/` — a FastMCP **2.x** stdio server exposing **10 locked read-side tools**, all returning typed Pydantic models (never chunks/blobs), with `run_sql` forbidden and CI-guarded. Almost every implementation detail has a direct, working reference in the v1.0 archive (`archive/llm-wiki-2026-04:src/stock_mcp/` and `src/ingest/`): the RRF k=60 hybrid-search SQL, the WRAP+FLAG prompt-injection module (EN/KO pattern table), the `safe_join` path-traversal defense, the bge-m3 embedder, and the mecab-ko tokenizer. The job is to **port these patterns to the v2.0 whole-body schema** (`filings`/`news`/`notes`) rather than the archive's deleted `chunks`/`documents` tables — Veto #8 forbids the pre-chunking the archive relied on.

The single biggest finding: **hybrid_search has unbuilt infrastructure prerequisites.** Phase 1's `filings`/`news` tables declare `body_tsv` (TSVECTOR) and `body_embedding halfvec(1024)` columns but **leave them NULL** (per the entity_models.py docstring: "Phase 3 fills them"). There is **no `bm25_tokens INT[]` column, no VectorChord-BM25 index, no HNSW index, and no `notes` table at all** in any current migration (0001–0007). So `hybrid_search`, `get_note`, and `list_portfolio`-via-DB each need a Wave-0 migration + embedding/tokenization backfill before the tool can return anything. The other 7 tools (`get_filing`, `search_filings`, `ohlcv_range`, `flow_range`, `peer_view`, `get_decision_card`, `get_briefing`) read existing populated tables and need no new infra.

D-01 changes the archive's error model: the archive caught all exceptions and returned an `{"error": {...}}` dict (never raised). Phase 3 D-01 instead specifies **empty results = normal empty Pydantic model; real failures = typed exceptions** that FastMCP converts to MCP errors. This is *more* idiomatic for FastMCP 2.x — `raise ToolError(...)` is the documented mechanism. Use a `McpToolError` hierarchy raised on bad args / missing entity / DB error; return empty models for "no rows."

**Primary recommendation:** Port the archive's `stock_mcp` structure (server.py + tools/ + models.py + errors.py) to `src/mcp_v2/`, swap the error model to typed-exception/empty-model (D-01), rewrite `hybrid_search` to fuse over whole-body `filings`/`news`/`notes` (not chunks), add a Wave-0 migration (notes table + bm25_tokens + HNSW + BM25 indexes) and an embedding/tokenization backfill, and re-add a `mcp` dependency group pinning `fastmcp>=2.11,<3.0`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01 — 빈결과 = 정상 빈 모델, 실패 = typed 예외.** Normal zero-row results return a normal Pydantic model with empty `list`/`None` fields. Real failures (nonexistent ticker/corp_code, DB error, bad argument) **raise a typed exception** (`McpToolError` hierarchy) which FastMCP converts to an MCP error response. Do NOT collapse "no data" and "error" into the same `None`. Error messages must be specific about which argument is wrong. Each tool's return model MUST be able to represent an empty state (empty collection OK).
- **D-02 — references + snippet only.** `hybrid_search` returns per-match **ID + RRF score + short snippet** only. NO full `body_md`. The agent re-fetches full text via `get_filing(rcept_no)` / `get_note(path)` for the matches it cares about. Return model = `list[SearchHit]` (each: source_type, id/path, rrf_score, snippet, matched source). Snippet length (±N chars) is research/planner discretion.
- **D-03 — always XML-delimiter wrap + flag-on-match, NEVER block, NEVER strip.** All narrative body is wrapped in an XML delimiter on return. If a prefilter pattern matches, do NOT block — attach a warning flag to the return-model metadata (`injection_suspected: true` + match reason) and pass it through. Scope: every tool returning narrative — `get_filing` (body_md), `get_note` (content_md), `hybrid_search` (snippet). Pure-numeric tools (ohlcv/flow/peer) and structured derived fields are NOT in scope. Blocking risks false-negatives (real DART/news disappearing); stripping corrupts source → breaks numeric verbatim checksum (Veto). Concrete prefilter pattern set + XML delimiter format = research/planner discretion.
- **D-04 — sensible defaults + explicit `limit` arg; "caller specifies range" over hard caps.**
  - `ohlcv_range` / `flow_range`: caller MUST specify `from_date`/`to_date` (no hard ceiling — range is caller's responsibility).
  - `search_filings`: default `limit=50`, adjustable via `limit` arg, `filed_at DESC` ordering.
  - `hybrid_search`: default top-10 (after RRF k=60 fusion), `limit` arg allowed.
  - `get_filing` / `get_note` / `get_decision_card`: single-row.

### Claude's Discretion (delegated to planner/research)

1. `src/mcp_v2/` module structure (server.py + tools/ + models.py + errors.py split). Reference archive `src/stock_mcp/` structure; do NOT carry over `search_vault`/`run_sql`.
2. `hybrid_search` snippet length (±N chars) + extraction method (match-window vs body head).
3. Prefilter pattern set + XML delimiter format (injection defense — best-practice research).
4. RRF k=60 implementation detail (k=60 locked by SC#4) + pgvector dense + VectorChord-BM25 combine SQL. Reuse Phase 1/2 `body_tsv` config + `body_emb halfvec(1024)` patterns.
5. `.mcp.json` registration + stdio server boot (Claude Code config / systemd).
6. Each tool's return Pydantic model (must represent empty state — D-01).
7. `peer_view` "동종업종 median PER/PBR/ROE" computation — `entities.sector` grouping + financial source.
8. `get_decision_card` wraps `src/cards/store.get_active` — `view="payload"`(default)|`"both"` via serialize-time `model_dump(exclude=...)`.
9. `get_briefing` implementation timing — briefing rows (`report_type`) are Phase 5. Phase 3 returns an empty model now (D-01); full wiring is Phase 5.

### Deferred Ideas (OUT OF SCOPE)

- `get_briefing` full wiring (Phase 5 produces `report_type` rows + data; Phase 3 returns empty model only).
- decision_cards semantic search (Phase 2 did NOT add `body_embedding` to decision_cards — narrative-search-excluded lock; Phase 4 may `ALTER TABLE` if needed).
- Write-side MCP tools (`save_card` etc.) — read-side only this phase. Phase 4 analysis runner calls `src/cards/store` DIRECTLY (not via MCP).
- write/action tools (KIS orders) — Phase 6+.
- `hybrid_search` over decision_cards/ohlcv/macro_series (Veto #6, SC#4).
- `run_sql` / arbitrary-SQL escape hatch (Veto #7, SC#3).
- DART body pre-chunking (Veto #8 — return whole body_md).
- analysis runner / 3-role debate (Phase 4).
- briefing generation (Phase 5).
- KIS auto-trade (Phase 6).
</user_constraints>

<phase_requirements>
## Phase Requirements

No explicit REQUIREMENTS.md IDs are mapped to Phase 3 (`phase_req_ids = null`). The requirement set is ROADMAP Success Criteria SC#1–5 + CONTEXT.md D-01..D-04.

| ID | Description | Research Support |
|----|-------------|------------------|
| SC#1 | `src/mcp_v2/` new module; FastMCP 2.x stdio server; `.mcp.json` registers it | Module Structure (Discretion #1) + Standard Stack (FastMCP) + `.mcp.json` (Discretion #5) |
| SC#2 | 10 tools, all return Pydantic models (no chunks) | Tool-by-Tool table + per-tool model designs (Discretion #6) |
| SC#3 | `run_sql` / arbitrary-SQL tool FORBIDDEN (CI guard) | CI Guard pattern (Pitfall + Validation Architecture) |
| SC#4 | `hybrid_search` narrative-only (`filings.body_md`/`news.body_md`/`notes.content_md`); NOT ohlcv/macro_series/decision_cards | hybrid_search RRF section (Discretion #4) + Wave 0 prerequisites |
| SC#5 | All tools pass body through prompt-injection defense (XML delimiter + pattern prefilter) | Prompt-Injection Defense section (Discretion #3) |
| D-01 | empty model vs typed exception | Error Model section + `McpToolError` hierarchy |
| D-02 | references + snippet, not blobs | hybrid_search return shape (`SearchHit`) |
| D-03 | WRAP + FLAG, never block/strip | Prompt-Injection Defense section |
| D-04 | defaults + explicit `limit` | Per-tool signatures + limit handling |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Tool dispatch / JSON-RPC over stdio | MCP server (`src/mcp_v2/server.py`) | — | FastMCP owns transport + schema generation |
| Typed query of numeric tables (ohlcv/macro) | Database / Storage | MCP tool wrapper | Veto #6 — numbers stay typed SQL, never embeddings |
| Narrative retrieval (hybrid RRF) | Database / Storage (pgvector+BM25) | Python (embed query, tokenize, fuse-or-let-SQL-fuse) | RRF fusion can run entirely in SQL CTE (archive pattern) |
| Query embedding (bge-m3) | Python in-process (sentence-transformers) | — | CLAUDE.md §4 locks in-process embedding, no LLM server |
| Korean tokenization (mecab-ko) | Python in-process | — | BM25 needs content-POS INT[] tokens |
| decision_card read + view projection | `src/cards/store.get_active` (existing) | MCP tool serialize-time `exclude` | Veto #13 layering already designed in Phase 2 |
| Prompt-injection wrap+flag | Python leaf util (`src/mcp_v2/injection.py`) | every narrative-returning tool | Pure function, DB/LLM-free (archive `injection_defense.py`) |
| Path-traversal defense (get_note) | Python leaf util (`safe_resolve`) | — | Filesystem boundary, not DB |
| portfolio parse (list_portfolio) | `src/shared/portfolio.py` (existing) | MCP tool wrapper | `Portfolio.load(repo_root)` already exists |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastmcp` | `>=2.11,<3.0` (latest 2.x = **2.14.7**) | MCP server framework; `@mcp.tool` decorator, stdio transport, `ToolError`, auto JSON-schema from type hints | `[VERIFIED: PyPI]` Established (jlowin/PrefectHQ); archive pinned exactly this range. `[CITED: gofastmcp.com/servers/tools]` Pydantic-model returns → structured output automatically. |
| `sqlalchemy` | `>=2.0,<3` | Typed `text()` parameterized SQL (Veto #7) | Already in `db` group; store.py uses it |
| `psycopg[binary]` | `>=3.2` | Postgres driver | Already in `db` group |
| `pydantic` | `>=2.13,<3` | Tool return models + arg validation | Already a core dep; DecisionCard uses it |
| `sentence-transformers` | `>=3.0` (latest **5.5.1**) | bge-m3 1024-d query embedding (in-process) | `[VERIFIED: PyPI]` archive `ingest` group; CLAUDE.md §4 lock |
| `python-mecab-ko` | `>=1.3,<2` (latest **1.3.7**) | Korean content-POS tokenization → INT[] for BM25 | `[VERIFIED: PyPI]` archive `ingest` group; import name is `mecab` |
| `pgvector` | `>=0.4` | psycopg vector adapter (optional — archive formats vectors as literals) | archive `mcp`/`ingest` groups |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `transformers` | `>=4.44` | bge-m3 backbone (pulled by sentence-transformers) | Only if pinning explicitly for reproducibility |
| `pyyaml` | `>=6.0` | portfolio.md frontmatter parse | Already core; `Portfolio.load` uses it |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| FastMCP 2.x | FastMCP 3.x (3.3.1) | 3.x is mostly backward-compatible (`@mcp.tool`/`run()`/`ToolError` unchanged) but ROADMAP SC#1 + CONTEXT lock "FastMCP 2.x". `[CITED: jlowin.dev/blog/fastmcp-3]` only breaking changes are constructor-kwarg removal + repo move + tasks-as-optional-extra. **Recommendation: honor the lock — pin `>=2.11,<3.0`.** Revisit 3.x only via a future explicit decision. |
| in-process bge-m3 | API embedding service | CLAUDE.md §4 explicitly locks in-process sentence-transformers; no LLM server. Do NOT introduce one. |
| RRF in SQL CTE | RRF in Python after two queries | SQL CTE (archive pattern) is one round-trip and keeps the `_RRF_K=60` constant in one place; Python fusion is simpler to unit-test. Either honors SC#4. Recommend SQL CTE per archive precedent. |

**Installation (re-add deleted groups to pyproject.toml):**
```toml
[dependency-groups]
mcp = [
    "fastmcp>=2.11,<3.0",
    "psycopg[binary]>=3.2",
    "pgvector>=0.4",
    "sqlalchemy>=2.0,<3",
]
ingest = [   # embedding/tokenization backfill for hybrid_search Wave 0
    "sentence-transformers>=3.0",
    "transformers>=4.44",
    "python-mecab-ko>=1.3,<2",
    "pgvector>=0.4",
]
```
Note: CI (`.github/workflows/ci.yml` line 43) ALREADY references `--group ingest --group mcp` — those groups were deleted from pyproject.toml in the shutdown, so CI currently fails on `uv sync` until Phase 3 re-adds them. Re-adding closes that gap.

**Version verification:** `[VERIFIED: PyPI 2026-06-01]` `fastmcp` 3.3.1 latest (2.x latest 2.14.7); `sentence-transformers` 5.5.1; `python-mecab-ko` 1.3.7; `mcp` (low-level SDK) 1.27.2.

## Package Legitimacy Audit

> slopcheck 0.6.1 was installed and run in `scan --pkg pypi --json` mode against all three new packages.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `fastmcp` | PyPI | est. ~2 yr (v0.1 → 3.3.1) | high | github.com/PrefectHQ/fastmcp (moved from jlowin/fastmcp) | `OK` (no flags) | Approved |
| `sentence-transformers` | PyPI | est. 5+ yr | very high | github.com/UKPLab/sentence-transformers | `OK` (no flags) | Approved |
| `python-mecab-ko` | PyPI | est. 4+ yr | moderate | github.com/jonghwanhyeon/python-mecab-ko | `OK` (info flag only) | Approved |

**slopcheck note:** `python-mecab-ko` carries a single `info`-severity flag: `HALLUCINATION_PATTERN — "Name starts with 'python-' ... LLM bait but package is established."` This is informational only (established package); no action needed.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

All three are `[VERIFIED: PyPI registry]` per slopcheck `OK` AND prior project use (archive `ingest`/`mcp` groups already depended on them). No new postinstall risk (Python wheels, no npm postinstall).

## Architecture Patterns

### System Architecture Diagram

```
Claude Code (.mcp.json registers stdio server)
        │  spawn:  .venv python -m mcp_v2  (stdio JSON-RPC)
        ▼
┌───────────────────────────────────────────────────────────┐
│  src/mcp_v2/server.py  — FastMCP("stock-mcp-v2")            │
│  - imports tools/* (side-effect @mcp.tool registration)     │
│  - mcp.run()  (stdio transport)                             │
└───────┬─────────────────────────────────────────────────────┘
        │  tool call (typed args, Pydantic-validated)
        ▼
┌───────────────────────────────────────────────────────────┐
│  tools/*.py  — one callable per tool, returns Pydantic model│
│  on bad arg / missing entity / DB error → raise McpToolError│
│  on zero rows                           → return empty model│
└───┬───────────────┬───────────────┬───────────────┬─────────┘
    │ numeric        │ narrative      │ card           │ disk
    ▼                ▼                ▼                ▼
ohlcv/macro     filings/news/notes  cards.store    notes/private/
(typed SQL)     RRF: dense(pgvector  .get_active    safe_resolve +
                 HNSW) + BM25        (existing)     Portfolio.load
                 (VectorChord)                       (existing)
                 ──fuse k=60──►SearchHit[]
                       │
                       ▼ narrative bodies/snippets
              ┌───────────────────────────┐
              │ injection.wrap_untrusted() │  ← WRAP every narrative
              │ injection.detect()         │  ← FLAG on match (D-03)
              │  → XML delimiter + flag     │     never block / strip
              └───────────────────────────┘
                       │
                       ▼  typed Pydantic model (structured output)
                  back to Claude Code
```

### Recommended Project Structure (Discretion #1)

Port the archive `stock_mcp` layout, drop `search_vault`/`run_sql`/`graph_*`/`overview`/`related`, add the v2.0 tools and an injection leaf module:

```
src/mcp_v2/
├── __init__.py          # exports mcp (the FastMCP instance) + tool callables
├── __main__.py          # entry point: _check_db_connection() then mcp.run() (stdio)
├── server.py            # FastMCP("stock-mcp-v2"); side-effect imports tools/*
├── errors.py            # McpToolError hierarchy (D-01) — raised, not returned
├── models.py            # return Pydantic models (FilingDetail, FilingHit, OhlcvBar,
│                        #   FlowRow, PeerView, SearchHit/SearchResult, NoteContent,
│                        #   CardView, Portfolio passthrough, Briefing) — each empty-able
├── injection.py         # wrap_untrusted() + detect_injection_patterns() (WRAP+FLAG, D-03)
├── retrieval.py         # hybrid_search RRF core (dense + BM25 + k=60 CTE) + snippet
├── embedding.py         # bge-m3 query encoder (lazy singleton + LRU cache) [Wave 0]
├── tokenizer.py         # mecab-ko → INT[] (content POS) [Wave 0]
├── paths.py             # safe_resolve(repo_root, path) read-only whitelist (get_note)
└── tools/
    ├── __init__.py
    ├── filing.py        # get_filing, search_filings
    ├── market.py        # ohlcv_range, flow_range, peer_view  (pure numeric, no injection)
    ├── search.py        # hybrid_search  (+ registers the shared mcp instance, like archive)
    ├── note.py          # get_note  (path-traversal defense + injection wrap)
    ├── card.py          # get_decision_card  (wraps cards.store.get_active)
    ├── portfolio.py     # list_portfolio  (wraps shared.portfolio.Portfolio.load)
    └── briefing.py      # get_briefing  (Phase-3: empty model; Phase-5 wires data)
```

Rationale vs alternatives: a single `server.py` with all tools inline is simpler but the archive's per-tool module split is already proven, keeps each tool independently testable, and mirrors Phase 2's `src/cards/` (models.py + store.py separation). Keep `embedding.py`/`tokenizer.py`/`retrieval.py` as siblings (not under tools/) because the Wave-0 backfill job also imports them outside the MCP context.

### Pattern 1: Typed tool returning a Pydantic model (structured output)
**What:** Annotate the return type with a Pydantic model; FastMCP auto-generates the output schema and emits structured content.
**When to use:** Every Phase 3 tool.
```python
# Source: [CITED: gofastmcp.com/servers/tools]
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

mcp = FastMCP("stock-mcp-v2")

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def ohlcv_range(ticker: str, from_date: str, to_date: str) -> OhlcvRange:
    """Daily OHLCV+flow for a ticker over [from_date, to_date]. Pure numeric."""
    ...
    return OhlcvRange(ticker=ticker, bars=[...])   # bars=[] is a VALID empty result (D-01)
```
All Phase 3 tools are read-only → set `ToolAnnotations(readOnlyHint=True)`.

### Pattern 2: Error model — empty model vs typed exception (D-01)
**What:** Zero rows → return a normal model with an empty collection. A genuine fault → `raise McpToolError(...)`; FastMCP converts it to an MCP error.
**When to use:** Every tool.
```python
# errors.py — D-01 typed exception hierarchy. FastMCP surfaces ToolError messages
# to the client; subclassing ToolError keeps the message visible (no masking needed).
from fastmcp.exceptions import ToolError

class McpToolError(ToolError):
    """Base for all stock-mcp-v2 tool faults (bad arg, missing entity, DB error)."""

class InvalidArgument(McpToolError): ...   # e.g. ticker not ^[0-9]{6}$
class EntityNotFound(McpToolError): ...     # ticker/corp_code resolves to nothing
class FilingNotFound(McpToolError): ...     # get_filing(rcept_no) — no such row
class NotePathForbidden(McpToolError): ...  # get_note path outside whitelist
class DataBackendError(McpToolError): ...   # DB unreachable / query failure
```
```python
# in a tool:
ent = resolve_entity(engine, ticker)
if ent is None:
    raise EntityNotFound(f"ticker {ticker!r} not found in entities")   # LOUD (D-01)
rows = conn.execute(_OHLCV_SQL, {...}).all()
return OhlcvRange(ticker=ticker, bars=[_to_bar(r) for r in rows])      # [] is NORMAL
```
**Critical distinction from the archive:** the archive's `to_error_response()` returned an `{"error":{...}}` dict and *never raised* (because it ran a raw stdio loop where a traceback would corrupt JSON-RPC). FastMCP 2.x handles that conversion itself — `raise ToolError(...)` is the documented path `[CITED: gofastmcp.com/servers/tools]`. Do NOT resurrect the dict-return pattern. Set `FastMCP(..., mask_error_details=True)` so any *non*-`ToolError` exception (an unexpected bug) shows a generic message, while `McpToolError` messages stay specific (D-01 "tell the caller what to fix").

### Pattern 3: Argument validation up front
**What:** Validate ticker/corp_code shape with the existing regexes BEFORE touching the DB (matches `entity.py` D-12 discipline).
```python
import re
_TICKER_RE = re.compile(r"^[0-9]{6}$")      # ASCII-only (str.isdigit accepts superscripts)
_CORP_CODE_RE = re.compile(r"^[0-9]{8}$")
if not _TICKER_RE.match(ticker):
    raise InvalidArgument("ticker must be 6 ASCII digits")
```

### Anti-Patterns to Avoid
- **`run_sql` / any free-form SQL tool** — Veto #7, SC#3. CI guard required (below).
- **Returning chunks / sliced body** — Veto #8 / D-02. `get_filing` returns whole `body_md`; `hybrid_search` returns snippet+ref only.
- **`hybrid_search` over ohlcv/macro_series/decision_cards** — Veto #6, SC#4. Narrative tables only.
- **f-string SQL interpolation** — every statement is a module-level `text()` constant bound with params (store.py / entity.py precedent).
- **Blocking or stripping on injection match** — D-03 WRAP+FLAG only.
- **Re-adding the archive's `{"error":...}` dict return** — use `raise ToolError` (FastMCP idiom).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Path-traversal defense for `get_note` | custom `..`/symlink string checks | `Path.resolve()` + `is_relative_to(whitelist_root)` (archive `paths.safe_join` pattern, read-only variant) | resolve() collapses `..` AND follows symlinks before the whitelist check — string checks miss symlink escapes |
| portfolio.md parsing | new YAML parser in the tool | `src/shared/portfolio.py::Portfolio.load(repo_root)` (EXISTS) | Already validated (Pydantic `extra='forbid'`, ticker regex); `list_portfolio` just wraps it |
| decision_card payload/both projection | re-query DB per view | `cards.store.get_active` + serialize-time `model_dump(exclude=...)` | Phase 2 *designed* get_active to return the full typed card so view is a serialize-time exclude (Veto #13 layering) |
| RRF fusion | bespoke ranking math | port archive `search_core.py` RRF k=60 CTE (adapt to whole-body tables) | Proven SQL; `1.0/(k+rank)` summed over FULL OUTER JOIN |
| Korean tokenization | regex word-split | `python-mecab-ko` content-POS → BLAKE2s INT[] (archive `tokenizer.py`) | mecab segments Korean correctly; josa/endings dropped; same fn at index+query time |
| query embedding | new model load logic | archive `embedder.py` lazy singleton + LRU(256) `encode_query` | bge-m3 load is expensive; cache query vectors |
| prompt-injection wrap/flag | inline string scan | archive `injection_defense.py` PATTERNS + `wrap_untrusted` | EN+KO pattern table already curated; attribute-safe XML delimiter |
| MCP tool schema / JSON-RPC | hand-rolled JSON-RPC loop | FastMCP `@mcp.tool` + `mcp.run()` | Auto schema-gen from type hints; stdio transport built-in |

**Key insight:** ~90% of Phase 3 is *porting* battle-tested archive code to the v2.0 whole-body schema and swapping the error model to D-01. The genuinely new work is the Wave-0 infra (notes table + BM25/HNSW indexes + embedding backfill) and the CI guard.

## Runtime State Inventory

> Phase 3 is greenfield code (new `src/mcp_v2/`), but it DEPENDS on runtime state that does not yet exist. This inventory flags prerequisites the planner must schedule in Wave 0.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `filings.body_tsv` and `filings.body_embedding` / `news.*` columns EXIST but are **NULL** (Phase 1 collectors never populate them — entity_models.py docstring: "Phase 3 fills them"). No `bm25_tokens` column at all. | **Wave 0 backfill job**: tokenize body_md → bm25_tokens INT[], embed body_md → body_embedding halfvec(1024), populate body_tsv. Without it `hybrid_search` returns empty for all queries. |
| Live service config | `.mcp.json` does NOT exist (deleted in shutdown; CLAUDE.md says "Phase 3 완료 시 재생성"). | **Create `.mcp.json`** registering the stdio server (Discretion #5). |
| OS-registered state | None — no systemd unit / scheduled task references mcp_v2 yet. | None (Phase 9 owns scheduling). |
| Secrets/env vars | `DATABASE_URL` (read by `db.engine.get_engine()` via `os.environ["DATABASE_URL"]`, fail-fast). No new secret. | Ensure `.mcp.json` env passes `DATABASE_URL` to the spawned server process. |
| Build artifacts / installed packages | `.venv` has NO `fastmcp`/`sentence-transformers`/`mecab` installed (verified — site-packages empty of them). pyproject.toml has NO `mcp`/`ingest` groups (deleted), yet CI references them. | **Re-add `mcp` + `ingest` dependency groups** to pyproject.toml; `uv sync` to install. |

**Schema prerequisites NOT present in migrations 0001–0007 (verified by reading every migration):**
- **No `notes` table.** The redesign §2 sketch shows `notes(path PK, corp_code, updated_at, content_md, content_emb halfvec(1024))` but **no migration creates it.** `get_note` and `hybrid_search`-over-notes require a new migration (0008) creating it. (`get_note` could alternatively read `notes/private/*.md` from disk directly — see get_note section.)
- **No `bm25_tokens INT[]` column** on `filings`/`news` and **no VectorChord-BM25 index** (`USING bm25`). The archive added these on `chunks` in migration 0002 (now deleted/dormant). Phase 3 needs a migration adding them to `filings`/`news`/`notes`.
- **No HNSW index** on `filings.body_embedding` / `news.body_embedding`.
- `body_tsv` exists but is the SC#6 *fallback* path only (config `'simple'`, not `'korean'` — PG17 has no korean tsearch config; see Pitfall 1). BM25 is the real Korean sparse path.

## Common Pitfalls

### Pitfall 1: `to_tsvector('korean', ...)` hard-fails — there is no Korean config in PG17
**What goes wrong:** Using a `'korean'` text-search config (e.g. in a generated `body_tsv` or query) errors at runtime.
**Why it happens:** PostgreSQL 17 ships no Korean tsearch config; `scripts/init-extensions.sql` installs only `vector` / `vchord_bm25` / `pg_trgm`. Migration 0007 explicitly uses `'simple'` for this reason.
**How to avoid:** Korean morphological tokenization happens in **Python (mecab-ko → INT[])** feeding **VectorChord-BM25**, NOT Postgres tsearch. Use `body_tsv('simple')` only as an SC#6 fallback. `[CITED: src/db/migrations/versions/0007_decision_cards.py lines 36-41]`

### Pitfall 2: pgvector 0.8 filtered HNSW scan loses recall without a session GUC
**What goes wrong:** Hybrid search with structured filters (corp_code/date) returns too few dense hits.
**Why it happens:** pgvector 0.8 HNSW with a pre-filter needs `SET hnsw.iterative_scan = 'relaxed_order'` per connection.
**How to avoid:** Issue `SET hnsw.iterative_scan = 'relaxed_order'` per session in `retrieval.py` before the hybrid query (archive `search_core.py` `_SESSION_SET_ITERATIVE_SCAN`). `[VERIFIED: archive search_core.py]`

### Pitfall 3: NULL filter params cause `AmbiguousParameter` in psycopg3
**What goes wrong:** A bind param that only appears in `:x IS NULL` predicates can't have its type inferred → psycopg3 raises `AmbiguousParameter`.
**Why it happens:** Optional filters (corp_code/source/date) are NULL when unused.
**How to avoid:** Cast every nullable filter param explicitly: `(CAST(:corp_code AS char(8)) IS NULL OR ...)`. `[VERIFIED: archive search_core.py _FILTER_WHERE]`

### Pitfall 4: VectorChord-BM25 score is NEGATIVE (more negative = more relevant)
**What goes wrong:** Sorting BM25 results ascending/descending wrong inverts ranking.
**Why it happens:** `<&>` / `search_bm25query` returns a negative score by design. `[CITED: blog.vectorchord.ai]`
**How to avoid:** When converting BM25 results to a *rank* for RRF, order by score `ASC NULLS LAST` (archive does exactly this), then RRF uses `1.0/(60+rank)` so sign is irrelevant downstream.

### Pitfall 5: `body_md` is whole-document — embedding a 200K-char 사업보고서 as one 1024-d vector dilutes recall
**What goes wrong:** Veto #8 forbids pre-chunking, but a single bge-m3 vector over a giant filing body is a weak retrieval signal.
**Why it happens:** bge-m3 has an 8K-token context; a full 사업보고서 far exceeds it and gets truncated.
**How to avoid (decision for planner):** Two honest options — (a) embed a **truncated head / title+summary** of `body_md` into `body_embedding` (lossy but Veto-compliant, simple); (b) keep a **sibling chunk-view table** for embeddings only (CLAUDE.md Veto #8 explicitly allows "chunk view in a sibling table" — "DART 본문 pre-chunking 금지; 전체 body_md 저장; chunk view는 sibling 테이블에"). **Option (b) is the Veto-sanctioned path** and matches CLAUDE.md's exact wording, but is more infra. BM25 (full body, no truncation) carries most of the Korean keyword recall regardless. `[CITED: CLAUDE.md Hard Veto #8]` — flag as Open Question.

### Pitfall 6: CI already references deleted dependency groups → `uv sync` fails today
**What goes wrong:** `.github/workflows/ci.yml` line 43 runs `uv sync --group collectors --group ingest --group mcp --group db --group dev`, but `ingest`/`mcp` groups were deleted from pyproject.toml.
**How to avoid:** Re-add both groups in Wave 0 (see Installation). `[VERIFIED: .github/workflows/ci.yml + pyproject.toml]`

### Pitfall 7: stdio server must NOT print to stdout
**What goes wrong:** Any `print()` / logging to stdout corrupts the JSON-RPC protocol stream.
**How to avoid:** All logging to **stderr** (CLAUDE.md convention: "로그는 stderr; 사용자 출력은 stdout JSON" — but for an MCP stdio server, stdout is the protocol, so ALL diagnostic logging goes to stderr). FastMCP handles protocol stdout; your code logs via `logging` to stderr only.

## Code Examples

### hybrid_search RRF k=60 over whole-body tables (Discretion #4, SC#4, D-02)
Adapt the archive `search_core.py` CTE. Key change: fuse over **whole-body narrative tables** (`filings`/`news`/`notes`), NOT the deleted `chunks`/`documents`. Each candidate is one whole filing/article/note (Veto #8 — no chunks). Below is a per-table skeleton (run per requested source, or UNION the candidate sets); RRF in SQL:

```python
# Source: adapted from [VERIFIED: archive src/stock_mcp/search_core.py]
import sqlalchemy as sa

_RRF_K = 60  # SC#4 LOCKED — do not parameterize away

_SET_ITERATIVE_SCAN = sa.text("SET hnsw.iterative_scan = 'relaxed_order'")  # Pitfall 2

# Per narrative source. :qvec = bge-m3 query vector literal; :qtoks = mecab INT[].
# NULL filters CAST-guarded (Pitfall 3). LIMIT 50 candidates each side, RRF, top_k.
_HYBRID_FILINGS_SQL = sa.text("""
WITH dense AS (
    SELECT f.rcept_no AS id,
           ROW_NUMBER() OVER (ORDER BY f.body_embedding <=> CAST(:qvec AS halfvec)) AS rk
    FROM filings f
    WHERE f.body_embedding IS NOT NULL
      AND (CAST(:corp_code AS char(8)) IS NULL OR f.corp_code = CAST(:corp_code AS char(8)))
      AND (CAST(:date_from AS date) IS NULL OR f.filed_at >= CAST(:date_from AS date))
      AND (CAST(:date_to   AS date) IS NULL OR f.filed_at <  CAST(:date_to   AS date))
    ORDER BY f.body_embedding <=> CAST(:qvec AS halfvec)
    LIMIT 50
),
sparse AS (
    SELECT f.rcept_no AS id,
           ROW_NUMBER() OVER (
             ORDER BY (f.bm25_tokens)::bm25_catalog.bm25vector
                      <&> bm25_catalog.to_bm25query('ix_filings_bm25'::regclass,
                            CAST(:qtoks AS int[])::bm25_catalog.bm25vector) ASC NULLS LAST
           ) AS rk
    FROM filings f
    WHERE f.bm25_tokens IS NOT NULL
      AND (CAST(:corp_code AS char(8)) IS NULL OR f.corp_code = CAST(:corp_code AS char(8)))
      AND (CAST(:date_from AS date) IS NULL OR f.filed_at >= CAST(:date_from AS date))
      AND (CAST(:date_to   AS date) IS NULL OR f.filed_at <  CAST(:date_to   AS date))
    LIMIT 50
)
SELECT COALESCE(dense.id, sparse.id) AS id,
       COALESCE(1.0/(:k + dense.rk), 0) + COALESCE(1.0/(:k + sparse.rk), 0) AS rrf_score
FROM dense FULL OUTER JOIN sparse USING (id)
ORDER BY rrf_score DESC
LIMIT :top_k
""")
```
Notes:
- `<&>` is the VectorChord-BM25 0.2 score operator; the archive used `bm25_catalog.search_bm25query(...)` — **verify which API the project's pinned vchord image (`tensorchord/vchord-suite:pg17-latest`) exposes** by checking the archive migration 0002 (`search_bm25query` + `bm25_ops`) which is what was tested against this exact image. Use whichever the image supports. `[VERIFIED: archive 0002 used search_bm25query/bm25_ops]`
- `<=>` distance operator works on `halfvec` (cosine via `halfvec_cosine_ops` HNSW index).
- For `source_filter`, run only the requested source's CTE; for "all narrative", run filings+news+notes and union candidate rows into one RRF (each carries a `source_type` tag).
- After RRF, fetch snippet+id per hit (see snippet pattern) → `SearchHit` (NO body_md, D-02).

### hybrid_search snippet extraction (Discretion #2)
**Recommendation:** default snippet = **±200 chars match-window** (≈first BM25 match offset ± 200), falling back to **body head (first 300 chars)** when no literal match offset is available (pure-dense hit).
**Why:** A match-centered window is far more informative than a fixed head for "is this candidate relevant?" decisions, and 200 chars (~60–100 Korean chars of context each side) is enough to judge relevance while staying well under token budget (D-02 references-not-blobs). Postgres `ts_headline` is an option but uses tsearch (`'simple'` — weak for Korean) and re-tokenizes; a Python match-window over the already-fetched body head is simpler and locale-correct. Wrap the snippet in the injection XML delimiter (D-03).
```python
def make_snippet(body_md: str, query_terms: list[str], width: int = 200) -> str:
    lo = min((body_md.find(t) for t in query_terms if body_md.find(t) >= 0), default=-1)
    if lo < 0:
        return body_md[:300]
    start = max(0, lo - width)
    return body_md[start:lo + width]
```

### Prompt-injection WRAP + FLAG (Discretion #3, D-03, SC#5)
Port archive `src/ingest/injection_defense.py` into `src/mcp_v2/injection.py`. The archive *gated* (skipped adversarial); Phase 3 D-03 says **never block, never strip — wrap + flag and pass through**.
```python
# Source: [VERIFIED: archive src/ingest/injection_defense.py]
import re

# Stable IDs — EN + KO instruction-override / role-injection / fake-tag patterns.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EN_IGNORE_PREV",  re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|prompts|rules)", re.I)),
    ("FAKE_SYSTEM_TAG", re.compile(r"</?(?:system|assistant|user|instructions|prompt)\s*>", re.I)),
    ("DAN_MODE",        re.compile(r"\b(?:DAN\s*mode|jailbreak|developer\s+mode)\b", re.I)),
    ("ROLEPLAY_ADMIN",  re.compile(r"(?:role[-\s]?play\s+as|pretend\s+(?:you\s+are|to\s+be))\s+(?:admin|root|system)", re.I)),
    ("KO_IGNORE_PREV",  re.compile(r"이전\s*(?:지시|프롬프트)\s*무시")),
    ("KO_ADMIN_MODE",   re.compile(r"관리자\s*모드|시스템\s*프롬프트\s*출력")),
    # Consider adding: tool/role injection ("you are now", "system:"), base64/markdown-link
    # exfil hints, "###" header spoofing. Snapshot the ID list in a test (archive did).
]
_SAFE_ATTR = re.compile(r"^[A-Za-z0-9_:.-]+$")

def detect(body: str) -> list[dict]:
    hits = []
    for pid, rx in PATTERNS:
        for m in rx.finditer(body):
            hits.append({"pattern_id": pid, "match": m.group(0)[:80], "span": [m.start(), m.end()]})
    return sorted(hits, key=lambda h: h["span"][0])

def wrap_untrusted(body: str, source: str, ref_id: str) -> str:
    # XML delimiter — boundary marker for downstream LLM, NOT enforcement. NEVER strip body.
    if not _SAFE_ATTR.match(source) or not _SAFE_ATTR.match(ref_id):
        raise ValueError("invalid delimiter attribute")  # info-disclosure guard
    return f'<untrusted source="{source}" ref="{ref_id}">\n{body}\n</untrusted>'
```
Return-model integration (every narrative tool — `get_filing`, `get_note`, `hybrid_search` snippets):
```python
flags = detect(body_md)
return FilingDetail(
    rcept_no=rcept_no,
    body_md=wrap_untrusted(body_md, "dart", rcept_no),   # WRAP (D-03)
    injection_suspected=bool(flags),                      # FLAG (D-03) — NEVER block
    injection_flags=[h["pattern_id"] for h in flags],
    ...
)
```
**XML delimiter format recommendation:** use a distinctive, namespaced tag `<untrusted source="..." ref="...">…</untrusted>` (low collision risk; carries provenance). `[CITED: gocodeo.com / dev.to delimiter-defense]` wrapping untrusted content in explicit unique XML delimiters + a model instruction to treat the contents as data yields ~95% defense on current models vs ~60% baseline. The delimiter is a *boundary marker, not enforcement* — the FLAG metadata is what makes it auditable per D-03.

### get_decision_card view projection (Discretion #8, Veto #13)
```python
# cards.store.get_active returns a FULL typed DecisionCard (payload + body_md + status).
# View is a SERIALIZE-TIME exclude — no re-query (Veto #13 layering, Phase-2 designed).
from cards import get_active  # src/cards/store.py

def get_decision_card(corp_code: str, latest: bool = True, view: str = "payload"):
    if not _CORP_CODE_RE.match(corp_code):
        raise InvalidArgument("corp_code must be 8 ASCII digits")
    card = get_active(get_engine(), corp_code)
    if card is None:
        return CardView(corp_code=corp_code, found=False)   # D-01 empty model, NOT an error
    if view == "payload":
        data = card.model_dump(mode="json", exclude={"body_md"})   # Veto #13 default
    elif view == "both":
        data = card.model_dump(mode="json")                        # includes body_md
        # body_md is narrative → wrap+flag (D-03)
    else:
        raise InvalidArgument("view must be 'payload' or 'both'")
    return CardView(corp_code=corp_code, found=True, card=data)
```
**Verified against the actual model:** `DecisionCard` (src/cards/models.py) has `body_md: str` as a top-level field, and `_PAYLOAD_EXCLUDE = {"body_md","status","invalidation_reason"}` is already the store convention. Excluding `{"body_md"}` at serialize time is exactly the Veto #13 payload-default. `get_active` returning `None` (no active card) maps to the **empty model** branch (D-01), distinct from a bad-corp_code **exception**.

### peer_view median PER/PBR/ROE (Discretion #7)
**Critical gap:** there is **no fundamentals/valuation table** in the current schema. `entities` has `sector` (TEXT, nullable) for grouping, but PER/PBR/ROE source columns **do not exist anywhere** (ohlcv is OHLCV+flow only; no `market_cap`, `eps`, `bps`, `net_income`). `numeric_facts` on a decision_card carries `pe_ttm` etc. but only for analyzed tickers, not a peer universe.
**Recommendation (flag as Open Question):** `peer_view(corp_code, metric)` cannot compute a real same-sector median PER/PBR/ROE until a fundamentals source exists. Two honest paths:
1. **Phase 3 minimal:** group by `entities.sector`, compute `percentile_cont(0.5)` over whatever metric IS available (e.g. derive a crude P/E only if a price+EPS source is added). Likely returns an **empty PeerView** (D-01) for most metrics this phase.
2. **Add a fundamentals collector/table first** (out of current scope — no Phase 1 collector produces fundamentals).
```sql
-- Shape ONLY (assumes a future fundamentals table with the metric column):
SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY fnd.per) AS median_per
FROM fundamentals fnd
JOIN entities e ON e.corp_code = fnd.corp_code
WHERE e.sector = (SELECT sector FROM entities WHERE corp_code = :corp_code)
  AND fnd.per IS NOT NULL
```
> **[RESOLVED 2026-06-01 → D-06]:** User chose the **latter** — pull a fundamentals source into Phase 3 scope. pykrx `get_market_fundamental` (PER/PBR/EPS/BPS) + dart-fss 재무제표 (ROE) feed a new `fundamentals` table; `peer_view` computes the real same-sector median via `percentile_cont(0.5)`. The "empty model now" path below is superseded.

The planner must decide: ship `peer_view` returning an empty/`metric_unavailable` model now (D-01-consistent, honest), or pull a fundamentals source into Phase 3 scope. ~~**Recommend the former**~~ → **per D-06, the latter is locked.**

### get_note path-traversal defense (Discretion #9, get_note)
```python
# Source: [VERIFIED: archive src/stock_mcp/paths.py safe_join] — read-only variant
from pathlib import Path
_WHITELIST = ("notes/private/",)

def safe_resolve(repo_root: Path, user_path: str) -> Path:
    rr = repo_root.resolve()
    candidate = (rr / user_path).resolve()   # collapses '..' AND follows symlinks
    roots = tuple((rr / p.rstrip("/")).resolve() for p in _WHITELIST)
    if not any(candidate == r or candidate.is_relative_to(r) for r in roots):
        raise NotePathForbidden(f"path outside whitelist: {user_path!r}")
    if not candidate.is_file():
        raise FilingNotFound(f"note not found: {user_path!r}")  # or NoteNotFound
    return candidate
```
`get_note` reads the file, wraps+flags content (D-03), returns `NoteContent`. **Note table vs disk:** the redesign sketch has a `notes` DB table, but `notes/private/` is gitignored on-disk and `Portfolio.load` already reads disk. Simplest Phase-3 path: `get_note` reads **disk** (no notes table needed for get_note); the `notes` table is only required if `hybrid_search` must search notes. Planner decides whether to create the `notes` table this phase or defer note-search.

### get_briefing partial impl (Discretion #9)
Briefing rows (`report_type='daily_briefing'`/`'weekly_briefing'`) are Phase 5 — the `decision_cards` table has **no `report_type` column** (migration 0007 locked 12 columns; Phase 5 adds it via its own migration). Phase 3 returns an **empty model** (D-01) without faking data:
```python
def get_briefing(date: str, type: str = "daily") -> Briefing:
    if type not in ("daily", "weekly"):
        raise InvalidArgument("type must be 'daily' or 'weekly'")
    # Phase 5 will query decision_cards WHERE report_type=... ; that column does not
    # exist yet, so there is nothing to return. Honest empty model, NOT a fake row.
    return Briefing(date=date, type=type, found=False, entries=[])
```
Do NOT add a `report_type` column or query against one in Phase 3 — that's Phase 5's migration. Returning `found=False, entries=[]` is the D-01-correct "no data yet" shape.

### Tool-by-Tool summary

| Tool | Reads | New infra needed? | Injection wrap? | Empty-model case | Exception case |
|------|-------|-------------------|-----------------|-------------------|----------------|
| `get_filing(rcept_no)` | filings (whole body_md) | no | YES (body_md) | — (single row) | FilingNotFound if no row |
| `search_filings(corp_code, event_type?, since?, until?, limit=50)` | filings (metadata, `filed_at DESC`) | no | no (metadata only) | `hits=[]` | EntityNotFound / InvalidArgument |
| `ohlcv_range(ticker, from_date, to_date)` | ohlcv (numeric) | no | no | `bars=[]` | InvalidArgument / EntityNotFound |
| `flow_range(ticker, from_date, to_date)` | ohlcv (foreign_net/inst_net/short_*) | no | no | `rows=[]` | InvalidArgument / EntityNotFound |
| `peer_view(corp_code, metric)` | entities.sector + `fundamentals` table (NEW, D-06) | **YES (fundamentals collector + table — D-06 in-scope)** | no | `median=None`/`n=0` when sector has no data | InvalidArgument (unknown metric) |
| `hybrid_search(query, source_filter?, date_range?, limit=10)` | filings/news/notes narrative, RRF k=60 | **YES (bm25_tokens + indexes + embeddings backfill + notes table)** | YES (snippets) | `hits=[]` | DataBackendError |
| `get_note(path)` | notes/private/ disk (or notes table) | maybe (notes table only if searched) | YES (content_md) | — | NotePathForbidden / NoteNotFound |
| `get_decision_card(corp_code, latest=true, view='payload')` | cards.store.get_active | no | YES if view='both' | `found=False` | InvalidArgument |
| `list_portfolio()` | shared.portfolio.Portfolio.load(repo_root) | no | no (structured) | empty holdings/watchlist | PortfolioLoadError→DataBackendError |
| `get_briefing(date, type='daily')` | (Phase 5 rows — absent) | no (returns empty) | n/a | `found=False, entries=[]` | InvalidArgument (bad type) |

## State of the Art

| Old Approach (v1.0 archive) | Current Approach (Phase 3 v2.0) | When Changed | Impact |
|--------------|------------------|--------------|--------|
| RRF over pre-chunked `chunks`/`documents` | RRF over whole-body `filings`/`news`/`notes` | Veto #8 (2026-04 redesign) | No chunk table; one candidate = one whole filing |
| Tool returns `{"error":{...}}` dict, never raises | empty model (no data) vs `raise McpToolError` (fault) | D-01 | More idiomatic FastMCP; loud failures |
| `search_vault` single tool | 10 typed tools, no `run_sql` | redesign §2 | Code-execution-with-MCP pattern (references not blobs) |
| FastMCP 2.11 | FastMCP 2.x pinned `<3.0` (3.x exists, deferred) | FastMCP 3.0 GA late-2025 | API stable; honor lock |

**Deprecated/outdated:**
- Archive `chunks.bm25_tokens` / `chunks.embedding` indexes (migration 0002) — that table is dormant; do NOT search it. Build the equivalent on `filings`/`news`/`notes`.
- Archive `add_note` write tool — Phase 3 is read-side ONLY; do not port it.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | VectorChord-BM25 in `tensorchord/vchord-suite:pg17-latest` exposes the `bm25_catalog.search_bm25query`/`to_bm25query`/`bm25_ops` API the archive used (vs only the newer `<&>`/`pg_tokenizer` 0.2 API) | hybrid_search SQL | RRF SQL operator/function names need adjusting; verify against the live image at Wave 0 |
| A2 | bge-m3 embedding of a truncated/whole `body_md` is acceptable for the dense side (vs requiring a sibling chunk-view table per Veto #8 wording) | Pitfall 5 | Dense recall on long filings weaker; BM25 still carries Korean keyword recall — may need sibling chunk-embed table (Veto-sanctioned) |
| A3 | `get_note` reading `notes/private/` from disk (no `notes` DB table) is acceptable for Phase 3 | get_note | If `hybrid_search` must search notes, a `notes` table + embeddings ARE required (Wave 0 migration) |
| A4 | `peer_view` returning empty/metric_unavailable now is acceptable (no fundamentals source exists) | peer_view | If real medians are required this phase, a fundamentals collector/table must enter scope |
| A5 | `.mcp.json` for a Python stdio server uses `command`+`args` spawning `.venv` python with `DATABASE_URL` in `env` (standard Claude Code MCP config) | .mcp.json | If Claude Code expects a different registration shape, server won't load; verify against current Claude Code MCP docs at planning time |
| A6 | FastMCP `mask_error_details=True` lets `ToolError` subclass messages through while masking other exceptions | Error Model | If masking also hides ToolError messages, D-01 "specific error" needs a different mechanism — verify in FastMCP 2.x docs |

## Open Questions (RESOLVED)

> **Resolution status (2026-06-01, plan-phase):** A3 and A4 were resolved by explicit user decisions (CONTEXT.md D-05, D-06). A1 and A2 remain genuine technical unknowns but are RESOLVED *as plan items* — both are explicitly scheduled as Wave-0 spikes/decisions in the plans (no longer open against planning).

1. **VectorChord-BM25 API surface in the pinned image (A1)** — **RESOLVED: deferred to Wave-0 spike (plan 03-01/03-06).**
   - What we know: archive migration 0002 used `bm25_catalog.search_bm25query` + `bm25_ops` against the SAME image and it was tested.
   - What's unclear: whether the current `pg17-latest` tag pulls a vchord 0.2 with the `<&>`/`pg_tokenizer` API instead.
   - Resolution: Wave-0 spike — `\dx` + `\df bm25_catalog.*` in the testcontainer; lock migration 0008 + retrieval.py SQL to whatever the image exposes.

2. **Long-body dense embedding (A2, Pitfall 5)** — **RESOLVED: ship head-truncated dense + strong BM25 first; sibling chunk-embed table only if recall inadequate.**
   - What we know: Veto #8 forbids storing chunked bodies as canonical, but explicitly allows a *sibling chunk-view table*; bge-m3 caps at 8K tokens.
   - What's unclear: whether title+head truncation gives acceptable dense recall on 사업보고서-scale filings.
   - Resolution: ship BM25-strong hybrid with head-truncated dense first; measure; add Veto-sanctioned sibling chunk-embed table later only if recall is inadequate (out of Phase-3 scope).

3. **notes table now or later (A3)** — **RESOLVED → D-05 (notes table + ingest IN-SCOPE this phase).** Wave-0 migration 0008 creates the `notes` table and an ingest job loads `notes/private/` disk memos into the DB (bge-m3 embedding + mecab-ko BM25 tokens) so `hybrid_search` covers filings/news/notes (SC#4 full). `get_note` still reads disk read-only whitelist separately. *(Supersedes the earlier "defer" recommendation.)*

4. **peer_view fundamentals dependency (A4)** — **RESOLVED → D-06 (fundamentals collection IN-SCOPE this phase).** A fundamentals collector (pykrx `get_market_fundamental` for PER/PBR/EPS/BPS + dart-fss 재무제표 for ROE) + a `fundamentals` table are added to Phase 3; `peer_view` computes real `entities.sector` `percentile_cont(0.5)` medians. *(Supersedes the earlier "empty model now" recommendation — user chose full scope.)*

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Postgres 17 + pgvector + vchord_bm25 + pg_trgm | all DB tools / hybrid_search | ✓ (docker-compose `tensorchord/vchord-suite:pg17-latest`; CI service) | pg17 | — |
| `fastmcp` 2.x | server | ✗ (not in .venv; group deleted) | — | Re-add `mcp` group + `uv sync` (Wave 0) |
| `sentence-transformers` (bge-m3) | hybrid_search dense embeddings | ✗ | — | Re-add `ingest` group; lazy-load model (Wave 0) |
| `python-mecab-ko` | hybrid_search BM25 tokenization | ✗ | — | Re-add `ingest` group (Wave 0) |
| `.mcp.json` | Claude Code registration | ✗ (deleted) | — | Create in Wave 0 (Discretion #5) |
| `notes/private/portfolio.md` | list_portfolio | ✗ on disk (test fixture provides it) | — | Tool raises PortfolioLoadError→DataBackendError if absent (D-01 honest) |
| `notes` DB table + bm25_tokens cols + BM25/HNSW indexes | hybrid_search | ✗ (no migration creates them) | — | **Wave-0 migration 0008 + backfill job — BLOCKING for hybrid_search** |

**Missing dependencies with no fallback (BLOCKING for the specific tool):**
- BM25/HNSW indexes + `bm25_tokens` columns + embedding/tsv backfill → `hybrid_search` returns empty until built.
- fundamentals source → `peer_view` cannot compute real medians.

**Missing dependencies with fallback:**
- fastmcp / sentence-transformers / mecab → re-add dependency groups (one-time Wave 0).
- `.mcp.json` → create it.
- notes table → `get_note` can read disk instead.

## Validation Architecture

> nyquist_validation: config not read as explicitly false → treated as ENABLED.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=9.0 (`[tool.pytest.ini_options]`, `pythonpath=["src"]`) |
| Config file | pyproject.toml (markers: `slow`, `e2e`, `db`) |
| Quick run command | `.venv/Scripts/python.exe -m pytest tests/mcp_v2/ -q -m "not db"` (CONTEXT note: uv NOT on Bash PATH; use `.venv/Scripts/python.exe`) |
| Full suite command | `.venv/Scripts/python.exe -m pytest tests/ -q` (DB tests use session-scoped `pg_engine` testcontainer running `alembic upgrade head`) |
| Live-DB fixtures | `tests/conftest.py::pg_engine` (session, `tensorchord/vchord-suite:pg17-latest`), `pg_clean` (function, TRUNCATE), `seeded_engine` (삼성전자/00126380/005930 pre-seeded) |

### Phase Requirements → Test Map
| Req | Behavior | Test Type | Automated Command | File Exists? |
|-----|----------|-----------|-------------------|-------------|
| SC#1 | server imports + registers 10 tools; `mcp.run` stdio | unit | `pytest tests/mcp_v2/test_server.py::test_all_tools_registered -x` | ❌ Wave 0 |
| SC#2 | each tool returns its Pydantic model; empty case valid | unit+db | `pytest tests/mcp_v2/test_tools_contract.py -x` | ❌ Wave 0 |
| SC#3 | **CI guard: no run_sql / arbitrary-SQL tool exists** | unit | `pytest tests/mcp_v2/test_no_run_sql_guard.py -x` | ❌ Wave 0 |
| SC#4 | hybrid_search rejects ohlcv/macro/decision_cards source; narrative-only | unit+db | `pytest tests/mcp_v2/test_hybrid_search.py -x` | ❌ Wave 0 |
| SC#5 | narrative tools wrap body in XML delimiter + set injection flag | unit | `pytest tests/mcp_v2/test_injection.py -x` | ❌ Wave 0 |
| D-01 | empty rows → empty model; bad ticker → McpToolError raised | unit+db | `pytest tests/mcp_v2/test_error_model.py -x` | ❌ Wave 0 |
| D-02 | hybrid_search hit carries id+score+snippet, NO body_md | unit+db | `pytest tests/mcp_v2/test_hybrid_search.py::test_no_body_md -x` | ❌ Wave 0 |
| D-03 | injection match flags (not blocks/strips) — pattern ID snapshot | unit | `pytest tests/mcp_v2/test_injection.py::test_flag_not_block -x` | ❌ Wave 0 |
| D-04 | search_filings default limit=50, filed_at DESC; ohlcv requires dates | unit+db | `pytest tests/mcp_v2/test_market.py -x` | ❌ Wave 0 |
| Veto#13 | get_decision_card payload default excludes body_md; both includes | db | `pytest tests/mcp_v2/test_card.py -x` | ❌ Wave 0 |
| get_note | path-traversal `..`/symlink rejected; whitelist enforced | unit | `pytest tests/mcp_v2/test_paths.py -x` | ❌ Wave 0 |

### CI Guard for run_sql (SC#3, Veto #7)
**Recommendation:** a pure-AST/registry test (no DB) that fails if any tool named/aliased `run_sql`/`execute_sql`/`raw_sql`/`query` is registered OR if any `tools/*.py` calls `engine.execute`/`conn.execute` with a non-`text()`-constant argument (i.e., an f-string / user-string SQL). Two layers:
1. **Registry check:** introspect the FastMCP instance's registered tool names; assert the set == the 10 locked names (no extras). Catches an added arbitrary-SQL tool.
2. **Static check:** `ast`-walk `src/mcp_v2/**.py`; flag any `text(` call whose argument is not a module-level constant (f-string / `%`/`+` concatenation / `.format`), and any direct `.execute(<str literal built from input>)`. Mirrors store.py/entity.py discipline.
```python
# tests/mcp_v2/test_no_run_sql_guard.py (skeleton)
def test_only_locked_tools_registered():
    from mcp_v2.server import mcp
    names = set(mcp.get_tools().keys())  # FastMCP API — verify exact accessor in 2.x
    assert names == {
        "get_filing","search_filings","ohlcv_range","flow_range","peer_view",
        "hybrid_search","get_note","get_decision_card","list_portfolio","get_briefing",
    }, f"unexpected tool surface: {names}"

def test_no_fstring_sql_in_mcp_v2():
    import ast, pathlib
    for p in pathlib.Path("src/mcp_v2").rglob("*.py"):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "text":
                arg = node.args[0] if node.args else None
                assert isinstance(arg, (ast.Constant, ast.Name)), \
                    f"{p}: text() arg must be a constant/module-level name, got {ast.dump(arg)}"
```
Run this in CI as a fast non-DB step (like the existing `tests/test_import_guard.py` step in ci.yml).

### Sampling Rate
- **Per task commit:** `pytest tests/mcp_v2/ -q -m "not db"` (server registration, injection, paths, error-model unit tests — fast).
- **Per wave merge:** `pytest tests/mcp_v2/ -q` + `tests/db/` (full, incl. testcontainer hybrid_search).
- **Phase gate:** full suite green + `test_no_run_sql_guard.py` green before `/gsd:verify-work`.

### Wave 0 Gaps
- [ ] `tests/mcp_v2/__init__.py` + `tests/mcp_v2/conftest.py` — re-declare `pg_clean`/`seeded_engine` (per-dir conftest scoping) + seed `filings`/`news`/`notes` rows with non-NULL body_tsv/body_embedding/bm25_tokens for hybrid_search tests.
- [ ] `tests/mcp_v2/test_no_run_sql_guard.py` — SC#3 (registry + AST) — runnable WITHOUT DB.
- [ ] `tests/mcp_v2/test_server.py`, `test_tools_contract.py`, `test_hybrid_search.py`, `test_injection.py`, `test_error_model.py`, `test_market.py`, `test_card.py`, `test_paths.py`.
- [ ] Migration **0008** — `notes` table (if note-search in scope) + `filings.bm25_tokens`/`news.bm25_tokens` INT[] + VectorChord-BM25 indexes + HNSW indexes on `body_embedding` (+ notes content_emb). Adapt archive migration 0002 SQL.
- [ ] **Backfill job** — tokenize `body_md`→bm25_tokens, embed→body_embedding, populate body_tsv for existing filings/news rows.
- [ ] Re-add `mcp` + `ingest` dependency groups to pyproject.toml; `uv sync`.
- [ ] `.mcp.json` at repo root.
- [ ] Add `src/mcp_v2` to `[tool.hatch.build.targets.wheel].packages`.

## Security Domain

> security_enforcement: not set false in config → ENABLED.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | stdio server spawned locally by Claude Code; no network auth surface this phase |
| V3 Session Management | no | stateless tool calls |
| V4 Access Control | yes | `get_note` whitelist (read-only `notes/private/`); read-side only (no write tools) |
| V5 Input Validation | yes | Pydantic models + ASCII ticker/corp_code regex BEFORE DB; `extra='forbid'` on models |
| V6 Cryptography | no | no crypto in this phase (content_hash is sha256 dedup, not a Phase-3 concern) |
| V12 Files & Resources | yes | path-traversal defense `Path.resolve()` + `is_relative_to` (symlink-safe); read-only |
| V13/V5 Injection (SQL) | yes | parameterized `text()` only; **no run_sql** (Veto #7, CI-guarded) |
| LLM-specific: Prompt Injection | yes | WRAP + FLAG XML delimiter on all narrative (D-03, SC#5) |

### Known Threat Patterns for {FastMCP stdio + Postgres + LLM-consumed narrative}
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via tool arg | Tampering | parameterized `text()` constants; ASCII regex pre-filter; no run_sql (CI guard) |
| Arbitrary-SQL escape hatch | Elevation of Privilege | SC#3 CI guard: registry + AST checks |
| Path traversal in get_note (`..`, symlink) | Tampering / Info Disclosure | `Path.resolve()`+`is_relative_to(whitelist)`; read-only; reject outside `notes/private/` |
| Prompt injection in DART/news/notes body | Tampering (of downstream LLM) | XML-delimiter WRAP + pattern FLAG (never block/strip — D-03); downstream LLM treats `<untrusted>` as data |
| stdout protocol corruption | Denial of Service | all diagnostic logging to stderr only (Pitfall 7) |
| Info disclosure via error messages | Info Disclosure | `mask_error_details=True` for non-ToolError exceptions; delimiter attrs validated, never echo offending value |
| Oversized response (token DoS) | Denial of Service | D-04 default limits (search_filings 50, hybrid 10); references-not-blobs (D-02) |

## Sources

### Primary (HIGH confidence)
- `[CITED: gofastmcp.com/servers/tools]` — Pydantic-model returns → structured output; `@mcp.tool` decorator; `ToolError` + `mask_error_details`; `ToolAnnotations(readOnlyHint=True)`; `Annotated`/`Field` params.
- `[CITED: gofastmcp.com/getting-started/welcome]` — `@mcp.tool` + `mcp.run()` stdio.
- `[VERIFIED: PyPI 2026-06-01]` `pip index versions` — fastmcp 3.3.1 (2.x latest 2.14.7), sentence-transformers 5.5.1, python-mecab-ko 1.3.7, mcp 1.27.2.
- `[VERIFIED: slopcheck 0.6.1 scan --json]` — fastmcp/sentence-transformers/python-mecab-ko all `OK`.
- `[VERIFIED: codebase]` — `src/cards/store.py`, `src/cards/models.py`, `src/db/entity_models.py`, `src/db/entity.py`, `src/shared/portfolio.py`, migrations 0001/0006/0007, `tests/conftest.py`, `.github/workflows/ci.yml`, `scripts/init-extensions.sql`, `pyproject.toml`.
- `[VERIFIED: git archive/llm-wiki-2026-04]` — `src/stock_mcp/{server,errors,paths}.py`, `src/stock_mcp/tools/{search,notes}.py`, `src/stock_mcp/search_core.py` (RRF k=60 CTE), `src/ingest/{injection_defense,embedder,tokenizer}.py`, archive `pyproject.toml` (exact dep pins).
- `.planning/research/redesign-2026-05.md` §2 (MCP tool surface, anti-patterns), §3 (decision_card), §4 (payload-default), §6, §8.

### Secondary (MEDIUM confidence)
- `[CITED: jlowin.dev/blog/fastmcp-3]` — FastMCP 3.0 breaking changes (constructor kwargs, repo move, tasks-extra); API largely unchanged.
- `[CITED: blog.vectorchord.ai]` — VectorChord-BM25 0.2 (`bm25vector`, `<&>` operator, negative score, pg_tokenizer); hybrid-search-with-RRF guidance.
- `[CITED: gocodeo.com / dev.to delimiter-defense / robertmelton.com]` — XML-delimiter wrapping ~95% vs 60% baseline; unique delimiters; treat-as-data instruction.
- `[CITED: anthropic.com/engineering/code-execution-with-mcp]` — filter/transform in code; references-not-blobs; progressive tool loading (98.7%).

### Tertiary (LOW confidence — flagged for validation)
- VectorChord-BM25 exact function/operator names in the project's pinned image (A1) — verify at Wave 0 against the live testcontainer.
- FastMCP 2.x `mcp.get_tools()` accessor name for the registry guard (A6) — verify in 2.x docs.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions PyPI-verified + slopcheck-clean + archive precedent.
- Module structure / error model / path defense / injection / get_decision_card / get_briefing: HIGH — direct archive + Phase-2 code references.
- hybrid_search RRF: MEDIUM — proven archive CTE, but depends on unbuilt Wave-0 infra and the vchord API surface (A1).
- peer_view: MEDIUM-LOW — no fundamentals source exists; likely empty-model this phase (A4).
- `.mcp.json` / FastMCP 2.x registry accessor: MEDIUM — standard pattern, verify exact shapes at planning (A5/A6).

**Research date:** 2026-06-01
**Valid until:** ~2026-07-01 (FastMCP / VectorChord move fast — re-verify versions and the vchord BM25 API before Wave 0).
