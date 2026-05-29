# Phase 2 Context — Decision Card Schema & Storage

**Milestone:** v2.0 (DB-direct redesign)
**Phase slug:** `02-decision-card-schema-storage`
**Status:** discussion complete, awaiting research → plan
**Created:** 2026-05-29
**Source:** discuss-phase (gsd-discuss-phase 2)

<domain>
## Phase Boundary

`decision_cards` 테이블 + Pydantic 모델 + Alembic 마이그레이션 0007. CRUD helper는
`src/cards/` 신규 모듈. **decision_card는 v2.0 분석 출력의 canonical storage**다 —
Phase 3 MCP `get_decision_card`/`get_briefing`, Phase 4 `analyze_ticker` 저장,
Phase 5 briefing row 모두가 이 테이블을 향한다.

Depends on Phase 1 (entities 테이블 채워져 있어야 corp_code FK 가능).

이 phase는 **WHAT(스키마 컬럼 목록, helper 이름)**을 ROADMAP SC#1-#6과 redesign §3 YAML
예제에서 lock으로 받고, **HOW(인덱스 세부·페이로드 분할·validator 강도·검색 인덱스 종류·
Phase 5 호환)**를 이 CONTEXT.md에서 결정한다.
</domain>

<decisions>
## Implementation Decisions

### Payload Structure (영역 1)

- **Pure JSONB payload** — `decision.stance`, `decision.conviction`, `decision.horizon_days`,
  `decision.price_ref`는 typed 컬럼으로 승격하지 **않는다**. 모두 `payload->'decision'->>...`
  경로로 접근. ROADMAP SC#1의 top-level 컬럼 lock과 일치(`expires_at`만 typed로 별도).
- **JSONB expression 인덱스 스코프 = planner discretion.** Phase 2는 ROADMAP SC#2 3개 인덱스
  (`(corp_code,status,generated_at DESC)`, `(supersedes)`, `(expires_at)`)만 의무. JSONB
  expression idx(stance/conviction)는 Phase 5 briefing이 실측 후 결정. YAGNI 우선.
- §4 anti-pattern #1 정신("don't make Claude re-parse Markdown") 보존: `stance`/`conviction`
  은 *payload JSONB* 안에 구조화되어 있어야지 `body_md` Markdown에 묻혀선 안 된다.

### Validator 강제 범위 (영역 2)

- **ROADMAP SC#5 그대로**: Pydantic이 거부할 조건은 두 가지 — `expires_at`이 누락이거나,
  `assumptions[]`가 비어 있을 때.
- `invalidation_triggers`, `contradictions`, `key_claims`, `guards_passed`, `numeric_facts`의
  shape/누락 검증은 Pydantic 타입 시스템에 맡기고 *추가 비즈니스 강제 없음*. Phase 4
  (analysis runner)가 빈 카드를 보내올 가능성이 없으므로 over-engineering 회피.
- `numeric_facts` 디지트 체크섬은 **Phase 4 책임** (analysis runner가 본문 verbatim 검증
  후 카드 emit). Phase 2 Pydantic은 dict shape만 검증.

### Body_md fallback 검색 인덱스 (영역 3)

- **`body_tsv TSVECTOR` 한 개만 추가.** Phase 1 filings/news 패턴과 일치(`body_md TEXT` +
  `body_tsv TSVECTOR`). SC#6의 "BM25 인덱스" 요건 충족.
- **`body_tsv`는 `GENERATED ALWAYS AS (to_tsvector(...)) STORED`로 선언** — DB가
  INSERT/UPDATE 시점에 자동 계산. 앱 레이어가 body_md만 INSERT하면 됨. 외부 SQL이나 다른
  도구가 INSERT해도 누락 없음. 트리거 대신 generated column 선택 이유: 트리거는 숨은
  상태가 디버깅 어려움.
- 사용할 tsearch config(`'korean'` vs `'simple'` vs VectorChord-BM25 tokenizer 특화)는
  **planner discretion** — Phase 1 filings/news가 어떤 config를 쓰는지 RESEARCH 단계에서
  확인 후 동일 패턴.
