---
phase: 03-mcp-tool-surface-read-side
plan: 03
subsystem: mcp-server
tags: [fastmcp, pydantic-v2, tool-error, mask-error-details, prompt-injection, wrap-flag, path-traversal, xml-delimiter, empty-model, leaf-layer]

# Dependency graph
requires:
  - phase: 03-01
    provides: "mcp + ingest dep groups (fastmcp 2.14.7); migration 0008 (notes + fundamentals + bm25/hnsw indexes) applied; src/mcp_v2 registered as wheel package"
  - phase: 03-02
    provides: "src/mcp_v2/{embedding,tokenizer}.py leaf siblings; tests/mcp_v2 package + SC#3 run_sql AST guard (enforced) + registry guard (staged for 03-06)"
  - phase: 02-decision-card-schema-storage
    provides: "src/cards/models.py Pydantic v2 discipline (ConfigDict(extra='forbid'), Field, ^[0-9]{6}$/^[0-9]{8}$ regex) — replicated by mcp_v2.models"
provides:
  - "src/mcp_v2/_mcp.py — shared mcp = FastMCP('stock-mcp-v2', mask_error_details=True) instance for Plans 04/05/06 to register tools on"
  - "src/mcp_v2/errors.py — D-01 typed exception hierarchy: McpToolError(ToolError) + InvalidArgument/EntityNotFound/FilingNotFound/NotePathForbidden/NoteNotFound/DataBackendError (raised, not returned)"
  - "src/mcp_v2/models.py — 12 empty-able Pydantic v2 return models for all 10 tools (FilingDetail, FilingHit, SearchFilingsResult, OhlcvBar/OhlcvRange, FlowRow/FlowRange, PeerView, SearchHit/SearchResult, NoteContent, CardView, Briefing, PortfolioHolding/PortfolioView)"
  - "src/mcp_v2/injection.py — WRAP+FLAG: PATTERNS table (6 stable EN+KO ids) + detect(body)->list[dict] + wrap_untrusted(body, source, ref_id) XML <untrusted> delimiter (D-03/SC#5)"
  - "src/mcp_v2/paths.py — safe_resolve read-only notes/private whitelist (symlink + .. safe, V12)"
affects: [03-04-tools-filing-market, 03-05-tools-card-note-portfolio-briefing-fundamentals, 03-06-hybrid_search-server]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "D-01 split: zero-row = normal empty Pydantic model (empty list / found=False / median=None); genuine fault = raised McpToolError(ToolError) subclass — FastMCP surfaces the message under mask_error_details=True (only non-ToolError bugs masked)"
    - "shared FastMCP instance lives in a tiny dependency-free _mcp.py to break the server.py <-> tool-module circular import (server side-effect-imports tools; tools import mcp to decorate)"
    - "WRAP+FLAG (never block, never strip): wrap_untrusted always wraps body UNCHANGED in <untrusted source ref> XML delimiter; detect() returns advisory flags the tool attaches as injection_suspected/injection_flags; _SAFE_ATTR guard raises ValueError without echoing the offending value (T-03-06 info-disclosure)"
    - "read-only path defense = Path.resolve() (collapse .. + follow symlinks) + is_relative_to(notes/private) whitelist; vault/ root dropped (Veto #9); typed NotePathForbidden/NoteNotFound instead of archive StructuredError dict"
    - "narrative models carry injection_suspected/injection_flags; pure-numeric models (OhlcvRange/FlowRange/PeerView) carry neither (Veto #6 — numbers never embedded/wrapped)"

key-files:
  created:
    - "src/mcp_v2/_mcp.py"
    - "src/mcp_v2/errors.py"
    - "src/mcp_v2/models.py"
    - "src/mcp_v2/injection.py"
    - "src/mcp_v2/paths.py"
    - "tests/mcp_v2/test_error_model.py"
    - "tests/mcp_v2/test_injection.py"
    - "tests/mcp_v2/test_paths.py"
  modified:
    - "src/mcp_v2/__init__.py"

