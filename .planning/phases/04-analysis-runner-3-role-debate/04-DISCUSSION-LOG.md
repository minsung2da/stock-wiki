# Phase 4: Analysis Runner (3-role Debate) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-25
**Phase:** 4-analysis-runner-3-role-debate
**Areas discussed:** Sub-agent 실행 방식, Evidence 수집 경계, 숫자 checksum 방식, Stance 게이트 정의

---

## Sub-agent 실행 방식

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid adapter | runner 순수 Python + LLM 호출만 DebateBackend Protocol 뒤로(TaskTool/ClaudeCLI/Fake) | |
| 헤드리스 claude CLI | runner.py가 `claude` CLI를 subprocess로 호출하는 순수 Python callable, Max 구독 auth | ✓ |
| 세션 Task tool recipe | analyze_ticker = Claude Code 세션이 실행하는 recipe, Task tool로 spawn(redesign §3 원안) | |

**User's choice:** 헤드리스 claude CLI
**Notes:** 사용자가 옵션 차이를 이해하기 위해 두 차례 설명 요청 → 주방 비유(누가 오케스트레이터냐:
Python vs Claude 세션)로 설명. 핵심 결정 기준 = 무인 자동 실행(Phase 9) + 테스트성(Phase 8).
제약: `CLAUDE.md` "자체 LLM 호출 X / Claude Code 경유" → API 직호출 배제, 세 옵션 모두 Max 구독.
redesign §3 "via Task tool"은 in-session 가정으로 해석, headless로 대체.

---

## Evidence 수집 경계

| Option | Description | Selected |
|--------|-------------|----------|
| 고정 번들 미리 수집 | runner가 MCP 도구로 evidence 한 묶음 모아 Bull/Bear/Judge에 동일 주입 | ✓ |
| 에이전트가 직접 호출 | 각 sub-agent가 필요 시 MCP 도구를 스스로 호출 | |
| 하이브리드 | 핵심 번들 미리 + 부족분만 추가 도구 호출 허용 | |

**User's choice:** 고정 번들 미리 수집 (A)
**Notes:** MCP 도구(search_filings/get_filing/ohlcv_range/flow_range/peer_view/hybrid_search/
get_note)와 Bull/Bear/Judge 역할을 도서관 사서/요리사 비유로 설명 요청. 선택 근거 = 재현성·공정
토론·숫자검증 용이, redesign §3/SC#2a 순서와 일치.

---

## 숫자 checksum 방식

| Option | Description | Selected |
|--------|-------------|----------|
| 한국식 단위까지 정규화 | 콤마 제거 + 억·조·% 단위 변환 후 '값'으로 대조 | ✓ |
| 정확히 그대로만 | 원문에 글자 그대로 나와야만 인정(exact string) | |
| 정확 우선 + 정규화 fallback | exact 먼저, 실패 시 정규화 재비교 | |

**User's choice:** 한국식 단위까지 정규화
**Notes:** 한국 표기 다양성(42.5조원 = 42,500,000,000,000 = 425000억) 때문에 exact-only는 멀쩡한
값 대량 drop 위험. 실패 시 drop + `_warnings`는 SC#3 lock. Toss numeric checksum 선례.

---

## Stance 게이트 정의

| Option | Description | Selected |
|--------|-------------|----------|
| 변화가 생겼을 때만 | 새 공시·이벤트/가격·수급 급변/만료/전제깨짐 시 풀토론, 그 외 가벼운 갱신 | |
| 정해진 주기마다 | N일마다 무조건 풀토론, 사이엔 가벼운 갱신 | |
| 변화 기반 + 주기 안전망 | 변화 시 즉시 풀토론 + 변화 없어도 N일 경과 시 1회 풀토론 | ✓ |

**User's choice:** 변화 기반 + 주기 안전망 (C)
**Notes:** 이벤트 중심(PEAD) 프로젝트라 변화 기반이 자연스럽되, 오래 잠잠해도 thesis가 곪지 않게
주기 안전망 추가. lightweight refresh = as_of 갱신 + 근거/전제 유효성 재점검(AI 풀토론 X), SC#6.

---

## Claude's Discretion

planner/researcher 위임 (CONTEXT.md `<decisions>` Claude's Discretion 1-9 참조):
Judge 루브릭→conviction/stance 매핑(Veto #4), sub-agent JSON 출력 스키마, EvidenceBundle 스키마,
숫자 정규화 규칙 세트, stance 게이트 구체 임계치/주기 N, SC#7 비용·시간 로깅 형태, save_card
supersession 연결, empty contradictions 경고, as_of 산출 방식.

## Deferred Ideas

- guards_passed 실제 게이트 평가 → Phase 6 (Phase 4는 필드만)
- briefing 생성 → Phase 5
- CPCV 백테스트 + Sonnet KR 정확도 eval → Phase 8
- daily routine/모순율 대시보드/전제 만료 알람 → Phase 9
- KIS auto-trade(주문) → Phase 6-7
- Open Q4 토큰 이코노믹스 실측 종합 → 구현 후 Phase 9 quota 분석
