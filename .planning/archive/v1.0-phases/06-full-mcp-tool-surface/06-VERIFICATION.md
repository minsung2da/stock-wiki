---
phase: 06-full-mcp-tool-surface
verified: 2026-05-04T12:19:06Z
status: human_needed
score: 5/5 success criteria verified
overrides_applied: 0
human_verification:
  - test: "Render docstrings in MCP inspector and confirm each tool reads as a coherent LLM-facing behavioral contract (SC-5)"
    expected: "Each of the 8 registered tools (search, get_ticker_overview, get_recent_events, get_portfolio_state, get_related, get_filing, add_note, health) shows a docstring containing purpose, inputs, returns, and error semantics in the MCP Inspector UI"
    why_human: "Visual rendering quality and LLM-facing readability cannot be auto-verified beyond the keyword-presence checks already in tests/stock_mcp/test_docstrings.py — actual MCP inspector rendering is a UX check"
  - test: "Live Claude Code call: invoke get_ticker_overview('005930') from a real MCP-connected Claude Code session"
    expected: "Single structured object returns financials/investor flow/recent events/related notes axes (Phase-10 fields None placeholders) with vault paths cited; perceived latency feels acceptable in interactive use"
    why_human: "End-to-end stdio transport + Claude Code rendering of the structured response cannot be exercised by pytest"
---

# Phase 6: Full MCP Tool Surface — Verification Report

**Phase Goal:** Deliver the full FastMCP toolbox (`get_ticker_overview`, `get_recent_events`, `get_portfolio_state`, `get_related`, `get_filing`, `add_note`, `health`) with LLM-facing docstring contracts, write-scope rules (`vault/notes/` ∪ `notes/private/` only), and CI gates on response latency and token size.

**Verified:** 2026-05-04T12:19:06Z
**Status:** human_needed (automated checks fully pass; UX/inspector verification deferred to human)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | `get_ticker_overview("005930")` returns single structured object combining financials/flow/events/related notes — cited with vault paths — under 8k tokens p95 | VERIFIED | `tests/perf/test_mcp_perf_gates.py::test_p95_perf_gates[get_ticker_overview-...-5000-8000]` PASSED (latency<5s, tokens<8k); `src/stock_mcp/tools/overview.py` returns `OverviewResponse` with portfolio/events/related_notes/valuation/supply_demand/private_thesis axes, Phase-10 fields = None placeholders per D-01 |
| SC-2 | `get_recent_events`, `get_portfolio_state`, `get_related`, `get_filing` each correct on fixture vault and enforce ID-based two-step pattern | VERIFIED | All 4 tools registered in `server.py`; perf gates pass for each; ID two-step verified in `test_get_recent_events.py` (returns `id`+`snippet`) and `test_get_filing.py` (returns full body keyed by sha256 id, 200K-char truncate); 110/110 tests PASSED in `tests/stock_mcp/` |
| SC-3 | `add_note` writes only under `vault/notes/` ∪ `notes/private/`; rejects `raw/`/`ingested/` with clear error | VERIFIED | `src/stock_mcp/tools/notes.py` enforces D-09 whitelist after `Path.resolve()` (symlink-safe); `tests/stock_mcp/test_add_note_paths.py` covers `..` traversal + `raw/`/`ingested/` rejection with `WRITE_FORBIDDEN`; tests pass |
| SC-4 | `health()` reports last batch success per source, DB connectivity, staleness derived from heartbeat | VERIFIED | `src/stock_mcp/tools/health.py` reads `ingest_runs` (primary) with heartbeat fallback; staleness thresholds + DB-down graceful path; `tests/stock_mcp/test_health.py` passes |
| SC-5 | CI tests assert every tool's p95 latency < 5s and p95 tokens < 8k (with `get_filing` exception <50k); docstrings render as coherent LLM contracts | VERIFIED (auto) / HUMAN-NEEDED (UX) | All 8 perf gates PASSED in `tests/perf/test_mcp_perf_gates.py` with N=20 samples and tiktoken cl100k_base encoder; `get_filing` budget = 50000 tokens matches CONTEXT D-07 / UI-SPEC exception; `tests/stock_mcp/test_docstrings.py` enforces docstring-keyword contract per tool. MCP inspector rendering is a human UX check. |

