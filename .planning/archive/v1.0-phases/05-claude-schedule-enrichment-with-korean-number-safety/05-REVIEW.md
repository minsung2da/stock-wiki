---
phase: 05-claude-schedule-enrichment-with-korean-number-safety
reviewed: 2026-04-24T16:58:56Z
depth: standard
files_reviewed: 23
files_reviewed_list:
  - .claude/routines/enrich/README.md
  - .claude/routines/enrich/SKILL.md
  - .claude/routines/enrich/helpers/__init__.py
  - .claude/routines/enrich/helpers/facts_equal.py
  - .claude/routines/enrich/helpers/walk.py
  - .claude/routines/enrich/helpers/zone_integrity.py
  - .claude/routines/enrich/prompts/derived_dart_b.md
  - .claude/routines/enrich/prompts/derived_kind.md
  - .claude/routines/enrich/prompts/derived_macro.md
  - .claude/routines/enrich/prompts/derived_news.md
  - src/collectors/dart/financials.py
  - src/ingest/backlog.py
  - src/ingest/disk_metrics.py
  - src/ingest/heartbeat.py
  - src/shared/frontmatter.py
  - src/shared/number_extraction.py
  - src/shared/number_sanity.py
  - src/shared/units.py
  - tests/test_backlog.py
  - tests/test_dart_financials.py
  - tests/test_disk_metrics.py
  - tests/test_enrich_walk.py
  - tests/test_facts_equal.py
  - tests/test_frontmatter_v2.py
  - tests/test_heartbeat_enrich.py
  - tests/test_number_extraction.py
  - tests/test_number_sanity.py
  - tests/test_skill_structure.py
  - tests/test_units.py
  - tests/test_zone_integrity.py
findings:
  critical: 1
  warning: 4
  info: 3
  total: 8
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-04-24T16:58:56Z
**Depth:** standard
**Files Reviewed:** 23 (source) + tests
**Status:** issues_found

## Summary

Phase 5 adds the Claude Schedule enrichment routine (SKILL.md + helpers) and
supporting Python for numeric safety, backlog, disk metrics, and heartbeat
extensions. Code quality is high overall: atomic writes are used consistently,
COLL-07 (no LLM SDK imports in collectors/ingest/shared) is explicitly tested,
and pure-function boundaries are well preserved. Validation coverage (echo-back,
sanity rules, self-consistency, zone integrity) is thorough and matches the
decision log.

The most serious issue is a runtime-breaking import instruction in `SKILL.md`
that references a non-existent package; the helpers are only importable through
`spec_from_file_location` or via `sys.path` injection, neither of which the
routine performs. Additional Warnings concern a unit-Literal mismatch between
regex extraction and the Pydantic schema (`index_pt`), an assumption about DART
period-column ordering, silent failure modes in the candidate walker, and
duplicated `.git` scan logic in disk_metrics.

## Critical Issues

### CR-01: SKILL.md pre-flight uses non-existent import path (routine will fail on first run)

**File:** `.claude/routines/enrich/SKILL.md:24`
**Issue:** The Pre-flight step instructs:

```
python -c "from routines_enrich_helpers import walk; print(len(walk.find_candidates('vault')))"
```

No package named `routines_enrich_helpers` exists. The helpers live at
`.claude/routines/enrich/helpers/` and are not registered in `pyproject.toml`,
not installed by `uv sync`, and not placed on `sys.path`. The tests import them
via `importlib.util.spec_from_file_location` precisely because they are not
importable as a normal module. The routine will raise `ModuleNotFoundError` on
the very first sanity check, and the Per-document loop's references to
`walk.find_candidates`, `compute_zone_hash`, `assert_zones_unchanged`,
`facts_equal` share the same problem.

**Fix:** Either install the helpers as a package, or prepend the helpers dir to
`sys.path` at routine startup. Replace the Pre-flight line and all helper-call
references with an explicit loader, for example:

```bash
export PYTHONPATH=".claude/routines/enrich/helpers:src:${PYTHONPATH}"
python -c "import walk; print(len(walk.find_candidates('vault')))"
```

