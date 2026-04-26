# Quick Task 260426-k8h: Code Review Report

**Reviewed:** 2026-04-26
**Depth:** quick
**Files Reviewed:** 8
**Status:** issues_found (1 Warning, 2 Info — no Critical)

## Summary

`read_existing_derived` is well-designed: fail-soft on missing/malformed files,
uses the existing `_derived_is_populated` heuristic to avoid carrying empty
defaults, and explicitly documents the content_hash poisoning hazard. All 5
collector writers (dart, kind, krx, macro, news) follow an identical, correct
pattern: read prior derived → conditionally splat into `FrontMatter(**{"derived":
...})` only when non-None.

- **COLL-07 clean** — no anthropic/openai imports introduced.
- **No accidental provenance mutation** — every site rebuilds `ProvenanceBlock`
  from new collector inputs.
- **No accidental ingest_state preservation** (see WR-01) — sites construct
  fresh `FrontMatter` without passing `ingest_state`, falling back to default
  empty `IngestStateBlock()`.

## Warnings

### WR-01: `ingest_state` is silently reset on every collector rewrite

**Files:** `src/collectors/{dart,kind,krx,macro,news}/writer.py` (all 5 sites)

When a collector rewrites a doc, the prior `ingest_state` block (`processed`,
`processed_at`, `embedding_model`, `ingest_model`, `ingest_version`,
`injection_flags`) is dropped because the new `FrontMatter(...)` call omits
`ingest_state`, falling back to the default-factory empty block. `_derived`
is now preserved, but the ingest pipeline's "I already processed this"
marker disappears, which may cause re-processing storms or — more
concerning — `injection_flags` (D-18 prompt-injection security flag) being
silently cleared on re-collect, re-exposing a previously-flagged doc to LLM
extraction.

This may be intentional per the locked CONTEXT.md decision ("ALWAYS preserve
[_derived], never invalidate") — but the scope is ambiguous: does "preserve"
mean only `_derived`, or also Zone 2 markers tied to that derived block?

**Recommended follow-up:** New quick task to extend the helper:
```python
def read_existing_zones(path: Path) -> tuple[IngestStateBlock | None, DerivedBlock | None]:
    ...
```
and carry `injection_flags` (at minimum) forward — losing an injection flag
is a security regression.

## Info

### IN-01: Test coverage gap — only macro is exercised end-to-end

`tests/test_collectors_preserve_derived.py` covers macro with full integration
tests; the other 4 writers (dart, kind, krx, news) are covered solely by a
grep guard ("`read_existing_derived` substring is present"). A future refactor
could keep the import but accidentally drop the `**({"derived": prior_derived}
if ...)` splat — the grep test would still pass.

**Recommended:** Add one parametrized integration test per writer using a
minimal seeded vault file, OR an AST check that verifies each writer's
`FrontMatter(...)` call splats a `derived` kwarg gated on `prior_derived is
not None`.

### IN-02: Edge case — body unchanged but prior derived populated

No test covers the kind/macro idempotent-skip path (`rewrote=False`) when
prior `_derived` exists. `kind/writer.py` returns early at the no-rewrite
branch before reading derived (correct, since file is unchanged). Worth one
explicit test to lock in the contract.
