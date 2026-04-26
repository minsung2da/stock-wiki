# Phase 10: Decision-context coverage — peer/historical valuation + supply-demand + private notes scaffold

**Gathered:** 2026-04-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Claude Code의 "X 매수해야 하나?" 통합 4축 질의(밸류에이션 + 수급 + 공시 + 메모)에 답할 수 있도록, v1 71개 요구사항에는 없는 **결정-맥락(reference frame) 레이어**를 추가한다. 구체적으로 4개 surface:

1. **Sector-relative valuation** — KRX 업종 소분류 기준 시가총액 top 10 피어와 5개 멀티플(PER/PBR/EV-EBITDA/PSR/배당수익률) 비교
2. **Historical valuation bands** — 관심 종목의 자기 자신 5년 멀티플 시계열 + 현재 퍼센타일
3. **Supply-demand signals** — Phase 4가 raw로 수집 중인 KRX 투자자 수급·공매도 데이터를 신호화(net buy 윈도우/streak/z-score/잔고변화), 티커별 적응 임계값 적용
4. **Private notes scaffold** — `notes/private/`(Phase 1 D-03) 하위에 ticker 폴더 + 날짜 journal 폴더 구조, 모든 메모 콘텐츠는 private overlay(.gitignored), Phase 8은 템플릿·스키마만 담당

**경계 — 이 페이즈가 다루지 않는 것:**
- 새로운 raw 수집기 추가 없음 — Phase 4 KRX raw + Phase 3/4 dart 재무 데이터만 재활용
- 공매도/대차 *원시* 수집은 Phase 4 책임이며 본 페이즈는 신호화만
- 자동 매매·스크리너·알림은 v2/Out-of-scope
- Phase 6 기존 MCP 툴 시그니처 변경 없음 — 신규 툴 3개 추가로 분리

</domain>

<decisions>
## Implementation Decisions

### Sector + Peer Selection (D-01 ~ D-04)

- **D-01:** 섹터 분류 = **KRX 업종 소분류** 우선, 해당 소분류 내 시총 상위 10개 미만이면 **대분류로 fallback**. pykrx `stock.get_market_sector_classifications()` 활용. KOSPI/KOSDAQ 별도 코드 체계 정규화 헬퍼 작성.
- **D-02:** Top 10 선정 = **시가총액 단순 상위 10개**. 거래대금·유동성 가중 없음(v2 검토). 선정 기준일은 valuation 스냅샷 산출일과 동일.
- **D-03:** 추적 멀티플 = **5개 모두**: PER, PBR, EV/EBITDA, PSR, 배당수익률. 적자 기업/금융주 무효 케이스는 멀티플 값 `null` + `_derived.valuation_caveats`에 사유 기록.
- **D-04:** **관심 종목이 sector top 10에 자동 포함되지 않으면 11번째 행으로 강제 추가** (rank=11, label="watchlist") — '내 종목이 어디 있나' 맥락 유지.

### Valuation Data Pipeline (D-05 ~ D-09)

- **D-05:** 데이터 소스 hybrid 전략:
  - **관심 종목(watchlist + holdings)** = `dart-fss` 자체계산. 분기 보고서에서 EPS/BPS/매출/EBITDA/총부채/현금성/배당 직접 추출 → pykrx 종가와 결합 → 5개 멀티플 산출. SoT·재현성 확보.
  - **피어(관심 X)** = 네이버 증권 종목개요 페이지 스크래이핑(완료된 멀티플 그대로). 빠른 처리, 원본 산식 이슈는 수용.
  - 양 소스의 동일 ticker 데이터가 같은 sector 파일에 공존 가능, `provenance.computed_by` 필드로 구분(`dart_fss` / `naver_scrape`).
