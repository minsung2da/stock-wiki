# Phase 4: Multi-Source Collector Coverage - Context

**Gathered:** 2026-04-18
**Status:** Ready for planning

<domain>
## Phase Boundary

DART 외 네 개 수집기(`collect_krx`, `collect_news`, `collect_macro`, `collect_kind`)를 Phase 3에서 확립한 형태(`src/collectors/{source}/` 모듈 · 최소 frontmatter · content_hash 멱등 · tenacity 재시도 · heartbeat 소스별 기록 · anthropic/openai 금지)대로 구현한다. 각 수집기는 서로 독립적으로 실패 가능해야 하고, 하나가 실패해도 나머지는 완주한다. 이 페이즈는 **수집(raw/)까지만** 다룬다 — `_derived` 추출·임베딩·BM25 재인덱싱은 Phase 5 이후.

</domain>

<decisions>
## Implementation Decisions

### Ticker Scope (D-01 ~ D-04)
- **D-01 (AMENDED 2026-04-26 by Phase 10 P-01):** Watchlist·Portfolio 원본은 **`notes/private/portfolio.md`** 프론트매터(Dataview-ready, gitignored). Phase 1 D-03/D-05 원칙 복구. Phase 8 대시보드(DASH-01)가 동일 파일을 Dataview source로 참조. ~~원안: `vault/notes/portfolio.md`~~ 폐기.
- **D-02:** 프론트매터 스키마(Phase 8 선행 확정):
  ```yaml
  ---
  holdings:
    - ticker: "005930"
      qty: 10
      avg_cost: 72500
  watchlist:
    - "000660"
    - "035420"
  ---
  ```
  Pydantic 모델 `src/shared/portfolio.py::Portfolio` (새로 생성)로 로드·검증. 필드 누락·형식 오류는 수집 실패(fail-fast).
- **D-03 (AMENDED 2026-04-26 by Phase 10 P-01):** `notes/private/portfolio.md`는 **gitignored 로컬-only**. `.gitignore`의 `notes/private/` 규칙으로 자연 제외(Phase 1 D-03 일관). `templates/portfolio.md`(Phase 1 D-04)는 git clone 후 사용자가 `notes/private/`에 복사. **Migration:** Phase 6 plan 첫 task에서 atomic cutover — `vault/notes/portfolio.md` 콘텐츠를 `notes/private/portfolio.md`로 이동 + Portfolio.load 인자 변경 + 테스트 fixture 업데이트. ~~원안: vault/notes/portfolio.md 전체 git commit~~ 폐기.
- **D-04 (AMENDED 2026-04-26 by Phase 10 P-01):** 모든 수집기는 **`Portfolio.load(repo_root)`** 한 번 호출해 `watchlist + holdings.ticker` 합집합을 스코프로 사용 (헬퍼는 `notes/private/portfolio.md`에서 읽음). holdings는 Phase 4 수집에서 watchlist와 동일하게 취급(qty/avg_cost 미사용 — Phase 10 D-22에서 private_thesis가 활용).

### Vault Layout per Source (D-05 ~ D-08)
- **D-05:** KRX = `raw/krx/YYYY-MM-DD/{ticker}.md` (로드맵 명시). 한 파일 frontmatter에 OHLCV + 투자자 수급(외국인·기관·개인) + 공매도 잔고 **병합**. 세 섹션 분리 파일 생성하지 않음.
- **D-06:** News = `raw/news/YYYY-MM/{outlet}_{url_hash8}.md` (기사 단위 1파일). `url_hash8` = sha256(url)[:8]. 같은 기사를 다른 경로로 두 번 받더라도 `content_hash` 멱등.
- **D-07:** Macro = `raw/macro/{source}/{series_id}.md` (시리즈 단위 1파일). frontmatter에 `observations: [{date, value}, ...]` 테이블 append. 재실행 시 동일 (date,value) 중복은 skip, 새 관측만 append → 파일 content_hash 갱신.
- **D-08:** KIND = `raw/kind/YYYY-MM/{event_type}_{ticker}_{event_date}.md` (이벤트 단위 1파일). `event_type ∈ {suspension, watchlist_designation, investment_caution, unfaithful_disclosure}` 고정 enum. `event_date`는 이벤트 발효일 YYYYMMDD.

