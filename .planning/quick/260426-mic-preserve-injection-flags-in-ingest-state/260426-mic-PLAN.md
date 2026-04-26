---
phase: quick-260426-mic
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/shared/frontmatter.py
  - src/collectors/dart/writer.py
  - src/collectors/kind/writer.py
  - src/collectors/krx/writer.py
  - src/collectors/macro/writer.py
  - src/collectors/news/writer.py
  - tests/test_frontmatter.py
  - tests/test_collectors_preserve_derived.py
autonomous: true
requirements:
  - QT-260426-mic
---

<objective>
Stop all five collectors (dart/kind/krx/macro/news) from silently clearing
`ingest_state.injection_flags` (D-18 prompt-injection security marker) when
they re-write a vault doc. Mirror the 260426-k8h pattern exactly, narrowed to
ONE field of `ingest_state`.

Purpose: per `260426-k8h-REVIEW.md` WR-01, after the k8h fix the prior
`ingest_state` block is silently reset on every collector rewrite — including
`injection_flags`. Losing an injection flag is a security regression: a
previously-flagged adversarial doc becomes re-eligible for LLM extraction the
next time the routine sees it. Same pattern as `_derived` preservation, scoped
to a single field.

Output: 1 new shared helper (~12 LOC) + 5 single-line writer patches + 5 unit
tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@src/shared/frontmatter.py
@tests/test_frontmatter.py
@tests/test_collectors_preserve_derived.py
@.planning/quick/260426-k8h-preserve-derived-block-when-collectors-r/260426-k8h-PLAN.md
@.planning/quick/260426-k8h-preserve-derived-block-when-collectors-r/260426-k8h-REVIEW.md

<interfaces>
From `src/shared/frontmatter.py`:
```python
class IngestStateBlock(BaseModel):
    """Zone 2: Written by ingest pipeline. Tracks processing state."""
    processed: bool = False
    processed_at: datetime | None = None
    embedding_model: str | None = None
    ingest_model: str | None = None
    ingest_version: int | None = None
    injection_flags: list[str] = Field(default_factory=list)

# Already exists (260426-k8h):
def read_existing_derived(path: Path) -> DerivedBlock | None: ...
def read_frontmatter(path: str) -> tuple[FrontMatter, str]: ...
def write_frontmatter(path: str, model: FrontMatter, body: str) -> None: ...
```

Helper to add (mirrors `read_existing_derived` exactly):
```python
def read_existing_injection_flags(path: Path) -> list[str] | None:
    """Return prior ingest_state.injection_flags from a vault file, or None.

    Returns None when:
      - the file does not exist (first-time collection),
      - frontmatter cannot be parsed (malformed YAML / schema fail),
      - or injection_flags is empty.

    NOTE: callers must NOT feed the returned list into content_hash
    computation. The new content_hash MUST be computed solely from the new
    body — no hash poisoning from carried-over markers.

    SCOPE: ONLY injection_flags is preserved. Other ingest_state fields
    (processed, processed_at, embedding_model, ingest_model, ingest_version)
    are pipeline-state markers owned by the ingest worker; they MUST reset
    on collector rewrite so re-processing is correctly triggered.
    injection_flags is the sole security marker that must survive.
    """
```

Writer patch shape (uniform across all 5 writers, mirroring the existing
`prior_derived` pattern):
```python
prior_derived = read_existing_derived(path)
prior_injection_flags = read_existing_injection_flags(path)
fm = FrontMatter(
    provenance=ProvenanceBlock(...),
    **(
        {"ingest_state": IngestStateBlock(injection_flags=prior_injection_flags)}
        if prior_injection_flags is not None
        else {}
    ),
    **({"derived": prior_derived} if prior_derived is not None else {}),
)
```
</interfaces>
</context>

<scope_lock>
## Scope Lock — preserve ONLY `injection_flags`

The other `ingest_state` fields (`processed`, `processed_at`,
`embedding_model`, `ingest_model`, `ingest_version`) are pipeline-state
markers that the ingest worker owns. They MUST reset on collector rewrite
because the body changed → the doc needs re-processing. Preserving them
would mask re-processing needs.

`injection_flags` is the sole security marker — it records that prior
content was flagged as poisoned (D-18). A new collector body must inherit
that finding until the ingest worker re-evaluates it; otherwise a
previously-flagged doc silently becomes re-eligible for LLM extraction.

