# Quick Task 260426-k8h: preserve `_derived` — Research

**Researched:** 2026-04-26
**Confidence:** HIGH (codebase-grounded, all paths verified by direct read)

## Summary

Five collectors (`macro/krx/news/dart/kind`) each build a fresh
`FrontMatter(provenance=...)` and call `shared.frontmatter.write_frontmatter()`,
which serializes `model.model_dump(by_alias=True, exclude_none=True)` —
overwriting the on-disk `_derived` block with the model's default empty
`DerivedBlock()`. None of the five currently reads the prior file's
`_derived`. Macro and KIND already use `read_frontmatter`/regex for OTHER
fields (observations / content_hash) but ignore `_derived`.

**Primary recommendation:** Add `read_existing_derived(path) -> DerivedBlock | None`
in `src/shared/frontmatter.py`. Each writer calls it BEFORE constructing
`FrontMatter(...)` and, when not None, passes `derived=<block>` to the
constructor. Single-line patch per collector.

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Apply fix to ALL 5 collectors (macro/krx/news/dart/kind), not just macro.
- Always preserve `_derived` verbatim — collector NEVER invalidates.
  Routine's `walk.find_candidates` is the single freshness gate.
- Helper lives in `src/shared/frontmatter.py`, signature
  `read_existing_derived(path: Path) -> DerivedBlock | None`.
- Returns `None` on missing file, malformed FM, or absent `_derived`.

### Claude's Discretion
- Test coverage: at least 1 unit test for the helper (4 cases minimum).
- Per-collector integration tests deferred unless plan-checker flags it.

### Deferred Ideas
- D-19 walk.find_candidates is NOT modified.
- Per-collector integration tests (deferred).

## Write Path Per Collector (verified)

| Collector | Writer module | Write fn | Reads existing FM today? | Status |
|-----------|--------------|----------|--------------------------|--------|
| macro | `src/collectors/macro/writer.py` | `write_macro_doc` | YES — `_read_existing_observations` (line 61) reads `provenance.observations` and `provenance.content_hash`; ignores `_derived`. | **Loses `_derived`** (proven case) |
| krx | `src/collectors/krx/writer.py` | `write_krx_doc` | NO — never reads prior file. Always builds fresh `FrontMatter`. | Loses `_derived` on overwrite |
| news | `src/collectors/news/writer.py` | `write_news_doc` | NO — always fresh. | Loses `_derived` on overwrite (rare; URL-hash path is usually unique) |
| dart | `src/collectors/dart/writer.py` | `write_filing` | NO — always fresh. (rcept_no path is normally unique → overwrites rare but possible if filing is re-fetched) | Loses `_derived` on overwrite |
| kind | `src/collectors/kind/writer.py` | `write_kind_event` | YES (regex) — `_read_existing_hash` (line 77) regex-greps `content_hash:`; short-circuits if hash matches. Does NOT read `_derived`. | Loses `_derived` only when hash actually changes (least likely, but still structurally exposed) |

**Common pattern in all 5:** every writer ends with
```python
fm = FrontMatter(provenance=ProvenanceBlock(...))   # NO derived= kwarg
write_frontmatter(str(path), fm, body)
```
Default `DerivedBlock()` (empty) is what gets dumped to YAML.

**Patch shape (uniform across all 5):**
```python
prior_derived = read_existing_derived(path)
fm = FrontMatter(
    provenance=ProvenanceBlock(...),
    **({"derived": prior_derived} if prior_derived is not None else {}),
)
```
or equivalently `derived=prior_derived or DerivedBlock()` — same on-disk
result because `DerivedBlock()` defaults dump to empty lists which `exclude_none`
filters down to a tiny stub. (Use the conditional form for cleaner diffs.)

## Existing `read_frontmatter` Helper

`src/shared/frontmatter.py:207`:

```python
def read_frontmatter(path: str) -> tuple[FrontMatter, str]:
    # Raises FileNotFoundError if missing
    # Raises ValueError if YAML malformed OR Pydantic validation fails
```

Returns `(FrontMatter, body)`. `FrontMatter.derived` is always populated
(defaults to empty `DerivedBlock()` via `Field(default_factory=...)` and
`alias="_derived"`). So composition is trivial:

```python
def read_existing_derived(path: Path) -> DerivedBlock | None:
    if not path.exists():
        return None
    try:
        fm, _ = read_frontmatter(str(path))
    except (ValueError, OSError):
        return None
    # Distinguish "absent" from "default empty": check if any field is non-default.
    # Reuse walk._derived_is_populated heuristic OR just return fm.derived
    # unconditionally (returning an empty block is harmless — same as default).
    return fm.derived
```

**Design note:** Returning the empty `DerivedBlock` even when nothing was
populated is BEHAVIORALLY EQUIVALENT to returning `None` (both produce the
same YAML output via `exclude_none=True`). But CONTEXT.md spec says "returns
None if `_derived` absent". Recommend treating "all fields default" as
absent for clarity. Use the same heuristic as `walk._derived_is_populated`
(`.claude/routines/enrich/helpers/walk.py:35`) to keep behavior consistent
across the boundary.

## Pitfalls / Corner Cases

1. **Malformed frontmatter** — `read_frontmatter` raises `ValueError`. Helper
   MUST catch `(ValueError, OSError)` and return `None`. Do NOT log/raise —
   `walk.find_candidates` (which scans the same file later) already records
   malformed-FM into `LAST_PARSE_ERRORS` for backlog observability. Silent
   `None` return here avoids double-noise.

2. **`_derived` fails Pydantic validation** — folded into case 1: any
   ValidationError surfaces as `ValueError` from `read_frontmatter` (line 224).
   Returning None means the collector writes a fresh empty `_derived`,
   which is the safest possible behavior (no partial restore).

3. **First-time write (no prior file)** — `path.exists()` short-circuit
   returns `None`. Collector writes default empty `DerivedBlock()`. Exactly
   today's behavior. No change.

4. **Order of operations — content_hash provenance:** All 5 writers compute
   `content_hash` from the NEW body (`compute_body_hash(body)` in dart/krx/kind,
   `_body_hash(body)` in macro, `compute_news_content_hash(title, body)` in
   news). The helper read of prior file is for `_derived` ONLY — never feeds
   into the new content_hash. **No risk of hash poisoning.** This must be
   stated in the helper docstring so future maintainers don't try to
   "optimize" by reusing the prior FrontMatter object.

5. **Macro special case:** macro already has `existing_hash == content_hash`
   short-circuit at line 134 — when that fires, no write happens and the
   prior `_derived` is preserved by virtue of the file being untouched. Patch
   only matters for the OTHER branch (hash changed → rewrite). Same for
   KIND's hash short-circuit at line 118.

## Zone-Integrity Interaction

`zone_integrity.compute_zone_hash()` hashes
`provenance + ingest_state` ONLY (`.claude/routines/enrich/helpers/zone_integrity.py:21-30`).
`_derived` is NOT in the hash payload. Carrying `_derived` forward across a
collector rewrite cannot trip `ZoneViolationError`.

Note that the zone-integrity check fires inside the Routine (before/after
LLM write), not at collector write time — so even a hypothetical change to
provenance during a collector rewrite (which DOES happen: `fetched_at`,
`content_hash` update) is outside zone-integrity's scope. **No interaction.**

## walk.find_candidates Interaction

Verified at `.claude/routines/enrich/helpers/walk.py:79-84`:

```python
if fm.derived.skip_reason is not None and stored == actual:
    continue
if _derived_is_populated(fm) and stored == actual:
    continue
```

Two scenarios after the fix lands:

| Scenario | Stored hash | Actual body hash | derived populated? | walk decision |
|----------|------------|------------------|---------------------|---------------|
| Idempotent re-collect (body unchanged) | matches | matches | YES (carried) | **SKIP** ✓ correct |
| Body changed, prior derived carried | new hash written by collector | matches new | YES (carried) | **PICK UP, reason=hash_changed** ✓ correct |
| First-ever collect | written | matches | NO | PICK UP, reason=missing_derived ✓ correct |

**Carry-forward is a SAFETY NET, not a perf optimization.** When body
changes, walk still re-enriches because `stored == actual` succeeds (collector
just stored a new hash) but the OUTER hash comparison happens against the
file content, not against the prior frontmatter — re-read the code: `stored`
comes from `fm.provenance.content_hash` (just-written by collector =
new hash), `actual` = `compute_content_hash(file)` = same new hash =>
they MATCH. So `_derived_is_populated` AND `stored==actual` ⇒ **SKIP**.

⚠️ **This means carrying forward `_derived` will cause walk to skip docs
where the body changed but the prior `_derived` is now stale.** This is
the intended, locked behavior per CONTEXT.md: "the Routine's existing logic
handles the 'content_hash changed → re-enrich' case for free; collector
preservation just means the Routine has the prior enrichment to fall back on
if the body is structurally similar."

