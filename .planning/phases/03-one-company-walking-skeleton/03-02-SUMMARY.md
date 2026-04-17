---
phase: 03-one-company-walking-skeleton
plan: 02
subsystem: collectors
tags: [collectors, dart, heartbeat, vault, provenance, trust-level]

requires:
  - phase: 03-one-company-walking-skeleton
    plan: 01
    provides: "ProvenanceBlock base schema + content_hash utility + frontmatter atomic write"
provides:
  - "src/collectors/dart/ — collect_dart(corp_code, since, max_docs, vault_root) → dict"
  - "src/ingest/heartbeat.py — record_source_run(source, stats, heartbeat_path?) atomic writer"
  - "ProvenanceBlock.trust_level Literal['trusted','semi_trusted','adversarial'] default 'trusted' (D-19)"
  - "Vault layout: vault/raw/dart/YYYY/{rcept_no}_{corp_code}.md (locked for Plan 04 worker)"
  - "Heartbeat layout: vault/ingested/_status/heartbeat.md with top-level sources dict per source"
  - "Body extraction strategy: pages[*].html → BeautifulSoup/lxml text, fallback to to_dict()['text']/['body'], fallback to empty string"
affects: [03-04, 03-05]

tech-stack:
  added: []
  patterns:
    - "Atomic write via tempfile+os.replace in same directory (reused from Phase 1 write_frontmatter)"
    - "Heartbeat YAML parsed outside the FrontMatter Pydantic schema (sources dict is operational telemetry, not document frontmatter)"
    - "Per-filing try/except isolation with stats['failed'] = [{doc, error}]"
    - "Idempotency: hash the freshly-fetched normalized body, compare to existing frontmatter.provenance.content_hash → skip when equal"
    - "Lazy dart_fss import inside client.get_client so tests monkeypatch client.find_corp before dart-fss ever loads"

key-files:
  created:
    - src/collectors/dart/__init__.py
    - src/collectors/dart/client.py
    - src/collectors/dart/fetcher.py
    - src/collectors/dart/writer.py
    - src/ingest/heartbeat.py
    - tests/test_heartbeat.py
    - tests/test_collect_dart.py
  modified:
    - src/shared/frontmatter.py

key-decisions:
  - "trust_level lives on ProvenanceBlock (Zone 1) — collector-written, never overwritten by ingest, aligns with D-19"
  - "Content-hash comparison happens on the freshly-fetched body, NOT the existing file's hash — this avoids missing remote-side edits where content_hash would match disk but not the upstream canonical version"
  - "Body extraction defaults to .pages iteration (canonical for 정기보고서 with sections); falls back to to_dict().text/body for short 주요사항보고서; returns '' for genuinely empty filings rather than raising"
  - "Heartbeat sources dict lives outside FrontMatter Pydantic schema — parsed via yaml.safe_load directly; keeps document frontmatter schema clean and the telemetry flexible"
  - "Per-filing isolation via try/except around fetch+hash+write loop body; one failed filing never stops the run (COLL-08)"

patterns-established:
  - "Collector module tree: collectors/{source}/__init__.py exports collect_*; client.py, fetcher.py, writer.py internal"
  - "CollectorConfigError typed exception — error message never includes the secret value (T-3-03)"
  - "Test mock pattern: _FakeFiling + _FakeCorp + _FakeSearchResults dataclasses + state-passing mock_dart fixture"

requirements-completed: [COLL-01, COLL-06, COLL-08, COLL-09]

duration: 12min
completed: 2026-04-17
---

# Phase 03 Plan 02: DART Walking-Skeleton Collector Summary

**Ship the DART collector end-to-end (dart-fss → vault/raw/dart/YYYY/ Markdown with provenance-only frontmatter + trust_level='trusted' + content-hash idempotency + atomic heartbeat), making COLL-01/06/08/09 green without any LLM or DB touch.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-04-17T13:38Z
- **Completed:** 2026-04-17T13:51Z
- **Tasks:** 2
- **Files created:** 7 (4 collector modules + 1 ingest heartbeat + 2 test files)
- **Files modified:** 1 (src/shared/frontmatter.py — trust_level field)

