# Phase 6: Full MCP Tool Surface — Research

**Researched:** 2026-04-26
**Domain:** FastMCP 2.x tool surface, Pydantic models, Postgres reads, vault path-safe writes
**Confidence:** HIGH (codebase fully grep-verified; CONTEXT.md already locks 24 design decisions)

## Summary

Phase 6 adds 6 new FastMCP tools alongside the existing `search` tool registered on `mcp = FastMCP("stock-mcp")` in `src/stock_mcp/tools/search.py:29`. All major design choices are pre-locked in CONTEXT.md (D-01..D-24). The serving layer is read-only against Postgres + vault filesystem; no migrations, no collector changes.

**Primary recommendation:** Implement one tool per file under `src/stock_mcp/tools/`, importing the shared `mcp` instance from `tools.search` (or relocate `mcp` to `tools/__init__.py` to avoid the circular smell). Reuse `StructuredError`, `to_error_response`, `log_tool_call`, `_check_db_connection`, `resolve_entity`, `hybrid_search` verbatim. The first plan must be the **P-01 atomic portfolio cutover** before any new tool work; nine code/test sites currently hard-code `vault/notes/portfolio.md`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**MCP-03 `get_ticker_overview` & Phase 10 interface**
- **D-01:** OverviewResponse Pydantic model includes `valuation: ValuationContext | None = None`, `supply_demand: SupplyDemandSignals | None = None`, `private_thesis: PrivateThesis | None = None` — always `None` in Phase 6, wired in Phase 10.
- **D-02:** Phase 6 axes = `events` (subset of get_recent_events output), `portfolio` (matching holdings row if any), `related_notes` (`search(source='note', ticker=X, top_k=5)`).
- **D-03:** `ticker` accepts 6-digit KRX or 8-digit corp_code, normalized via `resolve_entity`.
- **D-04:** No `as_of` parameter (Phase 10 owns historical valuation).

**Two-step ID pattern**
- **D-05:** `get_recent_events(ticker, since)` → `[{id, source, date, type, title, snippet_200ch, vault_path}]`; no inline body.
- **D-06:** `get_related(document_id, depth=1)` → `[{id, edge_type, depth, vault_path, snippet_200ch}]`; max depth=2; SQL `edges` only (no graphify file dependency).
- **D-07:** `get_filing(id)` keyed on `documents.id` (sha256). Response: `{id, vault_path, frontmatter, body, body_chars, truncated}`. Truncate body at 200K chars.
- **D-08:** Snippet = `_derived.summary` if present, else first 200 chars of body. Wrap with `<vault_excerpt>` delimiter (Phase 3 INGEST-09 reuse).

**`add_note` write policy**
- **D-09:** Whitelist = `vault/notes/` ∪ `notes/private/` only. Path normalize → `..`-block → symlink-resolve → check prefix. Otherwise `WRITE_FORBIDDEN`.
- **D-10:** Conflict = append-only. Existing file → prepend `\n\n---\n## {ISO ts KST}\n\n` to body. Frontmatter `updated` refreshed; `tickers`/`tags` union-merged. No overwrite mode.
- **D-11:** `NoteFrontmatter` Pydantic model required: `type` (Literal[thesis/journal/conviction/note]), `tickers`, `tags`, `created`, `updated`, `author='yamin'`, `conviction_score? float`. Missing `type` → `INVALID_FRONTMATTER`. Invalid tickers → warning, not error.
- **D-12:** Path aliases: `journal/today` → `notes/private/journal/{YYYY-MM-DD KST}.md`; `005930/thesis` → `notes/private/005930/thesis.md`. Auto-mkdir within whitelist. Auto-`.md` extension.
- **D-13:** Append idempotency: identical timestamp header + body skipped → `idempotent=true`.

**`health()`**
- **D-14:** STALENESS_THRESHOLDS_HOURS = `{dart:26, krx:26, news:12, macro:26, kind:26}` (code constant, monkeypatchable).
- **D-15:** Schema: `SourceHealth{status: ok|stale|down, last_success, age_hours, last_error}`, `HealthResponse{overall, sources: dict, db: SourceHealth, timestamp}`. `overall` = any-down→down, any-stale→stale, else ok.
- **D-16:** Data source priority = `ingest_runs` SQL → fallback to `vault/ingested/_status/heartbeat.md` parse on DB failure.
- **D-17:** DB connectivity reuses `_check_db_connection`. On failure, `db.status='down'`, other sources go via heartbeat fallback.

**CI gates**
- **D-18:** `tests/fixtures/mcp-vault/` ≈ 10 tickers × 100 docs (DART 4-type + news + KIND + memo). testcontainers Postgres + alembic upgrade + ingest before tool calls.
- **D-19:** N=20 reps; record latency + token count via `tiktoken` cl100k_base on `json.dumps(response)`. Fail when p95 latency > 5s OR p95 tokens > 8k.
- **D-20:** PR test (not nightly). Save measurements to `tests/perf/{tool_name}.json` for diff review.