- **`body_embedding halfvec(1024)`는 Phase 2에서 추가하지 않는다.** decision_cards는
  Phase 3 `hybrid_search` 대상에서 명시적으로 제외됨(narrative 테이블만). 필요해지면
  Phase 4 또는 후속에서 `ALTER TABLE`. pg_trgm 인덱스도 추가하지 않음 — BM25로 충분.

### Phase 5 briefing row 호환성 (영역 4)

- **Phase 2 = ROADMAP SC#1 컬럼 정확 일치.** `report_type`, `source_reports`, briefing-specific
  컬럼은 Phase 2에 *추가하지 않는다*. Phase 5가 자체 ALTER TABLE 마이그레이션으로 추가.
- Phase 2의 `DecisionCard` Pydantic 모델은 **종목별 분석 카드(ticker_card) shape만** 정의.
  Briefing row의 Pydantic은 Phase 5에서 별도 정의(같은 테이블, 다른 schema_version 또는
  다른 model 클래스).
- 이로 인한 부작용: Phase 5는 (a) `report_type` 컬럼 추가, (b) 기존 row backfill
  `'ticker_card'`, (c) NOT NULL constraint 적용 — 3단계 마이그레이션이 필요. Phase 5에서
  감안.

### Planner Discretion (이 phase가 의도적으로 위임하는 결정)

다음 5개 implementation detail은 RESEARCH 단계에서 best practice 확인 후 planner가 결정.
사용자 선호 없음이 명시된 영역:

1. **`status` enum 표현** — Postgres `CREATE TYPE status_t AS ENUM(...)` vs Phase 1 events
   처럼 `TEXT + CheckConstraint`. Phase 1 패턴(`ck_events_source`, `ck_events_event_type`)을
   참조해 일관성 우선 추천.
2. **Supersession 원자성** — `save_card(supersedes=prev_id)` 호출 시 신규 INSERT + 구
   row의 `superseded_by` UPDATE를 단일 트랜잭션 / DB 트리거 / deferred constraint 중 어느
   것으로 보장할지.
3. **`src/cards/` 모듈 구조** — `store.py` 단일 vs `models.py`(Pydantic) + `store.py`(CRUD)
   + `validators.py` 분리. Phase 1 `src/db/entity_models.py` 패턴 참조.
4. **CRUD helper 반환 타입** — `get_active()`이 `DecisionCard` Pydantic 인스턴스 반환 vs
   `(DecisionCard, body_md: str)` 튜플 vs `dict`. Phase 3 MCP `get_decision_card`의
   `view="both"` 옵션과 어떻게 맞물릴지 고려.
5. **`schema_version` 표현 + translator scaffold 시점** — integer (redesign §3 YAML 예시는
   `schema_version: 1`) vs semver string. v1→v2 `migrate_v{n}_to_v{n+1}()` 함수는 Phase 2
   에서 빈 stub만 만들지 vs 실제 v2 도입 시점에 만들지.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner) MUST read these before acting.**

### Architecture / Design (authoritative)
- `.planning/research/redesign-2026-05.md` §3 — decision_card schema, multi-agent debate,
  action layer gates, hard vetoes. **YAML 예시는 Phase 2 Pydantic 모델의 round-trip 기준.**
- `.planning/research/redesign-2026-05.md` §4 — Report format (frontmatter + body, single
  Postgres row); supersession chain pointer pattern; anti-patterns. **`get_decision_card`
  의 payload-only default 근거.**
- `.planning/research/redesign-2026-05.md` §6 — Architecture diagram mapping; decision_cards가
  diagram 5번 위치 ("결과 저장 = decision_cards 테이블 (payload JSONB + body_md TEXT,
  단일 row)").

### Project-wide constraints
- `CLAUDE.md` Hard Vetoes #2 (만료일 + assumptions[] 없는 thesis 저장 금지 — SC#5의 근거),
  #3 (Contradictions[]는 1급 출력), #4 (Black-box 점수 금지), #13 (`get_decision_card`
  default = payload만).
- `CLAUDE.md` Conventions — Python 3.12, type hints (strict mypy), Pydantic v2.