## Accomplishments

- **ProvenanceBlock.trust_level** added as the final field: `Literal["trusted", "semi_trusted", "adversarial"] = "trusted"`. Module docstring extended with D-19 rationale. All 10 Phase 1 `tests/test_frontmatter.py` tests still pass (backward compat: default 'trusted' added under `exclude_none=True` dump → no churn in existing files).
- **`src/ingest/heartbeat.py`** provides atomic `record_source_run(source, stats, heartbeat_path=None)`. Pattern:
  1. Read existing frontmatter YAML directly (sources dict lives outside FrontMatter schema)
  2. Update `sources[source]` block — preserves prior last_success when new run has failures (and vice versa); always updates last_run + docs_processed (= stats['succeeded'])
  3. tempfile + os.replace in same parent directory — POSIX-atomic; failure cleans up .tmp
  4. Other source blocks (krx, news, …) preserved verbatim across per-source updates
- **`src/collectors/dart/`** — 4-module walking skeleton:
  - `client.py`: `get_client()` memoized API-key init via `DART_API_KEY` env var, raises `CollectorConfigError` scrubbed of the key value (T-3-03). `find_corp(corp_code)` thin wrapper for monkeypatching.
  - `fetcher.py`: `list_ab_filings(corp_code, since, max_docs)` translates `since` YYYY-MM-DD → YYYYMMDD and calls `corp.search_filings(pblntf_ty=['A','B'], last_reprt_at='Y')`; slices to `max_docs` (D-03). `fetch_body(filing)` iterates `.pages[*].html` → BeautifulSoup/lxml text extraction, falls back to `to_dict()['text']`/`['body']`, returns `""` for empty. Wrapped with `tenacity.retry(stop_after_attempt(3), wait_exponential(0.3, 2.0))`.
  - `writer.py`: `vault_path_for(filing, corp_code, vault_root)` → `vault_root/raw/dart/YYYY/{rcept_no}_{corp_code}.md`. `compute_body_hash(body)` → sha256(normalize_body(body)) matches `shared.content_hash.compute_content_hash()` output. `write_filing(...)` composes FrontMatter with `trust_level='trusted'`, `date=YYYY-MM-DD` from `rcept_dt[0:4/4:6/6:8]`, `source_url` from `DART_FILING_URL_TMPL`, `fetched_at=datetime.now(UTC)`, computed content_hash → writes via `write_frontmatter` (atomic).
  - `__init__.py`: `collect_dart(corp_code, since, max_docs=100, vault_root=Path('vault'))` — calls `client.get_client()`, `client.find_corp()` (grabs ticker via `.stock_code`), `fetcher.list_ab_filings()`, then per-filing: fetch body → compute new hash → if existing file's frontmatter.content_hash matches new_hash, skip (COLL-08) else write. Per-filing try/except isolates failures (COLL-08). Calls `record_source_run('dart', stats, heartbeat_path=vault_root/'ingested/_status/heartbeat.md')` at end.
- **7 heartbeat tests** (trust_level default/roundtrip/validation + heartbeat create/preserve-sources/failure-path/atomic-crash/preserves-existing/docs_processed-matches-succeeded) pass.
- **8 collector tests** (writes A+B files + max_docs cap + pblntf_ty=['A','B'] assertion + idempotent skip + changed-body rewrite + heartbeat on success + heartbeat on partial failure + AST import-guard for anthropic/openai) pass.
- **CI import-guard (`tests/test_import_guard.py`)** still green — no `anthropic`/`openai` imports anywhere under `src/collectors/` or `src/ingest/`.

## Task Commits

1. **Task 1: ProvenanceBlock.trust_level + atomic heartbeat writer** — `4ab918a` (feat)
2. **Task 2: DART collector (client + fetcher + writer) with idempotent vault write** — `fc6de4e` (feat)

## Files Created/Modified