key-decisions:
  - "shared FastMCP instance placed in _mcp.py (not server.py) — server.py must side-effect-import the tool modules to register them, and the tool modules must import the instance to decorate; a tiny leaf module breaks that cycle (RESEARCH §Recommended Structure separates _mcp/server)"
  - "mask_error_details=True VERIFIED present on FastMCP.__init__ in installed fastmcp 2.14.7 (RESEARCH A6 confirmed empirically: kwarg accepted, instance .name preserved); McpToolError subclasses ToolError so its message stays visible while non-ToolError bugs are masked"
  - "errors.py drops the archive StructuredError/ErrorCode/to_error_response dict pattern entirely (D-01 raises typed exceptions); a no-dict-return guard test AST-checks that no such class/function is *defined* (docstring is allowed to name the rejected pattern)"
  - "injection PATTERNS ported VERBATIM from archive (6 ids); archive is_adversarial/trust_level GATE dropped (D-03 never gates/strips); detect_injection_patterns renamed detect; _SAFE_ATTR widened to [A-Za-z0-9_:.-] (from archive [A-Za-z0-9_-]) to admit dot/colon provenance ids like rcept_no/notes_private:a-b.c"
  - "paths whitelist collapsed to ('notes/private/',) only — archive's vault/notes root is deleted (Veto #9); resolve_path_alias (write-oriented) dropped (read-side only this phase)"
  - "all 12 return models empty-able with identifier-only construction; narrative bodies returned pre-wrapped (the tool, not the model, calls wrap_untrusted) so the model stays a plain data carrier"

patterns-established:
  - "leaf-layer-first ordering: errors/models/injection/paths/_mcp are dependency-free contracts that Plans 04/05/06 import without codebase exploration"
  - "no-dict-return AST guard over errors.py (class/function definitions, not substring) so the explanatory docstring can name the rejected archive pattern"

