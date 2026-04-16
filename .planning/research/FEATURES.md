# Feature Research

**Domain:** Claude-powered Korean stock market knowledge base (Obsidian + pgvector + MCP, for 2–5 person internal team)
**Researched:** 2026-04-17
**Confidence:** MEDIUM-HIGH (Korean-market specifics HIGH via official sources; LLM-wiki patterns MEDIUM; competitor feature parity MEDIUM from web search)

---

## Scope-Setting Principles (read first)

The Core Value from PROJECT.md narrows the feature space sharply:

1. **The reader is Claude, not a human dashboard user.** Anything that exists only for eyeballs (pretty charts, heatmaps, sparkline widgets) is automatically demoted relative to tools that sharpen LLM retrieval.
2. **Batch, not realtime.** The product is explicitly a knowledge base, not a trading terminal. Latency budget is minutes-to-hours, not milliseconds.
3. **Small closed team.** No login, no multi-tenancy, no per-user permissions, no billing — all features that dominate the competitor feature matrix drop away.
4. **LLM cost is a hard constraint.** Features that fan out into many Claude calls per day (e.g., per-filing LLM summary over all KOSPI/KOSDAQ) must be bounded to the watchlist.

With that frame, the feature landscape is deliberately narrower than commercial comparables (Koyfin, Stock Rover, FinChat/Fiscal.ai, OpenBB). We inherit the *decision-support shape* from them and discard the *broad-market dashboard shape*.

---

## Feature Landscape

### Table Stakes (v1 must-have)

Missing any of these makes the Core Value ("Claude가 근거 있는 매수/매도 판단을 즉시 제시") fall apart.

#### A. Data Ingestion & Coverage

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **DART 공시 수집 (정기 A · 주요사항 B · 발행 C · 지분 D 전 유형)** | Korean-market table stakes. Any event-driven judgment without DART is blind. `OpenDartReader`/`dart-fss` exist. | MEDIUM | API 인증키 필요. 문서 유형별로 frontmatter 스키마 분기 필요 (e.g. 유상증자 vs 전환사채 vs 대주주변동) |
| **KOSPI/KOSDAQ 일일 가격·거래량** | 기준 시세가 없으면 "최근 급락/급등" 같은 기본 질의가 불가능 | LOW | `pykrx`·`FinanceDataReader` 라이브러리로 해결. OHLCV + 시총 + 상장주식수 |
| **투자자별 매매동향 (외국인·기관·개인 순매수)** | 한국 시장 판단에 사실상 필수. 외인/기관 수급은 국내 리테일 담론의 공용어 | LOW | `pykrx.get_market_trading_value_by_investor`. 일별·종목별 모두 확보 |
| **종목 기본정보 (재무제표·업종·시총·상장일)** | 어떤 판단 질의든 최소한 "이 회사가 뭐 하는 곳인가" 필요 | LOW-MEDIUM | DART 재무제표 API + pykrx 시장정보. 분기별 갱신 충분 |
| **경제·금융 뉴스 (watchlist 종목 한정)** | 공시만으로는 맥락 부족. 뉴스 없이는 "왜 급등했는지" 설명 불가 | MEDIUM | RSS 우선, 실패 시 스크래핑. 크롤링 대상은 robots.txt·저작권 준수. 전문 대신 요약+링크 권장 |
| **매크로 지표 (기준금리·환율·원자재·한미 국채금리)** | 개별 종목 판단에 거시 맥락 필수. 특히 환율·금리 민감 종목 | LOW | ECOS(한국은행) + FRED + yfinance. 일단위로 충분 |
| **순수 스크립트 수집 (LLM 토큰 0)** | Constraint에 명시. 이게 깨지면 프로젝트 경제성 자체가 붕괴 | LOW | 원칙은 단순하지만 파이프라인 전체에서 지켜야 함 |

#### B. Note / Knowledge Organization

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Per-ticker hub note (종목 루트 문서)** | LLM이 한 종목에 대한 모든 링크를 한 곳에서 스캔해야 함. llm-wiki 패턴의 핵심 | LOW | `tickers/005930.md` 형태. frontmatter에 ticker/name/sector/isin, 본문은 요약 + 관련 노트 링크 |
| **공시·뉴스 개별 문서화 (frontmatter 표준화)** | 각 이벤트가 개별 ref-able 노트여야 graph·retrieval이 작동 | MEDIUM | 파일명 컨벤션 (e.g. `events/2026-04-17_005930_유상증자.md`), frontmatter 스키마 고정 |
| **Watchlist / Portfolio 대시보드 노트** | PROJECT.md active req. 사용자의 진입점. "내가 관심 있는 것"의 정의 | LOW | Markdown + Dataview. 수동 편집 가능해야 하며 자동 갱신과 공존 |
| **사용자 research memo (사람이 쓴 판단 노트)** | Karpathy llm-wiki의 핵심: 사람이 쓴 의견도 LLM이 읽는 1등급 소스 | LOW | `research/{ticker}/` 폴더 자유 기술. frontmatter에 `author: human`, 자동 수집물과 명시적으로 분리 |
| **Sector / Theme 노트** | 종목은 업종·테마 문맥 없이는 판단이 약해짐 | LOW-MEDIUM | 수동 seed + 자동 링크. 반도체/2차전지/조선 등 한국 특화 분류 체계 |
| **이벤트 타임라인 per ticker** | "최근 6개월 뭐 있었나"는 매도/매수 판단 직전 가장 자주 쓰는 뷰 | LOW | Dataview inline query로 ticker hub에 자동 렌더 |