### News Collection Policy (D-09 ~ D-13)
- **D-09:** RSS 2개 소스 = **한경(hankyung.com) + 이데일리(edaily.co.kr)** 확정. 서울경제는 deferred(필요 시 추가). 카테고리: 각 매체의 "경제·금융" 통합 피드 전체.
- **D-10:** 기사 수집 파이프라인:
  1. RSS 파싱 → URL·title·published 추출
  2. URL content_hash로 이미 있으면 skip (멱등)
  3. trafilatura로 본문 추출
  4. 본문을 entities 테이블 alias로 매칭(D-11) → 매칭 티커 없으면 **drop** (저장하지 않음)
  5. frontmatter에 `tickers: [matched]` 기재, body에는 **본문 첫 2문단만** 기계 추출(저작권, D-13)
- **D-11:** 회사명·별칭 매칭은 **entities + aliases 테이블(Phase 2) DB 조회**. 수집기는 engine을 인자로 받아 `resolve_entity_by_alias(name, as_of=published)` 호출. aliases 테이블에 없는 표기는 매칭 실패로 처리.
- **D-12:** 티커별 스코프 필터: `portfolio.watchlist + portfolio.holdings[].ticker`에 해당하는 entity.corp_code 집합만 유지. 매칭된 티커 중 하나라도 스코프 안에 있으면 저장.
- **D-13:** 저작권 정책 = **전문 저장 금지**. body에는 trafilatura가 추출한 본문의 **첫 2문단**(문단 경계 = blank line)만 기록. frontmatter 필수 필드: `title`, `outlet`, `published`, `url`, `tickers`, `content_hash`. `license_flag: summary_only` 고정. Phase 5의 `_derived.summary`는 이 2문단 + title을 입력으로 생성(Claude Schedule 영역, 이 페이즈 밖).

### KIND Event Acquisition (D-14 ~ D-17)
- **D-14 (AMENDED 2026-04-20 → Option D):** **DART 거래소공시(`pblntf_ty="I"`) 중심 + KIND 스크레이핑 보조.** 원안의 pykrx 경로는 폐기 — pykrx 1.0.51 및 GitHub master에 `get_market_status_by_ticker` 같은 관리종목/투자경고 판별 함수가 존재하지 않음이 live 검증으로 확인됨(2026-04-20). 대신 DART 거래소공시에 이미 이 이벤트들이 전부 흘러들어감이 확인됐다 (30일 샘플: 거래정지 190건, 관리종목 16건, 불성실공시 23건).
  - **DART 거래소공시(`pblntf_ty="I"`) — 3종 이벤트 분류 (주요 소스):**
    - `suspension` ← `report_nm` 패턴 `주권매매거래정지` (기재정정 제외)
    - `watchlist_designation` ← `report_nm` 패턴 `관리종목지정우려`
    - `unfaithful_disclosure` ← `report_nm` 패턴 `불성실공시법인지정`
    - 정규식 상수는 `src/collectors/kind/sources.py::DART_EXCHANGE_EVENT_PATTERNS`에 배치
  - **KIND 스크레이핑 — `investment_caution`/`investment_risk` 전용:** `/investwarn/investattentwarnrisky.do` 페이지만 파싱. DART는 이 이벤트 타입을 별도 공시로 분리하지 않으므로 유일한 구조화 소스가 KIND임.
  - **KRX OHLCV 교차확증(보조, INFO-only):** Plan 02 `collect_krx`가 이미 `heartbeat.extra.suspended_tickers`(거래량=0)를 기록함. Plan 05는 이를 DART-derived `suspension` 이벤트와 대조해 불일치 시 `heartbeat.extra.suspension_cross_check_mismatch`에 기록. 권위 소스는 DART.
  - **개념 축 근거:** 거래소가 내리는 상태 지정(거래정지·관리종목·투자경고·불성실공시)은 "기업 평가(fundamental) 축"에 속함 → DART+KIND로 수집. pykrx는 "시장가격(market behavior) 축"(OHLCV·수급·공매도) 전용으로 분리.
  - 세부 이력: `04-05-SUMMARY.md` §"Strategy Amendment (Option D)" 및 `04-HUMAN-UAT.md` Gap-04-02 참조.
- **D-15:** KIND 스크레이핑 규약:
  - `https://kind.krx.co.kr/robots.txt` 확인 후 disallowed 경로 접근 금지(수집기 기동 시 assert)
  - Rate limit **1 req/sec 상한** (tenacity `wait_exponential` + 추가 상한)
  - User-Agent = `stock-wiki-collector/{version} (+github.com/.../stock)` 식별 가능 형태
  - 수집 성공 시 `content_hash` 캐시 활용 → 같은 이벤트는 재요청하지 않음(DB에 이미 저장된 이벤트 id 스킵)
