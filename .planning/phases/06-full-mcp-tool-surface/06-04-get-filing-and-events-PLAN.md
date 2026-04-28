---
phase: 06-full-mcp-tool-surface
plan: 04
type: execute
wave: 2
depends_on: [02, 03]
files_modified:
  - src/stock_mcp/tools/filing.py
  - src/stock_mcp/tools/events.py
  - tests/stock_mcp/test_get_filing.py
  - tests/stock_mcp/test_get_recent_events.py
autonomous: true
requirements: [MCP-04, MCP-07]
must_haves:
  truths:
    - "get_filing(id) returns full body up to 200K chars; >200K sets truncated=true and preserves body_chars"
    - "get_filing returns NOT_FOUND on unknown sha256 id"
    - "get_recent_events returns chronological list with id + snippet_200ch + vault_path; never inline body"
    - "Snippet uses _derived.summary when present, else body[:200], wrapped in <vault_excerpt>"
    - "ticker param accepts 6-digit and 8-digit forms; resolved via resolve_entity"
    - "Both tools docstrings have 4-section contract per D-24"
  artifacts:
    - path: "src/stock_mcp/tools/filing.py"
      provides: "get_filing tool"
      contains: "def get_filing"
    - path: "src/stock_mcp/tools/events.py"
      provides: "get_recent_events tool"
      contains: "def get_recent_events"
  key_links:
    - from: "src/stock_mcp/tools/filing.py"
      to: "documents.id (sha256)"
      via: "SQL SELECT body FROM documents WHERE id = :id"
      pattern: "FROM documents"
    - from: "src/stock_mcp/tools/events.py"
      to: "src/stock_mcp/snippets.build_snippet"
      via: "import"
      pattern: "build_snippet"
---

<objective>
Implement `get_filing(id)` (MCP-07, D-07) and `get_recent_events(ticker, since)` (MCP-04, D-05) per the UI-SPEC tool surface inventory. Both tools follow the search.py pattern verbatim: error envelope, log_tool_call, mcp.tool() registration.

Purpose: Two-step ID pattern foundation — events list returns IDs + snippets only; callers fetch bodies via get_filing. Used by get_ticker_overview (Plan 06-08) and end-user Claude judgment workflow.

Output: 2 tool modules + 2 test modules. Tools registered via `mcp.tool()(get_filing)` / `mcp.tool()(get_recent_events)`.
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
@src/stock_mcp/errors.py
@src/stock_mcp/logging.py
@src/db/entity.py

<interfaces>
Pattern (from src/stock_mcp/tools/search.py:39-128):
```python
from fastmcp import FastMCP
from db.engine import get_engine
from ..errors import ErrorCode, StructuredError, to_error_response
from ..logging import log_tool_call
from .search import mcp  # singleton lives in tools/search.py

def my_tool(...) -> ResponseModel | dict:
    """4-section docstring per D-24."""
    t0 = time.perf_counter()
    args_log = {...}
    try:
        engine = get_engine()
        ...
        result = ResponseModel(...)
        latency = int((time.perf_counter() - t0) * 1000)
        log_tool_call("my_tool", args_log, latency, len(result.model_dump_json()) // 4)
        return result
    except StructuredError as e:
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(e)
        log_tool_call("my_tool", args_log, latency, 0, error=err["error"])
        return err
    except Exception as e:
        wrapped = StructuredError(ErrorCode.INTERNAL, str(e)[:200])
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(wrapped)
        log_tool_call("my_tool", args_log, latency, 0, error=err["error"])
        return err

mcp.tool()(my_tool)
```

resolve_entity signature (src/db/entity.py:33-96): `resolve_entity(engine, ticker_or_corp_code: str, as_of: date | None = None) -> dict | None` — returns entity row dict (corp_code, ticker, ...) or None.

