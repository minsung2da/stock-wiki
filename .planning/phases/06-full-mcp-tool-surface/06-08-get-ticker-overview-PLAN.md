---
phase: 06-full-mcp-tool-surface
plan: 08
type: execute
wave: 3
depends_on: [02, 04, 05, 07]
files_modified:
  - src/stock_mcp/tools/overview.py
  - tests/stock_mcp/test_get_ticker_overview.py
autonomous: true
requirements: [MCP-03]
must_haves:
  truths:
    - "get_ticker_overview returns OverviewResponse with events + portfolio + related_notes axes populated"
    - "valuation, supply_demand, private_thesis fields are always None in Phase 6 (D-01 placeholders for Phase 10)"
    - "Truncation priority order applied when token guard approached: private_thesis < valuation < supply_demand < portfolio < related_notes < events"
    - "ticker accepts 6-digit and 8-digit; resolved via resolve_entity"
    - "Internally calls get_recent_events + get_portfolio_state-derived row + search() with source='note' for related notes"
    - "truncation_applied lists names of dropped/cut sections per D-22"
    - "Docstring 4 sections per D-24"
  artifacts:
    - path: "src/stock_mcp/tools/overview.py"
      provides: "get_ticker_overview composite tool"
      contains: "def get_ticker_overview"
  key_links:
    - from: "src/stock_mcp/tools/overview.py"
      to: "src/stock_mcp/tools/events.get_recent_events"
      via: "internal call"
      pattern: "get_recent_events"
    - from: "src/stock_mcp/tools/overview.py"
      to: "src/stock_mcp/search_core.hybrid_search"
      via: "for related_notes axis"
      pattern: "hybrid_search"
---

<objective>
Implement `get_ticker_overview(ticker)` (MCP-03, JUDGE-01, D-01..D-04, D-22) — composite tool combining 3 axes (events, portfolio, related_notes) with Phase-10 placeholders (valuation, supply_demand, private_thesis) typed `T | None = None` ready for Phase 10 wiring.

Purpose: Single-call context bundle for Claude judgment workflow. JUDGE-01 ("종목 X 리서치해줘") expects this tool to return everything in one shot. Truncation logic ensures p95 < 8k tokens.

Output: 1 tool module + 1 test module.
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
@src/stock_mcp/tools/events.py
@src/stock_mcp/tools/portfolio.py
@src/stock_mcp/models.py
@src/stock_mcp/search_core.py
@src/db/entity.py

<interfaces>
From Plan 06-04: `from .events import get_recent_events` returns EventTimeline | dict.
From Plan 06-05: `from .portfolio import get_portfolio_state` returns PortfolioState | dict. Plan 06-02 provides `from stock_mcp.repo_root import repo_root` for any direct path resolution; this plan does NOT define a local `_repo_root`.
search_core.hybrid_search: `hybrid_search(engine, query, ticker, source, top_k, mode='hybrid') -> list[dict]` — used to fetch related_notes (source='note', top_k=5).
Plan 06-02 OverviewResponse model has all required fields including the truncation_applied list.