or add a `conftest.py`-equivalent bootstrap at the top of the routine:

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(".claude/routines/enrich/helpers").resolve()))
sys.path.insert(0, "src")
from walk import find_candidates
from zone_integrity import compute_zone_hash, assert_zones_unchanged
from facts_equal import facts_equal
```

Add a test that executes the exact command the routine runs (not just the
helpers in isolation) so future drift is caught.

## Warnings

### WR-01: `index_pt` regex guessed_unit cannot be persisted as `NumericFact.unit`

**File:** `src/shared/number_extraction.py:29-32`, `src/shared/frontmatter.py:127-141`
**Issue:** `extract_numeric_candidates` emits candidates with `guessed_unit="index_pt"` for KOSPI/KOSDAQ/포인트 patterns, but `NumericFact.unit` is a
Pydantic `Literal` that does not include `"index_pt"`. The sanity table maps
index keys to `unit="other"` (`number_sanity.py:54-55`) — a silent convention
the prompts do not document. If the LLM echoes the regex `guessed_unit`
verbatim into the structured output (the natural behavior), Pydantic validation
fails and the entire document is null-out per F-1b — a persistent false
negative for every index-containing document.

**Fix:** Either (a) add `"index_pt"` to the `NumericFact.unit` Literal and
update `SANITY_RULES` to use it, or (b) change the regex to emit
`guessed_unit="other"` for 포인트/index patterns and document the mapping in
each prompt. Option (b) is less invasive:

```python
# number_extraction.py
(rf"{_NUM}\s*포인트", "other"),  # was "index_pt"
```

Add an explicit assertion:

```python
from shared.frontmatter import NumericFact
_VALID_UNITS = set(NumericFact.model_fields["unit"].annotation.__args__)
for _pat, _unit in _PATTERNS:
    assert _unit in _VALID_UNITS or _unit == "index_pt", _unit
```

and pair it with a test that attempts to construct a `NumericFact` from every
`guessed_unit` the extractor can emit.

### WR-02: `financials._pick_value` silently returns leftmost numeric — period ordering assumption unverified

**File:** `src/collectors/dart/financials.py:78-100`
**Issue:** Docstring says "we take the leftmost non-null numeric column other
than `label_ko`." dart-fss live frames have multiple period columns
(`20250930`, `20240930`, ...), and column order is not contractually specified
by the library. If a row is structured `[label_ko, 20240930, 20250930]`
(ascending), the extractor records the older period as the authoritative value
and every DART cross-check (D-17) may disagree. There is no test covering a
multi-period live shape — only cassettes with a single `value` column
(`test_dart_financials.py:37`).

**Fix:** Sort period columns explicitly by YYYYMMDD descending and pick the
first. Add a test with a multi-period cassette that asserts the most recent
period is chosen:

```python
def _pick_value(row: Any) -> float | None:
    if "value" in row.index:
        ...
    period_cols = [c for c in row.index if c != "label_ko" and re.fullmatch(r"\d{8}", str(c))]
    for col in sorted(period_cols, reverse=True):
        ...
```

### WR-03: `walk.find_candidates` swallows all parse errors silently

**File:** `.claude/routines/enrich/helpers/walk.py:47-50`
**Issue:** `except Exception: continue` with the comment "malformed frontmatter;
human review via backlog" — but nothing is written to the backlog. A
systematically poisoned file (for example, all DART docs with a Pydantic schema
drift) would vanish from enrichment forever and never surface in the operator
backlog or heartbeat. This defeats the observability intent of D-25.

**Fix:** Collect failures and surface them to the caller so the Post-loop block
can emit a `missing_derived` or new `malformed_frontmatter` BacklogItem:

```python
@dataclass(frozen=True)
class WalkReport:
    candidates: list[Candidate]
    parse_errors: list[tuple[str, str]]  # (path, exc repr)

def find_candidates(vault_root) -> WalkReport:
    ...
    except Exception as e:
        errors.append((str(md_path), repr(e)))
        continue
