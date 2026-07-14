---
phase: 5
slug: briefing-renderer
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-14
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `05-RESEARCH.md` §Validation Architecture (all rows grounded in file:line evidence).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest `>=9.0` (`pyproject.toml:63`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths=["tests"]`, `pythonpath=["src"]`; markers `slow/e2e/db/live` |
| **DB fixtures** | `pg_engine` (session, runs `alembic upgrade head` once — `conftest.py:51-86`), `pg_clean` (function TRUNCATE incl. `decision_cards` — `conftest.py:97-145`), `seeded_engine` (삼성전자/005930 only — `tests/cards/conftest.py:101-124`) |
| **Quick run command** | `uv run pytest tests/briefing -x` |
| **Full suite command** | `uv run pytest` |
| **Migration roundtrip** | `alembic.command.upgrade/downgrade` vs testcontainers (pattern: `conftest.py:58-81`, `tests/test_migration.py`) |
| **Estimated runtime** | ~quick <30s / full ~several min (testcontainers Postgres spin-up) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/briefing -x` (+ the touched `tests/mcp_v2` / `tests/db` file).
- **After every plan wave:** Run `uv run pytest` (full suite, testcontainers Postgres).
- **Before `/gsd:verify-work`:** Full suite must be green.
- **Max feedback latency:** ~30 seconds (quick), full suite at wave boundaries.

---

## Per-Requirement Verification Map

> Task IDs are assigned by the planner (plans do not exist yet). Every row below is a
> deterministic property the plan's `<acceptance_criteria>` must assert. All test files
> are Wave 0 gaps (do not exist yet).

| SC / Decision | Behavior (deterministic property to assert) | Test Type | Automated Command | File Exists |
|---------------|---------------------------------------------|-----------|-------------------|-------------|
| SC#1 | >10 candidate events → exactly 10 entries (truncation) | unit | `uv run pytest tests/briefing/test_daily.py::test_truncates_to_ten -x` | ❌ W0 |
| SC#1 / D-01 | Fixed input → fixed priority order (held→event-class→conviction-desc) | unit | `uv run pytest tests/briefing/test_priority.py -x` | ❌ W0 |
| SC#1 / D-01 | Missing `portfolio.md` → no crash, held-tier collapses, order still deterministic | unit | `uv run pytest tests/briefing/test_priority.py::test_no_portfolio -x` | ❌ W0 |
| SC#1 / D-02 | HOLD→SELL across a superseded chain detected via `get_active`+`walk_supersedes` | integration(db) | `uv run pytest tests/briefing/test_diff.py -x` | ❌ W0 |
| SC#1 / D-03 | First card conv≥0.8 included; first card <0.8 excluded | unit | `uv run pytest tests/briefing/test_diff.py::test_first_card_rule -x` | ❌ W0 |
| SC#2 | NULL-corp briefing row INSERTs OK; analysis card with NULL corp REJECTED by partial CHECK | integration(db) | `uv run pytest tests/briefing/test_store_briefing.py -x` | ❌ W0 |
| SC#2 | migration 0009 up→down roundtrip (columns/CHECKs/index add+drop; `corp_code NOT NULL` restored) | integration(db) | `uv run pytest tests/db/test_migration_0009.py -x` | ❌ W0 |
| SC#3 | `body_md` header = `종목 \| 변화 \| 근거 \| 제안 \| Why now \| Why not`; 제안 = stance+conviction, no forecast text | unit | `uv run pytest tests/briefing/test_render.py -x` | ❌ W0 |
| SC#4 | `get_briefing(weekly)` returns stored row unchanged after the 7 dailies are mutated/deleted (proves no recompute) | integration(db) | `uv run pytest tests/briefing/test_weekly.py::test_no_recompute -x` | ❌ W0 |
| SC#4 / D-07 | Flip-flop BUY→HOLD→BUY nets to no-change (dropped); genuine start≠end retained | unit | `uv run pytest tests/briefing/test_weekly.py::test_net_change -x` | ❌ W0 |
| SC#4 / D-08 | 5 present / 2 missing dailies → `coverage: 5/7`, missing ≠ no-change | unit | `uv run pytest tests/briefing/test_weekly.py::test_coverage -x` | ❌ W0 |
| SC#5 | `get_briefing('daily')` reads `daily_briefing` row → found=True, entries populated; invalid type → InvalidArgument | integration(db) | `uv run pytest tests/mcp_v2/test_briefing_wired.py -x` | ❌ W0 |
| SC#5 / Veto#13 | `get_briefing` returns entries only (Briefing model has no body_md field) | unit | `uv run pytest tests/mcp_v2/test_briefing_wired.py::test_no_body_leak -x` | ❌ W0 |
| SC#6 | Empty collect-set → short row written; `get_briefing` returns found=True (NOT found=False, NOT empty page) | integration(db) | `uv run pytest tests/briefing/test_daily.py::test_no_change_writes_short_row -x` | ❌ W0 |

*Status legend: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/briefing/__init__.py` + `tests/briefing/conftest.py` — seed **multiple** entities + cards (existing `seeded_engine` seeds only 삼성전자/005930; truncation + multi-ticker priority need ≥11 tickers with active cards + superseded chains).
- [ ] `tests/db/test_migration_0009.py` — up/down roundtrip + partial-CHECK behavior.
- [ ] `tests/briefing/test_{daily,weekly,diff,priority,render,store_briefing}.py` — per the map above.
- [ ] `tests/mcp_v2/test_briefing_wired.py` — replaces the Phase-3 `test_portfolio_briefing.py:96-132` honest-empty guard (EXPECTED change, not a regression).
- [ ] No framework install needed — pytest + testcontainers already present.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | All Phase 5 behaviors have deterministic automated verification (no LLM call in the render path). |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s (quick)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-14
