---
phase: quick-260426-k8h
verified: 2026-04-26T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification: false
---

# Quick Task 260426-k8h: Preserve _derived Block — Verification Report

**Task Goal:** preserve `_derived` block when collectors re-write a doc with new observations
**Verified:** 2026-04-26
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Re-running `stock collect macro` on a vault with prior Routine-enriched `_derived` blocks does NOT wipe those blocks | ✓ VERIFIED | `test_macro_writer_carries_prior_derived` passes: new content_hash written, `_derived.tickers` and `.summary` preserved verbatim |
| 2 | All five collectors (macro/krx/news/dart/kind) carry forward the prior `_derived` block when overwriting | ✓ VERIFIED | `test_all_writers_call_read_existing_derived` passes grep-guard; all 5 writers confirmed to import and call `read_existing_derived` at lines macro:140, krx:89, news:85, dart:75, kind:128 |
| 3 | First-time collection (no prior file) writes the default empty `_derived` (no behavior change) | ✓ VERIFIED | `test_macro_writer_first_write_default_derived` passes; helper's `path.exists()` short-circuit returns None → FrontMatter uses default DerivedBlock() |
| 4 | A malformed prior frontmatter does NOT crash the collector — helper returns None and fresh empty `_derived` is written | ✓ VERIFIED | `test_macro_writer_malformed_prior_is_non_fatal` passes; `read_existing_derived` catches `(ValueError, OSError)` and returns None |
| 5 | The new content_hash is computed ONLY from the new body (no hash poisoning from the carried `_derived`) | ✓ VERIFIED | In all 5 writers, `content_hash = compute_body_hash(body)` / `_body_hash(body)` / `compute_news_content_hash(...)` is computed BEFORE `read_existing_derived` is called in macro (line 125 vs 140) and independently of `prior_derived` in all other writers. `prior_derived` is never passed to any hash function. Docstring in helper explicitly warns against this. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/shared/frontmatter.py` | `read_existing_derived(path: Path) -> DerivedBlock | None` | ✓ VERIFIED | Function at line 283; signature matches locked D-03 contract; docstring warns "do not feed into content_hash"; handles exists/malformed/empty-default correctly via `_derived_is_populated` check |
| `tests/test_frontmatter.py` | Unit tests for read_existing_derived (4 cases) in `TestReadExistingDerived` | ✓ VERIFIED | Class at line 174; 4 tests: `test_round_trip_returns_populated_block`, `test_missing_file_returns_none`, `test_malformed_frontmatter_returns_none`, `test_default_empty_derived_returns_none` — all 4 pass |
| `src/collectors/macro/writer.py` | reads prior `_derived` before constructing FrontMatter | ✓ VERIFIED | Imports `read_existing_derived` line 28, calls at line 140 (before FrontMatter construction at line 148+), conditional kwarg at line 156 |
| `src/collectors/krx/writer.py` | reads prior `_derived` before constructing FrontMatter | ✓ VERIFIED | Import line 28, call line 89, conditional kwarg line 104 |
| `src/collectors/news/writer.py` | reads prior `_derived` before constructing FrontMatter | ✓ VERIFIED | Import line 21, call line 85, conditional kwarg line 103 |
| `src/collectors/dart/writer.py` | reads prior `_derived` before constructing FrontMatter | ✓ VERIFIED | Import line 23, call line 75, conditional kwarg line 90 |
| `src/collectors/kind/writer.py` | reads prior `_derived` before constructing FrontMatter | ✓ VERIFIED | Import line 22, call line 128, conditional kwarg line 143 |
| `tests/test_collectors_preserve_derived.py` | Integration tests (4 tests) | ✓ VERIFIED | 4 tests: `test_all_writers_call_read_existing_derived`, `test_macro_writer_carries_prior_derived`, `test_macro_writer_first_write_default_derived`, `test_macro_writer_malformed_prior_is_non_fatal` — all 4 pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| all 5 collector writers | `src/shared/frontmatter.py:read_existing_derived` | `from shared.frontmatter import read_existing_derived` + call before `FrontMatter()` | ✓ WIRED | All 5 files: import confirmed, call before FrontMatter construction confirmed, `grep -L` guard test passes |
| FrontMatter(...) constructor in each writer | carried prior_derived value | conditional `**({"derived": prior_derived} if prior_derived is not None else {})` | ✓ WIRED | Pattern confirmed at macro:156, krx:104, news:103, dart:90, kind:143 — exactly matches locked patch shape |

### Data-Flow Trace (Level 4)

Not applicable — this task produces no UI or rendering components. The data flow is: `read_existing_derived(path)` → `prior_derived` → conditional `derived=` kwarg → `FrontMatter` model → `write_frontmatter()` → vault file. This is a pure write-path preservation fix, fully verified via integration tests.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 4 unit tests for helper | `uv run pytest tests/test_frontmatter.py::TestReadExistingDerived -v` | 4 passed in 1.82s | ✓ PASS |
| 4 integration tests | `uv run pytest tests/test_collectors_preserve_derived.py -v` | 4 passed in 1.82s | ✓ PASS |
| No regressions in related modules (frontmatter, content_hash, import_guard, zone_integrity, collectors preserve) | `uv run pytest tests/test_frontmatter.py tests/test_frontmatter_v2.py tests/test_frontmatter_news_fields.py tests/test_collectors_preserve_derived.py tests/test_content_hash.py tests/test_import_guard.py tests/test_zone_integrity.py -v --tb=short` | 50 passed in 5.76s | ✓ PASS |

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| QT-260426-k8h | `_derived` block preserved verbatim when collectors rewrite a vault doc with new observations | ✓ SATISFIED | Macro integration test proves carry-forward end-to-end; grep-guard proves all 5 collectors patched; hash-poisoning guard confirmed in implementation and docs |

### Anti-Patterns Found

No blockers or warnings found.

- `read_existing_derived` never logs or raises on malformed input — silent None is correct per RESEARCH pitfall #1 (walk.find_candidates handles observability).
- `prior_derived` is never passed to any hash function in any writer — no hash poisoning risk.
- No TODO/FIXME/placeholder patterns in any of the 7 modified files.
- The `_derived_is_populated` heuristic is inlined in `src/shared/frontmatter.py` (not imported from `.claude/routines/`) — correct per the "Don't import across src/ ↔ .claude/routines/ boundary" layering rule in RESEARCH.md.
- Known accepted tradeoff (PLAN `<known_tradeoff>` section): if body content changes but `_derived` is structurally still populated, `walk.find_candidates` will skip re-enrichment because the collector writes the new content_hash AND carries the prior `_derived`. This is locked by CONTEXT.md D-01/D-02 and explicitly documented in the plan — not a gap.

### Human Verification Required

None. All must-haves are verifiable programmatically and have been verified by running the test suite.

### Gaps Summary

No gaps. All 5 must-have truths are verified, all 8 required artifacts exist and are substantive and wired, both key links are confirmed, the full test suite (targeted: 50/50) is green.

---

_Verified: 2026-04-26_
_Verifier: Claude (gsd-verifier)_
