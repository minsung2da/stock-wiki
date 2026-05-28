# stock — Milestone v2.0 Roadmap

**DB-direct Korean stock analysis system**

Started: 2026-05-29
Predecessor: v1.0 (LLM-wiki strategy) — archived at git tag `pre-llm-wiki-shutdown` /
branch `archive/llm-wiki-2026-04`. Shutdown rationale and v2.0 design rationale in
`.planning/research/redesign-2026-05.md` (authoritative architecture criteria).

## Core Value (v2.0)

Claude Code에서 보유·관심 종목을 질의했을 때, **AI가 종목을 찍어주지 않는다.** 대신 매일
모은 공시·뉴스·가격·본인 thesis를 *근거 카드(decision_card)*로 압축해 보여주고, 모순과
만료 조건을 명시한다. 사람이 더 빨리, 더 discipline 있게 결정한다. 검증된 paper-trade
실적이 있는 종목에 한해 KIS API로 자동매매를 보조한다.

이 framing은 v1.0의 "LLM이 vault를 enrich한다"와 다르다 — 이번엔 Postgres가 source of
truth, Markdown vault는 폐기, 사용자 thesis 메모만 disk에 잔존.

## Phases

- [ ] **Phase 1: Collector DB-Direct Cutover** — 5개 collector가 Markdown 출력을 멈추고 Postgres에 직접 INSERT
- [ ] **Phase 2: Decision Card Schema & Storage** — `decision_cards` 테이블 + Pydantic 모델 + 마이그레이션
- [ ] **Phase 3: MCP Tool Surface (Read-Side)** — 타입드 MCP 도구로 stock-mcp 대체
- [ ] **Phase 4: Analysis Runner (3-role Debate)** — Bull/Bear/Judge 서브에이전트 → decision_card 생성
- [ ] **Phase 5: Briefing Renderer** — 일/주 top-N 변화 요약
- [ ] **Phase 6: Paper-Trade Action Layer** — Gates A–D + KIS 모의 API + ≥30일 shadow
- [ ] **Phase 7: Live Trade Promotion** — paper 성과 게이트 통과 시에만 실거래
- [ ] **Phase 8: Evaluation Harness** — CPCV+embargo 백테스트 + Sonnet KR 금융 보정 평가
- [ ] **Phase 9: Ops Hardening** — Routine 스케줄 + 모순율 대시보드 + 전제 만료 알람

## Phase Details

### Phase 1: Collector DB-Direct Cutover

**Goal**: 5개 collector(`dart`, `krx`, `news`, `macro`, `kind`)가 `vault/raw/*.md` 출력을 멈추고
Postgres 테이블에 직접 INSERT한다. `shared/heartbeat.py` no-op stub과 `--vault-root` CLI 인자도
제거한다.

**Depends on**: 없음 (시작 phase)

**Requirements**: [SC-1, SC-2, SC-3, SC-4, SC-5, SC-6]

**Driving design decision**: `redesign-2026-05.md` §2 — "Postgres가 source of truth, Markdown 중간층 폐기"

**Success Criteria** (what must be TRUE):
  1. `uv run stock collect dart --corp-code=00126380 --since=2026-01-01`이 `filings` 테이블에 직접
     INSERT 한다. `vault/raw/` 디렉토리가 다시 생기지 않는다.
  2. `krx`, `news`, `macro`, `kind` 모두 같은 패턴: 각자의 테이블(`ohlcv`, `news`, `macro_series`,
     `events`)에 직접 INSERT. content-hash 기반 dedup은 그대로 유지 (UPSERT ON CONFLICT).
  3. `src/shared/heartbeat.py` no-op stub이 제거되고 collector 5개에서 import도 제거된다.
     실행 통계는 구조화된 로그(`logging.info(extra=...)`)로 stderr에만 남긴다.
  4. `--vault-root` CLI 인자가 모든 subcommand에서 제거된다.
  5. `tests/collectors/` 테스트 스위트가 INSERT 경로를 검증한다. Markdown 작성 stub은 모두
     제거된다.
  6. `stock-enrich-daily` routine은 이미 disable됨 — 추가 작업 없음.

**Plans:** 9 plans across 4 waves
- [ ] 01-01-PLAN.md — Schema migration 0006 + ORM models (Wave 0)
- [ ] 01-02-PLAN.md — CLI cleanup + collector signature strip (Wave 0)
- [ ] 01-03-PLAN.md — macro collector cutover → `macro_series` (Wave 1)
- [ ] 01-04-PLAN.md — krx collector cutover → `ohlcv` (Wave 1)
- [ ] 01-05-PLAN.md — kind collector cutover → `filings` + `events` (Wave 2)
- [ ] 01-06-PLAN.md — news collector cutover → `news` (Wave 2)
- [ ] 01-07-PLAN.md — dart collector cutover → `filings` (Wave 2)
- [ ] 01-08-PLAN.md — Observability: `collector_runs` + delete heartbeat.py (Wave 3)
- [ ] 01-09-PLAN.md — Writer deletion + Veto #9 fences + SC coverage table (Wave 3)