- **D-16:** KIND 테스트 전략: 운영 스크레이핑은 실제 네트워크, CI는 `tests/fixtures/kind/*.html` 고정 스냅샷으로 파서 단위 테스트. 두 경로가 동일 파서를 공유.
- **D-17:** KIND 페이지 레이아웃 변경에 대한 방어: 파서는 selector 상수를 `src/collectors/kind/selectors.py`에 모아 두고, 선택자 불일치 시 `ParseError` + heartbeat에 `kind_parse_error: true` 기록(silent pass 금지).

### Orchestration CLI (D-18 ~ D-21)
- **D-18:** CLI 구조:
  - `stock collect <source>` — 개별 수집기 실행 (dart, krx, news, macro, kind)
  - `stock collect all [--sources=a,b,...]` — 통합 실행. 인자 없으면 {krx, news, macro, kind} 기본(dart는 기본 제외 — Phase 3에서 `stock collect dart` 유지)
  - Phase 3 `stock collect dart` 시그니처 변경 없음(하위호환)
- **D-19:** `stock collect all` 격리 = **in-process try/except 격리** (subprocess 불필요). 각 수집기는 자기 예외를 삼켜 heartbeat에 실패 기록하고 리턴. 최상위 CLI는 리턴 dict를 aggregate.
- **D-20:** 종료 코드·리포트:
  - 전부 성공 → `exit 0`, stderr에 JSON 리포트 1줄
  - 1개라도 실패 → `exit 1`, stderr에 JSON 리포트 + 실패 소스별 에러 상세
  - JSON 스키마: `{run_at, sources: {krx: {status, docs_processed, elapsed_ms, error?}, ...}}`
  - heartbeat는 소스별 키 독립 갱신(기존 Phase 3 패턴 유지)
- **D-21:** `stock collect all --sources=krx,news` 부분 집합 지원. 존재하지 않는 source 이름은 fail-fast(argparse choices 검증).

### Macro Collection Cadence (D-22 ~ D-23)
- **D-22:** `collect_macro`는 **매일 전체 시리즈 조회**. ECOS 월간(예: 기준금리)·분기·일간 시리즈 구분 없이 전부 요청. API 응답이 이전과 동일하면 content_hash 변화 없어 파일 미변경(Phase 3 dedup 패턴). LLM 토큰 없이 HTTP 호출만이므로 비용 우려 없음.
- **D-23:** 시리즈 카탈로그 = `.planning/macro_series.yaml` (신규):
  ```yaml
  ecos:
    - series_id: "722Y001"  # 기준금리 예시
      label: "base_rate_kr"
    - series_id: "731Y001"  # USD/KRW 예시
      label: "usd_krw"
  fred:
    - series_id: "DGS10"
      label: "us_10y"
    - series_id: "DCOILWTICO"
      label: "wti"
  ```
  실제 series_id는 리서처가 ECOS/FRED 공식 식별자로 확정. collector는 이 파일을 읽어 루프.

### Trust Levels (Phase 3 D-19 재확인)
- **D-24:** 본 페이즈 신규 소스의 `provenance.trust_level`:
  - KRX, ECOS, FRED, KIND = `trusted` (공식 거래소·중앙은행·통계 기관)
  - 한경, 이데일리 = `semi_trusted` (언론 — Phase 5에서 delimiter wrap 적용)