Hash safety mirror of k8h: `prior_injection_flags` is NEVER fed into
`compute_body_hash` / `content_hash` computation. The new `content_hash`
comes from the freshly-fetched body alone — no hash poisoning.
</scope_lock>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add `read_existing_injection_flags` helper + 4 unit tests (RED→GREEN)</name>
  <files>src/shared/frontmatter.py, tests/test_frontmatter.py</files>
  <behavior>
    Test 1 (round-trip populated): write a FrontMatter with `IngestStateBlock(injection_flags=["HIDDEN_INSTRUCTION", "ROLE_REASSIGNMENT"])`, call `read_existing_injection_flags(path)` → returns `["HIDDEN_INSTRUCTION", "ROLE_REASSIGNMENT"]`.
    Test 2 (missing file): `read_existing_injection_flags(tmp_path / "nope.md")` → None.
    Test 3 (malformed FM): file with broken YAML (`---\nnot: [valid yaml\n---\nbody`) → None (no exception).
    Test 4 (empty/default ingest_state): write FrontMatter with default `IngestStateBlock()` (injection_flags=[]) → `read_existing_injection_flags` returns None (treat empty list as absent, mirroring `_derived_is_populated` heuristic).
  </behavior>
  <action>
    Add `read_existing_injection_flags(path: Path) -> list[str] | None` to `src/shared/frontmatter.py` immediately AFTER the existing `read_existing_derived` function (cohesion — both are collector-side carry-forward helpers).

    Implementation (mirror `read_existing_derived` line-for-line, swap field):
    1. If `not path.exists()` → return None.
    2. Try `read_frontmatter(str(path))`; catch `(ValueError, OSError)` → return None (silent; same fail-soft contract as the derived helper).
    3. `flags = model.ingest_state.injection_flags`
    4. If `not flags` (empty list) → return None.
    5. Else return `list(flags)` (return a fresh list — never share the parsed model's reference, immutability rule from coding-style).
    6. Docstring MUST state both:
       - "Call BEFORE computing the new content_hash. Must NOT feed into hash computation."
       - "ONLY `injection_flags` is preserved. Other `ingest_state` fields reset on rewrite."

    Then add 4 unit tests in `tests/test_frontmatter.py` in a new class `class TestReadExistingInjectionFlags:`, mirroring the existing `TestReadExistingDerived` class pattern. Use the `tmp_vault: Path` fixture from `tests/conftest.py`. Import `read_existing_injection_flags` at the top of the test file.

    TDD order: write all 4 tests first, run pytest → confirm they FAIL (helper doesn't exist) → implement helper → run pytest → confirm they PASS.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run pytest tests/test_frontmatter.py::TestReadExistingInjectionFlags -v</automated>
  </verify>
  <done>4 new tests in `TestReadExistingInjectionFlags` all pass. Helper exists in `src/shared/frontmatter.py` with docstring noting (a) "do not feed into content_hash" and (b) "only `injection_flags` is preserved". `from shared.frontmatter import read_existing_injection_flags` succeeds.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wire helper into all 5 collector writers + integration tests</name>
  <files>src/collectors/dart/writer.py, src/collectors/kind/writer.py, src/collectors/krx/writer.py, src/collectors/macro/writer.py, src/collectors/news/writer.py, tests/test_collectors_preserve_derived.py</files>
  <behavior>
    Test 1 (macro carry-forward): in a `tmp_vault`, pre-write a macro doc with `IngestStateBlock(injection_flags=["HIDDEN_INSTRUCTION"])` and any `ProvenanceBlock`. Invoke `write_macro_doc(...)` with new observations that change the body and content_hash. Read the resulting file → assert `fm.ingest_state.injection_flags == ["HIDDEN_INSTRUCTION"]` AND `fm.provenance.content_hash != "OLD"` AND other `ingest_state` fields are at their defaults (`processed is False`, `processed_at is None`, etc.).
    Test 2 (first-write default): tmp_vault without prior file; invoke any writer; resulting `fm.ingest_state.injection_flags == []` (empty default; first writes get a clean `IngestStateBlock`).
    Test 3 (malformed prior is non-fatal): pre-write a corrupt `---\nnot: [valid\n---\nbody` file; invoke macro writer; no exception; resulting `fm.ingest_state` is the default empty block.
    Test 4 (grep guard): assert `read_existing_injection_flags` substring is present in all 5 writer files.
    Test 5 (carry-forward does NOT preserve other ingest_state fields): pre-write a macro doc with `IngestStateBlock(processed=True, processed_at=<some datetime>, embedding_model="bge-m3", ingest_model="claude-haiku-4-5", ingest_version=1, injection_flags=["X"])`. Invoke `write_macro_doc` with new observations. Read result → assert `fm.ingest_state.injection_flags == ["X"]` BUT `fm.ingest_state.processed is False`, `fm.ingest_state.processed_at is None`, `fm.ingest_state.embedding_model is None`, `fm.ingest_state.ingest_model is None`, `fm.ingest_state.ingest_version is None`. Locks the SCOPE LOCK contract.
  </behavior>
  <action>
    For EACH of the 5 writer files (`dart/kind/krx/macro/news/writer.py`), apply the uniform patch:

    1. Add `read_existing_injection_flags` and `IngestStateBlock` to the existing `from shared.frontmatter import (...)` import block (next to the already-imported `read_existing_derived`).
    2. Locate the existing line `prior_derived = read_existing_derived(path)`. Immediately AFTER it, add:
       ```python
       prior_injection_flags = read_existing_injection_flags(path)
       ```
    3. In the `FrontMatter(...)` construction, the existing `**({"derived": prior_derived} if prior_derived is not None else {})` splat stays. ADD a sibling splat for `ingest_state`:
       ```python
       **(
           {"ingest_state": IngestStateBlock(injection_flags=prior_injection_flags)}
           if prior_injection_flags is not None
           else {}
       ),
       ```
       Place it BEFORE the existing `derived` splat for stable diff ordering (matches frontmatter zone order: provenance → ingest_state → derived).
    4. CRITICAL: do NOT pass `prior_injection_flags` into any hash function. The new `content_hash` MUST come solely from the new body (mirror of k8h pitfall #4).
    5. For `kind` and `macro` which have a hash short-circuit BEFORE write (no overwrite when hash matches), the patch still applies on the rewrite branch only — same shape, same place as the existing `prior_derived` line.
    6. Per scope lock: do NOT preserve `processed`, `processed_at`, `embedding_model`, `ingest_model`, `ingest_version`. Constructing `IngestStateBlock(injection_flags=prior_injection_flags)` (positional default for all other fields) ensures those reset.

    Add the 5 tests above to `tests/test_collectors_preserve_derived.py` (file already exists from k8h). Tests 1, 3, 5 = macro integration tests (proven failure case — same as k8h). Test 2 = first-write default. Test 4 = grep guard:
    ```python
    def test_all_writers_call_read_existing_injection_flags() -> None:
        from pathlib import Path
        repo_root = Path(__file__).resolve().parent.parent
        for collector in ("macro", "krx", "news", "dart", "kind"):
            src = (repo_root / "src" / "collectors" / collector / "writer.py").read_text()
            assert "read_existing_injection_flags" in src, (
                f"{collector}/writer.py missing read_existing_injection_flags call"
            )
    ```

    TDD order: write Test 1 + Test 5 first → confirm FAIL (current writers wipe `ingest_state`). Apply patches to all 5 writers. Run → confirm PASS. Then add Tests 2, 3, 4.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run pytest tests/test_collectors_preserve_derived.py -v &amp;&amp; uv run pytest tests/ -x --ignore=tests/test_collectors_preserve_derived.py -q</automated>
  </verify>
  <done>
    - All 5 collector writers import and call `read_existing_injection_flags`.
    - `test_all_writers_call_read_existing_injection_flags` passes (proves patch applied to all 5).
    - Macro carry-forward integration test passes (proves `injection_flags` survives a body-changing rewrite).
    - Scope-lock test passes (proves OTHER `ingest_state` fields correctly reset on rewrite — `processed`, `processed_at`, `embedding_model`, `ingest_model`, `ingest_version`).
    - First-write default and malformed-prior tests pass.
    - Pre-existing test suite still green (no regressions; the k8h `_derived` carry-forward continues to work alongside the new `injection_flags` carry-forward).
  </done>
</task>

</tasks>

<verification>
End-to-end confirmation (operator-runnable, optional):

1. Find a vault doc with a populated `injection_flags` (likely none yet in
   prod — Phase 5 ingest worker writes them; if absent, manually inject one
   on a branch checkpoint by editing a doc's `ingest_state.injection_flags`
   to `["HIDDEN_INSTRUCTION"]`).
2. Run `uv run stock collect macro` (or whichever collector owns the doc).
3. `git diff vault/raw/.../{file}` → expected: `provenance.fetched_at`
   updated, body may change, `provenance.content_hash` may change, `_derived`
   preserved (k8h), AND `ingest_state.injection_flags` byte-identical to
   step 1. Other `ingest_state` fields (`processed`, etc.) reset to defaults.

Test commands:
- `uv run pytest tests/test_frontmatter.py::TestReadExistingInjectionFlags -v` (Task 1)
- `uv run pytest tests/test_collectors_preserve_derived.py -v` (Task 2)
- `uv run pytest tests/ -q` (regression — must remain green)
</verification>

<success_criteria>
- [ ] `read_existing_injection_flags` exists in `src/shared/frontmatter.py` with the locked signature `(path: Path) -> list[str] | None`.
- [ ] 4 unit tests pass: round-trip populated / missing file / malformed FM / empty-default-treated-as-None.
- [ ] All 5 collector writers (dart/kind/krx/macro/news) call `read_existing_injection_flags` before constructing `FrontMatter`.
- [ ] Macro integration test proves carried `injection_flags` survives a body-changing rewrite.
- [ ] Scope-lock test proves other `ingest_state` fields (`processed`, `processed_at`, `embedding_model`, `ingest_model`, `ingest_version`) correctly RESET on rewrite.
- [ ] `prior_injection_flags` is NEVER passed into content_hash computation in any writer.
- [ ] k8h's `_derived` carry-forward still works (no regression).
- [ ] Existing test suite remains green.
</success_criteria>

<output>
After completion, create `.planning/quick/260426-mic-preserve-injection-flags-in-ingest-state/260426-mic-SUMMARY.md` per template.
</output>
