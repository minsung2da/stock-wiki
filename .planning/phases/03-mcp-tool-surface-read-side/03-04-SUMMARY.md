---
phase: 03-mcp-tool-surface-read-side
plan: 04
subsystem: mcp-server
tags: [fastmcp, pydantic-v2, read-tools, whole-body, veto-13, prompt-injection, wrap-flag, path-traversal, empty-model, tool-registration]

# Dependency graph
requires:
  - phase: 03-03
    provides: "src/mcp_v2 leaf layer — shared mcp (_mcp.py), D-01 errors hierarchy, 12 return models (FilingDetail/SearchFilingsResult/CardView/NoteContent/PortfolioView/Briefing), injection.wrap_untrusted+detect (D-03), paths.safe_resolve (V12)"
  - phase: 03-02
    provides: "tests/mcp_v2 package + seeded_engine/seeded_narrative_engine fixtures + SC#3 run_sql AST guard (enforced, grows over new tool files)"
  - phase: 02-decision-card-schema-storage
    provides: "src/cards/store.get_active (full typed DecisionCard, Veto #13 serialize-time view layering) + DecisionCard model"
  - phase: 01-collector-db-cutover
    provides: "filings table (rcept_no PK, corp_code/ticker/filed_at/report_nm/event_type/source_url/body_md); db.entity.resolve_entity; db.engine.get_engine"
provides:
  - "src/mcp_v2/tools/__init__.py — empty package marker (server.py aggregation is Plan 06; importing the package registers nothing)"
  - "src/mcp_v2/tools/filing.py — get_filing (whole body_md, Veto #8, <untrusted>+flags) + search_filings (metadata, filed_at DESC, limit=50 D-04, NULL-cast filter guards)"
  - "src/mcp_v2/tools/card.py — get_decision_card wrapping cards.store.get_active; view='payload' (default) excludes body_md at serialize time (Veto #13), view='both' wraps body (D-03)"
  - "src/mcp_v2/tools/note.py — get_note disk-whitelist read-only (safe_resolve) + injection wrap (D-03/D-05)"
  - "src/mcp_v2/tools/portfolio.py — list_portfolio passthrough of shared.portfolio.Portfolio.load -> PortfolioView; PortfolioLoadError -> DataBackendError"
  - "src/mcp_v2/tools/briefing.py — get_briefing honest empty model (Briefing(found=False, entries=[])); Phase 5 wires report_type data"
affects: [03-06-hybrid_search-server, 04-analysis-runner]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "tool registration via the CALL form mcp.tool(annotations=...)(fn) instead of @mcp.tool decoration: the decorator REPLACES the module name with a non-callable FunctionTool wrapper (verified empirically — `foo.fn` holds the original callable). Registering by call leaves get_filing/etc. as PLAIN callables so the analysis runner + the tests can call them in-process, while still adding them to the FastMCP tool surface."
    - "whole-body return (Veto #8): get_filing selects body_md and returns it UNSLICED, wrapped via injection.wrap_untrusted(body, 'dart', rcept_no); injection_suspected=bool(detect(body)) + injection_flags=[pattern_id...]"
    - "search_filings NULL-cast filter guards: one parameterized text() covers all (event_type/since/until) combinations via `CAST(:x AS …) IS NULL OR col = …` — no SQL string concatenation (SC#3-safe). until is half-open (< :until)."
    - "Veto #13 view projection is a serialize-time exclude on the already-fetched card (card.model_dump(exclude={'body_md'})) — NO re-query; the body_md only materializes (and gets D-03-wrapped) on explicit view='both'"
    - "get_note derives a wrap_untrusted-safe ref from the path (non-[A-Za-z0-9_:.-] -> '_', 'note:' prefix) so the <untrusted ref=...> attr always passes injection._SAFE_ATTR while NoteContent.path still echoes the verbatim path"
    - "D-01 split honored per-tool: zero rows = empty model (SearchFilingsResult(hits=[]) / CardView(found=False) / Briefing(found=False, entries=[]) / empty PortfolioView); genuine fault = raised McpToolError subclass (FilingNotFound/EntityNotFound/InvalidArgument/NotePathForbidden/NoteNotFound/DataBackendError)"

