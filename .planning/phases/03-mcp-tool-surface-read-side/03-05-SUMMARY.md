---
phase: 03-mcp-tool-surface-read-side
plan: 05
subsystem: collectors + mcp-server
tags: [pykrx, dart-fss, fundamentals, veto-6, coll-07, numeric-tools, peer-view, percentile-cont, d-06, d-04, d-01, sc3-ast-guard, cli]

# Dependency graph
requires:
  - phase: 03-01
    provides: "fundamentals table (PURE NUMERIC per/pbr/eps/bps/roe, PK (ticker, fdate), NO embedding — Veto #6); run_log._ALLOWED_SOURCES + collector_runs.source CHECK widened to include 'fundamentals' (migration 0008, single owner)"
  - phase: 03-03
    provides: "src/mcp_v2 leaf layer — shared mcp (_mcp.py), D-01 errors hierarchy (InvalidArgument/EntityNotFound), pure-numeric return models (OhlcvBar/OhlcvRange/FlowRow/FlowRange/PeerView)"
  - phase: 03-04
    provides: "tool-module registration template (mcp.tool(...)(fn) call form → in-process callables); src/mcp_v2/tools/filing.py et al. on the shared mcp"
  - phase: 01-collector-db-cutover
    provides: "collectors/krx/{client,fetcher,db_writer,__init__} pattern; collectors/dart/financials.get_structured_financials + LINE_ITEM_SYNONYMS; db.entity.resolve_entity; ohlcv table; shared.portfolio.Portfolio.load().scope_tickers()"
provides:
  - "src/collectors/fundamentals/ — collect_fundamentals(*, engine, since=None): pykrx PER/PBR/EPS/BPS + dart-fss ROE, DB-direct upsert to fundamentals (typed NUMERIC), records a 'fundamentals' collector run"
  - "src/collectors/fundamentals/db_writer.upsert_fundamentals — ON CONFLICT (ticker, fdate) DO UPDATE, COALESCE(EXCLUDED.roe, fundamentals.roe) fill-in (no NULL-clobber)"
  - "src/collectors/fundamentals/roe.compute_roe — ROE = 당기순이익 / 자본총계 from dart-fss structured financials (divide-by-zero guard → None)"
  - "stock collect fundamentals CLI subcommand (cmd_collect_fundamentals, --since) wired under 'stock collect'"
  - "src/mcp_v2/tools/market.py — ohlcv_range + flow_range (pure numeric, required from/to dates, no injection wrap) + peer_view (real same-sector percentile_cont(0.5) median over fundamentals); all 3 registered on shared mcp (9/10 locked tools now live)"
affects: [03-06-hybrid_search-server, 04-analysis-runner, 05-briefing, 06-action-gates]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "fundamentals collector ports the KRX collector shape pattern-for-pattern: lazy pykrx client, tenacity @retry fetcher (_RETRYABLE_EXC verbatim), module-level text() upsert with COALESCE preservation, Portfolio.scope_tickers() + per-ticker try/except isolation + resolve_entity pre-write + dual-sink (_log.info('collector_run_complete') + record_collector_run)"
    - "ROE COALESCE fill-in (mirror of KRX T+2 short fill-in): COALESCE(EXCLUDED.roe, fundamentals.roe) so a later pykrx-only refresh (roe=None) never NULL-clobbers a dart-fss ROE that arrived earlier; _values_match_existing treats an incoming None on roe/corp_code as a no-op (skipped)"
    - "peer_view metric→SQL via a FIXED per-metric text() constant map ({per,pbr,roe} → pre-built _PEER_VIEW_*_SQL); the metric arg only SELECTS which constant runs — the column name is hard-coded inside each literal, never f-string-interpolated (SC#3 AST guard stays green, T-metric-sql mitigated)"
    - "numeric MCP tools carry NO injection wrap and NO embedding (Veto #6): ohlcv_range/flow_range/peer_view return typed numbers from typed columns; the only 'embedding'/'injection' tokens in market.py are docstring disclaimers"
    - "tool registration via call form mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(fn) (03-04 template) keeps ohlcv_range/flow_range/peer_view as plain in-process callables for the Phase-4 runner + tests"

key-files:
  created:
    - "src/collectors/fundamentals/__init__.py"
    - "src/collectors/fundamentals/client.py"
    - "src/collectors/fundamentals/fetcher.py"
    - "src/collectors/fundamentals/db_writer.py"
    - "src/collectors/fundamentals/roe.py"
    - "src/mcp_v2/tools/market.py"
    - "tests/collectors/test_fundamentals.py"
    - "tests/cli/__init__.py"
    - "tests/cli/test_collect_fundamentals.py"
    - "tests/mcp_v2/test_market.py"
  modified:
    - "src/cli/commands.py"
    - "src/cli/__main__.py"

