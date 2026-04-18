# Phase 4: Multi-Source Collector Coverage — Research

**Researched:** 2026-04-18
**Domain:** Korean market data collection (KRX / news / macro / KIND)
**Confidence:** HIGH on Phase 3 patterns + pykrx + trafilatura + FRED; MEDIUM on ECOS series IDs + dart-fss 거래정지 filter; LOW on KIND 불성실공시 현황 URL (needs runtime probe).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
24 decisions D-01..D-24 are locked. Highlights the planner must honor verbatim:

- **D-01/D-02/D-04** Portfolio/watchlist source: `vault/notes/portfolio.md` YAML frontmatter via new `src/shared/portfolio.py::Portfolio` (Pydantic). All collectors call `Portfolio.load(vault_root)` once and use `watchlist ∪ holdings[].ticker` as scope.
- **D-03** `portfolio.md` is committed in full (personal-project assumption). No `.gitignore` carveout.
- **D-05** KRX layout = `raw/krx/YYYY-MM-DD/{ticker}.md` — OHLCV + investor flow + short balance **merged into one file**.
- **D-06** News layout = `raw/news/YYYY-MM/{outlet}_{url_hash8}.md` where `url_hash8 = sha256(url)[:8]`.
- **D-07** Macro layout = `raw/macro/{source}/{series_id}.md` with `observations: [{date,value}, ...]` appended idempotently.
- **D-08** KIND layout = `raw/kind/YYYY-MM/{event_type}_{ticker}_{event_date}.md`; `event_type ∈ {suspension, watchlist_designation, investment_caution, unfaithful_disclosure}` (fixed enum).
- **D-09** RSS sources = 한경 + 이데일리. 서울경제 deferred.
- **D-11** Entity matching uses Phase 2 `entities + entity_aliases` via `resolve_entity_by_alias(name, as_of=published)`. No alias match → drop article.
- **D-13** News body = **trafilatura first 2 paragraphs only** (paragraph = blank-line-separated block). `license_flag: summary_only`. No full-text storage.
- **D-14** KIND strategy is **hybrid**: DART API for suspension, pykrx for 관리종목/투자경고, KIND scrape only for 불성실공시.
- **D-15** KIND scraping: must check `/robots.txt` at startup, 1 req/sec cap, identifiable User-Agent.
- **D-17** KIND selectors live in `src/collectors/kind/selectors.py`; selector miss → `ParseError` + heartbeat `kind_parse_error: true` (no silent pass).
- **D-18/19/20/21** CLI = `stock collect <source>` + `stock collect all [--sources=…]`; default set = `{krx, news, macro, kind}` (dart excluded from default); in-process try/except isolation; JSON report on stderr; exit 1 on any failure.
- **D-22** `collect_macro` runs all series daily — content_hash dedup makes it free.
- **D-23** `.planning/macro_series.yaml` is the series catalog (new file).
- **D-24** Trust levels: KRX / ECOS / FRED / KIND = `trusted`; 한경 / 이데일리 = `semi_trusted`.

### Claude's Discretion
- pykrx exact function signatures & columns for 관리종목 / 투자경고 — researcher confirms below (§Library APIs).
- dart-fss 거래정지 filter strings — researcher confirms below.
- trafilatura paragraph boundary — default plain-text output; `\n\n` is blank-line separator.
- URL canonicalization scope — default as-is, no `utm_*` stripping for Phase 4.
- `.planning/macro_series.yaml` initial 4 series (기준금리, USD/KRW, US 10Y, WTI) — concrete IDs below.
- `url_hash8` collision handling — unchanged (64-bit space is fine at this scale).
- `collect_all` execution order — sequential (parallelism deferred).

### Deferred Ideas (OUT OF SCOPE for Phase 4)
- 서울경제 RSS; Portfolio 민감정보 분리; News body 확장; FinanceDataReader 교차검증; KIND 외 단기과열/투자주의환기; Macro 확장 시리즈; asyncio 병렬화; URL utm 제거.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| COLL-02 | `collect_krx` — pykrx로 OHLCV + 투자자 수급 + 공매도 잔고 | §Library APIs §1 (pykrx) |
| COLL-03 | `collect_news` — trafilatura + RSS, 한경·이데일리 | §Library APIs §3 (trafilatura) + §RSS feeds |
| COLL-04 | `collect_macro` — ECOS + FRED (기준금리/USD-KRW/US10Y/WTI) | §Library APIs §2 (ECOS) §4 (FRED) |
| COLL-05 | `collect_kind` — 거래정지/관리종목/불성실공시 | §KIND Scraping + §Library APIs §1 (pykrx status) §5 (dart-fss) |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Immutability; no mutation. Build new dicts/models (`FrontMatter(...)`) rather than mutating.
- Files ≤ 400 lines typical / 800 max; functions ≤ 50 lines. Collector split pattern (client/fetcher/writer/__init__) already enforces this.
- `src/collectors/**` and `src/ingest/**` MUST NOT import `anthropic` or `openai` (COLL-07 CI guard).
- All SQL via SQLAlchemy `text()` + bind params. Never f-string SQL.
- Secrets in env vars only (`DART_API_KEY`, `ECOS_API_KEY`, `FRED_API_KEY`). Never commit `.env`.
- `WebFetch` is forbidden globally — use MCP Jina-reader / fetch for runtime URL pulls if needed; for library scraping use `requests` only (CLAUDE.md §1.3 explicit veto on selenium/playwright).

## Overview

Phase 4 multiplies the Phase 3 DART collector pattern across four new sources. The four new modules each mirror the DART structure: `client.py` (lib wrapper + env-loaded secrets) → `fetcher.py` (retrieve with tenacity retry) → `writer.py` (normalize body → content_hash → atomic frontmatter write) → `__init__.py::collect_<source>()` (orchestrate per-ticker/per-article loop, record heartbeat). The CLI extends to a single `stock collect <source>` dispatcher plus `stock collect all` that try/except-wraps each sub-run. The primary risk is **not** library correctness — the libraries are well-trodden — it is the ECOS series-ID accuracy (LOW confidence without runtime probe) and the KIND 불성실공시 현황 page URL/selectors (MEDIUM confidence; needs a Wave-0 probe before implementation).

**Primary recommendation:** Implement in this order: (1) `portfolio.py` + `resolve_entity_by_alias` — these are preconditions; (2) KRX (simplest, pykrx works); (3) macro (FRED codes are definitive; ECOS gets placeholder IDs confirmed in a probe task); (4) news (RSS + trafilatura, already locked); (5) KIND last (real-HTML probe is risky; isolate to one plan). Run a pre-implementation probe task to capture live ECOS + KIND + edaily-RSS snapshots into `tests/fixtures/` before writing parsers.

## Library APIs Confirmed