key-files:
  created:
    - "src/mcp_v2/tools/__init__.py"
    - "src/mcp_v2/tools/filing.py"
    - "src/mcp_v2/tools/card.py"
    - "src/mcp_v2/tools/note.py"
    - "src/mcp_v2/tools/portfolio.py"
    - "src/mcp_v2/tools/briefing.py"
    - "tests/mcp_v2/test_filing.py"
    - "tests/mcp_v2/test_card.py"
    - "tests/mcp_v2/test_note.py"
    - "tests/mcp_v2/test_portfolio_briefing.py"
  modified: []

key-decisions:
  - "Registration by call form mcp.tool(...)(fn), not @mcp.tool decoration — the decorator yields a FunctionTool that is NOT callable (TypeError on direct call), which broke the first test run. Probed fastmcp 2.14.7: the decorated object exposes the original callable on .fn, but rather than make every in-process caller reach through .fn, registering by call keeps the public name a plain function AND registers the tool. This matches how Phase-4 analysis runner is expected to call these tools directly."
  - "get_note keeps a DISK read (notes/private/ via safe_resolve), NOT a notes-table read (D-05) — even though Plan 02 ingests notes into a notes table for hybrid_search, a single-memo fetch reads the source-of-truth disk file. The table is the search index."
  - "search_filings since/until are ISO-8601 STRING args cast to timestamptz in SQL (CAST(:since AS timestamptz)) so the NULL-cast guard pattern works uniformly and no Python date parsing is needed at the tool boundary."
  - "get_briefing references no report_type token in executable code — an AST test (test_get_briefing_does_not_reference_report_type) allows the column name ONLY inside docstrings (collected by id) and fails if it appears as a string Constant in any statement, so a premature Phase-5 query regresses loudly."
  - "tests rely on the session pg_engine fixture's os.environ['DATABASE_URL'] (full URL incl. password) for the tools' get_engine() — NOT a monkeypatch of str(engine.url), which masks the password to *** and breaks the connect (caught on the first db run)."

patterns-established:
  - "tool-module shape: import shared mcp from .._mcp, define plain typed callables, register each at module bottom via mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(fn); module-level text() SQL constants only (Veto #7)"
  - "in-process-callable tools: every read tool is directly importable+callable (no FunctionTool wrapper at the module name), so unit tests and the Phase-4 runner call them without the MCP transport"

