---
phase: 04-multi-source-collector-coverage
plan: 05
subsystem: kind-collector
tags: [wave-2, kind, dart, exchange-events, option-d, coll-05]
dependency_graph:
  requires: [04-01]
  provides:
    - "collect_kind(vault_root, engine, since=None, enable_kind_scrape=False) → exchange status events to raw/kind/YYYY-MM/"
    - "DART_EXCHANGE_EVENT_PATTERNS + classify_dart_exchange_event() → report_nm → event_type mapping"
    - "KIND throttled_get/post client (1 req/sec, browser UA, SSRF scheme guard)"
    - "suspension_cross_check_mismatch heartbeat extra → Plan 02 reconciliation"
  affects: [04-06]
tech_stack:
  added: []
  patterns:
    - "Option D: DART pblntf_ty='I' primary for exchange-issued status events (fundamental axis); KIND AJAX auxiliary only"
    - "EUC-KR decode for KIND AJAX fragments (response.content.decode('euc-kr'))"
    - "Module-global monotonic throttle (1 req/sec) for single-flight rate limiting"
    - "SSRF scheme guard: _assert_kind_url() rejects non-https://kind.krx.co.kr URLs"
    - "Composite-key dedup: (event_type, ticker, event_date)"
key_files:
  created:
    - src/collectors/kind/sources.py
    - src/collectors/kind/client.py
    - src/collectors/kind/selectors.py
    - src/collectors/kind/dart_events.py
    - src/collectors/kind/scraper.py
    - src/collectors/kind/writer.py
    - src/collectors/kind/__init__.py
    - tests/collectors/kind/__init__.py
    - tests/collectors/kind/test_sources.py
    - tests/collectors/kind/test_client.py
    - tests/collectors/kind/test_scraper.py
    - tests/collectors/kind/test_writer.py
    - tests/collectors/kind/test_collect_kind.py
    - tests/fixtures/kind/admin_issue_list.html
    - tests/fixtures/kind/nfaith_status_page1.html
    - tests/fixtures/kind/trading_halt_list.html
    - tests/fixtures/kind/undisclosure_ajax_page1.html
    - tests/fixtures/kind/unfaithful_list_page1.html
    - tests/fixtures/kind/warning_risky_list.html
    - docs/kind-robots-snapshot.txt
  modified:
    - src/db/migrations/env.py
decisions:
  - "Option D supersedes D-14: pykrx exposes no market-status function; exchange status designations are fundamental-axis and must be sourced from DART+KIND"
  - "DART pblntf_ty='I' is primary source: verified 190/16/23 events/30d for suspension/watchlist/unfaithful"
  - "Classification by report_nm regex because pblntf_detail_ty is None across all samples"
  - "investment_caution/risk scraping deferred: captured warning_risky_list.html is a search-form shell, not data; DART 30d window had 0 such filings"
  - "KIND undisclosure AJAX auxiliary only, off by default (enable_kind_scrape=False)"
  - "alembic env.py disable_existing_loggers=False to preserve pytest caplog on non-alembic loggers"
metrics:
  duration_sec: 1800
  tasks_completed: 5
  tests_added: 25
  completed_date: 2026-04-20
requirements: [COLL-05]
---

# Phase 4 Plan 05: KIND Collector Summary

## Strategy Amendment (Option D) — IMPORTANT

**This plan's execution superseded the original D-14 hybrid strategy.** D-14
assumed pykrx exposes `get_market_status_by_ticker` for 관리종목/투자경고 flags.
Live verification on 2026-04-20 confirmed **this function does NOT exist** in
pykrx 1.0.51 or in its GitHub master branch — pykrx covers only market-price
data (OHLCV, 수급, 공매도), not exchange status designations.

### Operator's four-axis data frame

| Axis | Purpose | Sources |
|------|---------|---------|
| **기업 평가 (fundamental)** | Long-term investing — finding undervalued companies | DART (정기·주요사항·거래소공시), KIND (시장조치) |
| **시장가격 (market behavior)** | Long-term timing + short-term volatility | pykrx (OHLCV·수급·공매도) |
| **거시 맥락 (macro)** | Background conditions | ECOS, FRED |
| **변동성 신호 (sentiment)** | Short-term momentum | 뉴스 (한경·이데일리, semi_trusted) |

