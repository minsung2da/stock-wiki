# Phase 10: Decision-context coverage — peer/historical valuation + supply-demand + private notes scaffold

**Gathered:** 2026-04-26
**Patched:** 2026-04-26 (verification round — zone integrity, cross-phase coordination, gray-area policies)
**Status:** Ready for planning

<domain>
## Phase Boundary

Claude Code의 "X 매수해야 하나?" 통합 4축 질의(밸류에이션 + 수급 + 공시 + 메모)에 답할 수 있도록, v1 71개 요구사항에는 없는 **결정-맥락(reference frame) 레이어**를 추가한다. 구체적으로 4개 surface:

1. **Sector-relative valuation** — KRX 업종 소분류 기준 시가총액 top 10 피어와 5개 멀티플(PER/PBR/EV-EBITDA/PSR/배당수익률) 비교
2. **Historical valuation bands** — 관심 종목의 자기 자신 5년 멀티플 시계열 + 현재 퍼센타일
3. **Supply-demand signals** — Phase 4가 raw로 수집 중인 KRX 투자자 수급·공매도 데이터를 신호화(net buy 윈도우/streak/z-score/잔고변화), 티커별 적응 임계값 적용
4. **Private notes scaffold** — `notes/private/`(Phase 1 D-03) 하위에 ticker 폴더 + 날짜 journal 폴더 구조, 모든 메모 콘텐츠는 private overlay(.gitignored), Phase 8은 템플릿·스키마만 담당

**경계 — 이 페이즈가 다루지 않는 것:**
- 새로운 raw 수집기 추가 없음 — Phase 4 KRX raw + Phase 3/4 dart 재무 데이터만 재활용 (단 valuation 재가공용 신규 collector 1개는 추가)
- 공매도/대차 *원시* 수집은 Phase 4 책임이며 본 페이즈는 신호화만
- 자동 매매·스크리너·알림은 v2/Out-of-scope (피어 데이터는 컨텍스트 전용 — 피어 자체 매수 후보 surface 제공 X)
- 신호 *알림* surface(dashboards/alerts.md 자동 생성) = V2-ALERT-02 영역, 본 페이즈는 신호 *계산·노출*까지만
- Phase 6 기존 MCP 툴 시그니처 변경 없음(MCP-03, MCP-08은 응답·정책 확장만 — 본 페이즈가 수행) + 신규 툴 3개 추가

</domain>

<prerequisites>
## Cross-Phase Prerequisites

| ID | 영역 | 상태 | 잔여 작업 |
|---|---|---|---|
| **P-01** | Phase 1 ↔ Phase 4 portfolio 경로 단일화 | ✅ **결정·문서 갱신 완료 (2026-04-26)** | Phase 6 plan 첫 task: `vault/notes/portfolio.md` → `notes/private/portfolio.md` atomic cutover (파일 이동 + Portfolio.load 인자 변경 + fixture/테스트 갱신) |
| **P-02** | REQUIREMENTS MCP-03/MCP-05/MCP-08 wording | ✅ **갱신 완료 (2026-04-26)** | 없음 — REQUIREMENTS.md AMENDED 표시 |
| **P-03** | REQUIREMENTS NOTE-01/NOTE-02 wording | ✅ **갱신 완료 (2026-04-26)** | Phase 8 plan에서 `templates/notes/` 디렉토리 생성 + 템플릿 파일 작성 |
| **P-04** | Frontmatter 스키마 zone-safe 확장 | 📌 Phase 10 plan 첫 task | `ProvenanceBlock`에 `valuation_caveats`, `computed_by` 추가 / `IngestStateBlock`에 `valuation_restated_at`, `review_flags` 추가 / `ReviewFlag.flag` Literal에 `"restatement"` 추가 / Alembic 마이그레이션 동반 |

### P-01 결정 (resolved 2026-04-26)

- **SoT = `notes/private/portfolio.md`** (gitignored, Phase 1 D-03/D-05 원칙 복구). 사유: 개인 vault 본질, avg_cost 등 민감 데이터 git 미노출.
- 영향 받는 결정 (이미 갱신):
  - REQUIREMENTS MCP-05 wording (AMENDED) — `dashboards/portfolio.md` 오기 → `notes/private/portfolio.md`
  - Phase 4 CONTEXT D-01/D-03/D-04 (AMENDED) — `vault/notes/portfolio.md` → `notes/private/portfolio.md`, `Portfolio.load(vault_root)` → `Portfolio.load(repo_root)`
