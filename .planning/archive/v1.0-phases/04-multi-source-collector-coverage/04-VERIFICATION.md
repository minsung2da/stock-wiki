---
phase: 04-multi-source-collector-coverage
verified: 2026-04-20T15:15:12Z
status: human_needed
score: 5/5 success criteria verified (automated); 1 live-smoke behavior awaits human UAT
overrides_applied: 0
re_verification: # N/A — initial verification
  previous_status: null
requirements_verified: [COLL-02, COLL-03, COLL-04, COLL-05]
amendments_accepted:
  - decision: "D-14 hybrid (pykrx + DART + KIND) → Option D (DART pblntf_ty='I' primary for 3/4 event types + KIND aux)"
    accepted_by: "operator"
    accepted_at: "2026-04-20"
    rationale: "pykrx 1.0.51 (and GitHub master) exposes no 관리종목/투자경고/거래정지 status accessor. Verified live during Plan 05 Wave-0 probe. Operator pre-approved via 4-axis conceptual frame: exchange-issued status designations are fundamental-axis (DART+KIND), not market-price-axis (pykrx). Phase intent (capture 거래정지·관리종목·불성실공시) is fully preserved — ROADMAP SC #4 enumerates exactly those three types and all three are implemented."
    follow_up: "CONTEXT.md D-14 text still documents the original hybrid strategy. Follow-up commit should amend D-14 to reflect Option D; outside the scope of this verification."
deferred:
  - truth: "investment_caution / investment_risk event_types (CONTEXT D-08 enum) are defined but not implemented"
    addressed_in: "Deferred-05-01 (follow-up probe outside phase 4)"
    evidence: "KindEventType enum includes INVESTMENT_CAUTION + INVESTMENT_RISK; no DART_EXCHANGE_EVENT_PATTERNS mapping, no KIND fragment parser. ROADMAP SC #4 only names 거래정지 / 관리종목 / 불성실공시 — those three are implemented (DART pblntf_ty='I' → SUSPENSION + WATCHLIST_DESIGNATION + UNFAITHFUL_DISCLOSURE). Per operator guidance, ROADMAP SC is the binding contract; D-08 enum values were scoped beyond the roadmap and the investment_caution/risk pair is out-of-scope for phase 4 goal."
    judgment: "out-of-scope (roadmap-binding interpretation)"
