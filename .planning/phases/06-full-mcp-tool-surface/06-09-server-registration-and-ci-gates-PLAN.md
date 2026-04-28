---
phase: 06-full-mcp-tool-surface
plan: 09
type: execute
wave: 3
depends_on: [04, 05, 06, 07, 08]
files_modified:
  - src/stock_mcp/server.py
  - tests/stock_mcp/test_server_registration.py
  - tests/stock_mcp/test_docstrings.py
  - tests/perf/__init__.py
  - tests/perf/conftest.py
  - tests/perf/test_mcp_perf_gates.py
  - tests/perf/perf_history.json.gitkeep
  - pyproject.toml
autonomous: true
requirements: [MCP-10]
must_haves:
  truths:
    - "src/stock_mcp/server.py imports all 7 new tool modules so mcp.list_tools() returns 8 tools (search + 7 new)"
    - "tests/stock_mcp/test_docstrings.py asserts all 8 tools have ### Behavior contract / Response shape / Errors / Performance budget sections"
    - "tests/perf/test_mcp_perf_gates.py runs N=20 reps per tool against the fixture vault and asserts p95 latency < 5s and p95 tokens < 8k via tiktoken cl100k_base"
    - "Perf measurements saved to tests/perf/{tool_name}.json for PR diff review"
    - "test_mcp_perf_gates uses the slow pytest marker; runs in PR CI"
  artifacts:
    - path: "src/stock_mcp/server.py"
      provides: "Imports all 7 new tools for side-effect registration"
      contains: "from .tools import"
    - path: "tests/stock_mcp/test_docstrings.py"
      provides: "Docstring contract enforcement"
      contains: "Behavior contract"
    - path: "tests/perf/test_mcp_perf_gates.py"
      provides: "p95 latency + token gates per D-19"
      contains: "tiktoken"
    - path: "tests/perf/{tool_name}.json"
      provides: "Per-tool perf history (regenerated each CI run)"
      contains: "p95_latency_ms"
  key_links:
    - from: "src/stock_mcp/server.py"
      to: "all 7 new tool modules"
      via: "side-effect import"
      pattern: "from .tools import"
---

<objective>
Wire all 7 new tools into the FastMCP server so they register at startup; enforce the docstring 4-section contract via test (D-24); enforce p95 latency < 5s and p95 tokens < 8k per tool via tiktoken-based perf test (D-19, D-20). MCP-10 is the only requirement here — but it gates the entire phase.

Purpose: Without server-side import, the new tool modules are dead code. Without the docstring + perf tests, MCP-10's "CI tests assert p95 latency / token size" claim is empty.

Output: server.py modified to import all tools; 3 test files (registration smoke, docstring contract, perf gates); perf history directory.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md
@.planning/phases/06-full-mcp-tool-surface/06-UI-SPEC.md
@.planning/phases/06-full-mcp-tool-surface/06-VALIDATION.md
@src/stock_mcp/server.py
@src/stock_mcp/tools/search.py
@pyproject.toml

<interfaces>
Existing server.py imports `.tools.search` for side-effect registration. For Phase 6 add identical imports for: overview, events, portfolio, related, filing, notes, health.

FastMCP exposes `await mcp.list_tools()` (async); for sync tests use `mcp._tool_manager.list_tools()` or the equivalent registry attribute. Verify the correct accessor by reading the FastMCP 2.x source or looking at any existing test that lists tools.

Tools to perf-test (8 total):
1. search (Phase 3 — verify still passes)
2. get_ticker_overview
3. get_recent_events
4. get_portfolio_state
5. get_related
6. get_filing
7. add_note
8. health

