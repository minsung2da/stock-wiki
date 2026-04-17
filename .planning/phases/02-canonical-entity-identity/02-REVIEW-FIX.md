---
phase: 02-canonical-entity-identity
fixed_at: 2026-04-17T00:00:00Z
review_path: .planning/phases/02-canonical-entity-identity/02-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-04-17T00:00:00Z
**Source review:** .planning/phases/02-canonical-entity-identity/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (WR-01 through WR-05; Critical + Warning only)
- Fixed: 5
- Skipped: 0

## Fixed Issues

### WR-01: `resolve_entity` — 8-digit branch does not verify digits-only

**Files modified:** `src/db/entity.py`
**Commit:** 39e3baf
**Applied fix:** Removed `_is_digits` helper (which used `str.isdigit()`, accepting non-ASCII digit characters like superscript `²`). Replaced with two module-level compiled regexes `_CORP_CODE_RE = re.compile(r"^[0-9]{8}$")` and `_TICKER_RE = re.compile(r"^[0-9]{6}$")` using `[0-9]` character class (ASCII digits only). Both `if` and `elif` branches in `resolve_entity` now use `.match()` against these regexes. Updated module docstring and inline comments to reflect `[0-9]` patterns.

---

### WR-02: `test_downgrade_then_upgrade_idempotent` corrupts session-scoped engine state

**Files modified:** `tests/test_migration.py`
**Commit:** 7c6bb0e
**Applied fix:** Wrapped the downgrade/upgrade body in a `try/finally` block. The `finally` clause unconditionally calls `command.upgrade(cfg, "head")`, ensuring the session-scoped engine is always left in a fully-migrated state even if an assertion fails mid-test. This prevents schema state bleed to tests that run after this one regardless of collection ordering. No new dependencies required.

---

### WR-03: `pg_clean` TRUNCATE uses f-string on a constant list — safe today, fragile by design

**Files modified:** `tests/conftest.py`
**Commit:** dc9d0c8
**Applied fix:** Replaced the single `TRUNCATE {', '.join(to_truncate)} RESTART IDENTITY CASCADE` f-string (which would become an injection path if `_PHASE2_TABLES` ever gained dynamic entries) with a `for tbl in to_truncate:` loop that issues one `TRUNCATE {tbl} RESTART IDENTITY CASCADE` call per table. Each `tbl` is guaranteed to be a member of the constant `_PHASE2_TABLES` tuple (filtered via `information_schema`). Added a comment explaining the rationale.

---

### WR-04: `content_hash.compute_content_hash` opens file path without validation — path traversal risk

**Files modified:** `src/shared/content_hash.py`
**Commit:** e4eeaeb
**Applied fix:** Added `from pathlib import Path` import. Before passing the path to `fm.load()`, the function now calls `Path(path).resolve()` to canonicalize the path and eliminate any `../` traversal components. The resolved absolute path is converted back to `str` for `fm.load()`. Updated the docstring to document the path-traversal guard.

---

### WR-05: `write_frontmatter` opens file for writing without atomic write — partial write on crash

**Files modified:** `src/shared/frontmatter.py`
**Commit:** 4e777b7
**Applied fix:** Replaced the direct `open(path, "w")` write with an atomic write pattern using `tempfile.mkstemp(dir=dir_, suffix=".tmp")` to create a temp file in the same directory as the target, write content to it via `os.fdopen`, then call `os.replace(tmp_path, path)` which is atomic on POSIX. Added an `except Exception` handler that cleans up the temp file using `contextlib.suppress(OSError)` (as required by project ruff rules / SIM105) before re-raising. Added `import contextlib`, `import os`, `import tempfile`, and `from pathlib import Path` inside the function body. Updated the docstring to document the atomic-write guarantee and Windows caveat.

---

_Fixed: 2026-04-17T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
