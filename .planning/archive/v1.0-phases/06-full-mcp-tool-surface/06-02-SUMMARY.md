---
phase: 06-full-mcp-tool-surface
plan: 02
subsystem: stock_mcp.models + stock_mcp.errors + stock_mcp.snippets + stock_mcp.paths + stock_mcp.repo_root + shared.frontmatter
tags: [foundation, models, errors, helpers, wave-1]
requires:
  - Phase 3 SearchHit/DateRange (extended in this plan)
  - Phase 5 _derived.summary contract (consumed by build_snippet)
  - Phase 6 Plan 06-01 portfolio path cutover (downstream tools assume notes/private/portfolio.md)
provides:
  - "OverviewResponse + EventRow/Timeline + PortfolioRow/State + RelatedRow/Set + FilingResponse + AddNoteResponse + SourceHealth/HealthResponse Pydantic models (extra='forbid')"
  - "ValuationContext / SupplyDemandSignals / PrivateThesis Phase-10 placeholders"
  - "ErrorCode.{WRITE_FORBIDDEN, INVALID_FRONTMATTER, NOT_FOUND, PATH_NOT_FOUND, STALE_DATA, INVALID_DATE}"
  - "build_snippet(body, derived_summary) wrapping in <vault_excerpt>"
  - "safe_join(repo_root, user_path) whitelist enforcement (vault/notes/ ∪ notes/private/)"
  - "resolve_path_alias(user_path) for D-12 user-friendly aliases"
  - "NoteFrontmatter Pydantic model in src/shared/frontmatter.py"
  - "repo_root() public helper at src/stock_mcp/repo_root.py"
affects:
  - Plan 06-04 (get_filing, get_recent_events): may import EventRow, EventTimeline, FilingResponse, build_snippet, ErrorCode.{NOT_FOUND, INVALID_DATE}
  - Plan 06-05 (get_related, get_portfolio_state): may import RelatedRow/Set, PortfolioRow/State, repo_root
  - Plan 06-06 (add_note): may import AddNoteResponse, safe_join, resolve_path_alias, NoteFrontmatter, ErrorCode.{WRITE_FORBIDDEN, INVALID_FRONTMATTER}, repo_root
  - Plan 06-07 (health): may import SourceHealth, HealthResponse, ErrorCode.STALE_DATA, repo_root
  - Plan 06-08 (get_ticker_overview): may import OverviewResponse + repo_root
tech-stack:
  added: []
  patterns:
    - "Pydantic v2 extra='forbid' on every Phase 6 response model"
    - "Phase-10 placeholders typed `T | None = None` so OverviewResponse signature is stable across phases"
    - "<vault_excerpt> snippet wrapper — distinct from <untrusted ...> wrap_untrusted (the latter requires source/trust/doc_id; the former is the lighter trust marker for tool responses without per-source attribution)"
    - "Path.resolve() + is_relative_to() pair for write-scope enforcement (collapses .. + follows symlinks atomically)"
    - "Public repo_root() helper — eliminates per-tool _repo_root() duplication; STOCK_REPO_ROOT env var enables test/CI overrides"
key-files:
  created:
    - src/stock_mcp/snippets.py
    - src/stock_mcp/paths.py
    - src/stock_mcp/repo_root.py
    - tests/stock_mcp/__init__.py
    - tests/stock_mcp/test_models.py
    - tests/stock_mcp/test_errors.py
    - tests/stock_mcp/test_snippets.py
    - tests/stock_mcp/test_paths.py
    - tests/stock_mcp/test_repo_root.py
    - tests/shared/__init__.py
    - tests/shared/test_note_frontmatter.py
  modified:
    - src/stock_mcp/models.py
    - src/stock_mcp/errors.py
    - src/shared/frontmatter.py