#### C. Retrieval Surfaces

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **구조화 필터 (ticker, 날짜범위, 이벤트유형, 소스)** | LLM이 "삼성전자의 최근 3개월 유상증자 관련 문서" 같은 정밀 질의를 할 수 있어야 함. 의미검색만으로는 재현율 불안정 | MEDIUM | Postgres 정규 컬럼 (frontmatter → SQL). MCP tool로 노출 |
| **하이브리드 검색 (BM25 + dense embedding)** | 티커·제품명·법령 용어 같은 고유명사는 lexical, 개념·유사 사건은 semantic. 둘 중 하나만은 전 도메인 근거가 있는 명확한 패턴 | MEDIUM-HIGH | pgvector + pg_textsearch(BM25). RRF 융합. 임베딩은 bge-m3 등 한국어 지원 |
| **전문(full-text) 검색** | 정확한 인용구 찾기, 공시 본문 내 숫자 검색 | LOW | Postgres tsvector 또는 ripgrep over vault. 둘 다 가능 |
| **그래프 traversal (이웃 노드 조회)** | "이 공시와 연결된 뉴스·메모는?" — graphify 산출물의 존재 이유 | MEDIUM | graphify JSON 읽기 API 또는 Postgres edge table 쿼리 |

#### D. Claude Code Integration (stock-mcp tools)

Table stakes MCP tools — these are the 6 primitives a reasonable `get_ticker_info` / `semantic_search` / `recent_events` style API requires. Inspired by Financial Datasets MCP, Alpha Vantage MCP, EODHD MCP — but domain-scoped to the Korean market and the vault, not raw external APIs.

| Tool | Purpose | Complexity | Notes |
|------|---------|------------|-------|
| **`get_ticker_overview(ticker)`** | 티커 허브 노트 + 최신 시세·재무·수급 한 방 조회 | LOW | 여러 테이블 join. MCP tool 호출 1회로 사람이 10분 걸릴 조사 압축 |
| **`search(query, filters)`** | 하이브리드 검색 (semantic + keyword + 구조화 필터) | MEDIUM | 가장 자주 호출될 tool. ticker·date·event_type 필터 필수 |
| **`get_recent_events(ticker, days=30, event_types=[])`** | 최근 N일 공시·뉴스·시세 이벤트 타임라인 | LOW | 판단 세션의 기본 진입점 |
| **`get_portfolio_state()`** | 보유/관심 종목 + 각 요약 상태 (최근 이벤트 유무, 가격 변동, 미검토 알림) | LOW | PROJECT.md에 명시. 포트폴리오 대시보드 노트 읽기 |
| **`get_related(note_id, depth=1)`** | graphify/DB 엣지로 이웃 노드 탐색 | MEDIUM | "이 공시와 연결된 것들" |
| **`get_filing(dart_id)`** | 특정 DART 공시 원문 + 구조화된 추출 필드 | LOW | 원문은 본문 파일 참조. 파싱된 수치는 frontmatter |

#### E. Ingestion / Automation

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **일 1회 스케줄 배치 (수집→인제스트→DB 갱신)** | 주식시장 주기에 맞는 유일한 합리적 기본값. cron 수준으로 충분 | LOW | cron + makefile 또는 prefect lite. 장 마감 후 + 심야 배치 |
| **수동 트리거 (특정 ticker만 즉시 업데이트)** | 장중에 "지금 이 종목만 빨리"가 되는 순간이 반드시 생김 | LOW | CLI 엔트리포인트 하나 추가 |
| **중복 감지 (같은 공시·뉴스 두 번 적재 금지)** | 안 하면 DB가 금방 쓰레기장 됨. 소스별 고유 ID (DART rcept_no, URL hash) | LOW | 파일명·frontmatter id 기반 upsert |
| **증분 업데이트 (변경분만)** | 매일 전체 재수집은 비용·시간 낭비 | LOW | 각 소스별 last_run 타임스탬프 저장 |
| **실패 복구 / 재시도** | 외부 API·크롤링은 필연적으로 실패. 재시도 없으면 운영 못 함 | LOW-MEDIUM | tenacity retry + 실패 로그 노트 |

