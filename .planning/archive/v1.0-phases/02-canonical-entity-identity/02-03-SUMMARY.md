---
phase: 02-canonical-entity-identity
plan: 03
subsystem: db
tags: [resolve-entity, temporal, supersedes, fixtures, ENT-01, ENT-02, ENT-03]

requires:
  - phase: 02-canonical-entity-identity
    provides: Alembic revision 0001 (entities, entity_aliases, edges, documents), pg_clean fixture
provides:
  - src/db/entity.py exporting Entity dataclass + resolve_entity(engine, value, as_of)
  - Four YAML entity fixtures under fixtures/entities/ (rename, split, ticker_recycle synthetic, amendment)
  - tests/fixtures_loader.py parameterized INSERT helper
  - 12 passing integration tests (9 resolve_entity + 3 supersedes recursive CTE)
affects: [phase-03-collectors, phase-04-ingest, phase-05-hybrid-search]

tech-stack:
  added: []
  patterns:
    - "resolve_entity digit-length auto-branch (D-12): 8→corp_code, 6→ticker, else None"
    - "Temporal lookup via half-open interval [valid_from, valid_to): as_of=None→current-only, as_of=<date>→historical"
    - "All SQL via SQLAlchemy text() + bind params (T-02-11 mitigation, zero f-string SQL)"
    - "Recursive CTE walk with cycle guard (depth < 20) for supersedes chain (T-02-13 mitigation)"
    - "Synthetic ticker-recycle fixture flagged per Pitfall 1 — real-case mining deferred to v2"

key-files:
  created:
    - src/db/entity.py
    - fixtures/entities/rename_case.yaml
    - fixtures/entities/split_case.yaml
    - fixtures/entities/ticker_recycle.yaml
    - fixtures/entities/amendment_case.yaml
    - tests/fixtures_loader.py
    - tests/test_entity_resolve.py
    - tests/test_supersedes_edge.py
  modified: []

key-decisions:
  - "resolve_entity is the ONLY public lookup surface — downstream collectors must import, not re-implement"
  - "Ticker-recycle fixture kept synthetic (corp_codes 99999991/99999992, ticker 099999) — real KRX recycling example search returned nothing reproducible; v2 task to mine pykrx listings history"
  - "Recursive CTE convention: src supersedes dst; walk e.src_id = c.dst_id to reach terminal amendment"
  - "Gap-returns-None: ticker alias [valid_from, valid_to) non-coverage → resolve_entity returns None (not empty Entity)"

requirements-completed: [ENT-01, ENT-02, ENT-03]

metrics:
  duration: "~15 min"
  completed: 2026-04-17
  tasks: 2
  files_created: 8
  files_modified: 0
  tests_added: 12
---

# Phase 02 Plan 03: resolve_entity + temporal alias + supersedes CTE Summary

**`resolve_entity(engine, value, as_of=None)` ships as the canonical entity lookup with D-12 digit-length auto-branch, D-10/D-11 half-open temporal interval matching, and zero f-string SQL; four YAML fixtures (rename / split / synthetic ticker-recycle / DART amendment) plus 12 integration tests prove ENT-01/ENT-02/ENT-03 green against the live migrated schema.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 2
- **Files created:** 8
- **Tests added:** 12 (9 resolve_entity + 3 supersedes)
- **Test results:** 12/12 new pass; full suite 58/59 pass (1 pre-existing `.env`-existence test orthogonal to this plan)

## Accomplishments

- Shipped `src/db/entity.py` (94 LOC) with `Entity` frozen dataclass and `resolve_entity` helper covering all four ENT-02 truths (corp_code direct, current ticker, historical ticker under rename, ticker recycling under as_of)
- Authored four YAML entity fixtures under `fixtures/entities/`:
  - `rename_case.yaml` — Samsung-style rename (corp_code 00126380 stable across 2000-01-01 name change)
  - `split_case.yaml` — synthetic split fixture proving split-date boundary preserves corp_code + ticker identity
  - `ticker_recycle.yaml` — **SYNTHETIC** (Pitfall 1): two corp_codes (99999991/99999992) reuse ticker 099999 at non-overlapping valid ranges
  - `amendment_case.yaml` — DART 기재정정 (original + amendment doc + supersedes edge)
- Built `tests/fixtures_loader.py` with four parameterized-INSERT branches (entities / entity_aliases / documents / edges) — T-02-12 defensive pattern even for trusted fixture data
- Proved ENT-03 recursive CTE walk: `WITH RECURSIVE chain ... depth < 20` returns terminal amendment id from any starting doc; no-chain returns None; uq_edge_endpoints blocks duplicate edge inserts (IntegrityError)

## Task Commits

1. **Task 1 RED: failing fixtures + tests** — `c1d1389` (test)
2. **Task 2 GREEN: resolve_entity implementation** — `105990e` (feat)

## Verification Evidence