Per-tool budgets per UI-SPEC "Token Budget — Per-Tool Targets":
| Tool | p95 latency | p95 tokens |
|---|---|---|
| get_ticker_overview | 5.0s | 8000 |
| get_recent_events | 5.0s | 8000 |
| get_portfolio_state | 1.0s | 4000 |
| get_related | 2.0s | 4000 |
| get_filing | 3.0s | 50000 |
| add_note | 1.0s | 1000 |
| health | 2.0s | 2000 |
| search | 5.0s | 8000 |
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: server.py imports + registration smoke test + docstring contract test</name>
  <read_first>
    - src/stock_mcp/server.py (current imports — 1 line at line 16)
    - src/stock_mcp/tools/search.py (verify mcp.tool() registration shape)
    - All 7 new tool files from Plans 06-04..06-08
  </read_first>
  <action>
    1. **Modify src/stock_mcp/server.py** — Append a multi-import line for the 7 new tools, side-effect only:
       ```python
       # Import each tool module to trigger @mcp.tool() registration.
       # Order does not matter functionally — alphabetical for readability.
       from .tools import (  # noqa: F401  -- side-effect registration
           events,
           filing,
           health,
           notes,
           overview,
           portfolio,
           related,
       )
       ```
       Place AFTER the existing `from .tools.search import mcp` line so `mcp` is available when each tool module's `from .search import mcp` runs.

       Also extend `__all__` if it lists exports — keep `mcp` exported.

    2. **Create tests/stock_mcp/test_server_registration.py**:
       ```python
       """Verify all 8 Phase 6 tools are registered on the FastMCP singleton."""
       import pytest

       def test_eight_tools_registered():
           # Importing server has side effect of registering all tools
           from src.stock_mcp.server import mcp
           # FastMCP 2.x exposes registered tools via _tool_manager (private but stable in 2.x)
           # Adjust attribute access if FastMCP version differs.
           tool_names = set()
           # Try a few accessor patterns to be resilient across minor versions:
           for attr in ("_tool_manager", "tools"):
               t = getattr(mcp, attr, None)
               if t is None:
                   continue
               if hasattr(t, "list_tools"):
                   listed = t.list_tools()
                   if hasattr(listed, "__await__"):
                       import asyncio
                       listed = asyncio.get_event_loop().run_until_complete(listed)
                   tool_names = {tt.name for tt in listed}
                   break
               if hasattr(t, "_tools"):
                   tool_names = set(t._tools.keys())
                   break
           expected = {
               "search",
               "get_ticker_overview",
               "get_recent_events",
               "get_portfolio_state",
               "get_related",
               "get_filing",
               "add_note",
               "health",
           }
           assert expected.issubset(tool_names), (
               f"missing: {expected - tool_names}; got: {tool_names}"
           )
       ```
       If both accessor patterns fail, the test should print `dir(mcp)` and skip-fail with a clear message; the executor must adjust to the actual FastMCP 2.x accessor based on the installed version.

    3. **Create tests/stock_mcp/test_docstrings.py**:
       ```python
       """Enforce D-24 docstring 4-section contract for every Phase 6 tool."""
       import pytest

       REQUIRED_SECTIONS = (
           "### Behavior contract",
           "### Response shape",
           "### Errors",
           "### Performance budget",
       )

       def _all_tools():
           from src.stock_mcp.tools import (
               events, filing, health, notes, overview, portfolio, related
           )
           from src.stock_mcp.tools import search
           return {
               "search": search.search,
               "get_ticker_overview": overview.get_ticker_overview,
               "get_recent_events": events.get_recent_events,
               "get_portfolio_state": portfolio.get_portfolio_state,
               "get_related": related.get_related,
               "get_filing": filing.get_filing,
               "add_note": notes.add_note,
               "health": health.health,
           }

       @pytest.mark.parametrize("name,fn", list(_all_tools().items()))
       def test_docstring_has_four_sections(name, fn):
           doc = fn.__doc__ or ""
           for section in REQUIRED_SECTIONS:
               assert section in doc, (
                   f"{name} docstring missing '{section}' section"
               )
       ```

    4. Run both tests; ensure 9+ tests pass (1 registration + 8 parametrized docstrings).
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run pytest tests/stock_mcp/test_server_registration.py tests/stock_mcp/test_docstrings.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "from .tools import" src/stock_mcp/server.py` returns 1 hit; the import block contains the 7 new module names.
    - `grep -nE "events|filing|health|notes|overview|portfolio|related" src/stock_mcp/server.py` returns ≥7 hits across the import.
    - `grep -nE "expected = \{|search|get_ticker_overview|get_recent_events|get_portfolio_state|get_related|get_filing|add_note|health" tests/stock_mcp/test_server_registration.py` returns ≥8 hits in the expected set.
    - Test command exits 0; ≥9 tests pass (1 registration + 8 parametrized docstring).
  </acceptance_criteria>
  <done>All 7 new tools register on import of server; docstring contract enforced at test time.</done>
</task>

<task type="auto">
  <name>Task 2: Perf gates — N=20 latency + tiktoken token measurement (D-19, D-20)</name>
  <read_first>
    - .planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md D-18, D-19, D-20
    - .planning/phases/06-full-mcp-tool-surface/06-UI-SPEC.md "Token Budget — Per-Tool Targets" + "CI Gate Contract"
    - .planning/phases/06-full-mcp-tool-surface/06-VALIDATION.md task 6-12-01
    - tests/stock_mcp/conftest.py (mcp_vault_engine session fixture)
    - pyproject.toml [tool.pytest.ini_options] markers
  </read_first>
  <action>
    1. **Create tests/perf/__init__.py** (empty marker file).

    2. **Create tests/perf/conftest.py**:
       ```python
       """Shared perf-test helpers."""
       from __future__ import annotations
       import json
       import statistics
       import time
       from pathlib import Path
       from typing import Callable

       import tiktoken

       _ENC = tiktoken.get_encoding("cl100k_base")

       def measure(fn: Callable, args: dict, n: int = 20) -> dict:
           latencies_ms = []
           token_counts = []
           for _ in range(n):
               t0 = time.perf_counter()
               result = fn(**args)
               latency = (time.perf_counter() - t0) * 1000
               latencies_ms.append(latency)
               # Both Pydantic models and dicts:
               if hasattr(result, "model_dump_json"):
                   payload = result.model_dump_json()
               else:
                   payload = json.dumps(result, default=str)
               token_counts.append(len(_ENC.encode(payload)))

           def _p95(xs):
               return statistics.quantiles(xs, n=20)[-1] if len(xs) >= 2 else xs[0]

           return {
               "n": n,
               "p50_latency_ms": statistics.median(latencies_ms),
               "p95_latency_ms": _p95(latencies_ms),
               "p50_tokens": int(statistics.median(token_counts)),
               "p95_tokens": int(_p95(token_counts)),
               "max_latency_ms": max(latencies_ms),
               "max_tokens": max(token_counts),
           }

       def save_perf(tool_name: str, stats: dict) -> Path:
           out_dir = Path(__file__).parent
           out = out_dir / f"{tool_name}.json"
           out.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n")
           return out
       ```

    3. **Create tests/perf/test_mcp_perf_gates.py**:
       ```python
       """N=20 latency + token p95 assertions per D-19. PR-test (slow marker, D-20)."""
       from __future__ import annotations
       import pytest
       from .conftest import measure, save_perf

       # (tool_name, callable, args dict, p95_latency_ms_max, p95_tokens_max)
       PERF_BUDGETS = [
           ("search", lambda **kw: __import__("src.stock_mcp.tools.search", fromlist=["search"]).search(**kw),
                {"query": "삼성전자 분기 실적", "ticker": "005930", "top_k": 5}, 5000, 8000),
           ("get_ticker_overview", lambda **kw: __import__("src.stock_mcp.tools.overview", fromlist=["get_ticker_overview"]).get_ticker_overview(**kw),
                {"ticker": "005930"}, 5000, 8000),
           ("get_recent_events", lambda **kw: __import__("src.stock_mcp.tools.events", fromlist=["get_recent_events"]).get_recent_events(**kw),
                {"ticker": "005930", "since": "2026-01-01"}, 5000, 8000),
           ("get_portfolio_state", lambda **kw: __import__("src.stock_mcp.tools.portfolio", fromlist=["get_portfolio_state"]).get_portfolio_state(**kw),
                {}, 1000, 4000),
           ("get_related", lambda **kw: __import__("src.stock_mcp.tools.related", fromlist=["get_related"]).get_related(**kw),
                {"document_id": None, "depth": 1}, 2000, 4000),  # document_id filled at runtime
           ("get_filing", lambda **kw: __import__("src.stock_mcp.tools.filing", fromlist=["get_filing"]).get_filing(**kw),
                {"id": None}, 3000, 50000),  # id filled at runtime
           ("add_note", lambda **kw: __import__("src.stock_mcp.tools.notes", fromlist=["add_note"]).add_note(**kw),
                {"path": "vault/notes/perf-test.md", "body": "perf body", "frontmatter": {"type": "note"}}, 1000, 1000),
           ("health", lambda **kw: __import__("src.stock_mcp.tools.health", fromlist=["health"]).health(**kw),
                {}, 2000, 2000),
       ]

       @pytest.mark.slow
       @pytest.mark.parametrize("name,fn,args,lat_max,tok_max", PERF_BUDGETS)
       def test_p95_perf_gates(mcp_vault_engine, name, fn, args, lat_max, tok_max):
           # Bind dynamic args
           if name == "get_filing" or name == "get_related":
               # Fetch a real document id from the fixture-seeded DB
               import sqlalchemy as sa
               with mcp_vault_engine.connect() as conn:
                   row = conn.execute(sa.text(
                       "SELECT id FROM documents WHERE corp_code IS NOT NULL LIMIT 1"
                   )).mappings().first()
               assert row, "fixture vault must have at least one document with corp_code"
               key = "id" if name == "get_filing" else "document_id"
               args = {**args, key: row["id"]}
           stats = measure(fn, args, n=20)
           save_perf(name, stats)
           assert stats["p95_latency_ms"] < lat_max, (
               f"{name} p95 latency {stats['p95_latency_ms']:.0f}ms exceeds {lat_max}ms"
           )
           assert stats["p95_tokens"] < tok_max, (
               f"{name} p95 tokens {stats['p95_tokens']} exceeds {tok_max}"
           )
       ```

    4. **Verify pytest marker** — Confirm `slow` marker is in `pyproject.toml [tool.pytest.ini_options] markers`. If absent, add `"slow: marks tests as slow (deselect with '-m \"not slow\"')"`.

    5. **Create tests/perf/.gitkeep** (or `perf_history.json.gitkeep`) so the directory exists in git even if the .json files are gitignored. **Decision:** the per-tool .json files should be COMMITTED so PR diffs show perf regressions. Do NOT gitignore them.

    6. **Run the perf test** to verify it passes on the fixture vault. If any tool exceeds its budget, the test fails — surface the failure to the orchestrator (do not silently bump the threshold).
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run pytest tests/perf/test_mcp_perf_gates.py -x -q -m slow</automated>
  </verify>
  <acceptance_criteria>
    - `test -f tests/perf/test_mcp_perf_gates.py` succeeds.
    - `test -f tests/perf/conftest.py` succeeds.
    - `grep -n "tiktoken" tests/perf/conftest.py` returns ≥1 hit; `grep -n "cl100k_base" tests/perf/conftest.py` returns ≥1 hit.
    - `grep -n "n=20\|n: int = 20" tests/perf/conftest.py` returns ≥1 hit.
    - `grep -cE "search|get_ticker_overview|get_recent_events|get_portfolio_state|get_related|get_filing|add_note|health" tests/perf/test_mcp_perf_gates.py` returns ≥8 (one per tool in PERF_BUDGETS list).
    - After running: `find tests/perf -name '*.json' | wc -l` returns ≥8 (one per tool).
    - Verify command exits 0; all 8 parametrized tests pass under the budgets.
  </acceptance_criteria>
  <done>Perf gates green; per-tool budgets satisfied on fixture vault; perf history JSONs committed.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Test fixture → perf measurement | Fixture is repo-controlled; perf runs in CI |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-6-09-01 | Denial of Service | perf test runtime in CI (8 tools × 20 reps) | mitigate | Session-scoped fixture (Plan 06-03) amortizes Postgres + ingest cost; total perf-test target <3 minutes (Pitfall 6). |
| T-6-09-02 | Tampering | perf history JSONs in PR | accept | Files are PR-reviewable; manipulating budgets requires editing PERF_BUDGETS constants which are diff-visible. |
</threat_model>

<verification>
- All 8 tools registered (test_server_registration).
- All 8 tools have 4-section docstring (test_docstrings).
- All 8 tools meet p95 latency + token budgets (test_mcp_perf_gates).
- Per-tool perf JSONs committed.
</verification>

<success_criteria>
- All 3 test files green.
- `uv run pytest tests/stock_mcp/ tests/perf/ -x -q` exits 0 (full Phase 6 test surface green).
- Phase 6 success criteria #5 satisfied: "CI tests assert every tool's p95 latency < 5s and p95 response size < 8k tokens on the fixture corpus".
</success_criteria>

<output>
Create `.planning/phases/06-full-mcp-tool-surface/06-09-SUMMARY.md` with:
- Confirmed 8 tools registered
- Per-tool perf table (p95 latency + tokens)
- Phase 6 verification checklist (all 5 ROADMAP success criteria)
- Manual verification reminder: `npx @modelcontextprotocol/inspector uv run stock-mcp serve` to spot-check docstring rendering
</output>