#### F. Judgment-Support UX (the actual product)

This is *what Claude's answer looks like*. Not features of the vault — conventions for the MCP/prompt layer. But they belong in features because the vault must be structured so these conventions are cheap.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **항상 인용 (answer must cite vault note paths)** | llm-wiki 전체 가치 제안의 핵심. 인용 없으면 그냥 generic LLM 답변 | LOW | MCP tool이 결과에 note path 포함. Claude 프롬프트에 "모든 주장은 노트 경로로 인용" 명시 |
| **근거 묶음: 최신 공시 + 가격 액션 + 본인 메모 + 거시 맥락** | "buy/sell 판단에 필요한 근거"의 최소 구성. 4축 중 하나라도 빠지면 근거 빈약 | LOW | tool 응답 템플릿에 네 섹션 고정 |
| **pros / cons 리스트 출력 포맷** | 인간의 최종 판단에 가장 직관적. scorecard는 과도 |  LOW | 프롬프트 컨벤션 수준. 강제 아님 |
| **이벤트 타임라인 형식** | "최근에 뭐 있었나"는 시간순이 가장 읽힘 | LOW | 프롬프트 컨벤션 + `get_recent_events` 응답 구조 |

---

### Differentiators (v1.x or v2, adds real uniqueness)

These are where this project diverges from any existing commercial tool. They stem from the vault+graph+LLM architecture, not from more data.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **graphify 인터랙티브 그래프 (종목↔섹터↔공시↔뉴스↔메모)** | 사람이 "이 판단 왜 내렸지" 돌아볼 때 관계 그래프가 linear 노트보다 압도적. 경쟁 제품 중 없음 | MEDIUM | graphify 설치·설정 + vault 링크 규칙 준수. LLM이 graph JSON도 읽을 수 있게 함 |
| **"왜 그 판단에 이르렀나" 추적 (decision provenance)** | PROJECT.md 핵심 차별점. 세션마다 판단 근거 노트를 `decisions/` 에 기록 → 다음 세션이 읽음 | MEDIUM | Claude session 종료 시 결정 요약 자동 작성 후 사람 검토 |
| **로컬 LLM 기반 인제스트 (Ollama + Qwen2.5 + bge-m3)** | LLM 비용을 실질적으로 0에 가깝게. 민감 메모 외부 송출 방지 | MEDIUM-HIGH | 한국어 임베딩 품질 검증 필요. bge-m3 유력 |
| **Self-healing wiki linting pass** | Karpathy 아이디어. "끊어진 링크, 누락 frontmatter, 모순 발견" 주기적 검사 | MEDIUM | 규칙 기반 + 로컬 LLM. 야간 배치에 포함 |
| **Investment thesis 노트 템플릿 (assumption, kill criteria, time horizon)** | 매수 이유 명시 없이 나중에 매도 판단이 어려움. 트레이딩 저널 리서치에서 명확한 패턴 | LOW | Obsidian Templater 템플릿. 매수 시 강제 생성 |
| **공매도·대차잔고 트래킹** | 한국 시장 공매도는 시장 민감도 높음. short.krx.co.kr에 공식 데이터 있음 | LOW-MEDIUM | pykrx에 있음. 차별점은 "watchlist 전용 자동 수집 + 급증 알림" |
| **대주주 보유 변동 자동 감시 (5%/1% rule)** | 한국 시장 고유. 경영권 이슈·지분 변동은 가격 임팩트 큼. DART에서 직접 가능 | LOW | 이미 DART 수집 범위라 비용 미미 |
| **증권사 리포트 컨센서스 스냅샷 (목표가 추이, 상/하향 비율)** | 개별 리포트는 편향 있지만 집계는 유용. FnGuide·와이즈리포트가 유료 제공 | MEDIUM | 크롤링 난이도·저작권 고려. 요약·숫자만 저장 |
| **포트폴리오 상태 리뷰 자동 생성 (weekly digest 노트)** | 사람이 놓친 이벤트 catch-up. 장 개장 전 아침 읽기용 | MEDIUM | 배치 + 템플릿. 포트폴리오 상태 노트에 누적 |
| **거래정지/관리종목/불성실공시 경보** | 한국 시장 리스크 지표. KIND에서 공식 데이터 | LOW | 수집 범위 확장 수준. 보유 종목 한정 강한 경보 |

---

### Anti-Features (explicitly NOT building, with reasoning)

