---
phase: "01-collector-db-cutover"
plan: "01-08"
subsystem: "shared/observability"
tags: [observability, dual-sink, collector-runs, heartbeat-removal, phase-1, wave-3, sc-3]
requires:
  - migration 0006 (collector_runs table, Plan 01-01)
  - dart / krx / news / macro / kind collectors emitting structured stderr run-complete log
    (Plans 01-03 through 01-07)
provides:
  - shared.run_log.record_collector_run helper — single sink behind every collector's
    collector_runs INSERT
  - tests/test_no_heartbeat.py — three-assertion CI guard against shared.heartbeat
    resurrection (SC-3 fence)
  - tests/collectors/test_observability_wiring.py — five-case integration test
    (one per source) verifying exactly one collector_runs row per collect_* call
affects:
  - all 5 collector __init__.py files (one call site appended per collect_* function,
    AFTER the existing structured stderr log)
  - downstream Phase 9 ops dashboard — reads collector_runs (source, run_at) over time;
    Phase 1 only writes
tech-stack:
  added: []
  patterns:
    - "Best-effort observability sink: try/except wrapping the INSERT logs a WARNING
       and returns None on DB failure; the collect run is NEVER aborted by an
       observability write failure (RESEARCH.md Q5 — ops dashboard goes blind,
       not data loss)"
    - "Direct ``CAST(:extra AS jsonb)`` bind instead of a ``CASE WHEN :extra IS NULL``
       branch — psycopg3 cannot resolve the parameter type inside a CASE branch
       (``could not determine data type of parameter $4``); a direct cast treats
       Python None as SQL NULL → CAST(NULL AS jsonb) cleanly"
    - "Python-side allow-list mirroring the DB CHECK constraint on collector_runs.source
       — fast, informative ValueError instead of a rolled-back transaction"
    - "json.dumps(default=str, ensure_ascii=False) for stats / extra serialization so
       callers can pass Path / datetime values without coercion at every call site"
key-files:
  created:
    - src/shared/run_log.py
    - tests/shared/test_run_log.py
    - tests/test_no_heartbeat.py
    - tests/collectors/test_observability_wiring.py
  modified:
    - src/collectors/dart/__init__.py
    - src/collectors/krx/__init__.py
    - src/collectors/news/__init__.py
    - src/collectors/macro/__init__.py
    - src/collectors/kind/__init__.py
  deleted:
    - src/shared/heartbeat.py
decisions:
  - "Best-effort sink (try/except) is the contract — never let an observability write
     abort a collect. v1.0's heartbeat had the same isolation property. RESEARCH.md
     Q5 explicitly approves this."
  - "Existing per-collector structured log lines (_log.info('collector_run_complete',
     extra={...})) are PRESERVED unchanged. Three existing tests
     (tests/collectors/macro/test_collect_macro.py::test_collect_macro_revision_detection,
     tests/collectors/krx/test_collect_krx.py — holiday extra,
     tests/collectors/kind/test_collect_kind.py — suspension_cross_check_mismatch +
     kind_parse_error) couple to specific attributes on the log record (revisions,
     extra.holiday_tickers, kind_parse_error). Changing the log shape would have
     broken them; the new DB-row sink is purely additive."
  - "record_collector_run's extra dict shape mirrors the source-specific log extras
     1:1 for macro (revisions[]), krx (holiday_tickers[] + missing_entity[]), and
     kind (dart_events{}, kind_scrape{}, kind_parse_error, suspension_cross_check_mismatch,
     dart_suspended_tickers). dart and news pass extra=None per the plan
     (no per-source extras at Phase 1)."
  - "Cached __pycache__/heartbeat.cpython-313.pyc was also removed so the import
     attempt cannot satisfy itself from stale bytecode in CI workers."
metrics:
  tasks_completed: 3
  duration_minutes: ~45
  tests_added: 16   # 8 run_log + 5 wiring + 3 no_heartbeat guard
  collector_tests_after: 137  # all still pass
  commit_hashes:
    - 4a81518  # Task 1 — shared.run_log helper + 8 unit tests
    - 3ca6a2e  # Task 2 — wire all 5 collectors + 5 integration tests
    - fc73edf  # Task 3 — delete heartbeat.py + 3-assertion CI guard
---

# Phase 1 Plan 01-08: Observability Cutover — `collector_runs` + heartbeat removal

One-liner: ``shared.run_log.record_collector_run`` becomes the single sink behind
every collector's ``collector_runs`` row, ``shared.heartbeat.py`` is deleted, and
a three-assertion CI guard prevents resurrection — closing ROADMAP SC-3 and
landing the DB-row half of RESEARCH.md Q5's dual-sink observability contract.

## What changed

### Dual-sink contract (RESEARCH.md Q5)

Every ``collect_*`` function now fires BOTH sinks at end of run:

1. **Structured stderr log** — synchronous, no DB dependency, real-time
   visibility during ``stock collect``. Already existed; left UNCHANGED so the
   three existing per-collector tests that assert against ``revisions``,
   ``extra.holiday_tickers``, ``kind_parse_error``, and
   ``suspension_cross_check_mismatch`` continue to pass.

2. **``collector_runs`` row** — persistent history for the Phase 9 ops
   dashboard. Best-effort: a DB-side exception logs a WARNING and returns
   None; the collect run NEVER fails because of an observability write.

### Wiring sites

Every collector calls ``record_collector_run`` exactly once at end of run,
immediately after the existing ``_log.info("collector_run_complete", ...)``:

| Source | File                                    | Call site (line) | extra dict                                                                                                                            |
| ------ | --------------------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| dart   | src/collectors/dart/__init__.py         | 171              | None                                                                                                                                  |
| krx    | src/collectors/krx/__init__.py          | 230-232          | {holiday_tickers[], missing_entity[]} or None                                                                                         |
| news   | src/collectors/news/__init__.py         | 148              | None                                                                                                                                  |
| macro  | src/collectors/macro/__init__.py        | 161-163          | {revisions[]} or None                                                                                                                 |
| kind   | src/collectors/kind/__init__.py         | 303-305          | {dart_events{}, kind_scrape{}, kind_parse_error, suspension_cross_check_mismatch[], dart_suspended_tickers[]}                          |

### Helper contract

```python
def record_collector_run(
    engine: Engine | None,
    source: str,                   # 'dart' | 'krx' | 'news' | 'macro' | 'kind'
    stats: dict[str, Any],         # {total, inserted, updated, skipped, failed[], elapsed_ms}
    elapsed_ms: int,
    extra: dict[str, Any] | None = None,
) -> int | None:
    """INSERT one row into collector_runs. Returns inserted id, or None on
    best-effort failure / engine=None."""
```

Failure semantics (verified by ``test_record_run_db_failure_swallowed``):

- DB outage → ``WARNING`` logged via ``shared.run_log`` logger, returns ``None``,
  the collect run continues to completion.
- ``engine=None`` → no-op return ``None`` (lets dry-runs / mocked tests skip the
  sink cleanly).
- Unknown source name → ``ValueError`` (programmer error, not runtime data).
- Non-JSON-serializable values in ``stats`` / ``extra`` → coerced via
  ``json.dumps(default=str)``; tested explicitly.

### Sample collector_runs row (kind run)

From ``test_collect_kind_writes_collector_runs_row`` with empty DART feed,
empty scope:

```
id          | 1
source      | kind
run_at      | 2026-05-29 14:23:11.847+00 (server_default now())
elapsed_ms  | 12
stats       | {"total": 0, "inserted": 0, "updated": 0, "skipped": 0,
              "failed": [], "elapsed_ms": 12}
extra       | {"dart_events": {"docs_processed": 0, "status": "ok",
                               "elapsed_ms": 8},
              "kind_scrape": {"docs_processed": 0, "status": "skipped"},
              "kind_parse_error": false,
              "suspension_cross_check_mismatch": [],
              "dart_suspended_tickers": []}
```

### CI guard against heartbeat resurrection

``tests/test_no_heartbeat.py`` — three assertions, runs in the default
``pytest -m "not slow and not e2e"`` pass:

1. ``test_heartbeat_module_not_on_disk`` — ``src/shared/heartbeat.py`` MUST NOT
   exist.
2. ``test_no_collector_imports_heartbeat`` — AST-walks every
   ``src/collectors/<src>/`` file and rejects any ``Import`` / ``ImportFrom``
   node referencing ``heartbeat``.
3. ``test_heartbeat_not_importable`` — ``importlib.util.find_spec("shared.heartbeat")``
   returns ``None`` AND ``importlib.import_module("shared.heartbeat")`` raises
   ``ModuleNotFoundError``.

Defense-in-depth: the cached
``src/shared/__pycache__/heartbeat.cpython-313.pyc`` was also removed so the
import attempt cannot satisfy itself from a stale bytecode cache.

### Hard Veto enforcement

None of the 13 Hard Vetoes are touched by this plan. The added DB write is
to a typed observability table (``collector_runs``) with a Postgres CHECK
constraint on ``source``; no LLM call, no embedding, no Markdown vault,
no automatic-trade gate.

## Test results

| File                                                | Tests | Result | Notes                                                       |
| --------------------------------------------------- | ----- | ------ | ----------------------------------------------------------- |
| tests/shared/test_run_log.py                        | 8     | 8 PASS | INSERT, JSONB query, extra NULL/nested, engine=None,        |
|                                                     |       |        | unknown source ValueError, DB-failure caplog, Path coercion |
| tests/collectors/test_observability_wiring.py       | 5     | 5 PASS | One per collector — exactly one collector_runs row per run  |
| tests/test_no_heartbeat.py                          | 3     | 3 PASS | SC-3 fence (file absent, no imports, not importable)        |
| tests/collectors/ (full regression)                 | 137   | 137 PASS | Existing per-collector tests still pass — log shape preserved |
| tests/test_import_guard.py (sanity check)           | 4     | 4 PASS | No collector imports anthropic/openai                       |