```

At minimum, narrow the bare `Exception` to `(ValueError, OSError)` so truly
unexpected errors (memory, interrupt-driven) propagate.

### WR-04: `disk_metrics` duplicates `.git` scan logic and omits exclusion in `_git_mb`

**File:** `src/ingest/disk_metrics.py:14-43`
**Issue:** `_dir_mb` already accepts an `exclude` tuple and defaults to
`(".git",)`. `_git_mb` re-implements the same logic but cannot skip nested
`.git` worktrees or packed refs it was never supposed to include. More
importantly, when a caller passes `pgdata_path` that happens to live under the
repo (`pgdata_path=".docker/pgdata"`), the `_dir_mb` exclusion still only
covers `.git`, so pgdata is double-counted into `vault_mb` if placed inside
`vault/`. Not an immediate bug with the documented call sites, but a latent
foot-gun as configuration expands.

**Fix:** Collapse `_git_mb` into `_dir_mb` with explicit exclusion override
(`_dir_mb(path, exclude=())`), and document that `vault_path`, `repo_path`,
`pgdata_path` must be non-overlapping — or explicitly exclude pgdata from the
vault scan when they overlap:

```python
def _dir_mb(path, exclude=(".git",)):
    ...

def compute_disk_metrics(...):
    vault_mb = _dir_mb(vault_path)
    git_mb   = _dir_mb(Path(repo_path) / ".git", exclude=())
    ...
```

## Info

### IN-01: `heartbeat.compute_enrich_alert_level` reads `docs_processed` from `extra` but caller assembles it in `new_block`

**File:** `src/ingest/heartbeat.py:130-136`
**Issue:** Contract is implicit: `record_source_run` passes `extra=new_block`
(which already merges `stats.succeeded → docs_processed`), and
`compute_enrich_alert_level` then reads `extra.get("docs_processed", 0)`. If a
future refactor separates the two dicts, the flagged-ratio check will silently
divide by zero-default and report no alert. Consider making
`docs_processed` an explicit kwarg.

**Fix:** Change signature to
`compute_enrich_alert_level(*, docs_processed, docs_review_flagged, backlog_count, consecutive_failures, last_run_iso=None, now_iso=None)` and have the caller unpack explicitly.

### IN-02: `number_sanity.check_sanity` unknown-key pass-through hides schema drift

**File:** `src/shared/number_sanity.py:93-95`
**Issue:** Returning `None` for unknown `fact.key` is documented as defensive,
but it means a typo in the LLM's `key` field ("매출액 " with trailing space,
"매출 액") bypasses all validation. Combined with the `extra="forbid"` rule
on the block, a typo still slips through because `key` is a plain `str`. A
warning when `fact.key` appears to match a known-canonical-prefix-but-not-exact
would catch most cases.

**Fix:** Optional — emit a soft `review_flag` of `numeric_sanity_violation`
with `detail="unknown_key"` when the key is not in SANITY_RULES and the doc is
not a DART structured-path document.

### IN-03: `walk._derived_is_populated` also treats `skip_reason` as populated — correct but comment mixes two concerns

**File:** `.claude/routines/enrich/helpers/walk.py:26-37, 53-58`
**Issue:** Both the `_derived_is_populated` helper and the subsequent
`skip_reason` check test `fm.derived.skip_reason`. The code is correct (either
sticky-skip path reaches `continue`), but the redundancy makes the logic
harder to audit. Recommend one source of truth.

**Fix:** Drop `skip_reason` from `_derived_is_populated` and rely on the
explicit F-4c clause at `walk.py:53-55`; add a one-line comment:

```python
def _derived_is_populated(fm) -> bool:
    # skip_reason is handled by the F-4c sticky check in find_candidates
    d = fm.derived
    return bool(d.tickers or d.event_type or d.catalysts
                or d.sentiment is not None or d.numeric_facts or d.summary)
```

---

_Reviewed: 2026-04-24T16:58:56Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
