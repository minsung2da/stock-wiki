---
phase: 05-claude-schedule-enrichment-with-korean-number-safety
plan: 03
subsystem: shared
tags: [numbers, regex, korean, stage1, phase5]

requires:
  - phase: 05-claude-schedule-enrichment-with-korean-number-safety
    plan: 01
    provides: NumericFact v2 (Literal unit enum) — target schema consumed downstream
provides:
  - NumericCandidate dataclass (frozen) with codepoint-safe offsets
  - extract_numeric_candidates(body, section_hint) pure function
  - MAX_CANDIDATES_PER_DOC=100 overflow cap
  - 8 Korean-aware unit categories (KRW원/백만/억/조, shares, pct, bps, multiplier, index_pt, USD/JPY/EUR)
affects:
  - 05-04-number_sanity (will consume NumericCandidate output)
  - 05-08-routines-skill (will JSON-serialize candidates into Sonnet prompt; echo-back uses body[c.offset:c.offset+c.length])

tech-stack:
  added: []
  patterns:
    - "Longest-match + non-overlapping regex composition via ordered pattern table"
    - "Codepoint-indexed str slicing (Python native) as Hangul echo-back primitive"
    - "Pure function / pure stdlib (re) — no LLM, no I/O, no deps"

key-files:
  created:
    - src/shared/number_extraction.py
    - tests/test_number_extraction.py
    - tests/fixtures/number_extraction/hankyung_sample.md
    - tests/fixtures/number_extraction/dart_narrative_sample.md
  modified: []

key-decisions:
  - "Removed `\\b` word boundaries after Hangul unit suffixes (원/주/엔/배) — Python `\\b` is ASCII-word-based and fails between Hangul characters, silently suppressing matches"
  - "_NUM grouped into single non-capturing alternation `(?:comma-form|plain-form)` — bare alternation broke when embedded in larger compound patterns"
  - "Longest-first pattern order + claimed-range skip list: compound `4조 2,000억 원` beats short `4조` without lookahead contortions"

patterns-established:
  - "Regex module convention: NUM token wrapped in `(?:...)` for safe composition"
  - "Hangul-adjacent regex patterns: prefer context-shape (e.g., `\\s*조`) over `\\b` word boundary"

requirements-completed: [INGEST-07]

duration: ~12min
completed: 2026-04-25
---

# Phase 05 Plan 03: Korean Numeric Candidate Extractor Summary

**Pure-Python regex extractor (`src/shared/number_extraction.py`) returns `NumericCandidate` spans with codepoint-safe offsets and guessed unit — Stage 1 of the D-15 4-stage pipeline, feeding Sonnet 4.6 with enriched context so the LLM "selects and echoes" rather than invents numbers.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 2 (TDD RED → GREEN)
- **Files created:** 4 (1 module + 1 test file + 2 fixtures)

## Accomplishments

- `NumericCandidate` frozen dataclass with `raw_text`, `offset`, `length`, `guessed_unit`, `sentence_text`, `pre_context`, `post_context`, `section_hint`
- `extract_numeric_candidates(body, section_hint)` finds compound amounts (`4조 2,000억 원`), percentages (`5.3%`), multipliers (`15.2배`), bps (`50bps`), KRW (`72,000원`, `3,200억`, `12,345백만원`), shares (`100만 주`), FX (`1,400달러`), index points (`2,650포인트`)
- Codepoint-exact offset roundtrip on Hangul proven by `test_hankyung_offsets_roundtrip` — `body[c.offset:c.offset+c.length] == c.raw_text` holds for every candidate
- Non-overlapping longest-match: compound KRW pattern claims the span before the shorter subset can
- `MAX_CANDIDATES_PER_DOC=100` cap verified on 200-number synthetic body
- 7 fixture-backed tests, all green (`uv run pytest tests/test_number_extraction.py -x -q` → 7 passed in 0.94s)

## Task Commits

1. **Task 1 (RED)** — `700414c` (test): fixtures + failing tests for 7 behaviours
2. **Task 2 (GREEN)** — `f0ecbbb` (feat): 165 LOC regex extractor; all tests pass

## Files Created

- `src/shared/number_extraction.py` (165 LOC, well under 250 cap)
- `tests/test_number_extraction.py` (7 `def test_` functions)
- `tests/fixtures/number_extraction/hankyung_sample.md`
- `tests/fixtures/number_extraction/dart_narrative_sample.md`

## Decisions Made