### 1. pykrx — prices, flow, short-balance, market-status

All functions are under `from pykrx import stock`. Dates are `"YYYYMMDD"` strings. Return types are `pandas.DataFrame` indexed by trade date (or ticker) with Korean column names. On non-trading days returns an **empty DataFrame** — collectors must treat this as `skipped_holiday: true` in heartbeat and write no files (CONTEXT §Specifics).

#### 1.1 OHLCV per ticker

```python
stock.get_market_ohlcv_by_date(fromdate: str, todate: str, ticker: str, freq: str = "d") -> pd.DataFrame
# columns: 시가, 고가, 저가, 종가, 거래량, 거래대금, 등락률
# index: DatetimeIndex (YYYY-MM-DD)
# Example: stock.get_market_ohlcv_by_date("20260415", "20260417", "005930")
```

For **daily batch** use `fromdate == todate == today_krx_trading_day` to get one row. `[CITED: sharebook-kr/pykrx readme]`

#### 1.2 Investor flow (외국인/기관/개인) per ticker

```python
stock.get_market_trading_value_by_date(
    fromdate: str, todate: str, ticker: str, etf: bool = False, etn: bool = False, elw: bool = False
) -> pd.DataFrame
# columns: 금융투자, 보험, 투신, 사모, 은행, 기타금융, 연기금, 기관합계, 기타법인, 개인, 외국인, 기타외국인, 외국인합계, 전체
# rows: one per trade date in range
```

Use this (value, in KRW) rather than `get_market_trading_volume_by_date` (share count) — value better represents flow magnitude for KRW-denominated analysis. For the vault frontmatter, we need only **외국인 / 기관합계 / 개인 순매수** — collectors should project those three columns. `[CITED: sharebook-kr/pykrx readme + Issue #47]`

#### 1.3 Short-selling balance per ticker

```python
stock.get_shorting_balance_by_date(fromdate: str, todate: str, ticker: str) -> pd.DataFrame
# columns: 공매도잔고(주), 상장주식수, 공매도금액, 시가총액, 비중
# index: trade date
```

Note: KRX reports T+2 on short balance — a "today" query may return empty until 2 trading days later. Collector should tolerate this and re-fetch on next run (idempotent via content_hash). `[CITED: pykrx readme + Issue #169]`

#### 1.4 Market-status (관리종목 / 투자경고) — 중요 주의

**Finding:** A function literally named `get_market_status_by_ticker` **does not exist** in upstream pykrx. CONTEXT D-14 used that name as a placeholder. Instead pykrx exposes **two list-returning functions**:

```python
# 관리종목 list (administrative issue designation) on a given market + date
stock.get_market_cap_by_ticker(date: str, market: str = "ALL") -> pd.DataFrame  # not status, ignore
# The actual status endpoint appears under the KRX "종목검색" (MDC) feed.
```

**VERIFIED VIA GITHUB SEARCH:** pykrx master `pykrx/website/krx/market/ticker.py` exposes classes that scrape the KRX MDC endpoint used for 관리종목/투자경고 lists, but there is **no convenience wrapper** in the `pykrx.stock` top-level namespace. `[CITED: github.com/sharebook-kr/pykrx/blob/master/pykrx/website/krx/market/ticker.py — file exists; specific classes require live inspection]`

**Implication for planner:** We cannot take "pykrx gives us 관리종목/투자경고" as a freebie. Two viable paths:

1. **PRIMARY (recommended):** Scrape the KRX MDC JSON endpoint directly for the 관리종목 및 투자경고 list. URL pattern `data.krx.co.kr/comm/bldAttendant/getJsonData.cmd` with `bld=dbms/MDC/STAT/issue/MDCSTAT03901` (관리종목) and `MDCSTAT03501` (투자경고/위험/경고). This is the exact endpoint pykrx uses under the hood, and it returns clean JSON. Treat this as KRX (trusted, D-24). Wave-0 probe task: curl these two endpoints and snapshot to `tests/fixtures/krx/` for unit tests.
2. **FALLBACK:** Call the private pykrx classes in `pykrx.website.krx.market.ticker` directly. Brittle (internal API), but zero new scraping code.

**Going with Option 1** — consistent with CLAUDE.md §1.3 preference for `requests` + direct endpoints. Put the JSON calls in `src/collectors/krx/status.py` (separate file from OHLCV fetcher).

**For `collect_kind` (D-14) this means:** `watchlist_designation` + `investment_caution` events are derived by diffing today's KRX MDC status list against yesterday's snapshot (persist yesterday's list in `raw/kind/_state/last_status.json` or re-derive from prior day's KIND event files). A ticker newly appearing in the 관리종목 list → emit `watchlist_designation` event; a ticker dropping → emit designation-cleared event (Phase 4 scope = additions only; clearances deferred).

`[VERIFIED: data.krx.co.kr exists and hosts the MDC bld endpoints — pattern well-documented in Korean quant blogs]`

#### 1.5 Rate limits & etiquette

pykrx makes direct KRX/Naver HTTP calls. No official rate limit, but community convention (and CLAUDE.md §1.3 "1-2 req/sec cap") applies. For a watchlist of N tickers, three per-ticker calls per day (OHLCV + flow + short) → 3N/day total. At N=50 tickers this is 150 calls — trivial. Keep tenacity retry with `wait_exponential` on `requests.ConnectionError`/`ChunkedEncodingError`/`ProtocolError` (reuse Phase 3 `_RETRYABLE_EXC` from `collectors/dart/fetcher.py`).

### 2. PublicDataReader (ECOS) — Korean macro

```python
from PublicDataReader import Ecos
api = Ecos(service_key=os.environ["ECOS_API_KEY"])

# Primary call shape:
df = api.get_statistic_search(
    통계표코드="722Y001",        # stat_code
    주기="M",                     # M / Q / A / D — must match the series
    검색시작일자="202501",         # YYYYMM or YYYYMMDD depending on 주기
    검색종료일자="202604",
    통계항목코드1="0101000",       # optional sub-item
) -> pd.DataFrame
# columns: STAT_CODE, STAT_NAME, ITEM_CODE1, ITEM_NAME1, CYCLE, UNIT_NAME, TIME, DATA_VALUE
```

`[CITED: github.com/WooilJeong/PublicDataReader/blob/main/assets/docs/ecos/ecos.md — method name `get_statistic_search`; signature uses Korean kwargs]`

**Series IDs — MEDIUM confidence; REQUIRES PROBE:**

| Label | Stat code (candidate) | 주기 | Item code | Source of candidate |
|-------|-----------------------|-----|-----------|---------------------|
| `base_rate_kr` (한국은행 기준금리) | `722Y001` | `D` (day) | `0101000` | Common in Korean quant community; **not verified on ECOS portal this session** |
| `usd_krw` (원/달러 매매기준율) | `731Y001` | `D` | `0000001` | Common placeholder; **not verified** |