- **Migration 책임:** Phase 6 plan 첫 task (atomic). 현행 `vault/notes/portfolio.md`는 sample data만 들어있어 Phase 6 cutover 시 손실 위험 낮음.

### P-04 스키마 확장 상세 (Phase 10 plan에서 실행)

- `ProvenanceBlock`에 추가:
  - `valuation_caveats: list[str] = Field(default_factory=list)` — `["negative_eps", "financial_sector_per_invalid", "fy_carry_forward"]` 등
  - `computed_by: str | None = None` — `"dart_fss"` / `"naver_scrape"`
- `IngestStateBlock`에 추가:
  - `valuation_restated_at: datetime | None = None` — 분기 재무 정정 시 기록
  - `review_flags: list[ReviewFlag] = Field(default_factory=list)` — `_derived.review_flags`(Phase 5 D-11)와 zone 분리, 모델은 공유
- `ReviewFlag.flag` Literal: 기존 enum + `"restatement"` 추가 (Phase 5 D-11 enum 확장)
- Alembic 마이그레이션: zone 분리 enforce. 기존 문서에 신규 필드 default 적용은 backward-compat 유지.

</prerequisites>

<decisions>
## Implementation Decisions

### Sector + Peer Selection (D-01 ~ D-04)

- **D-01:** 섹터 분류 = **KRX 업종 소분류** 우선, 해당 소분류 내 시총 상위 10개 미만이면 **대분류로 fallback**. pykrx `stock.get_market_sector_classifications()` 활용. KOSPI/KOSDAQ 별도 코드 체계 정규화 헬퍼 작성.
- **D-02:** Top 10 선정 = **시가총액 단순 상위 10개**. 거래대금·유동성 가중 없음(v2 검토). 선정 기준일은 valuation 스냅샷 산출일과 동일.
- **D-03:** 추적 멀티플 = **5개 모두**: PER, PBR, EV/EBITDA, PSR, 배당수익률. 적자 기업/금융주 무효 케이스는 멀티플 값 `null` + `provenance.valuation_caveats`(리스트, 예: `["negative_eps", "financial_sector_per_invalid"]`)에 사유 기록. **caveats는 collector가 산출 시점에 결정하므로 `provenance` zone**(Phase 1 D-09 zone 분리 준수).
- **D-04:** **관심 종목이 sector top 10에 자동 포함되지 않으면 11번째 행으로 강제 추가** (rank=11, label="watchlist") — '내 종목이 어디 있나' 맥락 유지. 단 본 행도 위 5개 멀티플만 표기, 추가 surface 없음(Out-of-scope 스크리너 회피).

### Valuation Data Pipeline (D-05 ~ D-09)

- **D-05:** 데이터 소스 hybrid 전략:
  - **관심 종목(watchlist + holdings)** = `dart-fss` 자체계산. 분기 보고서에서 EPS/BPS/매출/EBITDA/총부채/현금성/배당 직접 추출 → pykrx 종가와 결합 → 5개 멀티플 산출. SoT·재현성 확보. `provenance.computed_by = "dart_fss"`.
  - **피어(관심 X)** = 네이버 증권 종목개요 페이지 스크래이핑(완료된 멀티플 그대로). `provenance.computed_by = "naver_scrape"`.
  - **네이버 스크래이핑 정책**(CLAUDE.md TechStack §1.3 gray-area 경고 반영):
    - Rate limit: **1 req / 2초** 캡, jitter ±0.5s
    - User-Agent: `stock-wiki-personal/1.0 (+contact)` 명시
    - robots.txt 자동 확인 (수집 직전 fetch + 24h 캐시), Disallow 경로 즉시 skip
    - 실패·429·차단 응답 시 fallback: 해당 ticker는 dart-fss 자체계산 시도(시간 비용 감수)
    - 1일 1회만 호출(daily-batch 슬롯), peer 50-200 ticker × 1req/2s = 약 2-7분