See `.planning/phases/01-collector-db-cutover/PLAN-INDEX.md` for the dependency
graph and Success Criteria Coverage table.

---

### Phase 2: Decision Card Schema & Storage

**Goal**: `decision_cards` 테이블, Pydantic 모델, Alembic 마이그레이션. CRUD helper는 `src/cards/`
신규 모듈.

**Depends on**: Phase 1 (entities 테이블 채워져 있어야 FK 가능)

**Driving design decision**: `redesign-2026-05.md` §3 (decision_card schema) + §4 (frontmatter + body 패턴)

**Success Criteria**:
  1. 마이그레이션이 다음 컬럼으로 `decision_cards` 테이블 생성: `card_id PK`, `corp_code FK`,
     `ticker`, `generated_at`, `as_of`, `payload JSONB`, `body_md TEXT`, `status`(active|superseded|invalidated),
     `supersedes FK`, `superseded_by FK`, `expires_at`, `schema_version`.
  2. 인덱스: `(corp_code, status, generated_at DESC)` for "latest active by ticker",
     `(supersedes)` for chain walk, `(expires_at)` for stale-detection job.
  3. `DecisionCard` Pydantic 모델이 §3의 YAML 예제와 round-trip 한다 (`key_claims`, `contradictions`,
     `assumptions`, `invalidation_triggers`, `numeric_facts`, `evidence_weights`, `guards_passed` 모두
     포함).
  4. `src/cards/store.py`에 `save_card(card)`, `get_active(corp_code)`, `walk_supersedes(card_id)`,
     `invalidate(card_id, reason)` helper.
  5. **만료일 + assumptions가 없는 카드는 저장 거부** (Pydantic validator로 강제). Hard veto.
  6. `body_md`은 `pg_trgm`/BM25 인덱스로 fallback 검색 가능.

**Plans**: TBD

---

### Phase 3: MCP Tool Surface (Read-Side)

**Goal**: 타입드 MCP 도구로 삭제된 `src/stock_mcp/`를 대체. FastMCP 2.x 기반. `run_sql` escape hatch
금지.

**Depends on**: Phase 1 (데이터 있음) + Phase 2 (decision_cards 있음)

**Driving design decision**: `redesign-2026-05.md` §2 — "Anthropic Code Execution with MCP 패턴,
타입드 코드 API"

**Success Criteria**:
  1. `src/mcp_v2/` 신규 모듈. FastMCP 2.x stdio 서버. `.mcp.json`이 등록.
  2. 도구 surface (모두 Pydantic 모델 반환, chunk 반환 금지):
     - `get_filing(rcept_no)` — 전체 본문 포함
     - `search_filings(corp_code, event_type?, since?, until?)` — filed_at DESC
     - `ohlcv_range(ticker, from_date, to_date)` — 순수 숫자
     - `flow_range(ticker, from_date, to_date)` — 외국인/기관/공매도
     - `peer_view(corp_code, metric)` — 동종업종 median
     - `hybrid_search(query, source_filter?, date_range?)` — pgvector + BM25 RRF (k=60), **narrative only**
     - `get_note(path)` — `notes/private/` 화이트리스트 read-only
     - `get_decision_card(corp_code, latest=true)` — 기본 `payload`만 반환, `view="both"` 옵션
     - `list_portfolio()` — `notes/private/portfolio.md` 파싱
     - `get_briefing(date, type='daily'|'weekly')` — Phase 5 산출물 조회
  3. `run_sql` 또는 동등한 임의 SQL 실행 도구 **금지** (CI 가드).
  4. `hybrid_search`는 `ohlcv`/`macro_series`/`decision_cards` 같은 *숫자* 테이블 대상 호출
     **금지** — narrative 테이블(`filings.body_md`, `news.body_md`, `notes.content_md`)만.
  5. 모든 도구는 prompt-injection defense (XML delimiter + 패턴 prefilter)를 통과한 본문만 LLM
     pipeline으로 흘려보낸다.

**Plans**: TBD

---

### Phase 4: Analysis Runner (3-role Debate)

**Goal**: Bull / Bear / Judge 서브에이전트 orchestration → `decision_card` 생성. 숫자 사실은
원문 verbatim checksum.

**Depends on**: Phase 2 + 3

**Driving design decision**: `redesign-2026-05.md` §3 (multi-agent debate as reasoning scaffold) +
hard veto: "AI가 가격 예측 금지, evidence 압축만"

