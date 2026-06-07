---
phase: 03-mcp-tool-surface-read-side
plan: 06
subsystem: mcp-server
tags: [fastmcp, hybrid-search, rrf-k60, pgvector, vchord-bm25, halfvec, stdio, references-not-blobs, sc1, sc3, sc4, d-02, d-04, prompt-injection, registry-guard, server-aggregation]

# Dependency graph
requires:
  - phase: 03-01
    provides: "migration 0008 (notes + fundamentals + bm25_tokens INT[] + BM25 ix_{filings,news,notes}_bm25 + HNSW halfvec_cosine_ops indexes), APPLIED to live DB (alembic current==0008); .mcp.json spawning .venv python -m mcp_v2"
  - phase: 03-02
    provides: "src/mcp_v2/embedding.encode_query (bge-m3, LRU) + tokenizer.tokenize_ko (mecab-ko INT[]); notes-ingest + backfill_narrative so filings/news/notes carry non-NULL body_embedding/bm25_tokens; seeded_narrative_engine fixture; SC#3 AST guard + skip-tolerant registry guard"
  - phase: 03-03
    provides: "src/mcp_v2 leaf layer — shared mcp (_mcp.py), D-01 McpToolError hierarchy (InvalidArgument/DataBackendError), SearchHit/SearchResult models, injection.wrap_untrusted/detect (D-03)"
  - phase: 03-04
    provides: "6 read tools (filing/card/note/portfolio/briefing) + the mcp.tool(...)(fn) call-form registration template (in-process callables); tools/__init__.py empty marker"
  - phase: 03-05
    provides: "3 numeric tools (market.py: ohlcv_range/flow_range/peer_view); fundamentals collector → real peer_view medians"
provides:
  - "src/mcp_v2/retrieval.py — RRF k=60 hybrid retrieval core (dense pgvector HNSW halfvec <=> + VectorChord-BM25 search_bm25query, FULL OUTER JOIN per narrative source) over WHOLE-body filings/news/notes (Veto #8); make_snippet ±200 match-window; source_filter naming ohlcv/macro_series/decision_cards → InvalidArgument at the retrieval layer (SC#4, Veto #6)"
  - "src/mcp_v2/tools/search.py — hybrid_search (10th locked tool) on the shared mcp; references+snippets only (D-02), default limit=10 (D-04), SC#4 forbidden-source rejection at the tool boundary"
  - "src/mcp_v2/server.py — FastMCP assembly: side-effect-imports all 7 tool modules so the shared mcp holds EXACTLY the 10 locked tools (SC#1); _check_db_connection SELECT 1 fail-fast → DataBackendError"
  - "src/mcp_v2/__main__.py — python -m mcp_v2 stdio entry point (load_dotenv → _check_db_connection → mcp.run(transport=stdio)); stderr-only diagnostics (Pitfall 7)"
  - "tests: test_hybrid_search.py (retrieval + tool layers), test_server.py (SC#1 registry + stdio/stderr AST), test_tools_contract.py (SC#2 + D-01 per-tool); test_no_run_sql_guard registry guard now ENFORCED (SC#3)"
affects: [04-analysis-runner, 05-briefing, 06-action-gates]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "RRF k=60 over whole-body narrative tables: per-source module-level text() CTE with a dense side (ROW_NUMBER OVER (ORDER BY <emb> <=> CAST(:qvec AS halfvec)) LIMIT 50) + a sparse side (ROW_NUMBER OVER (ORDER BY bm25_catalog.search_bm25query((bm25_tokens)::bm25vector, to_bm25query('ix_<t>_bm25'::regclass, CAST(:qtoks AS int[])::bm25vector)) ASC NULLS LAST) LIMIT 50) fused via COALESCE(1.0/(60+dense.rk),0)+COALESCE(1.0/(60+sparse.rk),0) over FULL OUTER JOIN USING (id); k=60 is the inline literal AND _RRF_K module constant (never a parameter, SC#4)"
    - "candidate = one WHOLE row per Veto #8 (filings.rcept_no / news.id::text / notes.path) — no chunk join; notes carry no date axis so date_range applies only to filings.filed_at / news.published_at"
    - "SET hnsw.iterative_scan='relaxed_order' once per connection before the per-source queries (Pitfall 2 — filtered HNSW recall); NULL filter binds CAST-guarded (Pitfall 3 — psycopg3 AmbiguousParameter)"
    - "references-not-blobs (D-02): retrieval fetches the body per top hit ONLY to cut a make_snippet ±200 match-window (300-char head fallback), wraps it via injection.wrap_untrusted + detect (D-03/SC#5), and returns SearchHit(source_type, id_or_path, rrf_score, snippet, injection_*) — the model has NO body_md field at all"
    - "server aggregation: server.py side-effect-imports the 7 tool modules (from .tools import briefing, card, filing, market, note, portfolio, search) so every mcp.tool(...)(fn) registration runs; mcp lives in _mcp.py to keep server↔tool imports acyclic"
    - "stdio entry: __main__ load_dotenv → import server → _check_db_connection (McpToolError → print(stderr)+exit 1) → mcp.run(transport='stdio'); all diagnostics stderr (Pitfall 7 — stdout is the JSON-RPC frame)"