- **D-06:** 새 collector = `src/collectors/valuation/`. 진입점 `collect_valuation`. 일배치(매일 장 마감 후, KRX 마감과 동일 슬롯). Phase 4 collector 패턴 준수(content-hash 멱등 · tenacity 재시도 · heartbeat · `anthropic` 금지).
- **D-07:** 산출물 저장 = **`vault/raw/valuation/{sector_code}/{YYYY-MM-DD}.md`** (sector 단위, 1일 1파일). frontmatter에 `sector_code`, `sector_name`, `granularity`(small/large), `members: [{ticker, corp_code, market_cap, per, pbr, ev_ebitda, psr, dividend_yield, computed_by, caveats}]` 테이블 인라인 포함.
- **D-08:** Historical backfill = **일회성 스크립트** `stock backfill valuation --since 5y`. 관심 종목만 대상(피어는 backfill X). pykrx로 일별 종가 + dart-fss로 분기별 EPS/BPS 시계열 → 매 영업일 trailing 12M 멀티플 산출 → `vault/raw/valuation/_history/{ticker}.md`(append-only 시계열)에 적재. 피어 historical은 daily snapshot이 시간 흐름에 따라 자연 누적.
- **D-09:** 분기 재무 정정(supersedes 체인 — Phase 2 D-08) 시: 해당 분기 이후 모든 daily 멀티플 행에 대해 trailing 12M 자동 롤오버 재계산. 정정 사실은 `_derived.valuation_restated_at` + `review_flags: ["restatement"]`로 표시. 과거 스냅샷 파일은 in-place 재작성하고 git diff로 추적 가능하게 한다.

### Historical Bands & DB View (D-10 ~ D-12)

- **D-10:** Lookback = **5년**. 모든 percentile/min/max/avg 통계는 5년 윈도우 기준.
- **D-11:** **DB `valuation_snapshots` 테이블 추가** (Alembic 0003 추정). 컬럼: `id BIGSERIAL`, `corp_code CHAR(8)`, `as_of DATE`, `metric TEXT`(per/pbr/ev_ebitda/psr/div_yield), `value NUMERIC`, `computed_by TEXT`, `source_doc_id TEXT REFERENCES documents(id)`, `created_at TIMESTAMPTZ`. 인덱스: `(corp_code, metric, as_of DESC)`.
  - SoT는 여전히 vault `raw/valuation/`. ingest 워커가 sector 파일을 읽어 valuation_snapshots에 fan-out.
  - `ingest rebuild`(STORE-05)로 vault만으로 테이블 재생성 가능.
- **D-12:** Ticker 관점 historical 밴드 조회는 **MCP가 SQL 집계로 응답**. percentile_cont, min/max/avg 모두 SQL window function. 별도 ticker hub 파일 자동 생성하지 않음(Phase 8 DASH-04 hub가 추후 valuation 섹션을 dataview로 끌어옴).

### Supply-Demand Signals (D-13 ~ D-17)

- **D-13:** 신호 4종 모두 채택:
  - **Cumulative net buy** by 투자자(외국인·기관·개인) × window(5d/20d/60d)
  - **Streak counter** (연속 순매수일·순매도일) by 투자자
  - **Z-score** (60일 rolling 평균·표준편차 대비 당일 net buy)
  - **공매도 잔고 변화** + **대차 잔고 변화** (절댓값 + 시총 대비 비율)
- **D-14:** 계산·저장 = **DB `supply_demand_signals` 테이블** (Alembic 0004 추정). 컬럼: `corp_code`, `as_of DATE`, `investor TEXT`(foreign/institution/retail/null=overall), `window_days INT NULL`, `signal_type TEXT`(net_buy/streak/zscore/short_balance/loan_balance), `value NUMERIC`, `is_outlier BOOLEAN`. SoT는 Phase 4 `vault/raw/krx/`. ingest 워커가 KRX raw 변경 감지 시 fan-out 재계산. `ingest rebuild` 호환.
- **D-15:** 임계값 = **티커별 적응형**. 윈도우 = 직전 252영업일(약 1년). 알고리즘:
  - 네 신호 각각에 대해 252일 rolling 표준편차 계산
  - z-score `|z| ≥ 2.0` 또는 percentile ≤ 5/≥ 95 → `is_outlier = true`
  - streak는 자체 분포에서 95퍼센타일 길이 초과 시 outlier
  - 임계값 알고리즘은 첫 구현부터 적응형으로 가나, 계수(2.0σ, 95p)는 코드 상수 → 향후 조정 용이