**Success Criteria**:
  1. `src/analysis/runner.py::analyze_ticker(corp_code, as_of)` 호출 → `decision_card` 1개 반환 + Phase 2
     helper로 저장.
  2. 내부 흐름:
     a. MCP 도구로 evidence 수집 (`search_filings`, `flow_range`, `hybrid_search`, `get_note`)
     b. Bull / Bear sub-agent 병렬 spawn (Task 도구; 두 sub-agent는 서로의 출력을 모름)
     c. Judge sub-agent가 양쪽 받아서 rubric 채점 → 최종 카드 emit
  3. **Numeric checksum**: `numeric_facts[]`의 모든 값은 원문 본문에 verbatim 등장해야 함.
     실패 시 해당 fact 드롭 + 카드의 `_warnings`에 기록. Hard veto.
  4. **만료일 + assumptions[] + invalidation_triggers[]** 강제. Pydantic이 거부.
  5. **Contradictions[]** 가 빈 카드는 의심해야 함 — log warning.
  6. **Stance change 게이트**: 어제 카드와 같은 stance면 3-role debate 스킵하고 lightweight
     refresh(`as_of`만 업데이트, `key_claims`/`contradictions` 재확인). 토큰 절약.
  7. 모든 단계의 비용·시간 로깅 (Phase 9에서 quota 분석 재료).

**Plans**: TBD

---

### Phase 5: Briefing Renderer

**Goal**: 일/주 top-N 변화 요약. "바뀐 종목만" — per-ticker dump 금지.

**Depends on**: Phase 4

**Driving design decision**: `redesign-2026-05.md` §5 — "AlphaSense Workflow Agent + Bloomberg AI
Summary 패턴: 바뀐 것만, 최대 10개"

**Success Criteria**:
  1. `src/briefing/daily.py::generate_daily_briefing(date)` 가 다음을 모은다:
     - stance 변경된 카드
     - 새로 발견된 contradictions
     - 만료/invalidated 된 카드
     - 새 high-conviction(≥0.8) 카드
     - 최대 10개 entry, 우선순위 정렬
  2. 결과는 `decision_cards`에 `report_type='daily_briefing'` row로 저장 (payload + body_md).
  3. body_md는 표 형식 (`종목 | 변화 | 근거 | 제안 | Why now | Why not`).
  4. 주간 브리핑은 `weekly_briefing` row + `source_reports: [daily_briefing × 7]` — pre-materialize,
     read 시 재계산 금지.
  5. MCP `get_briefing(date, type)` 도구로 조회 가능.
  6. **만약 변화 없으면** 짧은 "no significant changes today" 카드만. 만들지 않거나 빈 페이지
     렌더 X.

**Plans**: TBD

---

### Phase 6: Paper-Trade Action Layer

**Goal**: Gates A–D + KIS 모의 API. 신규 전략은 ≥30일 paper shadow 후 promotion 가능.

**Depends on**: Phase 4

**Driving design decision**: `redesign-2026-05.md` §3 — "Auto-trade gating, Composer + QuantConnect
패턴", hard veto: "circuit breaker 없는 LLM auto-trade 금지"

**Success Criteria**:
  1. `src/action/gate.py::evaluate(card) -> ApprovedOrder | RejectedReason` — 모든 게이트 통과 시에만
     주문 생성:
     - **Gate A (deterministic, LLM 아님)**: 포지션 ≤ 2% portfolio, 일일 realized loss < 2%, no
       earnings blackout, ticker 서킷브레이커 통과, KIS rate-limit headroom (≤15 req/s 여유, 20
       req/s 한도의 75%).
     - **Gate B (card freshness)**: 카드 age ≤ 24h, conviction ≥ 0.8, unresolved
       contradictions 없음.
     - **Gate C (human kill switch)**: `notes/private/portfolio.md`의
       `auto_trade_enabled[ticker]: true` 가 명시되어 있을 때만. 기본값 false.
     - **Gate D (paper shadow)**: 해당 전략이 paper 모드로 ≥30일 + 실현 Sharpe ≥ X (threshold는
       Phase 8 결정) 만족해야 live 가능. 기본값은 paper 모드.
  2. KIS 모의 API 클라이언트 (`src/action/kis_paper.py`). 실제 주문 X. P&L tracking 테이블
     (`paper_orders`).
  3. 모든 거부 사유는 audit log (`action_log` 테이블) — `(timestamp, card_id, gate, reason, payload)`.
  4. CLI: `stock action evaluate --card=<card_id>` (dry-run), `stock action run --date=today`
     (daily batch).
  5. 거부된 카드는 다음 daily briefing의 "검토 후 거부" 섹션에 포함.

**Plans**: TBD

---