**`get_portfolio_state`**
- **D-21:** Meta only — no prices/eval. Schema: `PortfolioRow{ticker, corp_code, qty, avg_cost, tags, note}`, `PortfolioState{holdings, watchlist, source_path, last_modified}`.

**Token guard**
- **D-22:** Truncate priority (low→high cut order): `private_thesis → valuation → supply_demand → portfolio → related_notes → events`. Item-level for events/related; section drop for others. Response carries `truncation_applied: list[str]`.
- **D-23:** Phase 6 truncation only fires on events/related (others always None).

**Docstrings**
- **D-24:** Match `tools/search.py` shape: 1-line summary + req-ID, `### Behavior contract`, `### Response shape`, `### Errors`, `### Performance budget`.

### Claude's Discretion
- Snippet helper module placement (suggested `src/stock_mcp/snippets.py`).
- File granularity: 1 tool / 1 module under `tools/` (search.py 패턴).
- Where `mcp` instance lives (current: `tools/search.py`; can stay or migrate).
- BFS implementation for `get_related` (recursive CTE vs iterative — see §4 below).
- Path alias resolution helper location.
- README/`docs/mcp-tool-contract.md` for two-step flow guide.

### Deferred Ideas (OUT OF SCOPE)
- Prices / eval value in `get_ticker_overview` (Phase 10 valuation handles).
- `chunks.visibility` / multi-user perms (v2).
- Tool plugin / dynamic registration system.
- MCP-03 response cache (TTL).
- `add_note` `mode` param (overwrite/create-only).
- graphify wiki/json output direct usage (Phase 7).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MCP-03 | `get_ticker_overview(ticker)` 4-axis combined view | §1 (existing FastMCP infra), §3 (resolve_entity), §6 (related_notes via hybrid_search), D-01 model placeholders |
| MCP-04 | `get_recent_events(ticker, since)` timeline | §3 resolve_entity; §5 documents/events SQL; snippet helper |
| MCP-05 | `get_portfolio_state()` from `notes/private/portfolio.md` | §2 portfolio cutover; §10 Portfolio.load |
| MCP-06 | `get_related(document_id, depth?)` graph BFS | §4 edges schema (Phase 2 only `supersedes` populated; Phase 7 will widen) |
| MCP-07 | `get_filing(id)` two-step body fetch | §5 documents.id (sha256) keyed read; D-07 truncate |
| MCP-08 | `add_note` write to vault/notes ∪ notes/private | §7 whitelist + path normalize; §8 NoteFrontmatter |
| MCP-09 | `health()` source staleness + DB | §6 ingest_runs (NOT YET WRITTEN — risk!); §7 heartbeat fallback parser |
| MCP-10 | Docstring contracts + CI latency/token gates | §11 testcontainers fixture; §12 tiktoken (new dep) |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

| Directive | Implication for Phase 6 |
|-----------|--------------------------|
| `collectors/`, `ingest/` MUST NOT import `anthropic`/`openai` (CI guard COLL-07) | `stock_mcp/` is exempt (serving layer); but new `tools/*.py` MUST also avoid LLM imports — pure read/write surface |
| Markdown vault is single source of truth; DB is regenerable cache | `add_note` writes to vault FS; DB is rebuilt by Phase 3 ingest. Tool writes vault and returns; ingest picks up later |
| 800 line file cap, 50 line function cap, immutability | 1 tool / 1 file pattern naturally fits |
| Validate user input (Pydantic) | All params via Pydantic models, `extra='forbid'` |
| stdio = JSON-RPC: never `print()` or `raise` past tool boundary | Reuse `to_error_response` envelope (D-21 already enforced in `search.py`) |
| Korean comments OK in CONTEXT/discussion; code comments English unless quoting Korean fixtures | Tool docstrings should be English (LLM-facing contract) |

## Standard Stack

### Core (already pinned in pyproject.toml)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastmcp | >=2.11,<3.0 | MCP server + `@mcp.tool()` decorator | [VERIFIED: pyproject.toml mcp group, search.py:17] |
| pydantic | >=2.13,<3 | Tool input/output models with `extra='forbid'` | [VERIFIED: existing models.py:7] |
| sqlalchemy | >=2.0 | DB access via `engine.connect()` + `text()` bind params | [VERIFIED: search_core.py uses this exclusively] |
| pyyaml | >=6.0 | heartbeat.md parser, NoteFrontmatter dump | [VERIFIED: heartbeat.py, portfolio.py both use yaml.safe_load/safe_dump] |
| python-frontmatter | >=1.1 | Note read for append-merge | [VERIFIED: shared/frontmatter.py:22 already uses `import frontmatter as fm`] |