decisions:
  - "build_snippet uses inline <vault_excerpt> wrapping rather than reusing wrap_untrusted: the latter mandates source/trust/doc_id attributes which Phase 6 tools cannot always provide (e.g. portfolio rows have no provenance triple). The plan explicitly authorized this fallback and existing tests/e2e/test_search_citation_schema.py already accepts both <vault_excerpt> and <untrusted ...>."
  - "ErrorCode additions append-only — Phase 3 ordering preserved verbatim (no renumber, no reorder)."
  - "NoteFrontmatter co-located with FrontMatter/DerivedBlock in src/shared/frontmatter.py per plan; Phase 8 NOTE-03 will reuse from same module."
  - "Empty derived_summary string falls through to body fallback (truthiness check) — tested explicitly so callers passing '' (sentinel for 'no summary') get expected behavior."
metrics:
  duration_min: 12
  tasks: 3
  files_changed: 14
  completed: 2026-04-29
---

# Phase 06 Plan 02: Models, Errors, and Helpers Summary

**One-liner:** Wave-1 foundation — every Phase 6 Pydantic response model, six new ErrorCode constants, three pure helpers (snippets, paths, repo_root), and the NoteFrontmatter schema, all unit-tested before any tool is registered.

## Outcomes

- **5 source modules** new/extended: `models.py` (12 new classes incl. OverviewResponse), `errors.py` (+6 codes), `snippets.py`, `paths.py`, `repo_root.py`, plus `shared/frontmatter.py` (NoteFrontmatter).
- **6 test files** + 2 `__init__.py` markers; **42 tests passing** in 2.15s.
- All Phase 6 response models pin `extra='forbid'`; Phase-10 placeholders typed `T | None = None`.
- `safe_join` covers `..` escapes, off-whitelist paths, and symlink escapes (P3-P5).
- `repo_root()` honors `STOCK_REPO_ROOT` env override → walks up for `pyproject.toml`+`vault/` markers → falls back to cwd.

## Tasks

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Add Pydantic response models + extend ErrorCode | 5ce4170 | src/stock_mcp/models.py, src/stock_mcp/errors.py, tests/stock_mcp/__init__.py, tests/stock_mcp/test_errors.py, tests/stock_mcp/test_models.py |
| 2 | Add snippets.py + paths.py helpers + NoteFrontmatter | 97abeb2 | src/stock_mcp/snippets.py, src/stock_mcp/paths.py, src/shared/frontmatter.py, tests/shared/__init__.py, tests/stock_mcp/test_snippets.py, tests/stock_mcp/test_paths.py, tests/shared/test_note_frontmatter.py |
| 3 | Add public repo_root() helper module | 1fc16c4 | src/stock_mcp/repo_root.py, tests/stock_mcp/test_repo_root.py |

## Acceptance Criteria — Verified

**Task 1:**
- `grep -c "class OverviewResponse" src/stock_mcp/models.py` → **1**
- `grep -cE "WRITE_FORBIDDEN|INVALID_FRONTMATTER|NOT_FOUND|PATH_NOT_FOUND|STALE_DATA|INVALID_DATE" src/stock_mcp/errors.py` → **9** (6 enum members + 3 in the explanatory comment block; well above threshold of ≥6)
- `grep -cE 'model_config = ConfigDict\(extra="forbid"\)' src/stock_mcp/models.py` → **17** (well above ≥14)
- 3 placeholder Optional fields in OverviewResponse → **3 hits** confirmed
- `pytest tests/stock_mcp/test_models.py tests/stock_mcp/test_errors.py` → **15 passed**

**Task 2:**
- `grep -c "def build_snippet" src/stock_mcp/snippets.py` → **1**
- `grep -cE "def safe_join|def resolve_path_alias" src/stock_mcp/paths.py` → **2**
- `grep -c "class NoteFrontmatter" src/shared/frontmatter.py` → **1**
- `grep -c "vault_excerpt" src/stock_mcp/snippets.py` → **4** (≥1 satisfied)
- `grep -c "is_relative_to" src/stock_mcp/paths.py` → **2** (≥1 satisfied)
- `pytest tests/stock_mcp/test_snippets.py tests/stock_mcp/test_paths.py tests/shared/test_note_frontmatter.py` → **22 passed**