### Claude's Discretion
- pykrx `get_market_status_by_ticker`의 정확한 함수 시그니처·반환 컬럼(리서처가 pykrx 공식 문서 확인 후 확정)
- DART 주요사항 "거래정지" 필터링 기준 문자열(dart-fss의 report_tp·pbblntf_ty 등) — 리서처가 실제 응답 샘플 확인 후 결정
- trafilatura의 "문단" 경계 정의(blank line vs `<p>` 태그 vs 문장 개수) — 기본은 trafilatura 기본 출력 기준 첫 2 블록
- URL content_hash의 정규화(쿼리 파라미터 제거 범위 — `?utm_*` 드롭 여부)
- `.planning/macro_series.yaml` 초기 시리즈 목록(4개 핵심 시리즈는 로드맵 명시: 기준금리, USD/KRW, US 10Y, WTI. 그 외 추가는 디스크레션)
- news 파일명의 `url_hash8` 충돌 시 처리(64-bit 공간에서 1/2^32 확률 — 실제 발생 시 `_hash12`로 확장)
- `collect_all` 내부 실행 순서(병렬 vs 순차) — Phase 4 스케일에서는 순차 충분

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 3 Artifacts (Pattern Templates — 신규 수집기는 이 구조를 따른다)
- `src/collectors/dart/__init__.py` — 수집기 공개 함수 시그니처 · heartbeat 호출 패턴 · vault_root/engine 인자
- `src/collectors/dart/client.py` — dart-fss API 클라이언트 래퍼 패턴(환경변수 로드·세션)
- `src/collectors/dart/fetcher.py` — tenacity 재시도 + 예외 분류 패턴
- `src/collectors/dart/writer.py` — ProvenanceBlock·FrontMatter 조립 + atomic write + path traversal 방어
- `src/ingest/heartbeat.py::record_source_run` — 소스별 heartbeat 갱신 API

### Shared Utilities (재사용)
- `src/shared/content_hash.py::compute_content_hash, normalize_body` — 모든 writer가 사용
- `src/shared/frontmatter.py::FrontMatter, ProvenanceBlock, write_frontmatter` — 3-zone 스키마 · atomic write
- `src/db/entity.py::resolve_entity` (Phase 2) — ticker→corp_code 변환. 추가로 리서처가 `resolve_entity_by_alias(name, as_of)` API 유무 확인 · 없으면 신설(D-11).
- `src/db/engine.py::get_engine` — 수집기들이 news/kind 매칭에 공유

### Requirements
- `.planning/REQUIREMENTS.md` §Collection COLL-02/03/04/05 (미완료 요건), COLL-06/07/08/09 (재확인)

### Roadmap
- `.planning/ROADMAP.md` Phase 4 상세 — `raw/krx/YYYY-MM-DD/*.md` · `raw/news/...` · `raw/kind/...` 파일 경로 명시, orchestration 성공기준 #5

### Prior Decisions (Phase 3 CONTEXT 계승)
- `.planning/phases/03-one-company-walking-skeleton/03-CONTEXT.md` — D-15 trust_level, D-19 trust 분류, Phase 3 collector 파일 분할 패턴, ingest 영역과의 경계

### Tech Stack (CLAUDE.md)
- CLAUDE.md §1.2 KRX (pykrx + FinanceDataReader 병용)
- CLAUDE.md §1.3 네이버·언론 스크레이핑(requests + read_html + BeautifulSoup, selenium 금지)
- CLAUDE.md §1.4 trafilatura 본문 추출
- CLAUDE.md §1.5 PublicDataReader (ECOS)
- CLAUDE.md §1.6 fredapi + yfinance
- CLAUDE.md §2 systemd.timer (Phase 9 예정이나 CLI 형태에 영향 — `--yes` · exit code 규약)