- **D-06:** 새 collector = `src/collectors/valuation/`. 진입점 `collect_valuation`. **OPS-01 `daily-batch` 명령에 `valuation` 소스 추가**(KRX 마감 후, news·macro와 같은 슬롯). Phase 4 collector 패턴 준수(content-hash 멱등 · tenacity 재시도 · heartbeat · `anthropic` 금지 — COLL-07 CI 가드 유효).
- **D-07:** **저장 layout 단일화 — ticker-major append-only**(Phase 4 macro D-07 패턴 동일):
  - 정상 daily 산출 = `vault/raw/valuation/{ticker}.md` (1 ticker = 1 파일, frontmatter `observations: [{date, per, pbr, ev_ebitda, psr, dividend_yield, computed_by, caveats}]` 시계열 append)
  - 동일 (date, ticker) 중복은 skip, 새 관측만 append → 파일 content_hash 갱신
  - **Sector top10 비교는 별도 *collection-time index 파일* `vault/raw/valuation/_sector/{sector_code}/{date}.md`** — 그날 sector top10 명단(rank·ticker만, 멀티플 값은 ticker 파일 참조). 멀티플 값은 ticker 파일에 단일 SoT.
  - Backfill·daily 모두 동일 `vault/raw/valuation/{ticker}.md`에 append → 구조 통일(이전 검증 round 7번 해소).
- **D-08:** Historical backfill = **일회성 스크립트** `stock backfill valuation --since 5y`. 관심 종목만 대상(피어 backfill X). pykrx로 일별 종가 + dart-fss로 분기별 EPS/BPS 시계열 → 매 영업일 trailing 12M 멀티플 산출 → `vault/raw/valuation/{ticker}.md`에 과거→현재 순으로 일괄 append. **dart-fss 5y 분기 EPS/BPS 추출 신뢰성은 RESEARCH 단계에서 sample(삼성전자)로 실증 검증** 필수 — 누락 분기 발생 시 fallback(이전 분기 carry-forward + `valuation_caveats: ["fy_carry_forward"]`).
- **D-09:** 분기 재무 정정(supersedes 체인 — Phase 2 D-08) 시: 해당 분기 이후 모든 daily 멀티플 행에 대해 trailing 12M 자동 롤오버 재계산. 정정 사실은 **`ingest_state.valuation_restated_at`(timestamp)** + **`ingest_state.review_flags: [{flag: "restatement", detail: "..."}]`**로 표시(Phase 5 D-11 ReviewFlag 모델 공유, enum에 `"restatement"` 추가 — P-04). 과거 스냅샷의 observation 값은 in-place 재작성, git diff로 추적. **`_derived` zone은 건드리지 않음**(Phase 5 D-07 zone integrity 준수).

### Historical Bands & DB View (D-10 ~ D-12)

- **D-10:** Lookback = **5년**. 모든 percentile/min/max/avg 통계는 5년 윈도우 기준.
- **D-11:** **DB `valuation_snapshots` 테이블 추가** (Alembic 0003 추정). 컬럼: `id BIGSERIAL`, `corp_code CHAR(8)`, `as_of DATE`, `metric TEXT`(per/pbr/ev_ebitda/psr/div_yield), `value NUMERIC`, `computed_by TEXT`, `source_doc_id TEXT REFERENCES documents(id)`, `created_at TIMESTAMPTZ`. 인덱스: `(corp_code, metric, as_of DESC)`.
  - SoT는 여전히 vault `raw/valuation/{ticker}.md`. ingest 워커가 ticker 파일을 읽어 valuation_snapshots에 fan-out.
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
  - **Scope 명시:** 본 페이즈는 *outlier 계산·노출(MCP 응답에 `is_outlier` 플래그)*까지. Outlier 발생 시 *알림/dashboards/alerts.md 자동 생성*은 V2-ALERT-02 영역으로 분리 유지.
- **D-16:** 252일 미만 데이터 종목(신규 상장/거래정지 후 재개)은 `is_outlier = null` + `insufficient_history = true` 메타. Claude는 이 경우 raw 수치만 제시.
- **D-17:** 신호 계산은 KRX raw 도착 시 incremental(전일 대비 새 영업일분만 추가) — `daily-batch` 안에서 KRX 수집 직후 chained. 전체 재계산은 `stock signal rebuild` 명령(STORE-05 호환).

### Private Notes Scaffold (D-18 ~ D-22)