These are features the PROJECT.md `Out of Scope` section implies — articulated here so requirements scoping is unambiguous.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **자동 주문 실행 (autotrading / broker API 연동)** | "결정했으면 실행까지" 자연스러운 연장 | 법·리스크·책임 이슈 압도적. Core Value는 *판단 보조*지 집행 아님. 집행 붙는 순간 제품 성격 완전히 바뀜 | 판단 근거만 제공. 주문은 사용자가 브로커에서 수동 |
| **실시간 틱 스트리밍 / 장중 실시간 업데이트** | "최신 정보"에 대한 막연한 욕구 | 인프라 비용 폭증, vault-as-source-of-truth 모델 붕괴, 세션당 토큰 폭증. 일배치로 판단에 충분 | 장 마감 후 배치. 장중 수동 트리거로 특정 티커만 |
| **매 질의마다 실시간 웹 크롤링** | "최신 뉴스 바로 반영" | 세션 토큰·지연시간 폭증, 크롤링 실패 시 사용자 오판, 캐시 불가. PROJECT.md에 명시적 out-of-scope | 인제스트된 vault만 참조. 필요 시 사용자가 수동으로 "지금 갱신" |
| **공개 웹 서비스 / SaaS 배포** | "남들도 쓰게 하자" | 인증·멀티테넌시·법적책임·운영. 2~5명 팀 범위 이탈 | git 저장소 + 개인 Obsidian vault 동기화 수준 유지 |
| **멀티유저 동시 편집 / 실시간 협업** | Google Docs식 직관 | CRDT·충돌해결·권한이 거대한 축. Obsidian sync/git으로 이미 90% 해결 | git pull/push. 충돌은 사람이 머지 |
| **푸시 알림 / 모바일 앱** | "중요 이벤트 즉시 알림" | OS 권한, 푸시 인프라, 사용자 경험 디자인 모두 별도 제품. 우선순위 낮음 | 아침 digest 노트 수동 확인. v2+에서 이메일 요약 정도만 고려 |
| **암호화폐 데이터** | "투자 영역 확장" | 도메인 지식·데이터 소스·리스크 전부 다름. 범위 희석 | 별도 프로젝트 (PROJECT.md 명시) |
| **미국/글로벌 개별 종목 전면 지원** | "기왕이면 다 되면 좋지" | 데이터 소스 전혀 다름 (DART→SEC EDGAR, pykrx→yfinance). v1 깊이 희생 | 매크로 지표만 글로벌. 개별 종목은 v2 이후 |
| **옵션 체인 / 파생상품** | 일부 사용자 수요 | 국내 개인 대중 중 소수. 데이터·판단 로직 별도 영역 | 지수옵션·ELW 필요 시 v2+ 전용 모듈 |
| **tick-level / Level 2 order book / dark pools** | 기관 스타일 기능 욕구 | 데이터 구매 비용 천문학적. 판단 지평(일/주 단위)과 맞지 않음 | 일단위 OHLCV로 충분 |
| **초단기 기술적 지표 자동 매매 신호 (RSI=70이면 매도)** | "자동화된 매매 시그널" | 판단 주체를 LLM+사용자에서 규칙으로 바꿈. Core Value 배신 | 지표는 계산·제시만. 판단은 Claude가 맥락과 함께 |
| **Slack/Discord bot 통합 (v1)** | "어디서든 질의" | MCP stdio 모델과 transport 다름. Claude Code 한 곳에 집중 | Claude Code가 단일 프론트엔드. v2+에서 고려 |
| **종목 추천 / 스크리너 (KOSPI 전체에서 조건 매칭 종목 찾기)** | Stock Rover·Koyfin 대표 기능 | watchlist 수십~수백 종목 가정과 다름. 전체 시장 인제스트는 LLM 비용 폭증 | watchlist 한정 스크리닝만. 전체 스크리닝은 pykrx로 프리필터 후 vault 편입 |
| **Auto-trading backtest framework** | "과거에 이랬으면 어땠을까" | 판단 보조 범위 밖. 별도 제품 (zipline/backtrader) | 사용자가 선호하면 별도 스크립트 |

---

## Korean-Market-Specific Feature Notes

These are domain details commercial Western tools miss and that must be handled first-class:

| Item | What it is | Why it matters | Where it lives |
|------|-----------|----------------|----------------|
| **공시 유형 분류 (A/B/C/D 체계)** | DART의 정기(A)·주요사항(B)·발행(C)·지분(D) 분류 | 이벤트 심각도·시급성이 유형에 강하게 상관. event_type frontmatter 필수 | 수집 단계에서 DART 메타데이터 직접 반영 |
| **주요사항보고서 (B) 세부 유형** | 유상증자·감자·자사주·합병·분할·전환사채·대표이사 변경·소송·어음부도 등 | 각각이 가격에 미치는 방향·크기 다름. LLM이 구분해서 인용해야 | 파싱 시 하위 유형 frontmatter에 기록 |
| **5%/1% 대주주 보유 보고 (D)** | 5% 이상 보유 또는 1% 이상 변동 시 5영업일 내 보고 의무 | 경영권 이슈·매집·펀드 유입 탐지 | 전용 필드 (holder, pct, 변동) |
| **거래정지 / 관리종목 / 불성실공시 / 투자주의·투자경고·투자위험** | KIND 통해 공시. 보유 중이면 즉시 알아야 함 | 보유 종목 리스크 1순위 | KIND RSS/스크래핑 + 강한 경보 |
| **거래정지 사유 분류** | 조회공시 답변 대기, 풍문 등 회보 대기, 상장폐지 심의, 관리종목 지정 | 해제 예측이 완전히 다름 | 사유 필드 분리 저장 |
| **외인·기관 투자자별 매매동향** | KRX Data Marketplace 공식 | 한국 시장 논의의 공용어. 수급 설명 없이는 판단 약함 | pykrx로 일배치 |
| **공매도 잔고 / 대차잔고** | short.krx.co.kr 공식 | 숏 포지션 변화는 방향성 시그널 | pykrx, 일단위 |
| **증권사 컨센서스 (목표가·투자의견·예상 EPS)** | FnGuide·와이즈리포트 | 편향 있지만 집계는 의미 있음. 목표가 괴리율은 자주 인용됨 | 저작권 고려해 숫자/요약만 |
| **ECOS(한국은행) 매크로 지표** | 기준금리·환율·GDP·통화량 | 한국 시장 매크로 질의의 1차 소스 | 일/월/분기별 혼합, 개별 노트 또는 dashboard |
| **한경 컨센서스 / 와이즈리포트** | 리서치 리포트 집계 | 개별 리포트보다 집계 소스가 법적·실용적으로 안전 | 요약·링크, 전문 저장 지양 |

---

## Feature Dependencies

```
[Markdown + frontmatter convention]  ← foundation
        │
        ├─── [Collection scripts: DART, pykrx, news]
        │         │
        │         ├─── [Ingestion: parse → frontmatter → extract edges]
        │         │         │
        │         │         ├─── [Postgres/pgvector indexing (hybrid search)]
        │         │         │         │
        │         │         │         ├─── [stock-mcp tools: search, get_*]
        │         │         │         │         │
        │         │         │         │         └─── [Judgment-support UX (cite + 4-axis evidence)]
        │         │         │         │
        │         │         │         └─── [graphify pass → interactive graph]
        │         │         │                   │
        │         │         │                   └─── [get_related MCP tool]
        │         │         │
        │         │         └─── [Daily batch scheduler + retry + dedup]
        │         │
        │         └─── [Ticker hub, sector, watchlist, portfolio dashboard notes]
        │                   │
        │                   └─── [Weekly digest, thesis template, decision log]
        │                             ← differentiators layer, needs base
        │
        └─── [User research memos (manual)]
                  ← parallel track, works from day 1
```

### Dependency Notes

- **Everything depends on the frontmatter convention.** If ticker / event_type / source / date are not standardized at collection time, retrieval and graph both degrade. This is the single highest-leverage early decision.
- **Hybrid search requires normalized frontmatter → SQL columns.** Structured filters only work if `ticker`, `event_type`, `date` are reliably populated.
- **graphify pass is downstream of ingestion.** It consumes the vault; its quality is bounded by link density in notes. So ticker hubs and cross-linking conventions must precede graphify value.
- **Judgment-support UX depends on all four evidence axes being reachable.** Pros/cons output is worthless if any of (disclosures, price, memos, macro) can't be fetched in one MCP round-trip.
- **Decision log (differentiator) depends on base MCP tools.** Don't build it before `search` and `get_ticker_overview` work.
- **Portfolio dashboard conflicts with nothing but must come *after* ticker hubs exist** — otherwise it points at empty notes.
- **Local LLM ingestion (Ollama/bge-m3) is substitutable with Haiku fallback** — not a blocking dependency. Prefer local for cost, but v1 can mix.

---

## MVP Definition

### Launch With (v1) — The minimum that delivers Core Value

The v1 acceptance test is: *open Claude Code, ask "보유 중인 삼성전자에 대한 최근 상황 요약하고 매수·매도·홀드 의견 근거와 함께 제시해줘", and get an answer that cites recent DART filings, price action, macro context, and the user's own memo notes.*

