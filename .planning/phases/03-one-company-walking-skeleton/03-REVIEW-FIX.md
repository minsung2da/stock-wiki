---
phase: 03-one-company-walking-skeleton
fixed_at: 2026-04-17T19:26:09Z
review_path: .planning/phases/03-one-company-walking-skeleton/03-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 03: Code Review Fix Report

**Fixed at:** 2026-04-17T19:26:09Z
**Source review:** .planning/phases/03-one-company-walking-skeleton/03-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 4
- Fixed: 4
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
**Applied fix:** Added `import re` and module-level `_SAFE_TABLE_RE = re.compile(r"^[a-z_]+$")`. Added `assert _SAFE_TABLE_RE.match(tbl), f"unsafe table name: {tbl!r}"` before the f-string interpolation in the truncate loop. Removed the old comment that described the injection risk; replaced with a comment explaining the assertion guard.

---

## Post-Fix Verification

All 168 tests passed (0 failures, 9 deselected as slow/e2e) after all 4 fixes were applied:

```
168 passed, 9 deselected, 14 warnings in 39.91s
```

---

_Fixed: 2026-04-17T19:26:09Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
