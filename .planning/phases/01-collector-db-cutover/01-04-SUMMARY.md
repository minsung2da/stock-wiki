---
phase: "01-collector-db-cutover"
plan: "01-04"
subsystem: "collectors/krx"
tags: [collector, krx, ohlcv, db-direct, upsert, coalesce, phase-1, wave-1]
requires:
  - migration 0006 (filings/news/ohlcv/macro_series/events/collector_runs)
  - 01-02 collector signature strip (engine/since kwargs only)
provides:
  - src/collectors/krx/db_writer.py::upsert_ohlcv (ohlcv UPSERT + T+2 COALESCE)
  - collect_krx body switched from writer.write_krx_doc to db_writer.upsert_ohlcv
  - engine kwarg promoted from optional → required (RuntimeError when None)
  - stats schema delta: succeeded → inserted/updated split
  - structured "collector_run_complete" log carrying source/stats/elapsed_ms/extra
affects:
  - Wave 2A (01-05 kind) — pattern reuse for FK resolution at write boundary
  - Wave 2C (01-07 dart) — db_writer.upsert pattern reused for filings
  - Wave 2D (01-08 observability) — wires structured log into collector_runs table
  - 01-09 — deletes src/collectors/krx/writer.py (still on disk, intentionally)
tech-stack:
  added: []
  patterns:
    - "load → compare → upsert: read existing row in same transaction, return
       'skipped' when COALESCE-adjusted incoming matches, else INSERT ... ON
       CONFLICT DO UPDATE. fetched_at NOT bumped on skip (cheap-no-op)."
    - "COALESCE(EXCLUDED.x, ohlcv.x) on short_volume/short_balance/corp_code
       prevents a stale follow-up fetch from NULL-clobbering T+2-filled data."
    - "Korean→typed dict mapping at __init__ boundary (시가/고가/저가/종가/거래량 →
       open/high/low/close/volume) keeps db_writer KRX-agnostic."
    - "Per-ticker isolation (COLL-08) via try/except in the scope loop —
       single ticker failure adds to stats['failed'] without aborting."
key-files:
  created:
    - src/collectors/krx/db_writer.py
    - tests/collectors/krx/test_db_writer.py
  modified:
    - src/collectors/krx/__init__.py
    - tests/collectors/krx/test_collect_krx.py
decisions:
  - "db_writer takes plain dicts, not pandas DataFrames. The Korean-column
     coercion lives in collect_krx (the boundary where pykrx output lands).
     db_writer is reusable from any caller producing typed dicts."
  - "Outcome enum is exactly Literal['inserted','updated','skipped']. No
     'revision' notion (which macro tracks separately) — price corrections
     just look like 'updated', and the row history is the audit trail."
  - "_LEGACY_VAULT_ROOT constant deleted. Portfolio.load now resolves
     against Path('.') (cwd) which matches Phase 6 P-01 layout
     (notes/private/portfolio.md at repo root). Tests use monkeypatch.chdir."
  - "Structured log key shape: extra={source, stats, elapsed_ms, extra}.
     The nested 'extra' inside the log's 'extra' dict carries
     holiday_tickers + missing_entity lists for Phase 9 dashboards."
metrics:
  tasks_completed: 3
  duration_minutes: ~25
  tests_added: 16
  tests_total_in_krx_module: 25
  commit_hashes:
    - 6d02b17  # Task 1 — db_writer + 9 unit tests (sibling 01-03 swept up, see Deviations)
    - 4c6f8ef  # Task 2 — collect_krx rewire to db_writer
    - b7ee781  # Task 3 — collect_krx tests ported to DB assertions
---

# Phase 1 Plan 01-04: KRX Collector DB-Direct Cutover — Summary

One-liner: `collect_krx` now UPSERTs into the `ohlcv` Postgres table via
`db_writer.upsert_ohlcv`; the Markdown writer call path is severed and the
T+2 short-balance fill-in is handled by a COALESCE-based ON CONFLICT clause
that never NULL-clobbers populated columns.

## What Changed

### `db_writer.upsert_ohlcv` Public Contract

