---
phase: 6
slug: full-mcp-tool-surface
status: draft
shadcn_initialized: false
preset: not applicable — non-visual phase
created: 2026-04-26
non_visual: true
surface: llm-facing-mcp-tools
---

# Phase 6 — UI Design Contract (LLM-Facing Tool Surface)

> **Non-visual phase.** This phase ships 7 FastMCP tools whose "interface" is an LLM-facing JSON-RPC contract — tool docstrings, Pydantic response schemas, error codes, and behavior guarantees. Visual sections of the standard UI-SPEC template (spacing, color, typography, font) are not applicable; their LLM-facing analogs are documented instead.
>
> Downstream `gsd-ui-checker` and `gsd-ui-auditor` should treat this contract as the equivalent of a visual design system: the executor must produce tools that conform to these schemas and docstring shapes, and CI gates from D-19/D-20 enforce them.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none (non-visual) |
| Preset | not applicable |
| Component library | not applicable — substitute: **FastMCP 2.x `@mcp.tool()` decorator** |
| Icon library | not applicable |
| Font | not applicable |

**LLM-facing equivalent:**

| Property | Value |
|----------|-------|
| Protocol | JSON-RPC over stdio (FastMCP 2.x stable, pinned `>=2.11,<3.0`) |
| Schema engine | Pydantic v2 with `ConfigDict(extra="forbid")` |
| Tool registration pattern | `mcp.tool()(func_name)` call-form (preserves callable for tests) — verbatim from `src/stock_mcp/tools/search.py:128` |
| Singleton location | `src/stock_mcp/tools/search.py:29` — siblings import via `from .search import mcp` |
| Server-side registration | `src/stock_mcp/server.py` imports each tool module for side-effect registration |
| Error envelope | `to_error_response(StructuredError)` returning `{"error": {"code", "message", "details"}}` (D-21) |
| Logging sink | `log_tool_call(name, args, latency_ms, response_chars/4)` to stderr JSON (never stdout) |

---

## Spacing Scale (N/A — Substitute: Response Envelope Conventions)

**N/A — non-visual phase.**

LLM-facing equivalent — **response envelope conventions** that apply uniformly across all 7 tools:

| Convention | Rule | Source |
|------------|------|--------|
| Untrusted text wrapper | All snippets/excerpts wrapped in `<vault_excerpt>...</vault_excerpt>` XML delimiters | D-08, INGEST-09, reuse `wrap_untrusted` from `src/ingest/injection_defense.py` |
| Snippet length | ≤ 200 chars; prefer `_derived.summary` (Phase 5 D-08) over `body[:200]` | D-08 |
| Citation field | Every list item carries `vault_path: str` (citable for JUDGE-04) | JUDGE-04, RET-03 |
| Two-step ID pattern | List tools return `id + snippet` only; full body fetched via `get_filing(id)` | D-05, D-06 |
| Truncation metadata | Responses that hit token guard carry `truncation_applied: list[str]` naming dropped sections | D-22 |
| Idempotency flag | Write tools return `idempotent: bool` when re-issuing a no-op | D-13 |
| Body cap | `get_filing` truncates body at 200,000 chars; sets `truncated: bool` + preserves `body_chars` (true length) | D-07 |
| Error envelope | Errors NEVER raise past tool boundary; always `{"error": {...}}` dict | D-21 |
| stdout discipline | No `print()`, no `raise` past boundary — corrupts JSON-RPC stream | D-21 |

**Exceptions:** none — all 7 tools share these conventions.

---

## Typography (N/A — Substitute: Docstring Contract Structure)

**N/A — non-visual phase.**

LLM-facing equivalent — every tool docstring MUST follow the **4-section contract** established by `src/stock_mcp/tools/search.py` lines 47-81 (D-24):

| Section | Required content | Example anchor |
|---------|------------------|----------------|
| First line | One-sentence summary + parenthetical requirement IDs (e.g. `(MCP-04, JUDGE-04)`) | `search.py:47` |
| `### Behavior contract` | Each parameter's exact meaning, allowed values, normalization (e.g. ticker → `resolve_entity`) | `search.py:54-63` |
| `### Response shape` | Prose description of response dict keys + types — LLM must be able to infer structure without seeing the model | `search.py:65-72` |
| `### Errors` | Enumerated error codes the tool emits + cause; explicit "never raises" reminder | `search.py:74-77` |
| `### Performance budget` | p95 latency + p95 token cap | `search.py:79-80` |