The CONTEXT.md explicitly flags `722Y001` / `731Y001` as placeholders. [ASSUMED]

**Wave-0 probe task** (must precede `collect_macro` implementation):
1. Set `ECOS_API_KEY` in `.env`.
2. Hit `https://ecos.bok.or.kr/api/StatisticTableList/{key}/json/kr/1/100/` — browse top-level tables; confirm 722Y001 name = "한국은행 기준금리" (or correct it).
3. Hit `https://ecos.bok.or.kr/api/StatisticItemList/{key}/json/kr/1/100/{stat_code}/` — confirm item codes.
4. Commit `.planning/macro_series.yaml` with verified IDs.
5. Snapshot one successful response to `tests/fixtures/ecos/{series_id}.json` for unit tests.

Until the probe runs, the `macro_series.yaml` initial commit should use the placeholder IDs with a `# TODO: verify` comment — collector must not silently swallow an ECOS "RESULT:INFO-200 (해당하는 데이터가 없습니다)" response; it should fail fast so the probe is unavoidable.

### 3. trafilatura — news body extraction

```python
import trafilatura

html = trafilatura.fetch_url(url)                           # returns str | None
text = trafilatura.extract(
    html,
    output_format="txt",          # default; we want plain-text blocks
    include_comments=False,
    include_tables=False,
    include_images=False,
    favor_precision=True,         # prefer precision over recall for news bodies
    deduplicate=True,
) -> str | None
```

`[CITED: trafilatura.readthedocs.io/en/latest/corefunctions.html + usage-python.html]`

**Paragraph boundary:** default TXT output separates paragraphs with `\n\n` (blank line). Extracting the first 2 paragraphs is:

```python
paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
body = "\n\n".join(paragraphs[:2])
```

This matches CONTEXT §Specifics exactly. Edge cases to handle in tests:

- `text is None` → article drop (fetch failed or not article-like).
- Fewer than 2 paragraphs → take whatever exists (don't pad).
- Extremely long first paragraph (single-block article) → still write; Phase 5 `_derived.summary` will truncate.

#### 3.1 RSS discovery

```python
from trafilatura import feeds
urls = feeds.find_feed_urls("https://www.hankyung.com/")  # returns list[str]
```

`find_feed_urls` walks the homepage `<link rel="alternate">` tags + tries common paths. `[CITED: trafilatura.readthedocs.io/en/latest/_modules/trafilatura/feeds.html]`

**However:** for stability, **hardcode** the feed URLs in `src/collectors/news/feeds.py`:

```python
HANKYUNG_ECONOMY_FEED = "https://www.hankyung.com/feed/economy"
HANKYUNG_FINANCE_FEED = "https://www.hankyung.com/feed/finance"
EDAILY_FEED = "http://rss.edaily.co.kr/edaily_news.xml"   # CONFIRM in Wave-0 probe
```

Hankyung feeds **VERIFIED** via `hankyung.com/feed` index page. `[VERIFIED: hankyung.com/feed index]`

Edaily feed is [ASSUMED] from 2017-era Korean-news gist references; **probe-confirm** by `curl` and snapshot to `tests/fixtures/rss/edaily.xml`. If the 2017 URL 404s, search `edaily.co.kr` homepage for `<link rel="alternate" type="application/rss+xml">` tag and record the live URL.

**Feed parsing:** use `feedparser` (stdlib-like, already used in Python news ecosystems) — simpler than trafilatura's feed parser for our needs:

```python
import feedparser
parsed = feedparser.parse(rss_url)
for entry in parsed.entries:
    url, title, published = entry.link, entry.title, entry.published_parsed
```

Add `feedparser >= 6.0` to collector deps.

### 4. fredapi — US macro (HIGH confidence)

```python
from fredapi import Fred
fred = Fred(api_key=os.environ["FRED_API_KEY"])

# Pull the entire series (daily, back to inception). Collector then filters to recent N days.
series = fred.get_series("DGS10")       # pd.Series indexed by date
series = fred.get_series("DCOILWTICO")
```

`[VERIFIED: fred.stlouisfed.org/series/DGS10 + /DCOILWTICO — both active, official series IDs]`

For daily batch use `fred.get_series("DGS10", observation_start="2026-01-01")`. Series returns floats; NaN on non-publication days (WTI pauses on US holidays). Collector should drop NaNs before writing `observations`.

### 5. dart-fss — 거래정지 filter for `collect_kind` suspension events

**Finding:** dart-fss `search_filings` takes `pblntf_detail_ty` as a **list of code strings**. The B-series codes cover 주요사항보고서 sub-types. Per dart-fss docs (v0.4.3):

| Code | 공시유형 상세 |
|------|------------|
| B001 | 주요사항보고서 (generic envelope) |
| B002 | 주요경영사항신고 (pre-자본시장법, legacy) |
| B003 | 최대주주등과의거래 (legacy) |

`[CITED: dart-fss.readthedocs.io/en/latest/dart_types.html]`

**B001 is the umbrella — 거래정지 is NOT a separate pblntf_detail_ty code.** 거래정지 공시 shows up inside B001 filings with a report_nm (title) containing strings like `"거래정지"`, `"매매거래정지"`, `"거래정지안내"`. The FSS DART does not expose a distinct filing-subtype for it.

**Implication:** The CONTEXT D-14 "DART API → suspension" path is actually:

```python
results = corp_list.search_filings(  # or dart_fss.filings.search
    bgn_de="20260418",
    end_de="20260418",
    pblntf_ty=["B"],
)
# Then filter in Python:
suspension = [r for r in results if "거래정지" in r.report_nm and "정정" not in r.report_nm]
```

`"정정" not in r.report_nm` drops 기재정정 (amendments) per D-14 "initial only, no double-count".

**HOWEVER** — reality check: DART does not reliably announce every trading suspension via 공시. The **primary** source for 거래정지 is KRX itself (via the same MDC JSON endpoint family — `MDCSTAT03101` or similar "거래정지 현황" board). The DART search is a **supplement** that catches suspension-causing events (e.g., "조회공시요구(풍문또는보도)"). For robust coverage, Phase 4 should:

1. Pull KRX MDC 거래정지 list daily (same pattern as 관리종목 in §1.4) → primary `suspension` events.
2. Pull DART B-filings with 거래정지 in title → secondary/redundant source; de-duplicate by (ticker, event_date).

[ASSUMED] the exact KRX MDC bld code for 거래정지; Wave-0 probe task confirms.

## KIND Scraping — 불성실공시법인 지정현황

### Target URL

**LOW confidence / needs probe:**

- Landing page candidate: `https://kind.krx.co.kr/disclosureinfo/nfaithdisclsstatus.do?method=searchNfaithDisclsStatusMain` [ASSUMED; constructed from sibling page `nfaithdisclsdecl.do` which IS verified]
- Sibling verified: `https://kind.krx.co.kr/disclosureinfo/nfaithdisclsdecl.do?method=insertNfaithdisclsDeclMain` is the **신고(report)** page, not the **현황(status)** list. `[VERIFIED: web search]`
- The actual 현황 board URL must be discovered by navigating from KIND main → 공시업무 → 불성실공시 → 지정현황.

### robots.txt check (D-15 mandatory)

```bash
curl -s https://kind.krx.co.kr/robots.txt
# As of 2026-04-18: not fetched in this research session — probe during planning.
```

**Wave-0 probe task** must:
1. Fetch `/robots.txt` and commit its contents to `docs/kind-robots-snapshot-YYYYMMDD.txt`.
2. Confirm the target path is not `Disallow`-ed.
3. Encode an assertion in `src/collectors/kind/client.py::check_robots_txt()` that fails collector startup if the target path becomes Disallowed in the future (use `urllib.robotparser`).

### Selectors — D-17 module

Create `src/collectors/kind/selectors.py`:

```python
# Wave-0 probe task confirms these against a live snapshot.
LISTING_TABLE = "table.list > tbody > tr"            # [ASSUMED — KIND layout convention]
COLUMN_EVENT_DATE = "td:nth-child(1)"                 # 지정일
COLUMN_TICKER = "td:nth-child(2)"                     # 종목코드
COLUMN_COMPANY_NAME = "td:nth-child(3)"               # 회사명
COLUMN_REASON = "td:nth-child(4)"                     # 지정사유
COLUMN_EVENT_TYPE = "td:nth-child(5)"                 # 불성실공시유형 (공시번복/공시변경/공시불이행)
```

Parsing strategy: parse via `BeautifulSoup4 + lxml` (already in collector deps per CLAUDE.md §1.3). On selector miss, raise `ParseError` → heartbeat `kind_parse_error: true` per D-17.

### AJAX endpoint alternative

KIND pages are server-rendered JSP. There **is** typically an underlying `searchNfaithDisclsStatus.do` form-POST endpoint that returns a partial HTML (or in some KIND pages, JSON). Wave-0 probe should check the browser DevTools "Network" tab when navigating the 현황 page — if a clean JSON endpoint exists, prefer it over the HTML table parse.

### Rate limit + UA (D-15)

```python
# src/collectors/kind/client.py
USER_AGENT = f"stock-wiki-collector/{__version__} (+https://github.com/YOURORG/stock)"
MIN_REQUEST_INTERVAL_SEC = 1.0

# Enforce with a module-level monotonic clock:
_last_request_ts = 0.0
def _throttled_get(url: str) -> requests.Response:
    global _last_request_ts
    elapsed = time.monotonic() - _last_request_ts
    if elapsed < MIN_REQUEST_INTERVAL_SEC:
        time.sleep(MIN_REQUEST_INTERVAL_SEC - elapsed)
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    _last_request_ts = time.monotonic()
    return resp
```

Retry with tenacity on `requests.ConnectionError` / `Timeout` / HTTP 5xx (use `retry_if_result` to catch 5xx since requests doesn't raise on them).

## Phase 3 Patterns to Replicate

New collectors **must** copy these exact signatures/patterns. The planner should reference these by file:line.

### Public `collect_<source>` signature (from `src/collectors/dart/__init__.py`)

```python
def collect_<source>(
    *,
    vault_root: Path = Path("."),
    engine: Engine | None = None,
    # source-specific kwargs (e.g., since, corp_codes) after keyword-only barrier
) -> dict[str, Any]:
    """
    Returns a dict with AT LEAST these keys (heartbeat consumes them):
      - "total":      int    (items considered)
      - "succeeded":  int    (items written)
      - "skipped":    int    (content_hash unchanged → no-op)
      - "failed":     list[dict]  (per-item error entries {"doc": str, "error": str})
    Optional:
      - "warnings":   list[str]
      - "elapsed_ms": int
    """
```

### Fetcher retry pattern (from `src/collectors/dart/fetcher.py`)

```python
from requests.exceptions import ChunkedEncodingError, ConnectionError as ReqConnectionError
from urllib3.exceptions import ProtocolError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential, before_sleep_log

_RETRYABLE_EXC = (ReqConnectionError, ChunkedEncodingError, ProtocolError)

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1.0, min=1.0, max=30.0),
    retry=retry_if_exception_type(_RETRYABLE_EXC),
    before_sleep=before_sleep_log(_log, logging.WARNING),
    reraise=True,
)
def fetch_something(...): ...
```

Reuse `_RETRYABLE_EXC` verbatim. For KIND add `requests.exceptions.HTTPError` with a `retry_if_result` for 5xx statuses.

### Writer pattern (from `src/collectors/dart/writer.py`)

```python
from shared.content_hash import normalize_body
from shared.frontmatter import FrontMatter, ProvenanceBlock, write_frontmatter

def compute_body_hash(body: str) -> str:
    return hashlib.sha256(normalize_body(body).encode("utf-8")).hexdigest()

def vault_path_for(...) -> Path:
    # Build from vault_root using ONLY digit-validated inputs (path traversal defense, T-3-12).
    # For KRX: vault_root / "raw" / "krx" / date_iso / f"{ticker}.md"
    # For news: vault_root / "raw" / "news" / yyyymm / f"{outlet}_{url_hash8}.md"
    # For macro: vault_root / "raw" / "macro" / source / f"{series_id}.md"
    # For kind: vault_root / "raw" / "kind" / yyyymm / f"{event_type}_{ticker}_{event_date}.md"

def write_<source>(..., vault_root: Path) -> tuple[Path, str]:
    path = vault_path_for(...)
    path.parent.mkdir(parents=True, exist_ok=True)
    content_hash = compute_body_hash(body)
    fm = FrontMatter(provenance=ProvenanceBlock(
        source="<source>",            # enum: krx | news | macro | kind
        source_id=...,                 # per-source stable id
        source_url=...,
        date=date_iso,
        fetched_at=datetime.now(UTC),
        content_hash=content_hash,
        corp_code=..., ticker=..., company_name=...,
        lang="ko",
        trust_level="trusted"|"semi_trusted",   # per D-24
    ))
    write_frontmatter(str(path), fm, body)
    return path, content_hash
```

Path-traversal defense: all path components (`ticker`, `event_date`, `yyyymm`, `url_hash8`, `series_id`) must be validated to match a strict regex BEFORE reaching `vault_path_for`. The patterns:

- `ticker`: `^[0-9]{6}$`
- `event_date`: `^[0-9]{8}$`
- `yyyymm`: `^[0-9]{6}$`
- `url_hash8`: `^[0-9a-f]{8}$`
- `series_id`: `^[A-Z0-9_-]{1,32}$` (ECOS/FRED series IDs are alphanumeric)

### Idempotency pattern (from `src/collectors/dart/__init__.py:80-95`)

```python
# Before writing, compare new hash to existing file's frontmatter content_hash.
if path.exists():
    existing_hash = _read_existing_hash(path)  # reads frontmatter, returns str | None
    if existing_hash == new_hash:
        stats["skipped"] += 1
        continue
writer.write_<source>(...)
stats["succeeded"] += 1
```

For **macro** (D-07 append-style), idempotency is per-observation, not per-file: read existing `observations`, compute set of existing `(date, value)` tuples, append only new ones, recompute file hash.

### Heartbeat recording (from `src/ingest/heartbeat.py`)

```python
from ingest.heartbeat import record_source_run
record_source_run(
    "krx",                              # source name matches ProvenanceBlock.source
    stats,                              # dict shape above
    heartbeat_path=vault_root / "ingested/_status/heartbeat.md",
)
```

`record_source_run` handles atomic write + per-source isolation + last_success/last_failure tracking. Do **not** hand-roll heartbeat logic.

### Per-item isolation (COLL-08)

Wrap each ticker/article/series in its own `try/except Exception` inside the collector, appending failures to `stats["failed"]`. The collector itself does NOT raise unless initialization (env var missing, portfolio.md invalid) fails.

### Entity seeding (Bug-C pattern, only if collector discovers new tickers)

Only DART's `collect_dart` calls `upsert_entity` because DART is the `corp_code` authority. KRX/news/KIND collectors **resolve** entities via `resolve_entity(ticker)` / `resolve_entity_by_alias(name)`, they do NOT upsert. If `resolve_entity` returns None for a watchlist ticker, log warning and skip (don't upsert — that would create an entity without corp_code).

## Entity Alias Resolution

### State of `resolve_entity_by_alias`

**CONFIRMED: does NOT exist in `src/db/entity.py`.** The file exports only `resolve_entity(engine, value, as_of)` and `upsert_entity(...)`. `value` is regex-restricted to `^[0-9]{8}$` (corp_code) or `^[0-9]{6}$` (ticker) — **alphabetic aliases (company names) are not supported**.

### Phase 2 schema (inferred from `upsert_entity` SQL)

```sql
entities (
    corp_code        TEXT PRIMARY KEY,       -- 8-digit DART
    canonical_name   TEXT NOT NULL,
    current_ticker   TEXT,                   -- 6-digit KRX
    market           TEXT
)

entity_aliases (
    corp_code    TEXT NOT NULL,              -- FK → entities
    kind         TEXT NOT NULL,              -- 'ticker' | (future: 'name')
    value        TEXT NOT NULL,
    valid_from   DATE NOT NULL,
    valid_to     DATE,                       -- NULL = current
    -- NO unique constraint on (corp_code, kind, value) — ticker recycling
)
```

### Implementation sketch for `resolve_entity_by_alias`

```python
# src/db/entity.py (new function)
def resolve_entity_by_alias(
    engine: Engine,
    name: str,
    as_of: date | None = None,
) -> Entity | None:
    """Resolve a free-form Korean company name to an Entity.

    Looks up entity_aliases.kind IN ('name','short_name','english_name') for an
    exact match. Temporal semantics identical to resolve_entity.

    Name matching is EXACT (no fuzzy/substring) — aliases must be pre-populated.
    Caller is responsible for the name normalization they want (trim, NFC, etc.).
    """
    if not name or len(name) > 128:
        return None  # defensive bound
    if as_of is None:
        sql = text("""
            SELECT e.corp_code, e.canonical_name, e.current_ticker
            FROM entity_aliases a
            JOIN entities e USING (corp_code)
            WHERE a.kind IN ('name', 'short_name', 'english_name')
              AND a.value = :v
              AND a.valid_to IS NULL
            LIMIT 1
        """)
        params = {"v": name}
    else:
        sql = text("""
            SELECT e.corp_code, e.canonical_name, e.current_ticker
            FROM entity_aliases a
            JOIN entities e USING (corp_code)
            WHERE a.kind IN ('name', 'short_name', 'english_name')
              AND a.value = :v
              AND a.valid_from <= :asof
              AND (a.valid_to IS NULL OR a.valid_to > :asof)
            LIMIT 1
        """)
        params = {"v": name, "asof": as_of}
    with engine.connect() as conn:
        row = conn.execute(sql, params).first()
    if row is None:
        return None
    return Entity(
        corp_code=row.corp_code,
        canonical_name=row.canonical_name,
        current_ticker=row.current_ticker,
    )
```

### Precondition task: seed name aliases

The alias table currently only holds `kind='ticker'` rows (Bug-C seeding). For `collect_news` to resolve "삼성전자" → `corp_code=00126380`, an **alias-seeding task** must run before or during Phase 4:

```python
# src/db/seed_name_aliases.py (new)
# Query entities where canonical_name is set → insert (corp_code, kind='name', value=canonical_name, valid_from=today, valid_to=NULL)
# For short names (e.g., "삼성전" is NOT a real alias, but "삼성" might conflict) — only insert canonical_name + any additional names from DART corp list.
```

**Recommended:** a one-shot migration task (not a collector) that runs `dart_fss.get_corp_list()` once, iterates, and upserts `canonical_name` and any DART-supplied English name as aliases. Could live in Phase 4 Wave 0 or be a quick-task.

## CLI Extension Plan

Current `src/cli/__main__.py` has a `collect` subparser with a hard-coded `dart` sub-subparser (`collect_subs.add_parser("dart", ...)`). To add krx/news/macro/kind + `all`:

### New structure

```
stock collect dart   --corp-code X --since Y [--max-docs N]   # unchanged
stock collect krx    [--since YYYY-MM-DD]                     # defaults to today KRX
stock collect news   [--since YYYY-MM-DD] [--max-per-feed N]
stock collect macro  [--series base_rate_kr,usd_krw]          # default = all in macro_series.yaml
stock collect kind   [--since YYYY-MM-DD]
stock collect all    [--sources=krx,news,macro,kind]          # default set = {krx, news, macro, kind}
```

### Diff to `src/cli/__main__.py::build_parser`

```python
# After the existing `dart` subparser block, add:

krx = collect_subs.add_parser("krx", help="Collect KRX OHLCV + flow + short (COLL-02)")
krx.add_argument("--since", default=None, help="YYYY-MM-DD (default: today KST trading day)")
krx.set_defaults(func=cmd_collect_krx)

news = collect_subs.add_parser("news", help="Collect 한경/이데일리 news (COLL-03)")
news.add_argument("--since", default=None)
news.add_argument("--max-per-feed", type=int, default=100)
news.set_defaults(func=cmd_collect_news)

macro = collect_subs.add_parser("macro", help="Collect ECOS+FRED macro (COLL-04)")
macro.add_argument("--series", default=None, help="Comma-separated labels; default=all")
macro.set_defaults(func=cmd_collect_macro)

kind = collect_subs.add_parser("kind", help="Collect KIND events (COLL-05)")
kind.add_argument("--since", default=None)
kind.set_defaults(func=cmd_collect_kind)

all_ = collect_subs.add_parser("all", help="Run all collectors with per-source isolation")
all_.add_argument(
    "--sources",
    default="krx,news,macro,kind",
    help="Comma-separated subset (fail-fast on unknown — D-21). Default excludes dart.",
)
all_.add_argument("--since", default=None)
all_.set_defaults(func=cmd_collect_all)
```

### `src/cli/commands.py` additions

```python
def cmd_collect_krx(args) -> int:
    from collectors.krx import collect_krx
    from db.engine import get_engine
    stats = collect_krx(vault_root=Path(args.vault_root), engine=get_engine(), since=args.since)
    print(json.dumps(stats, ensure_ascii=False, default=str))
    return 0 if not stats.get("failed") else 1

# Analogous: cmd_collect_news, cmd_collect_macro, cmd_collect_kind

def cmd_collect_all(args) -> int:
    """D-19: in-process try/except isolation. D-20: exit 1 on any failure, JSON to stderr."""
    from db.engine import get_engine
    engine = get_engine()
    vault_root = Path(args.vault_root)
    requested = args.sources.split(",")
    known = {"krx", "news", "macro", "kind", "dart"}  # dart valid but not in default
    unknown = set(requested) - known
    if unknown:
        print(f"Unknown sources: {sorted(unknown)}", file=sys.stderr)
        return 2  # D-21 fail-fast

    results: dict[str, dict] = {}
    for src in requested:
        start = time.monotonic()
        try:
            fn = _SOURCE_DISPATCH[src]    # dict: 'krx' -> collect_krx, ...
            src_stats = fn(vault_root=vault_root, engine=engine, since=args.since)
            results[src] = {
                "status": "ok" if not src_stats.get("failed") else "partial",
                "docs_processed": src_stats.get("succeeded", 0),
                "elapsed_ms": int((time.monotonic() - start) * 1000),
                **({"failed_count": len(src_stats["failed"])} if src_stats.get("failed") else {}),
            }
        except Exception as exc:    # D-19 swallow
            results[src] = {
                "status": "error",
                "error": str(exc),
                "elapsed_ms": int((time.monotonic() - start) * 1000),
            }
    report = {
        "run_at": datetime.now(UTC).isoformat(),
        "sources": results,
    }
    print(json.dumps(report, ensure_ascii=False), file=sys.stderr)   # D-20: stderr
    any_failed = any(r["status"] in ("error", "partial") for r in results.values())
    return 1 if any_failed else 0
```

`_SOURCE_DISPATCH` is a module-level dict; `--since` kwargs may be `None` for collectors that don't need it (they default to today).

### Backwards compatibility (D-18)

`stock collect dart --corp-code=X --since=Y` signature is **unchanged** — `dart` sub-subparser kept verbatim. Add `dart` to `_SOURCE_DISPATCH` for `stock collect all --sources=dart` optional invocation (but keep it out of the default set).

## Test Fixture Inventory

Per-collector fixture layout under `tests/fixtures/`:

### `tests/fixtures/krx/`

| File | Purpose | How to capture |
|------|---------|----------------|
| `ohlcv_005930_20260417.json` | 1-row OHLCV snapshot | `stock.get_market_ohlcv_by_date(...)` → `df.to_json()` |
| `trading_value_005930_20260417.json` | Investor flow row | `df.to_json()` |
| `shorting_balance_005930_20260417.json` | Short balance row | `df.to_json()` |
| `krx_admin_issue_list_20260417.json` | 관리종목 list (MDC) | `curl` MDCSTAT03901 endpoint |
| `krx_warning_list_20260417.json` | 투자경고 list | `curl` MDCSTAT03501 endpoint |
| `krx_suspension_list_20260417.json` | 거래정지 list | `curl` MDC suspension endpoint |

Unit tests monkey-patch `pykrx.stock.get_market_ohlcv_by_date` to return `pd.read_json(fixture)`.

### `tests/fixtures/rss/`

| File | Source |
|------|--------|
| `hankyung_economy.xml` | `curl https://www.hankyung.com/feed/economy` |
| `hankyung_finance.xml` | `curl https://www.hankyung.com/feed/finance` |
| `edaily_news.xml` | Wave-0 probe — confirm URL first |

Also one full HTML article per outlet under `tests/fixtures/news/` to test trafilatura extraction + 2-paragraph slicing.

### `tests/fixtures/ecos/`

| File | Purpose |
|------|---------|
| `base_rate_kr.json` | Snapshot of `get_statistic_search` response for 기준금리 |
| `usd_krw.json` | Snapshot for 원/달러 |
| `empty_result.json` | Empty `StatisticSearch.row` response — tests error path |

### `tests/fixtures/fred/`

| File | Purpose |
|------|---------|
| `DGS10.json` | JSON from `fred.get_series("DGS10", observation_start=...)` |
| `DCOILWTICO.json` | Ditto |

### `tests/fixtures/kind/` (D-16 mandatory)

| File | Purpose |
|------|---------|
| `nfaith_status_page1.html` | Snapshot of 불성실공시 현황 list page |
| `nfaith_status_empty.html` | Page with no rows (edge case) |
| `nfaith_status_malformed.html` | Layout-changed variant → tests `ParseError` (D-17) |

CI runs the parser against these three; never hits live KIND.

### Framework choice

- **pytest** (already project convention — `tests/conftest.py` has `pg_engine, pg_clean`).
- For fixture recording: plain file snapshots. Do **not** introduce `vcrpy` — adds deps and parse complexity for this scale.
- Mock network via `monkeypatch.setattr` on the lowest-level function (e.g., `collectors.krx.fetcher._get_ohlcv`). The collector-level tests pass a fake `vault_root = tmp_path`.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio (if needed); already installed |
| Config file | `pyproject.toml [tool.pytest.ini_options]` (Phase 1 FOUND-05) |
| Quick run command | `uv run pytest tests/test_collect_<source>.py -x -q` |
| Full suite command | `uv run pytest -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| COLL-02 | KRX collector writes OHLCV+flow+short for a ticker | integration (fixtures) | `pytest tests/test_collect_krx.py::test_writes_merged_file -x` | ❌ Wave 0 |
| COLL-02 | KRX collector skips unchanged file by content_hash | unit | `pytest tests/test_collect_krx.py::test_idempotent -x` | ❌ Wave 0 |
| COLL-02 | KRX collector records heartbeat on success | unit | `pytest tests/test_collect_krx.py::test_heartbeat -x` | ❌ Wave 0 |
| COLL-02 | KRX collector tolerates non-trading-day empty DataFrame | unit | `pytest tests/test_collect_krx.py::test_holiday_skip -x` | ❌ Wave 0 |
| COLL-03 | News collector extracts 2 paragraphs from trafilatura output | unit | `pytest tests/test_collect_news.py::test_two_paragraph_slice -x` | ❌ Wave 0 |
| COLL-03 | News collector drops articles with no ticker match | unit | `pytest tests/test_collect_news.py::test_drop_unmatched -x` | ❌ Wave 0 |
| COLL-03 | News collector resolves alias → entity | integration | `pytest tests/test_collect_news.py::test_alias_resolution -x` | ❌ Wave 0 |
| COLL-03 | News url_hash8 dedup | unit | `pytest tests/test_collect_news.py::test_url_hash_dedup -x` | ❌ Wave 0 |
| COLL-04 | Macro collector appends new observations, skips duplicates | unit | `pytest tests/test_collect_macro.py::test_append_idempotent -x` | ❌ Wave 0 |
| COLL-04 | Macro collector handles empty ECOS response | unit | `pytest tests/test_collect_macro.py::test_empty_response -x` | ❌ Wave 0 |
| COLL-04 | Macro series catalog loads | unit | `pytest tests/test_collect_macro.py::test_yaml_loader -x` | ❌ Wave 0 |
| COLL-05 | KIND parser extracts event rows from fixture HTML | unit | `pytest tests/test_collect_kind.py::test_parse_fixture -x` | ❌ Wave 0 |
| COLL-05 | KIND parser raises ParseError on malformed HTML | unit | `pytest tests/test_collect_kind.py::test_parse_error -x` | ❌ Wave 0 |
| COLL-05 | KIND robots.txt check gates collector startup | unit | `pytest tests/test_collect_kind.py::test_robots_assertion -x` | ❌ Wave 0 |
| COLL-05 | KIND rate-limiter enforces ≥1s between requests | unit | `pytest tests/test_collect_kind.py::test_rate_limit -x` | ❌ Wave 0 |
| COLL-05 | KRX MDC 거래정지 snapshot produces suspension events | unit | `pytest tests/test_collect_kind.py::test_suspension_from_krx -x` | ❌ Wave 0 |
| CLI | `stock collect all --sources=krx,news` runs only requested | unit | `pytest tests/test_cli_collect_all.py::test_subset -x` | ❌ Wave 0 |
| CLI | One source failing does not block others; exit code 1 | unit | `pytest tests/test_cli_collect_all.py::test_isolation -x` | ❌ Wave 0 |
| CLI | Unknown `--sources=` value exits fail-fast | unit | `pytest tests/test_cli_collect_all.py::test_unknown_source -x` | ❌ Wave 0 |
| Shared | `Portfolio.load` validates schema; rejects missing fields | unit | `pytest tests/test_portfolio.py -x` | ❌ Wave 0 |
| Shared | `resolve_entity_by_alias` exact-match + as_of temporal | unit | `pytest tests/test_entity_alias.py -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_collect_<source>.py -x -q` (≤ 5s for a single source's suite).
- **Per wave merge:** `uv run pytest -x -q` (full project suite ≤ 60s — no live network calls in CI).
- **Phase gate:** Full suite green + one manual end-to-end probe of `stock collect all` against live APIs (non-CI, operator-run, documented in Phase 4 VERIFICATION).

### Wave 0 Gaps

- [ ] `tests/test_collect_krx.py`
- [ ] `tests/test_collect_news.py`
- [ ] `tests/test_collect_macro.py`
- [ ] `tests/test_collect_kind.py`
- [ ] `tests/test_cli_collect_all.py`
- [ ] `tests/test_portfolio.py`
- [ ] `tests/test_entity_alias.py`
- [ ] `tests/fixtures/krx/*.json` (6 files)
- [ ] `tests/fixtures/rss/{hankyung_economy,hankyung_finance,edaily_news}.xml`
- [ ] `tests/fixtures/news/*.html` (2 files)
- [ ] `tests/fixtures/ecos/*.json` (3 files)
- [ ] `tests/fixtures/fred/*.json` (2 files)
- [ ] `tests/fixtures/kind/*.html` (3 files)
- [ ] `.planning/macro_series.yaml` (new catalog file)
- [ ] `vault/notes/portfolio.md` (seed example)
- [ ] `src/shared/portfolio.py` (Portfolio Pydantic model + loader)
- [ ] `src/db/entity.py` +`resolve_entity_by_alias()` (new function in existing file)
- [ ] `src/db/seed_name_aliases.py` (one-shot alias seeder)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No user auth — personal CLI |
| V3 Session Management | no | No sessions |
| V4 Access Control | no | Local filesystem permissions only |
| V5 Input Validation | yes | Pydantic for `Portfolio`, regex for ticker/corp_code/url_hash/event_date before any path construction |
| V6 Cryptography | n/a | sha256 for content_hash is dedup-only (Phase 2 decision: not a security primitive) |
| V7 Error Handling & Logging | yes | Never log API keys; `CollectorConfigError` pattern (mirrors DART) omits secret from message |
| V10 Malicious Code | yes | `tests/test_import_guard.py` (COLL-07) already blocks `anthropic`/`openai` in collectors |
| V12 Files & Resources | yes | Path traversal defense: digit-regex validation before `Path.joinpath` (T-3-12 pattern) |
| V14 Configuration | yes | Secrets from `.env` only; `.env` gitignored (OPS-06 complete from Phase 1) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SSRF from user-supplied URL in feed item | Information Disclosure | Only parse RSS-advertised URLs; never follow arbitrary user input; bind timeout on `requests.get` |
| Prompt injection via news body | Tampering (downstream Phase 5) | `trust_level='semi_trusted'` + XML delimiter wrap by ingest (INGEST-08 already live) |
| HTML parsing XXE | Info Disclosure | `BeautifulSoup(html, "lxml")` does not resolve external entities by default; still, avoid `lxml.etree.parse` on untrusted XML streams — only `feedparser` (which is safe) for RSS |
| Secret leakage in error messages | Info Disclosure | Follow DART `client.py::CollectorConfigError` — never embed secret in raised message |
| Path traversal via `outlet` or `event_type` | Tampering | Enforce enums: `outlet ∈ {hankyung, edaily}`, `event_type ∈ {suspension, watchlist_designation, investment_caution, unfaithful_disclosure}` |
| Rate-limit bypass (accidental self-DoS of KIND) | Availability (theirs) | 1 req/sec throttle + identifiable User-Agent (D-15) |
| robots.txt scope creep | Compliance | `urllib.robotparser` assertion at startup; fail collector if Disallow |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | ECOS `722Y001` is 한국은행 기준금리 | §2 Library APIs | Collector returns empty; no data → heartbeat failure, no crash |
| A2 | ECOS `731Y001` is USD/KRW 매매기준율 | §2 Library APIs | Same as A1 |
| A3 | edaily RSS URL `rss.edaily.co.kr/edaily_news.xml` | §3.1 + Test Fixtures | News collector misses entire outlet → plan needs revised feed URL |
| A4 | KIND 불성실공시 현황 page = `nfaithdisclsstatus.do?method=searchNfaithDisclsStatusMain` | §KIND | Parser hits 404; Wave-0 probe must discover real path |
| A5 | KIND 현황 page is HTML table (not JS-rendered) | §KIND | If JS-rendered, `requests` returns empty body → must re-evaluate (selenium vetoed by CLAUDE.md — would need different data source or API) |
| A6 | KIND selectors `table.list > tbody > tr` etc. | §KIND | Parser fails gracefully to ParseError (D-17); planner must update selectors post-probe |
| A7 | KRX MDC `MDCSTAT03901` = 관리종목 list | §1.4 | Same as A1 — no data, no crash; probe confirms |
| A8 | 거래정지 has no distinct `pblntf_detail_ty` in DART | §5 | If wrong, we have a cleaner filter available; no harm |
| A9 | `feedparser` handles Korean RSS encoding correctly | §3.1 | Test fixtures will expose any mojibake |
| A10 | Phase 2 `entity_aliases.kind` column accepts new values `'name','short_name','english_name'` without migration | §Entity Alias | If CHECK constraint exists, needs a migration; inspect `db/migrations/` before implementation |

## Open Questions / Risks

1. **ECOS series IDs (A1/A2):** Must be confirmed via Wave-0 probe against live ECOS API before `macro_series.yaml` is committed with real IDs. Planner: schedule this as the first task in the macro plan.

2. **KIND 현황 URL (A4) + selectors (A6):** Must be discovered manually in a browser. Planner: schedule as the first task in the KIND plan. Output: committed `tests/fixtures/kind/nfaith_status_page1.html` + verified URL constant.

3. **edaily RSS URL (A3):** Single `curl` probe, 5 minutes work, but must happen before news collector implementation.

4. **pykrx 관리종목/투자경고 strategy (§1.4 A7):** Direct-MDC-JSON approach needs empirical confirmation that the endpoints still respond (KRX changes these periodically). Planner: Wave-0 probe all three bld codes (MDCSTAT03901 / MDCSTAT03501 / suspension).

5. **`entity_aliases.kind` CHECK constraint (A10):** Planner must read `src/db/migrations/` (specifically the Phase 2 migration that created `entity_aliases`) to check whether `kind` is enum-constrained or free-text. If constrained, the `resolve_entity_by_alias` implementation requires a new migration before it can match on `'name'`.

6. **DART 거래정지 vs KRX 거래정지 precedence (§5):** When both sources report the same ticker-date suspension, which wins? Recommendation: KRX primary (it's the authoritative source for halt status), DART is a supplement only for richer context. De-dup in collector by `(ticker, event_date, event_type)` composite key; first write wins, others skipped by content_hash.

7. **`valid_until`:** 30 days — the libraries (pykrx, trafilatura, fredapi) are stable; the ECOS codes + KIND page structure are the moving parts and both have Wave-0 probes to catch drift.

---

## RESEARCH COMPLETE

**Phase:** 4 - Multi-Source Collector Coverage
**Confidence:** HIGH on Phase 3 patterns & pykrx/trafilatura/FRED; MEDIUM on dart-fss 거래정지 filter & PublicDataReader API shape; LOW on ECOS series IDs & KIND 불성실공시 현황 URL (both flagged with explicit Wave-0 probes).

### Key Findings
- `resolve_entity_by_alias` does **not** exist — Phase 4 must add it (§Entity Alias Resolution). `entity_aliases.kind` CHECK constraint needs inspection before name-alias rows can be inserted.
- `pykrx.stock.get_market_status_by_ticker` as named in CONTEXT D-14 does **not** exist. Primary path is direct KRX MDC JSON scrape (well-known endpoint family; same source pykrx uses internally).
- ECOS series IDs in CONTEXT (`722Y001`, `731Y001`) are [ASSUMED] — must be verified in a Wave-0 probe, not at implementation time.
- KIND 불성실공시 현황 URL + selectors are [ASSUMED] — Wave-0 browser probe required; commit live HTML snapshot to `tests/fixtures/kind/` before parser work.
- Hankyung RSS feeds **verified** (`/feed/economy`, `/feed/finance`). edaily RSS URL is [ASSUMED] and needs a 5-minute curl probe.
- CLI extension plan is clean: add 4 subparsers + `all` subparser; `dart` subparser unchanged (backward compat D-18).

### File Created
`.planning/phases/04-multi-source-collector-coverage/04-RESEARCH.md`

### Confidence Assessment
| Area | Level | Reason |
|------|-------|--------|
| Phase 3 pattern replication | HIGH | Full source read; exact signatures/retry/atomic-write copied |
| pykrx OHLCV/flow/short | HIGH | Verified via GitHub + community references |
| pykrx 관리종목/투자경고 | MEDIUM | Function name in CONTEXT was a placeholder; MDC-JSON alternative is solid but needs probe |
| trafilatura extraction | HIGH | Official docs verified; 2-paragraph slicing is straightforward |
| RSS URLs — Hankyung | HIGH | Verified via hankyung.com/feed index |
| RSS URLs — edaily | LOW | One unverified source; probe task defined |
| ECOS series IDs | LOW | Placeholder codes explicitly; probe task defined |
| FRED series IDs | HIGH | DGS10 + DCOILWTICO are canonical FRED IDs |
| dart-fss 거래정지 filter | MEDIUM | No distinct subtype — in-Python title filter is correct but fragile |
| KIND URL + selectors | LOW | Needs live browser probe |
| CLI extension | HIGH | Clean argparse diff; Phase 3 `__main__.py` patterns well-understood |
| Entity alias implementation | MEDIUM | Requires migration check for `entity_aliases.kind` CHECK constraint |

### Open Questions
See §Open Questions / Risks. Seven items; five are Wave-0 probes (ECOS IDs, KIND URL, KIND selectors, edaily RSS, KRX MDC endpoints) plus one migration inspection (`entity_aliases.kind` constraint).

### Ready for Planning
Research complete. Planner should schedule probes as Wave-0 tasks (first in each relevant plan) before parser/client code is written. Recommended plan order: (01) Portfolio + resolve_entity_by_alias → (02) KRX → (03) Macro → (04) News → (05) KIND → (06) CLI `collect all` + integration test.
