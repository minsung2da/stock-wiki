# Quick Task 260426-k8h Summary

**Task:** preserve `_derived` block when collectors re-write a doc with new observations
**Mode:** quick-full (discuss + research + plan check + verify + code review)
**Status:** complete · verified · 5/5 must_haves
**Date:** 2026-04-26

## Commits

| SHA | Subject |
|-----|---------|
| `4ff651a` | feat(quick-260426-k8h-01): add `read_existing_derived` helper |
| `5eb3a79` | fix(quick-260426-k8h-02): collectors carry `_derived` block forward |

## Tasks executed

### Task 1 — `read_existing_derived` helper + unit tests
- Added function in `src/shared/frontmatter.py` with signature
  `read_existing_derived(path: Path) -> DerivedBlock | None`.
- Returns `None` when the file is missing, frontmatter is malformed, or
  `_derived` is absent / not populated. Returns the parsed `DerivedBlock`
  otherwise. Catches `(ValueError, OSError)` so collectors never crash on
  a bad prior file.
- 4 unit tests in `tests/test_frontmatter.py::TestReadExistingDerived`:
  missing-file, malformed-frontmatter, populated round-trip, default-empty
  not-carried.

### Task 2 — wire helper into all 5 collector writers
- Patched `src/collectors/{macro,krx,news,dart,kind}/writer.py` with the
  identical 3-step pattern: import the helper → call it before constructing
  `FrontMatter(...)` → conditionally splat `derived=prior_derived` into the
  constructor only when non-None (preserves the empty-default behavior on
  first writes).
- Hash-poisoning safety: prior `_derived` is never fed into
  `compute_body_hash` / content_hash computation; the new content_hash
  comes from the freshly-fetched body alone.
- Tests: `tests/test_collectors_preserve_derived.py` — grep guard
  (`test_all_writers_call_read_existing_derived`) plus 3 macro
  integration tests (carry-forward, first-write default, malformed prior
  non-fatal).

## Files

**Modified (7):**
- `src/shared/frontmatter.py` (+48 LOC)
- `src/collectors/dart/writer.py` (+9 LOC)
- `src/collectors/kind/writer.py` (+9 LOC)
- `src/collectors/krx/writer.py` (+9 LOC)
- `src/collectors/macro/writer.py` (+5 LOC)
- `src/collectors/news/writer.py` (+10 LOC)
- `tests/test_frontmatter.py` (+35 LOC, 4 tests)

**Created (1):**
- `tests/test_collectors_preserve_derived.py` (+125 LOC, 4 tests)

## Verification

- 4/4 unit tests pass (`TestReadExistingDerived`)
- 4/4 integration tests pass (`test_collectors_preserve_derived`)
- 459/459 full pytest regression green (15-min run)
- Pre-commit (gitleaks, ruff, ruff-format) clean

## Known tradeoff (per CONTEXT.md decision D-02)

After this fix, `walk.find_candidates` will SKIP a doc whose body changed
if the carried `_derived` is structurally still populated — the collector
writes a consistent content_hash, so the routine sees `_derived
populated AND fm.content_hash == recomputed_hash(body)` and treats the
doc as already enriched. This was the locked decision: the collector
never invalidates `_derived`; the routine layer owns freshness. For
intentional re-enrichment after a body change, operator clears `_derived`
manually or the routine gains a `_derived._enriched_for_hash` marker
(future enhancement, out of scope for this task).

## Code-review follow-up (separate scope)

`260426-k8h-REVIEW.md` flagged WR-01: `ingest_state.injection_flags`
(D-18 prompt-injection security flag) is also silently reset on every
collector rewrite. Same pattern, separate scope — this task locked
`_derived` only. Recommended follow-up quick task:
"preserve injection_flags in ingest_state on collector rewrite".