**Score:** 5/5 success criteria verified (one with human follow-up for UX)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/stock_mcp/server.py` | Wires all 8 tools via side-effect imports | VERIFIED | Imports `events, filing, health, notes, overview, portfolio, related` (search via `tools.search`); `_check_db_connection` fail-fast helper present (D-24) |
| `src/stock_mcp/tools/filing.py` | get_filing with sha256 id + 200K truncate | VERIFIED | 138 LOC, registered, tests pass |
| `src/stock_mcp/tools/events.py` | get_recent_events two-step (id+snippet) | VERIFIED | 194 LOC, registered, tests pass |
| `src/stock_mcp/tools/related.py` | get_related recursive CTE BFS depth<=2 | VERIFIED | 195 LOC, registered, tests pass |
| `src/stock_mcp/tools/portfolio.py` | get_portfolio_state from notes/private | VERIFIED | 179 LOC; reads `notes/private/portfolio.md`; Phase-10 P-01 cutover honored |
| `src/stock_mcp/tools/notes.py` | add_note with whitelist + symlink-resolve + atomic write + idempotency | VERIFIED | 283 LOC; D-09 whitelist (`vault/notes/` ∪ `notes/private/`), D-12 path aliases, frontmatter validation, append-only with `_last_section_matches` idempotency, `_atomic_write` |
| `src/stock_mcp/tools/health.py` | health with ingest_runs primary + heartbeat fallback | VERIFIED | 264 LOC; classifies staleness, DB-down graceful, registered |
| `src/stock_mcp/tools/overview.py` | get_ticker_overview composite + priority truncation | VERIFIED | 315 LOC; D-22 truncation order (private_thesis < valuation < supply_demand < portfolio < related_notes < events); Phase-10 placeholder None per D-01 |
| `src/stock_mcp/models.py` | Pydantic response models incl. Phase-10 placeholders | VERIFIED | 269 LOC; OverviewResponse with valuation/supply_demand/private_thesis fields typed as `T \| None` |
| `src/stock_mcp/errors.py` | 5 new ErrorCode constants + StructuredError | VERIFIED | 57 LOC; ErrorCode enum present; covers WRITE_FORBIDDEN, DB_UNAVAILABLE, PATH_NOT_FOUND, etc. |
| `src/db/migrations/versions/0003_relax_edges_check_for_phase6.py` | Alembic 0003 relaxing edges CHECK | VERIFIED | File present |
| `tests/fixtures/mcp-vault/` | 100-doc fixture corpus | VERIFIED | 103 markdown files under `tests/fixtures/mcp-vault/` |
| `tests/perf/test_mcp_perf_gates.py` | N=20 perf gates per tool with tiktoken cl100k_base | VERIFIED | 8 parametrized gates PASS; budgets per tool reflect D-19/D-20 |
| `tests/stock_mcp/test_docstrings.py` | docstring-contract test | VERIFIED | Present in `tests/stock_mcp/`; runs in 110-test suite |
| `notes/private/portfolio.md` | Post-cutover SoT path (Phase 6 P-01) | VERIFIED | File exists at expected path; 9 source/test sites updated |
| `pyproject.toml` tiktoken dep | tiktoken>=0.8,<1 | VERIFIED | Pinned in pyproject.toml + uv.lock |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `server.py` | 7 new tool modules | side-effect imports register on shared `mcp` FastMCP instance | WIRED | `from .tools import (events, filing, health, notes, overview, portfolio, related)` |
| `tools/portfolio.py` | `notes/private/portfolio.md` | `Portfolio.load(repo_root)` via `src/shared/portfolio.py` | WIRED | Path cutover confirmed in source + tests |
| `tools/notes.py` write whitelist | `vault/notes/` ∪ `notes/private/` only | `Path.resolve()` then prefix check (symlink-safe per D-09) | WIRED | `test_add_note_paths.py` validates `WRITE_FORBIDDEN` on `raw/`/`ingested/` and `..` traversal |
| `tools/overview.py` truncation | tiktoken cl100k_base + 8k budget | priority-ordered drop (`_apply_truncation`) per D-22 | WIRED | Perf gate enforces <8k p95 |
| `tools/health.py` | `ingest_runs` table + heartbeat file | sqlalchemy + filesystem read | WIRED | DB-down path returns DB_UNAVAILABLE classified status |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All stock_mcp unit/integration tests pass | `uv run pytest tests/stock_mcp/` | 110 passed in 196.86s | PASS |
| All 8 perf gates (latency + token budgets) pass | `uv run pytest tests/perf/ -v` | 8 passed in 318.79s; all parameter sets including get_filing-3000-50000 | PASS |
| All 8 phase tools registered on FastMCP instance | grep tool registrations | 8/8 (search + 7 new) | PASS |
| Pydantic Phase-10 placeholder fields default to None | grep `valuation=None, supply_demand=None, private_thesis=None` in overview.py | confirmed (lines 278-280) | PASS |
| Alembic 0003 migration file exists | `ls src/db/migrations/versions/0003*` | present | PASS |
| Fixture vault corpus ≥ 100 docs | `find tests/fixtures/mcp-vault -name '*.md' \| wc -l` | 103 | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| MCP-03 | 06-08 | get_ticker_overview composite (4 axes incl. Phase-10 placeholders) | SATISFIED | `tools/overview.py`, perf gate <8k tokens, Phase-10 fields None per D-01 |
| MCP-04 | 06-04 | get_recent_events timeline (DART/news/KIND) | SATISFIED | `tools/events.py`; perf gate; two-step id+snippet |
| MCP-05 | 06-05 | get_portfolio_state from notes/private/portfolio.md (P-01 amended) | SATISFIED | `tools/portfolio.py` + `shared/portfolio.py` + cutover at 9 sites |
| MCP-06 | 06-05 | get_related (graph edge neighbors, depth<=2) | SATISFIED | `tools/related.py` recursive CTE BFS |
| MCP-07 | 06-04 | get_filing full-body by id (two-step) | SATISFIED | `tools/filing.py`, sha256 id, 200K-char truncate, 50k-token perf budget |
| MCP-08 | 06-06 | add_note write whitelist `vault/notes/` ∪ `notes/private/` | SATISFIED | `tools/notes.py` D-09 whitelist + symlink-resolve + atomic write |
| MCP-09 | 06-07 | health (last batch, DB connectivity, staleness) | SATISFIED | `tools/health.py` ingest_runs primary + heartbeat fallback |
| MCP-10 | 06-09 | docstrings as LLM-facing contracts + CI latency/token gates | SATISFIED (auto)/HUMAN UX | `test_docstrings.py` + `test_mcp_perf_gates.py` (8 gates pass); inspector rendering is human UX |

All 8 requirement IDs accounted for. No orphaned IDs.

### Anti-Patterns Found

| File | Issue | Severity | Impact |
|------|-------|----------|--------|
| `src/stock_mcp/errors.py` | UP042: `class ErrorCode(str, Enum)` should inherit from `enum.StrEnum` | Info | Style only; tests pass |
| `src/stock_mcp/server.py` | I001: import block un-sorted | Info | Cosmetic |
| `src/stock_mcp/tools/health.py` | SIM108: if/else collapsible to `or` expression | Info | Cosmetic |
| `src/collectors/kind/sources.py` | UP042 + UP035 + SIM105 | Info | Pre-existing (not phase 6 scope) |
| `tests/perf/conftest.py`, `tests/stock_mcp/conftest.py`, `tests/stock_mcp/test_get_ticker_overview.py` | F401 unused `os`, UP035 Callable/Iterator, E501, I001 | Warning | Pre-commit ruff hook would block fresh commits unless run with `--fix`; phase commits used `core.hooksPath=/dev/null` to bypass during the index-lock race |

**Total ruff errors across `src/` + `tests/`: 10** (5 auto-fixable). These are lint-style issues, not behavioral defects — all 110 unit tests + 8 perf gates pass. Listed for follow-up cleanup but do not block goal achievement. Recommend running `uv run ruff check src/ tests/ --fix` and a `--unsafe-fixes` pass for the StrEnum migration in a small follow-up commit.

### Human Verification Required

1. **Docstring rendering in MCP inspector** — Open the FastMCP inspector (`uv run mcp dev src/stock_mcp/server.py` or similar) and confirm each of the 8 tools displays a coherent purpose/input/output/error contract. The `test_docstrings.py` keyword check verifies presence but not narrative quality.

2. **Live Claude Code end-to-end call** — Connect stock-mcp via stdio in a real Claude Code session and call `get_ticker_overview("005930")`. Confirm the response renders cleanly, vault path citations resolve, and interactive latency feels acceptable. Perf gates synthesize calls but do not cover real Claude Code transport.

### Gaps Summary

No goal-blocking gaps. All five roadmap success criteria are met against the codebase, all 8 tools are registered and pass behavioral + perf gates against the fixture vault, all 8 requirement IDs are satisfied, and the Phase 6 P-01 portfolio path cutover (`notes/private/portfolio.md`) is honored across source and test sites. Outstanding items are limited to:

- Lint-style ruff cleanup (10 cosmetic warnings; no behavioral impact)
- Two human verification items (MCP inspector UX + live Claude Code integration smoke test) — flagged because automated checks cannot exercise them.

The pre-commit-hook bypass (`core.hooksPath=/dev/null`) used during phase 6 commits warrants a follow-up: re-run `pre-commit run --all-files` in a maintenance task once the index-lock race is no longer in play, and fix the resulting ruff diff in a single dedicated commit.

---

_Verified: 2026-05-04T12:19:06Z_
_Verifier: Claude (gsd-verifier)_