- **D-18:** `notes/private/` 하위 hybrid 구조:
  ```
  notes/private/
  ├── {ticker}/                 # ticker 중심 누적
  │   ├── thesis.md             # 투자 논리 + kill criteria (single file, append on revision)
  │   ├── conviction.md         # 확신도 변화 로그
  │   └── notes.md              # 자유 메모
  ├── journal/
  │   └── YYYY-MM-DD.md         # 일자별 의사결정 로그(여러 종목 cross-cut)
  └── portfolio.md              # 보유·평단 (P-01 해소 시 여기로 단일화 권장)
  ```
  ticker 폴더는 종목별 누적 매모, journal은 일자별 cross-cut 기록 분리.
- **D-19:** **Phase 8과 분업** = Phase 8(NOTE-01/02/03)은 **템플릿 파일 + frontmatter 스키마 + Pydantic 검증만** 담당하고 git에 커밋. 실제 콘텐츠는 모두 `notes/private/`에 적재되며 `.gitignore` 영역(Phase 1 D-03 연속). **Phase 8 NOTE-01의 `notes/theses/` 디렉토리는 템플릿 디렉토리(`templates/notes/thesis.md` 등)로 위치 변경** — P-03 prerequisite 참조. REQUIREMENTS.md NOTE-01/02 wording 갱신 필요.
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
- **D-21:** **Claude 쓰기 권한** = MCP `add_note`(Phase 6 MCP-08) 경로 화이트리스트를 `vault/notes/` → `vault/notes/` ∪ `notes/private/` 으로 확장. 세션 중 "이 종목 메모해줘"·"오늘 의사결정 일기로 남겨줘" 자동 적재 가능. write 정책은 **append-only가 아닌 일반 write 허용**(사용자가 직접 수정도 자유롭게). **REQUIREMENTS.md MCP-08 wording 갱신 — P-02 prerequisite 참조**. raw/ingested 쓰기 금지는 유지.
- **D-22:** Private 메모는 ingest 파이프라인에 **포함**. embedding · BM25 인덱스 · DB chunks 모두 동일하게.
  - 검색(`search` MCP-02) 결과에서 private 메모도 등장. **모든 결과에 `provenance.source` 동봉**(예: `"private_note"` vs `"dart"`/`"news"`)되어 LLM이 가중 판단 가능 (JUDGE-06과 정합).
  - **`search(source_filter='raw')` / `source_filter='private_only'` 옵션 지원** — Phase 6 MCP-02 시그니처 확장(이미 `source` 파라미터 존재). 본 페이즈에서 `source` enum에 `"private_note"` 추가.
  - 다중 사용자 격리(`chunks.visibility` 컬럼)는 v2 — 본 페이즈는 개인 vault 가정.

### MCP Tool Surface Extension (D-23 ~ D-27)

- **D-23:** **신규 MCP 툴 3개 추가** (Phase 6 MCP-03~10과 동일한 FastMCP 패턴):
  - `get_valuation_context(ticker, as_of?)` — 5개 멀티플 현재 + sector top10 비교 테이블 + 5y 밴드(min/avg/current/max/percentile)
  - `get_supply_demand_signals(ticker, as_of?, since_days?=60)` — window 테이블(5d/20d/60d) × 투자자(외국인·기관·개인) net buy + streak + z-score + 공매도/대차 잔고
  - `get_private_thesis(ticker)` — `notes/private/{ticker}/*.md` 본문 결합 반환(thesis + conviction 최신 + notes 본문)
