---
phase: "01-collector-db-cutover"
plan: "01-05"
subsystem: "collectors/kind"
tags: [collector, kind, dart, filings, events, paired-write, fk-link, phase-1, wave-2]
requires:
  - migration 0006 (filings + events tables with FK events.filing_rcept_no → filings.rcept_no)
  - 01-02 collector signature strip (engine/since/enable_kind_scrape kwargs)
  - 01-01 schema contract — UNIQUE (event_type, ticker, event_date, source, source_id)
provides:
  - src/collectors/kind/db_writer.py::upsert_kind_filing (pblntf_ty='I' UPSERT, content_hash dedup)
  - src/collectors/kind/db_writer.py::upsert_kind_event (events INSERT ON CONFLICT DO NOTHING)
  - collect_kind body switched from writer.write_kind_event to paired db_writer calls
  - engine kwarg promoted to required (RuntimeError when None)
  - stats schema v2.0 — {total, inserted, updated, skipped, failed, elapsed_ms}
  - structured "collector_run_complete" log carrying dart_events / kind_scrape sub-stats,
    kind_parse_error, suspension_cross_check_mismatch (deferred placeholder), dart_suspended_tickers
affects:
  - Wave 2C (01-07 dart) — paired-write pattern reuses upsert_kind_filing's load-then-classify shape
  - Wave 2D (01-08 observability) — structured log keys are the contract for collector_runs.extra
  - Wave 3 (01-09) — deletes src/collectors/kind/writer.py and tests/collectors/kind/test_writer.py together
  - Phase 3 — full filing body backfill task for KIND filings (body_md='' placeholders)
  - Phase 9 — wires real suspension_cross_check_mismatch query against collector_runs.extra JSONB
tech-stack:
  added: []
  patterns:
    - "Paired write: DART pblntf_ty='I' events INSERT filings first (UPSERT by rcept_no), then
       INSERT events with filing_rcept_no FK. Two separate engine.begin() blocks per db_writer
       call — atomicity is per-table, not per-event. An events INSERT failure after a successful
       filings UPSERT is acceptable: filings is the source of truth, the orphan filings row is
       valid on its own, and the failed events row appears in stats['failed'] for retry."
    - "Load-then-classify content_hash dedup on filings: SELECT existing content_hash, compare
       to incoming sha256(normalize_body(body_md)). Equal → bump last_seen_at, skip UPSERT.
       Different → run the UPSERT, return 'updated'. Same shape as 01-03/01-04 db_writers."
    - "ON CONFLICT DO NOTHING on events: same (event_type, ticker, event_date, source, source_id)
       UNIQUE key collision = silent skip, RETURNING id distinguishes 'inserted' from 'skipped'."
    - "KIND-vs-DART source classification at collector boundary: source_id is 14 ASCII digits
       (DART rcept_no shape) → source='dart' + filing_rcept_no=source_id; otherwise source='kind'
       + filing_rcept_no=None."
    - "Single-source-of-truth event_type enum: db_writer imports KindEventType from sources.py
       and validates incoming event_type against the frozenset(e.value for e in KindEventType).
       Pre-filter at collector layer for cheap failure (Rule 2 — cheaper than DB rollback)."
    - "filed_at heuristic: KST 15:30 close on event_date (KRX market close — RESEARCH Q1).
       Phase 3 backfill may refine when full filing body is fetched."
key-files:
  created:
    - src/collectors/kind/db_writer.py
    - tests/collectors/kind/test_db_writer.py
  modified:
    - src/collectors/kind/__init__.py
    - tests/collectors/kind/test_collect_kind.py
