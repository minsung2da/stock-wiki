---
phase: 06-full-mcp-tool-surface
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - src/stock_mcp/models.py
  - src/stock_mcp/errors.py
  - src/stock_mcp/snippets.py
  - src/stock_mcp/paths.py
  - src/shared/frontmatter.py
  - tests/stock_mcp/__init__.py
  - tests/stock_mcp/test_models.py
  - tests/stock_mcp/test_errors.py
  - tests/stock_mcp/test_snippets.py
  - tests/stock_mcp/test_paths.py
autonomous: true
requirements: [MCP-03, MCP-04, MCP-05, MCP-06, MCP-07, MCP-08, MCP-09]
must_haves:
  truths:
    - "All Phase 6 Pydantic response models are defined with extra='forbid' and Phase-10 placeholders typed `T | None = None`"
    - "Phase 6 ErrorCode constants (WRITE_FORBIDDEN, INVALID_FRONTMATTER, NOT_FOUND, PATH_NOT_FOUND, STALE_DATA) exist"
    - "build_snippet() helper wraps text in <vault_excerpt> delimiters and prefers _derived.summary"
    - "safe_join() rejects paths outside vault/notes/ ∪ notes/private/ after symlink+`..` resolution"
    - "NoteFrontmatter Pydantic model in src/shared/frontmatter.py validates type/tickers/tags/created/updated/author/conviction_score"
  artifacts:
    - path: "src/stock_mcp/models.py"
      provides: "OverviewResponse, EventRow, EventTimeline, PortfolioRow, PortfolioState, RelatedRow, RelatedSet, FilingResponse, AddNoteResponse, SourceHealth, HealthResponse, ValuationContext, SupplyDemandSignals, PrivateThesis"
      contains: "class OverviewResponse"
    - path: "src/stock_mcp/errors.py"
      provides: "Phase 6 ErrorCode constants"
      contains: "WRITE_FORBIDDEN"
    - path: "src/stock_mcp/snippets.py"
      provides: "build_snippet(body, derived_summary) helper"
      contains: "vault_excerpt"
    - path: "src/stock_mcp/paths.py"
      provides: "resolve_path_alias() + safe_join() helpers"
      contains: "is_relative_to"
    - path: "src/shared/frontmatter.py"
      provides: "NoteFrontmatter Pydantic model (extends existing module)"
      contains: "class NoteFrontmatter"
  key_links:
    - from: "src/stock_mcp/snippets.py"
      to: "src/ingest/injection_defense.py wrap_untrusted"
      via: "import"
      pattern: "wrap_untrusted|<vault_excerpt>"
    - from: "src/stock_mcp/paths.py"
      to: "Path.resolve + is_relative_to"
      via: "stdlib"
      pattern: "is_relative_to"
---

<objective>
Wave-1 foundation: every Pydantic response model, every new error code, and every shared helper (snippets, paths, NoteFrontmatter) the seven Wave-2 tools need. No tool functions are registered in this plan — only the data contracts and pure helpers.

Purpose: Wave-2 tool plans (06-04, 06-05, 06-06, 06-07) and Wave-3 composite (06-08) all import from these modules. Defining contracts FIRST prevents cross-plan rework when downstream executors discover a missing field.

Output: 5 new/extended source modules + 4 unit-test files; all helpers grep-verifiable.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md
@.planning/phases/06-full-mcp-tool-surface/06-RESEARCH.md
@.planning/phases/06-full-mcp-tool-surface/06-UI-SPEC.md
@src/stock_mcp/models.py
@src/stock_mcp/errors.py
@src/shared/frontmatter.py
@src/ingest/injection_defense.py

<interfaces>
Existing Pydantic pattern (src/stock_mcp/models.py):
```python
from pydantic import BaseModel, ConfigDict
class SearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ...
```

Existing ErrorCode enum (src/stock_mcp/errors.py:15-21):
```python
class ErrorCode(str, Enum):
    SEARCH_TIMEOUT = "SEARCH_TIMEOUT"
    INVALID_TICKER = "INVALID_TICKER"
    DB_UNAVAILABLE = "DB_UNAVAILABLE"
    EMBEDDING_FAILED = "EMBEDDING_FAILED"
    BM25_FAILED = "BM25_FAILED"
    INTERNAL = "INTERNAL"
```