### Supporting (NEW dependencies for Phase 6)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **tiktoken** | latest (~0.8) | cl100k_base encoder for D-19 token-budget assertions in CI | Test-only dep; add to `dev` group not `mcp` group [ASSUMED: not yet in pyproject; verify with `npm view`-equivalent `pip show tiktoken`] |
| testcontainers[postgres] | >=4.8 | Already in `dev` group | reuse for D-18 fixture vault [VERIFIED: pyproject.toml line 70] |

**Verification:** `tiktoken` is not currently a project dep. Plan must add it to `[dependency-groups] dev`. Alternative: char-count / 4 estimate (used today in `logging.py:110: len(result_json)//4`) — cheaper but loose. Recommend tiktoken for the CI gate, char/4 for the live `log_tool_call` (already in place).

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| tiktoken | char/4 heuristic | Existing logging uses char/4; off by ~10-20% on Korean. Acceptable for live logging, NOT for CI gate (false negatives at 8k boundary) |
| Recursive CTE for BFS | Iterative Python loop with two SQL queries | Recursive CTE is cleaner + atomic; iterative loop is easier to bound on `depth` and to add per-edge filtering later. Recommend recursive CTE for depth ≤ 2 (D-06 max). |

## Architecture Patterns

### Existing `src/stock_mcp/` shape (verified from filesystem)
```
src/stock_mcp/
├── __init__.py          # (empty? exports nothing critical)
├── __main__.py          # entry point: `stock-mcp` script
├── server.py            # mcp re-export + _check_db_connection (lines 18-32)
├── errors.py            # ErrorCode enum + StructuredError + to_error_response
├── logging.py           # log_tool_call → stderr JSON line
├── models.py            # DateRange, SearchHit, SearchResult (search-only)
├── search_core.py       # hybrid_search SQL templates + RRF fusion
└── tools/
    ├── __init__.py      # (no auto-discovery — explicit import in server.py)
    └── search.py        # `mcp = FastMCP("stock-mcp")` + `search` tool def
```

**Critical insight:** the `mcp` singleton lives at `src/stock_mcp/tools/search.py:29` and `server.py` re-exports it via `from .tools.search import mcp` (server.py:16). Other Phase 6 tool modules MUST import `mcp` from `..tools.search` OR we relocate the singleton to `tools/__init__.py` (cleaner). Recommend: **leave `mcp` in `tools/search.py`** to minimize churn; new tools do `from .search import mcp`.

### Recommended new file layout
```
src/stock_mcp/
├── models.py            # ADD: OverviewResponse, EventRow, PortfolioRow,
│                        #      PortfolioState, RelatedRow, FilingResponse,
│                        #      AddNoteResponse, SourceHealth, HealthResponse,
│                        #      ValuationContext|None, SupplyDemandSignals|None,
│                        #      PrivateThesis|None (D-01 placeholders)
├── snippets.py          # NEW: build_snippet(body, derived_summary) helper
├── paths.py             # NEW: resolve_path_alias() + safe_join() for D-09/D-12
├── server.py            # MODIFY: import all new tool modules for side-effect registration
└── tools/
    ├── search.py        # UNCHANGED (keep `mcp` here)
    ├── overview.py      # NEW: get_ticker_overview
    ├── events.py        # NEW: get_recent_events
    ├── portfolio.py     # NEW: get_portfolio_state
    ├── related.py       # NEW: get_related
    ├── filing.py        # NEW: get_filing
    ├── notes.py         # NEW: add_note
    └── health.py        # NEW: health
```

### Pattern 1: Tool registration (verified in search.py:128)
```python
# Source: src/stock_mcp/tools/search.py:125-128
mcp.tool()(search)  # explicit call form preserves search as plain callable
```
Apply identically to each new tool. Then in `server.py`:
```python
from .tools import overview, events, portfolio, related, filing, notes, health  # noqa: F401  # side-effect registration
```

### Pattern 2: Error envelope (verified in search.py:112-122)
```python
try:
    ...
except StructuredError as e:
    err = to_error_response(e)
    log_tool_call(name, args, latency, 0, error=err["error"])
    return err
except Exception as e:
    wrapped = StructuredError(ErrorCode.INTERNAL, str(e)[:200])
    err = to_error_response(wrapped)
    log_tool_call(name, args, latency, 0, error=err["error"])
    return err
```

