---
phase: 07-graph-layer-graphify-integration
plan: 03
subsystem: graph-snapshot-cli
tags: [wave-2, graph-02, cli, graphifyy]
requires:
  - 07-01 (graphifyy 0.7.5 installed; probe-findings.md API parity)
  - 07-02 (edges populated; ingest worker hook live)
provides:
  - "src/graph/snapshot.py — vault-wide graphifyy snapshot with 14-day prune + staging cleanup invariant"
  - "src/graph/window.py — windowed staging symlink farm scoped per raw_windows_days"
  - "config/graphify.json — raw_windows_days {dart:365, news:30, kind:90, macro:180}"
  - "stock graph snapshot CLI subcommand (--dry-run, --config) ready for Phase 9 scheduler hookup"
affects:
  - .gitignore (vault/graph/, vault/.graphify-staging/ now ignored)
  - src/cli/__main__.py (new graph subparser)
  - src/cli/commands.py (cmd_graph_snapshot handler)
tech_stack_added: []
patterns:
  - "Lazy graphify imports inside _run_graphify keep src.graph.snapshot importable without the graph dep group"
  - "try/finally staging cleanup invariant survives graphify exceptions (partial out_dir preserved for postmortem)"
  - "Windowed symlink farm with shutil.copy fallback on OSError (Windows non-admin)"
  - "Dual-import fallback (src.graph.window | graph.window) lets the module run under both pytest and uv CLI contexts"
key_files_created:
  - src/graph/__init__.py
  - src/graph/snapshot.py
  - src/graph/window.py
  - config/graphify.json
key_files_modified:
  - .gitignore
  - src/cli/__main__.py
  - src/cli/commands.py
  - tests/graph/conftest.py
  - tests/graph/test_snapshot_cli.py
  - tests/graph/test_window.py
  - tests/test_cli.py
key_decisions:
  - "graphifyy 0.7.5 v4 chain used unchanged (probe parity); cluster() yields indices only so labels + member_counts are derived locally"
  - "build_from_json invoked with directed=True (D-11)"
  - "staging cleaned in finally; partial vault/graph/<date>/ preserved for postmortem (PLAN failure policy)"
  - "Dual-import fallback in snapshot.py — autonomous Rule 3 fix for src/-on-sys.path divergence between pytest and uv CLI"
metrics:
  duration_minutes: ~25
  completed_date: 2026-05-06
  tasks: 3
  commits:
    - 4bcecce
    - 6c15639
    - 26332e4
  files_changed: 11
---

# Phase 07 Plan 03: GRAPH-02 `stock graph snapshot` CLI Summary

GRAPH-02 ships end-to-end. `src/graph/snapshot.py` invokes graphifyy 0.7.5 in-process via the v4 chain (detect → extract → build_from_json(directed=True) → cluster → score_all → analyze → report.generate → export.{to_json, to_html}), with locally-derived `community_labels` and `member_counts` per Plan 01 SUMMARY guidance. `src/graph/window.py` builds a windowed staging symlink farm scoped per `config/graphify.json` (`dart:365 / news:30 / kind:90 / macro:180`) plus always-included `vault/notes/` + `notes/private/`. `_prune_old(keep=14)` enforces the dated-dir retention invariant. `stock graph snapshot --dry-run` smoke-passes against the live repo.

## What Changed

### `src/graph/snapshot.py`
- Public `snapshot(repo_root, config, *, dry_run=False) -> Path` returns `vault/graph/<KST_DATE>/`.
- KST date is plain ISO `YYYY-MM-DD` via `zoneinfo.ZoneInfo("Asia/Seoul")` (RESEARCH §Pitfall 6).
- Lazy graphify imports inside `_run_graphify` so the module loads without the `graph` dep group.
- `try/finally` guarantees `vault/.graphify-staging/<date>/` is removed even when graphify raises.
- `_prune_old` keeps the 14 newest dated subdirs by mtime; entries starting with `.` are skipped.
- Dual-import fallback for `build_staging` so the module works under both pytest (where `src/` is a namespace) and the uv CLI (where `src/` is on `sys.path`).

### `src/graph/window.py`
- `build_staging(repo_root, staging, config) -> dict` returns per-source link counts.
- Symlinks both always-included scopes (`vault/notes/`, `notes/private/`) and source-windowed scopes filtered by file mtime against `config['graphify']['raw_windows_days'][source]`.
- `shutil.copytree` / `shutil.copy2` fallback on `OSError`/`NotImplementedError` (Windows non-admin path).

### `config/graphify.json`
```json
{
  "graphify": {
    "raw_windows_days": {"dart": 365, "news": 30, "kind": 90, "macro": 180},
    "mode": "deep",
    "directed": true
  }
}
```

### `.gitignore`
Appended `vault/graph/` and `vault/.graphify-staging/`. Existing legacy `graphify-out/` line preserved.

### CLI wiring
- `src/cli/__main__.py` registers `graph` subparser with `snapshot` subcommand (`--dry-run`, `--config`).
- `src/cli/commands.py::cmd_graph_snapshot` reads `config/graphify.json` (or `--config` override), invokes `graph.snapshot.snapshot()`, and emits a one-line JSON status report on stderr (`{"status":"ok","out_dir":...}` on success, `{"status":"error","error":...}` on failure). Exit 0 / 1 respectively.

