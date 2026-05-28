---
phase: 06-full-mcp-tool-surface
plan: 05
type: execute
wave: 2
depends_on: [01, 02, 03]
files_modified:
  - src/stock_mcp/tools/related.py
  - src/stock_mcp/tools/portfolio.py
  - tests/stock_mcp/test_get_related.py
  - tests/stock_mcp/test_get_portfolio_state.py
autonomous: true
requirements: [MCP-05, MCP-06]
must_haves:
  truths:
    - "get_related(document_id, depth) walks edges via recursive CTE; default depth=1; max depth=2 (clamped)"
    - "get_related returns RelatedSet with id/edge_type/depth/vault_path/snippet_200ch per neighbor"
    - "get_portfolio_state reads notes/private/portfolio.md and returns PortfolioState with holdings + watchlist"
    - "get_portfolio_state response carries no price/eval fields (D-21 meta-only)"
    - "get_portfolio_state populates corp_code per ticker via resolve_entity; tags from portfolio.md if present, else []"
    - "Both tools have 4-section docstring per D-24"
  artifacts:
    - path: "src/stock_mcp/tools/related.py"
      provides: "get_related tool with recursive CTE BFS"
      contains: "def get_related"
    - path: "src/stock_mcp/tools/portfolio.py"
      provides: "get_portfolio_state tool"
      contains: "def get_portfolio_state"
  key_links:
    - from: "src/stock_mcp/tools/related.py"
      to: "edges + documents tables"
      via: "recursive CTE"
      pattern: "WITH RECURSIVE"
    - from: "src/stock_mcp/tools/portfolio.py"
      to: "src/shared/portfolio.Portfolio.load"
      via: "import"
      pattern: "Portfolio.load"
---

<objective>
Implement `get_related(document_id, depth?)` (MCP-06, D-06) using recursive CTE bounded BFS, and `get_portfolio_state()` (MCP-05, D-21) reading the post-cutover `notes/private/portfolio.md`.

Purpose: `get_related` powers graph traversal for "why did we conclude that?" queries. `get_portfolio_state` is read-only meta surface — Claude composes price/eval downstream. Both feed Plan 06-08 `get_ticker_overview`.

Output: 2 tool modules + 2 test modules.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md
@.planning/phases/06-full-mcp-tool-surface/06-UI-SPEC.md
@.planning/phases/06-full-mcp-tool-surface/06-RESEARCH.md
@src/stock_mcp/tools/search.py
@src/stock_mcp/models.py
@src/stock_mcp/snippets.py
@src/shared/portfolio.py
@src/db/entity.py

<interfaces>
edges schema (Phase 2 migration 0001):
- `src_type` (text), `src_id` (text), `dst_type` (text), `dst_id` (text), `edge_type` (text)
- After Plan 06-03 migration 0003, edge_type CHECK is dropped — any string allowed.

Portfolio.load post-cutover (Plan 06-01):
```python
@classmethod
def load(cls, repo_root: Path) -> Portfolio
# reads repo_root / "notes" / "private" / "portfolio.md"
# returns Portfolio(holdings=list[Holding], watchlist=list[str])
```

Holding currently has only ticker/qty/avg_cost. The CONTEXT D-21 PortfolioRow model adds tags + note + corp_code; tags/note are NOT in the current Holding schema. **Decision:** PortfolioRow comes from Plan 06-02 models.py and has its own shape. The tool maps Portfolio (from src/shared) → list[PortfolioRow] (response model) via:
- `ticker = h.ticker`
- `qty = h.qty` (None for watchlist entries)
- `avg_cost = h.avg_cost` (None for watchlist entries)
- `corp_code = resolve_entity(engine, h.ticker)["corp_code"]` if found else None
- `tags = []` (current Portfolio schema lacks tags; future-proof: empty list)
- `note = None` (same reasoning)

