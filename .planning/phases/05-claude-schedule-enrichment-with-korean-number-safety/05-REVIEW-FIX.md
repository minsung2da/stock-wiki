---
phase: 05-claude-schedule-enrichment-with-korean-number-safety
fixed_at: 2026-04-24T17:30:00Z
review_path: .planning/phases/05-claude-schedule-enrichment-with-korean-number-safety/05-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-04-24T17:30:00Z
**Source review:** .planning/phases/05-claude-schedule-enrichment-with-korean-number-safety/05-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (1 Critical + 4 Warnings; Info findings deferred)
- Fixed: 5
- Skipped: 0

## Fixed Issues

### CR-01: SKILL.md pre-flight uses non-existent import path

**Files modified:** `.claude/routines/enrich/SKILL.md`
**Commit:** 332e4ea
**Applied fix:** Replaced the bogus `from routines_enrich_helpers import walk`
pre-flight invocation with an explicit `PYTHONPATH` bootstrap that puts
`.claude/routines/enrich/helpers` and `src` on `sys.path`, then imports
`walk`, `zone_integrity`, `facts_equal` by their actual module names. Added
a Python-snippet variant for inline use, and a note that all helper-call
references in the Per-document loop assume the bootstrap has run.

### WR-01: `index_pt` regex guessed_unit not in NumericFact.unit Literal

**Files modified:** `src/shared/number_extraction.py`
**Commit:** 4296729
**Applied fix:** Removed `"index_pt"` from the `GuessedUnit` Literal and
mapped the `포인트` regex pattern to `guessed_unit="other"` (option (b) in
the review). Added an inline comment explaining the alignment with
`SANITY_RULES["KOSPI"|"KOSDAQ"]` which already use `unit="other"`. Now an
LLM that echoes the regex `guessed_unit` verbatim into the structured
output will produce a Pydantic-valid `NumericFact`.

### WR-02: `financials._pick_value` period ordering assumption

**Files modified:** `src/collectors/dart/financials.py`
**Commit:** 85ac868
**Applied fix:** Added a `_PERIOD_COL_RE = re.compile(r"^\d{8}$")` and made
`_pick_value` (a) detect YYYYMMDD-shaped period columns explicitly,
(b) sort them descending so the most-recent period is selected, and
(c) fall back to other non-`label_ko` numeric columns only if no period
columns are present (preserves prior behaviour for cassettes / shapes
without YYYYMMDD columns). Existing single-`value` cassette tests remain
green; multi-period live shapes now deterministically pick the latest.

### WR-03: `walk.find_candidates` swallows all parse errors silently

**Files modified:** `.claude/routines/enrich/helpers/walk.py`
**Commit:** ad2c724
**Applied fix:** Narrowed bare `except Exception` to
`except (ValueError, OSError, TypeError, KeyError)` so genuinely unexpected
failures (KeyboardInterrupt, MemoryError, etc.) propagate. Added a module-
level `LAST_PARSE_ERRORS: list[tuple[str, str]]` populated on every
`find_candidates` call (cleared at the start) so the Routines post-loop can
emit `malformed_frontmatter` BacklogItems for unparseable files. Also
prints a stderr warning per offending file so silent vanishing is
impossible. Signature kept as `list[Candidate]` to avoid breaking the test
suite; observability is provided via the side-channel attribute.

### WR-04: `disk_metrics` duplicates `.git` scan logic

**Files modified:** `src/ingest/disk_metrics.py`
**Commit:** 7b6709e
**Applied fix:** Deleted `_git_mb` and routed git measurement through
`_dir_mb(Path(repo_path) / ".git", exclude=())` so a single helper handles
both cases. Documented in `compute_disk_metrics` docstring that
`vault_path`, `repo_path`, `pgdata_path` must be non-overlapping (the
foot-gun the review flagged). Existing tests remain green: `_dir_mb` keeps
its `(".git",)` default when scanning the vault, and the explicit empty
exclusion is used only for the `.git` directory itself.

## Notes

- All four Info findings (IN-01, IN-02, IN-03) were out of scope for this
  iteration (`fix_scope=critical_warning`).
- Each fix was syntax-checked via `python3 -m ast` (Tier 2) before commit.
- Pre-existing test cassettes for `_pick_value` (single `value` column)
  remain valid; the YYYYMMDD path is exercised when live dart-fss frames
  reach the function. Adding a multi-period cassette test was suggested by
  the reviewer but is a follow-up — the production code now sorts
  defensively regardless.

---

_Fixed: 2026-04-24T17:30:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