documents schema (Phase 2 migration 0001): `id` (sha256 PK), `body` (text), `vault_path`, `frontmatter` (jsonb), `first_seen_at`, `corp_code`, `source` (text).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: get_filing tool (MCP-07, D-07)</name>
  <read_first>
    - src/stock_mcp/tools/search.py (full pattern reference)
    - src/stock_mcp/models.py (FilingResponse model added in Plan 06-02)
    - src/db/entity.py (documents table columns)
    - .planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md D-07 (truncate at 200K)
    - .planning/phases/06-full-mcp-tool-surface/06-UI-SPEC.md "Tool Surface Inventory" row 5
    - tests/stock_mcp/conftest.py (mcp_vault_engine fixture)
  </read_first>
  <behavior>
    - Test 1: `get_filing(id=<known sha256 from fixture>)` returns FilingResponse with `id`, `vault_path`, `frontmatter` dict, `body` str, `body_chars=len(original_body)`, `truncated=False`.
    - Test 2: `get_filing(id="0"*64)` returns dict with `error.code="NOT_FOUND"`.
    - Test 3: `get_filing(id="not-a-sha256")` returns dict with `error.code="NOT_FOUND"` (or INVALID_ID — pick NOT_FOUND for simplicity; SQL returns 0 rows).
    - Test 4: When fixture body is artificially extended past 200K chars (insert one large doc into fixture or mock), response has `truncated=True`, `len(body) <= 200_001`, `body_chars` reflects original length.
    - Test 5: Docstring contains all 4 sections: "### Behavior contract", "### Response shape", "### Errors", "### Performance budget".
  </behavior>
  <action>
    Create `src/stock_mcp/tools/filing.py`:

    ```python
    """get_filing tool — full document body fetch by sha256 id (MCP-07, D-07)."""
    from __future__ import annotations
    import time
    import sqlalchemy as sa
    from db.engine import get_engine
    from ..errors import ErrorCode, StructuredError, to_error_response
    from ..logging import log_tool_call
    from ..models import FilingResponse
    from .search import mcp

    BODY_TRUNCATE_AT = 200_000

    def get_filing(id: str) -> FilingResponse | dict:
        """Full body of a single vault document by content-hash id (MCP-07, JUDGE-04).

        Returns the complete body of the document keyed on `documents.id` (sha256 of
        body, Phase 2 D-01) along with its vault path and frontmatter. Bodies above
        200,000 characters are truncated; `body_chars` always reports the original
        (untruncated) length and `truncated` flags whether the returned body is cut.

        ### Behavior contract
        - `id`: content-hash sha256 (64 hex chars) — the same id returned by
          `search`, `get_recent_events`, and `get_related` list responses.
          Two-step pattern: list tools never inline body; callers fetch full body
          via this tool.
        - No filtering or pagination. One id → one document.

        ### Response shape
        Returns `FilingResponse` with:
        - `id`: echo of input
        - `vault_path`: citable path under `vault/raw/...` (for JUDGE-04)
        - `frontmatter`: parsed frontmatter dict (provenance + ingest_state + _derived)
        - `body`: document body, truncated at 200,000 chars when oversized
        - `body_chars`: original (pre-truncation) length
        - `truncated`: True iff body was cut

        ### Errors
        Returns `{"error": {...}}` — never raises. Codes:
        - `NOT_FOUND`: id does not match any documents row.
        - `DB_UNAVAILABLE`: Postgres unreachable.
        - `INTERNAL`: unexpected failure (string truncated to 200 chars).

        ### Performance budget
        p95 latency < 3s. Response size up to ~50,000 tokens (single 200K-char doc);
        well below the 8k-token guard for typical filings (≤30K chars).
        """
        t0 = time.perf_counter()
        args_log = {"id": id}
        try:
            engine = get_engine()
            with engine.connect() as conn:
                row = conn.execute(
                    sa.text(
                        "SELECT id, body, vault_path, frontmatter "
                        "FROM documents WHERE id = :id"
                    ),
                    {"id": id},
                ).mappings().first()
            if row is None:
                raise StructuredError(
                    ErrorCode.NOT_FOUND,
                    f"document not found: id={id[:16]}...",
                    details={"id": id},
                )
            body = row["body"] or ""
            body_chars = len(body)
            truncated = body_chars > BODY_TRUNCATE_AT
            if truncated:
                body = body[:BODY_TRUNCATE_AT]
            result = FilingResponse(
                id=row["id"],
                vault_path=row["vault_path"],
                frontmatter=row["frontmatter"] or {},
                body=body,
                body_chars=body_chars,
                truncated=truncated,
            )
            latency = int((time.perf_counter() - t0) * 1000)
            log_tool_call(
                "get_filing", args_log, latency, len(result.model_dump_json()) // 4
            )
            return result
        except StructuredError as e:
            latency = int((time.perf_counter() - t0) * 1000)
            err = to_error_response(e)
            log_tool_call("get_filing", args_log, latency, 0, error=err["error"])
            return err
        except Exception as e:  # noqa: BLE001
            wrapped = StructuredError(ErrorCode.INTERNAL, str(e)[:200])
            latency = int((time.perf_counter() - t0) * 1000)
            err = to_error_response(wrapped)
            log_tool_call("get_filing", args_log, latency, 0, error=err["error"])
            return err

    mcp.tool()(get_filing)
    ```

    Create `tests/stock_mcp/test_get_filing.py` covering Tests 1-5. For Test 4, either:
    - Insert a synthetic >200K-char document via fixture's session conn (preferred, isolated), or
    - Use unittest.mock.patch on `engine.connect()` to return a row with a body of `"x" * 250_000`.
    Pick the synthetic insert via fixture (more realistic).
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run pytest tests/stock_mcp/test_get_filing.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "def get_filing" src/stock_mcp/tools/filing.py` returns 1 hit.
    - `grep -n "mcp.tool()(get_filing)" src/stock_mcp/tools/filing.py` returns 1 hit.
    - `grep -nE "### Behavior contract|### Response shape|### Errors|### Performance budget" src/stock_mcp/tools/filing.py` returns 4 hits.
    - `grep -n "BODY_TRUNCATE_AT = 200_000" src/stock_mcp/tools/filing.py` returns 1 hit.
    - Test command exits 0; ≥5 tests pass.
  </acceptance_criteria>
  <done>get_filing tool registered, truncation works, NOT_FOUND on missing id, docstring 4-section contract verified.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: get_recent_events tool (MCP-04, D-05, D-08)</name>
  <read_first>
    - src/stock_mcp/tools/search.py (pattern)
    - src/stock_mcp/models.py (EventRow, EventTimeline added in 06-02)
    - src/stock_mcp/snippets.py (build_snippet helper from 06-02)
    - src/db/entity.py (resolve_entity signature)
    - .planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md D-05 + D-08
    - .planning/phases/06-full-mcp-tool-surface/06-UI-SPEC.md worked example for get_recent_events
    - tests/stock_mcp/conftest.py
  </read_first>
  <behavior>
    - Test 1: `get_recent_events(ticker="005930", since="2026-01-01")` returns EventTimeline with events list sorted DESC by date; each event has id/source/date/type/title/snippet_200ch/vault_path; NO `body`/`content` keys.
    - Test 2: `get_recent_events(ticker="00126380", since="2026-01-01")` (8-digit corp_code) resolves identically and returns events for the same entity.
    - Test 3: `get_recent_events(ticker="999999", since="2026-01-01")` returns dict with `error.code="INVALID_TICKER"` (resolve_entity returns None).
    - Test 4: `get_recent_events(ticker="005930", since="2030-01-01")` returns EventTimeline with events=[] (no events after future date).
    - Test 5: snippets are wrapped in `<vault_excerpt>` and ≤200 chars (after wrapper).
    - Test 6: Events with `_derived.summary` use the summary; events without it use body[:200].
    - Test 7: Docstring 4 sections present.
    - Test 8: At most 50 events returned (D-05 cap).
  </behavior>
  <action>
    Create `src/stock_mcp/tools/events.py`:

    Source filter: documents.source IN ('dart', 'news', 'kind') — exclude 'note' (memos) and 'krx', 'macro' (price/macro are not "events"). Order by `first_seen_at DESC`.

    Date field: prefer `documents.first_seen_at` for the `date` field (ISO YYYY-MM-DD). Type: read from `frontmatter -> '_derived' -> 'event_type'` JSONB path. Title: read from `frontmatter -> 'provenance' -> 'title'` if present, else use first 80 chars of body.

    SQL skeleton:
    ```python
    SELECT
      d.id,
      d.source,
      d.vault_path,
      d.first_seen_at,
      d.body,
      d.frontmatter
    FROM documents d
    WHERE
      d.corp_code = :corp_code
      AND d.source IN ('dart', 'news', 'kind')
      AND d.first_seen_at >= :since
    ORDER BY d.first_seen_at DESC
    LIMIT 50
    ```

    For each row, build snippet via `build_snippet(body, frontmatter['_derived']['summary'])` (defensive `.get` for missing keys).

    Date validation: parse `since` via `date.fromisoformat(since)` — on ValueError, raise `StructuredError(INVALID_TICKER, ...)` with detail `"since must be ISO YYYY-MM-DD"` — actually use a new code or reuse? Use existing `INVALID_TICKER` is wrong. Use `INTERNAL` with explicit detail, OR introduce no new code and surface via INTERNAL. **Decision:** Use `INTERNAL` with explicit message; if a more specific code is needed Phase 7 can add `INVALID_DATE`.

    Ticker resolve:
    ```python
    entity = resolve_entity(engine, ticker)
    if entity is None:
        raise StructuredError(ErrorCode.INVALID_TICKER, f"unknown ticker: {ticker}")
    corp_code = entity["corp_code"]
    ```

    Full tool follows search.py error-envelope pattern. Register via `mcp.tool()(get_recent_events)`.

    Docstring follows the worked example in UI-SPEC §"Typography" verbatim.

    Create `tests/stock_mcp/test_get_recent_events.py` covering Tests 1-8.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run pytest tests/stock_mcp/test_get_recent_events.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "def get_recent_events" src/stock_mcp/tools/events.py` returns 1 hit.
    - `grep -n "mcp.tool()(get_recent_events)" src/stock_mcp/tools/events.py` returns 1 hit.
    - `grep -n "build_snippet" src/stock_mcp/tools/events.py` returns ≥1 hit.
    - `grep -n "resolve_entity" src/stock_mcp/tools/events.py` returns ≥1 hit.
    - `grep -nE "### Behavior contract|### Response shape|### Errors|### Performance budget" src/stock_mcp/tools/events.py` returns 4 hits.
    - `grep -nE "\\bbody\\b|\\bcontent\\b" src/stock_mcp/tools/events.py` — body field is queried but NOT inserted into EventRow; verify by inspecting the tool's response construction.
    - Test command exits 0; all 8 tests pass.
  </acceptance_criteria>
  <done>get_recent_events tool registered with snippet wrapping + 50-cap + 6/8-digit ticker normalization; tests green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| MCP caller (LLM) → tool function | `id` and `ticker` are untrusted strings |