- **D-16:** 252일 미만 데이터 종목(신규 상장/거래정지 후 재개)은 `is_outlier = null` + `insufficient_history = true` 메타. Claude는 이 경우 raw 수치만 제시.
- **D-17:** 신호 계산은 KRX raw 도착 시 incremental(전일 대비 새 영업일분만 추가). 전체 재계산은 `stock signal rebuild` 명령(STORE-05 호환).

### Private Notes Scaffold (D-18 ~ D-22)

- **D-18:** `notes/private/` 하위 hybrid 구조:
  ```
  notes/private/
  ├── {ticker}/                 # ticker 중심 누적
  │   ├── thesis.md             # 투자 논리 + kill criteria (single file, append on revision)
  │   ├── conviction.md         # 확신도 변화 로그
  │   └── notes.md              # 자유 메모
  └── journal/
      └── YYYY-MM-DD.md         # 일자별 의사결정 로그(여러 종목 cross-cut)
  ```
  ticker 폴더는 종목별 누적 매모, journal은 일자별 cross-cut 기록 분리.
- **D-19:** **Phase 8과 분업** = Phase 8(NOTE-01/02/03)은 **템플릿 파일 + frontmatter 스키마 + Pydantic 검증만** 담당하고 git에 커밋. 실제 콘텐츠는 모두 `notes/private/`에 적재되며 `.gitignore` 영역(Phase 1 D-03 연속). Phase 8 NOTE-01의 `notes/theses/` 디렉토리는 **템플릿 디렉토리(`templates/notes/thesis.md` 등)로 위치 변경**하여 Phase 10에서 사용. (Phase 8 plan 갱신 필요 — Deferred 항목 참조)
- **D-20:** 메모 frontmatter 스키마(Phase 8 NOTE-03 베이스):
  ```yaml
  ---
  type: thesis | journal | conviction | note
  tickers: ["005930"]   # multi-ticker 가능 (journal entry)
  tags: [...]
  created: 2026-04-26T15:00:00+09:00
  updated: 2026-04-26T15:00:00+09:00
  author: "yamin"
  conviction_score: 0.7   # optional, 0-1, conviction.md only
  ---
  ```
- **D-21:** **Claude 쓰기 권한** = MCP `add_note`(Phase 6 MCP-08) 경로 화이트리스트를 `vault/notes/` → `vault/notes/` ∪ `notes/private/` 으로 확장. 세션 중 "이 종목 메모해줘"·"오늘 의사결정 일기로 남겨줘" 자동 적재 가능. write 정책은 **append-only가 아닌 일반 write 허용**(사용자가 직접 수정도 자유롭게).
- **D-22:** Private 메모는 ingest 파이프라인에 **포함**. embedding · BM25 인덱스 · DB chunks 모두 동일하게. 검색(`search` MCP-02)에서 private 메모도 결과로 나옴(개인 vault라는 가정 하에). 향후 다중 사용자 시 `chunks.visibility` 컬럼으로 격리 가능하나 v1+10에는 구현 X.

### MCP Tool Surface Extension (D-23 ~ D-27)

- **D-23:** **신규 MCP 툴 3개 추가** (Phase 6 MCP-03~10과 동일한 FastMCP 패턴):
  - `get_valuation_context(ticker, as_of?)` — 5개 멀티플 현재 + sector top10 비교 테이블 + 5y 밴드(min/avg/current/max/percentile)
  - `get_supply_demand_signals(ticker, as_of?, since_days?=60)` — window 테이블(5d/20d/60d) × 투자자(외국인·기관·개인) net buy + streak + z-score + 공매도/대차 잔고
  - `get_private_thesis(ticker)` — `notes/private/{ticker}/*.md` 본문 결합 반환(thesis + conviction 최신 + notes 본문)
