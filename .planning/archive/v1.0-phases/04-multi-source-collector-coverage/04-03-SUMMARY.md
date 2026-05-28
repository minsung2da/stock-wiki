---
phase: 04-multi-source-collector-coverage
plan: 03
subsystem: collectors.macro
tags: [ecos, fred, macro, collector, coll-04, d-07, r-05, r-06]
requirements: [COLL-04]
dependency-graph:
  requires:
    - shared.frontmatter.ProvenanceBlock.observations (Plan 04-01 Task 3)
    - shared.frontmatter.Observation (Plan 04-01 Task 3)
    - shared.content_hash.normalize_body
    - ingest.heartbeat.record_source_run (extra kwarg — Plan 04-01)
  provides:
    - collectors.macro.collect_macro
    - collectors.macro.load_catalog
    - collectors.macro.writer.write_macro_doc
    - collectors.macro.writer.merge_observations
    - collectors.macro.client.CollectorConfigError / MacroEmptyResultError
  affects:
    - .planning/macro_series.yaml (verified ECOS IDs committed)
tech-stack:
  added:
    - PublicDataReader (ECOS client, lazy import)
    - fredapi (FRED client, lazy import)
  patterns:
    - Per-source vault path regex guard (mirrors collectors.krx.writer)
    - Append-merge by (date,value) with revision surfacing (R-06)
    - Startup fail-fast on config; per-series soft-fail on empty result (R-05)
key-files:
  created:
    - src/collectors/macro/__init__.py
    - src/collectors/macro/client.py
    - src/collectors/macro/fetcher.py
    - src/collectors/macro/writer.py
    - tests/collectors/macro/__init__.py
    - tests/collectors/macro/test_collect_macro.py
    - tests/fixtures/ecos/base_rate_kr.json
    - tests/fixtures/ecos/usd_krw.json
    - tests/fixtures/ecos/empty_result.json
    - tests/fixtures/fred/DGS10.json
    - tests/fixtures/fred/DCOILWTICO.json
  modified:
    - .planning/macro_series.yaml (placeholders → verified IDs)
decisions:
  - ECOS StatisticSearch response must be filtered by ITEM_CODE1 when a catalog entry supplies one; a STAT_CODE alone returns all items under it.
  - ECOS series 722Y001/0101000 (base_rate_kr) and 731Y001/0000001 (usd_krw) verified live on 2026-04-20.
  - Append-merge reads prior observations from frontmatter.provenance.observations (D-07), not body-markdown parsing — structured is the source of truth.
  - R-05 startup fail-fast gates BEFORE any network call; env-var names are in the error message but secret values are never echoed (T-04-07).
  - R-06 revisions propagate as `extra={'revisions': [...]}` into record_source_run; each entry carries series_id + date + old_value + new_value.
metrics:
  duration: 7min
  completed: 2026-04-18
  commits: 2
  tasks: 2
  files: 12
---

# Phase 4 Plan 3: Macro Collector (ECOS + FRED) Summary

Collect ECOS + FRED macro series (기준금리 / USD·KRW / US 10Y / WTI) to `raw/macro/{source}/{series_id}.md` with append-idempotent writes; observations live in BOTH frontmatter (structured per D-07) and body markdown (human-readable).

## What Shipped

**Task 1 — Wave-0 probe (operator-verified):**
Replaced placeholder ECOS IDs in `.planning/macro_series.yaml` with live-probed values:
- `722Y001` / `0101000` → 한국은행 기준금리 (daily, 연%)
- `731Y001` / `0000001` → 원/미국달러 매매기준율 (daily, 원)

FRED `DGS10` and `DCOILWTICO` confirmed via live observations endpoint. Synthesized minimal JSON fixtures under `tests/fixtures/{ecos,fred}/` for offline tests. Commit `04140f6`.

**Task 2 — collect_macro implementation (TDD):**
Four-module package mirroring the KRX pattern:
- `client.py` — `ecos_client()` / `fred_client()` lazy-import PublicDataReader + fredapi; `require_env()` raises `CollectorConfigError` with env-var name but no value echo.
- `fetcher.py` — `fetch_ecos_series` filters response rows by ITEM_CODE1; raises `MacroEmptyResultError` on empty. `fetch_fred_series` skips NaN, raises `MacroEmptyResultError` on empty.
- `writer.py` — `merge_observations` dedups by (date,value) and surfaces same-date value changes as revisions; `write_macro_doc` reads existing frontmatter observations, merges, recomputes body hash, and only rewrites when the hash changes. Observations written BOTH in `ProvenanceBlock.observations` (D-07) and body markdown table.
- `__init__.py` — `collect_macro` validates every required API key at startup (R-05 fail-fast), then iterates series with per-series soft-fail isolation. Aggregates all revisions and flushes to heartbeat `extra={'revisions': [...]}`. `engine` kwarg kept unused for signature parity with other collectors (R-12).

Commit `5071b0d`.

## Verification Evidence

- `uv run pytest tests/collectors/macro/ -x -q` → **12 passed in 2.81s**
- `uv run pytest tests/test_import_guard.py -x -q` → **4 passed in 1.26s**
- `uv run pytest tests/ -k "frontmatter or heartbeat or dart or portfolio or entity_alias or krx" -x -q` → **86 passed, 1 skipped** (no regressions)
- Acceptance greps: `def collect_macro`, `MacroEmptyResultError`, `_SERIES_RE = re.compile`, `observations=merged`, `revisions`, `Path(__file__).resolve().parents`, `catalog_path` — all found.
- `ls tests/fixtures/fred/*.json | wc -l` → 2.

## Deviations from Plan

None. Plan executed as written; Task 1 (Wave-0 checkpoint) was pre-satisfied by the operator's live probe — the verified ECOS IDs and FRED confirmations were committed directly and fixtures synthesized per the plan's spec.

Minor ruff auto-fixes: pre-commit formatter reflowed list/dict layouts in `__init__.py`, `writer.py`, and the test module; no semantic change.

## Decisions Made

1. **ECOS ITEM_CODE1 filter is mandatory** — confirmed via live probe that StatisticSearch returns multiple items under a STAT_CODE when no item code is supplied. The fetcher also performs a defensive local filter.
2. **R-05 startup fail-fast checks all required keys before ANY series runs** — avoids mid-run credential errors that would leave some series succeeded and others failed-with-auth-error.
3. **Source-of-truth for append merge is frontmatter, not body** — `_read_existing_observations` reads `ProvenanceBlock.observations` (typed `Observation` models). Body markdown table is regenerated from merged observations on every rewrite.
4. **Revisions are structured objects, not log lines** — `record_source_run("macro", ..., extra={"revisions": [{series_id, date, old_value, new_value}, ...]})` makes them machine-readable in heartbeat.md for later ingest doctor analysis.
5. **Fixtures are synthetic, minimal, and date-stable** — tests don't depend on live API responses or today's date math beyond the deterministic monkey-patched fetchers.

## Self-Check: PASSED

- `src/collectors/macro/{__init__,client,fetcher,writer}.py` exist ✓
- `tests/collectors/macro/test_collect_macro.py` exists ✓
- `tests/fixtures/ecos/*.json` (3 files) and `tests/fixtures/fred/*.json` (2 files) exist ✓
- Commit `04140f6` (Task 1) and `5071b0d` (Task 2) on master ✓
- `.planning/macro_series.yaml` contains verified series IDs ✓