| documents.body → tool response | Untrusted (collector-fetched) text reaches LLM via snippet |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-6-04-01 | Tampering | get_filing id parameter | mitigate | SQL bind param (sa.text + dict) prevents injection; non-existent id → NOT_FOUND. |
| T-6-04-02 | Tampering | get_recent_events ticker | mitigate | resolve_entity normalizes; unknown → INVALID_TICKER (no SQL constructed from raw ticker). |
| T-6-04-03 | Tampering (prompt injection via body) | EventRow.snippet_200ch | mitigate | build_snippet wraps in `<vault_excerpt>` per D-08 / INGEST-09. |
| T-6-04-04 | Information Disclosure | get_filing returns full body | accept | Vault content is intentionally accessible; this IS the API contract. |
</threat_model>

<verification>
- Both tools register on the FastMCP `mcp` singleton (verifiable via `mcp.list_tools()` after server import).
- Snippet wrapper present on all event response items.
- get_filing truncates at 200K with truncated=true.
</verification>

<success_criteria>
- Verify commands in both tasks exit 0.
- Both tools have 4-section docstrings.
</success_criteria>

<output>
Create `.planning/phases/06-full-mcp-tool-surface/06-04-SUMMARY.md` listing tool function names, error codes used, and confirmed Plan 06-08 (`get_ticker_overview`) can compose them.
</output>