### Anti-Patterns to Avoid
- **`raise` past tool boundary** — corrupts JSON-RPC stdout (D-21).
- **`print()` to stdout** — same. Use `log_tool_call` (writes stderr).
- **f-string SQL** — every existing query uses bind params; preserve.
- **Reading `dashboards/portfolio.md`** — REQUIREMENTS.md AMENDMENT explicitly says SoT is `notes/private/portfolio.md` (MCP-05).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Path traversal defense | custom regex | `Path.resolve(strict=False)` + check `is_relative_to(allowed_root)` (Python 3.12 stdlib) | symlink + `..` covered atomically |
| Frontmatter read for append | manual YAML split | `frontmatter.load()` (already used in shared/frontmatter.py:22) | round-trip safe |
| Token counting in CI | char heuristic | tiktoken cl100k_base | matches Anthropic context window math |
| BFS over edges | Python loop with N SQL queries | Postgres recursive CTE bounded by depth ≤ 2 | atomic + cheap |
| Ticker normalization | re-parse value | `resolve_entity(engine, value, as_of=None)` (`db/entity.py:33`) | already handles 6 vs 8 digits + None on miss |
| ISO KST timestamp | manual offset math | `datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")` | stdlib ZoneInfo |

**Key insight:** Phase 3 already battle-tested all the primitives (mcp instance, error envelope, log_tool_call, hybrid_search, resolve_entity, frontmatter read/write). Phase 6 is composition, not invention.

## Runtime State Inventory

> Phase 6 includes a portfolio.md path cutover (P-01). All 5 categories below.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — Postgres holds documents/chunks/entities. portfolio.md is a vault file, not DB-stored. `entities` rows seeded from portfolio (`src/db/seed_entities.py:35`); the seed re-runs on demand and re-reads whatever path the loader points at. | None (re-run `uv run python -m src.db.seed_entities` after cutover for safety, but no schema change) |
| Live service config | None — no external service references this path | — |
| OS-registered state | None — no systemd unit, scheduled task, or pm2 process embeds the path | — |
| Secrets/env vars | None — `.env` carries DART_API_KEY etc., not path constants | — |
| Build artifacts | None — pure Python, no compiled artifact carrying the path | — |
| **Source code (P-01 cutover surface)** | 9 sites — see table below | Atomic edit in Plan 01 |

### P-01 Cutover Surface (every reference to the old path)

| File:line | Reference | Cutover action |
|-----------|-----------|----------------|
| `src/shared/portfolio.py:7` | docstring "vault file `vault/notes/portfolio.md`" | Update docstring to `notes/private/portfolio.md` |
| `src/shared/portfolio.py:25` | exception docstring | Update text |
| `src/shared/portfolio.py:67-73` | `Portfolio.load(vault_root)` builds `Path(vault_root) / "notes" / "portfolio.md"` | Change to accept `repo_root` and resolve `repo_root / "notes" / "private" / "portfolio.md"` (per CONTEXT P-01: `Portfolio.load(repo_root)`) |
| `src/db/seed_entities.py:2` | docstring | Update path |
| `src/db/seed_entities.py:35` | `Portfolio.load(vault_root)` call | Pass `repo_root` not `vault_root` |
| `src/collectors/dart/__init__.py` (none directly), `src/collectors/kind/__init__.py:85`, `src/collectors/krx/__init__.py:65`, `src/collectors/news/__init__.py:61` | All call `Portfolio.load(vault_root)` | Update each to pass `repo_root` (= vault_root.parent in current layout, or accept new signature) |
| `tests/test_cli_default_flags.py:19` | writes `(root/"vault"/"notes"/"portfolio.md")` | Update fixture to write `notes/private/portfolio.md` |
| `tests/test_portfolio.py:19,24,31,40,45,55` | builds `vault/notes/portfolio.md` and calls `Portfolio.load(tmp_path)` | Update fixture path + signature |
| `tests/collectors/conftest.py:39` | writes `tmp_path/"notes"/"portfolio.md"` (already at top of vault, so this might already be near-target — confirm) | Move under `notes/private/` |
| `tests/collectors/krx/test_collect_krx.py:170` | writes portfolio.md | Move |
| `tests/db/conftest.py:35` | same | Move |
| `tests/db/test_seed_entities.py:31` | writes `vault_root/"notes/portfolio.md"` | Move |
| `vault/notes/portfolio.md` | actual data file | `git mv vault/notes/portfolio.md notes/private/portfolio.md` (note: `notes/private/` is gitignored — file becomes local-only, must be created locally per `templates/portfolio.md`) |
| `templates/portfolio.md:12-13` | comments already say `notes/private/portfolio.md` | No change |
| `.gitignore:9` | `notes/private/` already gitignored | Verify pattern still covers; consider whitelisting `notes/private/portfolio.md.example` if desired |
| `README.md:32, 98, 156, 266` | doc references | Update |
| `CLAUDE.md:126` | first-time setup instruction | Update path in setup step |

**Critical sequencing:** the cutover MUST land in a single atomic commit (one task) — a partial cutover breaks all collector E2E tests. The plan's first task should be "Plan 06-01: P-01 portfolio.md cutover" before any new tool work.

## Common Pitfalls