- **D-24:** **`get_ticker_overview`(MCP-03) 응답에 자동 포함**: `valuation` (get_valuation_context summary), `supply_demand` (활성 신호만 강조 + 핵심 수치 표), `private_thesis` (get_private_thesis 본문, 섹션 기본 하단). Phase 6 MCP-03 스펙은 본 페이즈가 확장.
  - "X 매수해야 하나?" 단일 호출로 4축(밸류+수급+공시+메모) 답변 가능 — JUDGE-01과 직접 정합.
- **D-25:** Valuation 응답 스키마(get_valuation_context):
  ```json
  {
    "ticker": "005930", "corp_code": "00126380", "as_of": "2026-04-26",
    "current": {"per": 18.2, "pbr": 1.4, "ev_ebitda": 6.7, "psr": 1.8, "dividend_yield": 0.022,
                "computed_by": "dart_fss", "caveats": []},
    "sector": {"code": "...", "name": "...", "granularity": "small"},
    "sector_top10": [{"rank": 1, "ticker": "...", "name": "...", "market_cap": ..., "per": ..., ...}, ...],
    "historical_5y": {
      "per": {"min": 12.1, "avg": 15.4, "current": 18.2, "max": 22.0, "percentile": 78},
      "pbr": {...}, ...
    },
    "vault_paths": ["vault/raw/valuation/{sector_code}/{date}.md", "vault/raw/valuation/_history/{ticker}.md"]
  }
  ```
- **D-26:** Supply-demand 응답 스키마(get_supply_demand_signals):
  ```json
  {
    "ticker": "005930", "as_of": "2026-04-26",
    "windows": [
      {"window_days": 5,
       "by_investor": {"foreign": {"net_buy_won": ..., "is_outlier": false},
                       "institution": {...}, "retail": {...}}},
      {"window_days": 20, "..."}, {"window_days": 60, "..."}
    ],
    "streak": {"foreign": {"days": 12, "side": "buy", "is_outlier": true},
               "institution": {...}, "retail": {...}},
    "zscore": {"foreign_today": 2.3, "institution_today": -0.4, "retail_today": -1.1},
    "short_balance": {"shares": ..., "ratio_to_float": 0.012, "delta_5d": +0.002, "is_outlier": false},
    "loan_balance": {"shares": ..., "delta_5d": ..., "is_outlier": false},
    "insufficient_history": false,
    "vault_paths": ["vault/raw/krx/{date}/{ticker}.md", ...]
  }
  ```
- **D-27:** 응답 토큰 가드 = Phase 3 RET-03 정책 유지(8k 미만, p95 < 5초). sector_top10 테이블이 가장 큰 비중 — 컬럼 한도 + 멀티플 소수 자릿수 제한(.2f).

### Folded Todos
없음 (todo backlog에서 본 페이즈 매칭 항목 없음).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Boundary & Prior Decisions
- `.planning/PROJECT.md` — Core value (4축 통합 판단), 비용 원칙, vault SoT
- `.planning/REQUIREMENTS.md` — v1 71 요구사항(완료 현황 확인), Out of Scope
- `.planning/ROADMAP.md` §"Phase 10" — 페이즈 타이틀 출처
- `.planning/phases/01-load-bearing-foundation/01-CONTEXT.md` D-03~D-05 — `notes/private/` 경로·`.gitignore` 정책, `templates/portfolio.md` 패턴
- `.planning/phases/01-load-bearing-foundation/01-CONTEXT.md` D-09~D-11 — frontmatter 3-zone 구조 (provenance/ingest_state/_derived)
- `.planning/phases/02-canonical-entity-identity/02-CONTEXT.md` D-05~D-08 — supersedes edge 처리 (Phase 10 D-09 재무 정정 정합 근거)
- `.planning/phases/02-canonical-entity-identity/02-CONTEXT.md` D-13~D-15 — content-hash dedup (Phase 10 D-06 멱등 패턴)
- `.planning/phases/03-one-company-walking-skeleton/03-CONTEXT.md` D-09~D-14 — 하이브리드 검색 파라미터 (D-22 chunks 인덱싱 정합)
- `.planning/phases/04-multi-source-collector-coverage/04-CONTEXT.md` D-01~D-04 — Portfolio 로딩 패턴 (Phase 10 collector 재사용)
- `.planning/phases/04-multi-source-collector-coverage/04-CONTEXT.md` D-05 — KRX raw layout (Phase 10 supply-demand SoT)