key-files:
  created:
    - "src/mcp_v2/retrieval.py"
    - "src/mcp_v2/tools/search.py"
    - "src/mcp_v2/server.py"
    - "src/mcp_v2/__main__.py"
    - "tests/mcp_v2/test_hybrid_search.py"
    - "tests/mcp_v2/test_server.py"
    - "tests/mcp_v2/test_tools_contract.py"
  modified:
    - "tests/mcp_v2/test_no_run_sql_guard.py"

key-decisions:
  - "BM25 API = search_bm25query/to_bm25query/bm25_ops (the archive 0002 surface), NOT the newer <&> operator the RESEARCH skeleton listed as an alternative. Verified against the LIVE tensorchord/vchord-suite:pg17-latest image via \\df bm25_catalog.* — only search_bm25query(bm25vector, bm25query) + to_bm25query(regclass, bm25vector) exist (no <&> operator). This resolves RESEARCH assumption A1 in favor of the archive API."
  - "_RRF_K=60 is BOTH a module constant AND the inline literal 60 in every fusion tail (the archive style), rather than a :k bind (the RESEARCH skeleton's :k). Hard-coding 60 in the SQL makes SC#4 'k=60 is not a parameter' literally true at the SQL layer — there is no bind that could override it."
  - "hybrid_search rejects forbidden sources at BOTH layers: the tool boundary (tools/search.py — early/clear caller error) AND the retrieval core (retrieval._validate_source_filter — defense in depth, since the Phase-4 runner may call retrieval.hybrid_search directly without the tool). The plan's acceptance_criteria explicitly require macro_series rejection at the retrieval layer, not only in Task 2."
  - "snippet match-window uses the RAW whitespace surface terms of the query (qtoks_terms = query.split()), NOT the mecab-ko INT token ids — str.find needs surface substrings; the INT ids are for the BM25 index only. Falls back to the 300-char body head for a pure-dense hit."
  - "notes have no date axis: notes.updated_at is an ingest timestamp, not a filed/published date, so date_range is NOT applied to the notes CTE (only corp_code). filings.filed_at / news.published_at carry the half-open [from, to) date filter."
  - "server.py imports 7 tool modules (filing/market/search/note/card/portfolio/briefing) = the 10 tools (filing=2, market=3, search=1, +4 singles). The archive imported 9 modules for its different tool set; v2.0's 7-module split is the 03-04/03-05 reality."
  - "test_server stdio/stderr assertions are STRUCTURAL (AST over __main__.py), not a subprocess: running main() would start the blocking stdio loop. The AST asserts mcp.run(transport='stdio') is called and every print() targets sys.stderr (Pitfall 7)."

patterns-established:
  - "RRF k=60 whole-body hybrid retrieval is the canonical narrative-search analog for any future search tool; numeric tables are structurally excluded (forbidden-source guard + narrative-only SQL)"
  - "FastMCP server aggregation = _mcp.py (shared instance) + server.py (side-effect tool imports + db health) + __main__.py (stdio boot, stderr-only); the registry guard (==N locked names, no run_sql) becomes an enforced CI gate the moment server.py exists"

requirements-completed: ["SC#1", "SC#2", "SC#3", "SC#4", "SC#5", "D-01", "D-02", "D-03", "D-04"]

# Metrics
duration: 11 min
completed: 2026-06-07
---

# Phase 3 Plan 06: hybrid_search + Server Aggregation (phase close) Summary

