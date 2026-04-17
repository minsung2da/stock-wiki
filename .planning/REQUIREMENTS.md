# Requirements: Stock Wiki — Claude-Powered Korean Market Knowledge Base

**Defined:** 2026-04-17
**Core Value:** Claude Code에서 보유·관심 종목을 질의했을 때, 최신 공시·뉴스·가격·본인 리서치 메모를 종합한 근거 있는 매수/매도 판단을 즉시 받을 수 있다.

## v1 Requirements

v1 스코프는 리서치(`.planning/research/`)의 Must-Have(table stakes) 9개 그룹에서 도출되었다. 각 요구사항은 원자적·테스트 가능·사용자 중심으로 기술되었다.

### 토대 (Foundation)

- [x] **FOUND-01**: 프로젝트가 네이티브 Postgres 17 컨테이너(Docker)를 `docker-compose`로 기동할 수 있다 (pgvector + VectorChord-BM25 + pg_trgm extension 로드됨)
- [x] **FOUND-02**: Obsidian vault에 `raw/`, `notes/`, `ingested/`, `dashboards/`, `graph/` 폴더 구조가 준비되어 있다 (기존 `.obsidian/`, `환영합니다!.md` 보존)
- [x] **FOUND-03**: `.gitignore`가 `.obsidian/workspace*`, `.obsidian/cache`, Ollama 캐시, 개인 포트폴리오 overlay 파일을 제외한다
- [ ] **FOUND-04**: WSL 성능을 위해 vault 경로를 `/mnt/c/…/stock` 에서 WSL 네이티브 경로(`~/stock` 또는 symlink)로 마이그레이션 옵션이 문서·스크립트로 제공된다
- [ ] **FOUND-05**: `uv` 기반 Python 3.12 환경에 수집·인제스트·MCP 각 의존성이 격리된 venv로 설치된다 (특히 ingest venv에는 `anthropic` 패키지 없음)
- [ ] **FOUND-06**: Pydantic 기반 frontmatter 스키마 (`FrontMatter`, `ProvenanceBlock`, `IngestStateBlock`, `DerivedBlock`)가 정의되고 단위 테스트로 검증된다

### 엔티티 모델 (Entity Model)

- [ ] **ENT-01**: `corp_code`(DART 8자리)가 캐노니컬 엔티티 ID로 사용된다; 6자리 KRX 티커는 편의 필드
- [ ] **ENT-02**: 종목명 변경·합병·분할·상장폐지·티커 재활용을 추적할 수 있는 `entities` 테이블과 시간 범위 이력이 있다
- [ ] **ENT-03**: DART 기재정정(`supersedes`) 체인이 엣지로 저장되어 최신 공시만 소비 가능하다

### 수집 (Collection) — LLM 토큰 0

- [ ] **COLL-01**: `collect_dart` 스크립트가 dart-fss로 DART 4유형(A 정기 / B 주요사항 / C 발행 / D 지분)을 일배치 수집하여 `vault/raw/dart/YYYY-MM-DD/*.md`에 저장한다
- [ ] **COLL-02**: `collect_krx` 스크립트가 pykrx로 관심·보유 종목의 일별 OHLCV·투자자 수급(외국인·기관·개인)·공매도 잔고를 수집한다
- [ ] **COLL-03**: `collect_news` 스크립트가 trafilatura + RSS로 관심 종목 스코프 경제·금융 뉴스(한경·이데일리·서울경제 중 최소 2개)를 수집한다
- [ ] **COLL-04**: `collect_macro` 스크립트가 한은 ECOS + FRED에서 기준금리·USD/KRW·미10년물·WTI를 수집한다
- [ ] **COLL-05**: `collect_kind` 스크립트가 KIND에서 거래정지·관리종목·불성실공시 지정을 수집한다
- [ ] **COLL-06**: 모든 수집 스크립트는 최소 frontmatter(`source`, `date`, `id`, `ticker?`, `corp_code?`, `url`, `content_hash`)만 작성하고 LLM 호출을 하지 않는다
- [ ] **COLL-07**: CI 테스트가 `ingest/` 및 `collectors/` 디렉터리에서 `anthropic`·`openai` import를 검출하면 실패한다
- [ ] **COLL-08**: 각 수집기가 소스별 격리(한 소스 실패가 다른 소스 실행을 막지 않음) + 재시도 + 멱등 업서트(content-hash 키)를 지원한다
- [ ] **COLL-09**: 수집 실행 성공·실패 heartbeat가 `vault/ingested/_status/heartbeat.md`에 기록되어 사일런트 실패를 감지할 수 있다