| File | Purpose |
|------|---------|
| `src/shared/frontmatter.py` (M) | Added `trust_level: Literal['trusted','semi_trusted','adversarial'] = 'trusted'` + `Literal` import; extended docstring with D-19 gate explanation |
| `src/ingest/heartbeat.py` (C) | `record_source_run` atomic writer; `_read_sources` direct YAML parser (sources dict outside FrontMatter schema); `_atomic_write` mirrors Phase 1 pattern |
| `src/collectors/dart/__init__.py` (C) | `collect_dart` orchestration with per-filing isolation |
| `src/collectors/dart/client.py` (C) | `get_client()` + `find_corp()` + `CollectorConfigError` |
| `src/collectors/dart/fetcher.py` (C) | `list_ab_filings` + `fetch_body` (tenacity-retried) + `_strip_html` |
| `src/collectors/dart/writer.py` (C) | `vault_path_for` + `compute_body_hash` + `write_filing` |
| `tests/test_heartbeat.py` (C) | 9 tests (3 trust_level + 6 heartbeat behavior) |
| `tests/test_collect_dart.py` (C) | 8 tests covering COLL-01/06/08/09 with mock dart-fss |

## Body Extraction Strategy (Canonical)

`fetch_body(filing)` resolution order:

1. **`.pages` iteration** — for each `Page`, read `.html` and strip tags. Canonical for 정기보고서 (multi-section bodies). Preserves ordering for downstream D-07 section parsing in Plan 04.
2. **`to_dict()`** fallback — for 주요사항보고서 where `.pages` may be empty or minimal, read `data['text']` or `data['body']`.
3. **Empty string** — return `""` for genuinely empty filings rather than raising (let the upper layer decide whether to record the empty file or skip it).

The retry decorator (`tenacity.retry(stop_after_attempt(3), wait_exponential(multiplier=0.3, max=2.0))`) sits above this chain — transient network flakes during `.pages` hydration get three attempts before falling through to the per-filing try/except in `collect_dart`.

## Heartbeat File Schema

Written at `vault/ingested/_status/heartbeat.md`:

```yaml
---
sources:
  dart:
    last_run: "2026-04-17T13:45:23+00:00"
    last_success: "2026-04-17T13:45:23+00:00"
    docs_processed: 5
  # krx, news, ... populated by later plans
---
<!-- auto-generated; do not edit -->
```

- `last_run` always = UTC ISO timestamp of the most recent invocation
- `last_success` only updated on failure-free runs; preserved from prior run when current has failures
- `last_failure` only updated when `stats['failed']` is non-empty; preserved otherwise
- `docs_processed` = `stats['succeeded']` (not `stats['total']`)
- Atomic via tempfile+os.replace in `vault/ingested/_status/` — on crash the file either stays at its pre-crash contents or never exists (first run)

## Per-Filing Error Isolation (COLL-08)

`collect_dart` wraps each filing's fetch+hash+write in `try/except Exception`. On exception:

- Append `{"doc": str(path), "error": str(exc)}` to `stats["failed"]`
- Continue to the next filing
- Heartbeat still updates — with `last_failure` set and `last_success` preserved from a prior run (if any)

This preserves forward progress: one flaky filing (DART intermittent 500, malformed page HTML, unexpected structure) never blocks the rest. The cost is that `stats["failed"]` must be reviewed per run; Plan 06 `ingest doctor` will surface recurring failure patterns.

## Decisions Made

- **Content-hash comparison on freshly-fetched body, not existing file's hash.** Alternative: trust existing `frontmatter.content_hash`, skip fetch entirely if present. Rejected — remote body could have changed while local file is stale. Fetching first costs one API call per filing per run but guarantees correctness. Phase 3 max_docs=100 stays well under DART's 1000 req/min cap (Pitfall 2).
- **Body extraction via `.pages` before `to_dict()`.** `to_dict()` alone returns metadata (rcept_no, title, dates) rather than text; pages-first preserves section boundaries for Plan 04's D-07 TOC parser. Documented in `fetcher.py` and here for the Plan 04 parser implementer.
- **Heartbeat `sources` dict lives outside FrontMatter Pydantic schema.** Alternative: extend FrontMatter with a `sources` block. Rejected — frontmatter schema describes *document* content, heartbeat is *operational telemetry*. Keeping them separate means future per-source fields (rate-limit counters, last_api_error_code) don't pollute the document schema.
- **Lazy `dart_fss` import inside `client.get_client()`.** Alternative: top-level import. Rejected — lazy import lets tests monkeypatch `client.find_corp` before `dart_fss.get_corp_list()` ever runs, keeping unit tests fully offline.

