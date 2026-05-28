---
phase: 01-load-bearing-foundation
fixed_at: 2026-04-17T10:06:19Z
review_path: .planning/phases/01-load-bearing-foundation/01-REVIEW.md
iteration: 2
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 01: Code Review Fix Report

**Fixed at:** 2026-04-17T10:06:19Z
**Source review:** .planning/phases/01-load-bearing-foundation/01-REVIEW.md
**Iteration:** 2 (cumulative — includes iteration 1 fixes)

**Summary:**
- Findings in scope: 9 (1 Critical, 4 Warning, 4 Info)
- Fixed: 9
- Skipped: 0

---

## Fixed Issues

### CR-01: Real password committed in `.env.example`

**Files modified:** `.env.example`, `docker-compose.yml`
**Commit:** f97ed6c (iteration 1)
**Applied fix:** Replaced `stockwiki_dev` with `your_postgres_password_here` in `.env.example` lines 8-9, and replaced the `:-stockwiki_dev` fallback default in `docker-compose.yml` line 8 with `:-change_me_in_dotenv`.

---

### WR-01: `read_frontmatter` has no error handling for missing or malformed files

**Files modified:** `src/shared/frontmatter.py`
**Commit:** 7a1d063 (iteration 1)
**Applied fix:** Added `ValidationError` to the pydantic import. Wrapped `fm.load(path)` in a `try/except Exception` that re-raises as `ValueError` with a descriptive message. Wrapped `FrontMatter.model_validate(...)` in a `try/except ValidationError` that re-raises as `ValueError`. Added `Raises:` section to the docstring.

---

### WR-02: `write_frontmatter` opens file without error handling; silent overwrite risk

**Files modified:** `src/shared/frontmatter.py`
**Commit:** 7a1d063 (iteration 1)
**Applied fix:** Moved `fm.dumps(post)` before the `open()` call so the content string is fully computed before the file is opened. A serialization error in `fm.dumps` now raises before the file is truncated.

---

### WR-03: Hardcoded personal path in shared migration script

**Files modified:** `scripts/migrate-to-wsl.sh`
**Commit:** a15f269 (iteration 1)
**Applied fix:** Replaced `SRC="/mnt/c/Users/minsu/workspace/stock"` with `SRC="${STOCK_SRC:?Set STOCK_SRC to your Windows vault path, e.g. /mnt/c/Users/yourname/workspace/stock}"`. Also updated the header comment to reference `$STOCK_SRC`.

---

### WR-04: `docker-compose.yml` has no restart policy

**Files modified:** `docker-compose.yml`
**Commit:** 650e7d1 (iteration 1)
**Applied fix:** Added `restart: unless-stopped` to the `postgres` service definition.

---

### IN-01: `pyproject.toml` pins `ruff>=0.15` but pre-commit config pins `ruff v0.11.7`

**Files modified:** `pyproject.toml`
**Commit:** fdfd282
**Applied fix:** Changed `ruff>=0.15` to `ruff>=0.11.7` in the dev dependency group to align with the pre-commit hook rev `v0.11.7`. The `>=0.15` pin referenced a non-existent future version; `0.11.7` is the current stable release used by pre-commit.

---

### IN-02: `test_secrets.py` does not test that `.env` itself is absent from the repo

**Files modified:** `tests/test_secrets.py`
**Commit:** 6e8fae9
**Applied fix:** Added `test_env_file_not_committed` method to `TestSecretManagement`. It asserts `PROJECT_ROOT / ".env"` does not exist, catching accidental commits of the live secrets file.

---

### IN-03: `DerivedBlock.sentiment` and `DerivedBlock.numeric_facts` use untyped `dict` and `list[dict]`

**Files modified:** `src/shared/frontmatter.py`
**Commit:** b798211
**Applied fix:** Added `SentimentBlock` (fields: `bullish_score: float | None`, `label: str | None`) and `NumericFact` (fields: `key: str`, `value: float`, `unit: str | None`) Pydantic models. Updated `DerivedBlock.sentiment` to `SentimentBlock | None` and `DerivedBlock.numeric_facts` to `list[NumericFact]`. Existing tests confirm compatibility — they only check for empty defaults which remain unchanged.

---

### IN-04: `migrate-to-wsl.sh` `tr -d '\r\0'` NUL character not portable across WSL distributions

**Files modified:** `scripts/migrate-to-wsl.sh`
**Commit:** 28d9cb3
**Applied fix:** Split `tr -d '\r\0'` into two separate calls: `tr -d '\r' | tr -d '\000'`. The `\0` escape in a `tr` delete class is not recognized on all platforms and silently produces an empty result on some WSL distributions; `\000` (octal) is POSIX-portable and handles the NUL strip correctly.

---

_Fixed: 2026-04-17T10:06:19Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