Exchange-issued status designations (거래정지·관리종목·투자경고·불성실공시) belong
to the **fundamental axis** — they are evaluations *by* the exchange *about*
the issuer. They therefore must be sourced from DART + KIND, not pykrx.

### Verified event volumes (DART `pblntf_ty="I"`, 30-day window, 2026-04-20)

| event_type | report_nm pattern | Observed 30d count |
|------------|-------------------|--------------------|
| `suspension` | `주권매매거래정지` (includes 기간변경) | 190 |
| `watchlist_designation` | `관리종목지정우려` | 16 |
| `unfaithful_disclosure` | `불성실공시법인지정` | 23 |
| `investment_caution` / `investment_risk` | *no matching pattern in DART* | 0 |
| `delisting` (extended, flag-gated) | `상장폐지` | 122 |
| `listing_eligibility_review` (extended) | `상장적격성 실질심사` | 15 |

`pblntf_detail_ty` was None for all samples → classification is by `report_nm`
regex (`DART_EXCHANGE_EVENT_PATTERNS` in `sources.py`).

### KIND endpoints

The only primary KIND endpoint used by this plan is
`https://kind.krx.co.kr/investwarn/undisclosure.do` (AJAX POST,
`method=searchUnfaithfulDisclosureCorpSub`, 15 rows/page, **EUC-KR encoded**).
It is *auxiliary* — DART already captures unfaithful_disclosure at higher
fidelity via `rcept_no`. `enable_kind_scrape=False` by default; operator may
flip once EUC-KR AJAX stability is confirmed in production.

The `investwarn/investattentwarnrisky.do` endpoint for 투자경고/위험 is a
live-rendered shell page whose data fragment is AJAX-loaded from a separate
(not-yet-probed) endpoint. Operator must run a follow-up probe to locate the
data fragment URL and schema before `investment_caution`/`investment_risk`
events can be collected. Documented under **Deferred** below.

### Follow-up action for CONTEXT.md

Request that **CONTEXT.md D-14 be amended in a follow-up commit** (not this
plan) to reflect:
1. Strategy Option D (4-axis frame).
2. DART `pblntf_ty="I"` as primary exchange-events source.
3. pykrx removed from Plan 05 scope.
4. `investment_caution`/`investment_risk` deferred.

---

## One-liner

`collect_kind` lands as Plan 05's final Wave-2 collector: DART `pblntf_ty="I"`
→ suspension / watchlist_designation / unfaithful_disclosure events classified
by `report_nm` regex, with optional EUC-KR KIND undisclosure AJAX cross-check,
1 req/sec throttle, SSRF scheme guard, content-hash idempotency, and
per-source heartbeat sub-blocks including `suspension_cross_check_mismatch`
reconciliation against Plan 02's `krx.suspended_tickers`.

## Tasks Completed

| Task | Name                                                                      | Commit    | Tests |
| ---- | ------------------------------------------------------------------------- | --------- | ----- |
| 1    | Probe fixtures + sources.py + docs/kind-robots-snapshot.txt               | `8b8f32f` | 0 (scaffold) |
| 2    | client.py + dart_events.py + scraper.py + selectors.py + writer.py + collect_kind + 25 tests + alembic-logger fix | `6e780cf` | 25 |

## Verification Evidence

