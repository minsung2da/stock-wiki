---
phase: 05-claude-schedule-enrichment-with-korean-number-safety
plan: 06
subsystem: backlog
tags: [backlog, observability, markdown, phase5]

requires:
  - phase: 05-claude-schedule-enrichment-with-korean-number-safety
    plan: 01
    provides: DerivedBlock v2 (upstream skip_reason / review_flags context)
provides:
  - "BacklogItem dataclass + render_backlog(today_items, prior_path, now) pure function"
  - "First-seen carryover keyed on (path + flag) across runs"
  - "Chronic items (>=3 days) auto-detection"
  - "Prior non-today sections preserved verbatim; today section regenerated"
  - "schema_version: 1 frontmatter for future migration"
affects:
  - 05-08-routines-skill (post-loop calls render_backlog and writes vault/ingested/_status/backlog.md)
  - Phase 6 MCP health tool (parses schema_version:1 backlog.md — deferred)
  - Phase 8 Dataview dashboard chronic-items banner (deferred)

tech-stack:
  added: []
  patterns:
    - "Pure-function rendering: prior_path read is the only I/O; caller owns atomic write"
    - "Regex table-row parser tolerant to malformed rows (silently skips)"
    - "Frontmatter block stripped via explicit \\n--- sentinel search (not YAML parse)"

key-files:
  created:
    - src/ingest/backlog.py
    - tests/test_backlog.py
  modified: []

key-decisions:
  - "BacklogItem uses compound key path::flag for first_seen lookup — two flags on same path track independently"
  - "Tolerant regex parser over YAML parse for prior backlog: schema drift in older files cannot crash today's run (T-05-06-02 mitigation)"
  - "Today's section always regenerated from today_items; stale prior today section dropped — prevents accumulation if multiple runs occur in one day (per D-25)"
  - "Preserved prior sections appended after today + chronic + horizontal rule — stable reading order newest-first"

patterns-established:
  - "Render-from-disk + pure-function composition: Plan 05-08 Routines skill calls render_backlog(today_items, prior_path=...), writes result atomically"
  - "Tolerant parsing of self-generated artifacts: prior file assumed self-compatible but parsed defensively"

requirements-completed: [INGEST-03, INGEST-04]

metrics:
  duration: ~5min
  started: 2026-04-24T16:28:33Z
  completed: 2026-04-24T16:33:00Z
  tasks: 2
  files: 2
  test_count: 10

completed: 2026-04-24
---

# Phase 05 Plan 06: Backlog Renderer Summary

**`src/ingest/backlog.py::render_backlog` — pure function that produces `vault/ingested/_status/backlog.md` content from today's flagged items, carrying first_seen forward across runs and surfacing chronic items persisting >=3 days. Routines skill (05-08) post-loop calls it directly.**

## Performance

- **Duration:** ~5 min
- **Tasks:** 2 (TDD RED -> GREEN)
- **Files created:** 2 (1 module + 1 test)
- **Tests:** 10/10 pass

## Accomplishments

- `BacklogItem` dataclass with `category` (Literal of 5), `path`, `flag`, `note`, `first_seen` (filled by render_backlog), and `key()` helper returning `path::flag` compound identifier.
- `BacklogCategory` Literal enforces the 5 known categories per D-25.
- `CHRONIC_DAYS = 3`, `SCHEMA_VERSION = 1` module-level constants.
- `render_backlog(today_items, prior_path, now)` builds frontmatter + today's dated section (5 category subsections + chronic items) + preserved prior sections.
- `_parse_prior_first_seen` regex-scans prior table rows to build `{path::flag -> date}` map; tolerant to malformed rows (header, separator, date parse errors all silently skipped).
- `_extract_prior_nontoday_sections` strips frontmatter then walks `## YYYY-MM-DD` headers, preserving verbatim every section whose date differs from today.
- Empty categories render as `*(none)*`; chronic absent renders as `*(none)*` — no empty tables.

## Task Commits

1. **RED** — `6b33b3c` (`test(05-06): add failing tests for ingest.backlog render_backlog`)
2. **GREEN** — `a21e66c` (`feat(05-06): implement ingest.backlog render_backlog (D-25)`)