### 인제스트 (Ingestion) — 로컬 LLM 우선

- [ ] **INGEST-01**: 인제스트 워커가 raw 문서를 content-hash 기반으로 중복 감지하고 변경된 것만 재처리한다 (idempotent)
- [ ] **INGEST-02**: 단일 `llm_client.py` 추상화가 Ollama 엔드포인트를 기본으로 하고 `ALLOW_CLOUD_LLM=1` + `MAX_CLOUD_USD` 가드 하에서만 Claude Haiku 4.5 폴백을 허용한다
- [ ] **INGEST-03**: Ollama + Qwen2.5-14B-Instruct (Q4_K_M)가 기본 추출 모델로 동작한다
- [ ] **INGEST-04**: EXAONE-3.5-7.8B가 한국어 특화 문서(뉴스 본문·리포트)에 사용된다
- [ ] **INGEST-05**: LLM이 frontmatter의 `_derived` 블록에 `tickers`, `event_type`, `catalysts`, `sentiment`, `numeric_facts`, `summary` 속성을 추출하여 쓴다
- [ ] **INGEST-06**: DART 재무제표 수치는 LLM을 거치지 않고 dart-fss 구조화 접근자를 통해 직접 추출된다
- [ ] **INGEST-07**: 뉴스·리포트 본문의 숫자 추출은 regex 후보 추출 → LLM 선택 → Pydantic 검증 → 자릿수 체크섬 단계를 거친다
- [ ] **INGEST-08**: 프롬프트 인젝션 방어: untrusted 본문은 XML 델리미터로 감싸 전달, 알려진 주입 패턴(`ignore previous`, 가짜 system 태그 등)을 사전 필터링한다
- [ ] **INGEST-09**: 종목토론방 같은 적대적 소스의 개별 게시물 본문은 LLM 추출 파이프라인에 투입하지 않는다
- [ ] **INGEST-10**: bge-m3 임베딩(1024차원)이 Ollama를 통해 생성되고 Postgres `chunks` 테이블에 저장된다
- [ ] **INGEST-11**: mecab-ko로 한국어 사전 토큰화된 필드가 `chunks.bm25_tokens`에 저장되어 BM25 쿼리에 사용된다
- [ ] **INGEST-12**: 임베딩 모델 버전이 `chunks.embedding_model` 컬럼에 기록되어 모델 변경 시 재인덱싱이 가능하다

### 저장소 (Storage)

- [ ] **STORE-01**: Alembic 마이그레이션으로 `documents`, `chunks`, `entities`, `edges`, `events`, `ingest_runs` 테이블과 인덱스가 생성된다
- [ ] **STORE-02**: `documents.id`는 `sha256(body)`로 정의되어 콘텐츠 주소화된다
- [ ] **STORE-03**: `chunks`에 HNSW 벡터 인덱스(pgvector 0.8, `iterative_scan=relaxed_order`)가 설정된다
- [ ] **STORE-04**: VectorChord-BM25 인덱스가 `chunks.bm25_tokens`에 설정된다
- [ ] **STORE-05**: Markdown+frontmatter vault 단독으로 DB 전체를 재구성할 수 있는 `ingest rebuild` 커맨드가 있다 (DB는 캐시, vault는 SoT)
- [ ] **STORE-06**: frontmatter 세 구역(provenance / ingest state / `_derived`)이 혼합되지 않도록 ingest 코드가 구역별 write 권한을 enforce한다

### 하이브리드 검색 (Retrieval)

- [ ] **RET-01**: `search(query, …)` API가 dense(HNSW 코사인) + BM25를 병렬 실행하고 RRF(k=60)로 융합한다
- [ ] **RET-02**: `search`가 구조화 필터(`ticker`, `corp_code`, `date_range`, `source`, `event_type`)를 벡터 스캔 전에 SQL WHERE로 적용한다
- [ ] **RET-03**: 응답은 `{vault_path, excerpt, frontmatter_ref, score}` 배열이며 단일 응답 8k 토큰 미만, 레이턴시 p95 < 5초이다

### stock-mcp 서버

