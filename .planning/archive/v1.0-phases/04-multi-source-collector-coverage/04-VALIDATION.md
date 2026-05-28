---
phase: 4
slug: multi-source-collector-coverage
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-18
updated: 2026-04-18
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (Phase 3 established) |
| **Config file** | `pyproject.toml` / `pytest.ini` |
| **Quick run command** | `uv run pytest tests/collectors/ -x` |
| **Full suite command** | `uv run pytest -x` |
| **Estimated runtime** | ~30-60s (no network — all fixtures) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest {scoped to touched module}`
- **After every plan wave:** Run `uv run pytest tests/collectors/ tests/test_portfolio.py tests/test_entity_alias.py tests/test_heartbeat_extra.py tests/test_frontmatter_news_fields.py tests/test_cli_collect_all.py`
- **Before `/gsd-verify-work`:** Full suite + import-guard (COLL-07) must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-T1 | 01 | 1 | COLL-02/03/04/05 | T-04-01 | Portfolio strict schema, extra=forbid | unit | `uv run pytest tests/test_portfolio.py -x -q` | ❌ W0 | ⬜ pending |
| 01-T2 | 01 | 1 | COLL-03 | T-04-02 | resolve_entity_by_alias: bind param + length guard | unit+DB | `uv run pytest tests/test_entity_alias.py -x -q` | ❌ W0 | ⬜ pending |
| 01-T3 | 01 | 1 | COLL-04 | — | macro_series.yaml parseable; shared test fixtures wired | unit | `uv run python -c "import yaml; yaml.safe_load(open('.planning/macro_series.yaml'))"` | ❌ W0 | ⬜ pending |
| 01-T4 | 01 | 1 | COLL-02/03/04/05 | T-04-22 | heartbeat `extra` kwarg round-trip + merge | unit | `uv run pytest tests/test_heartbeat_extra.py -x -q` | ❌ W0 | ⬜ pending |
| 01-T5 | 01 | 1 | COLL-03/COLL-04 | — | ProvenanceBlock news (tickers/outlet/license_flag) + observations additive fields | unit | `uv run pytest tests/test_frontmatter_news_fields.py -x -q` | ❌ W0 | ⬜ pending |
| 02-T1 | 02 | 2 | COLL-02 | T-04-04 | KRX writer: ticker regex + trust_level=trusted + .to_markdown(index=True) | unit | `uv run pytest tests/collectors/krx/test_writer.py -x -q` | ❌ W0 | ⬜ pending |
| 02-T2 | 02 | 2 | COLL-02 | T-04-05,06 | collect_krx: idempotent, heartbeat extra=skipped_holiday, isolation | integration | `uv run pytest tests/collectors/krx/ -x -q` | ❌ W0 | ⬜ pending |
| 03-T1 | 03 | 2 | COLL-04 | — | ECOS IDs live-verified, fixtures captured | checkpoint | manual probe (ECOS curl) | ❌ W0 | ⬜ blocked on ECOS_API_KEY |
| 03-T2 | 03 | 2 | COLL-04 | T-04-07,08,09 | macro append-idempotent, fail-fast empty, observations in frontmatter+body, no secret leak | unit | `uv run pytest tests/collectors/macro/ -x -q` | ❌ W0 | ⬜ pending |
| 04-T1 | 04 | 2 | COLL-03 | — | edaily RSS URL confirmed, fixtures captured | checkpoint | manual probe (curl edaily) | ❌ W0 | ⬜ pending |
| 04-T2 | 04 | 2 | COLL-03 | T-04-10..14 | 2-paragraph cap raises on 3 paragraphs, scheme guard blocks non-http(s), cross-URL dedup by content_hash, alias match drops, url_hash8 dedup, trust_level=semi_trusted, license_flag=summary_only | unit+integration | `uv run pytest tests/collectors/news/ -x -q` | ❌ W0 | ⬜ pending |
| 05-T1 | 05 | 2 | COLL-05 | T-04-15 | KRX MDC bld codes + KIND URL + robots.txt snapshot live-verified | checkpoint | manual probe (curl KRX+KIND) | ❌ W0 | ⬜ pending |
| 05-T2 | 05 | 2 | COLL-05 | T-04-15,16,18 | robots.txt gates startup; 1 req/sec throttle; ParseError on drift; Phase-3 import style (no `src.` prefix) | unit | `uv run pytest tests/collectors/kind/test_parser.py -x -q` | ❌ W0 | ⬜ pending |
| 05-T3 | 05 | 2 | COLL-05 | T-04-17,18 | collect_kind hybrid + dedup by (type,ticker,date); parse error → heartbeat extra flag | integration | `uv run pytest tests/collectors/kind/ -x -q` | ❌ W0 | ⬜ pending |
| 06-T1 | 06 | 3 | COLL-02/03/04/05 | T-04-20,21 | collect all: fail-fast unknown source; isolation; JSON stderr; exit 1 on any failure | integration | `uv run pytest tests/test_cli_collect_all.py -x -q` | ❌ W0 | ⬜ pending |
| R-01 | 04 | 2 | COLL-03 | — | Alias-inventory matching: single DB query loads scoped alias_map; title+body substring scan; nickname alias hits | unit+integration | `uv run pytest tests/collectors/news/test_matcher.py -x -q` | ❌ W0 | ⬜ pending |
| R-02 | 05 | 1 | COLL-05 | T-04-15 | Wave-0 hard gate: KRX_MDC_BLD verified (both) + KIND_NFAITH_STATUS_URL + nfaith_status_page1.html + robots.txt committed | checkpoint | `test -f tests/fixtures/kind/nfaith_status_page1.html && test -f tests/fixtures/kind/robots.txt && test -f docs/kind-robots-snapshot.txt && ! grep -q 'verify in probe' src/collectors/kind/sources.py` | ❌ W0 | ⬜ blocked on probe |
| R-03 | 02 | 2 | COLL-02 | — | KRX missing-entity Option A: ticker without entities row → not written + heartbeat missing_entity list + other tickers continue | integration | `uv run pytest tests/collectors/krx/test_collect_krx.py -k missing_entity -x -q` | ❌ W0 | ⬜ pending |
| R-04 | 01 | 1 | COLL-02/03/04/05 | — | Phase 3 regression gate: existing frontmatter/heartbeat/dart tests still green after schema extension | regression | `uv run pytest tests/ -k "frontmatter or heartbeat or dart" -x -q` | ❌ W0 | ⬜ pending |
| R-06 | 03 | 2 | COLL-04 | — | Same-date revision surfaces revisions list to heartbeat extra; (date,value) dedup skips identical pairs | unit | `uv run pytest tests/collectors/macro/ -k revision -x -q` | ❌ W0 | ⬜ pending |
| R-07 | 01 | 1 | COLL-03/COLL-04 | — | Typed TickerRef + Observation nested models reject bad patterns; round-trip preserves .value | unit | `uv run pytest tests/test_frontmatter_news_fields.py -k "typed or TickerRef or Observation" -x -q` | ❌ W0 | ⬜ pending |
| R-08 | 04 | 2 | COLL-03 | T-04-10 | RSS via requests (bytes) + article via trafilatura (str); scheme guard on both; no cross-import | unit | `uv run pytest tests/collectors/news/ -k "rss or article or scheme or fetch_sep" -x -q` | ❌ W0 | ⬜ pending |
| R-09 | 04 | 2 | COLL-03 | — | collect_news startup raises NoAliasesSeededError when entity_aliases lacks name rows (no HTTP issued) | unit | `uv run pytest tests/collectors/news/ -k "seeded or NoAliases" -x -q` | ❌ W0 | ⬜ pending |
| 07-T1 | 07 | 4 | COLL-02/03/04/05 | T-04-07-01 | CLI --vault-root default=vault; default-flag integration test guards against Gap-04-03 regression | integration | `uv run pytest tests/test_cli_default_flags.py -x -q` | — | ⬜ pending (gap closure) |
| 07-T2 | 07 | 4 | COLL-04 | T-04-07-02 | ECOS fetcher drops 통계항목코드1 kwarg; client-side ITEM_CODE1 filter is sole filter; fixture includes mixed-ITEM_CODE1 rows | unit | `uv run pytest tests/collectors/macro/test_collect_macro.py::test_fetch_ecos_series_client_side_filter_drops_unrelated_item_codes -x -q` | — | ⬜ pending (gap closure) |
| 07-T3 | 07 | 4 | COLL-02/03/04/05 | — | Full keyword regression suite still green after Gap-04-03/04/06 fixes | regression | `uv run pytest tests/ -k "frontmatter or heartbeat or dart or portfolio or entity_alias or krx or macro or news or kind or cli or import_guard or default_flags" -x -q` | — | ⬜ pending (gap closure) |
| 08-T1 | 08 | 4 | COLL-03 | T-04-08-01 | CLAUDE.md First-time Setup section + news --help epilog document seed precondition (Gap-04-05) | docs+help | `grep -q "^## First-time Setup$" CLAUDE.md && uv run python -m cli collect news --help 2>&1 \| grep -q seed_name_aliases` | — | ⬜ pending (gap closure) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements (fixtures + seed files created during plan tasks)

- [ ] `tests/collectors/conftest.py` — vault_tmp + seeded_engine fixtures (Plan 01 Task 4)
- [ ] `.planning/macro_series.yaml` — scaffold with placeholders + TODO markers (Plan 01 Task 4)
- [ ] `vault/notes/portfolio.md` — seed example (Plan 01 Task 1)
- [ ] `tests/test_heartbeat_extra.py` — heartbeat `extra` kwarg tests (Plan 01 Task 3)
- [ ] `tests/test_frontmatter_news_fields.py` — ProvenanceBlock news+observations tests (Plan 01 Task 3)
- [ ] `tests/fixtures/krx/ohlcv_005930.json`, `trading_value_005930.json`, `shorting_balance_005930.json` (Plan 02 Task 1)
- [ ] `tests/fixtures/krx/krx_admin_issue_list.json`, `krx_warning_list.json`, `krx_suspension_list.json` (Plan 05 Task 1 probe)
- [ ] `tests/fixtures/rss/hankyung_economy.xml`, `hankyung_finance.xml`, `edaily_news.xml` (Plan 04 Task 1 probe)
- [ ] `tests/fixtures/news/hankyung_sample.html`, `edaily_sample.html` (Plan 04 Task 1 probe)
- [ ] `tests/fixtures/ecos/base_rate_kr.json`, `usd_krw.json`, `empty_result.json` (Plan 03 Task 1 probe)
- [ ] `tests/fixtures/fred/DGS10.json`, `DCOILWTICO.json` (Plan 03 Task 2)
- [ ] `tests/fixtures/kind/nfaith_status_page1.html`, `nfaith_status_empty.html`, `nfaith_status_malformed.html`, `robots.txt` (Plan 05 Task 1 probe)
- [ ] `docs/kind-robots-snapshot.txt` (Plan 05 Task 1)
- [ ] **R-02 gate**: `src/collectors/kind/sources.py` contains zero `# verify in probe` comments after Task 1 approval

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ECOS series IDs resolve to expected Korean labels | COLL-04 | Requires live ECOS API key + network | Plan 03 Task 1 checkpoint — operator runs curl + updates `.planning/macro_series.yaml` |
| edaily RSS URL currency | COLL-03 | URL may have changed since 2017 references | Plan 04 Task 1 checkpoint — operator confirms via curl + DevTools |
| KIND 불성실공시 현황 URL + selectors | COLL-05 | Server-rendered page; selectors may drift | Plan 05 Task 1 checkpoint — operator browses + snapshots |
| KRX MDC bld codes | COLL-05 | Codes are well-known but may have evolved | Plan 05 Task 1 checkpoint — operator curls each bld |
| robots.txt compliance at runtime | COLL-05 | robots.txt may change upstream | `curl https://kind.krx.co.kr/robots.txt` before first prod run |
| Live `stock collect all` smoke run | Phase 4 #5 | End-to-end real API traffic | After all plans green, operator runs `stock collect all 2>report.json`; confirms report matches D-20 schema + files appear under `vault/raw/{src}/` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify OR a Wave-0 checkpoint dependency
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (checkpoints 03-T1, 04-T1, 05-T1 are each followed by automated tasks)
- [x] Wave 0 covers all MISSING fixtures (listed above)
- [x] No watch-mode flags
- [x] Feedback latency < 60s (full suite ~30-60s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending operator review of plans
