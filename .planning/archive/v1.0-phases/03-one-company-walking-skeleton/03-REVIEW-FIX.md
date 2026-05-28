---
phase: 03-one-company-walking-skeleton
fixed_at: 2026-04-17T21:20:40Z
review_path: .planning/phases/03-one-company-walking-skeleton/03-REVIEW.md
iteration: 2
findings_in_scope: 8
fixed: 8
skipped: 0
status: all_fixed
---

# Phase 03: Code Review Fix Report

**Fixed at:** 2026-04-17T21:20:40Z
**Source review:** .planning/phases/03-one-company-walking-skeleton/03-REVIEW.md
**Iteration:** 2 (cumulative — iteration 1 fixed WR-01 through WR-04; iteration 2 fixed IN-01 through IN-04)

**Summary:**
- Findings in scope: 8
- Fixed: 8
- Skipped: 0

## Fixed Issues

### WR-01: DateRange strings reach Postgres without ISO-format validation

**Files modified:** `src/stock_mcp/models.py`
**Commit:** e19343e
**Applied fix:** Added `field_validator("start", "end", mode="before")` to `DateRange` that calls `date.fromisoformat()` and raises `ValueError("date must be ISO YYYY-MM-DD") from exc` on invalid input. Also imported `date` from `datetime` and `field_validator` from `pydantic`.

---

### WR-02: Sliding-window chunker drops tail tokens when step divides evenly

**Files modified:** `src/ingest/chunking.py`
**Commit:** d0cb685
**Applied fix:** Added `if not piece.strip(): continue` guard after `tok.decode()` in the sliding-window loop so empty or whitespace-only chunks are skipped rather than inserted into the database.

---

### WR-03: `wrap_untrusted` hard-codes `trust_level="trusted"` for all search excerpts

**Files modified:** `src/stock_mcp/search_core.py`
**Commit:** c731eb5
**Applied fix:** Added `_SOURCE_TRUST` dict mapping `{"dart": "trusted", "news": "semi_trusted", "note": "semi_trusted"}` inside the result assembly block. The `wrap_untrusted` call now passes `trust_level=_SOURCE_TRUST.get(row.source or "", "semi_trusted")` instead of the hard-coded `"trusted"`. A comment notes the Phase 4 follow-up to add `documents.trust_level` column.

---

### WR-04: conftest `pg_clean` uses f-string SQL interpolation for table names

**Files modified:** `tests/conftest.py`
**Commit:** 36f9153
**Applied fix:** Added `import re` and module-level `_SAFE_TABLE_RE = re.compile(r"^[a-z_]+$")`. Added `assert _SAFE_TABLE_RE.match(tbl), f"unsafe table name: {tbl!r}"` before the f-string interpolation in the truncate loop. Replaced the old injection-risk comment with a comment explaining the assertion guard.

---

### IN-01: `client._initialized` global is not reset between test runs

**Files modified:** `src/collectors/dart/client.py`
**Commit:** 90576f4
**Applied fix:** Added a `_reset()` module-level function that sets `_initialized = False`. The function includes a docstring explicitly marking it as test-only and explaining that it allows test fixtures to force re-reading of `DART_API_KEY` after unsetting it, preventing test-ordering dependencies.

---

### IN-02: `chunk_document` receives a `sections` list typed as `list` (no element type)

**Files modified:** `src/ingest/chunking.py`
**Commit:** eba4f74
**Applied fix:** Added `from typing import TYPE_CHECKING` and a `TYPE_CHECKING`-guarded `from ingest.parsers.dart import Section` import. Changed the `sections: list` parameter to `sections: list[Section]` to surface `AttributeError`s as type errors at static analysis time rather than at runtime.

---

### IN-03: `rebuild_from_vault` has no transaction boundary around alembic round-trip

**Files modified:** `src/ingest/rebuild.py`
**Commit:** cc0776c
**Applied fix:** Added a `.. warning::` docstring block describing the interrupted-rebuild risk and recovery steps. Added a schema-health check after `alembic upgrade head` that queries `information_schema.tables` for the `documents` table and raises `RuntimeError` with a clear recovery message if it is absent.

---

### IN-04: `DateRange` does not validate that `start <= end`

**Files modified:** `src/stock_mcp/models.py`
**Commit:** cc2cefb
**Applied fix:** Added `model_validator` import and a `_start_before_end` model validator (mode="after") that raises `ValueError("start must be <= end")` when both fields are non-None and `start > end` (lexicographic comparison, safe for ISO YYYY-MM-DD strings).

---

## Post-Fix Verification

All 168 tests passed (0 failures, 9 deselected as slow/e2e) after all 8 fixes were applied:

```
168 passed, 9 deselected, 14 warnings in 40.37s
```

---

_Fixed: 2026-04-17T21:20:40Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