- [ ] **DART collection (정기·주요사항·발행·지분 4개 유형)** — event-driven 판단의 최소 소스
- [ ] **KOSPI/KOSDAQ 일일 OHLCV + 투자자별 매매동향 + 공매도 잔고 수집** — `pykrx` 기반
- [ ] **경제 뉴스 수집 (watchlist 한정, RSS 우선)** — 2~3개 매체로 시작
- [ ] **매크로 지표 수집 (ECOS 기준금리·환율 + FRED 미 10년물·유가)** — 최소 집합
- [ ] **Markdown + frontmatter 표준 스키마 (ticker/event_type/date/source/id 필수 필드)** — 모든 것의 기반
- [ ] **Ticker hub 노트 자동 생성/갱신 + 수동 편집 공존**
- [ ] **포트폴리오 / watchlist 대시보드 노트** — 사용자 진입점
- [ ] **사용자 research memo 폴더 + 템플릿** — 사람이 쓴 판단도 LLM이 읽음
- [ ] **Postgres + pgvector 하이브리드 검색 (BM25 + dense)** — multilingual embedding
- [ ] **일 1회 배치 스케줄 + 수동 트리거 + 중복 감지**
- [ ] **stock-mcp 6개 tool: get_ticker_overview / search / get_recent_events / get_portfolio_state / get_related / get_filing**
- [ ] **MCP 응답에 vault note path 포함 (citation 필수)**
- [ ] **4축 근거 프롬프트 컨벤션 (disclosure · price · memo · macro)**

### Add After Validation (v1.x) — Once daily loop works

Trigger: v1 answers cite sources but feel shallow or miss events. Add when a concrete miss is observed.

- [ ] **graphify pass over vault → 인터랙티브 그래프 + get_related MCP tool** (trigger: "related context" 질의가 linear search로 해결 안 되는 순간)
- [ ] **거래정지 / 관리종목 / 불성실공시 KIND 수집 + 보유 종목 강경보** (trigger: 한 번이라도 놓쳤을 때)
- [ ] **증권사 컨센서스 스냅샷 (FnGuide 또는 와이즈리포트)** (trigger: "목표가/의견" 질의 반복)
- [ ] **Thesis / decision log 템플릿 + 매수 시 강제** (trigger: 과거 판단 근거 잊어버린 경험)
- [ ] **Weekly digest 노트 자동 생성** (trigger: 일 단위로 보면 놓침)
- [ ] **로컬 LLM 인제스트 전환 (Ollama+Qwen2.5, bge-m3)** (trigger: Haiku 비용이 월별로 유의미해진 시점)
- [ ] **Self-healing lint pass** (trigger: vault가 커지고 링크 깨짐·frontmatter 불일치 누적)
- [ ] **Sector / Theme 노트 확장 (반도체·2차전지·조선 등 한국 특화)**
- [ ] **대주주 5%/1% 변동 전용 추적 모듈**

### Future Consideration (v2+) — Defer until pattern is clear

- [ ] **미국 주식 개별 종목 지원 (SEC EDGAR + yfinance)** — 깊이 확보 후 고려
- [ ] **이메일 weekly digest** — push 알림 대체로 최소 비용
- [ ] **Slack/Discord 프론트엔드** — MCP HTTP transport가 성숙하면
- [ ] **Whole-market 스크리닝 (watchlist 밖 종목 편입 후보 탐색)**
- [ ] **PDF 리포트 OCR (증권사 원문 파싱)** — 저작권·품질 이슈 해결 후
- [ ] **포트폴리오 백테스트 / 가상 매매 시뮬레이터** — 판단 보조 범위 재확인 후

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Frontmatter schema + Markdown convention | HIGH | LOW | P1 |
| DART 4개 유형 수집 | HIGH | MEDIUM | P1 |
| pykrx 가격·수급·공매도 일배치 | HIGH | LOW | P1 |
| 뉴스 RSS (watchlist 한정) | HIGH | MEDIUM | P1 |
| ECOS + FRED 매크로 지표 | HIGH | LOW | P1 |
| Ticker hub / portfolio / research memo 노트 | HIGH | LOW | P1 |
| Postgres + pgvector 하이브리드 검색 | HIGH | MEDIUM-HIGH | P1 |
| 일 배치 + 수동 트리거 + 중복 감지 | HIGH | LOW | P1 |
| 6개 MCP tools + 인용 규칙 | HIGH | MEDIUM | P1 |
| graphify 통합 | MEDIUM-HIGH | MEDIUM | P2 |
| 거래정지·관리종목·KIND 경보 | HIGH (위험) | LOW | P2 |
| 증권사 컨센서스 스냅샷 | MEDIUM | MEDIUM | P2 |
| Thesis / decision log 템플릿 | HIGH | LOW | P2 |
| Weekly digest 자동생성 | MEDIUM-HIGH | MEDIUM | P2 |
| 로컬 LLM 인제스트 전환 | MEDIUM (비용) | MEDIUM-HIGH | P2 |
| Self-healing lint | MEDIUM | MEDIUM | P2 |
| 미국 주식 지원 | LOW (v1) | HIGH | P3 |
| 자동 주문 실행 | — | — | ANTI |
| 실시간 틱 데이터 | — | — | ANTI |
| 공개 웹 서비스 | — | — | ANTI |