key-decisions:
  - "Registration stays in market.py (mcp.tool(...)(fn) at module bottom), NOT in src/mcp_v2/tools/__init__.py. The orchestrator note said 03-04 'registered tools in __init__.py', but 03-04's actual __init__.py is a deliberate empty package marker (its SUMMARY + docstring state aggregation lives in server.py, Plan 06; importing the package registers nothing). The plan's files_modified does NOT list tools/__init__.py, and the plan <action> says 'registering all three on shared mcp' inside market.py. Followed the PLAN (authoritative) + the 03-04 module template; verified all 9 implemented tools co-register on the shared mcp when their modules are co-imported, as plain callables."
  - "peer_view metric column chosen via a fixed per-metric text() constant map (not f-string). The metric string is allow-list-validated against {per,pbr,roe}, then used only as a dict key to pick a pre-built _PEER_VIEW_*_SQL constant. This satisfies the SC#3 AST guard (every text() arg is a string literal) AND closes T-metric-sql (the user string never reaches SQL as a column name)."
  - "ROE is best-effort within collect_fundamentals: a dart-fss failure is caught (roe=None) so the pykrx PER/PBR/EPS/BPS still persist. Combined with the db_writer COALESCE, a ROE arriving on a later run fills in without re-fetching pykrx, and a pykrx-only refresh never wipes a prior ROE."
  - "fundamentals is NOT in tests/conftest.py _LIVE_TABLES (that list predates migration 0008), so pg_clean does not truncate it. Each fundamentals/peer_view test DELETEs the fundamentals rows it owns up-front for isolation rather than editing the shared conftest (scope discipline)."
  - "peer_view counts the sample via count(fnd.<metric>) (not count(*)) so NULL-metric peers don't inflate n; n=0 with median=None is the honest empty model when a sector has no metric-bearing peers (D-01)."

patterns-established:
  - "fundamentals collector dir is the canonical analog for any future pure-numeric collector (typed NUMERIC, COALESCE late-fill, dual-sink observability against an 03-01-owned allow-list)"
  - "numeric MCP tool shape: regex pre-filter → resolve_entity (range tools) → module-level text() → typed Pydantic model with empty-list/None default (D-01); NO injection wrap, NO embedding (Veto #6)"

requirements-completed: ["SC#2", "D-01", "D-04", "D-06", "Veto#6"]

# Metrics
duration: 12 min
completed: 2026-06-07
---

# Phase 3 Plan 05: Fundamentals Pipeline + Numeric MCP Tools Summary