**However**, re-reading `walk.find_candidates`: `stored` is read from the
file's frontmatter at scan time. After the collector writes the new hash,
`stored == actual` is ALWAYS true (the file was just written consistently).
So the only way walk re-enriches a doc with non-empty `_derived` is via the
OLD-hash path, which doesn't exist after a collector rewrite.

🚨 **PLANNER ATTENTION:** This is a behavior change worth flagging in the
plan. Today: every macro re-collect → fresh empty `_derived` → walk picks
up (reason=missing_derived) → re-enrich. After fix: every macro re-collect
with carried `_derived` → walk skips because `_derived` populated and hash
matches. If the body genuinely changed but the carried `_derived` is stale
(e.g., new observations added shifting sentiment), there is no automatic
re-enrichment trigger. CONTEXT.md explicitly accepts this tradeoff (locked
decision: "collector never invalidates"). No code action needed — just
make sure the plan TASKS section calls this out for the human reviewer.

## Test Pattern Reference

`tests/test_frontmatter.py:136-163` — `TestFileReadWrite.test_write_and_read_file`
uses the `tmp_vault: Path` fixture, builds a `FrontMatter`, writes it, reads
it back, and asserts field equality. Mirror this for the helper:

```python
def test_read_existing_derived_round_trip(tmp_vault: Path) -> None:
    p = tmp_vault / "doc.md"
    populated = DerivedBlock(tickers=["005930"], summary="hi")
    fm = FrontMatter(
        provenance=ProvenanceBlock(source="dart", content_hash="x"),
        derived=populated,
    )
    write_frontmatter(str(p), fm, "body")
    got = read_existing_derived(p)
    assert got == populated

def test_read_existing_derived_missing_file(tmp_path: Path) -> None:
    assert read_existing_derived(tmp_path / "nope.md") is None

def test_read_existing_derived_malformed(tmp_path: Path) -> None:
    p = tmp_path / "bad.md"
    p.write_text("---\nnot: [valid yaml\n---\nbody")
    assert read_existing_derived(p) is None

def test_read_existing_derived_no_derived_block(tmp_vault: Path) -> None:
    p = tmp_vault / "no_d.md"
    fm = FrontMatter(provenance=ProvenanceBlock(source="dart", content_hash="x"))
    write_frontmatter(str(p), fm, "body")
    assert read_existing_derived(p) is None  # default empty -> treated as absent
```

`tmp_vault` fixture exists in `tests/conftest.py` (used by existing
test_write_and_read_file).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Read+modify+write FM | YAML re-emit by hand | `read_frontmatter` + `write_frontmatter` (already atomic via tempfile + os.replace) |
| Detect "is `_derived` populated?" | New regex/heuristic | Reuse `walk._derived_is_populated` logic verbatim (or import it — but importing across `src/` ↔ `.claude/routines/` is a layering smell; copy the 7-line function instead) |
| Atomic write | tempfile+rename ad-hoc | `write_frontmatter` already does it (line 252) |

## Files To Touch (planning hint)

1. `src/shared/frontmatter.py` — add `read_existing_derived()` (~15 LOC).
2. `src/collectors/macro/writer.py` — line 137-152: insert call before
   `FrontMatter(...)`, add `derived=` kwarg.
3. `src/collectors/krx/writer.py` — line 83-97: same pattern.
4. `src/collectors/news/writer.py` — line 78-95: same pattern.
5. `src/collectors/dart/writer.py` — line 69-83: same pattern.
6. `src/collectors/kind/writer.py` — line 122-136: same pattern.
7. `tests/test_frontmatter.py` (or new `tests/test_read_existing_derived.py`) —
   4 helper unit tests above.

## Open Questions

None blocking. The "stale `_derived` after body change" tradeoff is locked
in CONTEXT.md and just needs to be highlighted in the plan summary so the
human reviewer sees it.

## Sources

- HIGH: Direct reads of all 6 source files + 2 routine helpers + 1 test file (codebase ground truth, 2026-04-26).
- HIGH: CONTEXT.md (locked user decisions).

## RESEARCH COMPLETE

**File:** `/mnt/c/Users/minsu/workspace/stock/.planning/quick/260426-k8h-preserve-derived-block-when-collectors-r/260426-k8h-RESEARCH.md`