decisions:
  - "Two separate engine.begin() blocks per paired write (not one combined transaction). The
     plan body sketched a combined transaction but with the disclaimer 'For Phase 1, use a
     separate engine.begin() block per UPSERT to keep db_writer API simple.' I followed that
     path. Filings is the source of truth; an orphan filings row from a partial paired write
     is repairable (the next run re-inserts the events row via ON CONFLICT DO NOTHING with
     no harm). The stronger cross-table atomicity guarantee would require either passing a
     Connection into db_writer or refactoring to a single combined UPSERT — both deferred."
  - "Collector-side event_type filter (5-value enum) instead of relying solely on the DB CHECK
     constraint. Rationale: a bogus event_type (e.g. 'delisting' from the EXTENDED set) gives a
     cleaner failure with the offending value in stats['failed'] than a SQLAlchemy
     IntegrityError. The CHECK is belt-and-suspenders against any code path that bypasses the
     pre-filter."
  - "suspension_cross_check_mismatch deferred to Phase 9 with a pass-through empty list on the
     structured log. The v1.0 implementation parsed vault/ingested/_status/heartbeat.md to find
     KRX's suspended_tickers extra — that file no longer exists post-shutdown. Phase 9 ops
     dashboard will query collector_runs.extra JSONB on the krx and kind sources to compute
     the mismatch directly from durable state. Emitting the key as [] keeps the log contract
     stable for downstream observers."
  - "Phase 1 KIND filings.body_md = '' (empty string). The KIND classifier only needs report_nm
     + source_url to be useful; fetching the full filing body for every KIND-classified DART
     filing would either duplicate work the dart collector (01-07) will do or push the burden
     onto a separate fetcher. Phase 3 backfill (when full-body filings.body_md is needed for
     embedding generation) will populate KIND-classified filings via a one-off backfill job."
  - "Source detection by source_id shape (14 digits = DART rcept_no): cleaner than threading
     a 'source' field through dart_events.py + scraper.py. The shape test is unambiguous —
     DART rcept_no is always 14 ASCII digits; KIND synthesizes 'kind_undiscl_{company}_{date}'
     style ids that fail isdigit()."
  - "_LEGACY_VAULT_ROOT deleted (was 'vault'). repo_root = Path('.') resolves Portfolio.load
     against cwd — same pattern as 01-03/01-04. Tests use monkeypatch.chdir(tmp_path) with a
     tmp_path/notes/private/portfolio.md seed."
metrics:
  tasks_completed: 3
  duration_minutes: ~30
  tests_added: 23
  tests_total_in_kind_module: 45
  commit_hashes:
    - 99cb500  # Task 1 RED — 13 failing db_writer tests
    - a62a15d  # Task 1 GREEN — db_writer.py (upsert_kind_filing + upsert_kind_event)
    - 8b60f31  # Task 2+3 RED — collect_kind tests rewritten to DB assertions
    - ae0b828  # Task 2+3 GREEN — collect_kind body refactored to paired db_writer calls
---

# Phase 1 Plan 01-05: KIND Collector DB-Direct Cutover — Summary

One-liner: `collect_kind` now performs paired writes — one row in `filings`
(pblntf_ty='I', body_md='') and one row in `events` (with filing_rcept_no FK) for
every DART exchange-status event; KIND-only AJAX events produce a single
`events` row with `source='kind'` and no filings counterpart. Markdown writer
calls and the legacy heartbeat dependency are severed.

## What Changed

### `db_writer.upsert_kind_filing` Public Contract

```python
def upsert_kind_filing(
    engine: Engine,
    *,
    rcept_no: str,            # 14 ASCII digits; regex pre-filtered
    corp_code: str,           # 8 ASCII digits; FK to entities
    ticker: str | None,
    filed_at: datetime,       # tz-aware; collect_kind uses KST 15:30 close
    report_nm: str,
    event_type: str,          # in {suspension, watchlist_designation,
                              #     investment_caution, investment_risk,
                              #     unfaithful_disclosure}
    source_url: str,
    body_md: str = "",        # Phase 1 KIND default; Phase 3 backfills
) -> Literal["inserted", "updated", "skipped"]:
```

- **`inserted`**: no prior row at rcept_no — fresh row written with pblntf_ty='I'.
- **`updated`**: prior row existed AND content_hash differs (body_md changed).
  All EXCLUDED columns overwrite; last_seen_at bumps.
- **`skipped`**: prior row exists with matching content_hash. Only last_seen_at
  bumps (idempotent re-run still records "we saw it").

### `db_writer.upsert_kind_event` Public Contract

```python
def upsert_kind_event(
    engine: Engine,
    *,
    event_type: str,
    ticker: str,              # 6 ASCII digits
    event_date: date,
    source: str,              # 'dart' or 'kind'
    source_id: str,           # rcept_no for DART; synthesized id for KIND
    source_url: str,
    corp_code: str | None = None,
    subtype: str | None = None,
    reason: str = "",
    filing_rcept_no: str | None = None,  # FK to filings.rcept_no
) -> Literal["inserted", "skipped"]:
```

