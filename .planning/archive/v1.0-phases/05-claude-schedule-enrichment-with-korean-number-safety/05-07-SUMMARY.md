---
phase: 05-claude-schedule-enrichment-with-korean-number-safety
plan: 07
subsystem: ingest/heartbeat
tags: [heartbeat, observability, enrich, disk, sla]
requires: [05-01]
provides:
  - compute_disk_metrics (src/ingest/disk_metrics.py)
  - compute_disk_alert_level (src/ingest/disk_metrics.py)
  - compute_enrich_alert_level (src/ingest/heartbeat.py)
  - write_disk_section (src/ingest/heartbeat.py)
  - record_source_run auto-alert_level for source='enrich'
affects:
  - src/ingest/heartbeat.py (extended, backward compatible)
tech-stack:
  added: []
  patterns: [pure-function-module, atomic-write, per-source-isolation-COLL-08]
key-files:
  created:
    - src/ingest/disk_metrics.py
    - tests/test_disk_metrics.py
    - tests/test_heartbeat_enrich.py
  modified:
    - src/ingest/heartbeat.py
decisions:
  - "alert_level auto-populated ONLY when source='enrich' (preserves COLL-08 per-source isolation for dart/krx/news/macro)"
  - "compute_disk_metrics accepts db_size_mb as injected value — module has zero DB deps, Routines skill queries pg_database_size"
  - ".git excluded from vault_mb walk to prevent double-counting when vault_path == repo_path"
  - "stale-last_run threshold uses isoformat parse with Z->+00:00 normalization for robustness"
metrics:
  duration: 13min
  completed_date: 2026-04-24
  tasks: 2
  files_changed: 4
  new_tests: 19
  all_tests_in_scope_passing: 32
requirements: [INGEST-03, INGEST-04]
---

# Phase 05 Plan 07: Heartbeat Enrich & Disk Metrics Summary

Extended `heartbeat.py` with a D-23 `enrich` source schema plus a top-level `disk` section, added a pure-function `disk_metrics.py` module, and wired D-24 SLA thresholds so Plan 05-08 Routines skill can post-loop call `record_source_run("enrich", stats, extra={...})` + `write_disk_section(compute_disk_metrics(...))` and the operator gets an auto-computed `alert_level` in heartbeat.md.

## What Shipped

### Task 1 — `src/ingest/disk_metrics.py` + tests (commit `7433ec2`)

- `compute_disk_metrics(vault_path, repo_path, db_size_mb=None, pgdata_path=None)` walks vault / `.git` recursively, tolerates missing paths (returns 0.0), and returns the D-23 disk dict.
- `compute_disk_alert_level(metrics)` applies D-24 disk rules: `vault_mb > 2000 -> "info"`, `db_mb > 10000 -> "warn"` (warn wins over info).
- Zero DB dependency — Postgres size is injected by the caller (Routines skill queries `pg_database_size(current_database())`).
- 9 tests: missing paths, vault counting, git dir, db passthrough, all threshold combinations, `.git` exclusion from vault walk.

### Task 2 — heartbeat extensions + tests (commit `3bee3fb`)

- `compute_enrich_alert_level(extra, prior_block, now_iso)` implements 4 D-24 SLA thresholds:
  - `consecutive_failures >= 2` → `warn`
  - `backlog_count > 50` → `warn`
  - `now - last_run > 26h` → `warn`
  - `docs_review_flagged / docs_processed > 10%` → `info` (warn overrides info)
- `write_disk_section(disk, heartbeat_path)` atomically merges the top-level `disk` dict into heartbeat.md while preserving `sources`.
- `record_source_run` now auto-populates `alert_level` when `source == "enrich"` and caller did not explicitly set it. Non-enrich sources remain untouched (COLL-08 per-source isolation, asserted by `test_other_sources_unchanged`).
- 10 new tests + existing 22 heartbeat tests (test_heartbeat.py + test_heartbeat_extra.py) all green → 32 total.

## Verification Evidence

```
$ uv run --group dev pytest tests/test_heartbeat_enrich.py tests/test_disk_metrics.py tests/test_heartbeat.py tests/test_heartbeat_extra.py -x -q
................................                                         [100%]
32 passed in 322.97s
```

- `src/ingest/heartbeat.py`: 204 lines (< 300 budget)
- `src/ingest/disk_metrics.py`: 86 lines (< 150 budget)
- Backward compat: existing Phase 3/4 heartbeat behavior unchanged for dart/krx/news/macro sources

## Deviations from Plan

None — plan executed as written. Ruff-format reformatted test files (line-wrap on long dict literals and `from datetime import UTC`) — cosmetic, no semantic change.

## Threat Flags

None — surface matches plan threat_model (Routines skill extra dict, filesystem walk). `_RESERVED_SOURCE_KEYS` filter continues to block `last_run`/`last_success`/`last_failure`/`docs_processed` from caller override (T-04-22 defense-in-depth inherited).

## Integration Points for Plan 05-08

- Routines skill post-loop:
  ```python
  from ingest.heartbeat import record_source_run, write_disk_section
  from ingest.disk_metrics import compute_disk_metrics

  record_source_run("enrich", {"total": N, "succeeded": ok, "skipped": 0, "failed": errs},
                    extra={"docs_skipped_oversize": ..., "docs_review_flagged": ...,
                           "backlog_count": ..., "review_flags": {...},
                           "consecutive_failures": ...})
  write_disk_section(compute_disk_metrics(vault_path="vault", repo_path=".",
                                          db_size_mb=<pg_database_size_mb>))
  ```
- Heartbeat file gains two net-new shapes:
  - `sources.enrich.*` (docs_processed/docs_skipped_oversize/docs_review_flagged/backlog_count/review_flags/alert_level)
  - top-level `disk.*` (vault_mb/git_mb/db_mb/pgdata_mb/alert_level)

## Self-Check: PASSED

- `src/ingest/disk_metrics.py` — FOUND
- `src/ingest/heartbeat.py` — FOUND (extended)
- `tests/test_disk_metrics.py` — FOUND
- `tests/test_heartbeat_enrich.py` — FOUND
- commit `7433ec2` — FOUND in git log
- commit `3bee3fb` — FOUND in git log
- 32/32 tests in scope passing