**Closed Phase 3 by landing the data-dependent retrieval wave: `retrieval.py` implements the RRF k=60 hybrid core (pgvector HNSW `halfvec` dense `<=>` + VectorChord-BM25 `search_bm25query` sparse, fused via `COALESCE(1.0/(60+rk),0)` over a `FULL OUTER JOIN`) over the WHOLE-body `filings`/`news`/`notes` tables (Veto #8 — one candidate is one whole row, no chunk join), with `SET hnsw.iterative_scan='relaxed_order'` per session, NULL-cast filter guards, and a ±200-char match-window snippet. `tools/search.py` registers the 10th and final locked tool `hybrid_search` (references + snippet only — D-02; default `limit=10` — D-04), which rejects `ohlcv`/`macro_series`/`decision_cards` as `source_filter` at BOTH the tool boundary and the retrieval layer (SC#4, Veto #6). `server.py` side-effect-imports all 7 tool modules so the shared `mcp` holds EXACTLY the 10 locked tools (SC#1) and adds a `SELECT 1` fail-fast `_check_db_connection`; `__main__.py` makes `python -m mcp_v2` boot the FastMCP stdio server (stderr-only diagnostics, Pitfall 7) — exactly what `.mcp.json` spawns. The previously skip-tolerant SC#3 registry guard is now ENFORCED (`== 10` locked names, no `run_sql`-class tool). All snippets are `<untrusted>`-wrapped + injection-flagged (D-03/SC#5).**

## Performance

- **Duration:** ~11 min
- **Started:** 2026-06-07
- **Completed:** 2026-06-07
- **Tasks:** 3
- **Files modified:** 8 (7 created, 1 modified)

## Accomplishments
- `src/mcp_v2/retrieval.py` — `hybrid_search(engine, query, source_filter=None, date_range=None, limit=10) -> list[SearchHit]`. Embeds the query (`embedding.encode_query`, bge-m3), tokenizes it (`tokenizer.tokenize_ko`, mecab-ko INT[]), runs one of three module-level `text()` RRF CTEs per requested narrative source, fuses by `rrf_score` and caps at `limit`. Per top hit it fetches the body ONLY to cut a `make_snippet` ±200 match-window (300-char head fallback), wraps via `injection.wrap_untrusted` + flags via `injection.detect`, and builds a `SearchHit` with NO `body_md` (D-02). `_RRF_K=60` is a module constant; `60` is the inline literal in every fusion tail (SC#4 — never a bind). `_validate_source_filter` raises `InvalidArgument` for `ohlcv`/`macro_series`/`decision_cards` (and unknown names) at the retrieval layer; DB faults → `DataBackendError`.
- `src/mcp_v2/tools/search.py` — `hybrid_search(query, source_filter=None, date_range=None, limit=10) -> SearchResult` registered on the shared `mcp` (call form, read-only). Rejects forbidden numeric/structured sources at the tool boundary (SC#4), delegates to `retrieval.hybrid_search(get_engine(), ...)`, wraps hits in `SearchResult(hits=[...])`. Default `limit=10` (D-04); empty corpus → `SearchResult(hits=[])` (D-01). This is the 10th/final locked tool — the surface is now complete.
- `src/mcp_v2/server.py` — imports the shared `mcp` from `._mcp`, side-effect-imports all 7 tool modules (`from .tools import briefing, card, filing, market, note, portfolio, search`) so every `mcp.tool(...)(fn)` registration runs; `mcp.get_tools()` then holds EXACTLY the 10 locked names (SC#1). `_check_db_connection()` runs `SELECT 1` and raises `DataBackendError` (a `ToolError` subclass, not the archive `StructuredError` dict) on failure.
- `src/mcp_v2/__main__.py` — `python -m mcp_v2` entry: `load_dotenv(find_dotenv(usecwd=True))`, import `_check_db_connection, mcp` from server, run the check (`McpToolError` → `print(str(e), file=sys.stderr); sys.exit(1)`), then `mcp.run(transport="stdio")`. Diagnostics go to stderr only — stdout is the JSON-RPC protocol (Pitfall 7). Matches the `.mcp.json` (03-01) command `["-m", "mcp_v2"]`.
- `tests/mcp_v2/test_hybrid_search.py` — 16 tests across both layers: retrieval-layer + tool-layer forbidden-source rejection (ohlcv/macro_series/decision_cards ×3 each), `make_snippet` match-window + head-fallback, `test_no_body_md` (D-02), seeded-corpus hit shape (wrapped snippet + rrf_score, source_type ∈ {filing,news,note}), single-source filter, injection-flag wrap (D-03/SC#5), empty corpus → `hits=[]` (D-01), default `limit<=10` (D-04).
- `tests/mcp_v2/test_server.py` — SC#1 `test_all_tools_registered` (== 10 locked names), `_check_db_connection` export, AST assertion that `__main__` calls `mcp.run(transport='stdio')` and every `print()` targets `sys.stderr` (Pitfall 7).
- `tests/mcp_v2/test_tools_contract.py` — SC#2 Layer 1: every one of the 10 tool callables has a Pydantic-`BaseModel` return annotation (parametrized). Layer 2 (D-01): per-tool empty-state validity — `get_briefing` honest empty (no DB), `search_filings`/`ohlcv_range`/`flow_range`/`peer_view`/`get_decision_card`/`hybrid_search` empty models over seeded entities (db), `list_portfolio` valid model (skips gracefully when `notes/private/portfolio.md` is absent).
- `tests/mcp_v2/test_no_run_sql_guard.py` (MODIFIED) — removed the `try/except ImportError → skip` on `test_only_locked_tools_registered`; it now imports `mcp_v2.server` and ENFORCES the `== 10` locked-name set + no `run_sql`/`execute_sql`/`raw_sql`/`query`/`sql`/`exec_sql` tool (SC#3). Docstring updated to reflect enforced state.

## Task Commits

Each task was committed atomically:

1. **Task 1: retrieval.py — RRF k=60 over whole-body filings/news/notes + snippet** — `2512d06` (feat)
2. **Task 2: tools/search.py — hybrid_search tool (D-02/D-04/SC#4) + test_hybrid_search.py** — `723a87f` (feat)
3. **Task 3: server.py + __main__ stdio wiring; enforce SC#1/SC#2/SC#3 guards** — `a53c815` (feat)

**Plan metadata:** committed with this SUMMARY (docs).

## Files Created/Modified
- `src/mcp_v2/retrieval.py` (CREATED) — RRF k=60 dense+BM25 fusion over whole-body narrative tables; make_snippet; retrieval-layer forbidden-source guard.
- `src/mcp_v2/tools/search.py` (CREATED) — hybrid_search tool (10th locked tool); references+snippets only; default limit=10; SC#4 boundary rejection.
- `src/mcp_v2/server.py` (CREATED) — FastMCP assembly (side-effect imports of 7 tool modules) + _check_db_connection.
- `src/mcp_v2/__main__.py` (CREATED) — python -m mcp_v2 stdio entry point; stderr-only diagnostics.
- `tests/mcp_v2/test_hybrid_search.py` (CREATED) — 16 retrieval+tool tests (SC#4/D-02/D-03/D-04/D-01).
- `tests/mcp_v2/test_server.py` (CREATED) — SC#1 registry + stdio/stderr AST asserts.
- `tests/mcp_v2/test_tools_contract.py` (CREATED) — SC#2 return-model contract + D-01 per-tool empty states.
- `tests/mcp_v2/test_no_run_sql_guard.py` (MODIFIED) — registry guard skip removed → ENFORCED (SC#3).

## Decisions Made
- **BM25 API verified against the live image.** Ran `\df bm25_catalog.*` on the running `stock-postgres` (tensorchord/vchord-suite:pg17-latest): only `search_bm25query(bm25vector, bm25query)` + `to_bm25query(regclass, bm25vector)` exist — no `<&>` operator. Used the archive's `search_bm25query` API (RESEARCH A1 resolved), with `ASC NULLS LAST` ranking (BM25 scores are negative; Pitfall 4).
- **k=60 is an inline SQL literal, not a bind.** `_RRF_K=60` is the module constant for readability; the fusion tail hard-codes `60` so no parameter could ever override it — SC#4 "k=60 is fixed" is literally true at the SQL layer.
- **Forbidden-source rejection at both layers.** The tool boundary rejects for a clear early caller error; `retrieval._validate_source_filter` also rejects so the Phase-4 runner (which may call `retrieval.hybrid_search` directly) is equally protected. The plan's acceptance criteria require macro_series rejection AT the retrieval layer.
- **Snippet match window uses raw surface terms, not mecab INT ids.** `str.find` needs substrings; the INT token ids are for the BM25 index, not for snippet windowing.
- **server.py imports 7 modules = 10 tools.** v2.0's 7-module split (filing=2, market=3, search=1, +4 singles) differs from the archive's 9 — followed the 03-04/03-05 reality.
- **Structural stdio/stderr asserts.** test_server checks `__main__.py` via AST (not a subprocess) because running `main()` starts the blocking stdio loop.

## Deviations from Plan

None — plan executed as written. Two judgement calls, both within the plan's stated discretion / explicit instructions:
- The PLAN `<interfaces>` block and RESEARCH A1 directed verifying the BM25 operator against the live image; the `\df` probe confirmed `search_bm25query` (the archive API the PLAN's interfaces section specified), not the alternative `<&>` operator the RESEARCH skeleton listed. No deviation — the plan told me to verify and adapt.
- Forbidden-source rejection implemented at BOTH the tool and retrieval layers as the plan's acceptance criteria explicitly require (Task 1 AC: "assert all three [ohlcv/macro_series/decision_cards] in test_hybrid_search.py against retrieval.hybrid_search directly").

## Verification Results
- `tests/mcp_v2/test_hybrid_search.py` — 16 passed (retrieval-layer no-DB rejections/snippets + db hit-shape/tool/injection/empty).
- `tests/mcp_v2/test_server.py` — 4 passed (SC#1 registry + stdio/stderr AST).
- `tests/mcp_v2/test_tools_contract.py` — passed (10 return-annotation params + per-tool empty states; `list_portfolio` skips when portfolio.md absent).
- `tests/mcp_v2/test_no_run_sql_guard.py` — registry guard now ENFORCED and green (== 10 names, no run_sql); AST f-string guard green over all of src/mcp_v2 (incl. retrieval.py/search.py/server.py).
- Full `tests/mcp_v2/` suite: **124 passed, 2 skipped** (symlink-no-privilege + portfolio.md-absent). With `tests/db/`: **149 passed, 2 skipped**.
- Live boot smoke: `python -m mcp_v2` path — `_check_db_connection()` passes against the live `.env` DB and `mcp.get_tools()` returns 10 tools. `.mcp.json` spawns `.venv python -m mcp_v2` (matches the entry point).
- ruff check + ruff format clean on all created/modified files. No file deletions in any commit.

## Known Stubs
None. `hybrid_search` runs the real RRF k=60 fusion against live pgvector HNSW + VectorChord-BM25 indexes (proven against the seeded narrative corpus — filings/news/notes hits with non-empty wrapped snippets and positive rrf_scores). The `_StubEmbedder`/monkeypatched `encode_query` in tests is a TEST double (deterministic vector to skip the ~2GB bge-m3 download), not a production stub; the production `encode_query` is the real bge-m3 leaf.

## Threat Flags
None beyond the plan's threat model.
- **T-veto6 (mitigate):** hybrid_search SQL touches only filings/news/notes; `source_filter` naming ohlcv/macro_series/decision_cards → InvalidArgument at both layers (tests assert all three at both).
- **T-prompt-inj (mitigate):** every snippet is `<untrusted>`-wrapped + injection-flagged (D-03); SearchHit has no body_md (D-02, `test_no_body_md`).
- **T-SQL-escape (mitigate):** registry guard ENFORCED (==10 names, no run_sql-class tool, SC#3); all retrieval SQL is module-level `text()` constants (AST guard green).
- **T-stdout-corrupt (mitigate):** `__main__` logs/errors to stderr only; only FastMCP writes protocol stdout (AST-asserted, Pitfall 7).
- **T-03-token-DoS (mitigate):** default top-10 (D-04); references-not-blobs (D-02).
- **T-db-fault (mitigate):** `_check_db_connection` + retrieval DB faults → `DataBackendError`; FastMCP `mask_error_details=True` masks unexpected bugs.

## User Setup Required
None. No new dependencies, no migrations (schema at 0008), no env changes. `.mcp.json` already registers the server; restart Claude Code to load the 10 tools. The first real (non-test) `hybrid_search` query downloads bge-m3 (~2GB) to the HuggingFace cache; tests avoid this via the stubbed `encode_query`.

## Next Phase Readiness
- **Phase 3 is COMPLETE.** All 10 locked read-side tools are implemented, registered, and tested; the FastMCP stdio server boots via `python -m mcp_v2`; SC#1 (10-tool registry), SC#2 (Pydantic-model returns + empty states), SC#3 (no run_sql / AST guard), SC#4 (narrative-only RRF k=60), SC#5/D-02/D-03/D-04 (wrap+flag, references-not-blobs, top-10) all green.
- The Phase-4 analysis runner can call any tool in-process (all are plain callables) or via the MCP transport; `retrieval.hybrid_search` is directly importable for the Bull/Bear/Judge sub-agents.
- No blockers.

## Self-Check: PASSED

All 7 created files exist on disk (retrieval.py, tools/search.py, server.py, __main__.py, test_hybrid_search.py, test_server.py, test_tools_contract.py — all FOUND) and the modified test_no_run_sql_guard.py carries the enforced registry guard. All three task commits (`2512d06`, `723a87f`, `a53c815`) present in git log. 16 hybrid_search + 4 server + contract tests green; full mcp_v2 suite 124 passed / 2 skipped; mcp_v2+db 149 passed / 2 skipped. SC#3 registry guard enforced (== 10 names). Live `python -m mcp_v2` boot path verified (DB OK, 10 tools). No file deletions in any commit. ruff clean.

---
*Phase: 03-mcp-tool-surface-read-side*
*Completed: 2026-06-07*
