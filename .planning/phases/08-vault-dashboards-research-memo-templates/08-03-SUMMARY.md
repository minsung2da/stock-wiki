---
phase: 08-vault-dashboards-research-memo-templates
plan: 03
subsystem: dashboards-dataview-bootstrap
tags: [phase-8, dashboards, dataview, obsidian, dql, security]
requires:
  - .obsidian/ (Obsidian vault root)
  - notes/private/portfolio.md (D-05 Holdings/Watchlist SoT)
  - dashboards/_data/prices.md (Plan 08-02 derived prices)
  - vault/raw/{dart,news,kind} (collector outputs)
provides:
  - dashboards/portfolio.md
  - dashboards/watchlist.md
  - dashboards/events-this-week.md
  - .obsidian/community-plugins.json (dataview registration)
  - .obsidian/plugins/dataview/data.json (D-17 settings)
affects:
  - .gitignore (negative pattern carve-out for the two settings files)
tech_added: []
tech_patterns:
  - "DQL-only dashboards (zero DataviewJS, T-08-03-01 mitigation)"
  - "Cross-folder DQL FROM (notes/private + dashboards/_data + vault/raw)"
  - ".gitignore negative-pattern exception for committed plugin settings"
key_files_created:
  - dashboards/portfolio.md
  - dashboards/watchlist.md
  - dashboards/events-this-week.md
  - .obsidian/community-plugins.json
  - .obsidian/plugins/dataview/data.json
  - tests/dashboards/__init__.py
  - tests/dashboards/test_dataview_bootstrap.py
  - tests/dashboards/test_portfolio_dashboard_skeleton.py
  - tests/dashboards/test_watchlist_dashboard_skeleton.py
  - tests/dashboards/test_events_dashboard_skeleton.py
key_files_modified:
  - .gitignore
decisions:
  - "DQL-only across all 3 dashboards — DataviewJS explicitly disabled in data.json (enableDataviewJs:false, enableInlineDataviewJs:false). Removes RCE surface (T-08-03-01)."
  - ".gitignore negative-pattern exception added for the two committed plugin settings files. Base ignore rules still cover plugins state and other plugins/*."
  - "portfolio.md flags Pitfall 3 (frontmatter list indexing) as a UAT open question — DQL holdings × prices join may yield empty table if notes/private/portfolio.md uses markdown table instead of frontmatter list. Plan 04 follow-up if UAT confirms."
metrics:
  duration: "≈15 min (RED+GREEN x 2 tasks + UAT-driven fix; Task 3 re-verification pending)"
  tasks_completed: 2
  tasks_total: 3
  tests_added: 14
  tests_pass: "14/14 (tests/dashboards/)"
  files_created: 10
  files_modified: 3
  completed: 2026-05-06 (pending re-UAT after bracket-form fix)
---

# Phase 08 Plan 03: Dashboards + Dataview Bootstrap Summary (PARTIAL — UAT pending)

3 Dataview-only dashboards (portfolio / watchlist / events-this-week) committed alongside Obsidian Dataview plugin bootstrap (D-16/D-17/D-18). All 12 skeleton + bootstrap tests green. Task 3 is a `checkpoint:human-verify` UAT — execution paused for user visual verification in Obsidian.

## Outcome

After this plan ships:
- Opening the vault in Obsidian auto-prompts Dataview install via `.obsidian/community-plugins.json`.
- `.obsidian/plugins/dataview/data.json` ships with D-17 recommended settings (`enableDataviewJs: false`, `renderNullAs: "—"`, `refreshInterval: 2500`).
- Three dashboards render Holdings/Watchlist/Events from the existing SoT files (`notes/private/portfolio.md`, `dashboards/_data/prices.md`, `vault/raw/{dart,news,kind}`).
- DataviewJS is structurally impossible — disabled in settings AND absent from all three markdown files.

DASH-01 / DASH-02 / DASH-03 requirements are land-able subject to UAT approval.

## Dataview Settings (D-17 Verbatim)

| Key | Value | Why |
|-----|-------|-----|
| `enableDataviewJs` | `false` | T-08-03-01 RCE mitigation |
| `enableInlineDataview` | `true` | Required for `as_of` inline expression in portfolio.md |
| `enableInlineDataviewJs` | `false` | T-08-03-01 mitigation (inline JS path) |
| `renderNullAs` | `"—"` | Empty cell rendering |
| `warnOnEmptyResult` | `true` | Surface empty queries during UAT |
| `refreshEnabled` | `true` | Auto-refresh derived data |
| `refreshInterval` | `2500` | 2.5s tick |