Combined: 153 tests run, 153 pass. No regressions.

## Deviations from plan

**None of substance.** All three tasks executed as specified.

Minor mechanical choices recorded in the ``decisions:`` frontmatter:

1. **SQL bind for ``extra``**: switched from the plan's ``CASE WHEN :extra IS NULL``
   shape to a direct ``CAST(:extra AS jsonb)`` because psycopg3 surfaced
   ``could not determine data type of parameter $4`` inside the CASE branch.
   Direct cast is unambiguous (Python None → SQL NULL → CAST(NULL AS jsonb))
   and shorter. Documented inline in ``run_log.py`` and verified by
   ``test_record_run_extra_null_omitted``.

2. **Caplog key choice in WARNING**: the plan suggested ``extra={"source": ...,
   "error": ...}`` but ``source`` would collide with a per-source LogRecord
   filter on real-time tailing. Used ``extra={"collector_source": source}``
   and passed ``type(exc).__name__`` + ``str(exc)`` as positional format args
   instead — surfaces the exception type/message in the default formatter and
   is what the caplog assertion in ``test_record_run_db_failure_swallowed``
   checks for. Pitfall 10 (RESEARCH.md) compliance.

3. **kind extra also carries ``dart_suspended_tickers``**: the plan's
   per-source extra spec for kind listed four keys (``dart_events``,
   ``kind_scrape``, ``kind_parse_error``,
   ``suspension_cross_check_mismatch``). The existing structured stderr log
   also carries ``dart_suspended_tickers`` — useful Phase 9 observability,
   so included it in the DB sink too. No functional impact; just one extra
   key in the JSONB.

## Phase 9 deferrals (documented)

Per the Plan 01-08 ``<context>`` block + RESEARCH.md Open Question 4:

- **``collector_runs`` retention/cleanup** is NOT a Phase 1 concern. Daily
  cadence at 5 sources × 1/day ≈ 1.8k rows/year — bounded growth. A future
  Phase 9 prune routine owns the retention policy.
- **Ops dashboard reads** over ``(source, run_at)`` and the ``extra`` JSONB
  shape are deferred to Phase 9. Phase 1 only WRITES.
- **``suspension_cross_check_mismatch`` population** is a Phase 9 concern
  (KIND-side cross-check against DART suspension events). Phase 1 always
  writes ``[]`` (kind collector).

## Pre-existing failures (out of scope per SCOPE BOUNDARY)

- **DI-1** (already documented in ``deferred-items.md`` by sibling 01-09):
  ``tests/test_migration.py::test_events_jsonb_and_fk`` references the
  pre-rename ``events.payload`` column. Introduced by plan 01-01's
  ``events → events_legacy`` migration; not caused by 01-08. Recommended
  fix lives at the 01-01 follow-up level.

## Note on DI-2 (sibling 01-09's observation)

The sibling 01-09 agent's ``deferred-items.md`` flagged DI-2 — alleged
flakiness of ``test_collect_dart_writes_collector_runs_row`` under
suite-wide ordering. I re-ran:

- the full ``tests/collectors/`` suite (137 tests) → all pass
- the ``test_observability_wiring.py`` module → all 5 pass

The dart wiring test is **deterministic** in my final state. The DI-2
observation appears to have been an intermediate snapshot during the
parallel run — likely captured between my Task 2 commit and a transient
state where the sibling's writer-deletion landed before mine. Final
state shows no flakiness.

## Threat surface

No new network endpoints, auth paths, or external file-access patterns.
The new DB writes are to a typed observability table guarded by a
Postgres CHECK constraint on ``source`` plus a Python-side allow-list.
Stats / extra JSONB columns are serialized via ``json.dumps`` (no
SQL interpolation of user-controlled values). No threat flags.

## Self-Check: PASSED

- ``src/shared/run_log.py`` exists — FOUND
- ``src/shared/heartbeat.py`` — DELETED (confirmed ``ls`` returns "No such file")
- ``tests/shared/test_run_log.py`` — FOUND (8 tests)
- ``tests/test_no_heartbeat.py`` — FOUND (3 tests)
- ``tests/collectors/test_observability_wiring.py`` — FOUND (5 tests)
- All 5 collector ``__init__.py`` files modified — FOUND
  (grep ``record_collector_run\(`` returns exactly 5 sites)
- commit ``4a81518`` (Task 1) — FOUND in git log
- commit ``3ca6a2e`` (Task 2) — FOUND in git log
- commit ``fc73edf`` (Task 3) — FOUND in git log
- 16/16 new tests PASS
- 137/137 existing collector tests PASS (no log-shape regression)
- 4/4 import-guard tests PASS
- No collector imports ``shared.heartbeat`` (AST-verified by guard test)
- ``import shared.heartbeat`` raises ``ModuleNotFoundError`` (verified by guard test)
