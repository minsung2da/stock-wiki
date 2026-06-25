---
phase: 03-mcp-tool-surface-read-side
verified: 2026-06-25T00:00:00Z
status: verified
score: 6/6 must-haves verified (5/5 SC + Hard Vetoes)
overrides_applied: 0
human_verification_resolved:
  - test: "Started Docker Desktop + `docker compose up -d postgres`, then `python -m alembic -c src/db/alembic.ini current`"
    expected: "alembic current == 0008 (head)"
    result: "PASS — output: `0008 (head)` (resolved 2026-06-25)"
  - test: "With Docker running, `.venv/Scripts/python.exe -m pytest tests/mcp_v2 tests/db -q`"
    expected: "DB-dependent tests pass (testcontainers seeded fixtures: hybrid_search, filing/market/card/note round-trips, peer_view median)"
    result: "PASS — 149 passed, 2 skipped, 18 warnings in 29.23s (resolved 2026-06-25)"
deferred:
  - truth: "get_briefing returns populated briefing entries (found=True, entries non-empty)"
    addressed_in: "Phase 5"
    evidence: "ROADMAP Phase 5 SC#2: 'result is saved in decision_cards with report_type=daily_briefing'; Phase 3 explicitly returns Briefing(found=False, entries=[]) as an honest empty model per the plan's D-01 contract"
---

# Phase 3: MCP Tool Surface (Read-Side) — Verification Report

