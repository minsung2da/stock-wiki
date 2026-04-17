---
phase: quick-260418-asr
plan: 01
subsystem: collectors.dart + db.entity + ingest.worker
tags: [bugfix, phase-3-followup, collectors, entity-seeding, retry-hardening]
dependency_graph:
  requires: [phase-03 walking skeleton]
  provides: [upsert_entity helper, robust DART retry, vault-root alignment]
  affects: [stock collect dart CLI, resolve_entity downstream, MCP search]
tech_stack:
  added: [urllib3.exceptions.ProtocolError handling, tenacity before_sleep_log]
  patterns:
    - "SELECT-then-INSERT idempotency for entity_aliases (Pitfall 5)"
    - "Per-task regex validation before SQL bind (T-Q1-01)"
key_files:
  created:
    - tests/test_dart_fetcher_retry.py
    - tests/test_entity_upsert.py
  modified:
    - src/collectors/dart/__init__.py
    - src/collectors/dart/fetcher.py
    - src/cli/__main__.py
    - src/cli/commands.py
    - src/db/entity.py
    - src/ingest/worker.py
    - tests/test_cli.py
decisions:
  - "Default vault_root Path('.'): repo root IS the Obsidian vault root (Phase 1 D-01/D-02). Collector and CLI now agree."
  - "Retry 5x with 1-30s exponential backoff. Retry only ConnectionError, ChunkedEncodingError, and urllib3 ProtocolError — programming bugs (ValueError, RuntimeError) raise on attempt 1."
  - "entity_aliases upsert via SELECT-then-INSERT, NOT ON CONFLICT. Pitfall 5 forbids a unique key on (corp_code, kind, value) because KRX recycles tickers — ON CONFLICT would fail at the DB."
  - "collect_dart gains optional engine kwarg; entity seeding is opt-in at the call site. Preserves backward-compat with 8 existing offline-mocked collector tests."
  - "Upsert failures are swallowed into stats.warnings — never fail a filing collect because of DB seeding trouble (defense-in-depth for crons)."
  - "CLI commands.py wires engine=get_engine() so production `stock collect dart` seeds entities; unit tests use sentinel_engine objects."
metrics:
  duration: "~25 min"
  completed: "2026-04-17"
  tasks: 3
  commits: 4
  new_tests: 14
  total_tests_passing: 183
---

# Quick Task 260418-asr: Fix Phase 3 E2E Bugs Summary

One-liner: Fixed three latent bugs surfaced by JUDGE-04 Samsung 180-day E2E — collector writing to stale vault/ subdir, fetcher dying on large 사업보고서 RemoteDisconnected, and entities table never seeded so ticker lookup returned INVALID_TICKER.

## Scope

Bugfix against existing Phase 3 walking-skeleton behavior. No new requirements, no schema changes. All three fixes share a single focus: restore end-to-end usability of `stock collect dart → stock ingest run → mcp search(ticker=...)`.

## Task 1: Bug A — Vault path consistency (e93ed65)

**What changed:**
- `collect_dart(..., vault_root=Path("vault"))` → `vault_root=Path(".")`
- `stock --vault-root` default `"vault"` → `"."`
- Aligns with Phase 1 D-01/D-02 (repo root IS the Obsidian vault root)
- Dropped untracked stale `vault/raw/dart/2026/*.md` files from the E2E smoke run — user can re-collect via `stock collect dart` which now writes to `./raw/dart/YYYY/`

**Tests:** 31 pass (8 collect_dart + 17 ingest_worker + 6 heartbeat). No new tests added — existing tests already passed `vault_root=tmp_path` and expected `tmp_path/raw/dart/...`, so the default change was silently compatible.

**Key decision:** Existing E2E-collected files in `vault/raw/dart/2026/` were untracked (not in git — raw/ is the committed location by design from Phase 3 .gitignore), so no `git mv` history preservation was needed. User's DB rows referencing the old `vault_path` will be rebuilt by the next `stock ingest rebuild --yes` as anticipated in plan context.