- [ ] **MCP-01**: FastMCP 2.x 기반 `stock-mcp` 서버가 stdio 전송으로 Claude Code에 등록된다
- [ ] **MCP-02**: `search(query, ticker?, date_range?, source?, mode='hybrid'|'semantic'|'bm25')` 툴
- [ ] **MCP-03**: `get_ticker_overview(ticker)` 툴 — 재무·수급·최근 이벤트·관련 메모 통합 뷰
- [ ] **MCP-04**: `get_recent_events(ticker, since)` 툴 — DART 공시·뉴스·KIND 이벤트 타임라인
- [ ] **MCP-05**: `get_portfolio_state()` 툴 — `dashboards/portfolio.md`의 보유 종목·상태 반환
- [ ] **MCP-06**: `get_related(document_id, depth?)` 툴 — 그래프 엣지 이웃 조회
- [ ] **MCP-07**: `get_filing(id)` 툴 — 특정 문서 전체 본문 반환 (ID 기반 two-step 패턴)
- [ ] **MCP-08**: `add_note(path, body, frontmatter?)` 툴 — `vault/notes/`에만 쓰기 허용 (raw/ingested는 write-protected)
- [ ] **MCP-09**: `health()` 툴 — 마지막 배치 성공 시각, DB 연결, 각 소스별 스테일니스 반환
- [ ] **MCP-10**: 툴 docstring이 LLM-facing 행동 계약으로 작성되어 있고 CI 테스트로 레이턴시·토큰 크기를 검증한다

### 그래프 (Graph)

- [ ] **GRAPH-01**: 인제스트가 `edges` 테이블에 `ticker→filing`, `filing→event`, `note→ticker`, `event→event`, `ticker→sector` 엣지를 구축한다
- [ ] **GRAPH-02**: graphify가 일배치 또는 수동 실행으로 vault 스냅샷을 생성하여 `vault/graph/{YYYY-MM-DD}/` 에 `index.html`·`graph.json`·`GRAPH_REPORT.md`를 쓴다
- [ ] **GRAPH-03**: 3-5개의 캐노니컬 서브그래프 쿼리 (예: "내 포지션 관련 최근 30일 이벤트", "섹터 내 공시 클러스터") 가 문서화되고 graphify wiki 출력에 링크된다

### 대시보드 (Dashboards)

- [ ] **DASH-01**: `dashboards/portfolio.md`가 보유 종목·평가액·최근 이벤트 요약을 Dataview 쿼리로 자동 표시한다
- [ ] **DASH-02**: `dashboards/watchlist.md`가 관심 종목 상태를 표시한다
- [ ] **DASH-03**: `dashboards/events-this-week.md`가 이번 주 주요 공시·뉴스·거래정지를 집계한다
- [ ] **DASH-04**: 티커별 hub 노트(`ingested/by-ticker/{corp_code}.md`)가 자동 생성되어 관련 문서·메모·가격 트렌드를 링크한다

### 메모·리서치 (Notes)

- [ ] **NOTE-01**: `notes/theses/` 아래에 thesis(투자 논리·kill criteria) 템플릿이 있고 새 노트가 템플릿으로 생성된다
- [ ] **NOTE-02**: `notes/journal/` 아래에 일지·의사결정 로그 템플릿이 있다
- [ ] **NOTE-03**: 메모 frontmatter가 `tickers[]`, `tags[]`, `created`, `author`를 포함해 DB에 인덱싱된다

### Claude 판단 보조 (Judgment Support)

- [ ] **JUDGE-01**: "종목 X 리서치해줘" 쿼리 시 Claude가 `get_ticker_overview`+`get_recent_events`+`search(user notes)`를 호출하여 공시·가격·유저메모·매크로 4축 근거 번들로 답한다
- [ ] **JUDGE-02**: "포트폴리오 오늘 어때?" 쿼리 시 Claude가 `get_portfolio_state`+ 각 보유 종목 최근 이벤트 요약으로 답한다
- [ ] **JUDGE-03**: "매도 후보 3개" 쿼리 시 Claude가 portfolio+events 기반 근거 포함 후보를 제안한다
- [ ] **JUDGE-04**: 모든 응답에 vault 경로 인용이 포함된다 (`see: vault/raw/dart/2026-04-15/123.md`)
- [ ] **JUDGE-05**: 관련 문서가 없거나 스테일할 때 Claude는 추측 대신 "근거 없음/스테일" 규칙을 따른다 (MCP `health()` 신호 활용)
- [ ] **JUDGE-06**: 유저의 강한 의견(notes/)과 공시·뉴스(raw/)의 가중치를 프롬프트 규약에서 명시해 편향을 줄인다