```python
def upsert_ohlcv(
    engine: Engine,
    *,
    ticker: str,
    trade_date: date,
    corp_code: str | None,
    ohlcv_row: dict,                # {open, high, low, close, volume}
    flow_row: dict | None = None,    # {trading_value, foreign_net, inst_net, retail_net}
    short_row: dict | None = None,   # {short_volume, short_balance}
) -> Literal["inserted", "updated", "skipped"]:
    ...
```

- **`inserted`**: no prior row at (ticker, trade_date) — fresh row written.
- **`updated`**: prior row existed, at least one column would change after
  COALESCE adjustment.
- **`skipped`**: prior row matches incoming values — no UPDATE issued
  (and `fetched_at` is preserved, the optimization).
- Ticker is regex-pre-filtered `^[0-9]{6}$` (carry-over from writer.py D-12).
- `corp_code=None` is permitted (column is NULL-able).
- `flow_row=None` / `short_row=None` leaves those columns NULL.

### COALESCE T+2 Short Fill-In Pattern (RESEARCH.md Pitfall 4)

The ON CONFLICT clause uses **column-specific** COALESCE — OHLCV columns
always overwrite (price corrections do happen), but
`short_volume / short_balance / corp_code` use
`COALESCE(EXCLUDED.x, ohlcv.x)`:

```sql
ON CONFLICT (ticker, trade_date) DO UPDATE SET
    open          = EXCLUDED.open,
    high          = EXCLUDED.high,
    low           = EXCLUDED.low,
    close         = EXCLUDED.close,
    volume        = EXCLUDED.volume,
    trading_value = EXCLUDED.trading_value,
    foreign_net   = EXCLUDED.foreign_net,
    inst_net      = EXCLUDED.inst_net,
    retail_net    = EXCLUDED.retail_net,
    short_volume  = COALESCE(EXCLUDED.short_volume,  ohlcv.short_volume),
    short_balance = COALESCE(EXCLUDED.short_balance, ohlcv.short_balance),
    corp_code     = COALESCE(EXCLUDED.corp_code,     ohlcv.corp_code),
    fetched_at    = now()
```

Two test cases cover the bidirectional behavior:

- `test_upsert_ohlcv_short_fillin` — first call with `short_row=None`, second
  with populated short data → outcome `updated`, OHLCV unchanged, short
  columns now populated.
- `test_upsert_ohlcv_short_fillin_does_not_clobber` — first call populates
  shorts, second call with `short_row=None` → outcome `skipped`, prior
  short values preserved.

This load → compare → upsert pattern (with a Python-side `_values_match_existing`
helper) is what lets us return `skipped` distinctly from `updated`. A naive
`ON CONFLICT DO UPDATE` would bump `fetched_at` on every rerun.

### Stats Schema Delta (Phase 1 v2.0)

| Before (v1.0)  | After (v2.0)                          |
| -------------- | ------------------------------------- |
| `succeeded`    | `inserted` + `updated` (split)        |
| `skipped`      | unchanged (covers idempotent + holiday) |
| `failed[]`     | unchanged                             |
| `elapsed_ms`   | unchanged                             |
| heartbeat call | structured `collector_run_complete` log |

### Smoke / Verification Counts

(From the test-container session — testcontainer reused across tests.)

| Verification                                                 | Result          |
| ------------------------------------------------------------ | --------------- |
| `ohlcv` rows UPSERTed across the 8 collect_krx tests          | 7 distinct rows |
| COALESCE T+2 short fill-in path verified                      | YES — 2 tests   |
| `missing_entity` (R-03) isolation preserved                   | YES             |
| Holiday skip (empty pykrx) preserved                          | YES             |
| `writer.*` call sites removed from `collect_krx`              | YES (verified)  |
| `_LEGACY_VAULT_ROOT` macro removed                            | YES             |
| `from shared.heartbeat import …` removed                      | YES             |
| `Veto #6` (no body_md/embedding on ohlcv) verified            | YES (schema-enforced) |
| Markdown writer file (`src/collectors/krx/writer.py`) on disk | YES (01-09 will delete) |
| `vault/raw/krx/` created during test                          | NO              |

## Test Results

| File                                       | Tests | Result  |
| ------------------------------------------ | ----- | ------- |
| `tests/collectors/krx/test_db_writer.py`   | 9     | 9 PASS  |
| `tests/collectors/krx/test_collect_krx.py` | 8     | 8 PASS  |
| `tests/collectors/krx/test_writer.py`      | 8     | 8 PASS  |
| **Total `tests/collectors/krx/`**          | **25**| **25**  |