**Phase Goal:** 타입드 MCP 도구로 삭제된 `src/stock_mcp/`를 대체. FastMCP 2.x 기반. `run_sql` escape hatch 금지.
**Verified:** 2026-06-25
**Status:** VERIFIED (env constraint resolved 2026-06-25 — Docker brought up, DB suite green)
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (SC#1 through SC#5 + Hard Vetoes)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `src/mcp_v2/` is a FastMCP 2.x stdio server; `.mcp.json` registers it | VERIFIED | `src/mcp_v2/__main__.py` calls `mcp.run(transport="stdio")`; `.mcp.json` root registers `"stock-mcp-v2"` with `.venv/Scripts/python.exe -m mcp_v2` |
| 2 | Exactly 10 locked tools registered (no more, no fewer) | VERIFIED | `asyncio.run(mcp.get_tools())` returned 10 names matching LOCKED set exactly; `test_server.py::test_all_tools_registered` PASSED |
| 3 | Every tool returns a Pydantic model (no chunk/raw-dict returns) | VERIFIED | `test_tools_contract.py::test_tool_returns_pydantic_model[*]` — all 10 PASSED; return annotations confirmed via `typing.get_type_hints` |
| 4 | NO `run_sql` escape hatch; CI/AST guard enforced and catches violations | VERIFIED | `test_no_run_sql_guard.py` — all 4 tests PASSED; `test_guard_catches_fstring_sql` self-tests that an f-string `text()` arg raises an AST violation |
| 5 | `hybrid_search` is RRF k=60 over narrative tables only; numeric tables rejected at BOTH tool and retrieval layers | VERIFIED | `retrieval.py:_RRF_K=60`; `_FORBIDDEN_SOURCES=frozenset({"ohlcv","macro_series","decision_cards"})`; rejection in both `tools/search.py:79` and `retrieval.py:288`; `test_hybrid_search.py::test_retrieval_rejects_forbidden_source[*]` and `test_tool_rejects_forbidden_source[*]` PASSED (no DB needed) |
| 6 | All tools route narrative bodies through prompt-injection defense (XML delimiter + pattern prefilter) | VERIFIED | `injection.py:PATTERNS` (6 EN+KO patterns); `wrap_untrusted()` wraps in `<untrusted source="..." ref="...">` delimiter; used by `get_filing`, `get_note`, `hybrid_search` snippet, `get_decision_card` view="both" |

**Score:** 6/6 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/mcp_v2/server.py` | FastMCP stdio server assembly | VERIFIED | Side-effect imports 7 tool modules; `_check_db_connection` fail-fast probe; `server.py:25-45` |
| `src/mcp_v2/__main__.py` | stdio boot entry point | VERIFIED | `mcp.run(transport="stdio")`; all prints routed to `sys.stderr` |
| `src/mcp_v2/_mcp.py` | Shared FastMCP instance | VERIFIED | `FastMCP("stock-mcp-v2", mask_error_details=True)` |
| `src/mcp_v2/models.py` | 13 Pydantic return models | VERIFIED | `extra="forbid"` on all; `FilingDetail`, `SearchFilingsResult`, `OhlcvRange`, `FlowRange`, `PeerView`, `SearchHit`, `SearchResult`, `NoteContent`, `CardView`, `Briefing`, `PortfolioHolding`, `PortfolioView`, `FilingHit` |
| `src/mcp_v2/errors.py` | Typed exception hierarchy | VERIFIED | `McpToolError(ToolError)` base + 6 subclasses; `test_error_model.py::test_base_is_tool_error` PASSED |
| `src/mcp_v2/injection.py` | Prompt injection WRAP+FLAG | VERIFIED | 6 PATTERNS; `detect()`; `wrap_untrusted()` with `_SAFE_ATTR` validation |
| `src/mcp_v2/paths.py` | `safe_resolve` whitelist | VERIFIED | `WHITELIST_PREFIXES=("notes/private/",)`; resolves symlinks before check; `test_paths.py` — 7 PASSED |
| `src/mcp_v2/retrieval.py` | RRF k=60 hybrid core | VERIFIED | `_RRF_K=60`; 3 SQL constants (`_HYBRID_FILINGS_SQL`, `_HYBRID_NEWS_SQL`, `_HYBRID_NOTES_SQL`); BM25+HNSW fusion; `make_snippet` (±200 window) |
| `src/mcp_v2/tools/filing.py` | `get_filing` + `search_filings` | VERIFIED | `get_filing` returns whole `body_md` (Veto #8) wrapped; `search_filings` returns metadata-only `SearchFilingsResult` |
| `src/mcp_v2/tools/market.py` | `ohlcv_range` + `flow_range` + `peer_view` | VERIFIED | Pure numeric (Veto #6 — no injection fields); `peer_view` uses `percentile_cont(0.5)` over `fundamentals` (D-06) |
| `src/mcp_v2/tools/search.py` | `hybrid_search` tool | VERIFIED | Delegates to `retrieval.hybrid_search`; SC#4 source check at tool boundary |
| `src/mcp_v2/tools/card.py` | `get_decision_card` | VERIFIED | Default `view="payload"` excludes `body_md` at serialize time (Veto #13); `view="both"` wraps body (D-03) |
| `src/mcp_v2/tools/note.py` | `get_note` | VERIFIED | Whole disk read (Veto #8); wraps via `injection.wrap_untrusted`; `paths.safe_resolve` whitelist |
| `src/mcp_v2/tools/portfolio.py` | `list_portfolio` | VERIFIED | Delegates to `shared.portfolio.Portfolio.load`; no injection wrap (structured data) |
| `src/mcp_v2/tools/briefing.py` | `get_briefing` | VERIFIED (honest empty) | Returns `Briefing(found=False, entries=[])` — no Phase 5 data yet; intentional D-01 empty model |
| `.mcp.json` | Server registration | VERIFIED | `{"mcpServers":{"stock-mcp-v2":{"command":".venv/Scripts/python.exe","args":["-m","mcp_v2"]}}}` |
| `src/db/migrations/versions/0008_phase03_mcp_surface.py` | notes + fundamentals tables + BM25/HNSW indexes | VERIFIED | `notes` (whole `content_md`, halfvec, bm25_tokens — Veto #8), `fundamentals` (pure numeric, NO embedding — Veto #6), BM25+HNSW indexes on filings/news/notes |
| `src/collectors/fundamentals/` | Fundamentals collector (D-06) | VERIFIED | `collect_fundamentals()` fetches pykrx PER/PBR/EPS/BPS + dart-fss ROE; DB-direct to typed NUMERIC `fundamentals` table; no embedding (Veto #6) |
| `src/collectors/notes_ingest/` | Notes ingest (D-05) | VERIFIED | `upsert_note()` stores whole `content_md` (Veto #8); bge-m3 embedding + mecab-ko BM25; sha256 dedup |
| `tests/mcp_v2/test_no_run_sql_guard.py` | SC#3 AST guard | VERIFIED | 4 tests: registry check + AST f-string check + self-test violation detection + self-test constant acceptance — all PASSED |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `__main__.py` | `server.py` | `from .server import _check_db_connection, mcp` | VERIFIED | Import deferred until after `load_dotenv` |
| `server.py` | 7 tool modules | Side-effect imports in `tools/__init__.py` and tool module registration | VERIFIED | Each tool calls `mcp.tool(annotations=_READ_ONLY)(fn)` at import time |
| `tools/search.py` | `retrieval.py` | `retrieval.hybrid_search(get_engine(), ...)` | VERIFIED | `search.py:85` |
| `retrieval.py` | narrative tables only | `_SOURCE_SQL` keyed on `{"filing","news","note"}` | VERIFIED | No ohlcv/macro_series/decision_cards SQL exists |
| `tools/card.py` | `cards.store` | `store.get_active(get_engine(), corp_code)` | VERIFIED | No direct SQL in card.py (SC#3 clean) |
| `tools/note.py` | `paths.safe_resolve` | `resolved = safe_resolve(_REPO_ROOT, path)` | VERIFIED | `note.py:68` |
| `get_decision_card` | Veto #13 | `model_dump(mode="json", exclude={"body_md"})` for `view="payload"` | VERIFIED | `card.py:79` |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `retrieval.hybrid_search` | `fused` list | SQL: `_HYBRID_FILINGS_SQL`, `_HYBRID_NEWS_SQL`, `_HYBRID_NOTES_SQL` with RRF k=60 | Yes — real DB queries over `filings.body_embedding`, `news.body_embedding`, `notes.content_emb` (BM25+HNSW) | VERIFIED |
| `peer_view` | `median` | SQL: `percentile_cont(0.5)` over `fundamentals` + `entities` sector join | Yes — real `fundamentals` table | VERIFIED |
| `get_briefing` | `entries` | No DB query (Phase 5 column does not exist yet) | Intentionally empty — `found=False` | DEFERRED to Phase 5 |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Exactly 10 tools registered | `asyncio.run(mcp.get_tools()).keys()` | `{flow_range, get_briefing, get_decision_card, get_filing, get_note, hybrid_search, list_portfolio, ohlcv_range, peer_view, search_filings}` — count: 10 | PASS |
| SC#3 AST guard enforces no f-string SQL | `pytest test_no_run_sql_guard.py::test_no_fstring_sql_in_mcp_v2` | PASSED (walks all `src/mcp_v2/*.py`) | PASS |
| SC#3 guard self-tests violation | `pytest test_no_run_sql_guard.py::test_guard_catches_fstring_sql` | PASSED — f-string `text()` arg detected as `ast.JoinedStr` | PASS |
| `hybrid_search` rejects numeric sources at retrieval layer | `retrieval.hybrid_search(None, "q", source_filter="ohlcv")` | raises `InvalidArgument` | PASS |
| `hybrid_search` rejects numeric sources at tool layer | `hybrid_search("q", source_filter="decision_cards")` | raises `InvalidArgument` | PASS |
| All 10 tools return Pydantic model (annotation check) | `pytest test_tools_contract.py::test_tool_returns_pydantic_model[*]` | 10/10 PASSED | PASS |
| stdio transport wired | AST check: `__main__.py` calls `mcp.run(transport='stdio')` | PASSED | PASS |
| All prints to stderr | AST check: no `print()` without `file=sys.stderr` | PASSED | PASS |

---

## Test Results

**Environment:** CPython 3.12.13, Windows 11. Initial run had Docker Desktop down (testcontainers ERRORed); env constraint resolved 2026-06-25 by launching Docker Desktop + `docker compose up -d postgres` (container healthy).

### Full live run (2026-06-25, Docker up)

`.venv/Scripts/python.exe -m pytest tests/mcp_v2 tests/db -q`
→ **149 passed, 2 skipped, 18 warnings in 29.23s**
`alembic current` → **`0008 (head)`**

### `tests/mcp_v2/` — 126 total

| Category | Count | Result |
|----------|-------|--------|
| Non-DB (`-m "not db"`) | 84 | **84 PASSED, 2 SKIPPED** (initial run, no Docker) |
| DB-dependent (`@pytest.mark.db`) | 40 | **PASSED** (live run 2026-06-25, Docker up) |
| Intentional skips | 2 | `test_symlink_escape_forbidden` (Windows symlink privileges); `test_list_portfolio_returns_model` (no portfolio.md in checkout) |

**Pass rate: 149 passed / 2 skipped across `tests/mcp_v2 tests/db` = 100% of runnable tests**

### DB-dependent tests (now confirmed PASS in live run)

These tests cover the behaviors below; verified both in code AND by the live run:

- `test_filing.py` — `get_filing` whole body, `search_filings` metadata, `EntityNotFound` path
- `test_hybrid_search.py` — hit shape (D-02 no body_md), source_filter single-source, empty corpus (D-01), injection flag (D-03/SC#5)
- `test_market.py` — `ohlcv_range` bars, `flow_range` rows, `peer_view` same-sector median (D-06)
- `test_card.py` — `get_decision_card` payload/both views (Veto #13), empty-state
- `test_tools_contract.py` (db subset) — empty states for search_filings, ohlcv/flow, peer_view, hybrid_search

---

## Requirements Coverage

| SC | Description | Status | Evidence |
|----|-------------|--------|----------|
| SC#1 | FastMCP 2.x stdio server; `.mcp.json` registered; exactly 10 locked tools | PASS | Programmatic tool count = 10; `test_server.py` 4/4 PASSED |
| SC#2 | All tools return Pydantic models; no chunk/raw-dict returns | PASS | All 10 return-annotation checks PASSED; `extra="forbid"` on all models |
| SC#3 | No `run_sql`; AST guard enforced; guard catches violations | PASS | `test_no_run_sql_guard.py` 4/4 PASSED; violation self-test confirms catch |
| SC#4 | `hybrid_search` RRF k=60; narrative tables only; numeric tables rejected at BOTH layers | PASS | `_RRF_K=60` in `retrieval.py`; double-rejection confirmed in code + no-DB tests |
| SC#5 | All tools wrap narrative bodies through injection defense (XML delimiter + prefilter) | PASS | `injection.py` 6 patterns; used by 4 tools; `test_injection.py` 9/9 PASSED |
| D-05 | `notes` table + notes-ingest; `hybrid_search` covers private memos | PASS | Migration 0008 creates `notes`; `collectors/notes_ingest/` exists; `_NARRATIVE_SOURCES` includes "notes" |
| D-06 | `fundamentals` table + collector; `peer_view` real same-sector median | PASS | Migration 0008 creates `fundamentals` (pure numeric); `collectors/fundamentals/` exists; `peer_view` uses `percentile_cont(0.5)` |
| Veto #6 | Fundamentals/OHLCV are pure typed columns — NO embedding | PASS | `fundamentals` table: no `content_emb`/`body_embedding` column in migration 0008; `OhlcvRange`/`FlowRange`/`PeerView` models have no injection fields |
| Veto #8 | `get_filing`/`hybrid_search` use whole body, no pre-chunking | PASS | `filing.py:116`: `body = row.body_md  # whole body — Veto #8`; retrieval uses whole rows not chunk joins |
| Veto #13 | `get_decision_card` default returns payload only; body_md on `view="both"` only | PASS | `card.py:79`: `model_dump(mode="json", exclude={"body_md"})` for `view="payload"` |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/mcp_v2/tokenizer.py` | 46 | `return []` | INFO | Valid early-return for empty input — NOT a stub; data-fetching is caller-side |
| `src/mcp_v2/tools/briefing.py` | 46 | `return Briefing(found=False, entries=[])` | INFO | Intentional honest empty model — Phase 5 delivers briefing data; explicitly documented |

No TBD/FIXME/XXX/PLACEHOLDER markers found in `src/mcp_v2/`.

---

## Human Verification — RESOLVED (2026-06-25)

### 1. Alembic Migration at 0008 — ✅ RESOLVED

**Test:** Started Docker Desktop, brought up Postgres (`docker compose up -d postgres`), ran `.venv/Scripts/python.exe -m alembic -c src/db/alembic.ini current`
**Result:** Output `0008 (head)` — confirmed.

### 2. DB-Dependent Test Suite — ✅ RESOLVED

**Test:** With Docker running (`stock-postgres Up (healthy)`), ran `.venv/Scripts/python.exe -m pytest tests/mcp_v2 tests/db -q`
**Result:** **149 passed, 2 skipped, 18 warnings in 29.23s** — all DB-dependent tests pass. The initial `docker.errors.DockerException` errors were a verification-environment issue (Docker daemon down), not a code issue, as predicted.

---

## Gaps Summary

No code gaps found. All 6 SC and all 3 Hard Vetoes are verified by static analysis AND the full live test run (149 passed, 2 skipped). Open items:

1. ~~**Environment gap**: Docker Desktop down~~ — **RESOLVED 2026-06-25**: Docker brought up, `alembic current == 0008`, full `tests/mcp_v2 tests/db` suite green (149 passed, 2 skipped).
2. **`get_briefing` deferred**: The tool is registered and returns the correct `Briefing` Pydantic model, but Phase 5 is required to produce actual briefing data. This is an intentional deferred item, not a gap in Phase 3 scope.

---

## Final Verdict

**PHASE GOAL ACHIEVED** — environment constraint resolved 2026-06-25; full DB-dependent suite green (149 passed, 2 skipped), `alembic current == 0008`.

All static, no-DB, AND live-DB evidence is conclusive:
- `src/mcp_v2/` exists as a complete FastMCP 2.x stdio server
- Exactly 10 locked tools are registered (programmatically confirmed)
- All tools return Pydantic models (annotation-checked)
- No `run_sql` escape hatch exists anywhere in `src/mcp_v2/` (AST-verified + registry-verified)
- `hybrid_search` is RRF k=60 over narrative tables only, with double rejection of numeric sources
- Prompt-injection defense (`injection.py`) wraps all narrative bodies before LLM pipeline
- `notes` + `fundamentals` tables and collectors exist (D-05/D-06)
- All Hard Vetoes (#6, #8, #13) are satisfied by code inspection

The only blocking items are environment-level (Docker down), not code-level.

---

_Verified: 2026-06-25_
_Verifier: Claude (gsd-verifier)_
