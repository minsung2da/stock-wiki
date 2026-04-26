# Quick Task 260426-k8h: preserve _derived block when collectors re-write a doc with new observations - Context

**Gathered:** 2026-04-26
**Status:** Ready for planning

<domain>
## Task Boundary

When a collector (macro/krx/news/dart/kind) re-writes a vault/raw markdown
document because new observations or new fetched data are available, the
existing `_derived` block (populated by the Phase 5 Routine) is currently
lost. The collector's frontmatter template overwrites `_derived` with an
empty placeholder (`tickers: [], catalysts: [], numeric_facts: [], ...`).

This was discovered on 2026-04-26 when `stock collect macro` produced fresh
ECOS/FRED snapshots; all 4 prior Routine-enriched `_derived` blocks were
wiped, forcing a full re-enrichment cycle on every collect run. Symptom is
zero-data-loss but unbounded token cost growth and stale local state until
the next Routine fires.

The fix: collectors must read the existing file (if present) and carry
forward its `_derived` block verbatim into the new write — without the
collector ever inspecting or judging whether `_derived` is "stale". The
Routine's `walk.find_candidates` already gates re-enrichment on content_hash
change, so the agent layer makes the freshness decision.

</domain>

<decisions>
## Implementation Decisions

### Scope (which collectors get the fix)
- **All collectors that may overwrite a doc:** macro + krx + news + dart + kind.
- Even though only macro is the proven failure case today, the symptom is
  structural (every collector goes through a similar write path), so a
  shared helper applied uniformly avoids whack-a-mole later.

### Invalidation policy (what happens on content_hash change)
- **Always preserve `_derived` verbatim.** The collector never invalidates.
- Rationale: the Routine's `walk.find_candidates` is the single source of
  truth for "needs re-enrichment". It uses content_hash + presence of
  `_derived` to decide. If the collector additionally invalidated, there
  would be two competing freshness gates, and we'd lose the ability to
  ever ship "obs appended but enrichment still valid" cases (e.g., a macro
  series gaining 1 daily observation without any narrative change).
- The Routine's existing logic handles the "content_hash changed → re-enrich"
  case for free; collector preservation just means the Routine has the
  prior enrichment to fall back on if the body is structurally similar.

### Code location
- **Shared helper in `src/shared/frontmatter.py`.**
- Signature (proposed): `read_existing_derived(path: Path) -> DerivedBlock | None`
- Returns `None` if file missing, frontmatter unparsable, or `_derived`
  absent. Returns the parsed `DerivedBlock` otherwise.
- Each collector's writer calls this before constructing the new
  `FrontMatter()` and assigns the returned block to `fm.derived`
  (or skips if None — uses the default empty block).
- Single function, ~30 LOC, easy to test exhaustively in one place.

### Claude's Discretion
- Test coverage: at least one unit test for the shared helper (covers
  missing file, no frontmatter, no `_derived`, populated `_derived`
  round-trip). Per-collector integration tests deferred unless plan-checker
  flags coverage gap.
- Naming: `read_existing_derived` chosen over `carry_forward_derived` —
  reads more clearly at the call site, doesn't assume the caller's intent.
- Atomicity: collectors already use atomic tempfile + os.replace for
  writes; the read happens before any write so there's no race window.
- D-19 walk.find_candidates is NOT modified — its behavior already
  composes correctly with carried-forward `_derived`.

</decisions>

<specifics>
## Specific Ideas

The triggering symptom (operator-witnessed 2026-04-26):
```
$ stock collect macro
{... "macro": {"status": "ok", "docs_processed": 4 ...}}

$ git diff --stat vault/raw/macro/
 vault/raw/macro/ecos/722Y001.md    | 39 +++++++---------------------
 vault/raw/macro/ecos/731Y001.md    | 53 +++++---------------------------------
 vault/raw/macro/fred/DCOILWTICO.md | 47 +++++----------------------------
 vault/raw/macro/fred/DGS10.md      | 39 +++++-----------------------
 4 files changed, 28 insertions(+), 150 deletions(-)
```
Files SHRANK because the collector wrote an empty `_derived` placeholder
(4 lines) where the prior Routine had written 30+ lines of `tickers/event_type/
catalysts/sentiment/numeric_facts/summary`.

</specifics>

<canonical_refs>
## Canonical References

- `.planning/phases/05-claude-schedule-enrichment-with-korean-number-safety/05-HUMAN-UAT.md`
  — Phase 5 closeout records this issue under "Phase 5.1 follow-up" notes
  as the trigger for this quick task.
- `src/shared/frontmatter.py` — defines `FrontMatter`, `DerivedBlock`,
  zone separation contract (D-07: provenance / ingest_state / _derived).
- `.claude/routines/enrich/helpers/walk.py` — `find_candidates` gates
  re-enrichment; this fix preserves the data it relies on.

</canonical_refs>