`test_writer.py` (legacy) continues to pass because `writer.py` is intentionally
preserved on disk until 01-09 deletes it (matches plan's scope boundary).
Tests run against the session testcontainer with `pg_clean` truncating live
tables between tests.

## Deviations from Plan

### `[Rule 1 - Bug] Task 1 commit accidentally swept up by sibling 01-03`

- **Found during:** Task 1 commit step
- **Issue:** The sibling agent running 01-03 (macro) staged its files and
  issued `git commit` before my Task 1 commit completed. Their commit
  (`6d02b17`) included my untracked `src/collectors/krx/db_writer.py` and
  `tests/collectors/krx/test_db_writer.py` because the git index had both
  agents' files staged at the moment of commit.
- **Fix:** None applied — the work is preserved in `6d02b17` with a
  technically-misleading commit message (`feat(01-03): …`) but the files
  and content are correct. Reverting and re-committing would introduce
  destructive operations against the sibling's already-landed work.
- **Files involved:** `src/collectors/krx/db_writer.py` (207 lines),
  `tests/collectors/krx/test_db_writer.py` (308 lines).
- **Commit:** `6d02b17` (shared with 01-03).
- **Mitigation for future work:** Sibling agents should use
  `git commit -- <paths>` with files already in the index. The
  worktree-style isolation that the orchestrator instructions hinted at
  was not actually in effect (the `.claude/worktrees/<name>` directories
  are not real `git worktree`s — `.git` is a dir, not a file).

### `[Rule 3 - Blocking] Plan's grep verification command was too coarse`

- **Found during:** Task 2 verification
- **Issue:** Plan's `inspect.getsource` assertion `assert 'writer.' not in src`
  trips on the legitimate substring `db_writer.` inside the call site
  `db_writer.upsert_ohlcv(...)`. The plan's intent was to forbid the
  `writer.write_krx_doc(...)` call.
- **Fix:** Used a refined assertion (` writer.` with leading space,
  `from collectors.krx import writer`, plus explicit checks for
  `vault_root` / `_LEGACY_VAULT_ROOT` / `heartbeat`). All refined checks
  pass.
- **Files modified:** None — verification only.

### No other deviations.

## Auth Gates

None.

## Hard Veto Compliance

- **#6** (no embedding on `ohlcv`): schema-enforced (migration 0006 has no
  body/embedding columns on `ohlcv`); `db_writer.upsert_ohlcv` only writes
  to typed numeric columns. Verified live via
  `SELECT count(*) FROM information_schema.columns WHERE table_name='ohlcv'
  AND (column_name LIKE 'body%' OR column_name LIKE '%embedding%')` → 0.
- **#9** (no vault revival): `_LEGACY_VAULT_ROOT` constant removed; the
  `Path('.') / "vault" / "raw" / "krx"` directory is never written to by
  the new code path (`test_collect_krx_no_markdown_written` asserts this).

## Threat Flags

No new network endpoints, auth paths, or file access patterns introduced.
All SQL flows through SQLAlchemy bind parameters; ticker is regex-validated
before any DB call (D-12 / T-04-04 carry-over). No threat flags.

## Self-Check: PASSED

- `src/collectors/krx/db_writer.py` — FOUND
- `src/collectors/krx/__init__.py` (modified) — FOUND, contains `db_writer.upsert_ohlcv` call
- `tests/collectors/krx/test_db_writer.py` — FOUND (9 tests)
- `tests/collectors/krx/test_collect_krx.py` — FOUND, no `vault_root=` references
- commit `6d02b17` (Task 1, shared with 01-03) — FOUND in git log, includes both krx + macro files
- commit `4c6f8ef` (Task 2) — FOUND in git log
- commit `b7ee781` (Task 3) — FOUND in git log
- 25/25 tests in `tests/collectors/krx/` PASS
- `grep "writer\.|vault_root|_LEGACY_VAULT_ROOT|heartbeat" src/collectors/krx/__init__.py` → no real matches (only legit `db_writer.` substring)
- `grep "vault/raw" tests/collectors/krx/` → only docstring mention in `test_collect_krx_no_markdown_written`
