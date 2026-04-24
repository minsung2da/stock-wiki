---
type: quick
task: entities seed expansion
created: 2026-04-24
completed: 2026-04-24
files_modified:
  - src/db/seed_entities.py
  - tests/db/__init__.py
  - tests/db/conftest.py
  - tests/db/test_seed_entities.py
  - CLAUDE.md
  - .planning/STATE.md
---

# Quick 260424-asr: entities seed expansion — Summary

**Done.** `src/db/seed_entities.py` seeds the `entities` table from
`vault/notes/portfolio.md` (holdings ∪ watchlist) via OpenDART `find_by_stock_code`,
closing the Phase 4 live-smoke gap where `collect_krx` fell into its fail-soft
`missing_entity` branch for un-seeded watchlist tickers (notably 000660
SK하이닉스). `upsert_entity`'s existing `ON CONFLICT (corp_code)` makes the
seeder idempotent — safe to re-run whenever the portfolio grows.

Ran live against the real OpenDART API + dev Postgres: 2 rows upserted
(005930 삼성전자 already present via DART collector; 000660 SK하이닉스 newly
seeded from watchlist). Subsequent `uv run stock collect krx` returned
`{succeeded: 0, skipped: 2, failed: []}` — the `failed` list is the critical
metric; both tickers are now resolvable and simply skipped as already-collected
today. The operational runbook (`CLAUDE.md §First-time Setup`) gained step 4.5
documenting the new command.

## Commits

- `766f6d3` feat(quick-260424): add seed_entities from portfolio.md
- `5ff0219` test(quick-260424): seed_entities unit tests
- (final) docs(quick-260424): document entities seed step + SUMMARY + STATE

## Test evidence

- `uv run pytest tests/db/test_seed_entities.py -x -q` → **3 passed**
- `uv run pytest tests/ -k "(entity_alias or portfolio or krx or seed_entities) and not api_probes" -x -q` → **36 passed, 281 deselected**
- `uv run pytest tests/test_import_guard.py -x -q` → **4 passed** (no anthropic/openai leak)

## Live seed row counts

```
corp_code  canonical_name  current_ticker
00164779   SK하이닉스       000660
00126380   삼성전자         005930
```

## Collector verification

`uv run stock collect krx` (after seed):
```
{"total": 2, "succeeded": 0, "skipped": 2, "failed": [], "elapsed_ms": 35834}
```
Exit code 0. No `missing_entity` in `failed` — 000660 resolves cleanly.