### Phase 6/8 Coordination (Forward Refs)
- `.planning/REQUIREMENTS.md` §"stock-mcp 서버" MCP-03·MCP-08 — 본 페이즈가 확장하는 툴 시그니처
- `.planning/REQUIREMENTS.md` §"메모·리서치" NOTE-01/02/03 — Phase 8과의 분업 경계
- `.planning/REQUIREMENTS.md` §"Claude 판단 보조" JUDGE-01·JUDGE-06 — 4축 답변·private 가중치 정합

### External Specs
- pykrx README — `stock.get_market_sector_classifications()`, OHLCV·투자자 수급·공매도 API
- dart-fss README — 재무제표 구조화 접근자 (EPS/BPS/EBITDA 산출 경로)
- pgvector 0.8 — `iterative_scan` 옵션 (D-22 검색 정합)
- VectorChord-BM25 — Korean 토큰화 정합

### Korean Sector Taxonomy
- KRX 표준코드 분류표 (KOSPI/KOSDAQ 업종 코드, 대·소분류 매핑) — collector 구현 시 캐시 필요. URL: krx.co.kr 통계 → 업종분류 메뉴

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`src/shared/portfolio.py::Portfolio`** (Phase 4) — watchlist + holdings 로딩 헬퍼. Phase 10 valuation/signals collector가 동일 호출로 ticker scope 결정.
- **`src/collectors/krx/`** (Phase 4) — pykrx 기반 OHLCV·투자자 수급·공매도 수집기. Supply-demand 신호 계산은 이 raw 파일을 입력으로 받으며 별도 수집 없음.
- **`src/collectors/dart/`** (Phase 3+4) — dart-fss 래퍼. EPS/BPS/매출/총부채/현금성 추출 메서드 활용 → 자체 멀티플 계산.
- **`src/shared/frontmatter.py`** (Phase 1) — `FrontMatter` Pydantic 모델. `_derived.valuation_caveats`·`review_flags` 추가 필드는 본 페이즈에서 확장.
- **`src/shared/content_hash.py`** (Phase 1·2) — 멱등 업서트 키. Sector 파일·private notes 모두 동일 해시 패턴 사용.
- **`src/db/migrations/`** Alembic — `valuation_snapshots`·`supply_demand_signals` 신규 테이블 마이그레이션.
- **`src/db/entity.py`** — ORM 베이스. 신규 테이블 두 개 추가.
- **`src/ingest/worker.py`** — sector valuation 파일·KRX raw 파일 변경 감지 후 fan-out.
- **`src/stock_mcp/tools/`** — `search.py` 패턴 그대로. `get_valuation_context.py`·`get_supply_demand_signals.py`·`get_private_thesis.py` 신규 모듈.
- **`src/stock_mcp/models.py`** — Pydantic 응답 스키마(D-25/D-26 정의 모델 신규 추가).

### Established Patterns

- **Collector 패턴(Phase 4)** — `Portfolio.load()` 호출 → tenacity 재시도 → content-hash 멱등 업서트 → heartbeat append → fail-isolated. 본 페이즈 valuation collector 동일 적용.
- **Frontmatter 3-zone(Phase 1 D-09)** — provenance/ingest_state/_derived 분리. valuation 산출물의 `caveats`·`computed_by`는 `provenance` (수집 시 결정), `valuation_restated_at`은 `ingest_state` (재인제스트 메타).
- **MCP tool docstring(Phase 6 MCP-10)** — LLM-facing 행동 계약. 신규 3개 툴 모두 동일 컨벤션 + CI 레이턴시·토큰 검증.
- **하이브리드 검색(Phase 3 RET-01)** — private 메모도 동일 인덱스에 들어가므로 `search`에서 자연 노출.