## Deviations from Plan

None — plan executed exactly as written. All 15 tests (7 heartbeat + 8 collector) pass on first RED→GREEN cycle; no Rule 1/2/3 auto-fixes triggered.

Auto-fixes applied by `ruff --fix` during pre-commit (formatting only, no behavior change):
- `timezone.utc` → `UTC` alias in writer.py (UP017)
- `import os`/unused `real_replace` cleanup in tests (F401/F841)
- `with A: with B:` → combined `with (A, B):` in test_heartbeat.py (SIM117)
- nested `if` → combined `elif ... and ...` in test_collect_dart.py (SIM102)

## Known Stubs

None. No hardcoded empty values flow to any UI surface; `collect_dart` returns a fully-populated stats dict; heartbeat always reflects the latest run.

## Threat Flags

None. Files created/modified stay within the threat model already declared in the plan:
- `client.py` env-var read + error scrubbing matches T-3-03 mitigation
- `heartbeat.py` atomic write matches T-3-05 mitigation
- `writer.py` path construction uses only digit-only fields from dart-fss (T-3-12 mitigated)
- `fetcher.py` treats dart-fss as trusted upstream (T-3-13 accepted) — no new surface introduced

## User Setup Required

`DART_API_KEY` must be set in `.env` or environment for `collect_dart` to actually fetch. Without it, `client.get_client()` raises `CollectorConfigError("DART_API_KEY not set")`. Tests monkeypatch past the key check, so the test suite runs offline.

Smoke test command (when key is available):
```bash
DART_API_KEY=$(cat ~/.secrets/dart_key) uv run --group collectors --group ingest python -c "
from pathlib import Path
from collectors.dart import collect_dart
print(collect_dart('00126380', '2026-01-01', max_docs=5, vault_root=Path('vault')))
"
```
Expected: writes up to 5 Samsung filings under `vault/raw/dart/2026/` and prints a stats dict.

## Next Phase Readiness

- **Plan 03 (resolve_entity integration / CLI scaffolding)** unblocked: trust_level field exists on all future provenance blocks; heartbeat can be surfaced via `stock ingest doctor` later.
- **Plan 04 (ingest worker)** unblocked: DART collector writes real `vault/raw/dart/YYYY/*.md` files with content_hash ready for dedup (INGEST-01) and trust_level ready for D-19 gate. Body-extraction strategy documented here so the parser (`src/ingest/parsers/dart.py`) can assume the `.pages` ordering survived collection.
- **Plan 05 (hybrid_search MCP)** unblocked indirectly: frontmatter schema stable.

---
*Phase: 03-one-company-walking-skeleton*
*Completed: 2026-04-17*

## Self-Check: PASSED

- `src/shared/frontmatter.py` (modified): FOUND — `grep -n 'trust_level: Literal' src/shared/frontmatter.py` returns 1 line
- `src/ingest/heartbeat.py`: FOUND
- `src/collectors/dart/__init__.py`: FOUND
- `src/collectors/dart/client.py`: FOUND
- `src/collectors/dart/fetcher.py`: FOUND
- `src/collectors/dart/writer.py`: FOUND
- `tests/test_heartbeat.py`: FOUND (9 test methods)
- `tests/test_collect_dart.py`: FOUND (8 test methods)
- Commit `4ab918a`: FOUND in git log
- Commit `fc6de4e`: FOUND in git log
- All 31 tests green (8 collector + 9 heartbeat + 10 frontmatter + 4 import-guard)
- `grep -rE '(import|from) (anthropic|openai)' src/collectors/ src/ingest/` returns nothing (COLL-06/07 clean)