### Phase 1 patterns to mirror
- `.planning/phases/01-collector-db-cutover/CONTEXT.md` — v2.0 phase context 작성 패턴.
- `src/db/migrations/versions/0006_phase01_domain_tables.py` — narrative 테이블 패턴
  (body_md TEXT + body_tsv TSVECTOR + body_embedding halfvec(1024)), CheckConstraint
  enum-like 강제 패턴, halfvec 컬럼 ALTER TABLE 분리 패턴.
- `src/db/entity_models.py` — ORM declarative + `_HalfVec` UserDefinedType 재사용 가능.
- `tests/db/test_migration_0006.py::test_orm_round_trip` (라고 명시된 패턴) — Phase 2도
  ORM↔migration round-trip test 의무.

### Roadmap lock
- `.planning/ROADMAP.md` Phase 2 — Success Criteria 6개 (스키마 컬럼 lock, 인덱스 lock,
  Pydantic round-trip lock, CRUD helper 4개 lock, validator hard veto, fallback 검색).
</canonical_refs>

<specifics>
## Specific Ideas / References

- **Pydantic round-trip 기준**: redesign §3의 YAML 예시 (corp_code "00126380", card_id
  card_005930_2026-05-28). 이 예시를 그대로 fixture로 두고 `DecisionCard.model_validate()`
  → `model_dump()` → 동치 비교 가능해야 함.
- **`expires_at` lock**: `MANDATORY — no untimed thesis` (redesign §3 schema example
  코멘트). Pydantic field는 `expires_at: datetime` (no default, no Optional).
- **`assumptions` lock**: `list[str]`, min_length=1.
- **CRUD helper 4종**: `save_card(card)`, `get_active(corp_code)`, `walk_supersedes(card_id)`,
  `invalidate(card_id, reason)`. 이름·시그니처는 SC#4에 lock.
- **마이그레이션 번호**: 0007 (revises 0006). Phase 1이 0006을 차지.
- **테이블 이름**: `decision_cards` (복수, snake_case — Phase 1 events/news/filings 패턴).
- **`status` enum 값**: `active`, `superseded`, `invalidated` (ROADMAP SC#1 명시).

### Out of Scope for Phase 2

- `report_type` 컬럼 — Phase 5
- `source_reports`, briefing-specific 컬럼 — Phase 5
- 가격/숫자 예측, sentiment-only 분석 (Veto #1, #5) — analysis runner Phase 4 책임
- `body_embedding halfvec(1024)` — 필요 시 Phase 4 또는 후속에서 ALTER TABLE
- pg_trgm 인덱스 — body_tsv로 충족
- `view="both"` MCP API — Phase 3 MCP
- analysis runner / 3-role debate — Phase 4
- KIS auto-trade gates — Phase 6
- CPCV 백테스트 / Sonnet eval — Phase 8
</specifics>

<deferred>
## Deferred Ideas

논의 중 surface된 비-Phase-2 아이디어. 향후 phase 시작 시 검토.

- **JSONB expression 인덱스 (stance, conviction)** — Phase 5 briefing 실측 시 추가 검토.
- **decision_cards.body_embedding halfvec(1024)** — Phase 4가 카드 간 의미 검색 필요해지면
  `ALTER TABLE`로 도입.
- **`schema_version` v1→v2 translator scaffold** — 실제 v2 schema 도입 시점에 함께. Phase 2는
  schema_version=1 고정만.
- **CheckConstraint vs Postgres ENUM 타입 비교 ADR** — `status`/`report_type` enum 표현이
  반복 등장하면 별도 ADR로 표준화 검토 (Phase 9 ops hardening 즈음).
</deferred>

---

## Pointers

- ROADMAP: `.planning/ROADMAP.md` Phase 2 섹션 (Goal, Depends on, Success Criteria 6개)
- Design doc: `.planning/research/redesign-2026-05.md` §3 + §4 + §6
- Hard Vetoes: `CLAUDE.md` 상단 (#2, #3, #4, #13이 직접 관련)
- Phase 1 reference: `.planning/phases/01-collector-db-cutover/` (CONTEXT 작성 패턴,
  PLAN-INDEX 구조, plan 분할 방식)
- Migration 컨벤션: `src/db/migrations/versions/0006_phase01_domain_tables.py`

---

*Phase: 02-decision-card-schema-storage*
*Context gathered: 2026-05-29 via /gsd-discuss-phase 2*
