# Quick Task 260426-mic Summary

**Task:** preserve `ingest_state.injection_flags` (D-18 prompt-injection security
marker) when collectors re-write a vault doc with new observations
**Mode:** quick (TDD per plan, executor-driven)
**Status:** complete · verified · 8/8 success criteria
**Date:** 2026-04-26

## Commits

| SHA | Subject |
|-----|---------|
| `95ba26e` | feat(quick-260426-mic-01): add `read_existing_injection_flags` helper |
| `45cbf36` | fix(quick-260426-mic-02): collectors carry `injection_flags` forward |

## Tasks executed

### Task 1 — `read_existing_injection_flags` helper + 4 unit tests (TDD)
- Added function in `src/shared/frontmatter.py` immediately after the
  existing `read_existing_derived`, signature
  `read_existing_injection_flags(path: Path) -> list[str] | None`.
- Returns `None` on (a) missing file, (b) malformed YAML / schema fail
  (catches `(ValueError, OSError)` — same fail-soft contract as the derived
  helper), or (c) empty `injection_flags` list (default).
- Returns `list(flags)` (a fresh list — never shares the parsed model's
  reference; immutability rule from `coding-style.md`).
- Docstring locks both invariants: "Call BEFORE computing the new
  content_hash. Must NOT feed into hash computation." AND "ONLY
  `injection_flags` is preserved; other `ingest_state` fields reset on
  rewrite."
- 4 unit tests in `tests/test_frontmatter.py::TestReadExistingInjectionFlags`:
  round-trip populated / missing-file / malformed-FM / empty-default-as-None.
- TDD verified RED→GREEN: tests authored first → ImportError →
  implementation → all 4 pass.

### Task 2 — wire helper into all 5 collector writers + integration tests (TDD)
- Patched `src/collectors/{macro,krx,news,dart,kind}/writer.py` with the
  identical 3-step pattern:
  1. add `IngestStateBlock` and `read_existing_injection_flags` to the
     existing `from shared.frontmatter import (...)` block.
  2. call `prior_injection_flags = read_existing_injection_flags(path)`
     immediately after the existing `prior_derived = ...` line.
  3. add a sibling splat in the `FrontMatter(...)` constructor BEFORE the
     existing `derived` splat (zone-order: provenance → ingest_state →
     derived):
     ```python
     **(
         {"ingest_state": IngestStateBlock(injection_flags=prior_injection_flags)}
         if prior_injection_flags is not None
         else {}
     ),
     ```
- Hash-poisoning safety: `prior_injection_flags` is never fed into
  `compute_body_hash`. The new `content_hash` comes from the freshly-fetched
  body alone.
- Scope-lock locked: constructing `IngestStateBlock(injection_flags=...)`
  with positional defaults for all other fields ensures `processed`,
  `processed_at`, `embedding_model`, `ingest_model`, `ingest_version` reset
  on every collector rewrite (re-processing must be triggered).
- 5 new tests in `tests/test_collectors_preserve_derived.py`:
  - grep guard `test_all_writers_call_read_existing_injection_flags` (proves
    patch reached all 5 writers)
  - 3 macro integration tests: carry-forward, first-write-default,
    malformed-prior-non-fatal (mirror k8h's macro proven-failure case)
  - 1 scope-lock contract test
    `test_macro_writer_scope_lock_other_ingest_state_fields_reset` —
    proves OTHER `ingest_state` fields correctly reset on rewrite.
- TDD verified RED→GREEN: 3 of 5 new tests failed before patches landed
  (grep guard + carry-forward + scope-lock), all 9 in the file pass after.

## Files

**Modified (7):**
- `src/shared/frontmatter.py` (+39 LOC, 1 new function)
- `src/collectors/dart/writer.py` (+9 LOC)
- `src/collectors/kind/writer.py` (+9 LOC)
- `src/collectors/krx/writer.py` (+9 LOC)
- `src/collectors/macro/writer.py` (+12 LOC, includes 3-line comment block)
- `src/collectors/news/writer.py` (+9 LOC)
- `tests/test_frontmatter.py` (+34 LOC, 4 tests + 1 import)
- `tests/test_collectors_preserve_derived.py` (+121 LOC, 5 tests + helper)

## Verification

- 4/4 unit tests pass (`TestReadExistingInjectionFlags`)
- 9/9 integration tests pass (`tests/test_collectors_preserve_derived.py` —
  k8h's 4 + mic's 5)
- 111/111 frontmatter+collectors regression suite green (30 s run)
- Pre-commit (gitleaks, ruff, ruff-format) clean — ruff auto-fixed import
  ordering on first commit attempt; second commit landed without changes.

## Success criteria status

- [x] `read_existing_injection_flags` exists with signature
      `(path: Path) -> list[str] | None`.
- [x] 4 unit tests pass: round-trip / missing / malformed / empty-default.
- [x] All 5 collector writers call `read_existing_injection_flags` before
      `FrontMatter` construction (grep guard passing).
- [x] Macro integration test proves `injection_flags` survives a
      body-changing rewrite.
- [x] Scope-lock test proves `processed`, `processed_at`, `embedding_model`,
      `ingest_model`, `ingest_version` correctly RESET on rewrite.
- [x] `prior_injection_flags` is NEVER passed into content_hash computation
      in any writer (verified by code inspection — all 5 writers compute
      `content_hash` from `body` alone).
- [x] k8h's `_derived` carry-forward still works (k8h test set still green).
- [x] Existing test suite remains green (collectors+frontmatter, 111
      passed).

## Known interaction with k8h

Both fixes compose cleanly: the constructor now has TWO conditional splats
(ingest_state then derived), each independent. A doc with both a populated
`_derived` AND a non-empty `injection_flags` carries both forward in a
single rewrite. The empty-default heuristic for each is independent —
clearing one does not affect the other.

## Threat Flags

None — this change strictly tightens an existing security marker (D-18
prompt-injection flag preservation). No new network surface, auth path,
file-access pattern, or schema change at a trust boundary is introduced.

## Self-Check: PASSED

- File `src/shared/frontmatter.py` contains
  `read_existing_injection_flags` (verified by test import + helper test
  pass).
- All 5 writers contain `read_existing_injection_flags` (verified by
  `test_all_writers_call_read_existing_injection_flags` passing).
- Commits `95ba26e` and `45cbf36` exist on `main` (verified by
  `git log --oneline -3`).
- Test suite 111/111 green on collectors+frontmatter scope.
