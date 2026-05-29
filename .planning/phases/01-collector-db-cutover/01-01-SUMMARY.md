---
phase: "01-collector-db-cutover"
plan: "01-01"
subsystem: "db/schema"
tags: [migration, alembic, schema, ddl, orm, phase-1, wave-0]
requires:
  - migration 0005 head (Phase 8 documents.note_type column)
provides:
  - migration 0006 (Alembic head) — five v2.0 domain tables + observability
  - tables filings / news / ohlcv / macro_series / events / collector_runs
  - renamed legacy table events_legacy (was events from migration 0001)
  - ORM declarative classes Filing/News/OHLCV/MacroSeries/Event/CollectorRun
  - tests/conftest.py::_LIVE_TABLES tuple (was _PHASE2_TABLES) for FK-safe TRUNCATE
affects:
  - Wave 1A (01-03 macro collector) — UPSERT into macro_series
  - Wave 1B (01-04 krx collector) — UPSERT into ohlcv
  - Wave 2A (01-05 kind collector) — INSERT into filings (pblntf_ty=I) + events
  - Wave 2B (01-06 news collector) — UPSERT into news with tickers TEXT[]
  - Wave 2C (01-07 dart collector) — UPSERT into filings.body_md (whole body)
  - Wave 2D (01-08 observability) — INSERT into collector_runs
tech-stack:
  added: []
  patterns:
    - "halfvec(N) column declared via raw `ALTER TABLE ... ADD COLUMN ... halfvec(N)`
       in migration (SQLAlchemy 2.0 has no built-in type); ORM declares custom
       `_HalfVec` UserDefinedType so column is mapped in introspection without
       forcing a custom type into the migration namespace"
    - "Partial indexes via `postgresql_where=sa.text(...)`"
    - "GIN index on TEXT[] column via `postgresql_using='gin'`"
    - "Composite NUMERIC PK with empty-string default for FRED rows
       (macro_series.item_code)"
    - "Multi-column UNIQUE with NULL-tolerant source_id (events dedup)"
key-files:
  created:
    - src/db/migrations/versions/0006_phase01_domain_tables.py
    - src/db/entity_models.py
    - tests/db/test_migration_0006.py
  modified:
    - tests/conftest.py (rename _PHASE2_TABLES → _LIVE_TABLES + append 6 new tables + events_legacy)
decisions:
  - "halfvec(1024) physical column declared via raw SQL in the migration (option (b) in RESEARCH.md Q1) — matches the pattern in migration 0001 that uses `op.execute(\"ALTER TABLE chunks ADD COLUMN embedding vector(1024)\")` for the same reason."
  - "Legacy ix_events_corp_code_time index also renamed to ix_events_legacy_corp_code_time so the new events table can use ix_events_* names without collision; downgrade reverses both."
  - "_LIVE_TABLES order is FK-child-first (collector_runs → events → news → filings → ohlcv → macro_series → events_legacy → dormant Phase 2) so TRUNCATE CASCADE has no FK cycle risk."
  - "Skipped adding a CHECK constraint enforcing tickers array element pattern (`^[0-9]{6}$`) because Postgres lacks per-element ARRAY CHECK; the regex pre-filter at the news collector layer (existing matcher.py) is the right place."
metrics:
  tasks_completed: 3
  duration_minutes: ~35
  tests_added: 9
  tests_total_in_db_module: 17
  commit_hashes:
    - 1a8b4ba  # Task 1 — migration 0006
    - 8424ed7  # Task 2 — ORM models
    - 4ef8ca1  # Task 3 — schema regression test + conftest rename
---

# Phase 1 Plan 01-01: Schema Migration 0006 + ORM Models + Regression Test — Summary

One-liner: Alembic migration 0006 establishes the v2.0 schema contract — five
domain tables (filings/news/ohlcv/macro_series/events) plus a collector_runs
observability table — and renames the dormant Phase 2 events table to
events_legacy so the new KIND-classifier events table can claim the name;
SQLAlchemy ORM models mirror the migration so downstream collector plans can
use type-safe inserts.

## What Changed

### Tables Created (6)