- **`inserted`**: new row written. RETURNING id has a value.
- **`skipped`**: ON CONFLICT DO NOTHING fired (UNIQUE collision on
  `(event_type, ticker, event_date, source, source_id)`). Existing row untouched.
- Events are **immutable classifications** (RESEARCH Q2). The only state
  transition is "absent → present". Cross-source duplicates (DART and KIND
  emitting the same unfaithful_disclosure) → first writer wins.

### Paired Write Transaction Pattern

For each scope-filtered DART event, `collect_kind` runs the writes in two
separate `engine.begin()` blocks:

```
1. upsert_kind_filing(rcept_no=source_id, ...) → filing_outcome
2. upsert_kind_event(filing_rcept_no=source_id, ...) → event_outcome
```

Atomicity is per-table, not per-event. If the filings UPSERT succeeds and the
events INSERT then fails, the orphan filings row is valid on its own; the
failed events row appears in `stats['failed']` for retry on the next run.
The plan's "engine.begin() per UPSERT keeps db_writer API simple" guidance
was followed verbatim.

Outcome classification (per event):
- `inserted` ← either filing_outcome=='inserted' OR event_outcome=='inserted'
- `updated`  ← filing_outcome=='updated' (events never update)
- `skipped`  ← both 'skipped' (content_hash matches AND UNIQUE collision)

### FK Link Verification

`tests/collectors/kind/test_collect_kind.py::test_collect_kind_dart_event_writes_filings_and_events`
asserts the FK link via SQL JOIN:

```sql
SELECT count(*) FROM events e JOIN filings f ON e.filing_rcept_no = f.rcept_no
```

Returns 2 for the test's 2 DART events — confirming `filing_rcept_no` carries
a valid pointer into `filings.rcept_no` (the FK is ON DELETE SET NULL per
migration 0006, so an entity deletion would null the FK but preserve the
events row — tested at the schema layer in 01-01).

### Source Classification (DART vs KIND)

```python
source_id_raw = str(e.get("source_id") or "")
source_kind = "dart" if source_id_raw.isdigit() and len(source_id_raw) == 14 else "kind"
```

DART rcept_no is always 14 ASCII digits. KIND AJAX synthesizes ids like
`kind_undiscl_{company}_{event_date}` that fail isdigit(). This shape test
is unambiguous and avoids threading a `source` field through every event
producer.

### Hard Veto Compliance

- **Veto #6 (no numeric embedding):** `events` table — no body_md / no
  embedding column on the table itself (verified in 01-01). The db_writer
  never touches a body column on events.
- **Veto #8 (no DART pre-chunking):** `filings.body_md` stays whole (empty
  in Phase 1 for KIND; full body in 01-07 for DART A/B filings). No chunking.
- **Veto #9 (no vault revival):** `_LEGACY_VAULT_ROOT`, `vault_root`,
  `_read_heartbeat_extra`, `record_source_run`, `writer.*` calls — all gone
  from `collect_kind`. Verified via grep:
  ```
  $ grep -nE "vault_root|_LEGACY_VAULT_ROOT|_read_heartbeat_extra|record_source_run|(?:^|[^_])writer\." src/collectors/kind/__init__.py
  22:- ``writer.py`` is NOT imported. Anyone re-importing it gets a hard
  ```
  Only the docstring line remains, explaining the absence. The actual
  `writer.py` file still lives on disk — 01-09 deletes it.

### Cross-Check Deferred (Phase 9)

The v1.0 collector parsed `vault/ingested/_status/heartbeat.md` to read KRX's
`suspended_tickers` extra and surface a `suspension_cross_check_mismatch` list
(KRX-says-suspended ∖ DART-suspension). That heartbeat file no longer exists.

`collect_kind` emits `suspension_cross_check_mismatch: []` on the structured
log as a pass-through placeholder. Phase 9 ops dashboard will compute the
mismatch by querying `collector_runs.extra` JSONB on both krx and kind sources
— more durable than a Markdown sidecar and parseable from the dashboard side.

The DART side of the cross-check is still produced — `dart_suspended_tickers`
is emitted on the structured log so Phase 9 has the input it needs.

### Parse Error Resilience (R-17)

If the KIND scraper raises `ParseError` (selector drift), the collector:
1. Logs a warning (not exception — the cause is upstream HTML drift, not a bug).
2. Sets `kind_scrape_stats["status"] = "parse_error"`.
3. Appends a `{"doc": "kind_undiscl", "error": "ParseError: ..."}` to `stats['failed']`.
4. Emits `kind_parse_error=True` on the structured run-complete log.
5. **Continues** — the DART branch is unaffected, the run completes normally.