If the user has extended portfolio.md schema with tags/notes per holding, adapt — but the CURRENT Portfolio Pydantic model uses extra='forbid', so tags/note absence is correct.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: get_related tool (MCP-06, D-06) — recursive CTE BFS</name>
  <read_first>
    - src/stock_mcp/tools/search.py (pattern + log_tool_call usage)
    - src/stock_mcp/models.py (RelatedRow, RelatedSet from 06-02)
    - src/stock_mcp/snippets.py (build_snippet)
    - .planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md D-06
    - .planning/phases/06-full-mcp-tool-surface/06-RESEARCH.md "Recursive CTE for BFS" SQL block
    - tests/stock_mcp/conftest.py (mcp_vault_engine seeds 2+ test edges per Plan 06-03 task 3)
  </read_first>
  <behavior>
    - Test 1: `get_related(document_id=<existing doc id>, depth=1)` returns RelatedSet with all direct neighbors per the seeded edges; each row has id/edge_type/depth=1/vault_path/snippet_200ch.
    - Test 2: `get_related(document_id=<id>, depth=2)` includes 2-hop neighbors with `depth=2` rows.
    - Test 3: `get_related(document_id=<id>, depth=5)` clamps depth to 2 (no 3+ hop traversal).
    - Test 4: `get_related(document_id="0"*64)` returns dict with `error.code="NOT_FOUND"` (no document with that id).
    - Test 5: Cyclic graph (A→B→A): no infinite loop; returns each unique destination once per shortest path; bounded by `depth ≤ max_depth`.
    - Test 6: Snippet uses `build_snippet`; vault_path comes from documents JOIN; unknown dst_type (non-document) → snippet/vault_path None.
    - Test 7: Docstring 4 sections present.
  </behavior>
  <action>
    Create `src/stock_mcp/tools/related.py`:

    Use the recursive CTE from RESEARCH.md (depth ≤ 2 hard cap). Bind `:doc_id` and `:max_depth` parameters. Clamp `depth` argument: `max_depth = max(1, min(depth, 2))`.

    Pre-flight: verify document_id exists via `SELECT 1 FROM documents WHERE id = :id`. If not → raise `StructuredError(NOT_FOUND, ...)`.

    SQL:
    ```sql
    WITH RECURSIVE related AS (
        SELECT dst_type, dst_id, edge_type, 1 AS depth
        FROM edges
        WHERE src_type = 'document' AND src_id = :doc_id
        UNION
        SELECT e.dst_type, e.dst_id, e.edge_type, r.depth + 1
        FROM edges e
        JOIN related r ON e.src_type = r.dst_type AND e.src_id = r.dst_id
        WHERE r.depth < :max_depth
    )
    SELECT r.dst_type, r.dst_id, r.edge_type, r.depth,
           d.vault_path, d.body, d.frontmatter
    FROM related r
    LEFT JOIN documents d
      ON r.dst_type = 'document' AND r.dst_id = d.id
    ORDER BY r.depth, r.edge_type, r.dst_id
    ```
    Note: use `UNION` (not `UNION ALL`) to dedupe — Postgres recursive CTE with UNION is acceptable for cycle protection at small depth.

    Build RelatedRow per result: when `dst_type == 'document'` and `d.body` not null, `snippet_200ch = build_snippet(d.body, frontmatter['_derived']['summary'])`. Otherwise `snippet_200ch = None`, `vault_path = None`.

    Wire mcp.tool() registration. Cap response items at 100 (defensive guard).

    Create `tests/stock_mcp/test_get_related.py` covering Tests 1-7. For Test 5, the conftest fixture should seed at least one cycle (A→B + B→A) — if it doesn't, add the cycle insertion to the test setup (function-scoped insert that gets rolled back, or an isolated transaction).
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run pytest tests/stock_mcp/test_get_related.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "def get_related" src/stock_mcp/tools/related.py` returns 1 hit.
    - `grep -n "WITH RECURSIVE" src/stock_mcp/tools/related.py` returns 1 hit.
    - `grep -n "max(1, min(depth, 2))" src/stock_mcp/tools/related.py` returns 1 hit (clamp).
    - `grep -n "mcp.tool()(get_related)" src/stock_mcp/tools/related.py` returns 1 hit.
    - `grep -nE "### Behavior contract|### Response shape|### Errors|### Performance budget" src/stock_mcp/tools/related.py` returns 4 hits.
    - Test command exits 0; all 7 tests pass.
  </acceptance_criteria>
  <done>get_related tool registered with bounded recursive CTE BFS; cycle-safe; tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: get_portfolio_state tool (MCP-05, D-21)</name>
  <read_first>
    - src/shared/portfolio.py (post-cutover Portfolio.load(repo_root) signature from 06-01)
    - src/stock_mcp/models.py (PortfolioRow, PortfolioState from 06-02)
    - src/db/entity.py (resolve_entity)
    - .planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md D-21
    - .planning/phases/06-full-mcp-tool-surface/06-UI-SPEC.md "Tool Surface Inventory" row 3
    - tests/stock_mcp/conftest.py (mcp_vault_engine + repo_root)
  </read_first>
  <behavior>
    - Test 1: `get_portfolio_state()` returns PortfolioState with holdings (3 fixture entries) and watchlist (7 fixture entries) per Plan 06-03 fixture portfolio.md.
    - Test 2: Each holdings PortfolioRow has ticker (6-digit), qty (>0), avg_cost (>0), corp_code (resolved or None), tags=[], note=None.
    - Test 3: Each watchlist PortfolioRow has ticker, qty=None, avg_cost=None, corp_code (resolved or None).
    - Test 4: Response JSON has NO field named `price`, `eval`, `evaluation_value`, `pnl` anywhere (recursive search via `model_dump_json()`).
    - Test 5: When `notes/private/portfolio.md` is missing, response is dict with `error.code="PATH_NOT_FOUND"`.
    - Test 6: `source_path` field equals `"notes/private/portfolio.md"` (relative).
    - Test 7: `last_modified` reflects file mtime as datetime.
    - Test 8: Docstring 4 sections present.
  </behavior>
  <action>
    Create `src/stock_mcp/tools/portfolio.py`:

    The tool locates the project root via the public helper produced by Plan 06-02:
    ```python
    from stock_mcp.repo_root import repo_root
    ```
    Do NOT define a local `_repo_root()` — the helper is the single source of truth (env override `STOCK_REPO_ROOT` + walk-up fallback already implemented). The fixture conftest (Plan 06-03) sets `STOCK_REPO_ROOT` to the per-session vault copy so tests pick the fixture path deterministically.

    Tool body:
    ```python
    def get_portfolio_state() -> PortfolioState | dict:
        """4-section docstring..."""
        t0 = time.perf_counter()
        args_log = {}
        try:
            root = repo_root()  # imported from stock_mcp.repo_root (Plan 06-02)
            portfolio_path = root / "notes" / "private" / "portfolio.md"
            if not portfolio_path.exists():
                raise StructuredError(
                    ErrorCode.PATH_NOT_FOUND,
                    f"portfolio.md not found at notes/private/portfolio.md",
                    details={"resolved_path": str(portfolio_path)},
                )
            from src.shared.portfolio import Portfolio
            portfolio = Portfolio.load(root)
            engine = get_engine()
            holdings_rows = []
            for h in portfolio.holdings:
                ent = resolve_entity(engine, h.ticker)
                holdings_rows.append(PortfolioRow(
                    ticker=h.ticker,
                    corp_code=(ent or {}).get("corp_code"),
                    qty=float(h.qty),
                    avg_cost=float(h.avg_cost),
                    tags=[],
                    note=None,
                ))
            watchlist_rows = []
            for t in portfolio.watchlist:
                ent = resolve_entity(engine, t)
                watchlist_rows.append(PortfolioRow(
                    ticker=t,
                    corp_code=(ent or {}).get("corp_code"),
                    qty=None,
                    avg_cost=None,
                    tags=[],
                    note=None,
                ))
            mtime = datetime.fromtimestamp(
                portfolio_path.stat().st_mtime, tz=ZoneInfo("Asia/Seoul")
            )
            result = PortfolioState(
                holdings=holdings_rows,
                watchlist=watchlist_rows,
                source_path="notes/private/portfolio.md",
                last_modified=mtime,
            )
            latency = int((time.perf_counter() - t0) * 1000)
            log_tool_call(
                "get_portfolio_state", args_log, latency,
                len(result.model_dump_json()) // 4
            )
            return result
        except StructuredError as e:
            ...  # standard envelope
        except Exception as e:
            ...  # standard envelope

    mcp.tool()(get_portfolio_state)
    ```

    Docstring includes 4 sections per D-24. Errors enumerated: `PATH_NOT_FOUND`, `DB_UNAVAILABLE`, `INTERNAL`. Performance budget: p95 < 1s, < 4k tokens.

    Create `tests/stock_mcp/test_get_portfolio_state.py` covering Tests 1-8. Test 4 (no price fields) uses substring search:
    ```python
    raw_json = result.model_dump_json()
    for forbidden in ("price", "eval", "evaluation_value", "pnl"):
        assert forbidden not in raw_json, f"forbidden field {forbidden} present"
    ```
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run pytest tests/stock_mcp/test_get_portfolio_state.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "def get_portfolio_state" src/stock_mcp/tools/portfolio.py` returns 1 hit.
    - `grep -n "from stock_mcp.repo_root import repo_root" src/stock_mcp/tools/portfolio.py` returns 1 hit.
    - `grep -nE "^def _repo_root|^    def _repo_root" src/stock_mcp/tools/portfolio.py` returns 0 hits (no local helper duplication).
    - `grep -n "Portfolio.load(root)" src/stock_mcp/tools/portfolio.py` returns 1 hit (uses imported helper output).
    - `grep -n "notes/private/portfolio.md" src/stock_mcp/tools/portfolio.py` returns ≥1 hit.
    - `grep -nE "price|evaluation_value|pnl" src/stock_mcp/tools/portfolio.py` returns 0 hits (no price-related code paths).
    - `grep -nE "### Behavior contract|### Response shape|### Errors|### Performance budget" src/stock_mcp/tools/portfolio.py` returns 4 hits.
    - Test command exits 0; all 8 tests pass.
  </acceptance_criteria>
  <done>get_portfolio_state tool registered, reads notes/private/portfolio.md, no price fields, tests green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| MCP caller (LLM) → tool function | document_id, depth (untrusted) |
| filesystem (portfolio.md) → tool response | Portfolio data is locally authored — trusted |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-6-05-01 | Denial of Service | get_related deep traversal | mitigate | Hard depth cap of 2; recursive CTE bounded; response item cap 100. |
| T-6-05-02 | Information Disclosure | get_portfolio_state private holdings | accept | Tool exposes private data BY DESIGN — Claude needs holdings to reason about user's portfolio. Vault is local and gitignored. |
| T-6-05-03 | Tampering | document_id injection via SQL | mitigate | Bind params (sa.text + dict). |
</threat_model>

<verification>
- get_related works on cyclic graphs without infinite recursion.
- get_portfolio_state response contains no price-related keys.
</verification>

<success_criteria>
- Verify commands in both tasks exit 0.
</success_criteria>

<output>
Create `.planning/phases/06-full-mcp-tool-surface/06-05-SUMMARY.md`.
</output>