| Table             | Columns | PK                                                        | Indexes                                                                      |
| ----------------- | ------- | --------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `filings`         | 14      | `rcept_no` CHAR(14)                                        | ix_filings_corp_filed (corp_code, filed_at DESC), ix_filings_pblntf_ty (pblntf_ty), ix_filings_event_type (partial WHERE event_type IS NOT NULL) |
| `news`            | 16      | `id` BIGSERIAL                                             | UNIQUE url_hash, ix_news_corp_pub (corp_code, published_at DESC), ix_news_outlet (outlet, published_at DESC), ix_news_tickers GIN(tickers) |
| `ohlcv`           | 15      | (`ticker`, `trade_date`)                                   | ix_ohlcv_date (trade_date DESC), ix_ohlcv_corp partial (corp_code, trade_date DESC) WHERE corp_code IS NOT NULL |
| `macro_series`    | 9       | (`source`, `series_id`, `item_code`, `obs_date`)            | ix_macro_obs (obs_date DESC) + CHECK source IN ('ecos','fred')               |
| `events`          | 12      | `id` BIGSERIAL; UNIQUE (event_type, ticker, event_date, source, source_id) | ix_events_ticker_date, ix_events_type_date + 2 CHECKs (event_type 5-value enum, source IN ('dart','kind')) + FK filing_rcept_no → filings.rcept_no ON DELETE SET NULL |
| `collector_runs`  | 6       | `id` BIGSERIAL                                             | ix_collector_runs_source_time + CHECK source IN ('dart','krx','news','macro','kind') |

### Indexes Created (12)

ix_filings_corp_filed, ix_filings_pblntf_ty, ix_filings_event_type (partial),
ix_news_corp_pub, ix_news_outlet, ix_news_tickers (GIN), ix_ohlcv_date,
ix_ohlcv_corp (partial), ix_macro_obs, ix_events_ticker_date,
ix_events_type_date, ix_collector_runs_source_time.

Plus implicit BTREE on the UNIQUE constraints (url_hash on news, the 5-col
dedup key on events).

### Legacy events Rename Verification (A1)

The migration runs `ALTER TABLE events RENAME TO events_legacy` as its very
first DDL step. I verified Assumption A1 (legacy events table is empty
post-shutdown) live:

```
Run on testcontainer at HEAD=0005:
  SELECT count(*) FROM events  →  0

After 0006 upgrade:
  SELECT count(*) FROM events_legacy  →  0
  SELECT count(*) FROM events         →  0  (new KIND-classifier table)

Round-trip downgrade 0006 → 0005:
  SELECT count(*) FROM events  →  0  (restored, original shape preserved)

Re-upgrade 0005 → head:
  count(tables IN domain set)  →  6  (all six new tables re-created cleanly)
```

A1 holds. Even if it did not, the rename would still be safe because the
new schema's events table is a completely different column shape; no FK
points into the new events row by id, and the legacy table's payload column
is preserved on events_legacy.

### Hard Veto Enforcement (Baked into Schema)

- **Veto #6 (no numeric embedding)**: tests/db/test_migration_0006.py
  asserts `body_md` and `body_embedding` columns are ABSENT from `ohlcv`,
  `macro_series`, and `events`. Only `filings` and `news` carry
  halfvec(1024) body_embedding.

- **Veto #8 (no DART pre-chunking)**: `filings.body_md` is TEXT NOT NULL,
  asserted in test_filings_table_shape. No chunking column on filings; the
  dormant `chunks` table (RESEARCH Q3 Option B) is left untouched for Phase
  3 to re-design narrative search.

### Dormant Phase 2 Tables (Q3 Option B)

`documents`, `chunks`, `edges`, `ingest_runs` — all kept intact. Verified
in `test_dormant_tables_untouched` (column-set spot-check per table).

## Test Results

| File                                   | Tests | Result |
| -------------------------------------- | ----- | ------ |
| `tests/db/test_migration_0006.py`      | 9     | 9 PASS |
| `tests/db/` overall (includes others)  | 17    | 17 PASS |

Schema test breakdown:

- test_filings_table_shape (PK/FK/body types/3 indexes + partial WHERE)
- test_news_table_shape (UNIQUE url_hash/TEXT[]/GIN/license_flag default/halfvec)
- test_ohlcv_table_shape (composite PK/numeric(18,4)/bigint/**Veto #6 enforcement**)
- test_macro_series_table_shape (4-col PK/item_code default ''/source CHECK/**Veto #6**)
- test_events_table_shape (UNIQUE dedup key/FK SET NULL/event_type CHECK 5-values/**Veto #6**)
- test_collector_runs_shape (JSONB stats+extra/index)
- test_events_legacy_exists (legacy `payload` column on events_legacy, NOT on new events)
- test_dormant_tables_untouched (documents/chunks/edges/ingest_runs preserved)
- test_orm_round_trip (every ORM model's columns ≡ live DB columns; Base.metadata = {6 tables})

Runtime: 6-12s per `tests/db/` run on the session testcontainer.

## Deviations from Plan

**None of substance.** All three tasks executed as specified.

Minor mechanical choices noted in `decisions:` frontmatter:

1. **Indexed legacy index rename**: The plan instructed "rename any indexes
   on the old events table to keep `events_*` index names available".
   Migration 0001 only created `ix_events_corp_code_time`; the migration
   renames it to `ix_events_legacy_corp_code_time` (and downgrade reverses
   the rename). This was specifically called out in the plan body.

2. **halfvec declaration choice**: Followed the plan's recommendation (b)
   — raw `op.execute("ALTER TABLE ... ADD COLUMN ... halfvec(1024)")` in
   the migration, mirrored by a custom `_HalfVec(UserDefinedType)` in the
   ORM for introspection only. Documented in both module docstrings.

3. **PK naming**: Composite PKs were given explicit names
   (`pk_ohlcv`, `pk_macro_series`) so downgrade can be clean if ever
   needed. Plan did not specify names; this is a hygiene choice.

## Pitfalls Encountered + Resolution

| # | Pitfall                                                       | Resolution                                                                                                  |
| - | ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| 1 | `uv` CLI not on PATH (only `python -m uv` works on this box) | Used `python -m uv run` for all alembic/pytest invocations during development; commits restored uv.lock via `git checkout -- uv.lock` after each sync because `uv sync` rewrote it (likely due to platform marker churn from the broken pre-existing `.venv` symlinks). |
| 2 | Console `cp949` codec rejecting em-dash in print output      | Used ASCII-only diagnostic prints in the A1 verification script.                                            |
| 3 | SQLAlchemy `SAWarning: Did not recognize type 'halfvec'`     | Expected — SQLAlchemy 2.0 has no built-in halfvec adapter. The column still works (we never SELECT it in Phase 1; Phase 3 will install a proper adapter). Warning is informational and was confirmed in the test output. |
| 4 | Sibling agent (01-02) had also modified some files (collectors/*/__init__.py + tests/test_cli*) | Stayed within my plan's file set: migration + ORM + tests/db/* + tests/conftest.py rename. No collision; `git status` showed both work streams separately. |

## Threat Surface

No new network endpoints, auth paths, or external file access patterns
introduced. All schema additions are typed columns guarded by Postgres CHECK
constraints (source enums on events / macro_series / collector_runs;
event_type enum on events) plus regex-validated bind params from the
existing `entity.py` D-12 pre-filter (carry-over from Phase 2). No threat
flags.

## Self-Check: PASSED

- `src/db/migrations/versions/0006_phase01_domain_tables.py` — FOUND
- `src/db/entity_models.py` — FOUND
- `tests/db/test_migration_0006.py` — FOUND
- `tests/conftest.py` modified — FOUND (`_LIVE_TABLES` present, `_PHASE2_TABLES` absent in code)
- commit `1a8b4ba` (Task 1) — FOUND in git log
- commit `8424ed7` (Task 2) — FOUND in git log
- commit `4ef8ca1` (Task 3) — FOUND in git log
- 17/17 tests in `tests/db/` PASS
- Migration head is 0006 (verified via `alembic history`)
- Round-trip downgrade 0006 → 0005 → head is clean