### Phase 7: Live Trade Promotion

**Goal**: paper 성과가 promotion threshold 통과한 ticker에 한해 실거래 KIS API 연동. Kill switch
latency <5s.

**Depends on**: Phase 6 + ≥30일 paper 데이터

**Driving design decision**: `redesign-2026-05.md` §3 — "Gate D: paper-trade shadow ≥30일", hard
veto: "Eurekahedge AI 인덱스 underperformance — 검증 없이 live 금지"

**Success Criteria**:
  1. `src/action/promotion.py::can_promote_to_live(ticker, strategy_id)` 가 통계적 유의성 검정 통과
     판정 (Sharpe + 신뢰구간; threshold는 Phase 8 backtest 결과 기반).
  2. KIS 실거래 API 클라이언트 (`src/action/kis_live.py`). API 키는 `.env`.
  3. **모든 실거래 호출은 idempotent**: 동일 `client_order_id`로 재호출 시 중복 주문 X.
  4. **Kill switch latency**: `notes/private/portfolio.md`의 토글 변경 → 다음 daily batch 시점에
     반영 + 진행 중인 미체결 주문 즉시 cancel API 호출. p95 ≤ 5초.
  5. 실거래 audit log에 KIS 응답 raw 저장.
  6. **Promotion 후에도 paper shadow 병행** — paper와 live 모두 기록, 분기 결과 비교.

**Plans**: TBD

---

### Phase 8: Evaluation Harness

**Goal**: CPCV+embargo 백테스트 + Sonnet KR 금융 정확도 보정 평가.

**Depends on**: Phase 4 (decision_cards 누적 데이터)

**Driving design decision**: `redesign-2026-05.md` §3 — "CPCV로만 백테스트, walk-forward 단독
금지" + 한국 PEAD anomaly 검증

**Success Criteria**:
  1. `src/eval/cpcv.py` — Combinatorial Purged Cross-Validation 구현. Purge + 5-day embargo (T+2
     settlement + 3일 buffer).
  2. 백테스트 출력: 각 fold별 Sharpe + 95% 신뢰구간. **신뢰구간이 0 포함하면 promotion 거부.**
  3. Sonnet 4.x KR 금융 정확도 eval:
     - 보유 DART 본문 N개 + ground-truth `numeric_facts` 페어
     - Sonnet 추출 결과 vs ground truth → precision/recall, digit-level accuracy
     - 80% 미만이면 prompt 조정 / 모델 업그레이드 트리거
  4. 한국 PEAD anomaly 측정: 보유 corpus의 어닝 발표 이벤트 + 후속 N일 OHLCV로 surprise →
     drift 회귀. magnitude + significance 리포트.
  5. 모든 평가 결과는 `.planning/eval/` 디렉토리에 timestamped Markdown으로 저장. 재현 가능한
     seed 명시.
  6. CI에 `pytest -m "eval"` 단독 runner — 매일 자동 X (비용), PR/release 게이트에서만.

**Plans**: TBD

---

### Phase 9: Ops Hardening

**Goal**: Routine 스케줄 + 운영 모니터링 + 알람.

**Depends on**: Phase 4–7

**Driving design decision**: 운영 안정성. 'AI는 silent failure가 가장 위험'.

**Success Criteria**:
  1. Daily routine: 수집(collect all) → 분석(analyze top-priority tickers) → 브리핑 → paper action
     evaluate. systemd.timer 또는 Claude Schedule routine.
  2. Routine 실패 시 알람 (Slack webhook 또는 이메일).
  3. **모순율 대시보드**: 카드별 `contradictions[]` 카운트 추이. 갑자기 0개가 늘면 — Bull/Bear
     debate가 약해진 신호.
  4. **전제 만료 알람**: `expires_at < now() + 7d` 카드 리스트를 일일 브리핑 상단에 노출.
  5. **KIS rate-limit headroom 모니터링**: 일일 max 사용률 + 임계값(80%) 도달 시 alert.
  6. **Schedule quota 모니터링**: Claude Schedule API 사용량 일일 리포트 (Max 한도 대비).
  7. Stale stub (Phase 1의 heartbeat 같은) 발견 시 CI fail.

**Plans**: TBD

---

## v1.0 (Archived)

v1.0의 11 phase는 `archive/llm-wiki-2026-04` 브랜치 + `pre-llm-wiki-shutdown` 태그에 보존됨.
`.planning/phases/` 디렉토리에 plan 파일들이 historical reference로 남아있다 — v2.0 phase 번호와
혼동 주의.

복구 필요시:
```bash
git checkout archive/llm-wiki-2026-04
# 또는 특정 plan만:
git show archive/llm-wiki-2026-04:.planning/phases/01-load-bearing-foundation/01-01-PLAN.md
```