### Pitfall 1: `mcp` singleton circular import
**What goes wrong:** Putting `mcp = FastMCP(...)` in `tools/search.py` and importing it from siblings creates a sibling-import dance.
**Why it happens:** Python imports are lazy but order-sensitive when side effects register tools.
**How to avoid:** Always import via `from stock_mcp.tools.search import mcp` (absolute) or relocate `mcp` to `tools/__init__.py`. server.py imports all tool modules at the bottom for registration ordering.

### Pitfall 2: `add_note` symlink escape
**What goes wrong:** Caller passes `notes/private/../../etc/passwd` or a path containing a symlink to outside the whitelist.
**How to avoid:** Use `Path(p).resolve()` (follows symlinks) then `is_relative_to(allowed_root.resolve())`. Reject before any FS write.

### Pitfall 3: `health()` when `ingest_runs` is empty
**What goes wrong:** `ingest_runs` table EXISTS in migration 0001 but **NO CODE WRITES IT TODAY** (verified: only refs are migration + test schema check). Phase 9 (OPS-03) will populate it. Phase 6 must not rely on rows being present.
**How to avoid:** Treat `ingest_runs` query returning 0 rows as "fall through to heartbeat.md". This makes Phase 9 a transparent upgrade.

### Pitfall 4: `get_related` empty edge set
**What goes wrong:** `edges` table has CHECK `edge_type IN ('supersedes')` only (Phase 2 migration 0001:153). Phase 7 (GRAPH-01) widens this. Phase 6 BFS will return mostly empty results today.
**How to avoid:** Implement BFS correctly anyway; document expected post-Phase-7 behavior. Add a fixture that pre-inserts test edges (bypass CHECK by relaxing in a test-only migration or by inserting `supersedes` rows; or add Phase 7 edge types in a Phase 6 prep migration — **decision needed: discuss with user; CONTEXT does not lock this**).

### Pitfall 5: `tiktoken` adds 100MB+ dependency for one CI assertion
**Mitigation:** Add to `dev` group only, not `mcp`. Server runtime stays slim.

### Pitfall 6: testcontainers slow boot in PR CI (D-20)
**What goes wrong:** Running 7 tools × N=20 reps with full Postgres+ingest fixture per run easily blows past 5 minutes.
**Mitigation:** Session-scoped Postgres fixture (already pattern in conftest.py:51 `pg_engine` is `scope="session"`); single ingest run feeds all 7 tool perf tests; serialize the 7×20=140 calls in a single test to amortize fixture cost.

### Pitfall 7: `documents.body` text column has no length limit
**What goes wrong:** `get_filing(id)` returns full body. Some DART filings are >500K chars. D-07 caps at 200K.
**Mitigation:** Truncate in Python after SELECT; set `truncated=True`. SQL `SUBSTRING(body, 1, 200001)` is faster but loses an exact char count for the original — track via `LENGTH(body)`.

### Pitfall 8: Append-merge race on add_note
**What goes wrong:** Two concurrent `add_note` calls on the same path → lost write.
**Mitigation:** Use `tempfile.mkstemp` + `os.replace` atomic write (mirrors `frontmatter.write_frontmatter` pattern at `shared/frontmatter.py:243-261`). Read-modify-write within a single function call. Concurrent MCP calls are rare (single-user) but the pattern is free.

## Code Examples

### Tool docstring template (extracted from search.py:47-81)
```python
def get_ticker_overview(ticker: str) -> OverviewResponse | dict:
    """Combined 4-axis context for a ticker (MCP-03, JUDGE-01).

    Returns events, portfolio row, related notes, and Phase 10 placeholders
    (valuation, supply_demand, private_thesis — always None in Phase 6).

    ### Behavior contract
    - `ticker`: 6-digit KRX or 8-digit corp_code; resolved via `resolve_entity`.
    - No `as_of` parameter (Phase 10 owns historical valuation).

    ### Response shape
    Returns `OverviewResponse` with:
    - `events`: list of EventRow (≤ 20 most recent)
    - `portfolio`: PortfolioRow if ticker in holdings, else None
    - `related_notes`: SearchHit[≤5] from `search(source='note', ticker=...)`
    - `valuation` / `supply_demand` / `private_thesis`: always None (Phase 10)
    - `truncation_applied`: list of dropped sections per D-22

    ### Errors
    Returns `{"error": {...}}` with codes INVALID_TICKER, DB_UNAVAILABLE, INTERNAL.

    ### Performance budget
    p95 latency < 5s, p95 response < 8k tokens (cl100k_base).
    """
```

### Recursive CTE for BFS (D-06, depth ≤ 2)
```sql
WITH RECURSIVE related AS (
    SELECT dst_type, dst_id, edge_type, 1 AS depth
    FROM edges
    WHERE src_type = 'document' AND src_id = :doc_id
    UNION ALL
    SELECT e.dst_type, e.dst_id, e.edge_type, r.depth + 1
    FROM edges e
    JOIN related r ON e.src_type = r.dst_type AND e.src_id = r.dst_id
    WHERE r.depth < :max_depth
)
SELECT r.dst_type, r.dst_id, r.edge_type, r.depth,
       d.vault_path, d.body
FROM related r
LEFT JOIN documents d ON r.dst_type = 'document' AND r.dst_id = d.id
ORDER BY r.depth, r.edge_type;
```