human_verification:
  - test: "Live `stock collect all` smoke run"
    expected: |
      After setting DART_API_KEY, ECOS_API_KEY, FRED_API_KEY in .env and running
      `uv run stock collect all 2> report.json`:
      - stderr JSON matches D-20 schema: {run_at, sources: {krx, news, macro, kind: {status, docs_processed, elapsed_ms}}}
      - vault/raw/krx/YYYY-MM-DD/005930.md, 000660.md written with OHLCV+flow+short merged frontmatter
      - vault/raw/news/YYYY-MM/{hankyung,edaily}_*.md written for matched tickers only (2-paragraph body)
      - vault/raw/macro/{ecos,fred}/*.md written with observations[] frontmatter + body table
      - vault/raw/kind/YYYY-MM/*.md written for scoped ticker exchange events (if any in window)
      - vault/ingested/_status/heartbeat.md updated with per-source sub-blocks
      - Force one source to fail (e.g., unset FRED_API_KEY) → other 3 still complete, exit 1, JSON reports partial/error for failed one only
    why_human: "Requires live network + real API keys + observational validation of Obsidian vault contents. Phase VALIDATION.md §Manual-Only explicitly lists this as operator smoke run."
---

# Phase 4: Multi-Source Collector Coverage Verification Report

**Phase Goal:** Beyond DART, the vault receives KRX prices + investor flow + short balance, Korean economy news from at least two outlets, macro indicators from ECOS and FRED, and KIND trading-halt/관리종목/불성실공시 events. Each collector is an isolated module: one source failing does not block the others, and reruns are idempotent.

**Verified:** 2026-04-20T15:15Z
**Status:** human_needed (all automated evidence passes; live-smoke run awaits operator UAT per VALIDATION.md §Manual-Only)
**Re-verification:** No — initial verification

---

## Goal Achievement — ROADMAP Success Criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | `collect_krx` writes daily OHLCV + investor flow + short-position balance per watchlist/portfolio ticker to `vault/raw/krx/YYYY-MM-DD/*.md` | VERIFIED | `src/collectors/krx/__init__.py:43 def collect_krx(vault_root, engine, since=None, heartbeat_path=None)`; `fetcher.py` has `fetch_ohlcv` / `fetch_trading_value` / `fetch_shorting_balance` (pykrx); writer merges all three into single frontmatter. `tests/collectors/krx/test_collect_krx.py` covers holiday skip, R-03 missing-entity, per-ticker isolation, idempotency. 14/14 tests green. |
| 2 | `collect_news` uses trafilatura + RSS to pull economy-and-finance articles from ≥2 of {한경, 이데일리, 서울경제}, writing summary + URL (not full body) | VERIFIED | `src/collectors/news/feeds.py` defines HANKYUNG_ECONOMY_FEED, HANKYUNG_FINANCE_FEED, EDAILY_FEED (2 outlets, 3 RSS feeds — 서울경제 deferred per D-09). `fetcher.extract_first_two_paragraphs` caps body at 2 paragraphs (D-13 copyright). `writer._assert_two_paragraph_cap` raises on violation (defense-in-depth). `trust_level=semi_trusted`, `license_flag=summary_only`. 31/31 tests green (10 matcher + 21 collect_news). |
| 3 | `collect_macro` writes daily ECOS + FRED rows; schema matches search-filter keys | VERIFIED | `src/collectors/macro/__init__.py:61 def collect_macro(vault_root, engine=None, catalog_path=None)`. `.planning/macro_series.yaml` contains base_rate_kr + usd_krw (ECOS live-verified 2026-04-20) + us_10y (DGS10) + wti (DCOILWTICO). Writer emits `ProvenanceBlock.observations: [{date, value}, ...]` (D-07 structured schema) + body markdown table. Append-idempotent via merge_observations + revision surfacing (R-06). 12/12 tests green. |
| 4 | `collect_kind` captures 거래정지, 관리종목, 불성실공시 events with structured event-type tags | VERIFIED (with amendment) | `src/collectors/kind/sources.py:33 KindEventType` enum + `DART_EXCHANGE_EVENT_PATTERNS`: `suspension ← 주권매매거래정지`, `watchlist_designation ← 관리종목지정우려`, `unfaithful_disclosure ← 불성실공시법인지정`. Writer path `raw/kind/YYYY-MM/{event_type}_{ticker}_{event_date}.md` (D-08 layout). 25/25 tests green. **Amendment:** Option D replaces D-14 hybrid — DART pblntf_ty='I' is primary source (pykrx has no market-status function, verified live). ROADMAP SC #4 names exactly these three event types; goal preserved. See `amendments_accepted` in frontmatter. |
| 5 | Orchestrated run with one source force-failed shows other three complete + heartbeat records per-source status | VERIFIED | `src/cli/commands.py:145 def cmd_collect_all(args)`: try/except per source (D-19), sequential dispatch via `_dispatch()`, stderr JSON with `{run_at, sources: {<src>: {status, docs_processed, elapsed_ms, error?}}}` (D-20). `tests/test_cli_collect_all.py::test_CA5_source_raises_isolation_other_sources_run` asserts RuntimeError in one source → caught + status=error + exit 1 + siblings still run. `test_CA6_partial` covers stats['failed'] non-empty → status=partial. 11/11 tests green. Heartbeat per-source updates via `record_source_run(..., extra=...)`. |

**Score:** 5/5 ROADMAP success criteria verified automatically. **1 human UAT item** remaining: live `stock collect all` smoke run (VALIDATION.md mandates before production).

---

## Requirements Coverage

| Req | Description | Plans declaring | Evidence | Status |
|-----|-------------|-----------------|----------|--------|
| COLL-02 | `collect_krx`: OHLCV + 투자자수급 + 공매도 잔고 | 01, 02, 06 | SC #1 above | SATISFIED |
| COLL-03 | `collect_news`: trafilatura + RSS, ≥2 outlets | 01, 04, 06 | SC #2 above | SATISFIED |
| COLL-04 | `collect_macro`: ECOS + FRED (기준금리/USD-KRW/US10Y/WTI) | 01, 03, 06 | SC #3 above | SATISFIED |
| COLL-05 | `collect_kind`: 거래정지·관리종목·불성실공시 | 01, 05, 06 | SC #4 above | SATISFIED |

No orphaned requirements. All 4 declared IDs appear in ≥1 plan's `requirements:` frontmatter AND in REQUIREMENTS.md marked `[x]`.

---

## Required Artifacts

| Artifact | Status | Lines | Notes |
|----------|--------|-------|-------|
| `src/shared/portfolio.py` | VERIFIED | 83 | Portfolio.load Pydantic model (D-02) |
| `src/collectors/krx/{__init__,client,fetcher,writer}.py` | VERIFIED | 336 total | 4-file pattern matching dart/ |
| `src/collectors/news/{__init__,client,feeds,fetcher,matcher,writer}.py` | VERIFIED | 498 total | +feeds.py + matcher.py for alias lookup |
| `src/collectors/macro/{__init__,client,fetcher,writer}.py` | VERIFIED | 430 total | ECOS + FRED unified |
| `src/collectors/kind/{__init__,client,scraper,selectors,sources,dart_events,writer}.py` | VERIFIED | 828 total | Option D: dart_events.py primary |
| `src/cli/{__main__,commands}.py` | VERIFIED | 360 total | Subparsers for dart/krx/news/macro/kind/all |
| `.planning/macro_series.yaml` | VERIFIED | — | ECOS 2 + FRED 2 series, verified IDs |
| `vault/notes/portfolio.md` | VERIFIED | — | Seed holdings + watchlist |
| `tests/collectors/{krx,news,macro,kind}/` | VERIFIED | — | 82 new tests |
| `tests/test_cli_collect_all.py` | VERIFIED | — | 11 orchestration tests |
| fixtures: rss/, news/, ecos/, fred/, kind/, krx/ | VERIFIED | — | All Wave-0 probe artifacts committed |

---

## Key Link Verification

| From | To | Pattern | Status |
|------|-----|---------|--------|
| `collect_{krx,news,macro,kind}` | `Portfolio.load(vault_root)` | scope resolution | WIRED — verified in `__init__.py` of each collector (except macro, which takes engine=None since scope is series-based not ticker-based, per D-22) |
| `collect_news` | `resolve_entity_by_alias` / `load_scoped_aliases` | alias→corp_code matching | WIRED — `src/collectors/news/matcher.py:load_scoped_aliases` + `assert_aliases_seeded` (R-09 guard) |
| `collect_*` | `record_source_run(..., extra=...)` | heartbeat per-source + flags | WIRED — each `__init__.py` writes heartbeat; extra kwarg carries skipped_holiday, missing_entity, revisions, parse_error flags |
| `cmd_collect_all` | `_dispatch()[src](vault_root, engine, ...)` | orchestrator → collectors | WIRED — `src/cli/commands.py:145-230`, test CA5 proves isolation |

---

## Data-Flow Trace (Level 4)

KRX/News/Macro/KIND collectors are not UI — they fetch and write. Level 4 concern is "does data actually flow end-to-end?"

| Collector | Data source | Flows to | Status |
|-----------|-------------|----------|--------|
| krx | pykrx.stock.get_ohlcv/trading_value/shorting_balance | `raw/krx/YYYY-MM-DD/{ticker}.md` | FLOWING (fixture tests prove write happens; live smoke deferred to human UAT) |
| news | feedparser RSS → trafilatura article HTML → alias match → writer | `raw/news/YYYY-MM/{outlet}_{hash8}.md` | FLOWING (31 tests incl. end-to-end; live smoke deferred) |
| macro | PublicDataReader (ECOS) + fredapi | `raw/macro/{source}/{series_id}.md` | FLOWING (append-merge tested; live ECOS IDs verified 2026-04-20) |
| kind | dart-fss pblntf_ty='I' filings → classify_dart_exchange_event → writer | `raw/kind/YYYY-MM/{event_type}_{ticker}_{date}.md` | FLOWING (DART path tested; KIND AJAX path off by default) |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 4 test suite passes | `uv run pytest tests/collectors/ tests/test_cli_collect_all.py tests/test_portfolio.py tests/test_entity_alias.py tests/test_heartbeat_extra.py tests/test_frontmatter_news_fields.py tests/test_import_guard.py -q` | 120 passed, 1 warning in 28.35s | PASS |
| `stock collect --help` lists all 6 subparsers | `grep add_parser src/cli/__main__.py` | dart, krx, news, macro, kind, all all present | PASS |
| KRX fetcher exposes all 3 data kinds | `grep -n "^def fetch_" src/collectors/krx/fetcher.py` | fetch_ohlcv, fetch_trading_value, fetch_shorting_balance | PASS |
| Macro catalog has 4 series | `grep -cE "series_id:" .planning/macro_series.yaml` | 4 (2 ECOS + 2 FRED) | PASS |
| News outlets ≥ 2 | `grep -E "(HANKYUNG|EDAILY)" src/collectors/news/feeds.py` | hankyung + edaily (2 outlets, 3 feeds) | PASS |
| KIND patterns cover 3 ROADMAP-named events | `grep DART_EXCHANGE_EVENT_PATTERNS src/collectors/kind/sources.py` | suspension, watchlist_designation, unfaithful_disclosure all mapped | PASS |
| Import guard clean (no anthropic/openai) | `uv run pytest tests/test_import_guard.py` | 4 passed | PASS |

---

## Anti-Patterns Found

None — a targeted scan of the new modules for TODO/FIXME/placeholder/stub-return patterns produced no blockers:
- No `return None` / `return {}` stubs in collector entry points
- No `TODO`/`FIXME` comments blocking goal-critical code paths
- `# TODO: verify` comments in `.planning/macro_series.yaml` are Wave-0 probe markers that were REPLACED by verified IDs in commit 04140f6 (confirmed: no remaining TODO markers in current file)
- `# verify in probe` markers in kind/sources.py were resolved per VALIDATION.md R-02 gate

Non-blocker notes:
- `src/collectors/kind/sources.py` defines `KindEventType.INVESTMENT_CAUTION` and `INVESTMENT_RISK` with no classification patterns — INTENTIONAL per Plan 05 deferral (see Deferred section above).
- `enable_kind_scrape=False` by default in `collect_kind` — INTENTIONAL, operator-toggleable per D-15 / Plan 05 decision.

---

## Cross-Phase Regression Check

Ran phase-3 regression keywords (`frontmatter or heartbeat or dart or portfolio or entity_alias or krx or macro or news or kind`) — 152 passed, 1 skipped (from Plan 05 SUMMARY evidence), and my own targeted run of `tests/test_api_probes.py` returned **2 passed, 1 skipped, 0 failed** — the `test_dart_fss_report_body_shape` pre-existing failure noted in the prompt is now showing as *skipped*, not failing. No phase-4-induced regressions detected.

---

## Amendment & Deferred Items — Explicit Judgments

### D-14 → Option D Amendment

**Verdict:** ACCEPTED as preserving phase intent.

Rationale:
1. **Factual necessity:** pykrx 1.0.51 (+ GitHub master) has no `get_market_status_by_ticker` or equivalent. Plan 05 Wave-0 probe verified this; the original D-14 strategy was predicated on a function that does not exist. An amendment was unavoidable once the probe surfaced this.
2. **Operator pre-approval:** The Option D pivot was explicitly discussed and approved by operator during execution (documented in 04-05-SUMMARY.md §Strategy Amendment).
3. **Goal preservation:** ROADMAP Phase 4 SC #4 enumerates "거래정지, 관리종목, 불성실공시" — all three are captured via DART pblntf_ty='I' + report_nm regex classification. The phase's observable outcome is identical whether the path is DART-only or DART+pykrx hybrid.
4. **Follow-up required:** CONTEXT.md D-14 text still reads as the original hybrid strategy. The 04-05-SUMMARY explicitly requests a follow-up commit to amend D-14 — this is a documentation drift that should be closed but does not affect the phase goal verification.

**Process note (not a gap):** Plan 05 executor operated on live-discovered evidence with operator approval. In a stricter workflow, this would have routed through `/gsd-discuss-phase` before Wave-2 execution. Recommend adding a short bullet to Phase 5 Context (or a CONTEXT addendum commit) to formally retire D-14 in favor of Option D.

### investment_caution / investment_risk Deferral

**Verdict:** OUT-OF-SCOPE (roadmap-binding).

Rationale:
- ROADMAP Phase 4 SC #4 enumerates exactly three event types; investment_caution/risk are NOT on the list.
- CONTEXT D-08 enum listed a broader set (investment_caution was in the enum). Plan 05 implemented the enum values but did not implement the classifier/parser for the 2 non-roadmap types.
- Per verification policy (roadmap SC is the binding contract), the phase goal is met when ROADMAP's named event types are captured. CONTEXT D-08 enum was a scope *superset* that the implementation did not fully realize.
- The gap is documented in Plan 05 SUMMARY §Deferred and tracked as Deferred-05-01 for a follow-up probe.

If the operator prefers a stricter reading (CONTEXT D-08 binding), flip to `gaps_found` and require Plan 05 to extend classification. Current verdict reflects the roadmap-binding interpretation.

---

## Gaps Summary

No blocking gaps. All 5 ROADMAP Success Criteria are satisfied by implemented, tested, wired code. The 120-test Phase 4 suite passes cleanly with no anti-pattern flags, no stubs, no missing artifacts, no broken key links.

The only remaining verification activity is the live `stock collect all` smoke run, which VALIDATION.md §Manual-Only explicitly designates as operator-driven (requires network + real API keys + vault inspection).

---

_Verified: 2026-04-20T15:15Z_
_Verifier: Claude (gsd-verifier)_