requirements-completed: [SC#2, SC#5, D-01, D-04, "Veto#13"]

# Metrics
duration: 14 min
completed: 2026-06-07
---

# Phase 3 Plan 04: MCP Read-Side Tools (filing / card / note / portfolio / briefing) Summary

**Implemented and registered 6 of the 10 locked read tools on the shared `mcp` instance: `get_filing` (whole `body_md`, Veto #8, `<untrusted>`-wrapped + injection-flagged) and `search_filings` (metadata-only, `filed_at DESC`, default `limit=50`, NULL-cast filter guards) in `filing.py`; `get_decision_card` (Veto #13 — `view='payload'` excludes `body_md` at serialize time, `view='both'` wraps the body D-03) in `card.py`; `get_note` (disk `notes/private/` read-only via `safe_resolve` + injection wrap) in `note.py`; `list_portfolio` (`Portfolio.load` passthrough, `PortfolioLoadError → DataBackendError`) in `portfolio.py`; and `get_briefing` (honest empty `Briefing(found=False, entries=[])`, no `report_type` query — Phase 5 wires data) in `briefing.py`. Every narrative body is WRAP+FLAG'd (D-03/SC#5), every tool honors the D-01 empty-model-vs-raised-exception split, and all SQL is module-level `text()` constants (Veto #7 / SC#3 guard green).**

## Performance

- **Duration:** 14 min
- **Started:** 2026-06-07
- **Completed:** 2026-06-07
- **Tasks:** 3
- **Files modified:** 10 (all created)

## Accomplishments
- `src/mcp_v2/tools/filing.py` — `get_filing(rcept_no)` validates the 14-digit shape (`InvalidArgument`), `SELECT … body_md FROM filings WHERE rcept_no = :rcept_no` (module-level `text()`), raises `FilingNotFound` on no row, returns the WHOLE `body_md` (Veto #8 — no slicing) wrapped in `<untrusted source="dart" ref="…">` (D-03) with `injection_suspected`/`injection_flags`. `search_filings(corp_code, event_type?, since?, until?, limit=50)` validates the 8-digit corp_code + `resolve_entity` existence (`InvalidArgument`/`EntityNotFound`), runs one parameterized `SELECT … ORDER BY filed_at DESC LIMIT :limit` with NULL-cast filter guards, returns metadata-only `FilingHit`s (no body, no injection wrap); zero rows → `SearchFilingsResult(hits=[])` (D-01).
- `src/mcp_v2/tools/card.py` — `get_decision_card(corp_code, latest=True, view='payload')` validates corp_code + view (`InvalidArgument`), delegates to `cards.store.get_active(get_engine(), corp_code)`. `None` → `CardView(found=False, card=None)` (D-01). `view='payload'` → `model_dump(exclude={'body_md'})` (Veto #13 — body excluded at serialize time, NO re-query). `view='both'` → full dump with `body_md` replaced by `injection.wrap_untrusted(body, 'card', card_id)` + `injection_suspected`/`injection_flags` (D-03). NO direct SQL in this file.
- `src/mcp_v2/tools/note.py` — `get_note(path)` resolves the path under cwd via `paths.safe_resolve` (raises `NotePathForbidden` on `..`/symlink/outside-whitelist escape, `NoteNotFound` on missing file), reads the whole file, returns `NoteContent` with the content wrapped `<untrusted source="note" ref="note:…">` (D-03). Derives a `_SAFE_ATTR`-valid ref from the path (path separators → `_`, `note:` prefix). Disk read of `notes/private/`, NOT the notes table (D-05).
- `src/mcp_v2/tools/portfolio.py` — `list_portfolio()` wraps `shared.portfolio.Portfolio.load(Path('.'))`; `PortfolioLoadError → DataBackendError`. Returns a structured `PortfolioView` (holdings carry `ticker`/`avg_price`/`quantity`, watchlist carries tickers) with NO injection wrap (Veto #6 spirit — structured, not narrative). Empty holdings/watchlist is a valid empty model (D-01).
- `src/mcp_v2/tools/briefing.py` — `get_briefing(date, type='daily')` validates `type ∈ {daily, weekly}` (`InvalidArgument`), positively returns `Briefing(date, type, found=False, entries=[])` — no `report_type` query/column reference (Phase 5's migration). Honest empty model (D-01).
- `src/mcp_v2/tools/__init__.py` — empty package marker; the side-effect aggregation that imports every tool module (so every registration runs) is deferred to `server.py` (Plan 06).

## Task Commits

Each task was committed atomically:

1. **Task 1: filing.py (get_filing + search_filings) + test_filing.py** - `9b55c54` (feat)
2. **Task 2: card.py (get_decision_card, Veto #13) + test_card.py** - `1b67b68` (feat)
3. **Task 3: note.py + portfolio.py + briefing.py + test_note.py + test_portfolio_briefing.py** - `ceca9c3` (feat)

**Plan metadata:** committed with this SUMMARY (docs).

## Files Created/Modified
- `src/mcp_v2/tools/__init__.py` (CREATED) - empty package marker; aggregation deferred to server.py (Plan 06).
- `src/mcp_v2/tools/filing.py` (CREATED) - get_filing (whole body, Veto #8) + search_filings (filed_at DESC, limit=50, D-04); module-level text() SQL.
- `src/mcp_v2/tools/card.py` (CREATED) - get_decision_card (Veto #13 serialize-time exclude; view='both' D-03 wrap); delegates to cards.store.get_active.
- `src/mcp_v2/tools/note.py` (CREATED) - get_note disk-whitelist read-only (safe_resolve) + injection wrap.
- `src/mcp_v2/tools/portfolio.py` (CREATED) - list_portfolio passthrough (PortfolioLoadError → DataBackendError).
- `src/mcp_v2/tools/briefing.py` (CREATED) - get_briefing honest empty model (no report_type).
- `tests/mcp_v2/test_filing.py` (CREATED) - 10 db-marked tests (whole-body wrap, injection flag, FilingNotFound/InvalidArgument, DESC ordering, limit, event_type filter, empty model, EntityNotFound).
- `tests/mcp_v2/test_card.py` (CREATED) - 5 db-marked tests (payload excludes body_md, both wraps body, found=False, bad corp/view InvalidArgument).
- `tests/mcp_v2/test_note.py` (CREATED) - 5 no-DB tests (wrapped content, injection flag KO, NotePathForbidden outside-whitelist + traversal, NoteNotFound).
- `tests/mcp_v2/test_portfolio_briefing.py` (CREATED) - 7 no-DB tests (holdings/watchlist, empty valid, missing → DataBackendError, briefing positively empty daily+weekly, AST no-report_type guard, bad type InvalidArgument).

## Decisions Made
- **Tool registration by call form, not decorator:** `@mcp.tool` replaces the name with a non-callable `FunctionTool` (caught on the first test run — `TypeError: 'FunctionTool' object is not callable`). Verified `fastmcp 2.14.7` exposes the original callable on `.fn`, but I register via `mcp.tool(annotations=…)(fn)` so the public module name stays a PLAIN callable for in-process callers (Phase-4 analysis runner + the tests) while still registering the tool. Confirmed all 6 tools register on the shared `mcp` when their modules are imported together (the Plan-06 aggregation precondition).
- **get_note reads disk, not the notes table (D-05):** a single-memo fetch reads the source-of-truth `notes/private/` file via `safe_resolve`; the notes DB table (Plan 02) is the hybrid_search index, refreshed by the ingest job.
- **search_filings filters via NULL-cast guards in ONE statement:** `CAST(:event_type AS text) IS NULL OR …` etc. keeps a single parameterized `text()` covering every filter combination — no SQL string-building (SC#3-safe). `until` is half-open.
- **Tests use the session fixture's `DATABASE_URL`, not a monkeypatch:** the `pg_engine` session fixture already sets `os.environ['DATABASE_URL']` to the live container URL (with password); the tools' `get_engine()` reads it. A monkeypatch of `str(engine.url)` masks the password to `***` and breaks the connect (the first db-run failure).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `@mcp.tool` decorator returns a non-callable FunctionTool**
- **Found during:** Task 1 (first `test_filing.py` run → `TypeError: 'FunctionTool' object is not callable`).
- **Issue:** The plan's `<action>` specified `@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))` decoration. In fastmcp 2.14.7 that decorator REPLACES the function name with a `FunctionTool` object that cannot be called directly — breaking both the tests and any in-process caller (the Phase-4 analysis runner calls these tools as plain functions).
- **Fix:** Register via the call form `mcp.tool(annotations=…)(fn)` at the module bottom, leaving the function name bound to the plain callable. Probed the FastMCP API empirically to confirm the call form registers identically (all 6 names appear in `mcp.get_tools()`).
- **Files modified:** `src/mcp_v2/tools/filing.py` (then applied the same pattern to card/note/portfolio/briefing).
- **Verification:** `tests/mcp_v2/test_filing.py` 10/10 green; the 6-tool co-registration probe passes.
- **Committed in:** `9b55c54` (Task 1) and the same pattern in `1b67b68`/`ceca9c3`.

**2. [Rule 1 - Bug] Wrong rcept_no assertion in test_search_filings_respects_limit**
- **Found during:** Task 1 (test run).
- **Issue:** The test inserted 3 filings with `rcept_no = f"2026060100000{i}"` (loop index as suffix) but asserted the newest hit's `rcept_no` was `20260603000002` (mixing the filed_at day into the rcept_no). The actual newest (i=2, filed Jun 3) has `rcept_no = 20260601000002`.
- **Fix:** Corrected the assertion to the index-suffix rcept_nos in DESC order (`…0002`, `…0001`).
- **Files modified:** `tests/mcp_v2/test_filing.py`
- **Verification:** test green.
- **Committed in:** `9b55c54` (Task 1).

**3. [Rule 1 - Bug] AST no-report_type guard false-positived on docstrings**
- **Found during:** Task 3 (`test_get_briefing_does_not_reference_report_type`).
- **Issue:** The first draft used `ast.get_docstring(tree)` (module docstring only) to exclude prose mentions; the FUNCTION docstring (which also names `report_type`) and the indentation-normalized module docstring were not excluded, so the guard flagged both legitimate prose mentions.
- **Fix:** Collect every docstring Constant node by `id()` (module + every def/class first-statement string) and exclude those; flag only `report_type` string Constants that are NOT docstrings. The guard now correctly allows the explanatory prose and would still fail on any executable `report_type` reference.
- **Files modified:** `tests/mcp_v2/test_portfolio_briefing.py`
- **Verification:** test green.
- **Committed in:** `ceca9c3` (Task 3).

---

**Total deviations:** 3 auto-fixed (1 blocking API-contract correction in production code — the registration form; 2 test-code bugs). The registration-form change is the only production deviation from the plan's literal `@mcp.tool` instruction and is required for the tools to be in-process callable.
**Impact on plan:** No scope change. All 6 specified tools are implemented, registered, and tested exactly as the plan's must-haves require.

## Issues Encountered
- **CRLF warnings on commit:** git reports `LF will be replaced by CRLF` for the new files — the repo's standard line-ending normalization, no impact.
- **cp949 console garbling on Windows:** Korean strings (and the em-dash `—`) render as mojibake / raise `UnicodeEncodeError` in `print()` from a Bash-captured probe; this is a stdout-codepage display artifact only — the assertions ran and passed before the print, and the tests themselves read/write UTF-8 explicitly.

## Verification Results
- `tests/mcp_v2/test_filing.py` — 10 passed (`-m db`, live Postgres at migration 0008).
- `tests/mcp_v2/test_card.py` — 5 passed (`-m db`).
- `tests/mcp_v2/test_note.py` — 5 passed (`-m "not db"`).
- `tests/mcp_v2/test_portfolio_briefing.py` — 7 passed (`-m "not db"`).
- Full `tests/mcp_v2` no-DB suite: **57 passed, 2 skipped** (SC#3 registry guard staged for 03-06 + symlink no-privilege skip), 15 deselected (db) in ~6.5s.
- `tests/mcp_v2/test_no_run_sql_guard.py::test_no_fstring_sql_in_mcp_v2` — passed (SC#3 AST guard green over the new tool files; all filing.py SQL is module-level `text()` constants, card/note/portfolio/briefing carry no SQL).
- All 6 read-side tools (`get_filing`, `search_filings`, `get_decision_card`, `get_note`, `list_portfolio`, `get_briefing`) confirmed registered on the shared `mcp` when their modules are imported together (Plan-06 server aggregation precondition).
- ruff check + ruff format-check clean on all 10 created files.

## Known Stubs
None. `get_briefing` returns an HONEST empty model (D-01) — it does not fake data and explicitly references no `report_type` column (enforced by an AST test); Phase 5 wires the actual briefing rows. This is the plan-specified "no data yet" shape, not a stub. All other tools return real data from live tables / disk.

## Threat Flags
None beyond the plan's threat model.
- **T-SQL-arg (mitigate):** rcept_no/corp_code ASCII regex pre-filter before DB; all SQL is parameterized module-level `text()`; search filters use NULL-cast guards (SC#3 guard green).
- **T-prompt-inj (mitigate):** `get_filing` body, `get_note` content, and `get_decision_card` view='both' body are `wrap_untrusted`-wrapped + `detect`-flagged (D-03); never blocked/stripped.
- **T-path-traversal (mitigate):** `get_note` uses `safe_resolve` (resolve + is_relative_to whitelist) — `..`/absolute/symlink escapes → `NotePathForbidden` (test_note.py).
- **T-veto13 (mitigate):** `get_decision_card` default `view='payload'` excludes `body_md` at serialize time; body only on explicit `view='both'` (test_card.py).
- **T-03-07 (mitigate):** `search_filings` default `limit=50`, `limit < 1` → `InvalidArgument` (D-04).

## User Setup Required
None. No new dependencies, no migrations, no env changes — the 5 tool modules + package marker are pure-Python over the already-installed fastmcp/pydantic + the Phase-1/2/3-03 contracts. Postgres is running at migration 0008; `.env` carries `DATABASE_URL`.

## Next Phase Readiness
- 6 of the 10 locked tools are implemented, registered, and tested. Plan 03-05 (market.py: ohlcv_range/flow_range/peer_view) and Plan 03-06 (search.py: hybrid_search + server.py aggregation) complete the surface.
- The `mcp.tool(...)(fn)` registration pattern + the module shape (import shared mcp, plain callables, register at bottom, module-level `text()` SQL) is the template for 03-05/03-06.
- The SC#3 registry guard (`test_only_locked_tools_registered`) flips from skip to enforced the moment `mcp_v2.server` exists (03-06) and imports all tool modules — these 6 tools already register cleanly when co-imported.
- The tools are in-process callable (no FunctionTool wrapper at the module name), so the Phase-4 analysis runner can call them directly without the MCP transport.
- No blockers.

## Self-Check: PASSED

All 10 created files exist on disk (6 tool modules + 4 test files — all FOUND). All three task commits (`9b55c54`, `1b67b68`, `ceca9c3`) present in git log. 10 filing + 5 card db tests green; 5 note + 7 portfolio/briefing no-DB tests green; full mcp_v2 no-DB suite 57 passed / 2 skipped; SC#3 AST guard green; ruff clean. All 6 tools co-register on the shared mcp.

---
*Phase: 03-mcp-tool-surface-read-side*
*Completed: 2026-06-07*