### Integration Points

- **`stock collect all`** CLI(Phase 4) — `valuation` 소스 추가. 호출 형태: `stock collect valuation --since YYYY-MM-DD`.
- **`stock backfill valuation`** — 신규 명령(historical 일회성 백필).
- **`stock signal rebuild`** — 신규 명령(supply_demand_signals 전체 재계산).
- **Phase 6 `get_ticker_overview`** — 본 페이즈가 응답 스키마에 `valuation`/`supply_demand`/`private_thesis` 섹션 주입(MCP-03 확장).
- **Phase 6 `add_note`(MCP-08)** — 화이트리스트 경로 확장 (`notes/private/` 추가). 본 페이즈에서 정책 변경.
- **Phase 8 `dashboards/portfolio.md`·by-ticker hub** — Dataview 쿼리로 valuation·supply-demand 섹션을 자연스럽게 끌어다 표시(Phase 8 plan 갱신 필요).

</code_context>

<specifics>
## Specific Ideas

- **"X 지금 비싼가?"가 single tool call로 답해져야 함** — get_valuation_context 한 번으로 sector 비교 + 자기 시계열 퍼센타일 둘 다 포함.
- **사용자 시나리오 1순위 = "X 매수해야 하나?" 통합 4축** — get_ticker_overview가 모두 합쳐서 답함. 신규 3툴은 drill-down용이지 1차 진입은 overview.
- **개인 vault 가정** — private 메모를 search 결과에서 격리하지 않음. 다중 사용자는 v2.
- **재무 정정 시점에서 historical 밴드가 바뀌는 게 옳다** — 시장 인지보다 진실 추적 우선(D-09).
- **티커별 적응 임계값** — 처음부터 252일 rolling σ 기반. 단순 고정 z=2.0 대신.

</specifics>

<deferred>
## Deferred Ideas

- **임계값 계수 튜닝(σ·percentile 상수)** — v1+10에서는 코드 상수로 두고, eval(V2-QUAL-01) 이후 데이터 기반 재조정.
- **Top 10 선정에 거래대금 가중** — 시총 단순 상위가 첫 구현. 왜곡(거래량 적은 대형주) 시 가중 도입.
- **다중 사용자 private 격리** — `chunks.visibility` 컬럼·MCP 사용자 컨텍스트. 2~5명이 같은 git repo면 자연 분리, 외부 공유 시점에 추가.
- **FICS/WICS 도입** — KRX 분류로 시작, 의미 부족 사례 누적되면 v2에서 검토.
- **공매도 잔고 통계 API 직접 사용(KRX 정보데이터시스템)** — 현재 pykrx 경유. 정확도 차이 발생 시 직접 호출.
- **Phase 8 NOTE-01/02 디렉토리 위치 변경(`notes/theses/` → `templates/notes/`)** — Phase 10 D-19에 따른 Phase 8 plan 갱신. Phase 8 진입 전에 통합 검토 필요(Phase 6 → 7 → 8 순서이므로 시간 여유 있음).
- **Adaptive threshold 계산기 추출(reusable helper)** — 첫 구현은 supply_demand_signals에 인라인. 다른 신호(가격 변동성 등)에도 재사용되면 분리.
- **PDF 리포트 valuation 입력** — V2-DOC-01 OCR 이후, 증권사 컨센서스 멀티플을 peer 데이터로 주입.
- **MCP 사용자 의견 가중치 정책** — Phase 9 JUDGE-06에서 정의. 본 페이즈는 private 노출만 책임지고 가중치 결정은 Phase 9에 위임.

### Reviewed Todos (not folded)
없음.

</deferred>

---

*Phase: 10-decision-context-coverage-peer-historical-valuation-supply-d*
*Context gathered: 2026-04-26*