**Task 3:**
- `grep -cE "^def repo_root\(" src/stock_mcp/repo_root.py` → **1**
- `grep -c '__all__ = ["repo_root"]' src/stock_mcp/repo_root.py` → **1**
- `grep -c "STOCK_REPO_ROOT" src/stock_mcp/repo_root.py` → **2**
- `grep -c "pyproject.toml" src/stock_mcp/repo_root.py` → **2**
- Import smoke from project root works: `repo_root()` returns absolute Path
- `pytest tests/stock_mcp/test_repo_root.py` → **5 passed**

**Cross-module import:** `uv run python -c "from stock_mcp import models, errors, snippets, paths, repo_root; from shared.frontmatter import NoteFrontmatter"` → exit 0.

**Full plan test slice:** **42 passed in 2.15s**.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `wrap_untrusted` produces `<untrusted ...>` not `<vault_excerpt>`**
- **Found during:** Task 2 read-first pass on `src/ingest/injection_defense.py`.
- **Issue:** Plan suggested `from src.ingest.injection_defense import wrap_untrusted` but that helper requires (body, source, trust_level, doc_id) and emits `<untrusted source="..." trust="..." doc_id="...">` tags — not `<vault_excerpt>` as the plan's behavior tests S1-S3 require. The two-arg `build_snippet(body, derived_summary)` signature is incompatible with `wrap_untrusted`.
- **Fix:** Used the inline 4-line wrapper option the plan explicitly authorizes: `f"<vault_excerpt>{trimmed}</vault_excerpt>"`. Documented the trust-marker distinction in the module docstring; existing E2E test `tests/e2e/test_search_citation_schema.py` already accepts both forms (`<vault_excerpt|<untrusted `).
- **Files modified:** src/stock_mcp/snippets.py
- **Commit:** 97abeb2

**2. [Rule 3 - Blocking] Plan code used `from src.ingest...` import style**
- **Found during:** Task 2 path planning.
- **Issue:** Plan code samples used `from src.ingest.injection_defense import wrap_untrusted` and `from src.stock_mcp.repo_root import repo_root` (with `src.` prefix), but `pyproject.toml` declares `pythonpath = ["src"]` and existing modules import as `from stock_mcp...` and `from ingest...`. The `src.` prefix would have broken consistency with the rest of the codebase.
- **Fix:** All new modules and tests use the canonical `from stock_mcp...` / `from shared...` import style. Tests verified by `uv run pytest`.
- **Files modified:** src/stock_mcp/{snippets,paths,repo_root}.py, all new test files
- **Commit:** 97abeb2 / 1fc16c4

### Plan Behavior Tests — Coverage Beyond the 6/3/5 Mandated

- Task 1: 15 tests (vs. plan's 6 behaviors) — adds Literal-rejection coverage for EventRow.source, AddNoteResponse.action, SourceHealth.extra='forbid'.
- Task 2: 22 tests (vs. plan's 11 behaviors) — adds explicit empty-summary-string fallback (S2 edge), `journal` alone (P6 sibling), already-`.md` paths.
- Task 3: 5 tests as planned.

## Downstream Impact

Wave-2 plans (06-04 ... 06-07) and Wave-3 (06-08) may now:

- `from stock_mcp.models import OverviewResponse, EventRow, EventTimeline, FilingResponse, ...`
- `from stock_mcp.errors import ErrorCode  # WRITE_FORBIDDEN, NOT_FOUND, ...`
- `from stock_mcp.snippets import build_snippet`
- `from stock_mcp.paths import safe_join, resolve_path_alias`
- `from stock_mcp.repo_root import repo_root  # NOT a per-tool _repo_root() copy`
- `from shared.frontmatter import NoteFrontmatter  # for add_note write path`

No tool functions are registered yet; that work begins in Plan 06-03 (fixture vault + deps) and Plan 06-04 (first tool: get_filing).

## Self-Check: PASSED

- Task 1 commit `5ce4170` present in `git log`.
- Task 2 commit `97abeb2` present in `git log`.
- Task 3 commit `1fc16c4` present in `git log`.
- All 14 source/test files exist on disk.
- Full plan test slice: `42 passed in 2.15s`.
- Cross-module import: exit 0.