### Path whitelist check (D-09)
```python
ALLOWED_ROOTS = (Path("vault/notes").resolve(), Path("notes/private").resolve())

def safe_join(repo_root: Path, user_path: str) -> Path:
    candidate = (repo_root / user_path).resolve()
    if not any(candidate.is_relative_to(root) for root in ALLOWED_ROOTS):
        raise StructuredError(ErrorCode.WRITE_FORBIDDEN, f"path outside whitelist: {user_path!r}")
    return candidate
```

### `health()` SQL (D-16) — when ingest_runs has rows
```sql
SELECT source,
       MAX(finished_at) FILTER (WHERE error IS NULL) AS last_success,
       MAX(finished_at) AS last_attempt,
       (SELECT error FROM ingest_runs ir2
        WHERE ir2.source = ir.source
        ORDER BY started_at DESC LIMIT 1) AS last_error
FROM ingest_runs ir
WHERE source IS NOT NULL
GROUP BY source;
```
Fallback: parse `vault/ingested/_status/heartbeat.md` top-level `sources` dict (already YAML-frontmatter; reuse `_read_sources` from `ingest/heartbeat.py:34` — refactor that helper to a public name in shared module, or read the file directly with `yaml.safe_load`).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single `search` tool | Multi-tool MCP surface (Phase 6) | This phase | Two-step ID pattern reduces token spend |
| Local LLM in ingest | Claude Schedule git round-trip | Phase 5 | `_derived.summary` available for snippets (D-08) |
| `dashboards/portfolio.md` (REQUIREMENTS wording, now superseded) | `notes/private/portfolio.md` | Phase 10 P-01 | Aligns with FOUND-03 gitignore policy |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | tiktoken acceptable as new dev dep | Standard Stack Supporting | If user prefers no new deps, fall back to char/4 heuristic with adjusted CI threshold (~1.6x slack) |
| A2 | `ingest_runs` rows can stay empty in Phase 6 (Phase 9 populates) | Pitfall 3 | If user wants rows now, Phase 6 scope grows to include OPS-03 |
| A3 | Phase 7 widens edges CHECK constraint; Phase 6 fixture inserts only `supersedes` rows for testing `get_related` | Pitfall 4 | If `get_related` needs richer edges for CI, plan must add a Phase-6-prep migration to relax CHECK |
| A4 | `Portfolio.load(repo_root)` (P-01 says repo_root, not vault_root) — confirm signature change is what user wants | Runtime State Inventory P-01 | If signature should remain `vault_root` and just look one level up, avoid changing collector call sites |
| A5 | `notes/private/` is gitignored; the actual portfolio.md file becomes local-only after cutover | Runtime State Inventory | Users on a fresh clone will get NoFile error until they create local portfolio.md from `templates/portfolio.md` (matches CONTEXT D-03 from Phase 1) |

## Open Questions

1. **Should Phase 6 include a small Alembic migration to relax `ck_edge_type_phase2` CHECK so test fixtures can insert non-supersedes edges for `get_related` testing?**
   - What we know: Phase 7 GRAPH-01 needs this anyway.
   - Recommendation: Yes, add a tiny migration `0003_relax_edges_check_for_phase6_tests.py` that drops the CHECK (or widens it). Cheap, decouples Phase 6 testing from Phase 7 work.

2. **Where should the `mcp = FastMCP(...)` singleton live long-term?**
   - Currently in `tools/search.py:29`. Adding 6 modules that import from a sibling tool feels off.
   - Recommendation: leave as-is for minimal diff; revisit in Phase 7.

3. **Confirm `Portfolio.load(repo_root)` signature shape.** CONTEXT says P-01 = "`Portfolio.load(repo_root)` 시그니처 갱신". Does `repo_root` mean the project root (parent of `vault/`)? Plan must confirm during Plan 06-01.

## Environment Availability

Phase 6 depends on infrastructure already in place — no new external services.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Postgres 17 + pgvector + vchord_bm25 | All read tools | ✓ | per docker-compose.yml | — |
| Python 3.12 | All | ✓ | per pyproject.toml | — |
| FastMCP 2.x | mcp registration | ✓ | >=2.11,<3.0 | — |
| testcontainers[postgres] | CI gate fixture | ✓ | >=4.8 in dev group | — |
| tiktoken | CI token measurement | ✗ NEW | latest | char/4 heuristic (less precise) |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** tiktoken (fallback: char/4).

## Validation Architecture