- **Removed `\b` after Hangul suffixes.** Python `\b` uses ASCII word-char class; between two Hangul characters (e.g., `원을`) it doesn't fire, so `_NUM\s*원\b` silently missed `72,000원을`. Switched to the suffix-character itself as the boundary (the non-overlapping claim list already prevents cross-pattern bleed).
- **`_NUM` wrapped in non-capturing group.** The bare alternation `\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?` was embedded in larger patterns like `{_NUM}\s*조\s*{_NUM}\s*억` where the outer context only attached to the right branch of the alternation — the compound pattern only matched `4` instead of `4조 2,000억 원`. Wrapping in `(?:...)` and requiring `+` on the comma group forced the alternation to behave atomically.
- **Longest-first pattern ordering + claimed-range skip list.** Simpler than regex lookahead gymnastics; the code iterates patterns in a fixed priority order and a second-pass pattern skips any span already covered.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `\b` word boundary broke Hangul matches**
- **Found during:** Task 2 verify step
- **Issue:** Plan's regex pattern `{_NUM}\s*원\b` couldn't match `72,000원을` because `\b` requires an ASCII word/non-word transition; between two Hangul codepoints neither is a word-char so the boundary never fires.
- **Fix:** Dropped `\b` from Hangul-suffix patterns (원/주/엔/배). Retained `\b` only after `bps` (ASCII token where it's meaningful).
- **Files modified:** `src/shared/number_extraction.py`
- **Committed in:** `f0ecbbb`

**2. [Rule 1 - Bug] Bare alternation in `_NUM` collapsed compound patterns**
- **Found during:** Task 2 verify step
- **Issue:** Plan's `_NUM = r"\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?"` — when spliced into `rf"{_NUM}\s*조\s*{_NUM}\s*억"` the trailing `\s*조...` attaches only to the right branch, so `4조` matched but compound `4조 2,000억 원` didn't.
- **Fix:** Wrapped as `_NUM = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"`. Also tightened comma group to `+` (prefers comma form when available) so `72,000` prefers the comma alternation and emits a clean match.
- **Files modified:** `src/shared/number_extraction.py`
- **Committed in:** `f0ecbbb`

**3. [Rule 3 - Blocking] ruff SIM110 (loop → any()) on `_overlaps`**
- **Found during:** pre-commit hook
- **Issue:** pre-commit ruff rejected the initial explicit `for` loop in `_overlaps`.
- **Fix:** Rewrote as `return any(not (e <= cs or s >= ce) for cs, ce in claimed)`.
- **Files modified:** `src/shared/number_extraction.py`
- **Committed in:** `f0ecbbb`

**4. [Rule 3 - Blocking] Plan `uv run --extra dev pytest` flag not defined**
- **Found during:** acceptance verify
- **Issue:** Same as Plan 05-01: `dev` is not declared as an optional-dependency extra; plain `uv run pytest` resolves because dev deps are already synced.
- **Fix:** Used `uv run pytest tests/test_number_extraction.py -x -q` directly.

---

**Total deviations:** 4 auto-fixed (2 regex bugs, 2 tooling/blocker). All preserve the plan's intent — the regex categories, offset guarantees, and MAX_CANDIDATES_PER_DOC contract are unchanged.

## Acceptance Criteria Verification

- `test -f tests/fixtures/number_extraction/hankyung_sample.md` → exit 0
- `test -f tests/fixtures/number_extraction/dart_narrative_sample.md` → exit 0
- `grep -c "^def test_" tests/test_number_extraction.py` → **7**
- `grep -q "MAX_CANDIDATES_PER_DOC = 100" src/shared/number_extraction.py` → found
- `grep -q "@dataclass(frozen=True)" src/shared/number_extraction.py` → found
- `wc -l src/shared/number_extraction.py` → **156** (< 250)
- `uv run pytest tests/test_number_extraction.py -x -q` → **7 passed**

## Threat Model Check

- **T-05-03-01 (DoS regex backtracking):** Patterns are bounded — `_NUM` caps group widths via `\d{1,3}(?:,\d{3})+` (no nested unbounded quantifiers). `finditer` runs each compiled pattern once per body.
- **T-05-03-02 (Integrity offset/length on Hangul):** `test_hankyung_offsets_roundtrip` enforces `body[c.offset:c.offset+c.length] == c.raw_text` for every candidate on Hangul fixture — green.
- **T-05-03-03 (DoS 10K numbers):** `MAX_CANDIDATES_PER_DOC=100` cap verified on 200-span synthetic body. Overflow sentinel wiring is Plan 05-08's job (Routines skill).

No new threat surface introduced beyond the plan's threat_model.

## Next Phase Readiness

- Plan 05-04 can import `from shared.number_extraction import NumericCandidate, extract_numeric_candidates` and feed the echo-back / sanity-check pipeline directly.
- Plan 05-08 (Routines skill) can JSON-serialize `NumericCandidate` instances into the Sonnet prompt; each candidate's `offset` + `length` seeds the character-level echo-back validation.

## Self-Check: PASSED

- `src/shared/number_extraction.py` exists, contains `NumericCandidate`, `extract_numeric_candidates`, `MAX_CANDIDATES_PER_DOC` — FOUND
- `tests/test_number_extraction.py` exists with 7 tests — FOUND
- `tests/fixtures/number_extraction/{hankyung,dart_narrative}_sample.md` exist — FOUND
- Commit `700414c` (test RED) — FOUND in `git log`
- Commit `f0ecbbb` (feat GREEN) — FOUND in `git log`
- All 7 tests pass

---
*Phase: 05-claude-schedule-enrichment-with-korean-number-safety*
*Completed: 2026-04-25*