**Worked example — `get_recent_events`:**

```python
def get_recent_events(ticker: str, since: str) -> EventTimeline | dict:
    """Recent disclosures, news, and KIND events for a ticker (MCP-04, JUDGE-04).

    Returns a chronological timeline of events from the vault — each entry
    carries `id` + `snippet_200ch` only, never inline body. Callers requiring
    the full body of an event MUST follow up with `get_filing(id)`.

    ### Behavior contract
    - `ticker`: 6-digit KRX ticker or 8-digit corp_code; normalized via
      `resolve_entity`. Recycled tickers resolve to the active entity at
      "now" (Phase 6 has no `as_of`).
    - `since`: ISO `YYYY-MM-DD` lower bound on `documents.first_seen_at`
      (inclusive). Required.
    - Returns at most 50 events sorted DESC on `first_seen_at`.

    ### Response shape
    Returns `EventTimeline` with `events` — each event carries:
    - `id`: documents.id (sha256) — pass to `get_filing(id)` for body
    - `source`: one of "dart" | "news" | "kind"
    - `date`: ISO `YYYY-MM-DD` (event date, not ingest date)
    - `type`: event_type from `_derived` (Phase 5 D-08 enum) or null
    - `title`: human-readable title
    - `snippet_200ch`: ≤200 chars, wrapped in <vault_excerpt> delimiters,
      prefers `_derived.summary` then `body[:200]` (D-08)
    - `vault_path`: citable path under `vault/raw/...` for JUDGE-04
    - `truncation_applied`: list[str] — names of dropped fields when over budget

    ### Errors
    On failure returns `{"error": {"code", "message", "details"}}` — never
    raises. Codes: `INVALID_TICKER`, `DB_UNAVAILABLE`, `INTERNAL`.

    ### Performance budget
    p95 latency < 5s, p95 response < 8k tokens (cl100k_base) on the
    fixture vault (D-19).
    """
```

**Voice & tone (LLM-facing):** declarative behavioral contract; no marketing copy; no second-person ("you") — write to the LLM as a strict API contract, not a human user. Mirror existing `search.py` register.

---

## Color (N/A — Substitute: Error Code Catalog & Source Status Enum)

**N/A — non-visual phase.**

LLM-facing equivalent — **error code catalog** (extends `src/stock_mcp/errors.py`) and **source status enum**:

### Error Codes — Phase 6 additions to existing `ErrorCode` enum

Existing (from Phase 3): `SEARCH_TIMEOUT`, `INVALID_TICKER`, `DB_UNAVAILABLE`, `EMBEDDING_FAILED`, `BM25_FAILED`, `INTERNAL`.

| New code | Tool(s) | Cause | Operator action | Decision |
|----------|---------|-------|-----------------|----------|
| `WRITE_FORBIDDEN` | `add_note` | path outside whitelist (`vault/notes/` ∪ `notes/private/`) after resolve | reject; no FS write | D-09 |
| `INVALID_FRONTMATTER` | `add_note` | `NoteFrontmatter` validation failed (e.g. missing `type`) | reject with detail of failed field | D-11 |
| `PATH_NOT_FOUND` | `get_filing` | `documents.id` does not match any row | return error; do not 404-cascade | new |
| `NOT_FOUND` | `get_related`, `get_filing` | document_id has no row | return error | new |
| `STALE_DATA` | reserved (consumer hint) | health() reports overall=stale; tools may include hint in details | informational only — JUDGE-05 path | D-15 |

**Codes are stable strings.** Adding a new code is a contract change; renaming requires a Phase 7+ migration.

### Source Status Enum (`health()` D-15)

| Status | Meaning | Mapping rule |
|--------|---------|--------------|
| `ok` | last successful run within threshold | `age_hours < threshold` |
| `stale` | last successful run too old | `age_hours >= threshold` and `age_hours < 7d` |
| `down` | last run errored OR no record at all | last `ingest_runs` row has non-null `error`, OR no rows |

Per-source thresholds (code constant, `STALENESS_THRESHOLDS_HOURS`, monkeypatchable; D-14):
`dart=26, krx=26, news=12, macro=26, kind=26`.

**Overall rule (D-15):** any `down` ⇒ overall=`down`; else any `stale` ⇒ `stale`; else `ok`.

---

## Copywriting Contract (Tool Surface Inventory)