### Test Fixtures
- `tests/conftest.py::pg_engine, pg_clean` — 통합 테스트 fixture
- 신규: `tests/fixtures/kind/*.html` (KIND 파서 CI용 스냅샷, D-16)
- 신규: `tests/fixtures/rss/{hankyung,edaily}.xml`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/collectors/dart/__init__.py::collect_dart` — 새 수집기들은 동일한 함수 시그니처 모양을 따른다: `collect_<source>(*, vault_root, engine, ...) -> dict[str, Any]`
- `src/collectors/dart/fetcher.py` — tenacity retry 데코레이터·retryable exception 분류 그대로 복사·변형
- `src/collectors/dart/writer.py::vault_path_for, compute_body_hash` — path 조립·hash 헬퍼 패턴
- `src/shared/frontmatter.py::write_frontmatter` — atomic write
- `src/ingest/heartbeat.py` — 소스별 heartbeat 갱신

### Established Patterns (Phase 3에서 확립)
- Collector 파일 분할: `client.py`(API 래퍼) + `fetcher.py`(데이터 획득·재시도) + `writer.py`(vault 저장) + `__init__.py`(공개 collect_* 함수)
- 소스별 격리: `stock collect all`은 각 수집기를 try/except로 감싸고 heartbeat에 실패 기록
- 멱등성: `content_hash`가 frontmatter·파일에 쓰이고, 같은 hash 발견 시 writer는 no-op
- anthropic/openai 금지: `tests/test_import_guard.py` CI(COLL-07) 유지
- SQLAlchemy text() + bind parameters only (f-string SQL 금지, Phase 2 WR-03)

### Integration Points (신규 생성)
- `src/collectors/krx/{client,fetcher,writer,__init__}.py` (신규) — pykrx 래퍼
- `src/collectors/news/{client,fetcher,writer,__init__}.py` (신규) — RSS + trafilatura
- `src/collectors/macro/{client,fetcher,writer,__init__}.py` (신규) — PublicDataReader + fredapi
- `src/collectors/kind/{client,fetcher,writer,selectors,__init__}.py` (신규, D-17)
- `src/shared/portfolio.py` (신규) — `Portfolio.load(vault_root)` Pydantic 모델
- `src/cli/collect.py` (기존 확장) — `stock collect <source>` · `stock collect all`
- `src/db/entity.py` — `resolve_entity_by_alias(name, as_of)` 없으면 신설(D-11)
- `.planning/macro_series.yaml` (신규) — ECOS/FRED 시리즈 카탈로그
- `vault/notes/portfolio.md` (신규) — 예시 watchlist·holdings

</code_context>

<specifics>
## Specific Ideas

- **KRX 수집 기준일**: 거래일 단위. 휴장일은 pykrx가 빈 DataFrame 반환 → 수집기는 빈 결과도 heartbeat에 `skipped_holiday: true`로 기록하되 파일은 쓰지 않는다.
- **News 본문 2문단 추출 예시**:
  ```
  trafilatura.extract(html) → "첫 문단…\n\n둘째 문단…\n\n셋째 문단…"
  body = "첫 문단…\n\n둘째 문단…"  # 저장
  ```
- **ECOS 기준금리 시리즈 id**는 리서처가 공식 코드북에서 확정(현재 문서의 `722Y001`은 placeholder).
- **KIND 스크레이핑 초기 대상 URL**: 불성실공시법인지정 현황 게시판 — 리서처가 실제 경로 확인.
- **portfolio.md 초기 예시**(스켈레톤으로 커밋):
  ```yaml
  ---
  holdings:
    - ticker: "005930"
      qty: 1
      avg_cost: 70000
  watchlist:
    - "000660"
  ---
  # Portfolio

  Phase 4: collector scope source.
  ```
- **CLI JSON 리포트 stderr 출력 예시**:
  ```json
  {"run_at":"2026-04-18T09:00:00+09:00","sources":{"krx":{"status":"ok","docs_processed":50,"elapsed_ms":12340},"news":{"status":"error","error":"RSS timeout"},"macro":{"status":"ok","docs_processed":4,"elapsed_ms":2100},"kind":{"status":"ok","docs_processed":2,"elapsed_ms":8500}}}
  ```

</specifics>

<deferred>
## Deferred Ideas

- **서울경제 RSS 추가** — Phase 4는 한경·이데일리 2개로 COLL-03 달성. 서울경제는 Phase 5 이후 필요 시.
- **Portfolio holdings 민감정보 분리** (`.gitignore` + `portfolio.local.md`) — 팀 규모가 2명 이상으로 확장될 때 Phase 8에서 재설계. Phase 4는 전체 commit.
- **News body 길이 확장** — 현재 첫 2문단. Phase 5 `_derived.summary` 품질 관찰 후 3-4문단으로 조정 검토.
- **pykrx 대안 (FinanceDataReader)** — KRX 데이터 교차검증. 두 라이브러리 disagree 탐지는 별도 페이즈(V2-COLL-01 backlog).
- **KIND 불성실공시 이외 이벤트 타입** (예: 단기과열종목, 투자주의환기종목) — 현재 scope 밖.
- **Macro series 확장** (국고채 3년, 유로/원, 금, 항셍 등) — `.planning/macro_series.yaml` append로 점진 확장.
- **수집기 병렬화** (asyncio / concurrent.futures) — Phase 4 스케일은 순차 충분. >수백 종목 watchlist 시 Phase 9에서 최적화.
- **URL canonicalization 고도화** (utm_* 파라미터 제거) — 기본은 URL as-is, 실 데이터 관찰 후 고도화.

### Reviewed Todos (not folded)
(없음 — Phase 4 매치된 todo 0건)

</deferred>

---

*Phase: 04-multi-source-collector-coverage*
*Context gathered: 2026-04-18*
