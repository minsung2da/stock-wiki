---
phase: 04-multi-source-collector-coverage
plan: 06
subsystem: cli
tags: [cli, orchestration, collectors, phase-4, D-18, D-19, D-20, D-21]
requires: [04-02, 04-03, 04-04, 04-05]
provides:
  - "stock collect {krx,news,macro,kind} subcommands"
  - "stock collect all orchestrator with per-source isolation"
  - "stderr JSON report schema (run_at + per-source status/docs_processed/elapsed_ms)"
affects:
  - src/cli/__main__.py
  - src/cli/commands.py
  - tests/test_cli_collect_all.py
tech_added: []
patterns:
  - "Lazy-import _dispatch() dict for cheap monkeypatch-based testing"
  - "Comma-separated --sources with argparse-free manual validation (argparse choices would require splitting first)"
key_files:
  created:
    - tests/test_cli_collect_all.py
  modified:
    - src/cli/__main__.py
    - src/cli/commands.py
decisions:
  - "Implemented _dispatch() helper (plan-specified) instead of direct module imports so tests patch a single boundary symbol"
  - "Exit code 2 reserved for unknown --sources (D-21 fail-fast); exit 1 reserved for in-run errors/partials (D-20)"
requirements: [COLL-02, COLL-03, COLL-04, COLL-05]
metrics:
  tasks_completed: 1
  tests_added: 11
  duration_min: ~18
  completed_utc: 2026-04-18
---

# Phase 4 Plan 06: Multi-Source CLI Orchestration Summary

Wired four Phase-4 collectors (`krx`, `news`, `macro`, `kind`) into argparse subcommands alongside Phase-3 `stock collect dart` (unchanged), plus `stock collect all` orchestrator with in-process try/except isolation, stderr JSON report, and three-tier exit codes — proving Phase 4 Success Criterion #5 (one collector failing does not block siblings).

## What Changed

### `src/cli/__main__.py`
Added five `collect_subs.add_parser(...)` blocks after the existing `dart` subparser:
- `krx` — `--since`
- `news` — `--since`, `--max-per-feed`
- `macro` — `--series`
- `kind` — `--since`
- `all` — `--sources` (default `krx,news,macro,kind`), `--since`

Imports widened to pull the five new `cmd_collect_*` handlers from `cli.commands`.

### `src/cli/commands.py`
- `_KNOWN_SOURCES = ("dart","krx","news","macro","kind")`
- `_DEFAULT_ALL = ("krx","news","macro","kind")` (dart excluded per D-18)
- `_dispatch()` — lazy-imports every collector and returns a name→callable dict; tests patch this single symbol to inject fakes
- `_engine()` — lazy-wraps `db.engine.get_engine()`; also patched in tests
- `cmd_collect_{krx,news,macro,kind}` — thin handlers; exit 1 when `stats["failed"]` non-empty
- `cmd_collect_all` — orchestrator:
  - Validates `--sources` against `_KNOWN_SOURCES`; unknown → exit 2 (D-21)
  - Loops requested sources sequentially inside try/except (D-19)
  - Records `{status, docs_processed, elapsed_ms}` per source; adds `error` on exception, `failed_count` on partial
  - `status ∈ {"ok","partial","error"}` — partial when collector returned non-empty `failed` list
  - Emits single-line JSON to **stderr** (D-20); stdout stays clean for composability
  - Exit 0 only when every source is `"ok"`; exit 1 if any `error`/`partial`

`cmd_collect_dart` unchanged (D-18 backward compat verified by `test_CA9`).

