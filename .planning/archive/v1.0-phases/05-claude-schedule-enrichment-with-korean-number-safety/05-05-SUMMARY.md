---
phase: 05-claude-schedule-enrichment-with-korean-number-safety
plan: 05
subsystem: collectors/dart
tags: [dart, financials, no-llm, numeric-safety]
requirements: [INGEST-06]
dependency_graph:
  requires:
    - 05-01 (NumericFact v2 schema)
    - 05-02 (unit normalization conventions)
    - 05-04 (number sanity baseline)
  provides:
    - "collectors.dart.financials.get_structured_financials (D-14 LLM-free accessor)"
    - "collectors.dart.financials.LINE_ITEM_SYNONYMS (22 canonical KR line items)"
  affects:
    - Plan 05-08 Routines skill (DART financial filings bypass LLM for numbers)
tech_stack:
  added: [dart-fss (lazy), pandas (already present)]
  patterns:
    - Cassette-driven offline tests (no live API call in CI)
    - Monkeypatchable _fs_extract wrapper (isolates dart-fss internals)
    - Canonical key → frozenset of label_ko variants (Pitfall 5)
key_files:
  created:
    - src/collectors/dart/financials.py
    - tests/test_dart_financials.py
    - tests/fixtures/dart_financial_responses/samsung_2025q4.json
    - tests/fixtures/dart_financial_responses/service_firm_synonym.json
  modified: []
decisions:
  - "LINE_ITEM_SYNONYMS covers 22 canonical keys (IS/BS/CF); growth path via backlog.md dart_structured_disagreement counter"
  - "_fs_extract is a thin monkeypatchable wrapper — test isolation from dart-fss internals"
  - "Docstring worded to avoid the literal substring 'import anthropic' so COLL-07 grep guard passes cleanly"
  - "Unmapped labels silently skipped — no fabricated mapping; new labels graduate via explicit synonym addition"
  - "First-match-wins dedup across sheets (bs → is → cis → cf); preserves dart-fss iteration order"
metrics:
  duration: 5min
  tasks: 2
  files: 4
  completed: 2026-04-24
---

# Phase 05 Plan 05: DART Structured Financials (LLM-free, D-14) Summary

LLM-free accessor `get_structured_financials(corp_code, bgn_de)` for DART financial statements using dart-fss `fs.extract`, emitting `NumericFact` records with `unit="KRW원"` and `source_span=None` so the Routines skill (Plan 05-08) bypasses the LLM entirely for DART numbers (INGEST-06).

## Scope Delivered

- **`src/collectors/dart/financials.py`** (150 LOC)
  - `LINE_ITEM_SYNONYMS`: 22 canonical keys mapping to observed IFRS label_ko variants (Pitfall 5 — `매출액` ⇔ `수익(매출액)` ⇔ `영업수익`; `영업이익` ⇔ `영업이익(손실)`; cash-flow "…현금흐름" ⇔ "…으로 인한 현금흐름")
  - `get_structured_financials(corp_code, bgn_de) -> list[NumericFact]` — iterates sheets (bs → is → cis → cf), first match wins per canonical key
  - `_fs_extract` monkeypatchable seam; lazy `import dart_fss`
  - `_pick_value` handles both cassette `value` column and live multi-period dart-fss frames
- **`tests/test_dart_financials.py`** — 7 tests, all offline (cassette-driven)
- **Cassette fixtures** — `samsung_2025q4.json` (canonical labels) + `service_firm_synonym.json` (수익(매출액), 영업이익(손실) variants)

## Verification Evidence

- `uv run --group dev pytest tests/test_dart_financials.py -x -q` → 7 passed in 7.64s
- `uv run --group dev pytest tests/test_import_guard.py -x -q` → 4 passed (COLL-07 preserved)
- `wc -l src/collectors/dart/financials.py` → 150 (<220 budget)
- `grep -E "import (anthropic|openai)|from (anthropic|openai)" src/collectors/dart/financials.py` → no matches

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Plan used `uv run --extra dev`; project exposes dev as a dependency-group**
- **Found during:** Task 1 verification
- **Issue:** `pyproject.toml` declares `[dependency-groups].dev`, not `[project.optional-dependencies].dev`. `uv run --extra dev` errors with "Extra `dev` is not defined in the project's `optional-dependencies` table".
- **Fix:** Used `uv run --group dev` for all test invocations.
- **Files modified:** none (invocation-only change; plan text not edited).

**2. [Rule 1 - Bug] `test_unmapped_labels_ignored` inconsistent with LINE_ITEM_SYNONYMS**
- **Found during:** Task 1 authoring
- **Issue:** Plan's test uses `판매비와관리비` as an "unmapped" label, but the same plan's LINE_ITEM_SYNONYMS includes `판매비와관리비` as a canonical key. Following the plan literally would make the test ambiguous.
- **Fix:** Renamed the test's unmapped-label sample from `판매비와관리비` to `판매비와관리비인식` (guaranteed non-member) so the test truthfully exercises the "unknown label → skipped" path.
- **Files modified:** `tests/test_dart_financials.py`.
- **Commit:** ea80cfb

**3. [Rule 1 - Bug] Docstring contained the literal substring `import anthropic`**
- **Found during:** Task 2 GREEN run — `test_no_llm_imports` failed because the guard grep matched prose inside the module docstring ("…must never import anthropic/openai").
- **Fix:** Reworded docstring to "must never depend on LLM SDKs (see COLL-07 guard test)".
- **Files modified:** `src/collectors/dart/financials.py`.
- **Commit:** 65d73e5

## Threat Flags

None. Trust boundaries + STRIDE register from plan are preserved:
- T-05-05-02 mitigated by `test_no_llm_imports` + lazy `import dart_fss` only.
- T-05-05-03 mitigated via silent-skip-on-unmapped (no fabricated mapping).
- T-05-05-04 mitigated by `_pick_value` NaN check (`f == f`).

## Known Stubs

None. Accessor returns real `NumericFact` pydantic models; fixtures are hand-crafted but representative.

## Follow-ups (not blocking this plan)

- Phase 9 will extend the cassette golden-set beyond 2 filings (RESEARCH.md calls out 10-filing target).
- Live DART cross-check harness (comparing LLM-narrative extractions to structured accessor) is Plan 05-07/05-08 territory — tracked there, not here.

## Commits

- `ea80cfb` test(05-05): add failing tests for DART structured financials accessor
- `65d73e5` feat(05-05): implement LLM-free DART structured financials accessor

## Self-Check: PASSED

- Created files exist:
  - FOUND: src/collectors/dart/financials.py
  - FOUND: tests/test_dart_financials.py
  - FOUND: tests/fixtures/dart_financial_responses/samsung_2025q4.json
  - FOUND: tests/fixtures/dart_financial_responses/service_firm_synonym.json
- Commits present in `git log`:
  - FOUND: ea80cfb
  - FOUND: 65d73e5