---

## Competitor Feature Analysis

Useful as reference for *shape of a stock research surface*, not feature parity targets. Our axis of differentiation is **LLM-native + vault as source of truth + Korean market depth**, which none of these combine.

| Feature | Koyfin (global terminal) | Stock Rover (US screener) | Simply Wall St (infographic) | Fiscal.ai/FinChat (AI copilot) | OpenBB (open-source terminal) | Our Approach |
|---------|--------------------------|---------------------------|------------------------------|--------------------------------|-------------------------------|--------------|
| **Scope** | 100K+ global securities | 8.5K US | Global retail-grade | Global, AI-first | Global, extensible | KOSPI/KOSDAQ deep; global only for macro |
| **Fundamentals data** | Rich, terminal-style | Best-in-class screening | Simplified infographic | AI-summarized | Pluggable providers | DART 재무제표 + pykrx. Depth over breadth |
| **News integration** | Yes, bundled | Yes | Limited | Yes | Pluggable | Watchlist-scoped RSS → vault. Pull, not push |
| **Charting** | Advanced | Advanced | Infographic | Advanced + AI | Advanced | **Deliberately minimal.** Claude narrates; user views in Obsidian if needed |
| **Screener** | Powerful | Best-in-class | Limited | AI natural-language | Pluggable | **Out of scope for v1** — watchlist-only |
| **AI copilot** | Limited | No | No | Core feature | Recent addition | **This IS the product.** Not a feature, the substrate |
| **Korean market depth** | Thin (global list) | None | Thin | Thin | Thin | **Primary axis of differentiation** |
| **Personal notes / journal** | No | Limited | No | No | No | **First-class.** Karpathy llm-wiki pattern |
| **Graph view of relationships** | No | No | No | No | No | **graphify differentiator** |
| **Citations to source** | N/A | N/A | N/A | Links to data | N/A | **Mandatory vault path citations** |
| **Cost model** | Subscription | Subscription | Subscription | Subscription | Open-source (hosted tiers) | Self-host. LLM cost minimized via local ingest |
| **Trade journal** | No | Basic | No | No | No | **Decision log as differentiator** |

**Transferable patterns** (worth adopting):
- Pros/cons-style decision output (from Seeking Alpha scorecards)
- Thesis + kill criteria template (from trading journal best practices — TradesViz, TraderSync, TradeZella)
- 4-axis evidence bundle (implicit in OpenBB/Koyfin terminal UX where users see price + news + fundamentals + macro in one view)
- Consensus snapshot over individual reports (FnGuide/WiseReport pattern —집계가 더 안전)

**Different-product patterns** (explicitly reject):
- Broad-market screener
- Real-time tick streaming
- Auto-trading hooks
- Multi-user dashboards
- Mobile-first UX

---

## Open Questions for Requirements Phase

Not gaps in research — decisions that require the designer's input, noted here so roadmap planning surfaces them:

1. **News source selection** — which 2–3 Korean media outlets for v1? (한경·이데일리·서울경제·조선비즈 후보). Trade-off: RSS availability vs coverage quality vs legal risk.
2. **Memo 위치 / 구조** — `research/{ticker}/` 단일 폴더 vs 날짜 기반 저널 vs 혼합. 사용자 습관에 달림.
3. **Embedding 모델 확정** — bge-m3 vs multilingual-e5 vs E5-mistral. 한국어 품질 벤치마크 필요.
4. **Postgres vs PGLite** — PROJECT.md가 PGLite로 시작 언급. 2~5명이지만 서버 있으면 Postgres 낫다. 배포 편의 vs 성능.
5. **포트폴리오 상태 입력 방식** — 사람이 markdown에 직접 vs 브로커 CSV import vs API. v1은 수동이 단순하지만 오차 원인.
6. **그래프 갱신 주기** — graphify full pass는 비싸다. 일 1회 vs 주 1회 vs 증분.

These are requirements-phase questions, not research gaps. The feature landscape itself is well-mapped.

---

## Sources