### 운영 (Operations)

- [ ] **OPS-01**: systemd.timer(WSL) 또는 Windows 작업 스케줄러 유닛이 `daily-batch` 명령을 매일 장 마감 후 실행한다
- [ ] **OPS-02**: `stock batch run --source=…` 등 수동 CLI가 제공된다
- [ ] **OPS-03**: `ingest_runs` 테이블이 각 실행의 시작·종료·소스·결과를 기록한다
- [ ] **OPS-04**: `ingest doctor` 커맨드가 vault-DB drift(누락된 문서, 고아 chunks)를 감지·보고한다
- [ ] **OPS-05**: 수집·인제스트 실패가 heartbeat 파일·로그·MCP `health()`에 드러난다
- [ ] **OPS-06**: DART API 키·DB 비밀번호 등 시크릿이 `.env`에서 읽히고 vault·git에 커밋되지 않는다

## v2 Requirements

v1 검증 후 효용이 입증된 항목부터 점진 도입.

### 고급 인제스트·검색

- **V2-ING-01**: 임베딩 리랭커(bge-reranker-m3) 도입
- **V2-ING-02**: DART 사업보고서(장문) 최적 청킹 전략 벤치마크 결과 반영
- **V2-ING-03**: bge-m3-ko 파인튜닝 버전 평가 및 전환

### 알림·모니터링

- **V2-ALERT-01**: KIND 거래정지/관리종목/불성실공시 발생 시 `dashboards/alerts.md` 자동 생성
- **V2-ALERT-02**: 주요 수급 이상치(전일 대비 N표준편차) 알림
- **V2-DIGEST-01**: 주간 다이제스트 노트 자동 생성 (`notes/digests/YYYY-Www.md`)

### 정성 품질

- **V2-QUAL-01**: recall@10 eval suite (수작업 라벨 50-200 질의)
- **V2-QUAL-02**: self-healing lint pass — 고아 링크, 중복 티커 hub 자동 정리
- **V2-QUAL-03**: 로컬 LLM vs Haiku 추출 품질 벤치마크 + 자동 라우팅

### 원문·저작권

- **V2-DOC-01**: 증권사 PDF 리포트 OCR (저작권 이슈 해결 후)
- **V2-DOC-02**: 뉴스 원문은 요약+링크만, 본문 필요 시 사용자가 수동으로 `notes/clips/`에 저장하는 흐름

## Out of Scope

| Feature | Reason |
|---------|--------|
| 자동 주문 실행(autotrading) | 법적 리스크·스코프 외. 판단 보조가 목표이며 집행은 외부 HTS/MTS 사용 |
| 실시간 틱/레벨2 스트리밍 | 일배치로 충분, vault-as-SoT 모델 파괴, 비용 과다 |
| 매 질의당 실시간 크롤링 | 토큰 비용·레이턴시 폭발, 캐시 효과 상실. 인제스트된 vault만 참조 |
| 공개 SaaS 배포 | 2-5명 내부 사용, 인증·확장성 설계 회피 |
| 모바일 앱·푸시 알림 | 데스크톱 Obsidian + Claude Code가 인터페이스 |
| 미국 개별 종목 데이터 모델 | 다른 데이터 모델, 범위 희석. v2+ 이후 별도 설계 |
| 암호화폐 | 별도 도메인, 별도 프로젝트로 분리 |
| 전체 시장 스크리너 | 포트폴리오·관심 종목 중심이 기본 — 스크리닝은 v2+ |
| Slack/Discord 프론트엔드 | Obsidian + Claude Code가 유일 인터페이스 |
| 백테스트·시뮬레이션 | 의사결정 보조가 v1 목표이지 백테스트 엔진 아님 |
| 다중 사용자 collab(실시간) | git 기반 협업으로 충분, 실시간 편집은 Obsidian Sync나 외부 서비스 위임 |
| Claude API를 인제스트 배치 루프에 사용 | 비용 폭주 원천. 아키텍처적으로 금지 (COLL-07) |

## Traceability

