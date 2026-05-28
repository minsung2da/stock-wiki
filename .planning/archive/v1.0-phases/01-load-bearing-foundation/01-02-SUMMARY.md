---
phase: 01-load-bearing-foundation
plan: 02
subsystem: infra
tags: [python, uv, pydantic, frontmatter, yaml, tdd]

requires:
  - phase: 01-load-bearing-foundation-01
    provides: vault directory structure, docker-compose
provides:
  - Python project with uv dependency groups (collectors, ingest, mcp, dev)
  - Pydantic v2 frontmatter 3-zone schema (provenance, ingest_state, _derived)
  - read_frontmatter/write_frontmatter file I/O functions
  - src/ package layout (collectors, ingest, stock_mcp, db, orchestration, shared)
affects: [collectors, ingest, stock-mcp, db]

tech-stack:
  added: [pydantic-2.13, python-frontmatter-1.1, pyyaml-6.0, python-dotenv, pytest-9, ruff-0.15, mypy]
  patterns: [pydantic-v2-models, yaml-frontmatter-round-trip, 3-zone-frontmatter, tdd-red-green]

key-files:
  created:
    - pyproject.toml
    - src/shared/frontmatter.py
    - tests/conftest.py
    - tests/test_frontmatter.py
  modified: []

key-decisions:
  - "ingest dependency group excludes anthropic/openai to enforce cost discipline"
  - "_derived alias with populate_by_name enables both Python and YAML conventions"

patterns-established:
  - "3-zone frontmatter: provenance (collectors), ingest_state (pipeline), _derived (LLM)"
  - "Pydantic model_copy for immutable zone updates"
  - "model_dump(by_alias=True, exclude_none=True) for clean YAML output"
  - "pythonpath=[src] in pytest config for flat imports"

requirements-completed: [FOUND-05, FOUND-06]

duration: 4min
completed: 2026-04-17
---

# Phase 01 Plan 02: Python Project + Frontmatter Schema Summary

**uv-managed Python project with 4 dependency groups and Pydantic v2 3-zone frontmatter schema (provenance/ingest_state/_derived) with 10 passing TDD tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-17T09:17:45Z
- **Completed:** 2026-04-17T09:21:46Z
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments
- pyproject.toml with stock-wiki project definition and 4 dependency groups (collectors, ingest, mcp, dev)
- ingest group provably excludes anthropic/openai per cost discipline constraint
- Pydantic v2 frontmatter models: FrontMatter, ProvenanceBlock, IngestStateBlock, DerivedBlock
- _derived YAML alias correctly round-trips through Pydantic
- read_frontmatter/write_frontmatter file I/O functions
- 10 tests covering round-trip, zone isolation, alias, defaults, file I/O
- src/ package structure: collectors, ingest, stock_mcp, db, orchestration, shared

## Task Commits

Each task was committed atomically:

1. **Task 1: Create pyproject.toml and Python package structure** - `6653e0d` (feat)
2. **Task 2 RED: Add failing frontmatter tests** - `a619fba` (test)
3. **Task 2 GREEN: Implement frontmatter models** - `e5faa9a` (feat)

## Files Created/Modified
- `pyproject.toml` - Project definition with dependency groups
- `src/__init__.py` - Root package
- `src/collectors/__init__.py` - Collectors package placeholder
- `src/ingest/__init__.py` - Ingest package placeholder
- `src/stock_mcp/__init__.py` - MCP server package placeholder
- `src/db/__init__.py` - Database package placeholder
- `src/orchestration/__init__.py` - Orchestration package placeholder
- `src/shared/__init__.py` - Shared utilities package
- `src/shared/frontmatter.py` - Pydantic v2 3-zone frontmatter models
- `tests/__init__.py` - Test package
- `tests/conftest.py` - Shared test fixtures (tmp_vault, sample_yaml)
- `tests/test_frontmatter.py` - 10 tests for frontmatter schema

## Decisions Made
- ingest dependency group excludes anthropic/openai to enforce cost discipline (FOUND-05)
- _derived alias uses populate_by_name=True so Python code uses `.derived` while YAML emits `_derived`
- exclude_none=True in model_dump for clean YAML output without null fields

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Python environment ready, all base+dev dependencies installed
- Frontmatter schema locked -- collectors and ingest can import from shared.frontmatter
- Package structure in place for all downstream modules

## Self-Check: PASSED

All 12 created files verified on disk. All 3 commit hashes verified in git log.

---
*Phase: 01-load-bearing-foundation*
*Completed: 2026-04-17*
