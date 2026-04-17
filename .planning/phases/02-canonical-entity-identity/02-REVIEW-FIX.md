---
phase: 02-canonical-entity-identity
fixed_at: 2026-04-17T00:00:00Z
review_path: .planning/phases/02-canonical-entity-identity/02-REVIEW.md
iteration: 2
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-04-17T00:00:00Z
**Source review:** .planning/phases/02-canonical-entity-identity/02-REVIEW.md
**Iteration:** 2

**Summary:**
- Findings in scope: 9 (WR-01 through WR-05 + IN-01 through IN-04)
- Fixed: 9
- Skipped: 0

## Fixed Issues

### WR-01: `resolve_entity` — 8-digit branch does not verify digits-only

**Files modified:** `src/db/entity.py`
**Commit:** 39e3baf (iteration 1)
**Applied fix:** Removed `_is_digits` helper (which used `str.isdigit()`, accepting non-ASCII digit characters like superscript `²`). Replaced with two module-level compiled regexes `_CORP_CODE_RE = re.compile(r"^[0-9]{8}$")` and `_TICKER_RE = re.compile(r"^[0-9]{6}$")` using `[0-9]` character class (ASCII digits only). Both `if` and `elif` branches in `resolve_entity` now use `.match()` against these regexes. Updated module docstring and inline comments to reflect `[0-9]` patterns.

---

### WR-02: `test_downgrade_then_upgrade_idempotent` corrupts session-scoped engine state

**Files modified:** `tests/test_migration.py`
**Commit:** 7c6bb0e (iteration 1)
**Applied fix:** Wrapped the downgrade/upgrade body in a `try/finally` block. The `finally` clause unconditionally calls `command.upgrade(cfg, "head")`, ensuring the session-scoped engine is always left in a fully-migrated state even if an assertion fails mid-test. This prevents schema state bleed to tests that run after this one regardless of collection ordering. No new dependencies required.

---

### WR-03: `pg_clean` TRUNCATE uses f-string on a constant list — safe today, fragile by design

**Files modified:** `tests/conftest.py`
**Commit:** dc9d0c8 (iteration 1)
**Applied fix:** Replaced the single `TRUNCATE {', '.join(to_truncate)} RESTART IDENTITY CASCADE` f-string with a `for tbl in to_truncate:` loop that issues one `TRUNCATE {tbl} RESTART IDENTITY CASCADE` call per table. Each `tbl` is guaranteed to be a member of the constant `_PHASE2_TABLES` tuple (filtered via `information_schema`). Added a comment explaining the rationale.

---

### WR-04: `content_hash.compute_content_hash` opens file path without validation — path traversal risk

**Files modified:** `src/shared/content_hash.py`
**Commit:** e4eeaeb (iteration 1)
**Applied fix:** Added `from pathlib import Path` import. Before passing the path to `fm.load()`, the function now calls `Path(path).resolve()` to canonicalize the path and eliminate any `../` traversal components. The resolved absolute path is converted back to `str` for `fm.load()`. Updated the docstring to document the path-traversal guard.

---

### WR-05: `write_frontmatter` opens file for writing without atomic write — partial write on crash

**Files modified:** `src/shared/frontmatter.py`
**Commit:** 4e777b7 (iteration 1)
**Applied fix:** Replaced the direct `open(path, "w")` write with an atomic write pattern using `tempfile.mkstemp(dir=dir_, suffix=".tmp")` to create a temp file in the same directory as the target, write content to it via `os.fdopen`, then call `os.replace(tmp_path, path)` which is atomic on POSIX. Added an `except Exception` handler that cleans up the temp file using `contextlib.suppress(OSError)` before re-raising. Updated the docstring to document the atomic-write guarantee and Windows caveat.

---

### IN-01: `resolve_entity` — no test for non-digit 8-character input

**Files modified:** `tests/test_entity_resolve.py`
**Commit:** ed9c000
**Applied fix:** Added two assertions to `test_mismatch_length_returns_none`: `resolve_entity(pg_clean, "KOSPI001") is None` (8 chars, not all ASCII digits) and `resolve_entity(pg_clean, "²²²²²²²²") is None` (8 superscript digits, non-ASCII). These lock down the `[0-9]` regex gate introduced by WR-01 against both alphanumeric and superscript-digit bypass attempts.

---

### IN-02: `alembic.ini` — `sqlalchemy.url` left empty; no comment explaining the pattern

**Files modified:** `src/db/alembic.ini`
**Commit:** 23dd233
**Applied fix:** Added a two-line comment immediately above the blank `sqlalchemy.url =` line stating that the value must not be set here, and directing readers to `src/db/migrations/env.py -> run_migrations_online()` where `DATABASE_URL` is injected at runtime.

---

### IN-03: `migrations/env.py` — missing `run_migrations_offline` function

**Files modified:** `src/db/migrations/env.py`
**Commit:** 95c4dce
**Applied fix:** Added a `run_migrations_offline()` function that configures the Alembic context with `literal_binds=True` for SQL script generation without a live database. Changed the unconditional `run_migrations_online()` call at module load time to a standard `if context.is_offline_mode(): run_migrations_offline() else: run_migrations_online()` guard, matching the standard Alembic template pattern.

---

### IN-04: `fixture_loader` — entity aliases inserted with raw dict `a` without key validation

**Files modified:** `tests/fixtures_loader.py`
**Commit:** 6f80872
**Applied fix:** Replaced the bare `a` dict passed to `conn.execute(sql, a)` in the `entity_aliases` loop with an explicit key-unpacking dict that mirrors the `entities` loop pattern: required keys use `a["key"]` (raises `KeyError` immediately on missing field) and optional `valid_to` uses `a.get("valid_to")`. This surfaces missing required fields with a clear Python `KeyError` rather than a database null-constraint violation.

---

**Verification:** `uv run pytest tests/ -q` — 59 passed, 0 failures, 5 deprecation warnings (pre-existing).

---

_Fixed: 2026-04-17T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
