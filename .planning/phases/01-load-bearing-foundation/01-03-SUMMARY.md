---
phase: 01-load-bearing-foundation
plan: 03
subsystem: infra
tags: [pre-commit, gitleaks, ruff, ast, ci-guard, dotenv, wsl]

requires:
  - phase: 01-01
    provides: ".gitignore with .env and notes/private/ exclusions"
  - phase: 01-02
    provides: "pyproject.toml with pytest config, src/ingest/ and src/collectors/ directories"
provides:
  - "AST-based CI import guard preventing anthropic/openai in ingest/collectors"
  - "Pre-commit hooks with gitleaks secret scanning and ruff linting"
  - ".env.example documenting all required environment variables"
  - "WSL migration script for /mnt/c/ to ~/stock"
affects: [collectors, ingest, mcp, ci]

tech-stack:
  added: [gitleaks, pre-commit]
  patterns: [ast-import-guard, env-template-validation]

key-files:
  created:
    - tests/test_import_guard.py
    - tests/test_secrets.py
    - .env.example
    - .pre-commit-config.yaml
    - scripts/migrate-to-wsl.sh
  modified:
    - tests/test_import_guard.py

key-decisions:
  - "Downgraded gitleaks from v8.22.1 to v8.21.2 due to WASM panic on WSL2"

patterns-established:
  - "AST-based import guard pattern: scan directories with banned module list"
  - "Secret template validation: test .env.example existence and content in CI"

requirements-completed: [COLL-07, OPS-06, FOUND-04]

duration: 5min
completed: 2026-04-17
---

# Phase 01 Plan 03: CI Guard & Secret Management Summary

**AST-based import guard enforcing anthropic/openai ban in ingest/collectors, gitleaks pre-commit hooks, .env.example template, and WSL migration script**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-17T09:23:43Z
- **Completed:** 2026-04-17T09:29:15Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- AST-based CI import guard with 4 tests (positive scan, two negative tests, clean-file test) preventing cloud LLM SDK imports in src/ingest/ and src/collectors/
- Pre-commit hooks with gitleaks v8.21.2 (secret scanning) and ruff v0.11.7 (lint + format) all passing
- .env.example documenting 5 required environment variables (DART, Postgres, FRED, ECOS, database URL)
- WSL migration script with safety checks, file count verification, and Obsidian reconnection path
- Full test suite: 19 tests passing (10 frontmatter + 4 import guard + 5 secrets)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create CI import guard test and secret loading test** - `4d1d081` (test)
2. **Task 2: Create .env.example, pre-commit config, and WSL migration script** - `a4b82f8` (feat)

## Files Created/Modified
- `tests/test_import_guard.py` - AST-based scanner for banned anthropic/openai imports with negative tests
- `tests/test_secrets.py` - Validates .env.example existence, required keys, dotenv loading, gitignore patterns
- `.env.example` - Secret template with DART, Postgres, FRED, ECOS placeholders
- `.pre-commit-config.yaml` - gitleaks v8.21.2 + ruff v0.11.7 hooks
- `scripts/migrate-to-wsl.sh` - WSL path migration automation with safety checks

## Decisions Made
- Downgraded gitleaks from v8.22.1 to v8.21.2: v8.22.1 panics with a WASM error (`go-re2` invalid table access) on WSL2 Linux. v8.21.2 works correctly.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Downgraded gitleaks version from v8.22.1 to v8.21.2**
- **Found during:** Task 2 (pre-commit hook installation)
- **Issue:** gitleaks v8.22.1 panics with `wasm error: invalid table access` in `go-re2` on WSL2, preventing any commits
- **Fix:** Changed rev from `v8.22.1` to `v8.21.2` in `.pre-commit-config.yaml`
- **Files modified:** .pre-commit-config.yaml
- **Verification:** `pre-commit run --all-files` passes with v8.21.2
- **Committed in:** a4b82f8 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Version downgrade necessary for WSL2 compatibility. No functional difference in secret scanning capability.

## Issues Encountered
- Ruff auto-formatted test files (SIM102 rule: combined nested if into single condition, line-length wrapping). Resolved by staging ruff's modifications.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 01 (load-bearing-foundation) is now complete with all 3 plans executed
- All 19 tests pass across frontmatter, import guard, and secret management
- Pre-commit hooks active (gitleaks + ruff)
- Ready for Phase 02 (data collection infrastructure)

---
*Phase: 01-load-bearing-foundation*
*Completed: 2026-04-17*