## Task 2: Bug B — Fetcher retry hardening (e7d8d7f)

**What changed:**
- `stop_after_attempt(3)` → `stop_after_attempt(5)`
- `wait_exponential(multiplier=0.3, max=2.0)` → `wait_exponential(multiplier=1.0, min=1.0, max=30.0)`
- Added explicit `retry_if_exception_type((ConnectionError, ChunkedEncodingError, ProtocolError))`
- Added `before_sleep_log(_log, WARNING)` for observability

**Tests added (tests/test_dart_fetcher_retry.py):**
- R1: 5-attempt exhaustion on ConnectionError
- R2: ProtocolError (RemoteDisconnected wrapper) succeeds on 3rd attempt
- R3: WARNING logged per retry
- R4: Non-retryable (ValueError) raises on 1st attempt — no retry loop
- R5: ChunkedEncodingError retried (chunked transfer truncation)

All 5 new + 8 existing collector tests pass (13 total).

**Key decisions:**
- Chose `urllib3.exceptions.ProtocolError` because that's what wraps `http.client.RemoteDisconnected` observed in JUDGE-04 logs (dart-fss → requests → urllib3 → http.client chain).
- Did NOT inject per-request HTTP timeout — dart-fss 0.4.x provides no session-timeout knob; monkeypatching internals is out of scope for a bugfix. Tenacity stop_after_delay remains the safety net if needed in Phase 4.
- `RuntimeError` deliberately excluded from retry set — the existing `test_collector_records_heartbeat_on_failure` test raises RuntimeError and expects one-shot failure recording, which now works by design.

## Task 3: Bug C — Auto-seed entities on filing write (e6895b9 + e23cbc1)

**What changed:**
- New helper `db.entity.upsert_entity(engine, corp_code, canonical_name, ticker, market='KOSPI')`:
  - `entities`: INSERT ... ON CONFLICT (corp_code) DO UPDATE SET canonical_name, current_ticker
  - `entity_aliases`: SELECT-then-INSERT (no unique key — Pitfall 5 KRX ticker recycling)
  - Regex-validated corp_code + ticker before any SQL bind (T-Q1-01 mitigation)
  - All SQL via `text()` + bind params, no f-string SQL (WR-03)
- `collect_dart` gains optional `engine: Engine | None = None` param. When provided AND `stats["succeeded"] > 0`, calls `upsert_entity` once per run (not per filing — corp identity is constant across a corp's filings).
- `cli/commands.py::cmd_collect_dart` wires `engine=get_engine()` so production CLI seeds entities automatically (e23cbc1 follow-up).

**Tests added (tests/test_entity_upsert.py):**
- E1: upsert → resolve_entity(ticker) round-trip
- E2: Two identical upserts produce exactly 1 entity + 1 alias (idempotent)
- E3: canonical_name update re-applies; alias unchanged
- E4: None ticker tolerated (entities row written, no alias)
- E5: collect_dart(engine=pg_clean) seeds entities as byproduct of success
- E6: collect_dart(engine=None) is DB-inert (backward-compat)
- E_invalid_corp_code / E_invalid_ticker / E_no_success_no_seed (3 gate tests)

All 9 new + 9 existing resolve_entity + 8 existing collect_dart + 11 CLI tests pass (37 total, counting Task 1 carry-over).

**Key decisions:**
- SELECT-then-INSERT over ON CONFLICT because Pitfall 5 deliberately omitted a unique constraint on (corp_code, kind, value). ON CONFLICT would raise "no unique constraint matching specification" at runtime.
- Upsert is non-fatal: wrapped in try/except, failure appends to `stats["warnings"]`. A DB hiccup must never orphan the on-disk filings — Obsidian can still serve them, and `stock ingest rebuild` can re-seed.
- Lazy import `from db.entity import upsert_entity` inside the conditional branch — keeps `collectors/dart/__init__.py` import-time light and avoids pulling SQLAlchemy when the collector is imported for non-DB tests.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocker] CLI test_C2 broken by engine wiring (e23cbc1)**
- **Found during:** Task 3 completion (wiring `get_engine()` into `cmd_collect_dart`)
- **Issue:** Existing `test_C2_collect_dart_delegates` did not monkeypatch `get_engine`, causing `KeyError: 'DATABASE_URL'` after wiring.
- **Fix:** Updated test to monkeypatch `db.engine.get_engine` with a sentinel object and added an `engine=` kwarg to the fake collect_dart.
- **Files modified:** src/cli/commands.py, tests/test_cli.py
- **Commit:** e23cbc1