**LLM-facing equivalent — tool surface inventory + write-scope contract.**

### Tool Surface Inventory (7 tools)

| # | Tool | Req | Inputs | Response Pydantic model | Truncation behavior | Errors |
|---|------|-----|--------|-------------------------|---------------------|--------|
| 1 | `get_ticker_overview` | MCP-03, JUDGE-01 | `ticker: str` | `OverviewResponse` (events, portfolio, related_notes, valuation=None, supply_demand=None, private_thesis=None, truncation_applied) | D-22 priority order | `INVALID_TICKER`, `DB_UNAVAILABLE`, `INTERNAL` |
| 2 | `get_recent_events` | MCP-04, JUDGE-04 | `ticker: str, since: str (ISO date)` | `EventTimeline` (events: list[EventRow]) | item-level cap (top_k shrink) | `INVALID_TICKER`, `DB_UNAVAILABLE`, `INTERNAL` |
| 3 | `get_portfolio_state` | MCP-05 | none | `PortfolioState` (holdings, watchlist, source_path, last_modified) | none expected (size bounded) | `PATH_NOT_FOUND`, `INTERNAL` |
| 4 | `get_related` | MCP-06 | `document_id: str, depth: int = 1 (max 2)` | `RelatedSet` (related: list[RelatedRow]) | item-level cap | `NOT_FOUND`, `DB_UNAVAILABLE`, `INTERNAL` |
| 5 | `get_filing` | MCP-07 | `id: str (sha256)` | `FilingResponse` (id, vault_path, frontmatter, body, body_chars, truncated) | body cap @ 200K chars + `truncated=true` | `NOT_FOUND`, `DB_UNAVAILABLE`, `INTERNAL` |
| 6 | `add_note` | MCP-08 | `path: str, body: str, frontmatter: dict\|None` | `AddNoteResponse` (vault_path, action: 'created'\|'appended', idempotent: bool) | n/a | `WRITE_FORBIDDEN`, `INVALID_FRONTMATTER`, `INTERNAL` |
| 7 | `health` | MCP-09 | none | `HealthResponse` (overall, sources: dict[str, SourceHealth], db: SourceHealth, timestamp) | none | `INTERNAL` (never DB_UNAVAILABLE — DB-down is a successful response with `db.status='down'`) |

### Pydantic Model Conventions

All response models in `src/stock_mcp/models.py` (extending existing file):

- `model_config = ConfigDict(extra="forbid")` — verbatim Phase 3 pattern
- Field-level `Literal[...]` for enums (status, action, source)
- Datetimes ISO-8601 with KST `ZoneInfo("Asia/Seoul")` (D-12 timestamp convention)
- Phase-10 placeholders MUST be `field: SomeModel | None = None` so model_dump renders explicit `null` in JSON (D-01)

### Write-Scope Contract (`add_note`)

| Rule | Decision | Rationale |
|------|----------|-----------|
| Whitelist roots | `vault/notes/` ∪ `notes/private/` only | D-09; raw/, ingested/, dashboards/ are write-protected SoT |
| Path normalization | `Path(p).resolve(strict=False)` then `is_relative_to(allowed_root.resolve())` | symlink + `..` traversal closed atomically |
| Conflict policy | append-only with `\n\n---\n## {ISO ts KST}\n\n` separator | D-10 |
| Frontmatter merge | `tickers`/`tags` union; `updated` always refreshed | D-10 |
| Required frontmatter field | `type` ∈ {thesis, journal, conviction, note} | D-11; missing → `INVALID_FRONTMATTER` |
| Auto-fill defaults | `created` (now if absent), `updated` (always now), `author='yamin'` | D-11 |
| Path aliases | `journal/today` → `notes/private/journal/{KST date}.md`; `005930/thesis` → `notes/private/005930/thesis.md` | D-12 |
| Auto-mkdir | `parents=True, exist_ok=True` within whitelist only | D-12 |
| Auto `.md` extension | append if missing | D-12 |
| Idempotency | identical timestamp header + body within last append → skip + `idempotent=true` | D-13 |
| Atomic write | `tempfile.mkstemp` + `os.replace` (mirrors `shared/frontmatter.write_frontmatter`) | Pitfall 8 race protection |

### Two-Step Interaction Patterns (LLM Chaining)

The contract is LLM-facing chain-discoverable; docstrings must describe these flows so Claude executes them naturally without orchestration in the tool itself:

```
events listing → full body
  Claude: get_recent_events(ticker="005930", since="2026-04-01")
    → returns 12 events with {id, snippet_200ch, vault_path}
  Claude: get_filing(id="<sha256 of an interesting one>")
    → returns full body up to 200K chars

related neighbors → walk
  Claude: get_related(document_id=X, depth=1)
    → returns 5 neighbors with {id, edge_type, depth, vault_path, snippet}
  Claude: get_filing(id=<neighbor id>)
    → full body

memo → ingest pickup (async)
  Claude: add_note(path="005930/thesis", body="...", frontmatter={...})
    → returns {vault_path, action="created", idempotent=false}
  ...next ingest cycle picks up file from vault and indexes into Postgres
```

**Critical contract:** the tool surface NEVER inlines body in list results. Two-step is non-negotiable — this is the token-budget guarantee.

### Token Budget — Per-Tool Targets

| Tool | p95 latency (s) | p95 tokens (cl100k_base) | Truncation expected? |
|------|-----------------|---------------------------|----------------------|
| `get_ticker_overview` | < 5.0 | < 8,000 | yes — D-22 priority order |
| `get_recent_events` | < 5.0 | < 8,000 | yes — item cap |
| `get_portfolio_state` | < 1.0 | < 4,000 | no |
| `get_related` | < 2.0 | < 4,000 | yes — item cap |
| `get_filing` | < 3.0 | up to ~50,000 (single doc; 200K char cap) | body-level only |
| `add_note` | < 1.0 | < 1,000 | no |
| `health` | < 2.0 | < 2,000 | no |

**Truncation priority order** (D-22, low → high — drop low first):
`private_thesis → valuation → supply_demand → portfolio → related_notes → events`

In Phase 6 only `events` and `related_notes` ever hit truncation (D-23) since the three Phase-10 placeholders are always `None`.

---

## Registry Safety (Tool Module Layout)

**N/A for shadcn/visual blocks — non-visual phase.**

LLM-facing equivalent — **tool module layout** governs which code may register tools and which may not:

| Module path | Owner | Allowed to import | Phase |
|-------------|-------|-------------------|-------|
| `src/stock_mcp/tools/search.py` | Phase 3 (existing — singleton holder) | FastMCP, errors, logging, models, search_core | unchanged |
| `src/stock_mcp/tools/overview.py` | Phase 6 NEW | `from .search import mcp` + Phase 6 helpers | this |
| `src/stock_mcp/tools/events.py` | Phase 6 NEW | same | this |
| `src/stock_mcp/tools/portfolio.py` | Phase 6 NEW | same + `shared.portfolio` | this |
| `src/stock_mcp/tools/related.py` | Phase 6 NEW | same + recursive CTE in `search_core` | this |
| `src/stock_mcp/tools/filing.py` | Phase 6 NEW | same | this |
| `src/stock_mcp/tools/notes.py` | Phase 6 NEW | same + `shared.frontmatter`, `paths.py` | this |
| `src/stock_mcp/tools/health.py` | Phase 6 NEW | same + `ingest.heartbeat._read_sources` | this |
| `src/stock_mcp/snippets.py` | Phase 6 NEW | injection_defense.wrap_untrusted | this |
| `src/stock_mcp/paths.py` | Phase 6 NEW | stdlib only | this |
| `src/stock_mcp/models.py` | Phase 6 EXTEND | Pydantic | this |

**Guardrails (CI-enforced — match existing COLL-07 pattern):**
- `stock_mcp/tools/*.py` MUST NOT import `anthropic`, `openai` (serving layer is LLM-free; LLM is the *client*).
- `stock_mcp/tools/*.py` MUST NOT call `print()` to stdout — all logging via `log_tool_call` (stderr).
- `stock_mcp/tools/*.py` MUST NOT `raise` past tool boundary — wrap in `to_error_response`.
- `add_note` MUST NOT write outside whitelist; check via `Path.resolve()` + `is_relative_to`.

**Safety gate evidence:** No third-party MCP "registries" exist; FastMCP 2.x is the sole framework. CI tests at `tests/mcp/test_docstring_contract.py` enforce D-24 docstring shape across all 7 tools (MCP-10).

---

## CI Gate Contract (D-19, D-20)