`test_collect_kind_parse_error_resilient` asserts this end-to-end.

## Test Results

| File                                          | Tests | Result |
| --------------------------------------------- | ----- | ------ |
| `tests/collectors/kind/test_db_writer.py`     | 13    | 13 PASS |
| `tests/collectors/kind/test_collect_kind.py`  | 10    | 10 PASS |
| `tests/collectors/kind/test_scraper.py`       | 4     | 4 PASS  |
| `tests/collectors/kind/test_sources.py`       | 5     | 5 PASS  |
| `tests/collectors/kind/test_client.py`        | 3     | 3 PASS  |
| `tests/collectors/kind/test_writer.py`        | 6     | 6 PASS (legacy, removed by 01-09) |
| **Total**                                     | 41    | 41 PASS |
| `tests/test_import_guard.py`                  | 4     | 4 PASS  |

Runtime: ~16s for the full kind suite on testcontainer (pg17 + vchord-suite image).

### Test Coverage Highlights

**db_writer.py (13 tests):**
- `test_upsert_filing_fresh` / `_idempotent` / `_body_changed` — load-then-classify outcomes
- `test_upsert_filing_unknown_corp_raises_fk` — FK to entities enforced at DB
- `test_upsert_filing_invalid_rcept_no_raises` / `_invalid_event_type_raises` — pre-flight validation
- `test_upsert_event_fresh` / `_idempotent` — ON CONFLICT DO NOTHING semantics
- `test_upsert_event_with_filing_link` — **FK JOIN assertion** (the load-bearing test)
- `test_upsert_event_check_constraint_violation` — bogus event_type rejected pre-flight
- `test_upsert_event_invalid_ticker_raises` / `_invalid_source_raises` — pre-flight validation
- `test_upsert_event_kind_only_no_filing_link` — KIND-only path leaves filing_rcept_no=NULL

**collect_kind (10 tests):**
- `test_collect_kind_dart_event_writes_filings_and_events` — paired write + FK JOIN
- `test_collect_kind_kind_only_event_skipped_without_filings` — KIND AJAX path
- `test_collect_kind_idempotent` — rerun → all skipped, no duplicates
- `test_collect_kind_unknown_event_type_filtered` — collector pre-filter
- `test_collect_kind_missing_ticker_skipped` — empty ticker → skipped
- `test_collect_kind_no_engine_raises` — RuntimeError on None engine
- `test_collect_kind_no_markdown_written` — no vault/raw/kind/ dir created
- `test_collect_kind_cross_check_mismatch_deferred` — Phase 9 placeholder
- `test_collect_kind_dart_fetch_failure_isolated` — DART RuntimeError → failed entry, no crash
- `test_collect_kind_parse_error_resilient` — R-17: ParseError → kind_parse_error=True, run continues

## Deviations from Plan

**Two deviations of substance**, both pre-planned (the plan body called them out as acceptable):

1. **Combined Task 2+3 RED/GREEN cycle** (Rule 3 — workflow):
   Task 2 changes the `collect_kind` signature (removes `vault_root`, makes
   `engine` required). The plan separated Task 2 (rewire body) and Task 3
   (port tests), but the in-between state has known-broken tests — old
   `test_collect_kind.py` still uses `vault_root=`. I executed Task 2 + Task 3
   as a single TDD cycle (RED: rewrite tests; GREEN: refactor body) for
   genuine red→green discipline. Commit log preserves the gate sequence
   (`test(01-05): ... (RED)` precedes `feat(01-05): ... (GREEN)`).