- **D-24:** **`get_ticker_overview`(MCP-03) 응답에 자동 포함**: `valuation` (get_valuation_context summary), `supply_demand` (활성 신호만 강조 + 핵심 수치 표), `private_thesis` (get_private_thesis 본문, 섹션 기본 하단). Phase 6 MCP-03 스펙은 본 페이즈가 확장 — REQUIREMENTS MCP-03 wording에 4축 응답 구조 추가 필요(P-02와 함께 요청).
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
    "vault_paths": ["vault/raw/valuation/{ticker}.md", "vault/raw/valuation/_sector/{sector_code}/{date}.md"]
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
- `.planning/REQUIREMENTS.md` — v1 71 요구사항(완료 현황 확인), Out of Scope, **MCP-03·MCP-08·NOTE-01·NOTE-02 갱신 대상**
- `.planning/ROADMAP.md` §"Phase 10" — 페이즈 타이틀 출처
- `.planning/phases/01-load-bearing-foundation/01-CONTEXT.md` D-03~D-05 — `notes/private/` 경로·`.gitignore` 정책, `templates/portfolio.md` 패턴 (P-01 portfolio 단일화 근거)
- `.planning/phases/01-load-bearing-foundation/01-CONTEXT.md` D-09~D-11 — frontmatter 3-zone 구조 (provenance/ingest_state/_derived) — **본 페이즈 D-03/D-09 zone 준수 필수**
- `.planning/phases/02-canonical-entity-identity/02-CONTEXT.md` D-05~D-08 — supersedes edge 처리 (Phase 10 D-09 재무 정정 정합 근거)
- `.planning/phases/02-canonical-entity-identity/02-CONTEXT.md` D-13~D-15 — content-hash dedup (Phase 10 D-06 멱등 패턴)
- `.planning/phases/03-one-company-walking-skeleton/03-CONTEXT.md` D-09~D-14 — 하이브리드 검색 파라미터 (D-22 chunks 인덱싱·source_filter 정합)
- `.planning/phases/04-multi-source-collector-coverage/04-CONTEXT.md` D-01~D-04 — Portfolio 로딩 패턴 (P-01 해소 시 수정 대상)
- `.planning/phases/04-multi-source-collector-coverage/04-CONTEXT.md` D-05 — KRX raw layout (Phase 10 supply-demand SoT)
- `.planning/phases/04-multi-source-collector-coverage/04-CONTEXT.md` D-07 — Macro append-only 시계열 패턴 (D-07 valuation ticker 파일 동일 패턴)
- `.planning/phases/05-claude-schedule-enrichment-with-korean-number-safety/05-CONTEXT.md` D-07 — Frontmatter zone safety (collector·ingest는 `_derived` 쓰기 금지) — **위반 시 Phase 5 ingest doctor가 검출**
- `.planning/phases/05-claude-schedule-enrichment-with-korean-number-safety/05-CONTEXT.md` D-11 — `ReviewFlag` Pydantic 모델 (P-04 enum 확장 베이스)

### Phase 6/8/9 Coordination (Forward Refs)
- `.planning/REQUIREMENTS.md` §"stock-mcp 서버" MCP-02·MCP-03·MCP-08 — 본 페이즈가 확장하는 툴 시그니처
- `.planning/REQUIREMENTS.md` §"메모·리서치" NOTE-01/02/03 — Phase 8과의 분업 경계, P-03 갱신 대상
- `.planning/REQUIREMENTS.md` §"Claude 판단 보조" JUDGE-01·JUDGE-06 — 4축 답변·private vs raw 가중치 정합 (D-22 source 동봉이 JUDGE-06 사전 조건)
- `.planning/REQUIREMENTS.md` §"운영" OPS-01 — `daily-batch` 슬롯 (D-06 통합 지점)
- `.planning/REQUIREMENTS.md` §"v2" V2-ALERT-02 — 본 페이즈 신호 outlier vs V2 알림 surface 경계 (D-15 명시)

### CLAUDE.md TechStack Constraints
- CLAUDE.md §1.3 — Naver Finance 스크래이핑 gray-area 경고 (D-05 정책 근거: 1req/2s, UA, robots.txt)
- CLAUDE.md §1.1 — dart-fss healthy 상태 (D-05/D-08 자체계산 근거, 단 5y backfill 신뢰성은 RESEARCH 검증)
- CLAUDE.md §2 — systemd.timer 스케줄러 (D-06 daily-batch 통합)

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

- **`src/shared/portfolio.py::Portfolio`** (Phase 4) — watchlist + holdings 로딩 헬퍼. **P-01 해소 시 `vault_root` 인자 → `repo_root` 변경 가능**. Phase 10 valuation/signals collector가 동일 호출로 ticker scope 결정.
- **`src/collectors/krx/`** (Phase 4) — pykrx 기반 OHLCV·투자자 수급·공매도 수집기. Supply-demand 신호 계산은 이 raw 파일을 입력으로 받으며 별도 수집 없음.
- **`src/collectors/dart/`** (Phase 3+4) — dart-fss 래퍼. EPS/BPS/매출/총부채/현금성 추출 메서드 활용 → 자체 멀티플 계산.
- **`src/shared/frontmatter.py`** (Phase 1) — `FrontMatter` Pydantic 모델. **P-04에 따라 zone-safe 확장**:
  - `ProvenanceBlock`: `valuation_caveats: list[str]`, `computed_by: str | None` 추가 (collector-time)
  - `IngestStateBlock`: `valuation_restated_at: datetime | None`, `review_flags: list[ReviewFlag]` 추가 (ingest worker가 기록)
  - `ReviewFlag.flag` Literal에 `"restatement"` 추가 (Phase 5 D-11 enum 확장)
