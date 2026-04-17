---
phase: 01-load-bearing-foundation
fixed_at: 2026-04-17T10:02:44Z
review_path: .planning/phases/01-load-bearing-foundation/01-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 01: Code Review Fix Report

**Fixed at:** 2026-04-17T10:02:44Z
**Source review:** .planning/phases/01-load-bearing-foundation/01-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (1 Critical, 4 Warning)
- Fixed: 5
- Skipped: 0

## Fixed Issues

### CR-01: Real password committed in `.env.example`

**Files modified:** `.env.example`, `docker-compose.yml`
**Commit:** f97ed6c
**Applied fix:** Replaced `stockwiki_dev` with `your_postgres_password_here` in `.env.example` lines 8-9, and replaced the `:-stockwiki_dev` fallback default in `docker-compose.yml` line 8 with `:-change_me_in_dotenv`.

---

### WR-01: `read_frontmatter` has no error handling for missing or malformed files

**Files modified:** `src/shared/frontmatter.py`
**Commit:** 7a1d063
**Applied fix:** Added `ValidationError` to the pydantic import. Wrapped `fm.load(path)` in a `try/except Exception` that re-raises as `ValueError` with a descriptive message. Wrapped `FrontMatter.model_validate(...)` in a `try/except ValidationError` that re-raises as `ValueError`. Added `Raises:` section to the docstring.

---

### WR-02: `write_frontmatter` opens file without error handling; silent overwrite risk

**Files modified:** `src/shared/frontmatter.py`
**Commit:** 7a1d063
**Applied fix:** Moved `fm.dumps(post)` before the `open()` call so the content string is fully computed before the file is opened. Added a comment and docstring note explaining the atomicity guarantee. A serialization error in `fm.dumps` now raises before the file is truncated.

---

### WR-03: Hardcoded personal path in shared migration script

**Files modified:** `scripts/migrate-to-wsl.sh`
**Commit:** a15f269
**Applied fix:** Replaced `SRC="/mnt/c/Users/minsu/workspace/stock"` with `SRC="${STOCK_SRC:?Set STOCK_SRC to your Windows vault path, e.g. /mnt/c/Users/yourname/workspace/stock}"`. Also updated the header comment on line 12 to use `"$STOCK_SRC"` instead of the hardcoded path.

---

### WR-04: `docker-compose.yml` has no restart policy

**Files modified:** `docker-compose.yml`
**Commit:** 650e7d1
**Applied fix:** Added `restart: unless-stopped` to the `postgres` service definition so the container automatically recovers after host reboots or Docker daemon restarts.

---

_Fixed: 2026-04-17T10:02:44Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
