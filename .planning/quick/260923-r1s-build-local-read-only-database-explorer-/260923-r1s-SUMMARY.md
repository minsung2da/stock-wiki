---
phase: quick-260923-r1s
plan: "01"
subsystem: database-explorer
tags: [postgresql, read-only, browser, korean, search]
requires:
  - migration 0010 and existing SQLAlchemy engine
provides:
  - Local Korean browser inventory and bounded search for ten stored datasets
  - Full stored record detail with exact NUMERIC serialization
affects: [database-read-side]
tech-stack:
  added: []
  patterns: [stdlib HTTP server, allowlisted bound SQL, read-only transactions]
key-files:
  created: [src/db/explorer.py, src/db/explorer.html, tests/db/test_explorer.py, docs/database-explorer.md]
  modified: []
key-decisions:
  - Bind only 127.0.0.1; no mutation or arbitrary SQL routes.
  - Exclude removed risk events and legacy internal pipeline tables.
  - Default keyword search covers lightweight descriptive fields and company names.
  - Explicit body search uses case-sensitive LIKE with a bounded 30-second timeout.
completed: 2026-09-23
---

# Quick 260923-r1s: Local Database Explorer

Ten-dataset Korean browser with actual row counts, company/ticker/KST date search,
pagination, complete stored record details and PostgreSQL-enforced read-only queries.

## Implementation

- `python -m db.explorer` serves <http://127.0.0.1:8766> using the existing project `.env`.
- Dataset counts and latest stored dates distinguish zero rows from unavailable queries.
- Keyword, ticker and date filters compose; news tickers arrays and company relationships are supported.
- Composite record keys are deterministic; NUMERIC values and large integers preserve precision.
- Full narratives and structured payloads are rendered using DOM text nodes.
- Host/Origin checks, no CORS, fixed descriptors, bound parameters, page caps and statement timeouts
  bound the new HTTP surface. Query errors do not expose database credentials or SQL.

## Commits

- `5e35fc5`: RED tests for read-only explorer boundaries.
- `d7414f5`: Query service, validation and isolated PostgreSQL test coverage.
- `084b520`: Korean responsive browser inventory, filters, table and detail dialog.
- `a54ba3c`: Correct form reset and body-search reset on dataset changes.
- `f72a7b7`: Local startup, query semantics and read-only operations documentation.

## Verification

- RED: `pytest tests/db/test_explorer.py -q` failed because `db.explorer` did not yet exist.
- GREEN: same command passed **12 tests in 13.24 seconds** against disposable migrated PostgreSQL.
  Covered KST midnight boundaries, company-name/array-ticker matching, literal wildcard/injection-like
  text, body-search opt-in and case semantics, pagination, complete stored body, exact decimal metrics,
  every descriptor against schema, PostgreSQL rejection of writes, HTTP access boundaries and sanitized
  database failures.
- `ruff check src/db/explorer.py tests/db/test_explorer.py`: passed.
- `mypy -p db.explorer --follow-imports=silent`: passed.
- Existing Alembic `path_separator` deprecation warning remains outside this task's scope.
- Parent headless Edge measurements after the search fix: ticker `005930` returned 8 filings in
  190 ms; company keyword `삼성전자` returned 8 in 387 ms; explicit body search returned 160 in
  5,542 ms; an absent keyword returned zero in 251 ms. Pagination reached page 2 of 24.
- First live filing detail contained exactly 8,509 stored body characters, matching independent SQL.
- Final parent headless Edge QA passed: all ten inventory counts match list totals and the first
  record of every populated dataset returns HTTP 200 detail. Switching to empty news shows zero
  and explanatory text, and clears body search. Reset returns 578 filings with all filters cleared.
- KST date filter `2026-06-26` returns exactly one record on the correct date. At 390 px viewport
  there is no horizontal page overflow. Final browser session has zero JavaScript errors.
- Parent started the live service at <http://127.0.0.1:8766>; service lifecycle and final STATE/PLAN
  bookkeeping remain with the parent orchestrator.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Performance] Full narrative ILIKE exceeded the production query timeout.**
- Found during parent live browser verification: keyword requests failed at approximately 5.41 seconds.
- Actual filings contained 325,415,895 bytes of stored bodies; the largest body was 4,243,085 bytes.
- Parent measured original case-insensitive keyword count for 삼성전자 at 22.0 seconds (160 matches).
  A case-sensitive body LIKE count took 3.49 seconds for the same 160 matches.
- Fixed by making full body search explicit, using case-sensitive body LIKE, preserving case-insensitive
  title/company matching, and granting body search a bounded 30-second per-statement timeout.
- UI and docs explain the distinction and recommend narrowing body searches by ticker/date.
- No schema migration or extra index was added.

**2. [Rule 1 - Bug] Reset button shadowed the HTML form reset method.**
- Found by parent browser verification when switching dataset: `reset is not a function`.
- Renamed the button identifier to `reset-filters` and explicitly reset the body-search checkbox.
- Browser verification covers dataset switching and resetting the filter form after this fix.

## Known Stubs

None. Input placeholder attributes provide search examples; no empty mock data is rendered as DB data.

## Threat Flags

None outside the plan's threat model. The new local HTTP read surface is the planned surface; no
collection, analysis, trading, auth, schema or mutation behavior was changed.

## Self-Check: PASSED

Created implementation, UI, tests and documentation exist. RED and feature commits are present on
`feat/collection-completeness`. User-owned untracked files were not staged or modified.