No other deviations — the other 182 tests stayed green without changes.

### Migration Outcome

- Stale `vault/` directory contained only untracked E2E artifacts (2 .md filings + 1 heartbeat). Deleted via `rm -rf vault/` — no git history to preserve.
- Committed `raw/.keep` + `ingested/_status/.keep`-equivalent state remains unchanged.
- Post-migration: `find . -maxdepth 2 -type d -name vault` returns nothing. `ls raw/` is empty awaiting next collect run.

## Verification

**Final full fast test suite (excluding `slow` bge-m3 marker):**
```
183 passed, 8 deselected, 14 warnings in 60.38s
```

**Verification greps (all returning empty = pass):**
- `grep -rn 'Path("vault")' src/` → nothing
- `grep -nE 'f"INSERT|f"SELECT|f"UPDATE|f"DELETE' src/db/entity.py src/collectors/dart/*.py src/ingest/worker.py` → nothing
- `grep -rE '(import|from) (anthropic|openai)' src/collectors/ src/ingest/ src/db/` → nothing
- `grep -n 'stop_after_attempt(5)\|ProtocolError\|ChunkedEncodingError\|retry_if_exception_type' src/collectors/dart/fetcher.py` → 4 matches confirmed

## Deferred

- **Live smoke test (DART_API_KEY)**: user should run the Samsung 5-filing end-to-end re-test per plan `<verification>` section — agent did not execute because `~/.secrets/dart_key` is a user-local secret, not in the session environment. Smoke sequence:
  1. `uv run stock collect dart --corp-code=00126380 --since=$(date -d '180 days ago' +%Y-%m-%d) --max-docs=5` — verify files land at `raw/dart/...`
  2. `uv run stock ingest rebuild --yes --force-reembed` — re-index to flush stale `vault/raw/...` vault_path rows
  3. Python: `from stock_mcp.tools.search import search; search(query='삼성전자', ticker='005930', top_k=2).hits[0].vault_path` — must start with `raw/`, not `vault/raw/`
- **dart-fss session timeout**: no upstream knob in 0.4.x. Re-evaluate if Phase 4 expands corpus breadth and new timeout failure modes appear.
- **Entity upsert from Phase 4 non-DART collectors** (KRX, news): same pattern applies but is out of scope for this bugfix. Each Phase 4 collector will wire its own upsert_entity call with source-specific canonical_name/ticker extraction.

## Commits

| Order | Hash     | Type | Description                                                    |
| ----- | -------- | ---- | -------------------------------------------------------------- |
| 1     | e93ed65  | fix  | Task 1 (Bug A) — default vault_root to repo root               |
| 2     | e7d8d7f  | fix  | Task 2 (Bug B) — harden DART fetch_body retries (5x, wider catch) |
| 3     | e6895b9  | fix  | Task 3 (Bug C) — upsert_entity helper + collector wiring       |
| 4     | e23cbc1  | fix  | Rule-3 follow-up — wire engine=get_engine() into CLI + test    |

## Self-Check: PASSED

- tests/test_dart_fetcher_retry.py exists ✓
- tests/test_entity_upsert.py exists ✓
- All 4 commits present in git log ✓
- Full fast suite (183 tests) passes ✓
- Verification greps all return empty ✓