**Built the D-06 fundamentals data pipeline and the three numeric MCP read tools. A new `src/collectors/fundamentals/` collector fetches pykrx PER/PBR/EPS/BPS + derives ROE (당기순이익 / 자본총계) from dart-fss structured financials and DB-direct upserts typed NUMERIC columns to the `fundamentals` table (Veto #6 — never embedded), with a COALESCE ROE fill-in that never NULL-clobbers a prior value; it records a `fundamentals` collector run against Plan 03-01's allow-list (no run_log/CHECK edit). It is exposed via a `stock collect fundamentals` CLI subcommand. `src/mcp_v2/tools/market.py` registers `ohlcv_range` + `flow_range` (pure-numeric bars/rows over a REQUIRED from/to window, D-04, no injection wrap) and `peer_view` (a REAL same-sector `percentile_cont(0.5)` median over `fundamentals`, D-06; `median=None, n=0` for no peers per D-01; metric column chosen via a fixed per-metric `text()` constant so the SC#3 AST guard stays green). 9 of the 10 locked read tools now co-register on the shared `mcp`.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-06-07
- **Completed:** 2026-06-07
- **Tasks:** 3
- **Files modified:** 12 (10 created, 2 modified)

## Accomplishments
- `src/collectors/fundamentals/client.py` — `get_market_fundamental(ticker, date_str)` lazy `from pykrx import stock` → `stock.get_market_fundamental_by_date(date_str, date_str, ticker)` (PER/PBR/EPS/BPS). Mirrors `krx/client.py`.
- `src/collectors/fundamentals/fetcher.py` — `fetch_market_fundamental` with the KRX `@retry(stop=stop_after_attempt(5), wait=wait_exponential, retry=retry_if_exception_type(_RETRYABLE_EXC), reraise=True)` decorator + `_RETRYABLE_EXC` (ReqConnectionError/ChunkedEncodingError/ProtocolError) verbatim.
- `src/collectors/fundamentals/roe.py` — `compute_roe(corp_code, bgn_de)` reuses `collectors.dart.financials.get_structured_financials` (LLM-free; COLL-07) to read 당기순이익 + 자본총계 and returns `당기순이익 / 자본총계`, guarding missing line items and divide-by-zero → `None`.
- `src/collectors/fundamentals/db_writer.py` — `upsert_fundamentals` with module-level `_UPSERT_SQL = text(...)` `INSERT … ON CONFLICT (ticker, fdate) DO UPDATE` where `roe = COALESCE(EXCLUDED.roe, fundamentals.roe)` and `corp_code = COALESCE(...)`; `_TICKER_RE` pre-filter (→ ValueError); `Literal["inserted","updated","skipped"]`; `_values_match_existing` honoring COALESCE semantics so an incoming `None` roe/corp_code is a no-op (skipped). Veto #6 — only typed NUMERIC + key/source columns; no embedding.
- `src/collectors/fundamentals/__init__.py` — `collect_fundamentals(*, engine, since=None)` ports `collect_krx`: `Portfolio.load(Path(".")).scope_tickers()`, per-ticker try/except isolation (COLL-08), empty pykrx frame → `skipped`, missing entity → `stats["failed"]` (R-03), ROE best-effort, dual-sink `_log.info("collector_run_complete", …)` + `record_collector_run(engine, "fundamentals", …)`. `engine=None` → RuntimeError.
- `src/cli/commands.py` + `src/cli/__main__.py` — `cmd_collect_fundamentals` (mirrors `cmd_collect_krx`: builds engine, runs `collect_fundamentals`, prints stats as stdout JSON, exit 1 on failures) and the `fundamentals` subparser (`--since`) registered under `stock collect`. Other subcommands untouched.
- `src/mcp_v2/tools/market.py` — `ohlcv_range(ticker, from_date, to_date) -> OhlcvRange` and `flow_range(...) -> FlowRange`: `_TICKER_RE` (→ InvalidArgument), `resolve_entity` (→ EntityNotFound), REQUIRED dates (D-04, no hard cap), module-level `text()` `SELECT … FROM ohlcv WHERE ticker=:t AND trade_date>=:from_date AND trade_date<=:to_date ORDER BY trade_date`, pure-numeric models with NO injection wrap (Veto #6), zero rows → empty model (D-01). `peer_view(corp_code, metric) -> PeerView`: `_CORP_CODE_RE` (→ InvalidArgument), metric allow-list `{per,pbr,roe}` (→ InvalidArgument), fixed per-metric `text()` constant computing `percentile_cont(0.5) WITHIN GROUP (ORDER BY fnd.<metric>)` joined on `entities.sector`; no peers / NULL sector → `PeerView(median=None, n=0)` (D-01).

## Task Commits

Each task was committed atomically:

1. **Task 1: fundamentals collector (client/fetcher/db_writer/roe/__init__) + test** — `f6407c3` (feat)
2. **Task 2: `stock collect fundamentals` CLI subcommand + parse test** — `4d64e29` (feat)
3. **Task 3: market.py — ohlcv_range, flow_range, peer_view + test** — `1797d4d` (feat)

**Plan metadata:** committed with this SUMMARY (docs).

## Files Created/Modified
- `src/collectors/fundamentals/__init__.py` (CREATED) — `collect_fundamentals` orchestration + run recording.
- `src/collectors/fundamentals/client.py` (CREATED) — pykrx `get_market_fundamental` wrapper.
- `src/collectors/fundamentals/fetcher.py` (CREATED) — tenacity retry wrapper.
- `src/collectors/fundamentals/db_writer.py` (CREATED) — `upsert_fundamentals` typed NUMERIC upsert with ROE COALESCE.
- `src/collectors/fundamentals/roe.py` (CREATED) — ROE from dart-fss structured financials (COLL-07).
- `src/mcp_v2/tools/market.py` (CREATED) — ohlcv_range / flow_range / peer_view, registered on shared mcp.
- `src/cli/commands.py` (MODIFIED) — added `cmd_collect_fundamentals` + `__all__` entry.
- `src/cli/__main__.py` (MODIFIED) — registered the `fundamentals` subparser.
- `tests/collectors/test_fundamentals.py` (CREATED) — 6 db tests (typed row, run recorded, missing-entity isolation, empty skip, ROE COALESCE fill-in across 3 runs, engine=None raises).
- `tests/cli/__init__.py` (CREATED) — test package marker.
- `tests/cli/test_collect_fundamentals.py` (CREATED) — 4 no-db parse tests (dispatch + since, registration without since, unknown subcommand errors, help listing).
- `tests/mcp_v2/test_market.py` (CREATED) — 14 db tests (ordered bars, inclusive window, empty model, bad/unknown ticker, flow rows, real 2-peer median per/pbr/roe, other-sector exclusion, no-peers empty, NULL-sector empty, bad metric/corp_code).

## Decisions Made
- **Registration kept in market.py, not tools/__init__.py.** The orchestrator note claimed 03-04 registered tools in `tools/__init__.py`, but 03-04's `__init__.py` is an intentional empty marker (per its SUMMARY/docstring: aggregation lives in `server.py`, Plan 06). The plan's `files_modified` excludes `tools/__init__.py` and its `<action>` registers on the shared mcp inside `market.py`. Followed the plan + the 03-04 module template; empirically confirmed all 9 implemented tools (`get_filing`, `search_filings`, `get_decision_card`, `get_note`, `list_portfolio`, `get_briefing`, `ohlcv_range`, `flow_range`, `peer_view`) co-register on the shared `mcp` as plain callables.
- **peer_view metric via fixed per-metric `text()` constants.** Allow-list validate metric, then pick a pre-built `_PEER_VIEW_{PER,PBR,ROE}_SQL` constant by dict key — the column name is hard-coded inside each literal, never interpolated. Satisfies SC#3 AST guard and closes T-metric-sql.
- **`count(fnd.<metric>)` for n.** Sample size counts only metric-bearing peers, so NULL-metric rows don't inflate `n`; honest `n=0`/`median=None` empty model (D-01).
- **fundamentals test isolation via explicit DELETE.** `fundamentals` isn't in `_LIVE_TABLES`, so tests clean their own rows rather than mutating the shared conftest (scope discipline).

## Deviations from Plan

None — plan executed as written. The only judgement call was the `tools/__init__.py` registration question raised by the orchestrator note; resolved in favor of the authoritative plan (registration in `market.py`, matching the 03-04 template) — documented under Decisions Made, not a code deviation.

## Known Stubs
None. The fundamentals collector writes real typed values; `peer_view` computes a real `percentile_cont(0.5)` median over the live `fundamentals` table (proven against 2 seeded same-sector peers, median 15.0 for {10,20}). `median=None, n=0` for no peers is the plan-specified honest empty model (D-01), not a stub.

## Threat Flags
None beyond the plan's threat model.
- **T-veto6 (mitigate):** fundamentals = typed NUMERIC only (no embedding column/usage); ohlcv_range/flow_range/peer_view return pure numbers with no injection wrap — grep confirms `embedding`/`injection` tokens appear only in docstring disclaimers.
- **T-metric-sql (mitigate):** metric allow-listed {per,pbr,roe}; column chosen via fixed per-metric `text()` constant, never f-string (SC#3 AST guard green).
- **T-SQL-arg (mitigate):** ticker/corp_code ASCII regex pre-filter before DB; all SQL parameterized module-level `text()`.
- **T-coll07 (mitigate):** fundamentals collector imports no anthropic/openai (tests/test_import_guard.py green); ROE uses the in-tree dart-fss helper.
- **T-03-08 (accept):** ohlcv_range/flow_range range is caller-owned (D-04 — no hard cap), per locked decision.

## Verification Results
- `tests/collectors/test_fundamentals.py` — 6 passed (`-m db`, live Postgres at migration 0008).
- `tests/mcp_v2/test_market.py` — 14 passed (`-m db`).
- `tests/cli/test_collect_fundamentals.py` — 4 passed (`-m "not db"`).
- `tests/test_import_guard.py` — 4 passed (COLL-07; no LLM SDK under collectors/).
- `tests/mcp_v2/test_no_run_sql_guard.py` — 3 passed / 1 skipped (`test_no_fstring_sql_in_mcp_v2` green over market.py; registry check still staged for Plan 06's server.py).
- `tests/test_cli_collect_all.py` — 11 passed (no regression in existing collect subcommands).
- All 9 implemented tools confirmed co-registering on the shared `mcp` as in-process callables.
- ruff check + ruff format clean on all created/modified files.

## User Setup Required
None. No new dependencies (pykrx/dart-fss/tenacity already installed), no migrations (`fundamentals` table exists at 0008), no env changes. `stock collect fundamentals --since YYYY-MM-DD` runs against the live portfolio scope once data is desired; tests use fixtures/mocks (no live KRX/DART network).

## Next Phase Readiness
- 9 of 10 locked read tools are implemented and registered; only `hybrid_search` + the `server.py` aggregation (Plan 03-06) remain. The SC#3 registry guard flips from skip to enforced once `mcp_v2.server` imports all tool modules — the 9 implemented tools already co-register cleanly.
- The `fundamentals` table now has a real collector + CLI, so `peer_view` returns real medians and the Phase-4 analysis runner can call all numeric tools in-process.
- No blockers.

## Self-Check: PASSED

All 10 created files exist on disk (5 fundamentals modules + market.py + 4 test files incl. tests/cli/__init__.py — all FOUND) and both modified CLI files carry the new subcommand. All three task commits (`f6407c3`, `4d64e29`, `1797d4d`) present in git log. 20 db tests + 11 no-db guard tests green (1 staged skip). SC#3 AST guard green over market.py. No file deletions in any commit. ruff clean.

---
*Phase: 03-mcp-tool-surface-read-side*
*Completed: 2026-06-07*