- **`src/shared/content_hash.py`** (Phase 1·2) — 멱등 업서트 키. Ticker valuation 파일·private notes 모두 동일 해시 패턴 사용.
- **`src/db/migrations/`** Alembic — `valuation_snapshots`·`supply_demand_signals` 신규 테이블 + frontmatter zone 확장 마이그레이션.
- **`src/db/entity.py`** — ORM 베이스. 신규 테이블 두 개 추가.
- **`src/ingest/worker.py`** — ticker valuation 파일·KRX raw 파일 변경 감지 후 fan-out. `_derived` zone은 건드리지 않음(Phase 5 D-07).
- **`src/ingest/injection_defense.py`** (Phase 3 D-15) — Private notes도 untrusted body로 분류할지 결정 필요(개인 메모는 trusted, 그러나 자기 자신을 cross-XSS-style로 오염시킬 가능성은 낮음 → trusted 분류 권장).
- **`src/stock_mcp/tools/`** — `search.py` 패턴 그대로. `get_valuation_context.py`·`get_supply_demand_signals.py`·`get_private_thesis.py` 신규 모듈 + `search.py` source enum 확장(D-22).
- **`src/stock_mcp/models.py`** — Pydantic 응답 스키마(D-25/D-26 정의 모델 신규 추가).

### Established Patterns

- **Collector 패턴(Phase 4)** — `Portfolio.load()` 호출 → tenacity 재시도 → content-hash 멱등 업서트 → heartbeat append → fail-isolated. 본 페이즈 valuation collector 동일 적용.
- **Frontmatter 3-zone(Phase 1 D-09 + Phase 5 D-07)** — provenance/ingest_state/_derived 분리. **collector·ingest는 `_derived` 쓰기 금지**. valuation 산출물의 `caveats`·`computed_by` = `provenance` (수집 시 결정), `valuation_restated_at`·`review_flags` = `ingest_state` (재인제스트 메타). `_derived`는 Phase 5 Schedule agent만 채움.
- **Append-only 시계열 파일(Phase 4 D-07 macro)** — `observations: [{date, value, ...}]` 리스트에 append, 동일 (date, key) 중복 skip. valuation `vault/raw/valuation/{ticker}.md`도 동일 패턴.
- **MCP tool docstring(Phase 6 MCP-10)** — LLM-facing 행동 계약. 신규 3개 툴 모두 동일 컨벤션 + CI 레이턴시·토큰 검증.
- **하이브리드 검색(Phase 3 RET-01)** — private 메모도 동일 인덱스. `provenance.source` 동봉이 LLM 가중 판단의 사전 조건(JUDGE-06).
- **OPS-01 daily-batch(Phase 9)** — 매일 장 마감 후 systemd.timer/Task Scheduler에서 `stock daily-batch` 호출. 본 페이즈 valuation collector + signal incremental은 이 안에 chained.

### Integration Points

- **`stock daily-batch`** CLI(Phase 9 OPS-01) — 슬롯 추가: KRX 수집 후 → valuation collect → signal recompute (chain).
- **`stock collect valuation --since YYYY-MM-DD`** — 신규 명령(수동·디버그용).
- **`stock backfill valuation --since 5y`** — 신규 명령(historical 일회성 백필).
- **`stock signal rebuild`** — 신규 명령(supply_demand_signals 전체 재계산).
- **Phase 6 `get_ticker_overview`** — 본 페이즈가 응답 스키마에 `valuation`/`supply_demand`/`private_thesis` 섹션 주입(MCP-03 확장, REQUIREMENTS 갱신 — P-02).
- **Phase 6 `add_note`(MCP-08)** — 화이트리스트 경로 확장 (`notes/private/` 추가). REQUIREMENTS 갱신 — P-02.
- **Phase 6 `search`(MCP-02)** — `source` enum에 `"private_note"` 추가, `source_filter='raw'`/`'private_only'` 운용 패턴.
- **Phase 8 `dashboards/portfolio.md`·by-ticker hub** — Dataview 쿼리로 valuation·supply-demand 섹션을 자연스럽게 끌어다 표시(Phase 8 plan 갱신 필요, P-03과 함께).
- **Phase 9 JUDGE-06** — 본 페이즈가 `provenance.source` 동봉으로 사전 조건 충족, 가중치 prompt convention은 Phase 9에서 확정.