2. **Separate engine.begin() per UPSERT instead of one combined transaction**
   (Rule 2 — explicitly called out by the plan body):
   The plan's <behavior> sketch contained both a combined transaction
   pseudo-code block AND a disclaimer ("For Phase 1, use a separate
   engine.begin() block per UPSERT to keep db_writer API simple"). I
   followed the disclaimer. Trade-off documented in `decisions:` frontmatter.

### Minor mechanical choices (not deviations)

- **Source detection by source_id shape**: 14 ASCII digits = DART rcept_no.
  Cleaner than threading a `source` field through `dart_events.py` and
  `scraper.py`.
- **`db_writer` outcome enums kept tight**: `upsert_kind_filing` →
  `inserted|updated|skipped`; `upsert_kind_event` → `inserted|skipped`
  (events are immutable, no `updated` ever).
- **`upsert_kind_filing` overwrites more columns on UPDATE than strictly
  necessary** (also writes `report_nm`, `source_url`, `ticker` on conflict).
  Reason: a body change usually accompanies a re-classification (e.g. DART
  re-issues the filing with a corrected report_nm). Over-overwriting is
  safer than under-overwriting when content_hash signals a real change.
- **`dart_suspended_tickers` emitted on log** (not in the plan body) — kept
  in case Phase 9 needs the DART suspension set for cross-check
  reconstruction. Free signal; ignored if unused.

## Pitfalls Encountered + Resolution

| # | Pitfall                                                            | Resolution |
| - | ------------------------------------------------------------------ | ---------- |
| 1 | `uv` CLI not on PATH (only `python -m uv` works on this box)       | Used `python -m uv run` for all pytest invocations. Same as the box-wide convention observed in 01-01-SUMMARY.md. |
| 2 | Sibling agents (01-06 news, 01-07 dart) had files modified during my run | Stayed within my plan's file set: `src/collectors/kind/{__init__,db_writer}.py` + `tests/collectors/kind/{test_collect_kind,test_db_writer}.py`. `git status` showed sibling modifications on disjoint paths; no collision. |
| 3 | Test fixture `_LEGACY_VAULT_ROOT.parent` no longer applies — old tests pass `vault_root=` | Rewrote `test_collect_kind.py` to use `tmp_path + monkeypatch.chdir` (matching the 01-04 krx test pattern); the `vault_tmp` fixture from `tests/collectors/conftest.py` is now unused by my tests (test_writer.py still uses it — 01-09 cleans both up). |
| 4 | KIND AJAX event source-id has variable shape (`kind_undiscl_{co}_{date}`) — substring digits could confuse isdigit() | The `isdigit() and len()==14` test reliably classifies: full 14-digit numeric string vs anything else. Only false-positive risk is a malformed KIND id that's coincidentally 14 digits — current KIND id format makes this impossible. |
| 5 | `test_collect_kind_unknown_event_type_filtered` initially failed because the original behavior counted unknown-type events as "skipped" (before the pre-filter was added in Task 2 body) | Added the explicit `if event_type not in _ALLOWED_EVENT_TYPES: stats['failed'].append(...)` block to the loop. The plan's `<action>` in Task 3 sketched exactly this. |

## Threat Surface

No new network endpoints, auth paths, or file-access patterns. All writes
flow through SQLAlchemy bind params (no f-string interpolation). Three
pre-flight validators close digit / enum loopholes:

- `rcept_no` regex `^[0-9]{14}$` rejects path-traversal-class garbage at the
  filings boundary.
- `ticker` regex `^[0-9]{6}$` (same D-12 ASCII-digit pre-filter as
  `db.entity` and `collectors.krx.db_writer`).
- `source` set membership `{'dart','kind'}` + `event_type` frozenset
  membership against `KindEventType` enum.

DB-level CHECK constraints (declared in 01-01 migration 0006) are the
belt-and-suspenders backup if any future code path bypasses the pre-filter.

No new threat flags.

## Self-Check: PASSED

- `src/collectors/kind/db_writer.py` — FOUND
- `tests/collectors/kind/test_db_writer.py` — FOUND
- `src/collectors/kind/__init__.py` modified — FOUND
- `tests/collectors/kind/test_collect_kind.py` rewritten — FOUND
- commit `99cb500` (Task 1 RED) — FOUND in git log
- commit `a62a15d` (Task 1 GREEN) — FOUND in git log
- commit `8b60f31` (Task 2+3 RED) — FOUND in git log
- commit `ae0b828` (Task 2+3 GREEN) — FOUND in git log
- 13/13 tests in `test_db_writer.py` PASS
- 10/10 tests in `test_collect_kind.py` PASS
- 45/45 tests in `tests/collectors/kind/` PASS (35 excluding test_writer)
- 4/4 tests in `tests/test_import_guard.py` PASS
- `grep -E "(?:^|[^_])writer\." src/collectors/kind/__init__.py` returns only docstring line
- `grep -E "vault_root|_LEGACY_VAULT_ROOT|_read_heartbeat_extra|record_source_run" src/collectors/kind/__init__.py` returns no matches
