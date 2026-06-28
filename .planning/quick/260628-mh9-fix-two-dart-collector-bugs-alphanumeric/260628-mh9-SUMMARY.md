---
phase: quick-260628-mh9
plan: 01
subsystem: collectors
tags: [dart, ticker-validation, retry, fetcher, bugfix]
requires: []
provides:
  - "Widened ticker guard ^[0-9A-Z]{6}$ across six collector/entity write paths"
  - "Retryable DartThrottleError for OpenDART status 020/800"
affects:
  - src/collectors/dart/db_writer.py
  - src/db/entity.py
  - src/collectors/krx/db_writer.py
  - src/collectors/news/db_writer.py
  - src/collectors/kind/db_writer.py
  - src/collectors/fundamentals/db_writer.py
  - src/collectors/dart/fetcher.py
tech-stack:
  added: []
  patterns:
    - "pre-bind regex allowlist widened (uppercase alphanumeric, no SQL metachars)"
    - "retryable exception subclass routed through existing tenacity retry"
key-files:
  created:
    - tests/test_ticker_shape.py
  modified:
    - src/collectors/dart/db_writer.py
    - src/db/entity.py
    - src/collectors/krx/db_writer.py
    - src/collectors/news/db_writer.py
    - src/collectors/kind/db_writer.py
    - src/collectors/fundamentals/db_writer.py
    - src/collectors/dart/fetcher.py
    - tests/collectors/dart/test_db_writer.py
    - tests/test_entity_upsert.py
    - tests/collectors/dart/test_fetcher.py
    - tests/test_dart_fetcher_retry.py
decisions:
  - "Ticker class widened to uppercase-only (^[0-9A-Z]{6}$): KRX issues uppercase short codes; lowercase stays rejected"
  - "020/800 routed to a DartThrottleError subclass so a base DartDocumentError (014) stays non-retryable via isinstance gating"
metrics:
  duration: ~12 min (excl. 8m22s full regression)
  completed: 2026-06-28
---

# Phase quick-260628-mh9 Plan 01: Fix two DART collector bugs (alphanumeric ticker + throttle retry) Summary

Widened the digit-only ticker shape guard to uppercase ASCII alphanumeric across the six collector/entity write paths (unblocking KRX new-style codes like `0001A0`), and made `fetch_body` retry OpenDART's 020/800 throttle envelopes via a retryable `DartThrottleError` subclass.

## What changed

### Task 1 — ticker guard `^[0-9]{6}$` → `^[0-9A-Z]{6}$` (commit `d4d249e`)
- `_TICKER_RE` widened in `dart/db_writer.py`, `db/entity.py`, `krx/db_writer.py`, `news/db_writer.py`, `kind/db_writer.py`, `fundamentals/db_writer.py`; docstrings + `ValueError` messages updated to "6 ASCII alphanumeric (uppercase)".
- `corp_code` (`^[0-9]{8}$`) and `rcept_no` (`^[0-9]{14}$`) guards left untouched. No SQL string changed — added `A-Z` carries no metacharacters, so the pre-bind allowlist (Veto #7 / D-12) and SQLAlchemy bind-param flow are intact.
- New `tests/test_ticker_shape.py`: DB-free accept/reject matrix parametrized over all six imported guards + a "same widened literal" assertion.
- DB-backed proofs: `test_upsert_filing_alphanumeric_ticker_accepted` (DART filing INSERT stores `0001A0` exactly in CHAR(6)) and `test_alphanumeric_ticker_roundtrip` (entity upsert→resolve round-trips `0001A0`).

### Task 2 — retry OpenDART throttle status 020/800 (commit `2bbe71b`)
- Added `class DartThrottleError(DartDocumentError)`; moved both exception classes above `_RETRYABLE_EXC` (it's evaluated at import) and added `DartThrottleError` to the tuple.
- `_TRANSIENT_STATUSES = frozenset({"020", "800"})`; `_handle_error_envelope` now raises `DartThrottleError` for those, `DartDocumentError` otherwise (014 + unparseable non-ZIP). Status 013 still returns `""`. Tenacity config unchanged (`stop_after_attempt(5)`, `wait_exponential(1,1,30)`, `reraise=True`). No API key in any message.
- Retargeted the existing permanent-error fetcher test from 020 to 014; added 020-retries-then-succeeds, 020-exhausts-then-raises-throttle (5 attempts), and 014-not-retried (1 attempt) cases to the wait-neutralized retry module.

## Test results (exact counts)
- Task 1 verify (`test_ticker_shape` + `test_db_writer` + `test_entity_upsert` + `test_entity_resolve`): **113 passed**.
- Task 2 verify (`test_fetcher` + `test_dart_fetcher_retry`): **19 passed**.
- Full regression (`tests/collectors/dart tests/collectors tests/db`): **190 passed, 0 failed, 18 warnings** in 502s. Warnings are all pre-existing `SAWarning: Did not recognize type 'halfvec'` (cosmetic; unrelated to this change).

RED was confirmed before each implementation: ticker-shape 19 alphanumeric-accept cases failed pre-change; fetcher 4 throttle cases failed pre-change (`DartThrottleError` did not exist).

## Commits
- `d4d249e` — fix(collector-ticker): widen ticker guard to ^[0-9A-Z]{6}$ across six write paths
- `2bbe71b` — fix(dart-fetcher): retry OpenDART throttle (status 020/800) via DartThrottleError

## Deviations from Plan
None — both tasks executed exactly as written.

## Hard Veto compliance
- Veto #7 / D-12: ticker guard stays a pre-bind allowlist; added `A-Z` has no SQL metacharacters; all writes keep SQLAlchemy bind params (verified by `0;DROP`/`0001A!` rejection in the shape matrix).
- Veto #8: no chunking/body handling touched (whole-body `filings.body_md` path unchanged; DART body extraction untouched).
- COLL-07: no `anthropic`/`openai` imports added to collectors.

## Out of scope (surfaced, not fixed) — per plan `<scope_note>`
The read/analysis/shared layer still carries the digit-only `^[0-9]{6}$` ticker pattern and will reject a stored new-style ticker: `src/mcp_v2/models.py`/`tools/market.py`/`errors.py`, `src/cards/models.py`, `src/shared/portfolio.py`, `src/shared/frontmatter.py`. Also `src/collectors/kind/__init__.py:190` (`ticker.isdigit()`) is outside the six enumerated files. A new-style ticker written by the collectors here is not yet queryable via MCP tools or representable in a decision_card/portfolio entry — recommend a follow-up quick task to widen the read/analysis/shared layer for end-to-end consistency.

## Self-Check: PASSED
- `tests/test_ticker_shape.py` — FOUND
- commit `d4d249e` — FOUND
- commit `2bbe71b` — FOUND
- No file deletions across either commit
