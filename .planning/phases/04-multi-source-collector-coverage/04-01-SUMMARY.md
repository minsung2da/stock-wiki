---
phase: 04-multi-source-collector-coverage
plan: 01
subsystem: phase-4-preconditions
tags: [wave-1, portfolio, entity-alias, heartbeat, frontmatter, macro-catalog]
dependency_graph:
  requires: [03-one-company-walking-skeleton]
  provides:
    - "Portfolio.load(vault_root) → collector scope source (D-01..D-04)"
    - "resolve_entity_by_alias(engine, name, as_of) → news name→corp_code (D-11)"
    - "record_source_run(..., extra=) → Plans 02/05 heartbeat flags"
    - "ProvenanceBlock.{tickers,outlet,license_flag,observations} → Plans 03/04 writers"
    - "seed_name_aliases(engine) → pre-news alias seeder (R-09)"
    - "macro_series.yaml scaffold → Plan 03 catalog loader"
    - "tests/collectors/conftest.py → vault_tmp + seeded_engine fixtures"
  affects: [04-02, 04-03, 04-04, 04-05, 04-06]
tech_stack:
  added: []
  patterns:
    - "Additive Pydantic schema extension (Optional defaults + exclude_none) preserves Phase 3 YAML byte-identical"
    - "SELECT-then-INSERT idempotent seeder mirroring upsert_entity pattern"
    - "keyword-only `extra` kwarg with reserved-key deny-list"
key_files:
  created:
    - src/shared/portfolio.py
    - src/db/seed_name_aliases.py
    - vault/notes/portfolio.md
    - .planning/macro_series.yaml
    - tests/collectors/__init__.py
    - tests/collectors/conftest.py
    - tests/test_portfolio.py
    - tests/test_entity_alias.py
    - tests/test_heartbeat_extra.py
    - tests/test_frontmatter_news_fields.py
  modified:
    - src/db/entity.py
    - src/ingest/heartbeat.py
    - src/shared/frontmatter.py
decisions:
  - "Use 'eng_name' kind (not 'english_name') — migration 0001 CHECK constraint already permits it; no migration needed"
  - "TickerRef + Observation as typed nested Pydantic models (R-07) rather than raw dicts"
  - "Reserved heartbeat keys deny-listed from extra kwarg (T-04-22) instead of silent override"
metrics:
  duration_sec: 568
  tasks_completed: 4
  tests_added: 27
  completed_date: 2026-04-18
requirements: [COLL-02, COLL-03, COLL-04, COLL-05]
---

# Phase 4 Plan 01: Phase 4 Preconditions Summary

Wave-1 foundation: Portfolio model + loader, canonical name-alias resolver with idempotent seeder, macro catalog scaffold, shared collector pytest fixtures, heartbeat extra-kwarg extension, and additive ProvenanceBlock fields (tickers/outlet/license_flag/observations) — all ready for Wave-2 collectors (KRX/KIND/news/macro) to consume.

## One-liner

Landed the four preconditions Wave-2 plans block on: `Portfolio.load`, `resolve_entity_by_alias`+seeder, `record_source_run(..., extra=...)`, and news/macro-ready `ProvenanceBlock` — with Phase 3 regression (54 tests) still green.

## Tasks Completed

| Task | Name                                                                   | Commit    | Tests |
| ---- | ---------------------------------------------------------------------- | --------- | ----- |
| 1    | Portfolio model + loader + example portfolio.md                        | `ad771e5` | 5     |
| 2    | resolve_entity_by_alias + seed_name_aliases                            | `a12d935` | 7     |
| 3    | Heartbeat `extra` kwarg + ProvenanceBlock news/observations fields     | `2e2de2f` | 11    |
| 4    | macro_series.yaml scaffold + collectors conftest                       | `a419c88` | 0 (fixtures only) |

## Verification Evidence

```
$ uv run pytest tests/test_portfolio.py tests/test_entity_alias.py \
    tests/test_heartbeat_extra.py tests/test_frontmatter_news_fields.py \
    tests/test_import_guard.py -x -q
27 passed, 1 warning in 12.84s

$ uv run pytest tests/ -k "frontmatter or heartbeat or dart" -x -q
54 passed, 1 skipped, 162 deselected, 1 warning in 52.79s   # Phase 3 regression gate

$ uv run python -c "import yaml; d=yaml.safe_load(open('.planning/macro_series.yaml')); \
    assert len(d['ecos'])==2 and len(d['fred'])==2; print('ok')"
ok
```

## Deviations from Plan

None — plan executed exactly as written. Pre-commit hook reformatted a long-line in `tests/test_portfolio.py` and a docstring in `src/db/seed_name_aliases.py`; both cosmetic, content unchanged.

## Known Stubs

- `.planning/macro_series.yaml` ECOS entries carry `# TODO: verify` markers by design (D-23) — Plan 03 Wave-0 probe replaces them with live-verified IDs. FRED IDs are already canonical.

## Threat Flags

None. All changes are additive to existing trust-boundary-hardened modules; no new network or file-system surface.

## Self-Check: PASSED

**Files verified exist:**
- FOUND: src/shared/portfolio.py
- FOUND: src/db/seed_name_aliases.py
- FOUND: vault/notes/portfolio.md
- FOUND: .planning/macro_series.yaml
- FOUND: tests/collectors/conftest.py
- FOUND: tests/collectors/__init__.py
- FOUND: tests/test_portfolio.py
- FOUND: tests/test_entity_alias.py
- FOUND: tests/test_heartbeat_extra.py
- FOUND: tests/test_frontmatter_news_fields.py

**Commits verified in `git log`:**
- FOUND: ad771e5 (T1)
- FOUND: a12d935 (T2)
- FOUND: 2e2de2f (T3)
- FOUND: a419c88 (T4)