Token budget per D-19: p95 < 8000 tokens. Use tiktoken cl100k_base for any internal pre-truncation estimates if implemented; else estimate via `len(json.dumps(payload)) // 4` (consistent with logging.py heuristic) and apply a safety margin (target 7000 tokens for the heuristic to give cl100k headroom).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: get_ticker_overview composite + truncation logic (MCP-03, D-01..D-04, D-22)</name>
  <read_first>
    - src/stock_mcp/tools/events.py (Plan 06-04 output)
    - src/stock_mcp/tools/portfolio.py (Plan 06-05 — uses public repo_root from stock_mcp.repo_root + Portfolio.load(root))
    - src/stock_mcp/search_core.py (hybrid_search signature)
    - src/stock_mcp/models.py (OverviewResponse, EventRow, PortfolioRow, SearchHit, Phase 10 placeholder models)
    - .planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md D-01..D-04, D-22, D-23
    - .planning/phases/06-full-mcp-tool-surface/06-UI-SPEC.md "Token Budget — Per-Tool Targets" + "Truncation priority order"
    - tests/stock_mcp/conftest.py (fixture)
  </read_first>
  <behavior>
    - Test 1: `get_ticker_overview(ticker="005930")` returns OverviewResponse with events list (≤20 items per D-02), portfolio populated (since 005930 is in fixture holdings), related_notes list (≤5).
    - Test 2: `get_ticker_overview(ticker="207940")` (a watchlist-only ticker) returns portfolio=None (or PortfolioRow with qty=None), still returns events + related_notes.
    - Test 3: `get_ticker_overview(ticker="00126380")` (8-digit corp_code for Samsung) returns identical response to ticker="005930" (resolve_entity normalization).
    - Test 4: All three Phase-10 placeholder fields (valuation, supply_demand, private_thesis) are present in response and equal None.
    - Test 5: `get_ticker_overview(ticker="999999")` returns dict with `error.code="INVALID_TICKER"`.
    - Test 6: Truncation: when fixture has >20 events for the ticker, only top 20 returned; truncation_applied includes "events:cap20".
    - Test 7: Truncation when token estimate exceeds 7000: items dropped per priority order — first related_notes shrinks, then events shrinks; truncation_applied lists each.
    - Test 8: Docstring 4 sections present.
    - Test 9: `since` for events derived from "now KST minus 90 days" by default (D-02 implies recent events).
    - Test 10: response.ticker echoes the resolved ticker (6-digit normalized) and corp_code reflects entity row.
  </behavior>
  <action>
    Create `src/stock_mcp/tools/overview.py`:

    Composition flow:
    1. Resolve entity: `entity = resolve_entity(engine, ticker)` → return INVALID_TICKER if None.
    2. Compute `since_default = (datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(days=90)).strftime("%Y-%m-%d")`.
    3. Call `get_recent_events(ticker=entity["ticker"] or ticker, since=since_default)`. If response is dict-with-error, propagate via `truncation_applied=["events:error"]` + events=[]. Otherwise take `events_response.events[:20]` (D-02 cap).
    4. Build portfolio row by calling `get_portfolio_state()` and finding the matching ticker in holdings. If not in holdings, check watchlist and return that row; if not in either, set portfolio=None.
    5. Fetch related_notes via direct `hybrid_search(engine, query=entity_display_name, ticker=entity["ticker"], source='note', mode='hybrid', top_k=5)` — wrap each hit into SearchHit (already a model). If no notes match, related_notes=[].
    6. Construct OverviewResponse with events, portfolio, related_notes; valuation/supply_demand/private_thesis = None; ticker=entity["ticker"]; corp_code=entity["corp_code"]; truncation_applied = [] initially.
    7. Token guard pass:
       ```python
       def _estimate_tokens(model: BaseModel) -> int:
           return len(model.model_dump_json()) // 4

       TARGET_TOKENS = 7000  # safety margin under 8k cap
       ITEM_DROP_ORDER = [
           # (axis_name, lambda to shrink, lambda to fully drop)
           ("private_thesis", None, lambda r: r.model_copy(update={"private_thesis": None})),
           ("valuation", None, lambda r: r.model_copy(update={"valuation": None})),
           ("supply_demand", None, lambda r: r.model_copy(update={"supply_demand": None})),
           ("portfolio", None, lambda r: r.model_copy(update={"portfolio": None})),
           ("related_notes", lambda r: r.model_copy(update={"related_notes": r.related_notes[:max(1, len(r.related_notes)//2)]}), lambda r: r.model_copy(update={"related_notes": []})),
           ("events", lambda r: r.model_copy(update={"events": r.events[:max(1, len(r.events)//2)]}), lambda r: r.model_copy(update={"events": []})),
       ]

       result = OverviewResponse(...)
       applied = []
       while _estimate_tokens(result) > TARGET_TOKENS:
           progressed = False
           for axis, shrink, drop in ITEM_DROP_ORDER:
               if shrink:
                   new_result = shrink(result)
                   if new_result.model_dump_json() != result.model_dump_json():
                       result = new_result
                       applied.append(f"{axis}:shrunk")
                       progressed = True
                       break
               # else (Phase 10 placeholders / portfolio): drop the field if non-None
               current = getattr(result, axis)
               if current is not None and current != []:
                   result = drop(result)
                   applied.append(f"{axis}:dropped")
                   progressed = True
                   break
           if not progressed:
               break
       result = result.model_copy(update={"truncation_applied": applied})
       ```
       (D-23: in Phase 6, valuation/supply_demand/private_thesis are always None at construction so the drop loop only meaningfully shrinks related_notes and events.)

    8. Hard cap: if events still > 20 after truncation, force events=events[:20] and append `events:cap20` to truncation_applied (D-02 explicit cap).

    9. Return result. Standard error envelope.

    Docstring (4 sections per D-24):
    - Behavior contract: ticker accepts 6/8 digit; resolved; no `as_of` (Phase 10 owns historical); since default = -90d KST.
    - Response shape: OverviewResponse fields enumerated; explicit mention that Phase-6 placeholders are always None.
    - Errors: INVALID_TICKER, DB_UNAVAILABLE, INTERNAL.
    - Performance budget: p95 < 5s, p95 < 8k tokens (cl100k_base).

    Wire `mcp.tool()(get_ticker_overview)`.

    Create `tests/stock_mcp/test_get_ticker_overview.py` covering Tests 1-10.

    For Test 6: ensure fixture seeds >20 events for ticker 005930 (if not, add a function-scoped insert). For Test 7: artificially inflate snippet_200ch to push token count over 7000 — easiest is to inject a mock OverviewResponse into the truncation function via a unit test of the truncation helper. Decompose: extract the truncation loop into a top-level function `_apply_truncation(result, target_tokens) -> OverviewResponse` and unit-test it directly with crafted inputs.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run pytest tests/stock_mcp/test_get_ticker_overview.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "def get_ticker_overview" src/stock_mcp/tools/overview.py` returns 1 hit.
    - `grep -n "valuation=None\|supply_demand=None\|private_thesis=None" src/stock_mcp/tools/overview.py` returns ≥3 hits (or single OverviewResponse(...) construction with all three None).
    - `grep -nE "ITEM_DROP_ORDER|_apply_truncation|truncation_applied" src/stock_mcp/tools/overview.py` returns ≥3 hits.
    - `grep -n "hybrid_search" src/stock_mcp/tools/overview.py` returns ≥1 hit.
    - `grep -n "get_recent_events" src/stock_mcp/tools/overview.py` returns ≥1 hit.
    - `grep -n "mcp.tool()(get_ticker_overview)" src/stock_mcp/tools/overview.py` returns 1 hit.
    - `grep -nE "### Behavior contract|### Response shape|### Errors|### Performance budget" src/stock_mcp/tools/overview.py` returns 4 hits.
    - Test command exits 0; all 10 tests pass.
  </acceptance_criteria>
  <done>get_ticker_overview tool registered with 3 axes + Phase 10 None placeholders + priority-ordered truncation; tests green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| MCP caller (LLM) → tool function | ticker (untrusted) |
| Composed tool calls → response | Inherits trust boundaries from events, portfolio, search |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-6-08-01 | Tampering | ticker injection | mitigate | resolve_entity normalizes; downstream tools also bind-param SQL. |
| T-6-08-02 | Denial of Service | response over token budget | mitigate | _apply_truncation enforces 7000-token soft cap; events hard-capped at 20. |
| T-6-08-03 | Information Disclosure | private_thesis exposure (Phase 10 surface) | accept (Phase 10 problem) | Phase 6 placeholders are None; Phase 10 owns the actual exposure decision. |
</threat_model>

<verification>
- Test 4 confirms Phase-10 placeholders typed correctly + always None.
- Test 7 confirms truncation priority works.
- Tool composes events + portfolio + related_notes correctly per fixture.
</verification>

<success_criteria>
- Verify command exits 0.
- Composite response token estimate < 8k under fixture conditions.
</success_criteria>

<output>
Create `.planning/phases/06-full-mcp-tool-surface/06-08-SUMMARY.md` confirming Phase 10 wiring points (3 nullable fields) are ready.
</output>
