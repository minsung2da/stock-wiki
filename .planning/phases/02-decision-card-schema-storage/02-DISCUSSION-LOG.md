# Phase 2 Discussion Log — Decision Card Schema & Storage

**Date:** 2026-05-29
**Command:** `/gsd-discuss-phase 2`
**Mode:** default (4-area, single-question turns)

이 로그는 인간 참고용입니다 — 감사·회고용. Downstream agents(researcher, planner)는
`02-CONTEXT.md`만 읽습니다.

---

## Gray Area Selection

**Presented gray areas (4):**
1. 페이로드 구조 (JSONB vs 하이브리드)
2. Validator 강제 범위 (Hard Veto 경계)
3. body_md fallback 검색 인덱스
4. Phase 5 report 레코드 호환성

**User selected:** 4개 모두.

---

## Area 1 — Payload Structure

### Q1.1: decision.stance / decision.conviction 접근 방식

- **Options presented:**
  - Pure JSONB + expression 인덱스 (Recommended)
  - Hybrid — stance·conviction을 typed 컬럼으로 승격
  - Hybrid — decision 전부 승격 (stance, conviction, horizon_days, price_ref)
- **Selected:** Pure JSONB + expression 인덱스.
- **Rationale (User-stated/implicit):** ROADMAP SC#1 컬럼 lock과 일치, schema_version
  bump 시 유연함, redesign §4 anti-pattern #1 정신.

### Q1.2: JSONB expression 인덱스를 몇 개까지 선투입할까

- **Options presented:**
  - ROADMAP SC#2 3개에 한정 (Recommended)
  - SC#2 + stance 인덱스
  - SC#2 + stance + conviction 인덱스
- **Selected:** "이 주제 마이그레이션 속에서·planner에게 위임" (Other).
- **Resolution:** Planner discretion으로 분류. CONTEXT.md `<decisions>` Area 1 + Planner
  Discretion 섹션에 기록.
- **Mid-flow clarification:** 사용자가 "무슨 의미인지 설명필요" 응답 → JSONB expression
  index 개념·trade-off 설명 → 재질문 → 위임 선택.

---

## Area 2 — Validator 강제 범위

### Q2.1: save_card() 거부 조건을 어디까지 조일까

- **Options presented:**
  - ROADMAP SC#5 그대로 (최소)
  - +invalidation_triggers ≥1
  - +invalidation_triggers + key_claims ≥1
  - Max strict (+evidence_weights.sentiment != HIGH)
- **Selected:** ROADMAP SC#5 그대로.
- **Rationale (Claude's framing):** Phase 4 analysis runner가 빈 카드를 emit할 가능성
  낮음. validator는 시스템 contract 강제용이지 비즈니스 로직 강제용이 아님.

---

## Area 3 — body_md fallback 검색 인덱스

### Q3.1: 인덱스 종류 선택

- **Options presented:**
  - body_tsv (BM25)만 (Recommended)
  - pg_trgm only
  - body_tsv + body_embedding halfvec(1024)
  - body_tsv + pg_trgm 둘 다
- **Selected:** body_tsv (BM25)만.
- **Rationale:** Phase 1 filings/news 패턴 일치, mecab-ko 토크나이제이션, SC#6 'BM25'
  요건 충족, body_embedding은 필요해지면 ALTER TABLE.
- **Mid-flow clarification:** 사용자가 "무슨 의미인지?" 응답 → body_md 컬럼·fallback
  검색·3가지 인덱스 종류(pg_trgm vs BM25 vs embedding) 비교 설명 → 재질문 → body_tsv
  only 선택.

### Q3.2: body_tsv 채우는 방식

- **Options presented:**
  - GENERATED ALWAYS AS STORED (Recommended)
  - BEFORE INSERT 트리거
  - 앱 레이어 (src/cards/store.py)
  - Phase 1과 동일 전략 조사 후 일치
- **Selected:** GENERATED ALWAYS AS STORED.
- **Rationale:** DB가 INSERT/UPDATE 시점 자동 계산, 앱 코드는 body_md만 쓰면 됨, 외부 SQL
  도구 INSERT도 안전, 트리거의 hidden state 회피.
- **Follow-up note:** 실제 사용할 tsearch config(`'korean'` / `'simple'` / VectorChord 특화)
  는 planner discretion — Phase 1 패턴 일치 우선.

---

## Area 4 — Phase 5 briefing row 호환성

### Q4.1: Phase 5용 컬럼을 Phase 2에서 선투입할까

- **Options presented:**
  - report_type만 선투입 (Recommended)
  - Phase 2는 SC#1 그대로 — Phase 5가 ALTER TABLE
  - report_type + source_reports 둘 다
  - Pydantic은 report_type 필드 설계 + DB는 Phase 5
- **Selected:** Phase 2는 SC#1 그대로 — Phase 5가 ALTER TABLE.
- **Rationale (User-implicit):** ROADMAP 계약 정확 일치, Phase 2 범위 엄격 관리.
  Phase 5에서 (a) report_type 추가, (b) backfill 'ticker_card', (c) NOT NULL 3단계
  마이그레이션 필요 — CONTEXT.md에 명시.

---

## Wrap-up — 2차 그레이 에어리어

### Q5.1: 남은 5개 implementation detail 처리

- **Surfaced areas:**
  1. status enum 표현 (Postgres ENUM vs TEXT+CHECK)
  2. Supersession 원자성 (트랜잭션 범위)
  3. src/cards/ 모듈 구조
  4. CRUD helper 반환 타입
  5. schema_version 표현 + translator scaffold 시점
- **Options presented:**
  - 모두 planner·researcher에게 위임 (Recommended)
  - status enum 표현만 논의
  - src/cards/ 모듈 구조만 논의
  - schema_version 전략만 논의
- **Selected:** 모두 planner·researcher에게 위임.
- **Result:** CONTEXT.md `<decisions>` 끝 "Planner Discretion" 섹션에 5개 모두 명시 +
  Phase 1 패턴 참조 추천 (`src/db/entity_models.py`, `0006_phase01_domain_tables.py`의
  `ck_events_source` CheckConstraint 패턴).

---

## Scope Creep / Out-of-Scope (Noted)

논의 중 사용자가 요청하거나 surface된 *Phase 2 범위 밖* 항목:

- (없음) — 사용자가 scope creep 시도하지 않음. 모든 선택이 SC 잠금 범위 안에서 일관.

## Deferred Ideas (recorded in CONTEXT.md)

- JSONB expression idx (stance, conviction) — Phase 5 briefing 실측 시
- decision_cards.body_embedding halfvec(1024) — Phase 4 이후 필요 시
- schema_version v1→v2 translator scaffold — v2 도입 시점
- CheckConstraint vs Postgres ENUM 표준화 ADR — Phase 9 ops hardening

---

## Decision Summary (4-line digest)

1. **Payload** = pure JSONB; expression idx 스코프는 planner discretion.
2. **Validator** = ROADMAP SC#5 최소 (expires_at + assumptions ≥ 1).
3. **Body search** = `body_tsv TSVECTOR GENERATED ALWAYS AS STORED`만 추가 (Phase 1 mirror).
4. **Phase 5 호환** = Phase 2는 SC#1 정확 일치, Phase 5가 ALTER TABLE 책임.

---

*Generated: 2026-05-29 / `/gsd-discuss-phase 2`*
