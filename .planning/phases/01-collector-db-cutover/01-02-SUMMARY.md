---
phase: "01-collector-db-cutover"
plan: "01-02"
subsystem: ["cli", "collectors", "tests"]
tags: ["refactor", "signature-only", "wave-0", "cli-gate"]
requires: ["01-01"]
provides:
  - "CLI parser with no --vault-root flag"
  - "5 collect_* functions with keyword-only signature, no vault_root param"
  - "cmd_collect_all entries with inserted/updated keys (default 0)"
  - "tests/test_cli_collect_all.py asserting the new kwargs shape"
affects:
  - "src/cli/__main__.py"
  - "src/cli/commands.py"
  - "src/collectors/dart/__init__.py"
  - "src/collectors/krx/__init__.py"
  - "src/collectors/news/__init__.py"
  - "src/collectors/macro/__init__.py"
  - "src/collectors/kind/__init__.py"
  - "tests/test_cli_collect_all.py"
  - "tests/collectors/conftest.py"
deleted:
  - "tests/test_cli_default_flags.py (R-1 fix)"
tech_stack:
  added: []
  patterns:
    - "_LEGACY_VAULT_ROOT module-local placeholder constant (per-collector)"
    - "keyword-only signature uniformity across all 5 collectors"
key_files:
  created: []
  modified:
    - "src/cli/__main__.py"
    - "src/cli/commands.py"
    - "src/collectors/dart/__init__.py"
    - "src/collectors/krx/__init__.py"
    - "src/collectors/news/__init__.py"
    - "src/collectors/macro/__init__.py"
    - "src/collectors/kind/__init__.py"
    - "tests/test_cli_collect_all.py"
    - "tests/collectors/conftest.py"
  deleted:
    - "tests/test_cli_default_flags.py"
decisions:
  - "R-1: Deleted tests/test_cli_default_flags.py rather than rewriting as negative assertion (file had no other purpose beyond verifying --vault-root default behavior)"
  - "_LEGACY_VAULT_ROOT = Path('vault') (literal 'vault', not '.') — matches the old argparse default and lets writer modules emit at their historic vault-relative paths until Wave 1/2 deletes the call sites"
  - "repo_root resolution: _LEGACY_VAULT_ROOT.parent → Path('.') — preserves portfolio.load semantics when CLI is run from repo root"
  - "dart collector signature converted from positional to keyword-only for uniformity with the other 4 collectors"
metrics:
  duration_minutes: 25
  tasks_completed: 3
  files_modified: 9
  files_deleted: 1
  test_pass_count: 15
  test_fail_count: 0
completed_date: "2026-05-29"
---

# Phase 1 Plan 01-02: CLI cleanup + collector signature strip Summary

**One-liner:** Strips `--vault-root` from the argparse parser and from all 5 collector entrypoint signatures while preserving collector body behavior via a per-module `_LEGACY_VAULT_ROOT` placeholder; bodies still write Markdown via `writer.*` until Wave 1/2 plans replace them.

## Files Modified

