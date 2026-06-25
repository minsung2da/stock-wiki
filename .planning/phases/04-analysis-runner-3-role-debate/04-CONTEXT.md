# Phase 4: Analysis Runner (3-role Debate) - Context

**Gathered:** 2026-06-25
**Status:** Ready for planning
**Source:** discuss-phase (gsd-discuss-phase 4)

<domain>
## Phase Boundary

`src/analysis/runner.py::analyze_ticker(corp_code, as_of)` — 한 종목에 대해 MCP 도구로
evidence를 수집하고 Bull/Bear/Judge 3-role Sonnet sub-agent를 거쳐 **`decision_card` 1개**를
생성하고 Phase 2 store helper로 저장한다. AI는 **가격을 예측하지 않고 evidence를 압축**한다
(Veto #1). `src/analysis/`는 신규 모듈(현재 없음).

이 phase는 **WHAT**(3-role 구성, numeric checksum 강제, 만료·assumptions·invalidation 강제,
contradictions 1급 출력, stance-change 토큰 게이트, 단계별 비용 로깅)을 ROADMAP SC#1-7 +
redesign §3에서 lock으로 받고, **HOW**(sub-agent 실행 방식, evidence 수집 경계, checksum 정규화
방식, stance 게이트 트리거)를 이 CONTEXT.md에서 결정한다.

Depends on Phase 2 (`decision_cards` + `src/cards/store`) + Phase 3 (MCP read-side 도구).
</domain>

<decisions>
## Implementation Decisions

### 영역 1 — Sub-agent 실행 방식

- **D-01: 헤드리스 `claude` CLI (순수 Python callable).** `analyze_ticker`는 일반 Python
  함수로, 내부에서 `claude` CLI를 **subprocess**로 호출해 Bull/Bear(병렬)·Judge sub-agent를
  spawn한다. **Max 구독 auth 경유** — Anthropic API 직호출 금지(`CLAUDE.md` Tech Stack:
  "Analysis brain = Sonnet via Claude Code, 자체 LLM 호출 X"). 세션 비종속이므로 pytest·일배치·
  Schedule에서 직접 호출 가능.
- **근거:** Phase 8(eval)·Phase 9(daily routine)이 **무인 실행 + 테스트성**을 요구한다. runner가
  순수 callable이어야 자동 배치/CPCV/유닛테스트가 가능. redesign §3 line 303 "via Task tool"은
  *사람이 세션에 붙어 쓴다*는 가정이었으므로, 동일하게 Max 구독을 쓰되 headless CLI로 대체한다
  (비용 모델 동일, 오케스트레이터만 Claude 세션 → Python으로 이동). Open Q4(토큰/quota 적합성)는
  구현 후 실측해 Phase 9 quota 분석에 넘긴다.
- **시사 (planner/researcher 결정):** (a) `claude -p` 호출 방식 + **구조화 출력 강제**(JSON),
  (b) Bull/Bear 병렬 subprocess 관리(asyncio/concurrent.futures), (c) Max 구독 로그인 상태 전제 +
  auth 실패 처리, (d) per-call timeout/재시도, (e) Claude Agent SDK vs raw `claude -p` 적합성은
  researcher가 조사.

### 영역 2 — Evidence 수집 경계

- **D-02: 고정 번들 미리 수집(pre-fetch).** runner가 먼저 **in-process MCP 도구**
  (`search_filings`/`get_filing`/`ohlcv_range`/`flow_range`/`peer_view`/`hybrid_search`/`get_note`)로
  evidence를 모아 한 묶음(`EvidenceBundle`)으로 만들고, **Bull/Bear/Judge 모두 같은 번들**을 받는다.
  sub-agent는 도구를 직접 호출하지 않는다.
- **근거:** ① 재현성(동일 입력→동일 카드 — Phase 8 eval/CPCV에 필수), ② 공정한 토론(SC#2b:
  Bull/Bear가 서로 blind이되 **같은 사실**을 두고 다툼), ③ numeric checksum 용이(원문이 손에
  있어 verbatim 대조 쉬움). redesign §3/ROADMAP SC#2a 순서("(a) 도구로 수집 → (b) Bull/Bear spawn").
- **시사:** MCP 도구는 Phase 3(03-04)에서 in-process plain callable로 호출 가능. `EvidenceBundle`
  스키마(포함 도구·종목당 수집 범위/한도)는 planner 결정. Bull/Bear에 주입되는 narrative 원문은
  D-03(injection wrap)된 상태(`injection.wrap_untrusted`).

### 영역 3 — 숫자 checksum 방식

- **D-03: 한국식 단위 정규화 매치.** `numeric_facts[]` 각 값 검증 시 **콤마 제거 + 억(1e8)·
  조(1e12)·%·원 등 단위 변환** 후 '값'으로 원문 대조한다. 정확 문자열 매치만 요구하지 않는다.
  검증 실패 = 해당 fact **drop + 카드 `_warnings`에 기록**(SC#3, Hard Veto).
- **근거:** 한국 공시·뉴스는 동일 값을 다양하게 표기(`42.5조원` = `42,500,000,000,000` =
  `425000억`). exact-only는 멀쩡한 값을 대량 drop. Toss가 numeric checksum을 특별히 구축한 KR
  선례(redesign §3 line 218, 229).
- **시사:** planner는 (a) 정규화 규칙 범위(허용 단위·표기), (b) 부동소수 허용오차(반올림 표기 vs
  원값), (c) 검증 위치(**deterministic Python post-validation, AI 거치지 않음**)를 결정. 보수적
  원칙 — 원문에서 도출 불가한 값은 인정 금지(Veto: "실패 = drop the fact").

### 영역 4 — Stance 게이트 정의

- **D-04: 변화 기반 + 주기 안전망.** full 3-role debate 트리거(하나라도 충족 시):
  ① 마지막 카드 이후 **새 공시·이벤트**, ② **가격·수급 급변**(임계치), ③ 카드 **만료/만료임박**
  (`expires_at`), ④ **전제(assumption) 깨짐 / `invalidation_trigger` 발동**. 트리거 없으면
  **lightweight refresh**(`as_of` 갱신 + `key_claims`/`contradictions`/`assumptions` 유효성
  재점검, **AI 풀토론 X**). 추가로 변화 없어도 **N일 경과 시 1회 풀토론**(주기 안전망).
  '어제 카드' = corp_code의 최신 active 카드(`store.get_active`).
- **근거:** 이 프로젝트는 event-driven(PEAD) — 사건이 터질 때 다시 깊게 본다. steady-state HOLD
  재실행에 풀토론을 돌리지 않는 것이 토큰 이코노믹스 게이트(redesign §3 line 303, SC#6). 주기
  안전망은 "오래 잠잠해 trigger가 안 떠도 thesis가 곪지 않게" 하는 보수 장치.
- **시사:** planner는 (a) 가격·수급 급변 임계치, (b) 만료임박 윈도우(예: D-7), (c) 안전망 주기 N,
  (d) lightweight refresh가 재계산하는 정확 필드 집합, (e) refresh 중 material shift 감지 시 full로
  **에스컬레이션** 여부를 결정. **같은 stance인데 conviction이 크게 변하는** 케이스는 refresh의
  재점검에서 포착 → 필요 시 full로 에스컬레이션.

### Claude's Discretion (planner / researcher 위임)

사용자 선호 없음 — RESEARCH best-practice + 코드 패턴 확인 후 planner 결정:

1. **Judge 루브릭 → 카드 매핑**: 0–10 점수(fundamentals/catalyst presence/contradiction count/
   thesis freshness/position-sizing fit)를 카드 `conviction`(0–1) + `stance`로 변환하는 방식.
   **Veto #4(black-box 금지)**: 점수는 cited evidence item으로 decompose 가능해야 함.
2. **sub-agent 출력 구조(JSON 스키마)** — Bull/Bear/Judge 각 출력을 Judge·Python 레이어가
   소비하도록 구조화. `claude -p`에서 구조화 출력을 강제하는 방식(스키마/프롬프트).
3. **`EvidenceBundle` 스키마** + 종목당 수집 도구·범위·한도.
4. **한국식 숫자 정규화 규칙 세트** + 허용오차(D-03 디테일).
5. **stance 게이트 구체값** — 가격·수급 급변 임계치, 만료임박 윈도우, 안전망 주기 N,
   refresh 재계산 필드, 에스컬레이션 규칙(D-04 디테일).
6. **비용·시간 로깅 형태(SC#7)** — Phase 1 `shared/run_log.py` dual-sink 재사용 vs 신규 테이블 vs
   구조화 stderr. Phase 9 quota 분석 재료.
7. **저장·supersession 연결** — `analyze_ticker`가 `store.save_card`로 저장하고 이전 active 카드를
   supersede 처리하는 방식(Phase 2 `store.save_card`/`walk_supersedes` atomic supersession 재사용).
8. **empty `contradictions[]` 경고 로깅(SC#5)** 위치/형태 — "모순 0개 카드는 의심" warning.
9. **`as_of`(데이터 컷오프, KST close) 결정** 방식 — 호출자 지정 vs 자동 산출.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner) MUST read these before acting.**

### Architecture / Design (authoritative)
- `.planning/research/redesign-2026-05.md` §3 (line 205-348) — **PRIMARY.** Analysis methodology:
  `decision_card` schema(line 231-294), multi-agent debate scaffold(line 296-303, Bull/Bear/Judge
  병렬 + Judge 종합, ~30-60s/ticker, actionable 카드에만), hard vetoes(line 326-338), open
  empirical questions(line 340-347 — Q4 토큰 이코노믹스/Schedule quota).
- `.planning/research/redesign-2026-05.md` §1 (line 13-75) — architecture overview.
- `.planning/research/redesign-2026-05.md` §6 (line 443-456) — diagram, 분석이 "4. 분석" 위치.
- `.planning/research/redesign-2026-05.md` §8 Sources (line 485-502) — TradingAgents/FinDebate
  (multi-agent debate), Toss(numeric checksum), CPCV(De Prado).

### Roadmap lock
- `.planning/ROADMAP.md` Phase 4 (line 148-173) — Goal + Depends on + Success Criteria SC#1-7
  (analyze_ticker 시그니처, 내부 흐름 a/b/c, numeric checksum, 만료+assumptions+invalidation,
  empty contradictions warning, stance-change 게이트, 단계별 비용 로깅).

### Project-wide constraints
- `CLAUDE.md` Hard Vetoes — **#1**(AI 가격 예측 금지, evidence 압축만), **#2**(만료일+assumptions[]
  없는 thesis 금지 — Pydantic 강제), **#3**(contradictions[] 1급 출력 — silent 채택 금지),
  **#4**(black-box 점수 금지 — cited evidence로 decompose), **#5**(sentiment 단독 신호 금지 —
  DART/KRX/macro corroborate).
- `CLAUDE.md` Tech Stack — **Analysis brain = Claude Sonnet 4.x via Claude Code, Max subscription,
  자체 LLM 호출 X** (D-01 제약의 출처). Conventions: Python 3.12, strict mypy, Pydantic v2.

### Code to build on / reference
- `src/cards/store.py` — `save_card(engine, card)` / `get_active(engine, corp_code)` /
  `walk_supersedes(...)` / `invalidate(...)`. atomic single-txn supersession. analyze_ticker가
  저장·supersede에 사용.
- `src/cards/models.py` — `DecisionCard` Pydantic 모델(분석 출력 타입; expires_at/assumptions
  non-optional 강제 = Veto #2).
- `src/mcp_v2/tools/{filing,market,search,note}.py` — evidence 수집용 in-process plain callable
  (03-04 노트: `mcp.tool(...)(fn)` call form이라 in-process 호출 가능).
- `src/mcp_v2/injection.py` — `wrap_untrusted()` (Bull/Bear에 주입되는 narrative 원문 D-03 래핑).
- `src/shared/run_log.py` — Phase 1 dual-sink 로깅(SC#7 비용·시간 로깅 후보).

### External docs (researcher 조사 대상)
- Claude Agent SDK / `claude -p` headless CLI — 구조화 출력 강제, 병렬 호출, Max 구독 auth
  (D-01 구현 방식; Anthropic 공식 문서).
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/cards/store.save_card` / `get_active` — 카드 저장 + 최신 active 카드 조회(stance 게이트의
  '어제 카드'). supersession atomic.
- `src/cards/models.DecisionCard` — 분석 출력 타입. `_warnings`(D-03 checksum 실패 기록) 수용
  여부는 Phase 2 모델 확인 필요(필요 시 optional 필드, payload JSONB라 DB 컬럼 무변).
- `src/mcp_v2/tools/*` — evidence 도구. in-process 호출(세션/stdio 불필요).
- `src/mcp_v2/injection.wrap_untrusted` — D-02 번들의 narrative 원문 래핑.
- `src/shared/run_log.py` — SC#7 로깅 재사용 후보.

### Established Patterns
- **Typed Pydantic 반환** + **파라미터화 `text()` SQL**(Veto #7) — 전 phase 공통.
- **strict mypy + Python 3.12 + Pydantic v2.**
- **테스트는 `.venv/Scripts/python.exe -m pytest`** (uv는 Bash PATH에 없음).
- **`claude` CLI는 이 환경 PATH에 있음**(D-01 headless 호출 가능 — researcher가 옵션 확인).

### Integration Points
- `analyze_ticker` 흐름: MCP 도구(read) → `EvidenceBundle` → `claude` CLI sub-agents(Bull/Bear/
  Judge) → numeric checksum → `store.save_card`(write, supersede).
- `src/analysis/` 신규 생성(현재 `src/orchestration/`만 빈 stub 존재).
- Phase 5 briefing이 `decision_cards`를 소비. Phase 6 action layer가 카드 `guards_passed`를 소비.
</code_context>

<specifics>
## Specific Ideas

- **3-role**: Bull/Bear 병렬(서로 blind), Judge가 둘 다 수신 후 종합(SC#2b/c, §3 line 296-303).
- **decision_card 필수 필드**(§3 line 231-294): `stance`(BUY/ADD/HOLD/TRIM/SELL/AVOID) +
  `conviction`(0-1) + `horizon_days` + `invalidation_triggers` + `key_claims`(evidence_refs+weight+
  confidence) + `contradictions` + `assumptions` + `numeric_facts` + `evidence_weights` +
  `guards_passed` + `expires_at`(MANDATORY).
- **목표 ~30-60s/ticker**(§3 line 303).
- **conviction ≥ 0.8은 multi-source corroboration 시에만**(§3 line 245, Veto #5).
- **headless = Max 구독 경유, API 직호출 X**(D-01 / CLAUDE.md).
</specifics>

<deferred>
## Deferred Ideas

논의 중 surface된 비-Phase-4 아이디어 / 후속 phase 의존:

- **`guards_passed` 실제 게이트 평가** — Phase 4는 카드에 **필드만** 채운다(어떤 가드가 통과
  '가능'한지). Gate A-D 실제 평가·차단은 **Phase 6 action layer**.
- **briefing 생성**(top-N 변화 요약) — **Phase 5**. Phase 4는 카드 생성/저장까지만.
- **CPCV+embargo 백테스트 + Sonnet KR 금융 정확도 eval** — **Phase 8**.
- **daily routine 스케줄 + 모순율 대시보드 + 전제 만료 알람** — **Phase 9**.
- **KIS auto-trade(주문)** — **Phase 6-7**.
- **Open Q4 토큰 이코노믹스 실측 종합** — 구현 후 데이터를 Phase 9 quota 분석에서 종합(D-01 SC#7
  로깅이 재료 제공).

### Out of Scope for Phase 4
- 가격 예측 도구/출력(Veto #1)
- action layer 게이트 평가·KIS 주문(Phase 6-7)
- briefing 렌더링(Phase 5)
- 백테스트/eval harness(Phase 8)
- write-side MCP 도구(분석은 `src/cards/store`를 직접 호출, MCP 경유 아님)
</deferred>

---

*Phase: 04-analysis-runner-3-role-debate*
*Context gathered: 2026-06-25 via /gsd-discuss-phase 4*
