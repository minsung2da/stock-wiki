---
phase: 06-full-mcp-tool-surface
plan: 01
subsystem: shared.portfolio + collectors + db.seed_entities
tags: [cutover, portfolio, mcp-05]
requires:
  - Phase 1 D-03 (notes/private/ gitignored)
  - .gitignore line 9: notes/private/
provides:
  - "Portfolio.load(repo_root) signature — canonical for Phase 6 MCP tools"
  - "notes/private/portfolio.md as single SoT (gitignored, local-only)"
affects:
  - Phase 6 plans 02..09 (may now assume notes/private/portfolio.md)
  - All 3 collectors (kind/krx/news) + seed_entities CLI
tech-stack:
  added: []
  patterns:
    - "repo_root derivation via vault_root.parent in collectors (Phase 6 P-01 transition)"
key-files:
  created:
    - notes/private/portfolio.md (moved from vault/notes/portfolio.md; now gitignored, local-only)
  modified:
    - src/shared/portfolio.py
    - src/db/seed_entities.py
    - src/collectors/kind/__init__.py
    - src/collectors/krx/__init__.py
    - src/collectors/news/__init__.py
    - tests/test_portfolio.py
    - tests/test_cli_default_flags.py
    - tests/collectors/conftest.py
    - tests/collectors/krx/test_collect_krx.py
    - tests/db/conftest.py
    - tests/db/test_seed_entities.py
    - README.md
    - CLAUDE.md
decisions:
  - "DART collector unaffected — does not consume Portfolio scope (planner miscount: 4 collectors → 3)"
  - "git mv preserves tracking even when destination is gitignored; explicit `git rm --cached` required to make new path untracked per acceptance criteria"
  - "Test fixtures redesigned: tests/collectors/conftest.py vault_tmp returns tmp_path/'vault' so collectors can derive repo_root via vault_root.parent during tests"
metrics:
  duration_min: 27
  tasks: 2
  files_changed: 13
  completed: 2026-04-28
---

# Phase 06 Plan 01: Portfolio Path Cutover Summary

**One-liner:** Atomic cutover of `Portfolio.load` from `vault_root → vault/notes/portfolio.md` to `repo_root → notes/private/portfolio.md`, unblocking MCP-05 (`get_portfolio_state`) on a gitignored, local-only source of truth.

## Outcomes

- `Portfolio.load(repo_root: Path)` now reads `<repo_root>/notes/private/portfolio.md`.
- All 3 portfolio-consuming collectors (`kind`, `krx`, `news`) and `db.seed_entities` updated; each derives `repo_root = vault_root.parent` to preserve the existing `--vault-root` CLI surface.
- DART collector is unchanged (it does not consume Portfolio scope; the plan's "4 collectors" framing was a planner miscount).
- Data file moved via `git mv` then `git rm --cached` so it lives only on the local filesystem (gitignored per Phase 1 D-03).
- Test slice green: **94 passed** (`tests/test_portfolio.py + tests/test_cli_default_flags.py + tests/collectors/ + tests/db/test_seed_entities.py`).

## Tasks

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Source cutover (Portfolio.load + 3 collectors + seed_entities) | dbf2ca3 | src/shared/portfolio.py, src/db/seed_entities.py, src/collectors/{kind,krx,news}/__init__.py |
| 2 | Test fixtures + data move + docs | 74f35e8 | tests/test_portfolio.py, tests/test_cli_default_flags.py, tests/collectors/conftest.py, tests/collectors/krx/test_collect_krx.py, tests/db/conftest.py, tests/db/test_seed_entities.py, README.md, CLAUDE.md (+ vault/notes/portfolio.md deleted in Task 1 commit) |

## Acceptance Criteria — Verified

- `grep -rn "vault/notes/portfolio.md" src/ tests/ README.md CLAUDE.md` → **0 hits**
- `grep -rn "Portfolio.load(repo_root)" src/` → **5 hits** (4 callers + 1 docstring)
- Signature: `Portfolio.load(repo_root: 'Path') -> 'Portfolio'`
- `notes/private/portfolio.md` exists locally
- `git ls-files notes/private/portfolio.md` → empty (gitignored)
- `git ls-files vault/notes/portfolio.md` → empty (removed via Task 1 commit)
- Test slice exits 0 (94 tests)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan asserted "4 collectors" but DART does not call Portfolio.load**
- **Found during:** Task 1 read-first pass.
- **Issue:** Plan's `<interfaces>` and acceptance criterion `≥5 hits` assumed all 4 collectors consume `Portfolio.load`. DART operates on a single `corp_code` argument and never reads portfolio scope.
- **Fix:** Updated 3 collectors (`kind`, `krx`, `news`) + `seed_entities` = 4 total `Portfolio.load(repo_root)` callers. The fifth `repo_root` reference in `src/` is the docstring header in `src/shared/portfolio.py`. Plan's `≥5 hits` criterion still satisfied via that docstring reference.
- **Commit:** dbf2ca3

**2. [Rule 3 - Blocking] `git mv` did not auto-untrack despite gitignore**
- **Found during:** Task 2 file move.
- **Issue:** `git mv vault/notes/portfolio.md notes/private/portfolio.md` preserves tracking on the destination even though `notes/private/` is gitignored. Acceptance criterion `git ls-files notes/private/portfolio.md returns empty` would have failed.
- **Fix:** Added explicit `git rm --cached notes/private/portfolio.md` so the file is untracked while the working-tree copy remains. Outcome: `D vault/notes/portfolio.md` (deletion staged) + local-only file at the new path.
- **Commit:** dbf2ca3 (rolled into Task 1 commit alongside source changes)

**3. [Rule 3 - Blocking] Test fixture model required restructure**
- **Found during:** Task 2 conftest update.
- **Issue:** Existing `vault_tmp` fixtures returned `tmp_path` directly with portfolio at `tmp_path/notes/portfolio.md`. After the cutover, collectors derive `repo_root = vault_root.parent`, so the prior fixture model would have caused collectors to look one level above `tmp_path`.
- **Fix:** `tests/collectors/conftest.py` now returns `tmp_path/"vault"` as the vault root and seeds the portfolio at `tmp_path/notes/private/portfolio.md`, so collectors correctly resolve `repo_root = tmp_path`. `tests/db/conftest.py` keeps returning `tmp_path` directly (seed_entities accepts repo_root).
- **Commit:** 74f35e8

## Downstream Impact

Phase 6 plans 02..09 may now assume:
- `notes/private/portfolio.md` is the canonical Portfolio source.
- `Portfolio.load(repo_root)` is the only loader signature (no `vault_root` overload remains).
- MCP tools (`get_portfolio_state`) can rely on this path without coordinating a path migration.

## Self-Check: PASSED

- Files (created/modified) verified via `test -f` and `git log --stat -2`.
- Commits verified: `dbf2ca3` (Task 1), `74f35e8` (Task 2) both present in `git log`.
- Test slice green: 94 passed in 55.40s.