</code_context>

<specifics>
## Specific Ideas

- **"X 지금 비싼가?"가 single tool call로 답해져야 함** — get_valuation_context 한 번으로 sector 비교 + 자기 시계열 퍼센타일 둘 다 포함.
- **사용자 시나리오 1순위 = "X 매수해야 하나?" 통합 4축** — get_ticker_overview가 모두 합쳐서 답함. 신규 3툴은 drill-down용이지 1차 진입은 overview.
- **개인 vault 가정** — private 메모를 search 결과에서 격리하지 않음. 다중 사용자는 v2.
- **재무 정정 시점에서 historical 밴드가 바뀌는 게 옳다** — 시장 인지보다 진실 추적 우선(D-09).
- **티커별 적응 임계값** — 처음부터 252일 rolling σ 기반. 단순 고정 z=2.0 대신.
- **피어 데이터는 컨텍스트 전용** — 피어 ticker(50-200개) 자체는 매수 후보 surface에 노출하지 않음(Out-of-scope 스크리너 회피). Sector top10 테이블 안에서만 비교 reference로 등장.
- **dart-fss 5y 분기 EPS/BPS 추출 신뢰성** — RESEARCH 단계에서 sample(삼성전자 + 1 KOSDAQ + 1 금융주) backfill 실증 검증 필수. 누락·접근 실패 분기 발생 시 carry-forward 폴백 정책 확정.
- **Naver Finance 스크래이핑은 gray-area 인정 위에서 수행** — robots.txt + 1req/2s + UA 명시 + fallback dart-fss. 차단 시 daily-batch 부분 실패로 처리(Phase 4 collector 격리 원칙).
- **Frontmatter zone integrity는 hard rule** — collector/ingest가 `_derived`에 쓰면 Phase 5 ingest doctor가 `agent_zone_violation` 검출. Pydantic 모델이 Write 시점에 zone 분리 강제(P-04).

</specifics>

<deferred>
## Deferred Ideas

- **임계값 계수 튜닝(σ·percentile 상수)** — v1+10에서는 코드 상수로 두고, eval(V2-QUAL-01) 이후 데이터 기반 재조정.
- **Top 10 선정에 거래대금 가중** — 시총 단순 상위가 첫 구현. 왜곡(거래량 적은 대형주) 시 가중 도입.
- **다중 사용자 private 격리** — `chunks.visibility` 컬럼·MCP 사용자 컨텍스트. 2~5명이 같은 git repo면 자연 분리, 외부 공유 시점에 추가.
- **FICS/WICS 도입** — KRX 분류로 시작, 의미 부족 사례 누적되면 v2에서 검토.
- **공매도 잔고 통계 API 직접 사용(KRX 정보데이터시스템)** — 현재 pykrx 경유. 정확도 차이 발생 시 직접 호출.
- **Adaptive threshold 계산기 추출(reusable helper)** — 첫 구현은 supply_demand_signals에 인라인. 다른 신호(가격 변동성 등)에도 재사용되면 분리.
- **PDF 리포트 valuation 입력** — V2-DOC-01 OCR 이후, 증권사 컨센서스 멀티플을 peer 데이터로 주입.
- **MCP 사용자 의견 가중치 정책** — Phase 9 JUDGE-06에서 정의. 본 페이즈는 private 노출 + `provenance.source` 동봉만 책임지고 가중치 결정은 Phase 9에 위임.
- **V2-ALERT-02 알림 surface** — 본 페이즈는 outlier 계산까지. dashboards/alerts.md 자동 생성·푸시는 v2.
- **Sector top10 daily index 파일(`_sector/{sector}/{date}.md`) 폐기 가능성** — Phase 8 dataview 쿼리가 ticker 파일만으로 충분하다면 index 파일 자체를 dropping 검토.

### Reviewed Todos (not folded)
없음.

</deferred>

---

*Phase: 10-decision-context-coverage-peer-historical-valuation-supply-d*
*Context gathered: 2026-04-26 / Verification patch: 2026-04-26*
