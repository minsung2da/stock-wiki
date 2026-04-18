---
phase: 04-multi-source-collector-coverage
plan: 02
subsystem: krx-collector
tags: [wave-2, krx, pykrx, collector, coll-02]
dependency_graph:
  requires: [04-01]
  provides:
    - "collect_krx(vault_root, engine, since=None) → COLL-02 daily raw/krx writer"
    - "writer.write_krx_doc + vault_path_for_krx + compute_body_hash for downstream reuse"
    - "fetcher.fetch_{ohlcv,trading_value,shorting_balance} with tenacity retry"
  affects: [04-06]
tech_stack:
  added:
    - "tabulate>=0.9 (required by pandas.DataFrame.to_markdown)"
    - "tenacity>=9.0 (promoted to collectors group for non-DART retry)"
  patterns:
    - "Ticker/date regex pre-filter before Path.joinpath (T-04-04 path traversal)"
    - "R-03 Option A: resolve_entity pre-write → None → skip file + heartbeat.extra.missing_entity"
    - "Empty-DF holiday detection → no file + heartbeat.extra.skipped_holiday=True"
    - "Per-ticker try/except isolation appends {doc, error} to stats['failed'] (COLL-08)"
key_files:
  created:
    - src/collectors/krx/__init__.py
    - src/collectors/krx/client.py
    - src/collectors/krx/fetcher.py
    - src/collectors/krx/writer.py
    - tests/collectors/krx/__init__.py
    - tests/collectors/krx/test_writer.py
    - tests/collectors/krx/test_collect_krx.py
    - tests/fixtures/krx/ohlcv_005930.json
    - tests/fixtures/krx/trading_value_005930.json
    - tests/fixtures/krx/shorting_balance_005930.json
  modified:
    - pyproject.toml
    - uv.lock
decisions:
  - "Bundled collect_krx orchestrator into T1 commit alongside writer (inseparable: orchestrator tests in T2 depend on it); T2 commit delivered the behavior tests that pin the contract"
  - "Promoted tenacity to collectors dep group (was ingest-only) — KRX fetcher needs it outside the ingest path"
  - "Kept fetcher call order: ohlcv FIRST, then entity resolve, then flow+short — holiday detection avoids DB lookup for empty days"
metrics:
  duration_sec: 1107
  tasks_completed: 2
  tests_added: 14
  completed_date: 2026-04-18
requirements: [COLL-02]
---

# Phase 4 Plan 02: KRX Collector Summary

Delivered `collect_krx` per COLL-02 and Phase 4 Success Criterion #1: pykrx-backed daily writer that merges OHLCV + investor flow + short balance into one `raw/krx/YYYY-MM-DD/{ticker}.md` per scope ticker, with content-hash idempotency, per-ticker isolation, holiday handling, and R-03 missing-entity Option A — all fixture-driven, zero network in CI.

## One-liner

`collect_krx` lands as the second Wave-2 collector: pykrx OHLCV + investor flow + short balance merged per-ticker per-day, with regex-guarded paths, tenacity-retried fetchers, content-hash idempotency, and heartbeat extras for `skipped_holiday` and `missing_entity`.

## Tasks Completed

| Task | Name                                                          | Commit    | Tests |
| ---- | ------------------------------------------------------------- | --------- | ----- |
| 1    | KRX writer + client/fetcher + fixture tests                   | `dfac635` | 8     |
| 2    | collect_krx orchestrator integration tests (R-03, heartbeat)  | `2fbbad6` | 6     |

## Verification Evidence

```
$ uv run --group collectors --group db --group ingest --group dev \
    pytest tests/collectors/krx/ -x -q
14 passed, 1 warning in 23.76s

$ uv run --group collectors --group db --group ingest --group dev \
    pytest tests/test_import_guard.py tests/ -k "frontmatter or heartbeat or dart" -x -q
57 passed, 1 skipped, 173 deselected, 1 warning in 53.66s
# (54 Phase 3 regression + 3 krx-matched; import guard clean — no anthropic/openai)
```