### `tests/test_cli_collect_all.py` (new, 11 tests)
| Test | Verifies |
|------|----------|
| CA1 / CA1b | `collect krx` exit 0 (ok) / exit 1 (failed non-empty) |
| CA2 | `--sources=krx,news` runs exactly those two in order |
| CA3 | `--sources=krx,nope` → exit 2, zero collectors invoked |
| CA4 | default run = `[krx,news,macro,kind]`, dart excluded |
| CA5 | collector raising RuntimeError → caught; others run; exit 1; JSON carries `status=error` + `error` message |
| CA6 | `failed` list non-empty → `status=partial`; exit 1 |
| CA7 | full-success schema: `run_at`, per-source `{status,docs_processed,elapsed_ms}` |
| CA8 | stderr JSON is machine-parseable |
| CA9 | Phase-3 `collect dart --corp-code --since --max-docs` signature preserved |
| CA10 | `collect --help` lists all six subparsers |

Isolation is accomplished by `monkeypatch.setattr(cli.commands, "_dispatch", lambda: {...})` + `_engine` — no real collectors, no DB, no network.

## Key Decisions

1. **`_dispatch()` helper over direct imports.** The plan specified this exact shape (`grep "_SOURCE_DISPATCH\|_dispatch"` acceptance criterion). The alternative — patching each `collectors.<src>.collect_<src>` directly as in the legacy `test_cli.py::C2` pattern — would force tests to know the attribute path of each collector and fail whenever lazy-import ordering changes. Single boundary symbol wins.
2. **Manual `--sources` validation vs argparse `choices=`.** argparse `choices` requires the value to be a list; it cannot natively validate comma-separated tokens. Manual split + membership check is the simplest correct implementation and returns exit 2 with a human-readable error.
3. **Exit 2 reserved for CLI misuse (unknown source)**; exit 1 for in-run faults. Matches the Phase-3 convention where `ingest rebuild` user-abort also returns 2.
4. **Report on stderr, stats on stdout.** D-20 mandates stderr for the aggregate report. Individual subcommands still print their collector stats to stdout so shell pipelines can grep single-source JSON without stderr noise.

## Deviations from Plan

None. Plan executed as written:
- `_dispatch()` boundary matches acceptance criterion grep
- All 10 plan-specified test behaviors implemented (split CA1 into CA1+CA1b for clarity — 11 tests total vs 9 in plan)
- Exit code mapping matches D-20 (0/1) + added D-21 (2 for unknown source)
- Backward-compat `collect dart` covered by CA9

## Verification Evidence

```bash
$ uv run pytest tests/test_cli_collect_all.py -x -q
...........                                                              [100%]
11 passed in 2.66s

$ uv run pytest tests/test_cli.py tests/test_import_guard.py -x -q
...............                                                          [100%]
15 passed in 4.77s

$ uv run pytest tests/ -k "frontmatter or heartbeat or dart or portfolio or entity_alias or krx or macro or news or kind or cli or import_guard" -x -q --ignore=tests/e2e
177 passed, 1 skipped, 130 deselected, 1 warning in 53.73s

$ uv run stock collect --help | grep -E "dart|krx|news|macro|kind|all"
usage: stock collect [-h] {dart,krx,news,macro,kind,all} ...
  {dart,krx,news,macro,kind,all}
    dart                Collect DART filings (COLL-01)
    krx                 Collect KRX OHLCV + flow + short (COLL-02)
    news                Collect 한경/이데일리 news (COLL-03)
    macro               Collect ECOS+FRED macro (COLL-04)
    kind                Collect KIND events (COLL-05)
    all                 Run collectors with per-source isolation (D-18..D-21)
```

## Known Stubs

None. Every CLI handler dispatches to a real, implemented collector function (Phase 4 Plans 02-05). The `_dispatch()` indirection is a test seam, not a stub.

## Self-Check: PASSED

- FOUND: tests/test_cli_collect_all.py (11 tests)
- FOUND: src/cli/commands.py (`_dispatch`, `cmd_collect_all`, `cmd_collect_{krx,news,macro,kind}`)
- FOUND: src/cli/__main__.py (all six `collect_subs.add_parser` blocks incl. `dart` backward compat)
- FOUND: commit 6e77d46 (`git log --oneline | grep 6e77d46` confirms)
- FOUND: `stock collect --help` lists all six subparsers