requirements-completed: [SC#2, SC#5, D-01, D-03]

# Metrics
duration: 8 min
completed: 2026-06-07
---

# Phase 3 Plan 03: MCP Read-Side Leaf Layer (errors / models / injection / paths / shared instance) Summary

**Built the dependency-free leaf layer of `src/mcp_v2/`: the D-01 typed exception hierarchy (`McpToolError(ToolError)` + 6 subclasses, raised not returned), the 12 empty-able Pydantic v2 return models for all 10 tools, the WRAP+FLAG prompt-injection module (verbatim EN+KO `PATTERNS` + `detect` + `wrap_untrusted` XML delimiter — never block/strip, D-03), the read-only `notes/private/` path-traversal defense (`safe_resolve`, symlink + `..` safe, V12), and the shared `mcp = FastMCP("stock-mcp-v2", mask_error_details=True)` instance — no tool callables yet, those land in Plans 04/05/06.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-06-07
- **Completed:** 2026-06-07
- **Tasks:** 3
- **Files modified:** 9 (8 created, 1 modified)

## Accomplishments
- `src/mcp_v2/errors.py` — D-01 hierarchy subclassing `fastmcp.exceptions.ToolError`: `McpToolError` base + `InvalidArgument`, `EntityNotFound`, `FilingNotFound`, `NotePathForbidden`, `NoteNotFound`, `DataBackendError`. Raised on faults; the archive `StructuredError`/`ErrorCode`/`to_error_response` dict pattern is deliberately NOT ported.
- `src/mcp_v2/_mcp.py` — the single shared `mcp = FastMCP("stock-mcp-v2", mask_error_details=True)`. The `mask_error_details` kwarg and the preserved instance name were verified empirically against the installed `fastmcp 2.14.7` (RESEARCH A6) before use.
- `src/mcp_v2/models.py` — 12 empty-able Pydantic v2 models, each `ConfigDict(extra="forbid")`, each constructible in its empty state from identifiers only: `OhlcvRange(ticker=...).bars == []`, `FlowRange(...).rows == []`, `SearchFilingsResult/SearchResult(...).hits == []`, `PeerView(metric=...).median is None & .n == 0`, `CardView(corp_code=...).found is False`, `Briefing(...).found is False & .entries == []`, `PortfolioView().holdings == []`. Narrative models (`FilingDetail`, `NoteContent`, `SearchHit`) carry `injection_suspected: bool` + `injection_flags: list[str]`; numeric models do not (Veto #6). Reuses the `^[0-9]{6}$`/`^[0-9]{8}$` ASCII regexes from `src/cards/models.py`.
- `src/mcp_v2/injection.py` — WRAP+FLAG (D-03/SC#5). `PATTERNS` ported verbatim (EN_IGNORE_PREV, FAKE_SYSTEM_TAG, DAN_MODE, ROLEPLAY_ADMIN, KO_IGNORE_PREV, KO_ADMIN_MODE) as a stable ordered list. `detect(body) -> list[dict]` (`{pattern_id, match≤80, span}`, span-sorted, never raises). `wrap_untrusted(body, source, ref_id)` always wraps the body UNCHANGED in `<untrusted source="..." ref="...">…</untrusted>`; bad attr raises `ValueError("invalid delimiter attribute")` with no value/body leak. Archive `is_adversarial`/`trust_level` gating dropped.
- `src/mcp_v2/paths.py` — `safe_resolve(repo_root, user_path)`: `Path.resolve()` (collapses `..`, follows symlinks) + `is_relative_to` whitelist; whitelist = `("notes/private/",)` ONLY (vault dropped, Veto #9). Outside whitelist → `NotePathForbidden`; whitelisted-but-not-a-file → `NoteNotFound`. Read-only — no write aliases.
- `src/mcp_v2/__init__.py` — now exports `mcp` (from `_mcp`) + the 7 error classes.

## Task Commits

Each task was committed atomically:

1. **Task 1: errors.py + _mcp.py + models.py + test_error_model.py** - `dd7314b` (feat)
2. **Task 2: injection.py WRAP+FLAG + test_injection.py** - `4a3a231` (feat)
3. **Task 3: paths.py read-only safe_resolve + test_paths.py** - `9b446f5` (feat)

**Plan metadata:** committed with this SUMMARY (docs).

## Files Created/Modified
- `src/mcp_v2/errors.py` (CREATED) - D-01 `McpToolError(ToolError)` hierarchy (6 subclasses), docstring explains the empty-model-vs-raised-exception split.
- `src/mcp_v2/_mcp.py` (CREATED) - shared `FastMCP("stock-mcp-v2", mask_error_details=True)` instance.
- `src/mcp_v2/models.py` (CREATED) - 12 empty-able return models for all 10 tools; narrative vs numeric split.
- `src/mcp_v2/injection.py` (CREATED) - `PATTERNS` + `detect` + `wrap_untrusted` WRAP+FLAG (D-03).
- `src/mcp_v2/paths.py` (CREATED) - `safe_resolve` read-only `notes/private/` whitelist (V12).
- `src/mcp_v2/__init__.py` (MODIFIED) - exports `mcp` + error classes; docstring updated for the 03-03 leaf layer.
- `tests/mcp_v2/test_error_model.py` (CREATED) - 24 no-DB tests (empty-state construction, ToolError subclassing, shared-instance, no-dict-return AST guard).
- `tests/mcp_v2/test_injection.py` (CREATED) - 9 no-DB tests (flag-not-block, pattern-ID snapshot, EN/KO matches, no-leak ValueError, provenance chars).
- `tests/mcp_v2/test_paths.py` (CREATED) - 8 no-DB tests (whitelist-resolve, `..` traversal, absolute-outside, path-outside, symlink-escape, missing-file, dir-not-file, whitelist == notes/private only).

## Decisions Made
- **Shared instance in `_mcp.py`:** isolating `mcp` in a tiny leaf module breaks the `server.py` ↔ tool-module import cycle (server side-effect-imports tools; tools import `mcp` to decorate). This refines the RESEARCH skeleton (which put `mcp` in `server.py`); the tool plans import `from mcp_v2._mcp import mcp`.
- **`mask_error_details=True` verified, not assumed:** before writing `_mcp.py` I ran a probe against installed fastmcp 2.14.7 confirming the kwarg is accepted on `FastMCP.__init__` and the instance `.name` is preserved (RESEARCH A6 was MEDIUM-confidence).
- **`_SAFE_ATTR` widened** from the archive `^[A-Za-z0-9_-]+$` to `^[A-Za-z0-9_:.-]+$` so legitimate provenance ids (a `rcept_no`, a `notes_private:a-b.c`-style ref) pass while still rejecting whitespace/quotes/angle-brackets that could break the XML delimiter. The info-disclosure guard (no value echoed on failure) is preserved.
- **No-dict-return guard is AST-based:** it asserts no `StructuredError`/`ErrorCode`/`to_error_response` class/function is *defined* in errors.py, so the explanatory docstring is free to name the rejected archive pattern (a naive substring scan false-positived on it).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] no-dict-return guard false-positived on the errors.py docstring**
- **Found during:** Task 1 (`test_no_dict_return_error_pattern`).
- **Issue:** The first draft asserted the substring `"to_error_response"` was absent from `errors.py`. The errors.py docstring legitimately *names* the rejected archive pattern ("do NOT resurrect the archive's `StructuredError`/`ErrorCode`/`to_error_response` dict-return pattern"), so the substring scan failed even though no such code exists.
- **Fix:** Rewrote the guard to AST-parse errors.py and assert no `ClassDef`/`FunctionDef` named `StructuredError`/`ErrorCode`/`to_error_response` is *defined* — the docstring mention is allowed, the code definition is not.
- **Files modified:** `tests/mcp_v2/test_error_model.py`
- **Verification:** `pytest tests/mcp_v2/test_error_model.py` → 24 passed.
- **Committed in:** `dd7314b` (Task 1 commit)

**2. [Rule 1 - Bug] ruff B017/E501 on the Task-1 test (blind Exception + long line)**
- **Found during:** Task 1 (ruff check before commit).
- **Issue:** Four `pytest.raises(Exception)` assertions (B017 "do not assert blind exception") and one 101-char line (E501).
- **Fix:** Switched the model-construction failure assertions to `pytest.raises(ValidationError)` (the precise pydantic error) and wrapped the long `FilingDetail(...)` call across lines.
- **Files modified:** `tests/mcp_v2/test_error_model.py`
- **Verification:** `ruff check` + `ruff format --check` clean; 24 tests still green.
- **Committed in:** `dd7314b` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (both bugs in test code: an over-coarse string guard and ruff lint violations). No production-code deviations — errors.py / models.py / injection.py / paths.py / _mcp.py match the plan exactly.
**Impact on plan:** Both fixes corrected test code so the suite is precise and lint-clean. No scope change.

## Issues Encountered
- **Symlink-escape test skips on this Windows account (WinError 1314):** `os.symlink` requires the "create symbolic link" privilege, which this account lacks, so `test_symlink_escape_forbidden` skips here. The test runs on CI (Linux) where symlinks work. The symlink-escape DEFENSE is still exercised indirectly by the `..`-traversal and absolute-path-outside tests (both prove `resolve()` + `is_relative_to` rejects any path whose resolved target lands outside the whitelist — the same mechanism that catches a symlink escape). Honest skip, not a coverage gap in the logic.
- **mecab/console garbling on Windows (cp949):** Korean injection-pattern strings render as mojibake in Bash captures, but matching is correct (KO_IGNORE_PREV / KO_ADMIN_MODE assertions pass). Display artifact only.
- **CRLF warnings on commit:** git reports `LF will be replaced by CRLF` for the new files — the repo's standard line-ending normalization, no impact.

## Verification Results
- `tests/mcp_v2/test_error_model.py` — 24 passed (no DB).
- `tests/mcp_v2/test_injection.py` — 9 passed (no DB).
- `tests/mcp_v2/test_paths.py` — 7 passed, 1 skipped (symlink test, no-privilege Windows) (no DB).
- Full no-DB mcp_v2 suite: **45 passed, 2 skipped** (registry guard staged for 03-06 + symlink skip) in ~3.3s.
- `tests/mcp_v2/test_no_run_sql_guard.py::test_no_fstring_sql_in_mcp_v2` — passed (SC#3 AST guard trivially green; the 5 new leaf files are SQL-free).
- `mcp_v2` package imports cleanly (errors, models, injection, paths, _mcp); `mcp_v2.mcp.name == "stock-mcp-v2"`.
- ruff check + ruff format-check clean on all 9 changed files.

## Known Stubs
None. All five leaf modules are complete, real implementations (no placeholders, no `NotImplementedError`). The two SKIPS are by design: the SC#3 registry test stays skipped until `mcp_v2.server` exists (03-06), and the symlink test skips only on a no-privilege OS account — neither returns fake data. The tool *callables* (get_filing, hybrid_search, etc.) are intentionally out of scope for this plan (Plans 04/05/06), per the plan objective "No tool callables yet."

## Threat Flags
None beyond the plan's threat model.
- **T-path-traversal (mitigate):** `safe_resolve` `Path.resolve()` + `is_relative_to(notes/private)`, symlink-safe, read-only, raises `NotePathForbidden` (test_paths.py).
- **T-prompt-inj (mitigate):** `<untrusted>` WRAP + pattern FLAG, never block/strip (test_injection.py::test_flag_not_block).
- **T-03-05 (mitigate):** `mask_error_details=True` masks non-ToolError bug details; verified the kwarg exists in fastmcp 2.14.7.
- **T-03-06 (mitigate):** `_SAFE_ATTR` regex on source/ref_id; ValueError on bad attr with no value/body leak (test_injection.py::test_wrap_bad_source_raises_no_leak).

## User Setup Required
None. No new dependencies, no migrations, no env changes — all five files are pure-Python leaves over the already-installed fastmcp/pydantic.

## Next Phase Readiness
- The shared `mcp` instance is available for Plans 04/05/06 to register tools on via `from mcp_v2._mcp import mcp`.
- The D-01 error types, empty-able return models, `wrap_untrusted`/`detect`, and `safe_resolve` are contracts the tool plans import without codebase exploration (interface-first ordering achieved).
- The SC#3 registry guard (`test_only_locked_tools_registered`) flips from skip to enforced the moment `mcp_v2.server` exists (03-06).
- No blockers.

## Self-Check: PASSED

All 8 created files + 1 modified file exist on disk (errors.py, _mcp.py, models.py, injection.py, paths.py, __init__.py, test_error_model.py, test_injection.py, test_paths.py). All three task commits (`dd7314b`, `4a3a231`, `9b446f5`) present in git log. 45 passed / 2 skipped no-DB; ruff clean; package imports clean.

---
*Phase: 03-mcp-tool-surface-read-side*
*Completed: 2026-06-07*