```
$ uv run --group db --group dev pytest tests/test_entity_resolve.py tests/test_supersedes_edge.py -v
tests/test_entity_resolve.py::test_corp_code_direct_lookup PASSED        [  8%]
tests/test_entity_resolve.py::test_current_ticker_lookup PASSED          [ 16%]
tests/test_entity_resolve.py::test_rename_historical_ticker_resolves PASSED [ 25%]
tests/test_entity_resolve.py::test_split_date_boundary_same_corp_code PASSED [ 33%]
tests/test_entity_resolve.py::test_ticker_recycle_as_of_selects_correct_corp PASSED [ 41%]
tests/test_entity_resolve.py::test_gap_between_recycles_returns_none PASSED [ 50%]
tests/test_entity_resolve.py::test_mismatch_length_returns_none PASSED   [ 58%]
tests/test_entity_resolve.py::test_nonexistent_corp_code_returns_none PASSED [ 66%]
tests/test_entity_resolve.py::test_nonexistent_ticker_returns_none PASSED [ 75%]
tests/test_supersedes_edge.py::test_amendment_returns_latest_doc PASSED  [ 83%]
tests/test_supersedes_edge.py::test_no_amendment_returns_none PASSED     [ 91%]
tests/test_supersedes_edge.py::test_edge_unique_prevents_duplicate_insert PASSED [100%]
======================== 12 passed, 1 warning in 11.57s ========================

$ uv run --group db --group dev pytest tests/ --ignore=tests/test_secrets.py
======================= 53 passed, 4 warnings in 13.51s ========================

$ grep -E 'f"""|f"SELECT|f'\''SELECT' src/db/entity.py
(no output — zero f-string SQL)
```

## Requirement Coverage

| Req    | Evidence |
|--------|----------|
| ENT-01 | `resolve_entity("00126380")` → Samsung entity; digit-length auto-branch tested via `test_mismatch_length_returns_none` (7-digit, empty, alpha) |
| ENT-02 | Rename/split/recycle fixtures + 5 tests (current ticker, historical ticker, split boundary, recycle as_of old/new/current, gap-returns-None) |
| ENT-03 | Amendment fixture + 3 tests (recursive CTE terminal, no-chain-None, uq_edge_endpoints) |

## Decisions Made

- **resolve_entity is the ONLY lookup surface.** Documented in module docstring. Collectors must import, never re-implement — prevents drift on temporal semantics.
- **Ticker-recycle fixture is synthetic (Pitfall 1).** Public search returned no concrete KRX recycling example with enough metadata to build a realistic fixture. Test docstring explicitly flags it; v2 task to mine via `pykrx` listing history.
- **Half-open interval `[valid_from, valid_to)`.** `valid_to` exclusive upper bound per D-10; ticker_recycle old-corp valid_to=2001-01-01 means as_of=2001-01-01 already belongs to no corp (gap starts here).
- **Recursive CTE depth guard `< 20`.** T-02-13 cycle mitigation; DART amendment chains never exceed single-digit depth in practice.

## Deviations from Plan

None — plan executed exactly as written. Both tasks matched the acceptance criteria and verification commands produced the expected outputs on first run.

## Deferred Issues

**Pre-existing: `tests/test_secrets.py::test_env_file_not_committed` false positive.** Asserts `.env` must not exist at project root, but Plan 02-02 legitimately created a gitignored local `.env` for docker-compose Postgres. Test needs relaxation (`assert .env is gitignored`) but that's a Plan 01 cleanup, not 02-03 scope. Logged to `.planning/phases/02-canonical-entity-identity/deferred-items.md`.

## Known Stubs

None. All fixtures insert real (synthetic-but-valid) data; `resolve_entity` is fully implemented with no TODO/placeholder paths.

## Threat Flags

No new threat surface beyond the Plan 03 `<threat_model>` register. T-02-11, T-02-12, T-02-13 all mitigated as designed; T-02-14 accepted (helper returns only public metadata).

## Self-Check: PASSED

Verified on disk and in git:

- `[ -f src/db/entity.py ]` — present (94 LOC)
- `grep -c 'def resolve_entity' src/db/entity.py` → **1**
- `grep -c 'valid_to IS NULL' src/db/entity.py` → **2** (current-only branch + historical null upper bound)
- `grep -c 'valid_from <= :asof' src/db/entity.py` → **1** (historical half-open lower bound)
- `grep -c '_is_digits' src/db/entity.py` → **3** (definition + 2 call sites, D-12 auto-branch)
- No f-string SQL: `grep -E 'f"""|f"SELECT|f'\''SELECT' src/db/entity.py` → no match
- `[ -f fixtures/entities/rename_case.yaml ]` + split + ticker_recycle + amendment — all present
- `grep 'valid_to: null' fixtures/entities/rename_case.yaml` → 2 matches (current name + current ticker)
- `grep -E '99999991|99999992' fixtures/entities/ticker_recycle.yaml` → both matches present
- `grep 'WITH RECURSIVE' tests/test_supersedes_edge.py` → match
- `[ -f tests/fixtures_loader.py ]` with `def load_entity_fixture` — present
- Commits `c1d1389`, `105990e` present in `git log`
- 12/12 new tests green; full non-secrets suite 53/53 green

## Next Phase Readiness

- **Phase 3 collectors** can now `from db.entity import resolve_entity` before inserting any document with a `corp_code` — this is the canonical mapping from frontmatter `ticker` / `corp_code` to the entity row.
- **Phase 3 amendments** (DART 기재정정 ingestion) can insert `edges(edge_type='supersedes', src_id=original, dst_id=amendment)` and query the terminal with the documented recursive CTE.
- **v2 TODO:** Mine `pykrx` listing history for a real KRX ticker-recycling case and replace the synthetic fixture — or add a second fixture alongside it.

---
*Phase: 02-canonical-entity-identity*
*Completed: 2026-04-17*