**Korean market (HIGH confidence, official sources):**
- [DART 전자공시시스템 — 기업공시 길라잡이 (주요사항보고)](https://dart.fss.or.kr/info/main.do?menu=220)
- [DART 대량 보유상황 보고 (5%/1% rule)](https://dart.fss.or.kr/info/main.do?menu=310)
- [DART 임원 소유상황 보고](https://dart.fss.or.kr/info/main.do?menu=320)
- [KIND 대한민국 대표 기업공시채널 — 거래정지·관리종목](https://kind.krx.co.kr/investwarn/delcompany.do)
- [KRX Data Marketplace — 투자자별 매매동향](https://data.krx.co.kr/)
- [한국거래소 공매도 통계](https://short.krx.co.kr/)
- [한국은행 ECOS Open API](https://ecos.bok.or.kr/api/)
- [OpenDartReader (FinanceData)](https://github.com/FinanceData/OpenDartReader)
- [찾기쉬운 생활법령정보 — 관리종목 지정 및 상장폐지](https://easylaw.go.kr/CSP/CnpClsMain.laf?popMenu=ov&csmSeq=1701&ccfNo=1&cciNo=2&cnpClsNo=2)
- [KRX 코스닥시장 공시·상장관리 해설 2025](https://kind.krx.co.kr/external/dst/reference/11499/)
- [FnGuide / 컴퍼니가이드 요약리포트](https://comp.fnguide.com/SVO2/ASP/SVD_Report_Summary.asp)
- [와이즈리포트](https://www.wisereport.co.kr/)
- [한경 컨센서스](https://markets.hankyung.com/consensus)

**LLM-wiki and architecture patterns (MEDIUM-HIGH confidence):**
- [Karpathy LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [VentureBeat — Karpathy's LLM Knowledge Base architecture](https://venturebeat.com/data/karpathy-shares-llm-knowledge-base-architecture-that-bypasses-rag-with-an)
- [MindStudio — Personal knowledge base with Claude Code](https://www.mindstudio.ai/blog/andrej-karpathy-llm-wiki-knowledge-base-claude-code)
- [DAIR.AI — LLM Knowledge Bases](https://academy.dair.ai/blog/llm-knowledge-bases-karpathy)

**MCP and tools patterns (MEDIUM confidence):**
- [FastMCP — Tools](https://gofastmcp.com/servers/tools)
- [Financial Datasets MCP Server](https://github.com/financial-datasets/mcp-server)
- [Alpha Vantage MCP for Stock Market Data](https://mcp.alphavantage.co/)
- [EODHD MCP Server docs](https://eodhd.com/financial-apis/mcp-server-for-financial-data-by-eodhd)
- [Lambda Finance — MCP Server Stock Market Data ranking 2026](https://www.lambdafin.com/articles/mcp-server-stock-market-data)
- [LSEG — Claude Financial Plugins](https://www.lseg.com/en/insights/supercharge-claudes-financial-skills-with-lseg-data)

**Hybrid search (HIGH confidence):**
- [ParadeDB — Hybrid Search in PostgreSQL: The Missing Manual](https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual)
- [Pedro Alonso — BM25 Search in PostgreSQL](https://www.pedroalonso.net/blog/postgres-bm25-search/)
- [VectorChord — Hybrid search with native BM25](https://blog.vectorchord.ai/hybrid-search-with-postgres-native-bm25-and-vectorchord)
- [Tiger Data — Optimize full text search with BM25](https://www.tigerdata.com/docs/use-timescale/latest/extensions/pg-textsearch)

**Competitor products (MEDIUM confidence, surveys):**
- [OpenBB Terminal Pro Review 2026](https://aichief.com/ai-business-tools/openbb-terminal-pro/)
- [OpenBB Workspace — AI-powered research workspace](https://openbb.co/blog/introducing-the-new-openbb-terminal/)
- [Koyfin vs Stock Rover 2026 — TraderHQ](https://traderhq.com/koyfin-vs-stock-rover/)
- [Koyfin vs FinChat / Fiscal.ai 2026](https://traderhq.com/koyfin-vs-finchat/)
- [Best Simply Wall St Alternatives 2026 — Gainify](https://www.gainify.io/blog/best-alternatives-to-simplywall-stock-research)
- [13 Best Stock Research Websites 2026 — BusinessQuant](https://businessquant.com/best-stock-research-websites)

**Trading journals and decision frameworks (MEDIUM confidence):**
- [5 Best Trading Journals for 2026 — StockBrokers.com](https://www.stockbrokers.com/guides/best-trading-journals)
- [TradesViz](https://www.tradesviz.com/)
- [TraderSync](https://tradersync.com/)
- [TradeZella](https://www.tradezella.com/)
- [Winvesta — Fundamental analysis checklist](https://www.winvesta.in/blog/investors/building-your-fundamental-analysis-checklist-for-stock-picking)
- [Old School Value — 40 Point Stock Checklist](https://www.oldschoolvalue.com/investing-strategy/stock-selection-investment-checklist/)

**Obsidian patterns (MEDIUM confidence):**
- [Obsidian Charts View plugin](https://www.obsidianstats.com/plugins/obsidian-chartsview-plugin)
- [Top Obsidian Plugins in 2026 — Obsibrain](https://www.obsibrain.com/blog/top-obsidian-plugins-in-2026-the-essential-list-for-power-users)

---

*Feature research for: Korean-market stock knowledge base (Obsidian + gbrain + graphify + stock-mcp)*
*Researched: 2026-04-17*