## Dashboards Shipped

### `dashboards/portfolio.md` (D-06 + D-08)
- 2 DQL blocks: Holdings × 평가액 join (`notes/private/portfolio.md` FLATTEN file.lists WHERE section="Holdings", joins `dashboards/_data/prices.md` via `this.prices[ticker]`), and 보유종목 7일 이벤트 (`vault/raw` FROM + `dur(7 days)` window).
- Inline DQL freshness label `as_of` linked to `dashboards/_data/prices.md` frontmatter.
- Plain-Korean caveat note about the Pitfall 3 frontmatter list indexing question (deferred to UAT).

### `dashboards/watchlist.md` (D-07)
- 1 DQL block: pulls `## Watchlist` rows from the same `notes/private/portfolio.md` (no separate file).
- Columns: 티커 / 종목명 / 관심 이유.

### `dashboards/events-this-week.md` (D-09)
- 1 DQL block over `"vault/raw/dart" OR "vault/raw/news" OR "vault/raw/kind"`.
- 7-day window via `dur(7 days)`.
- Priority sort via nested `choice()`: 공시 > 거래정지 > 실적 > others, then `provenance.date DESC`.
- Columns: 날짜 / 티커 / 이벤트 / 제목 / 소스 / 링크. LIMIT 50.

## Test Counts

| File | Tests | Coverage |
|------|------:|----------|
| `tests/dashboards/test_dataview_bootstrap.py` | 3 | community-plugins.json registration, D-17 exact dict match, DataviewJS off |
| `tests/dashboards/test_portfolio_dashboard_skeleton.py` | 4 | ≥2 DQL blocks + dashboards/_data ref, no dataviewjs, as_of present, bracket-form `_derived` guard |
| `tests/dashboards/test_watchlist_dashboard_skeleton.py` | 2 | DQL block + portfolio.md SoT ref, no dataviewjs |
| `tests/dashboards/test_events_dashboard_skeleton.py` | 5 | DQL + vault/raw, event_type, dur(7 days), no dataviewjs, bracket-form `row["_derived"]` enforced |
| **Total** | **14** | All green |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `.gitignore` negative-pattern carve-out**
- **Found during:** Task 1 GREEN — `git add` rejected `.obsidian/community-plugins.json` and `.obsidian/plugins/dataview/data.json` because the base `.gitignore` (committed pre-Phase 8) ignored both `.obsidian/community-plugins.json` and `.obsidian/plugins/`.
- **Issue:** D-16 explicitly says these two files MUST be committed for the auto-install prompt to work, but the existing `.gitignore` blanket-ignored them.
- **Fix:** Added a Phase 8-tagged negative-pattern block in `.gitignore`:
  ```
  # Phase 8 D-16/D-17: commit Dataview plugin bootstrap (settings, not state)
  !.obsidian/community-plugins.json
  !.obsidian/plugins/
  !.obsidian/plugins/dataview/
  !.obsidian/plugins/dataview/data.json
  ```
  All other `.obsidian/plugins/*` and `.obsidian/plugins/*/data.json.bak` patterns still apply — only the two D-16/D-17 settings files are carved out.
- **Files modified:** `.gitignore`
- **Commit:** `f38e10a`

**2. [Rule 1 - Bug] UAT-discovered: Dataview DQL parser rejects `_derived.x` dotted form**
- **Found during:** Task 3 visual UAT (user reported `events-this-week.md` PARSING FAILED at column after `provenance.date AS "날짜",`).
- **Root cause:** Dataview DQL grammar treats leading-underscore identifiers (`_derived`) as illegal in dotted-path expressions. Bracket-form `row["_derived"].field` is required.
- **Fix:** Converted all 6 occurrences across 2 files:
  - `dashboards/portfolio.md` line 30 (TABLE clause in 7일 이벤트 query): 1 occurrence
  - `dashboards/events-this-week.md` lines 12, 13, 20, 21, 22 (TABLE × 2 + nested SORT choice() × 3): 5 occurrences
  - `dashboards/watchlist.md`: no change (does not reference `_derived`)
- **Regression guard:** Two new tests with regex `(?<!["\w/])_derived\.` — fails build if any future edit reintroduces bare dotted form. Path/string contexts (e.g., `dashboards/_data`, `frontmatter.as_of`) are excluded by the negative-lookbehind.
- **Files modified:** `dashboards/portfolio.md`, `dashboards/events-this-week.md`, `tests/dashboards/test_events_dashboard_skeleton.py`, `tests/dashboards/test_portfolio_dashboard_skeleton.py`
- **Commit:** `57100d0`

