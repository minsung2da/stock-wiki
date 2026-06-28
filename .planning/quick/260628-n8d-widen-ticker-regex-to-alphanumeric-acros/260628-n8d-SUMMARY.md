---
phase: quick-260628-n8d
plan: 01
subsystem: shared / mcp_v2 read-side / cards
tags: [validation, ticker, krx, alphanumeric, mh9-followup]
requires: [260628-mh9 (write-path widening)]
provides: read/analysis/shared ticker guards widened to ^[0-9A-Z]{6}$
affects: [cards.DecisionCard, mcp_v2.models, mcp_v2.tools.market, shared.frontmatter, shared.portfolio]
key-files:
  modified:
    - src/cards/models.py
    - src/mcp_v2/models.py
    - src/mcp_v2/tools/market.py
    - src/mcp_v2/errors.py
    - src/shared/frontmatter.py
    - src/shared/portfolio.py
    - tests/cards/test_models.py
    - tests/mcp_v2/test_market.py
    - tests/test_frontmatter_news_fields.py
    - tests/test_portfolio.py
metrics:
  tasks: 2
  files: 10
  completed: 2026-06-28
---

# Phase quick-260628-n8d: Widen Ticker Regex to Alphanumeric (Read/Shared Side) Summary

Widened the remaining five read/analysis/shared ticker guards from digit-only
`^[0-9]{6}$` to uppercase-alphanumeric `^[0-9A-Z]{6}$`, closing the mh9
write-accepts / read-rejects split so a stored new-style KRX code (e.g. `0001A0`
= 덕양에너젠) now round-trips end-to-end. corp_code guards left UNCHANGED.

## Task 1 — Widen 5 ticker code sites + sync prose (commit `c59d276`)

5 ticker code sites widened to `^[0-9A-Z]{6}$`:
- `src/cards/models.py:80` — `DecisionCard.ticker` Field(pattern=…)
- `src/mcp_v2/models.py:48` — `_TICKER_PATTERN` constant (shared by OhlcvRange/FlowRange/PortfolioHolding)
- `src/mcp_v2/tools/market.py:46` — `_TICKER_RE` compiled regex (ohlcv_range/flow_range guard)
- `src/shared/frontmatter.py:32` — `TickerRef.ticker` Field(pattern=…)
- `src/shared/portfolio.py:21` — `_TICKER_RE` (Holding + watchlist validators)

Prose synced to "uppercase-alphanumeric" wording (no test asserts on these):
`mcp_v2/models.py` module docstring, `mcp_v2/errors.py` (2 docstrings),
`mcp_v2/tools/market.py` (module docstring + pre-filter comment + both function
Args/Raises docstrings + both `InvalidArgument` messages), `portfolio.py` (2
ValueError messages), `frontmatter.py` (convenience-field comment). ASCII-class
rationale (`str.isdigit` accepts superscripts) preserved — guard stays ASCII-only.

corp_code `^[0-9]{8}$` left intact at all 4 sites (cards/models:79,
mcp_v2/models:49, market.py:47, frontmatter:33) — grep-confirmed.

Verify grep:
- stale `[0-9]{6}` ticker literal: ZERO matches across the touched files.
- widened `[0-9A-Z]{6}`: present at all 5 code sites + synced prose.
- corp_code `[0-9]{8}`: all 4 occurrences unchanged.

## Task 2 — Unit tests + regression (commit `48c183f`)

Added accept/reject matrix tests to the four existing test files (reused, no new files):
- **Accept**: `0001A0`, `005930`, `AAAAAA`, `0A0A0A`
- **Reject**: `00593` (5-char), `0059300` (7-char), `0001a0` (lowercase),
  `0001A!` (path/shell metachar), `0;DROP` (SQL metachar), `²²²²²²` (non-ASCII superscript)

Coverage per guard: `DecisionCard.ticker` (parametrized accept/reject);
`mcp_v2 _TICKER_RE` + `re.compile(_TICKER_PATTERN)` both checked + `OhlcvRange(ticker="0001A0")`
constructs (DB-free); `frontmatter.TickerRef` accept/lowercase-reject;
`portfolio.Holding` + watchlist YAML accept + lowercase-reject.

### Test results (exact counts)
- Targeted (`tests/cards/test_models.py tests/mcp_v2/test_market.py tests/test_frontmatter_news_fields.py tests/test_portfolio.py tests/test_ticker_shape.py`): **142 passed, 2 warnings** in 19.68s
- Full regression (`tests/mcp_v2 tests/cards tests/shared tests/db`): **211 passed, 2 skipped, 18 warnings** in 32.10s

The 2 skips and all warnings are pre-existing (halfvec/vector type SAWarnings,
authlib/alembic deprecations) — unrelated to this change. No previously-passing
test regressed. Tests use testcontainers/pg_clean, never the live DB.

## TDD Gate Compliance

Task 2 is tagged `tdd="true"`, but the plan deliberately ordered Task 1
(implementation) before Task 2 (verification tests); the widened guards already
existed when the tests were written, so the tests passed immediately (GREEN) with
no preceding RED commit. This is by plan design (mechanical regex widening), not a
gate violation — the accept matrix would have failed against the pre-mh9
`^[0-9]{6}$` literal and the reject matrix guards the new boundary.

## Deviations from Plan

None — plan executed exactly as written. corp_code guards confirmed untouched.

## Self-Check: PASSED

- All 6 source files + 4 test files modified (Edit calls succeeded).
- Commits exist: `c59d276` (Task 1, 6 files), `48c183f` (Task 2, 4 files).
- Grep gate: zero stale `[0-9]{6}` ticker literals; widened literal at all 5 sites;
  corp_code `[0-9]{8}` intact.
- Regression green: 211 passed, 2 skipped.