| Gate | Mechanism | Pass criterion |
|------|-----------|----------------|
| Latency | `pytest tests/perf/test_mcp_latency_tokens.py -m slow` — N=20 reps per tool against `tests/fixtures/mcp-vault/` (10 tickers × 100 docs) | p95 < 5s for all tools |
| Token size | `tiktoken` cl100k_base on `json.dumps(response)` for the same N=20 sample | p95 < per-tool table above |
| Docstring shape | `pytest tests/mcp/test_docstring_contract.py` — regex check for the four `### ...` sections per tool | every tool passes |
| Whitelist enforcement | `pytest tests/mcp/test_notes_tool.py::test_whitelist_enforcement` — supplies raw/, /etc/, symlink-to-/etc/ | all reject with `WRITE_FORBIDDEN` |
| Two-step purity | `pytest tests/mcp/test_events_tool.py::test_no_body_in_response` | event list response keys ⊄ {body, content} |
| Persistence: perf history | Save `{tool: {p95_latency_ms, p95_tokens}}` to `tests/perf/{tool_name}.json` | PR diff reviewable |

**Where it runs:** PR test (D-20). Not nightly. Pitfall 6 mitigation: session-scoped Postgres + single ingest run feeds all 7 tool perf tests in one slow test.

---

## Health Response Shape (D-15 fully expanded)

```python
class SourceHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok", "stale", "down"]
    last_success: datetime | None
    age_hours: float | None
    last_error: str | None  # ≤ 200 chars

class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overall: Literal["ok", "stale", "down"]
    sources: dict[str, SourceHealth]  # keys: dart, krx, news, macro, kind
    db: SourceHealth  # status restricted to ok|down (no stale concept), age_hours = None
    timestamp: datetime  # ISO with KST
```

**Data source priority (D-16):**
1. `ingest_runs` SQL aggregate per source (Phase 9 will populate; Phase 6 fixture seeds rows for tests).
2. If 0 rows OR DB unreachable → fallback to `vault/ingested/_status/heartbeat.md` parse via `_read_sources` (refactor to public name).
3. If both fail → `down` for that source with `last_error="no telemetry available"`.

**Pitfall 3 acknowledged:** `ingest_runs` is empty in production today. Phase 6 implementation MUST gracefully fall through to heartbeat without erroring; Phase 9 turns this into a transparent upgrade.

---

## Pre-populated From

| Source | Decisions used |
|--------|----------------|
| `06-CONTEXT.md` | D-01 .. D-24 (24 decisions, all consumed) |
| `06-RESEARCH.md` | Architecture patterns, Pydantic conventions, recursive CTE shape, path safety, tool module layout |
| `src/stock_mcp/tools/search.py` | Docstring contract template (lines 47-81), error envelope pattern, registration call-form |
| `src/stock_mcp/errors.py` | Existing `ErrorCode` enum (extended, not replaced) |
| `src/stock_mcp/models.py` | `ConfigDict(extra="forbid")` Pydantic pattern |
| REQUIREMENTS.md | MCP-03 .. MCP-10 (8 reqs) — all amended wording (Phase 10 P-01/P-02) honored |
| User input | none required (all questions answered upstream) |

---

## Checker Sign-Off

> Adapted dimensions for non-visual MCP tool surface.

- [ ] Dimension 1 — Docstring contract shape (D-24): every tool has 1-line summary + req-IDs, `### Behavior contract`, `### Response shape`, `### Errors`, `### Performance budget` — PENDING
- [ ] Dimension 2 — Response envelope conventions: `<vault_excerpt>` wrap, two-step ID, `truncation_applied`, `idempotent` flag — PENDING
- [ ] Dimension 3 — Error code catalog: WRITE_FORBIDDEN, INVALID_FRONTMATTER, NOT_FOUND, PATH_NOT_FOUND, STALE_DATA added; envelope `{"error": {...}}` uniform — PENDING
- [ ] Dimension 4 — Pydantic schema purity: `extra="forbid"`, Phase-10 placeholders typed `T | None = None`, ISO+KST datetimes — PENDING
- [ ] Dimension 5 — Token budget per tool table met under N=20 fixture (D-19) — PENDING
- [ ] Dimension 6 — Write-scope safety: whitelist + symlink resolve + atomic write; tool modules free of `anthropic`/`openai`/`print`/`raise` — PENDING

**Visual dimensions (1 Copywriting, 2 Visuals, 3 Color, 4 Typography, 5 Spacing, 6 Registry):** marked **N/A — non-visual phase** by checker mapping above.

**Approval:** pending