### Other Deviations

None. Plan executed as written for Task 1 (RED→GREEN) and Task 2 (RED→GREEN). UAT round 1 surfaced the bracket-form bug above; round 2 awaiting user re-verification.

## Authentication Gates

None encountered.

## Verification Evidence

```
$ uv run pytest tests/dashboards/ --no-header -v
collected 14 items

tests/dashboards/test_dataview_bootstrap.py::test_community_plugins_includes_dataview PASSED
tests/dashboards/test_dataview_bootstrap.py::test_dataview_data_json_recommended_settings PASSED
tests/dashboards/test_dataview_bootstrap.py::test_dataviewjs_disabled PASSED
tests/dashboards/test_events_dashboard_skeleton.py::test_file_exists_with_dataview PASSED
tests/dashboards/test_events_dashboard_skeleton.py::test_event_type_priority_visible PASSED
tests/dashboards/test_events_dashboard_skeleton.py::test_derived_uses_bracket_form PASSED
tests/dashboards/test_events_dashboard_skeleton.py::test_seven_day_window PASSED
tests/dashboards/test_events_dashboard_skeleton.py::test_no_dataviewjs PASSED
tests/dashboards/test_portfolio_dashboard_skeleton.py::test_file_exists_with_dataview_block PASSED
tests/dashboards/test_portfolio_dashboard_skeleton.py::test_no_dataviewjs PASSED
tests/dashboards/test_portfolio_dashboard_skeleton.py::test_freshness_indicator PASSED
tests/dashboards/test_portfolio_dashboard_skeleton.py::test_derived_uses_bracket_form_when_referenced PASSED
tests/dashboards/test_watchlist_dashboard_skeleton.py::test_file_exists_with_dataview PASSED
tests/dashboards/test_watchlist_dashboard_skeleton.py::test_no_dataviewjs PASSED

============================== 14 passed in 0.76s ==============================
```

```
$ ! grep -r '```dataviewjs' dashboards/   # exit 1 = no match
$ grep -l '```dataview' dashboards/*.md | wc -l
3
$ python3 -c "import json; d=json.load(open('.obsidian/plugins/dataview/data.json')); assert d['enableDataviewJs']==False"
(no output = ok)
```

## UAT Gate (Task 3 — Awaiting User)

User must verify in Obsidian:
1. Open vault → Dataview auto-install prompt appears → install + enable.
2. Open `dashboards/portfolio.md`:
   - `## Holdings × 평가액` table renders (empty table is OK if notes/private/portfolio.md is empty).
   - `as_of` freshness label visible.
3. Open `dashboards/watchlist.md`: Watchlist table renders.
4. Open `dashboards/events-this-week.md`: 이벤트 표 + event_type priority sort works.
5. Report: `approved` or describe DQL/render issues per dashboard.

Open question (RESEARCH A3): if holdings × prices join yields empty table, follow-up Plan 04 will mirror `## Holdings` to a frontmatter list or generate a derived `dashboards/_data/portfolio_holdings.md`.

## Self-Check: PASSED

**Files:**
- FOUND: dashboards/portfolio.md
- FOUND: dashboards/watchlist.md
- FOUND: dashboards/events-this-week.md
- FOUND: .obsidian/community-plugins.json
- FOUND: .obsidian/plugins/dataview/data.json
- FOUND: tests/dashboards/__init__.py
- FOUND: tests/dashboards/test_dataview_bootstrap.py
- FOUND: tests/dashboards/test_portfolio_dashboard_skeleton.py
- FOUND: tests/dashboards/test_watchlist_dashboard_skeleton.py
- FOUND: tests/dashboards/test_events_dashboard_skeleton.py

**Commits:**
- FOUND: cae15af (Task 1 RED — bootstrap tests)
- FOUND: f38e10a (Task 1 GREEN — bootstrap files + .gitignore carve-out)
- FOUND: 1090da2 (Task 2 RED — 9 skeleton tests)
- FOUND: 4f669af (Task 2 GREEN — 3 dashboards)
- FOUND: 57100d0 (UAT fix — bracket-form `_derived` access + regression guards)

**Live state:**
- 14/14 dashboard tests passing
- DataviewJS structurally absent (settings + content)
- All `_derived` references use bracket form `row["_derived"].field` (UAT fix)
- Task 3 UAT round 2 awaiting user re-verification in Obsidian