Existing injection wrapper (src/ingest/injection_defense.py): function `wrap_untrusted(text: str) -> str` exists and is reused by search_core.py:309 — re-use it for snippet wrapping per D-08.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add Pydantic response models + extend ErrorCode</name>
  <read_first>
    - src/stock_mcp/models.py (existing patterns: SearchHit, SearchResult, DateRange)
    - src/stock_mcp/errors.py (existing ErrorCode enum)
    - .planning/phases/06-full-mcp-tool-surface/06-UI-SPEC.md "Tool Surface Inventory" + "Health Response Shape (D-15 fully expanded)"
    - .planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md D-01, D-05, D-06, D-07, D-15, D-21, D-22
  </read_first>
  <behavior>
    - Test 1: OverviewResponse instantiates with valuation=None, supply_demand=None, private_thesis=None as defaults; non-None values are accepted but Phase 6 callers always pass None.
    - Test 2: OverviewResponse(extra={"foo": "bar"}) raises pydantic.ValidationError (extra='forbid').
    - Test 3: HealthResponse with overall='down' and one source SourceHealth(status='down') round-trips via model_dump_json.
    - Test 4: PortfolioRow accepts qty=None and avg_cost=None (watchlist case).
    - Test 5: FilingResponse with body_chars=300_000 and truncated=True is valid; body field length ≤ 200_001.
    - Test 6: ErrorCode.WRITE_FORBIDDEN, INVALID_FRONTMATTER, NOT_FOUND, PATH_NOT_FOUND, STALE_DATA exist as enum members and serialize to their literal string names via .value.
  </behavior>
  <action>
    1. **Extend src/stock_mcp/errors.py** — Append five new members to the `ErrorCode` enum (PRESERVE existing 6):
       ```python
       WRITE_FORBIDDEN = "WRITE_FORBIDDEN"
       INVALID_FRONTMATTER = "INVALID_FRONTMATTER"
       NOT_FOUND = "NOT_FOUND"
       PATH_NOT_FOUND = "PATH_NOT_FOUND"
       STALE_DATA = "STALE_DATA"
       ```
       Do NOT renumber or reorder existing members.

    2. **Extend src/stock_mcp/models.py** — Add the following classes (all with `model_config = ConfigDict(extra="forbid")`). Use Python 3.12 type hints, `Literal` from `typing`, `datetime` from stdlib, `Field` from pydantic.

       ```python
       # Phase 10 placeholders (D-01) — always None in Phase 6
       class ValuationContext(BaseModel):
           model_config = ConfigDict(extra="forbid")
           # Empty in Phase 6; Phase 10 fills. Pydantic accepts empty model.

       class SupplyDemandSignals(BaseModel):
           model_config = ConfigDict(extra="forbid")

       class PrivateThesis(BaseModel):
           model_config = ConfigDict(extra="forbid")

       # MCP-04 EventRow (D-05)
       class EventRow(BaseModel):
           model_config = ConfigDict(extra="forbid")
           id: str
           source: Literal["dart", "news", "kind"]
           date: str  # ISO YYYY-MM-DD
           type: str | None = None
           title: str
           snippet_200ch: str  # wrapped with <vault_excerpt>
           vault_path: str

       class EventTimeline(BaseModel):
           model_config = ConfigDict(extra="forbid")
           events: list[EventRow]
           truncation_applied: list[str] = Field(default_factory=list)

       # MCP-05 PortfolioRow (D-21)
       class PortfolioRow(BaseModel):
           model_config = ConfigDict(extra="forbid")
           ticker: str
           corp_code: str | None = None
           qty: float | None = None
           avg_cost: float | None = None
           tags: list[str] = Field(default_factory=list)
           note: str | None = None

       class PortfolioState(BaseModel):
           model_config = ConfigDict(extra="forbid")
           holdings: list[PortfolioRow]
           watchlist: list[PortfolioRow]
           source_path: str
           last_modified: datetime

       # MCP-06 RelatedRow (D-06)
       class RelatedRow(BaseModel):
           model_config = ConfigDict(extra="forbid")
           id: str
           edge_type: str
           depth: int
           vault_path: str | None = None
           snippet_200ch: str | None = None

       class RelatedSet(BaseModel):
           model_config = ConfigDict(extra="forbid")
           related: list[RelatedRow]
           truncation_applied: list[str] = Field(default_factory=list)

       # MCP-07 FilingResponse (D-07)
       class FilingResponse(BaseModel):
           model_config = ConfigDict(extra="forbid")
           id: str
           vault_path: str
           frontmatter: dict
           body: str
           body_chars: int  # original (untruncated) length
           truncated: bool

       # MCP-08 AddNoteResponse (D-10, D-13)
       class AddNoteResponse(BaseModel):
           model_config = ConfigDict(extra="forbid")
           vault_path: str
           action: Literal["created", "appended"]
           idempotent: bool

       # MCP-09 SourceHealth + HealthResponse (D-15)
       class SourceHealth(BaseModel):
           model_config = ConfigDict(extra="forbid")
           status: Literal["ok", "stale", "down"]
           last_success: datetime | None = None
           age_hours: float | None = None
           last_error: str | None = None  # ≤200 chars

       class HealthResponse(BaseModel):
           model_config = ConfigDict(extra="forbid")
           overall: Literal["ok", "stale", "down"]
           sources: dict[str, SourceHealth]
           db: SourceHealth
           timestamp: datetime

       # MCP-03 OverviewResponse (D-01, D-02, D-22)
       class OverviewResponse(BaseModel):
           model_config = ConfigDict(extra="forbid")
           ticker: str
           corp_code: str | None = None
           events: list[EventRow] = Field(default_factory=list)
           portfolio: PortfolioRow | None = None
           related_notes: list[SearchHit] = Field(default_factory=list)
           valuation: ValuationContext | None = None
           supply_demand: SupplyDemandSignals | None = None
           private_thesis: PrivateThesis | None = None
           truncation_applied: list[str] = Field(default_factory=list)
       ```

    3. **Create tests/stock_mcp/__init__.py** (empty file, marker only).

    4. **Create tests/stock_mcp/test_models.py** + **tests/stock_mcp/test_errors.py** covering the 6 behaviors above.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run pytest tests/stock_mcp/test_models.py tests/stock_mcp/test_errors.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "class OverviewResponse" src/stock_mcp/models.py` returns 1 hit.
    - `grep -nE "WRITE_FORBIDDEN|INVALID_FRONTMATTER|NOT_FOUND|PATH_NOT_FOUND|STALE_DATA" src/stock_mcp/errors.py` returns 5 hits.
    - `grep -cE "model_config = ConfigDict\(extra=\"forbid\"\)" src/stock_mcp/models.py` returns ≥14 (one per Phase 6 model added).
    - `grep -E "valuation: ValuationContext \| None = None|supply_demand: SupplyDemandSignals \| None = None|private_thesis: PrivateThesis \| None = None" src/stock_mcp/models.py` returns 3 hits.
    - Test command exits 0; ≥6 tests pass.
  </acceptance_criteria>
  <done>All Phase 6 response models + 5 new error codes defined; tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add snippets.py + paths.py helpers + NoteFrontmatter</name>
  <read_first>
    - src/ingest/injection_defense.py (search for `wrap_untrusted` function)
    - src/shared/frontmatter.py (existing FrontMatter, DerivedBlock, write_frontmatter pattern lines 22+, 243-261)
    - .planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md D-08 (snippet rules), D-09 (whitelist), D-11 (NoteFrontmatter), D-12 (path aliases)
    - .planning/phases/06-full-mcp-tool-surface/06-RESEARCH.md "Path whitelist check (D-09)" code example
    - .planning/phases/06-full-mcp-tool-surface/06-UI-SPEC.md "Write-Scope Contract"
  </read_first>
  <behavior>
    - Test S1: build_snippet(body="abc"*100, derived_summary="short summary") returns "<vault_excerpt>short summary</vault_excerpt>" (uses summary when present, ≤200 chars).
    - Test S2: build_snippet(body="x"*500, derived_summary=None) returns first 200 chars of body wrapped in `<vault_excerpt>...</vault_excerpt>`.
    - Test S3: build_snippet(body="", derived_summary=None) returns "<vault_excerpt></vault_excerpt>".
    - Test P1: safe_join(repo_root, "vault/notes/foo.md") returns absolute path under vault/notes/.
    - Test P2: safe_join(repo_root, "notes/private/journal/2026-01-01.md") returns absolute path under notes/private/.
    - Test P3: safe_join(repo_root, "raw/dart/foo.md") raises StructuredError with code=WRITE_FORBIDDEN.
    - Test P4: safe_join(repo_root, "../etc/passwd") raises StructuredError with code=WRITE_FORBIDDEN.
    - Test P5: safe_join with a symlink target outside whitelist raises WRITE_FORBIDDEN (resolve follows symlink).
    - Test P6: resolve_path_alias("journal/today") returns "notes/private/journal/{YYYY-MM-DD KST}.md" with current KST date.
    - Test P7: resolve_path_alias("005930/thesis") returns "notes/private/005930/thesis.md".
    - Test P8: resolve_path_alias("vault/notes/foo") returns "vault/notes/foo.md" (auto .md extension).
    - Test F1: NoteFrontmatter(type="thesis", tickers=["005930"]) is valid; created/updated auto-filled if absent.
    - Test F2: NoteFrontmatter(tickers=["005930"]) (no type) raises pydantic.ValidationError.
    - Test F3: NoteFrontmatter(type="conviction", conviction_score=0.7) is valid.
  </behavior>
  <action>
    1. **Create src/stock_mcp/snippets.py**:
       ```python
       """Snippet builder for MCP tools (D-08).

       Prefers _derived.summary when present (Phase 5 D-08), else first 200 chars
       of body. Always wraps in <vault_excerpt> XML delimiters via injection_defense
       so downstream LLMs distinguish trusted prompt from retrieved content.
       """
       from __future__ import annotations
       from src.ingest.injection_defense import wrap_untrusted

       SNIPPET_MAX_CHARS = 200

       def build_snippet(body: str, derived_summary: str | None) -> str:
           src = derived_summary if derived_summary else (body or "")
           trimmed = src[:SNIPPET_MAX_CHARS]
           return wrap_untrusted(trimmed)
       ```
       If `wrap_untrusted` import path differs in the codebase (verify with `grep -rn "def wrap_untrusted" src/`), adjust the import accordingly. If the function does not exist with that exact name, locate the existing wrapper that produces `<vault_excerpt>...</vault_excerpt>` and use it; otherwise inline a 4-line wrapper that wraps `f"<vault_excerpt>{trimmed}</vault_excerpt>"`.

    2. **Create src/stock_mcp/paths.py**:
       ```python
       """Path helpers for add_note (D-09, D-12).

       safe_join: whitelist enforcement (vault/notes/ ∪ notes/private/) with
       symlink + `..` resolution.
       resolve_path_alias: convert user-friendly aliases to canonical paths.
       """
       from __future__ import annotations
       from datetime import datetime
       from pathlib import Path
       from zoneinfo import ZoneInfo
       import re

       from .errors import ErrorCode, StructuredError

       _WHITELIST_PREFIXES = ("vault/notes/", "notes/private/")

       def _allowed_roots(repo_root: Path) -> tuple[Path, ...]:
           rr = repo_root.resolve()
           return tuple((rr / p).resolve() for p in ("vault/notes", "notes/private"))

       def safe_join(repo_root: Path, user_path: str) -> Path:
           rr = repo_root.resolve()
           candidate = (rr / user_path).resolve()
           roots = _allowed_roots(repo_root)
           if not any(candidate == r or candidate.is_relative_to(r) for r in roots):
               raise StructuredError(
                   ErrorCode.WRITE_FORBIDDEN,
                   f"path outside whitelist: {user_path!r}",
                   details={"allowed_prefixes": list(_WHITELIST_PREFIXES)},
               )
           return candidate

       _TICKER6 = re.compile(r"^[0-9]{6}$")

       def resolve_path_alias(user_path: str) -> str:
           """Convert aliases per D-12. Returns repo-relative path string with .md."""
           p = user_path.strip().rstrip("/")
           kst_today = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
           if p in ("journal", "journal/today"):
               return f"notes/private/journal/{kst_today}.md"
           if p.startswith("journal/"):
               # journal/<name> -> notes/private/journal/<name>.md
               name = p[len("journal/"):]
               return f"notes/private/journal/{name}{'' if name.endswith('.md') else '.md'}"
           # ticker/<kind> alias: e.g., 005930/thesis
           parts = p.split("/", 1)
           if len(parts) == 2 and _TICKER6.match(parts[0]):
               kind = parts[1]
               kind_md = kind if kind.endswith(".md") else f"{kind}.md"
               return f"notes/private/{parts[0]}/{kind_md}"
           # No alias matched. If under a whitelisted prefix, leave as-is and ensure .md.
           if any(p.startswith(prefix) for prefix in _WHITELIST_PREFIXES):
               return p if p.endswith(".md") else f"{p}.md"
           # Unrecognized: return as-is; safe_join will reject if outside whitelist.
           return p if p.endswith(".md") else f"{p}.md"
       ```

    3. **Extend src/shared/frontmatter.py** — Add `NoteFrontmatter` Pydantic model after the existing `DerivedBlock` definition. Place it in the same file per CONTEXT specifics (Phase 8 NOTE-03 will reuse).
       ```python
       from typing import Literal
       from datetime import datetime
       from zoneinfo import ZoneInfo

       def _now_kst() -> datetime:
           return datetime.now(ZoneInfo("Asia/Seoul"))

       class NoteFrontmatter(BaseModel):
           model_config = ConfigDict(extra="forbid", populate_by_name=True)
           type: Literal["thesis", "journal", "conviction", "note"]
           tickers: list[str] = Field(default_factory=list)
           tags: list[str] = Field(default_factory=list)
           created: datetime = Field(default_factory=_now_kst)
           updated: datetime = Field(default_factory=_now_kst)
           author: str = "yamin"
           conviction_score: float | None = Field(default=None, ge=0.0, le=1.0)
       ```
       Verify the existing imports (`from pydantic import BaseModel, ConfigDict, Field`) cover what's needed; add Literal/datetime/ZoneInfo as needed.

    4. **Create tests/stock_mcp/test_snippets.py + test_paths.py** covering S1-S3, P1-P8 above. Tests for NoteFrontmatter (F1-F3) live in test_models.py extension or a new tests/shared/test_note_frontmatter.py — pick the latter to keep concerns separate. Add `tests/shared/test_note_frontmatter.py`.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run pytest tests/stock_mcp/test_snippets.py tests/stock_mcp/test_paths.py tests/shared/test_note_frontmatter.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "def build_snippet" src/stock_mcp/snippets.py` returns 1 hit.
    - `grep -n "def safe_join\|def resolve_path_alias" src/stock_mcp/paths.py` returns 2 hits.
    - `grep -n "class NoteFrontmatter" src/shared/frontmatter.py` returns 1 hit.
    - `grep -n "vault_excerpt" src/stock_mcp/snippets.py` returns ≥1 hit (delimiter present).
    - `grep -n "is_relative_to" src/stock_mcp/paths.py` returns ≥1 hit.
    - Test command exits 0; ≥11 tests pass (S1-S3 + P1-P8 + F1-F3).
  </acceptance_criteria>
  <done>snippets.py + paths.py created; NoteFrontmatter added to frontmatter.py; all helpers + model unit-tested.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| MCP caller (LLM) → tool function | Untrusted input via `path` arg in add_note (later) consumed by paths.py here |
