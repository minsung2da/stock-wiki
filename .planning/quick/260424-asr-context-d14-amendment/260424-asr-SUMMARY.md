---
type: quick
task: CONTEXT D-14 Option D amendment
completed: 2026-04-24
resolves: Gap-04-02
---

# Quick: CONTEXT.md D-14 Option D 반영

## 배경

Plan 04-05 실행 중 operator-approved 전략 변경 (Option D: pykrx 폐기 → DART `pblntf_ty="I"` 3종 + KIND 스크레이핑 1종)은 04-05-SUMMARY에만 기록돼 있었고, CONTEXT.md D-14 본문은 여전히 pre-execution pykrx 하이브리드로 남아있었음. Phase 4 VERIFICATION에서 Gap-04-02로 기록.

## 변경

`.planning/phases/04-multi-source-collector-coverage/04-CONTEXT.md` D-14 섹션을 갱신:

- **주요 소스**: DART 거래소공시(`pblntf_ty="I"`) — `suspension`/`watchlist_designation`/`unfaithful_disclosure` 3종을 `report_nm` 정규식으로 분류
- **보조 소스**: KIND 스크레이핑(`/investwarn/investattentwarnrisky.do`) — `investment_caution`/`investment_risk` 전용
- **교차확증**: KRX OHLCV 거래량=0 → `heartbeat.extra.suspension_cross_check_mismatch`
- **pykrx 폐기 근거**: 함수 부재 live 검증(2026-04-20 pykrx 1.0.51 + GitHub master)
- **개념 축 근거**: 거래소 상태 지정 = 기업평가(fundamental) 축 → DART+KIND. pykrx = 시장가격(market behavior) 축 전용.
- **정규식 위치**: `src/collectors/kind/sources.py::DART_EXCHANGE_EVENT_PATTERNS`

## 파일

- `.planning/phases/04-multi-source-collector-coverage/04-CONTEXT.md` — D-14 본문 재작성
- `.planning/phases/04-multi-source-collector-coverage/04-HUMAN-UAT.md` — Gap-04-02 status `documentation` → `resolved`

## 후속

남은 gap 없음. Phase 4 `04-HUMAN-UAT.md`의 모든 gap은 resolved 또는 deferred(V2-KIND-01 백로그).