| File                                       | Change                                                                                                                                                |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/cli/__main__.py`                      | Drop `parser.add_argument("--vault-root", ...)`; document removal rationale in module docstring                                                       |
| `src/cli/commands.py`                      | Drop `vault_root=Path(args.vault_root)` from every `cmd_collect_*`; drop `vault_root` key from `cmd_collect_all` kwargs; add `inserted`/`updated` keys (default 0) to per-source entry; remove unused `from pathlib import Path` |
| `src/collectors/dart/__init__.py`          | Convert `collect_dart` to keyword-only `(*, corp_code, since, max_docs=100, engine=None)`; remove `vault_root: Path` param; replace body refs with `_LEGACY_VAULT_ROOT`; docstring notes 01-07 removal |
| `src/collectors/krx/__init__.py`           | Drop `vault_root: Path` param from keyword-only signature; `repo_root = _LEGACY_VAULT_ROOT.parent`; docstring notes 01-04 removal                     |
| `src/collectors/news/__init__.py`          | Drop `vault_root: Path` param from keyword-only signature; same repo_root resolution; docstring notes 01-06 removal                                   |
| `src/collectors/macro/__init__.py`         | Drop `vault_root: Path` param from keyword-only signature; engine remains Optional+unused (noqa retained per plan); docstring notes 01-03 removal     |
| `src/collectors/kind/__init__.py`          | Drop `vault_root: Path` param from keyword-only signature; same repo_root resolution; `_read_heartbeat_extra` consumes `_LEGACY_VAULT_ROOT`; docstring notes 01-05 removal |
| `tests/test_cli_collect_all.py`            | Drop `["--vault-root", str(tmp_path)]` from every CA1..CA8 argv; drop unused `tmp_path` fixture parameter; add `assert "vault_root" not in kwargs` checks (CA1, CA2); add `entry["inserted"]/["updated"] == 0` checks (CA7); rewrite CA9 fake signature drop `vault_root` |
| `tests/collectors/conftest.py`             | Add docstring note marking `vault_tmp` DEPRECATED after Phase 1 Wave 2 (deletion in 01-09)                                                            |
| `tests/test_cli_default_flags.py`          | **DELETED** (R-1) — file existed solely to verify the removed `--vault-root` default flag behavior                                                    |

## Signature Delta

| Collector       | Old signature                                                                                                                                  | New signature                                                                                                |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `collect_dart`  | `(corp_code: str, since: str, max_docs: int = 100, vault_root: Path = Path("."), engine: Engine \| None = None)` (positional)                  | `(*, corp_code: str, since: str, max_docs: int = 100, engine: Engine \| None = None)` (keyword-only)         |
| `collect_krx`   | `(*, vault_root: Path = Path("."), engine: Engine \| None = None, since: str \| None = None)`                                                  | `(*, engine: Engine \| None = None, since: str \| None = None)`                                              |
| `collect_news`  | `(*, vault_root: Path = Path("."), engine: Engine, since: str \| None = None, max_per_feed: int = 100)`                                        | `(*, engine: Engine, since: str \| None = None, max_per_feed: int = 100)`                                    |
| `collect_macro` | `(*, vault_root: Path = Path("."), engine: Engine \| None = None, series: list[str] \| None = None, catalog_path: Path \| None = None)`        | `(*, engine: Engine \| None = None, series: list[str] \| None = None, catalog_path: Path \| None = None)`    |
| `collect_kind`  | `(*, vault_root: Path = Path("."), engine: Engine \| None = None, since: str \| None = None, enable_kind_scrape: bool = False)`                | `(*, engine: Engine \| None = None, since: str \| None = None, enable_kind_scrape: bool = False)`            |

All 5 are now uniformly keyword-only with no `Path` parameter.

## `_LEGACY_VAULT_ROOT` Placement

| Collector file                              | Line | Value             | Removal plan |
| ------------------------------------------- | ---- | ----------------- | ------------ |
| `src/collectors/dart/__init__.py`           | 28   | `Path("vault")`   | 01-07        |
| `src/collectors/krx/__init__.py`            | 26   | `Path("vault")`   | 01-04        |
| `src/collectors/news/__init__.py`           | 28   | `Path("vault")`   | 01-06        |
| `src/collectors/macro/__init__.py`          | 52   | `Path("vault")`   | 01-03        |
| `src/collectors/kind/__init__.py`           | 46   | `Path("vault")`   | 01-05        |

Each placeholder is documented inline (`# Phase 1 transition placeholder; removed in 01-XX`) and called out in the module docstring's "PHASE 1 TRANSITION" preface.

## `tests/test_cli_default_flags.py` Decision

**DELETED** (per R-1, R-3 from PLAN-VERIFICATION.md).

Both tests in that file were tightly coupled to the removed flag:
- `test_default_vault_root_help_mentions_vault` asserted `"default: vault" in help_text` — impossible after Task 1.
- `test_default_vault_root_resolves_portfolio` asserted that the argparse default `'vault'` propagated through to the krx fake's `vault_root` kwarg — impossible after Tasks 1+2 (the kwarg is gone).