| filesystem → tool response | Untrusted body content snippet rendered into LLM prompt |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-6-02-01 | Tampering | paths.safe_join | mitigate | Path.resolve() follows symlinks; is_relative_to check rejects everything outside whitelist (D-09). Test P3-P5 cover. |
| T-6-02-02 | Tampering (prompt injection) | snippets.build_snippet | mitigate | wrap_untrusted XML delimiters per D-08 / INGEST-09 reuse. |
| T-6-02-03 | Tampering | NoteFrontmatter validation | mitigate | Pydantic extra='forbid' + Literal['thesis','journal','conviction','note'] for type field; missing type → ValidationError → INVALID_FRONTMATTER (downstream Plan 06-06). |
</threat_model>

<verification>
- All 4 module files importable from a fresh Python session: `python -c "from src.stock_mcp import models, errors, snippets, paths; from src.shared.frontmatter import NoteFrontmatter"`.
- Tests in both tasks green.
</verification>

<success_criteria>
- `uv run pytest tests/stock_mcp/test_models.py tests/stock_mcp/test_errors.py tests/stock_mcp/test_snippets.py tests/stock_mcp/test_paths.py tests/shared/test_note_frontmatter.py -x -q` exits 0.
- All grep acceptance criteria satisfied.
</success_criteria>

<output>
Create `.planning/phases/06-full-mcp-tool-surface/06-02-SUMMARY.md` listing the new modules, exported symbols, and confirming Wave-2 plans may now import them.
</output>