각 요구사항의 phase 매핑 (roadmap 생성 시 확정됨). 모든 v1 요구사항은 정확히 하나의 phase에 매핑된다.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FOUND-01 | Phase 1 | Complete |
| FOUND-02 | Phase 1 | Complete |
| FOUND-03 | Phase 1 | Complete |
| FOUND-04 | Phase 1 | Pending |
| FOUND-05 | Phase 1 | Pending |
| FOUND-06 | Phase 1 | Pending |
| ENT-01 | Phase 2 | Pending |
| ENT-02 | Phase 2 | Pending |
| ENT-03 | Phase 2 | Pending |
| COLL-01 | Phase 3 | Pending |
| COLL-02 | Phase 4 | Pending |
| COLL-03 | Phase 4 | Pending |
| COLL-04 | Phase 4 | Pending |
| COLL-05 | Phase 4 | Pending |
| COLL-06 | Phase 3 | Pending |
| COLL-07 | Phase 1 | Pending |
| COLL-08 | Phase 3 | Pending |
| COLL-09 | Phase 3 | Pending |
| INGEST-01 | Phase 3 | Pending |
| INGEST-02 | Phase 5 | Pending |
| INGEST-03 | Phase 5 | Pending |
| INGEST-04 | Phase 5 | Pending |
| INGEST-05 | Phase 5 | Pending |
| INGEST-06 | Phase 5 | Pending |
| INGEST-07 | Phase 5 | Pending |
| INGEST-08 | Phase 3 | Pending |
| INGEST-09 | Phase 3 | Pending |
| INGEST-10 | Phase 3 | Pending |
| INGEST-11 | Phase 3 | Pending |
| INGEST-12 | Phase 3 | Pending |
| STORE-01 | Phase 2 | Pending |
| STORE-02 | Phase 2 | Pending |
| STORE-03 | Phase 3 | Pending |
| STORE-04 | Phase 3 | Pending |
| STORE-05 | Phase 3 | Pending |
| STORE-06 | Phase 3 | Pending |
| RET-01 | Phase 3 | Pending |
| RET-02 | Phase 3 | Pending |
| RET-03 | Phase 3 | Pending |
| MCP-01 | Phase 3 | Pending |
| MCP-02 | Phase 3 | Pending |
| MCP-03 | Phase 6 | Pending |
| MCP-04 | Phase 6 | Pending |
| MCP-05 | Phase 6 | Pending |
| MCP-06 | Phase 6 | Pending |
| MCP-07 | Phase 6 | Pending |
| MCP-08 | Phase 6 | Pending |
| MCP-09 | Phase 6 | Pending |
| MCP-10 | Phase 6 | Pending |
| GRAPH-01 | Phase 7 | Pending |
| GRAPH-02 | Phase 7 | Pending |
| GRAPH-03 | Phase 7 | Pending |
| DASH-01 | Phase 8 | Pending |
| DASH-02 | Phase 8 | Pending |
| DASH-03 | Phase 8 | Pending |
| DASH-04 | Phase 8 | Pending |
| NOTE-01 | Phase 8 | Pending |
| NOTE-02 | Phase 8 | Pending |
| NOTE-03 | Phase 8 | Pending |
| JUDGE-01 | Phase 9 | Pending |
| JUDGE-02 | Phase 9 | Pending |
| JUDGE-03 | Phase 9 | Pending |
| JUDGE-04 | Phase 3 | Pending |
| JUDGE-05 | Phase 9 | Pending |
| JUDGE-06 | Phase 9 | Pending |
| OPS-01 | Phase 9 | Pending |
| OPS-02 | Phase 9 | Pending |
| OPS-03 | Phase 9 | Pending |
| OPS-04 | Phase 9 | Pending |
| OPS-05 | Phase 9 | Pending |
| OPS-06 | Phase 1 | Pending |

**Coverage:**
- v1 requirements: 71 total
- Mapped to phases: 71 ✓ (모든 v1 요구사항이 정확히 한 phase에 매핑됨)
- Unmapped: 0

**Phase distribution:**
- Phase 1 (Load-Bearing Foundation): 8 requirements
- Phase 2 (Canonical Entity Identity): 5 requirements
- Phase 3 (One-Company Walking Skeleton): 20 requirements
- Phase 4 (Multi-Source Collector Coverage): 4 requirements
- Phase 5 (Local-LLM Enrichment with Korean Number Safety): 6 requirements
- Phase 6 (Full MCP Tool Surface): 8 requirements
- Phase 7 (Graph Layer & graphify Integration): 3 requirements
- Phase 8 (Vault Dashboards & Research Memo Templates): 7 requirements
- Phase 9 (Judgment Prompt Conventions & Operations Hardening): 10 requirements

---
*Requirements defined: 2026-04-17*
*Last updated: 2026-04-17 after roadmap traceability mapping*
