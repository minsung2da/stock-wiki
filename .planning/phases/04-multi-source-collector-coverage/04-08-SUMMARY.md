---
phase: 04-multi-source-collector-coverage
plan: 08
subsystem: docs-ux
tags: [gap-closure, docs, cli, argparse, operator-experience, gap-04-05]

requires:
  - phase: 04-multi-source-collector-coverage
    provides: "Plan 01 R-09 startup guard (NoAliasesSeededError) surfaced the operator gap this plan documents"
  - phase: 04-multi-source-collector-coverage
    provides: "Plan 07 already closed Gap-04-03/04/06 (CLI defaults + ECOS filter); this plan closes the remaining Gap-04-05 docs/UX scope"
provides:
  - "CLAUDE.md First-time Setup section: 5-step bring-up from fresh clone to green `stock collect all`"
  - "`stock collect news --help` epilog pointing at `uv run python -m src.db.seed_name_aliases` precondition"
affects: []

tech-stack:
  added: []
  patterns:
    - "Pattern: when a startup guard is correct behavior (not a bug) but is surprising to first-run operators, close the gap with docs + --help hint — not by mutating the guard."
    - "Pattern: argparse `epilog=` kwarg renders below the help table, giving operators a discoverable precondition hint without polluting the one-line help string."

key-files:
  created:
    - .planning/phases/04-multi-source-collector-coverage/04-08-SUMMARY.md
  modified:
    - CLAUDE.md
    - src/cli/__main__.py

key-decisions:
  - "Document in CLAUDE.md (not README). CLAUDE.md is the canonical operator doc in this repo per CLAUDE.md convention. README.md + a standalone `stock setup` meta-command are explicitly deferred to backlog (gap scope)."
  - "Epilog copy is English. CLI help text throughout the codebase is English (argparse convention in src/cli/__main__.py); bilingual text would be inconsistent. Korean prose lives in CLAUDE.md where the surrounding content is Korean."

requirements-completed: [COLL-03]

duration: ~8 min
completed: 2026-04-18
---

# Phase 04 Plan 08: First-run Documentation Gap Closure Summary

**CLAUDE.md now has a First-time Setup section that tells a fresh operator exactly which 5 commands to run (including `seed_name_aliases`), and `stock collect news --help` points at the same seed command so operators who hit `NoAliasesSeededError` find the fix in the next terminal line.**

## Performance

- **Tasks:** 2/2 (both docs/text changes)
- **Files modified:** 2 (CLAUDE.md, src/cli/__main__.py)
- **Files created:** 1 (this SUMMARY)
- **Duration:** ~8 min
- **Tests added:** 0 (docs + help-text; verification is grep + `--help` subprocess)

## Accomplishments

- Gap-04-05 closed: `## First-time Setup` section inserted into CLAUDE.md between `<!-- GSD:project-end -->` and `<!-- GSD:stack-start -->`. 5 ordered steps, each with a code block: `uv sync` → `.env` config → `docker compose up -d postgres && alembic upgrade head` → `uv run python -m src.db.seed_name_aliases` → `uv run stock collect all` verification. Sentinel marker `<!-- GSD:first-run-setup-end -->` supports future grep-based validation.
- `stock collect news --help` now carries an `epilog=` string explaining the seed precondition and pointing at CLAUDE.md §First-time Setup. Verified by subprocess invocation — the epilog renders below the argparse help table exactly as intended.
- No GSD-managed marker content mutated. The insertion is strictly additive between two existing markers.
- Pre-commit hooks green on both commits (ruff + ruff-format + hardcoded-secret scan all passed for T2; T1 was doc-only with no Python files touched).

## Task Commits

| Task | Name                                                              | Commit    |
| ---- | ----------------------------------------------------------------- | --------- |
| 1    | CLAUDE.md First-time Setup section                                | `c9d9b6f` |
| 2    | `stock collect news --help` epilog                                | `4f056a9` |

## Files Created/Modified

