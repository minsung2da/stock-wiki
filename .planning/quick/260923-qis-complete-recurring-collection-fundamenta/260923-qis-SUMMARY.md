---
phase: quick
plan: 260923-qis
subsystem: collection
tags: [fundamentals, news, cli, postgres]
requires: [existing DB-direct collectors]
provides: [complete default batch, KST-day news, dividend storage]
affects: [collection operations]
tech-stack:
  added: []
  patterns: [typed numeric columns, isolated per-corporation collection]
key-files:
  created: [src/db/migrations/versions/0010_fundamentals_dividends.py, docs/collection.md]
  modified: [src/cli/commands.py, src/collectors/news/__init__.py, src/collectors/fundamentals/db_writer.py]
key-decisions:
  - Default batch includes all five active sources; explicit --sources intentionally narrows scope.
  - Scope remains portfolio holdings and watchlist; no scheduler cadence was supplied.
  - KIND runtime is removed while historical event schema and safety gates remain.
metrics:
  completed: 2026-09-23
  tasks: 3
---

# Quick 260923-qis: Complete recurring collection

Default portfolio collection now includes DART and fundamentals, admits only the selected KST news day, and persists dividend yield and DPS in typed columns.

## Changes

1. Mapped pykrx DIV/DPS into nullable NUMERIC dividend_yield/dps, preserving percent/KRW units and zero/NULL semantics. Added migration 0010 and dividend-aware UPSERT comparison; prior ROE preservation remains.
2. RSS UTC tuples now retain their timezone. News filters publication day before article HTTP and before eligible-item limit; repeated runs fetch feeds again and can discover later articles.
3. Default batch runs dart,krx,news,macro,fundamentals with one KST date. DART resolves portfolio corporate identities, deduplicates codes, isolates failures and reports unresolved identities. Reports use actual insertion/update/skip counters. Removed KIND CLI/runtime and exclusive tests; updated surviving import and observability checks. Added operational documentation.

## Validation

### Follow-up: Docker recovered, database validation completed (2026-09-23)

- Restored Docker Desktop by backing up inaccessible runtime socket directories; existing containers/images/volumes retained. Docker Engine 29.5.2 and stock-postgres healthy.
- Actual isolated PostgreSQL integration plus related regressions: **77 passed, 1 Alembic deprecation warning**, 22.83 seconds. Command: `.\.venv\Scripts\python.exe -m pytest tests/collectors/test_fundamentals.py tests/collectors/news tests/test_cli_collect_all.py tests/cli/test_collect_fundamentals.py tests/test_phase01_smoke.py tests/collectors/test_observability_wiring.py -q`.
- Applied additive migration to the configured stock database: **0009 -> 0010 (head)**. This supersedes the initial blocked database validation/application status below.
- Docker Desktop 4.75.0 normal restart reproduced the socket bug. A verified recovery helper exists at `C:/Users/minsu/workspace/control/scripts/repair-docker-desktop.ps1`; healthy reruns leave backend PIDs unchanged. Product-level recurrence remains possible.

### Initial validation (before Docker recovery)

- RED: dividend mapping 5 expected failures; news dates 3 expected failures; batch defaults 3 expected failures.
- Focused non-DB regression: **125 passed, 35 deselected**. Explicit fixture-based selection excluded tests requiring pg_engine; these are not passing integration tests.
- After final formatting and later-news assertion: affected CLI/news/dividend unit subset **25 passed** (overlaps the 125; do not add counts).
- Ruff check on changed CLI, fundamentals/news implementation, migration and new unit tests: passed.
- compileall, CLI help, git diff whitespace check: passed.
- Alembic offline upgrade 0009:head emitted ADD COLUMN dividend_yield NUMERIC(18,4) and dps NUMERIC(20,4).
- Real fundamentals DB suite: **1 passed, 6 setup errors** because Docker named pipe API failed (CreateFile error 231). PostgreSQL round trips and live schema application remain **unverified**. Production DB was not modified.
- No live providers, API charges or trading calls made. Scheduler not installed.

## Commits

- 75481fb: test missing dividend metrics (RED)
- ea1ef06: persist dividend yield and DPS
- 2733b29: test KST news boundaries (RED)
- 77eafe2: selected-day news implementation
- 818c50a: complete default batch tests (RED)
- 65b1e1b: run complete collection and retire KIND

## Deviations from Plan

- [Rule 3] KIND imports also existed in ticker-shape and observability tests; removed only the retired source cases so surviving guards remain meaningful.
- Existing event_type drift test concerns historical frontmatter, not KIND imports; retained unchanged.
- Docker unavailable: performed offline SQL and unit validation, retained real integration tests for a working Docker environment.
- Parent owns final STATE quick-task completion update. ROADMAP remains unchanged.

## Known limitations

Existing provider bounds remain: DART max 100 filings per corporation; news max 100 eligible articles per feed, RSS-visible history only. KRX/fundamentals are single-date snapshots and may be empty on holidays. This is repeated complete source coverage, not an all-market historical archive. Financial addition covers missing pykrx metrics, not every DART statement line item.

## Self-Check: PASSED

Implementation files and migration exist; atomic RED/GREEN commits were created on feat/collection-completeness. All deletions were intentional KIND runtime/test retirement. No implementation stubs introduced. Database validation remains explicitly unresolved.
