# Phase 2: Canonical Entity Identity - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-17
**Phase:** 02-canonical-entity-identity
**Areas discussed:** Entity Alias Model, Supersedes Storage, resolve_entity Temporal Semantics, Content-Hash Dedup

---

## Entity Alias History Model

| Option | Description | Selected |
|--------|-------------|----------|
| A) Separate `entity_aliases` table | valid_from/valid_to, SQL temporal queries 직관적 | ✓ |
| B) JSONB `entities.aliases` column | 단일 테이블, GIN index, but temporal WHERE 복잡 | |
| C) Both (table = SoT, JSONB = cache) | 정합성 유지 복잡, 과잉 | |

**User's choice:** A
**Notes:** ticker 재활용 케이스가 핵심 — 같은 6자리 value라도 시기별로 다른 corp_code에 매핑 가능

---

## Supersedes Edge Storage

| Option | Description | Selected |
|--------|-------------|----------|
| A) `edges` table only | 통합 관계 모델, Phase 7 graphify와 자연스럽게 통합 | ✓ |
| B) `documents.superseded_by_document_id` self-reference column | 단순하나 관계 타입 확장 시 컬럼 폭증 | |
| C) Both (edge = SoT, column = cache) | Phase 2에선 조기 최적화 | |

**User's choice:** A
**Notes:** 최신본 조회는 재귀 CTE로 해결. Phase 6 `get_filing(id)`에서 의미 명확화

---

## `resolve_entity` Temporal Semantics

| Option | Description | Selected |
|--------|-------------|----------|
| A) Single-axis (valid-time only) | "실세계 as_of 시점의 엔티티 상태" 의미 | ✓ |
| B) Bitemporal (valid + system time) | 감사/규제 준수용, 개인 스케일엔 오버킬 | |
| C) 현재 상태 + audit log | as_of 쿼리 재생 느림 | |

**User's choice:** A
**Notes:** 백테스트에서 "과거 판단 재구성"은 실세계 시점 기준으로 충분. DB가 언제 알게 됐는지는 비관여

---

## Content-Hash Dedup

### Sub-decision 1: body scope

| Option | Description | Selected |
|--------|-------------|----------|
| A) Raw body (frontmatter 포함) | 단순하나 메타데이터 변화로 해시 불안정 | |
| B) Frontmatter 제거 + line ending 정규화 | 재수집 시 같은 id 보장 | ✓ |
| C) 구조화 canonical JSON | 과잉, DART 원문 안정적 | |

**User's choice:** B
**Notes:** Phase 1의 3-zone frontmatter 설계와 정합. `provenance`는 수집 메타이므로 해시 영향 제외

### Sub-decision 2: 충돌 처리

| Option | Description | Selected |
|--------|-------------|----------|
| A) Upsert (metadata 갱신) | last_seen_at + source_urls 누적, idempotent | ✓ |
| B) Fail loudly (collector 책임) | DB 사전 조회 필요 | |
| C) Skip silently + 로그 | 재수집 이벤트 손실 | |

**User's choice:** A
**Notes:** `last_seen_at`, `source_urls` 배열로 재수집 흔적 자연스럽게 누적

---

## Claude's Discretion

- Alembic env.py 설정 (autogenerate vs explicit)
- 마이그레이션 파일 분할 전략
- `events`, `ingest_runs`, `chunks` 테이블 상세 (Phase 3 위임 가능 부분)
- pytest fixture 실제 기업 선정

## Deferred Ideas

- Bitemporal 모델 (v2+)
- `events` 이벤트 타입 확장 (Phase 4)
- `chunks.embedding` HNSW 인덱스 실제 생성 (Phase 3)
- graphify 전체 엣지 타입 등록 (Phase 7)
- `document_sources` 정규화 (필요 시)
- `entity_aliases` fuzzy matching (패턴 드러나면 추가)