- `CLAUDE.md` — added 43 lines (section + trailing marker + blank lines) between project-end and stack-start markers (Task 1, c9d9b6f)
- `src/cli/__main__.py` — expanded single-line `add_parser("news", help=...)` to multi-line call with `epilog=` kwarg; surrounding argparse structure untouched (Task 2, 4f056a9)
- `.planning/phases/04-multi-source-collector-coverage/04-08-SUMMARY.md` — this file (Task 3)

## Verification Evidence

Fresh runs (this session):

```
$ grep -q "^## First-time Setup$" CLAUDE.md && echo PASS
PASS

$ grep -q "seed_name_aliases" CLAUDE.md && echo PASS
PASS

$ grep -q "uv run alembic upgrade head" CLAUDE.md && echo PASS
PASS

$ grep -q "<!-- GSD:first-run-setup-end -->" CLAUDE.md && echo PASS
PASS

$ uv run python -m cli collect news --help 2>&1 | grep -q "seed_name_aliases" && echo PASS
PASS

$ uv run python -m cli collect news --help 2>&1 | grep -q "First-time Setup" && echo PASS
PASS

$ uv run pytest tests/test_cli.py tests/test_cli_collect_all.py tests/test_cli_default_flags.py tests/test_import_guard.py -x -q
28 passed in 11.27s
```

Rendered `stock collect news --help` output (tail):

```
usage: stock collect news [-h] [--since SINCE] [--max-per-feed MAX_PER_FEED]

options:
  -h, --help            show this help message and exit
  --since SINCE
  --max-per-feed MAX_PER_FEED

Requires: entity_aliases table seeded before first use. Run `uv run python -m
src.db.seed_name_aliases` once. See CLAUDE.md §First-time Setup.
```

## Decisions Made

1. **Place section between `<!-- GSD:project-end -->` and `<!-- GSD:stack-start -->`.** The plan's `<interfaces>` block called this out as the safe insertion point; it keeps all GSD-managed content untouched while placing operator bring-up adjacent to the project overview (logically where a new reader would look next).
2. **Do not add a `stock setup` meta-command.** The gap explicitly deferred this to backlog. A one-line README-style fix via docs + epilog is strictly cheaper and closes the symptom Gap-04-05 describes.
3. **Do not translate the argparse epilog to Korean.** Surrounding argparse `help=` strings in the same file are in English with only product names and Korean outlets in vernacular form. Matching that style keeps the CLI consistent.

## Deviations from Plan

None — plan executed exactly as written. Both commits passed pre-commit hooks on the first attempt; CLI keyword-suite regression (28 tests) green unchanged.

## Known Stubs

None. All content is load-bearing.

## Threat Flags

None. Docs-only + static argparse string. No new trust boundaries, no user input flows, no env-var coverage changes.

## Gap Coverage

| Gap ID | Coverage | Proof |
|--------|----------|-------|
| Gap-04-05 | ✅ Closed | `## First-time Setup` in CLAUDE.md with 5 ordered steps including `seed_name_aliases`; `stock collect news --help` epilog contains `seed_name_aliases` and `First-time Setup` references |

## User Setup Required

None new. This plan *documents* the existing setup requirements; it does not add any.

## Next Phase Readiness

Phase 04 now has all gap closures landed (Plans 04-07 + 04-08). The remaining operator action is the live `stock collect all` UAT re-run with real API keys — that is operator-driven validation, not further plan work. When the operator re-runs UAT with the newly-documented setup, all 4 source status values should be `ok` (or `partial` only where data legitimately lags), closing Phase 04 for good.

---
*Phase: 04-multi-source-collector-coverage*
*Completed: 2026-04-18*

## Self-Check: PASSED

**Files verified exist:**
- FOUND: CLAUDE.md (with `## First-time Setup` section)
- FOUND: src/cli/__main__.py (with epilog kwarg)
- FOUND: .planning/phases/04-multi-source-collector-coverage/04-08-SUMMARY.md

**Commits verified in `git log`:**
- FOUND: c9d9b6f (T1 — CLAUDE.md First-time Setup)
- FOUND: 4f056a9 (T2 — news --help epilog)
