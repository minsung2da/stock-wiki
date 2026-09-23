---
phase: quick-260923-th4
plan: "01"
subsystem: database-explorer
tags: [sorting, postgresql, accessibility, financial-data]
requires:
  - Existing read-only database explorer
provides:
  - Allowlisted typed database ordering before pagination
  - Keyboard-accessible ascending/descending table headers
affects: [database-read-side]
tech-stack:
  added: []
  patterns: [scalar sort allowlist, NULLS LAST, deterministic key tie ordering]
key-files:
  modified: [src/db/explorer.py, src/db/explorer.html, tests/db/test_explorer.py, docs/database-explorer.md]
key-decisions:
  - Sort original typed database columns, not serialized numeric strings.
  - Keep missing values last for both directions and break ties by ascending record keys.
  - Exclude array and JSON preview columns from sorting.
  - Preserve filters and sorting across pagination, page-size changes and refresh.
completed: 2026-09-23
---

# Quick 260923-th4: Server-side Explorer Sorting

PER/PBR and other allowlisted scalar table headers now sort all matching PostgreSQL
records numerically or by their stored type before pagination, with accessible direction indicators.

## Changes

- Added `sort_by` and strict `asc`/`desc` direction validation. Unknown, hidden, array and JSON
  fields are rejected. Direction-only requests are rejected; a new column defaults to ascending.
- Inventory identifies sortable columns. SQL orders typed values with `NULLS LAST` in both
  directions and stable ascending primary/composite keys for ties. Existing default ordering remains.
- Header buttons display arrows, support keyboard activation and expose `aria-sort`. Sorting starts
  at page one, keeps applied filters and clears stale details. Dataset switches and explicit resets
  clear sorting. Code columns explain their code-based ordering in tooltips.
- Parent updated `docs/database-explorer.md` with header sorting, retained filters and null behavior.
- No dependencies, schema, collection or stored records were changed.

## Verification

- RED: five new numeric-sort/inventory tests failed as expected before implementation because
  sort parameters and sortable metadata did not exist.
- GREEN: `.venv/Scripts/python.exe -m pytest tests/db/test_explorer.py -q` — **27 passed in
  17.12 seconds**, using a disposable migrated PostgreSQL testcontainer.
- Numeric fixtures cover PER and PBR in both directions with `-1`, `0`, `2`, duplicate `2`, `10`,
  `100` and NULL. Tests verify four pages, stable ties, distinct keys, repeatability, composed
  keyword/ticker/date filters and invalid/injection-like sort inputs, including HTTP rejection.
- `.venv/Scripts/python.exe -m ruff check src/db/explorer.py tests/db/test_explorer.py` — passed.
- `.venv/Scripts/python.exe -m mypy -p db.explorer --follow-imports=silent` — passed.
- Existing Alembic `path_separator` deprecation warning remains outside this task's scope.
- Parent live Edge QA passed against 198 stored fundamentals: PER ascending starts at `2.0900`,
  descending at `1360.3900`; PBR ascending starts at `0.1800`, descending at `64.4200`.
- Browser verified correct `aria-sort`, page-two sort preservation, page-one reset after changing
  sort, Samsung filter preservation across sorting, explicit reset and zero JavaScript errors.
- Parent captured desktop/mobile evidence at `control/docs/db-explorer-sort-desktop.png` and
  `control/docs/db-explorer-sort-mobile.png`.

## Deviations from Plan

None. Parent owns documentation, live browser verification and final commits/state bookkeeping.

## Known Stubs

None introduced. Header sorting calls the actual read-only API.

## Self-Check: PASSED

The three implementation/test files and this SUMMARY exist, and focused checks passed. The parent
owns final commit creation; no executor commits or STATE edits were made. Existing JEV and company
name display behavior, unrelated source files and user-owned untracked files were preserved.