Per `.planning/config.json` workflow.nyquist_validation default = enabled.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 9.0 (verified: pyproject.toml:66) |
| Config file | `pyproject.toml [tool.pytest.ini_options]` (verified: lines 73-80) |
| Quick run command | `uv run pytest tests/test_mcp_*.py -x` |
| Full suite command | `uv run pytest -x` (current ~2min on this codebase) |
| Markers | `slow`, `e2e`, `db` (verified: pyproject.toml:76-79) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| MCP-03 | get_ticker_overview returns 4 axes incl. None placeholders | integration | `pytest tests/mcp/test_overview_tool.py::test_combined_4_axis -x` | ❌ Wave 0 |
| MCP-03 | OverviewResponse model has valuation/supply_demand/private_thesis None fields (D-01) | unit | `pytest tests/mcp/test_overview_models.py::test_phase10_placeholder_fields -x` | ❌ Wave 0 |
| MCP-03 | D-22 truncation drops events first | unit | `pytest tests/mcp/test_overview_tool.py::test_truncation_priority -x` | ❌ Wave 0 |
| MCP-04 | get_recent_events returns ID + snippet, no body | integration | `pytest tests/mcp/test_events_tool.py::test_no_body_in_response -x` | ❌ Wave 0 |
| MCP-04 | Snippet uses _derived.summary if present (D-08) | unit | `pytest tests/mcp/test_snippets.py::test_summary_preferred -x` | ❌ Wave 0 |
| MCP-05 | get_portfolio_state reads notes/private/portfolio.md (P-01) | integration | `pytest tests/mcp/test_portfolio_tool.py::test_reads_private_path -x` | ❌ Wave 0 |
| MCP-05 | No prices/eval in response (D-21 meta-only) | unit | `pytest tests/mcp/test_portfolio_tool.py::test_no_price_fields -x` | ❌ Wave 0 |
| MCP-06 | get_related BFS depth=1 returns direct neighbors | integration | `pytest tests/mcp/test_related_tool.py::test_depth_one -x` | ❌ Wave 0 |
| MCP-06 | depth=2 traverses two hops; depth>2 clamped | integration | `pytest tests/mcp/test_related_tool.py::test_depth_clamp -x` | ❌ Wave 0 |
| MCP-07 | get_filing(sha256) returns full body up to 200K chars | integration | `pytest tests/mcp/test_filing_tool.py::test_full_body -x` | ❌ Wave 0 |
| MCP-07 | Truncated=true on >200K body | unit | `pytest tests/mcp/test_filing_tool.py::test_truncation_flag -x` | ❌ Wave 0 |
| MCP-08 | add_note writes vault/notes/foo.md | integration | `pytest tests/mcp/test_notes_tool.py::test_writes_vault_notes -x` | ❌ Wave 0 |
| MCP-08 | add_note rejects raw/, ingested/, /etc/ paths → WRITE_FORBIDDEN | unit | `pytest tests/mcp/test_notes_tool.py::test_whitelist_enforcement -x` | ❌ Wave 0 |
| MCP-08 | Append-merge to existing file with timestamp delimiter | integration | `pytest tests/mcp/test_notes_tool.py::test_append_idempotent -x` | ❌ Wave 0 |
| MCP-08 | Path alias `journal/today` resolves to dated file | unit | `pytest tests/mcp/test_paths.py::test_journal_today_alias -x` | ❌ Wave 0 |
| MCP-08 | NoteFrontmatter missing `type` → INVALID_FRONTMATTER | unit | `pytest tests/mcp/test_notes_tool.py::test_frontmatter_validation -x` | ❌ Wave 0 |
| MCP-09 | health() reports overall=down when DB unreachable | integration | `pytest tests/mcp/test_health_tool.py::test_db_down_overall -x` | ❌ Wave 0 |
| MCP-09 | Heartbeat fallback when ingest_runs empty | integration | `pytest tests/mcp/test_health_tool.py::test_heartbeat_fallback -x` | ❌ Wave 0 |
| MCP-09 | Stale source (>26h) → status=stale | unit | `pytest tests/mcp/test_health_tool.py::test_staleness_thresholds -x` | ❌ Wave 0 |
| MCP-10 | All 7 tools have `### Behavior contract`, `### Response shape`, `### Errors`, `### Performance budget` | unit | `pytest tests/mcp/test_docstring_contract.py -x` | ❌ Wave 0 |
| MCP-10 | p95 latency < 5s and p95 tokens < 8k for each tool over N=20 (D-19) | perf | `pytest tests/perf/test_mcp_latency_tokens.py -x -m slow` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/mcp/ -x` (fast unit + small integration)
- **Per wave merge:** `uv run pytest -x` (full suite incl. perf with `-m slow` when wave touches MCP-10)
- **Phase gate:** Full suite + perf green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/mcp/__init__.py` + `tests/mcp/conftest.py` — shared MCP fixture (mcp-vault, ingested DB)
- [ ] `tests/fixtures/mcp-vault/` — D-18 fixture: ~10 tickers × ~100 docs (DART, news, KIND, memo)
- [ ] `tests/perf/__init__.py` + `tests/perf/conftest.py` — N=20 harness + tiktoken counter
- [ ] `tests/mcp/test_overview_tool.py`, `test_events_tool.py`, `test_portfolio_tool.py`, `test_related_tool.py`, `test_filing_tool.py`, `test_notes_tool.py`, `test_health_tool.py`, `test_snippets.py`, `test_paths.py`, `test_docstring_contract.py`, `test_overview_models.py`
- [ ] Add `tiktoken` to `[dependency-groups] dev` in pyproject.toml
- [ ] (decision) Migration `0003_relax_edges_check.py` to allow non-supersedes edge_type values for fixtures

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | stdio MCP — single local user, no auth surface |
| V3 Session Management | no | same |
| V4 Access Control | yes (write scope) | `add_note` whitelist (D-09) — Path resolve + is_relative_to check |
| V5 Input Validation | yes | Pydantic `extra='forbid'` on all tool param/response models; `resolve_entity` regex pre-check |
| V6 Cryptography | no | no new crypto; sha256 already used as content-hash dedup primitive only (per Phase 2 doc) |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal in `add_note` | Tampering | `Path.resolve()` + `is_relative_to(allowed_root)` (Pitfall 2) |
| YAML deserialization in NoteFrontmatter | Tampering | Use `yaml.safe_load` only (mirrors heartbeat.py:50, portfolio.py:82) |
| stdout JSON-RPC corruption from raised exception | Repudiation | `to_error_response` envelope (D-21, search.py pattern) |
| Untrusted snippet text reaching downstream LLM unwrapped | Tampering (prompt injection) | `<vault_excerpt>` wrap helper (D-08, reuse `wrap_untrusted` from `ingest/injection_defense.py` already used by search_core.py:309) |
| Symlink escape from notes/private/ → /etc/ | Tampering | `Path.resolve(strict=False)` follows symlinks before whitelist check |
| Append-merge body that contains a YAML `---` delimiter forging frontmatter | Tampering | Body is appended AFTER existing closing fence; never re-parsed; new section uses `## {ts}` markdown header, not YAML |

