# Phase 10: Decision-context coverage — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-26
**Phase:** 10-decision-context-coverage-peer-historical-valuation-supply-d
**Areas discussed:** Scope/Success, Sector & Valuation pipeline, Historical bands, Supply-demand signals, Private notes, MCP tool contracts

---

## Phase Boundary & Success

| Question | Options | Selected |
|----------|---------|----------|
| Phase 10 surfaces in scope | Peer / Historical / Supply-demand / Private notes (multi-select) | All 4 (with "섹터 내 top 10 비교" clarification) |
| 1차 사용자 시나리오 | "X 비싼가?" / "X 큰손?" / "X 매수?" 통합 4축 / 메모 인프라 우선 | "X 매수해야 하나?" 통합 4축 (밸류+수급+공시+메모) |

**Notes:** 사용자 명시 — 동종업계가 아닌 sector top 10 광범위 비교, get_ticker_overview가 4축을 모두 합치는 single tool 답변.

---

## Area 1: Sector + Valuation Pipeline

| Question | Options | Selected |
|----------|---------|----------|
| 섹터 분류 체계 | KRX 업종 / FICS·WICS / 사용자 커스텀 / KRX + custom overlay | KRX 업종 (기본) |
| 섹터 분류 입도 | 소분류 기본 / 대분류 기본 / 소분류→대분류 fallback | 소분류 기본 |
| Top 10 선정 기준 | 시총 / 시총+관심 강제 / 시총+거래대금 / 컨센 커버리지 | 시가총액 단순 상위 10개 |
| 추적 멀티플 세트 | PER+PBR / +EV-EBITDA+배당 / +PSR+배당 / 5개 모두 | 5개 모두 (PER·PBR·EV/EBITDA·PSR·배당수익률) |
| 데이터 소스/계산 주체 | dart-fss 자체 / 네이버 스크래이핑 / Hybrid / MCP 온디맨드 | Hybrid (관심=dart-fss, 피어=네이버) |
| 산출물 저장 위치 | ticker 일별 스냅샷 / sector 일별 / ticker append | sector 일별 (vault/raw/valuation/{sector_code}/{date}.md) |

---

## Area 2: Historical Bands & Storage

| Question | Options | Selected |
|----------|---------|----------|
| Lookback 기간 | 5y / 10y / 3y | 5년 |
| Backfill 전략 | 일회성 스크립트 / 누적만 / 네이버 스크래이핑 | 일회성 스크립트 (종가 × 시점 EPS/BPS) |
| Ticker 관점 도출 | MCP 온디맨드 / ingest hub 파일 / DB 테이블 | DB valuation_snapshots 테이블 |
| 분기 EPS 갱신 동기화 | 과거 불변 / 정정 시 재계산 / Hybrid TTM 롤오버 | 정정 시 해당 그룹 재계산 + 재작성 플래그 |

---

## Area 3: Supply-Demand Signals

| Question | Options | Selected |
|----------|---------|----------|
| 신호 종류 (multi) | net buy 윈도우 / streak / z-score / 공매도·대차 잔고 | 4개 모두 |
| 계산 주체·저장 | ingest 시 vault / DB 테이블 / MCP 온디맨드 | DB supply_demand_signals + MCP SQL |
| 임계값 정책 | 고정 / 티커별 적응 / threshold 없음 raw만 | 티커별 적응 (자체 변동성 대비) |

---

## Area 4: Private Notes Scaffold

| Question | Options | Selected |
|----------|---------|----------|
| 폴더 구조 | ticker 중심 / 메모 종류 중심 / Hybrid (ticker + journal) | Hybrid |
| Phase 8과의 분업 | Phase 8 제거·private 통합 / 명확 차별화 / Phase 8=템플릿+Phase 10=콘텐츠 overlay | Phase 8=템플릿·스키마, Phase 10=콘텐츠 private overlay |
| MCP 노출 정책 | overview 자동 포함 / 별도 툴 / include_private flag | overview 자동 포함 (private_thesis 섹션 기본 하단) |
| Claude 쓰기 권한 | add_note로 private 쓸 수 있음 / 읽기 전용 / append-only | add_note로 private 쓸 수 있음 (일기·대화 자동 적재) |

---

## Bonus Area: MCP Tool Contracts

| Question | Options | Selected |
|----------|---------|----------|
| 툴 구조 | overview 확장 / 신규 3개 분리 / Hybrid drill-down | 신규 툴 분리 (get_valuation_context, get_supply_demand_signals, get_private_thesis) |
| Valuation 응답 스키마 | full(current+top10+5y bands) / current+top10만 / current+percentile만 | Full (current+sector_top10+historical_5y 퍼센타일까지) |
| Supply-demand 응답 스키마 | window×investor full / 활성 신호 강조 / latest+sparkline | Window 테이블 × 투자자 + streak + z-score + 공매도/대차 (full) |

---

## Claude's Discretion

본 페이즈에서 사용자가 명시 결정 — Claude 재량 영역 제한적. Adaptive threshold 알고리즘 세부(rolling 윈도우 길이 252일, σ 임계 2.0, percentile 95) 정도가 코드 단계 재량. KRX 업종 분류 코드 캐싱 전략·정규화 헬퍼 구현 방식도 Claude 재량.

## Deferred Ideas

본 페이즈 논의 중 명시적으로 v2/Out-of-scope로 분류된 것은 CONTEXT.md `<deferred>` 참조. 9건 deferred(threshold 튜닝, 거래대금 가중, 다중 사용자 격리, FICS/WICS, 공매도 직접 API, Phase 8 디렉토리 재배치, adaptive threshold 헬퍼 추출, PDF 리포트 valuation, JUDGE-06 가중치).