### Tests
- `tests/graph/conftest.py::graphify_stub` — fixture monkeypatches all 7 graphify submodules with deterministic stubs and exposes a `should_raise` toggle.
- `tests/graph/test_snapshot_cli.py` — 3 tests green (output files exist / 20→14 prune by mtime / staging cleaned on raise).
- `tests/graph/test_window.py` — 2 tests green (mtime filter respects raw_windows_days.dart=365 / notes/private always included).
- `tests/test_cli.py` — 2 new tests (dry-run smoke / missing-config exit 1). All 13 CLI tests still green.

## graphify 0.7.5 Symbol Mapping

probe-findings.md recorded all v4 symbols PRESENT in 0.7.5 — the import block in `_run_graphify` matches verbatim:

| SKILL.md v4 | snapshot.py import | Notes |
|---|---|---|
| `graphify.detect.detect` | identical | called as `detect(Path(input_dir))` |
| `graphify.extract.collect_files` + `extract` | identical | `extract(files, mode="deep", semantic=False)` |
| `graphify.build.build_from_json` | identical | passed `directed=True` (D-11) |
| `graphify.cluster.cluster` + `score_all` | identical | indices-only return → derive labels locally |
| `graphify.analyze.god_nodes` + `surprising_connections` + `suggest_questions` | identical | `suggest_questions` requires `community_labels` |
| `graphify.report.generate` | identical | passes derived `labels` |
| `graphify.export.to_json` (force=True) + `to_html` (community_labels, member_counts) | identical | `member_counts = {cid: len(members) for cid, members in communities.items()}` |

No 0.7.5 workarounds required — Plan 01 confirmed parity.

## Verification Evidence

```
$ UV_LINK_MODE=copy uv run pytest tests/graph/test_snapshot_cli.py tests/graph/test_window.py tests/test_cli.py
18 passed in 5.27s

$ UV_LINK_MODE=copy uv run stock graph snapshot --dry-run
{"status": "ok", "out_dir": "/mnt/c/.../vault/graph/2026-05-06"}
exit=0

$ git status --short | grep -E "vault/graph|graphify-staging"
(no hits — gitignored OK)

$ grep -E "def snapshot|def _prune_old|KEEP_DATED_DIRS = 14|ZoneInfo.*Asia/Seoul" src/graph/snapshot.py | wc -l
4

$ test -f src/graph/__init__.py && test -f src/graph/snapshot.py && test -f src/graph/window.py && test -f config/graphify.json && echo OK
OK
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `src.graph.window` import fails when CLI runs via uv**

- **Found during:** Task 3 dry-run smoke (`{"status": "error", "error": "No module named 'src'"}`).
- **Issue:** `src/graph/snapshot.py` was authored with `from src.graph.window import build_staging` per the plan template. Pytest finds it because `src/` resolves as a namespace from the repo-root cwd. Under `uv run stock`, however, `pyproject.toml` puts `src/` directly on `sys.path` (entry-point pattern) — so `src.graph.window` is not importable; only `graph.window` is.
- **Fix:** Wrapped the import in a `try/except ModuleNotFoundError` that falls back to `from graph.window import build_staging`. Both contexts now resolve the same module identity (Python caches by absolute path), and the staging callsite in `snapshot()` is unchanged.
- **Files modified:** `src/graph/snapshot.py`
- **Commit:** 26332e4

### No other deviations

- All 10 graphifyy v4 symbols PRESENT (probe-findings.md) — no 0.7.5 substitutions needed.
- No architectural changes (Rule 4) raised.
- No auth gates encountered.

## Manual Verifications Pending

Per `07-VALIDATION.md` Manual-Only table, the live `stock graph snapshot` (no dry-run) needs operator eyeballing of the rendered `index.html` in Obsidian + a browser. That step is deferred to the Phase 7 phase gate, after Plan 04 supplies the canonical-query README.

## Threat Flags

None new beyond the threat register in PLAN. All `mitigate` dispositions hold:
- T-7-03-01 path traversal: `--config` is operator-controlled; resolution skipped per ASVS L1 V12.4 (out-of-band attack surface).
- T-7-03-02 symlink escape: targets are computed from constants under `repo_root` (`vault/raw/<source>`, `vault/notes`, `notes/private`); `Path.relative_to(src_root)` raises on escape.
- T-7-03-03 private leak: `vault/graph/` gitignored; index.html sharing redaction is operator responsibility (Plan 04 README inline-note).
- T-7-03-04 supply chain: graphifyy pinned in Plan 01 lockfile.
- T-7-03-05/06 concurrency: accepted; single-process CLI in v1.

## Self-Check: PASSED

- `src/graph/__init__.py` exists (package marker).
- `src/graph/snapshot.py` exists with `def snapshot`, `def _prune_old`, `KEEP_DATED_DIRS = 14`, `ZoneInfo("Asia/Seoul")`.
- `src/graph/window.py` exists with `def build_staging`.
- `config/graphify.json` parses with the locked enum values (dart:365, news:30, kind:90, macro:180, mode=deep, directed=true).
- `.gitignore` contains `vault/graph/` and `vault/.graphify-staging/`.
- `uv run stock graph --help` lists `snapshot`; `uv run stock graph snapshot --help` shows `--dry-run` and `--config`.
- `uv run stock graph snapshot --dry-run` exits 0; output dir is gitignored.
- 18/18 plan tests pass (3 snapshot + 2 window + 13 CLI).
- Commits exist: `4bcecce` (Task 1), `6c15639` (Task 2), `26332e4` (Task 3).