A negative-assertion rewrite (`"vault-root" not in help_text`) would have duplicated coverage already provided by the executor's `<verification>` block (which runs `uv run stock --help | grep -c "vault-root" == 0`). Deletion was the cleanest path.

## Test Results

| Test target                              | Result        | Notes                                                  |
| ---------------------------------------- | ------------- | ------------------------------------------------------ |
| `tests/test_cli_collect_all.py`          | 11 passed     | All CA1..CA10 + CA1b                                   |
| `tests/test_cli_default_flags.py`        | (no items)    | File deleted per R-1                                   |
| `tests/test_import_guard.py`             | 4 passed      | No anthropic/openai imports in `src/collectors/`       |
| `tests/collectors/` collect-only         | 84 collected  | No ImportError; per-source execution is Wave 1/2 owned |

Overall verification:
- `stock --help`: `grep -c "vault-root"` → 0 (PASS)
- `argparse` namespace: `vault_root` attribute absent after `parse_args(['collect', 'macro'])` (PASS)
- `inspect.signature()` introspection: `vault_root` absent from all 5 collector signatures (PASS)
- `_LEGACY_VAULT_ROOT == Path("vault")` constant exists in all 5 collector modules (PASS)

## Commits

| Task | Hash      | Subject                                                                  |
| ---- | --------- | ------------------------------------------------------------------------ |
| 1    | `2044ac7` | refactor(01-02): remove --vault-root from CLI parser and dispatch        |
| 2    | `1814124` | refactor(01-02): strip vault_root from 5 collector __init__.py signatures|
| 3    | `41aac2f` | refactor(01-02): update CLI tests + delete obsolete --vault-root flag test |

## Deviations from Plan

**None for in-scope work.** The plan was executed exactly as written — with the R-1 / R-3 fixes from `PLAN-VERIFICATION.md` folded into Task 3 as specified.

Observed parallel-agent activity (not deviations, just noted for transparency):
- `uv.lock` was modified concurrently by the sibling 01-01 executor's `uv sync`. Not staged into any of my commits.
- `src/db/migrations/versions/0006_phase01_domain_tables.py` and `tests/db/test_migration_0006.py` and `tests/conftest.py` were created/modified by the sibling 01-01 executor. Not staged into any of my commits — files are disjoint per the wave-0 plan analysis (PLAN-VERIFICATION § Dependency Graph).

## Known Stubs

None introduced by this plan. The `_LEGACY_VAULT_ROOT` constants are explicit transitional shims, not stubs — they preserve behavior of `writer.*` call sites that Wave 1/2 plans replace wholesale, and each one is tagged with its removal plan ID. The `# noqa: ARG001` on `collect_macro`'s `engine` parameter is retained per plan instructions; 01-03 removes it when macro starts using `engine`.

## Threat Flags

None — no new network surface, no new auth path, no new file-write boundary. This plan removes a flag and shifts a placeholder constant; the writer modules' on-disk behavior is unchanged.

## Self-Check: PASSED

- src/cli/__main__.py: FOUND (modified)
- src/cli/commands.py: FOUND (modified)
- src/collectors/dart/__init__.py: FOUND (modified)
- src/collectors/krx/__init__.py: FOUND (modified)
- src/collectors/news/__init__.py: FOUND (modified)
- src/collectors/macro/__init__.py: FOUND (modified)
- src/collectors/kind/__init__.py: FOUND (modified)
- tests/test_cli_collect_all.py: FOUND (modified)
- tests/collectors/conftest.py: FOUND (modified)
- tests/test_cli_default_flags.py: ABSENT (deleted per R-1, verified)
- commit 2044ac7 (Task 1): FOUND in git log
- commit 1814124 (Task 2): FOUND in git log
- commit 41aac2f (Task 3): FOUND in git log