## Decisions Made

- **Compound key `path::flag`** instead of path-only: same document can have multiple flag types simultaneously (e.g. `numeric_echo_mismatch` + `self_inconsistent`); each tracks first_seen independently.
- **Regex parse over YAML** for prior file: prior backlog is self-generated but a schema-v2 migration (deferred per D-25) could break full-YAML load; tolerant row-scan is robust and O(N).
- **Today's section always regenerated** (stale today dropped) — prevents accumulation if routine fires twice in one day, matches D-25 wording "매 schedule run에 오늘 날짜 섹션을 regenerate".
- **Preserved sections appended after chronic**, separated by horizontal rule; ordering = newest-first reading.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `uv run --extra dev` flag — `dev` is not a declared extra**
- **Found during:** plan verify command
- **Issue:** pyproject.toml uses `[dependency-groups]` (PEP 735), not `[project.optional-dependencies]`, so `--extra dev` would error.
- **Fix:** used `uv run pytest ...` directly (deps resolved via default sync). Same deviation Plan 05-01 and 05-08 documented.
- **Files modified:** none (command-level only)

**2. [Rule 3 - Blocking] ruff-format reflow of test file**
- **Found during:** first git commit attempt
- **Issue:** pre-commit ruff-format broke long-string asserts into multi-line parenthesized form, and ran twice to converge. Plan's inline-string asserts were >100 chars.
- **Fix:** accepted the formatter rewrite verbatim (no test semantics change; only layout).
- **Files modified:** `tests/test_backlog.py`
- **Commit:** `6b33b3c`

**Total deviations:** 2 auto-fixed (both blocking command/lint, zero architectural).

## Acceptance Criteria Verification

Fresh verification at 2026-04-24T16:33Z:

- `grep -q "def render_backlog" src/ingest/backlog.py` -> found
- `grep -q "CHRONIC_DAYS = 3" src/ingest/backlog.py` -> found
- `grep -q "SCHEMA_VERSION = 1" src/ingest/backlog.py` -> found
- `grep -q "@dataclass" src/ingest/backlog.py` -> found
- `uv run python -c "from ingest.backlog import render_backlog, BacklogItem; print('ok')"` -> `ok`
- `uv run pytest tests/test_backlog.py -x -q` -> **10 passed in 0.75s**
- `grep -c "^def test_" tests/test_backlog.py` -> **10** (>= plan's 10 minimum)
- `wc -l src/ingest/backlog.py` -> **198** (< 280 budget)

## Threat Model Check

Threat register dispositions satisfied:
- **T-05-06-01** (operator tampers first_seen): accepted by design; git history is the audit trail. Not code-mitigated.
- **T-05-06-02** (malformed prior file): mitigated. `_parse_prior_first_seen` and `_extract_prior_nontoday_sections` silently skip unparseable rows / sections; frontmatter rebuilt from scratch every run.
- **T-05-06-03** (path disclosure on public push): accepted per CONTEXT "vault is private-by-convention". Not code-mitigated.
- **T-05-06-04** (10K-row prior DoS): mitigated. Regex row-scan is O(N); 10K lines of markdown is low-MB.

No new threat surface introduced.

## Next Phase Readiness

- **Plan 05-07** (heartbeat-enrich) proceeds in parallel wave — no dependency between them.
- **Plan 05-08** already integrates `render_backlog` via its SKILL.md post-loop step (delivered earlier in this phase). Integration test happens at deploy smoke-run.
- **Phase 6 MCP health tool** can now parse `schema_version: 1` backlog.md (deferred).

## Self-Check: PASSED

- `src/ingest/backlog.py` — FOUND (198 LOC)
- `tests/test_backlog.py` — FOUND (10 tests)
- Commit `6b33b3c` (RED) — FOUND in `git log`
- Commit `a21e66c` (GREEN) — FOUND in `git log`
- 10/10 tests pass
- All 4 acceptance grep markers present

---
*Phase: 05-claude-schedule-enrichment-with-korean-number-safety*
*Completed: 2026-04-24*