```
$ uv run --group collectors --group db --group ingest --group dev \
    pytest tests/collectors/kind/ -x -q
25 passed, 1 warning in 12.09s

$ uv run --group collectors --group db --group ingest --group dev \
    pytest tests/test_import_guard.py tests/ \
    -k "frontmatter or heartbeat or dart or portfolio or entity_alias or krx or macro or news or kind" -q
152 passed, 1 skipped, 146 deselected, 1 warning in 51.82s

$ grep -rn "from src\." src/collectors/kind/ tests/collectors/kind/
(no matches — Phase 3 import style preserved)

$ grep -rn "anthropic\|openai" src/collectors/kind/*.py
(no matches — import guard clean)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Strategy correction] Option D supersedes D-14's pykrx hybrid**

- **Found during:** Wave-0 probe
- **Issue:** pykrx has no `get_market_status_by_ticker` function (nor any
  equivalent 관리종목 / 투자경고 status accessor); pykrx covers only market-
  price data.
- **Fix:** Pivoted to DART `pblntf_ty="I"` as the primary source and KIND
  undisclosure AJAX as auxiliary. Operator pre-approved this change.
- **Files modified:** `src/collectors/kind/sources.py` (strategy doc),
  `src/collectors/kind/__init__.py` (removed pykrx wiring)
- **Commit:** `8b8f32f`, `6e780cf`

**2. [Rule 3 — Blocking issue] alembic fileConfig disabled caplog loggers**

- **Found during:** Task 4 regression gate
- **Issue:** `src/db/migrations/env.py` called `fileConfig(...)` with default
  `disable_existing_loggers=True`. Once any `@pytest.mark.db` test triggered
  the session-scoped `pg_engine` fixture (which runs alembic upgrade), the
  existing `collectors.dart.fetcher` logger was disabled — breaking
  `test_dart_fetcher_retry.py::test_R3_warning_logged_per_retry` whenever a
  DB-marked test ran first in the session.
- **Fix:** `fileConfig(config.config_file_name, disable_existing_loggers=False)`.
- **Files modified:** `src/db/migrations/env.py`
- **Commit:** `6e780cf`

### Other

- **[Plan sketch deviation]** Plan 05's embedded code sketches targeted the
  old pykrx+KIND-scrape strategy and used `src.` prefixes in some places. All
  new modules use Phase-3 `from collectors.kind.* import ...` (no `src.` prefix).
- **[Scope extension]** Enum gained `investment_risk` so KIND's 경고 vs 위험
  distinction can eventually be captured without renaming. `investment_risk`
  is defined but unused in this plan (no implementing code path).

## Deferred

- **투자경고/투자위험 scraping:** the captured `warning_risky_list.html` is a
  search-form shell; its data fragment is AJAX-loaded from an endpoint not
  yet probed. DART 30-day window had 0 matches. Operator needs a follow-up
  probe (DevTools → Network on a live visit) to capture the fragment URL +
  schema. Tracked as Deferred-05-01.
- **KIND undisclosure AJAX in production:** `enable_kind_scrape` defaults to
  `False`. Flip once EUC-KR AJAX stability is validated in a live smoke run.
- **delisting / listing_eligibility_review events:** extended patterns exist
  (`DART_EXCHANGE_EVENT_PATTERNS_EXTENDED`) but are not wired into
  `KindEventType`. Enable when Plan 05-next (Phase 5?) is ready to handle
  these event types in the graph.

## Known Stubs

None. All code paths are exercised by fixture-driven tests; no placeholders
in `collect_kind`.

## Threat Flags

None. Changes are additive to existing trust-boundary-hardened modules:

- KIND client enforces `https://kind.krx.co.kr` scheme guard (T-04-10) + 1 req/sec
  throttle (T-04-16) + browser UA.
- Writer path construction is pre-filtered by event_type enum + ticker `^\d{6}$` +
  event_date `^\d{8}$` regexes (T-04-17).
- No new secrets (DART reuses Phase-3 `DART_API_KEY`; KIND is public).
- Heartbeat `extra` uses only non-secret flags (ticker lists, status strings).

## Self-Check: PASSED

**Files verified exist:**
- FOUND: src/collectors/kind/sources.py
- FOUND: src/collectors/kind/client.py
- FOUND: src/collectors/kind/selectors.py
- FOUND: src/collectors/kind/dart_events.py
- FOUND: src/collectors/kind/scraper.py
- FOUND: src/collectors/kind/writer.py
- FOUND: src/collectors/kind/__init__.py
- FOUND: tests/collectors/kind/test_sources.py
- FOUND: tests/collectors/kind/test_client.py
- FOUND: tests/collectors/kind/test_scraper.py
- FOUND: tests/collectors/kind/test_writer.py
- FOUND: tests/collectors/kind/test_collect_kind.py
- FOUND: tests/fixtures/kind/undisclosure_ajax_page1.html (+5 more)
- FOUND: docs/kind-robots-snapshot.txt

**Commits verified in `git log`:**
- FOUND: 8b8f32f (T1 — feat(04-05-T1) KIND Option-D scaffolding)
- FOUND: 6e780cf (T2 — feat(04-05-T2) KIND collector + collect_kind + tests)