## Deviations from Plan

Minimal process deviations; no behavioral deviations.

1. **[Rule 2 — Packaging]** Plan specified only `pykrx` and `tabulate` additions to the collectors group. Added `tenacity>=9.0` as well, because `src/collectors/krx/fetcher.py` imports `tenacity` and the dep was previously only in the `ingest` group. Without this, fresh `uv sync --group collectors` would miss tenacity. Non-behavioral — dependency correctness only.
2. **[Task sequencing]** Plan structured Task 1 = writer-only, Task 2 = orchestrator. Because the orchestrator (`src/collectors/krx/__init__.py`) has no tests of its own in T1 but IS required for T2's test file to even import, I wrote the orchestrator alongside the writer in the T1 commit. T2 commit delivers only the 6 behavior tests that pin the contract. Both commits are runnable (T1 alone passes 8/8; T2 adds 6 more). Tests coverage and plan acceptance criteria unchanged.
3. **[Cosmetic]** Ruff auto-fixed two whitespace items in `test_collect_krx.py` on first commit attempt; re-staged and committed clean on retry. Pre-commit hook `secret-scanner`/ruff/ruff-format all green.

## R-03 Behavior Confirmed

`test_collect_krx_missing_entity_option_a` asserts, on a vault scoped to `[005930, 999999]` with only 005930 in `entities`:
- `raw/krx/2026-04-17/005930.md` IS written
- `raw/krx/2026-04-17/999999.md` is NOT written
- `stats['failed']` contains `{"doc": "999999", "error": "missing_entity"}`
- `heartbeat.md` → `sources.krx.missing_entity: ['999999']`
- 005930 succeeds despite 999999 failing (per-ticker isolation preserved)

## Holiday Behavior Confirmed

`test_collect_krx_holiday_skip_records_heartbeat_extra` injects an empty OHLCV DataFrame for one ticker. Collector:
- writes no file for that ticker
- increments `stats['skipped']`
- records `sources.krx.skipped_holiday: true` and `sources.krx.holiday_tickers: ['000660']` on heartbeat

## Idempotency Confirmed

`test_collect_krx_idempotent_rerun_all_skipped`: consecutive runs with unchanged fixture data → second run returns `stats['skipped'] == 2`, `succeeded == 0`, and file `mtime_ns` is byte-identical between runs (atomic-write never replaced the file because content_hash matched).

## Known Stubs

None. All code paths are exercised by fixture-driven tests; no placeholders in `collect_krx`.

## Threat Flags

None. Changes are additive to existing trust-boundary-hardened modules:
- New network surface is behind tenacity retry + pykrx's own HTTP client (no new scraper code)
- Path construction is pre-filtered by ticker `^\d{6}$` and date `^\d{4}-\d{2}-\d{2}$` regexes (T-04-04 mitigated)
- No new secrets (pykrx takes none)
- Heartbeat `extra` uses only non-secret flags (ticker lists)

## Self-Check: PASSED

**Files verified exist:**
- FOUND: src/collectors/krx/__init__.py
- FOUND: src/collectors/krx/client.py
- FOUND: src/collectors/krx/fetcher.py
- FOUND: src/collectors/krx/writer.py
- FOUND: tests/collectors/krx/test_writer.py
- FOUND: tests/collectors/krx/test_collect_krx.py
- FOUND: tests/fixtures/krx/ohlcv_005930.json
- FOUND: tests/fixtures/krx/trading_value_005930.json
- FOUND: tests/fixtures/krx/shorting_balance_005930.json

**Commits verified in `git log`:**
- FOUND: dfac635 (T1 — feat(04-02-T1): KRX writer + client/fetcher + fixture tests)
- FOUND: 2fbbad6 (T2 — feat(04-02-T2): collect_krx orchestrator integration tests)