## Sources

### Primary (HIGH confidence) — local codebase verified
- `src/stock_mcp/tools/search.py` (lines 1-128) — full pattern reference
- `src/stock_mcp/server.py` (lines 1-32) — DB fail-fast helper, mcp re-export
- `src/stock_mcp/errors.py` — ErrorCode enum (only 6 codes today; need to add WRITE_FORBIDDEN, INVALID_FRONTMATTER, PATH_NOT_FOUND, STALE_DATA, NOT_FOUND)
- `src/stock_mcp/models.py` — Pydantic ConfigDict(extra='forbid') pattern
- `src/stock_mcp/logging.py` — log_tool_call signature
- `src/stock_mcp/search_core.py` — SQL templating, bind params, hybrid_search
- `src/db/migrations/versions/0001_phase02_initial_schema.py` — documents/chunks/edges/events/ingest_runs schema
- `src/db/entity.py` — resolve_entity (lines 33-96)
- `src/shared/portfolio.py` — Portfolio.load (lines 65-83), to be amended in P-01
- `src/shared/frontmatter.py` — FrontMatter, read_frontmatter, write_frontmatter (atomic), DerivedBlock.summary field
- `src/ingest/heartbeat.py` — `_read_sources` parser (lines 34-53), HEARTBEAT_PATH_DEFAULT
- `tests/conftest.py` — pg_engine session-scoped testcontainers fixture (lines 51-86)
- `pyproject.toml` — dep groups, pytest markers
- CONTEXT.md (D-01..D-24), REQUIREMENTS.md (MCP-03..MCP-10 amended)

### Secondary (MEDIUM confidence)
- FastMCP 2.x decorator + stdio patterns: confirmed via `search.py` working implementation
- tiktoken cl100k_base for CI token gates: standard pattern in MCP ecosystem [ASSUMED based on Anthropic docs]

### Tertiary (LOW confidence)
- None — Phase 6 is composition over verified primitives.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already pinned in pyproject.toml; only tiktoken is new
- Architecture: HIGH — Phase 3 search.py provides template; reuse > invention
- Pitfalls: HIGH — most are direct projections of Phase 3 lessons; #3 (ingest_runs empty) and #4 (edges CHECK) are verified by grep
- Cutover surface: HIGH — every site grep-located with line numbers
- Validation map: HIGH — D-19 already specifies the measurement protocol

**Research date:** 2026-04-26
**Valid until:** 2026-05-26 (stable internal codebase; FastMCP 2.x stable per pin)
