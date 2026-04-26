# Phase 6: Full MCP Tool Surface - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-26
**Phase:** 06-full-mcp-tool-surface
**Areas discussed:** MCP-03 4축 조립 책임분담, Two-step ID 패턴 일관성, add_note 쓰기 정책, health() 스테일니스 임계값, CI 게이트 측정, get_portfolio_state 가격 포함, MCP-03 토큰 예산

---

## MCP-03 4축 조립 책임분담

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 6 = nullable 자리 잡기 | OverviewResponse에 valuation/supply_demand/private_thesis Optional, 기본 None. Phase 10 wiring | ✓ |
| Phase 6이 조립까지 책임 | placeholder stub 함수 만들고 Phase 10이 내부만 교체 | |
| MCP-03 자체를 Phase 10으로 이양 | ROADMAP 변경 필요 | |

**User's choice:** Phase 6 = nullable 자리 잡기

---

## MCP-03 기본축

| Option | Description | Selected |
|--------|-------------|----------|
| events + portfolio + related notes 3축 | Phase 6 단독으로 의미 있는 통합 | ✓ |
| events + related notes 2축 | portfolio 별도 | |
| events 단독 | 최소 구성 | |

**User's choice:** 3축 (events + portfolio + related_notes)

---

## get_recent_events 응답 형태

| Option | Description | Selected |
|--------|-------------|----------|
| ID + snippet (200자) + vault_path | 본문은 get_filing(id) 2차 호출 | ✓ |
| ID + _derived.summary inline | summary 없는 문서 fallback 필요 | |
| 전부 inline (small N) | 토큰 예산 타이트 | |

**User's choice:** ID + snippet only

---

## get_related 응답 형태

| Option | Description | Selected |
|--------|-------------|----------|
| ID + edge_type + snippet | 본문은 get_filing(id) | ✓ |
| Phase 7 의존 minimal stub | edges 그대로 (id, edge_type, depth) | |

**User's choice:** ID + edge_type + snippet (Phase 7 graphify 독립)

---

## add_note 충돌 정책

| Option | Description | Selected |
|--------|-------------|----------|
| Append | 구분자 + body 추가, frontmatter updated 갱신 | ✓ |
| Overwrite | 완전 교체 | |
| Error (create-only) | 명시적 mode 필요 | |

**User's choice:** Append (default)

---

## add_note frontmatter 검증

| Option | Description | Selected |
|--------|-------------|----------|
| Pydantic NoteFrontmatter 강제 + 자동 필드 | type 필수, created/updated/author 자동 | ✓ |
| free-form dict + 최소 검증 | type 없어도 허용 | |

**User's choice:** Pydantic 강제

---

## add_note 디렉터리 / 명명

| Option | Description | Selected |
|--------|-------------|----------|
| 자동 mkdir + journal alias 지원 | path='journal/today' 해석, 화이트리스트 외부 거절 | ✓ |
| 명시적 path만 | alias 없음 | |

**User's choice:** 자동 mkdir + alias

---

## health() staleness 임계값

| Option | Description | Selected |
|--------|-------------|----------|
| source별 다른 임계값, code constant | DART/KRX/macro/kind 26h, news 12h | ✓ |
| .planning/config.json 기반 | 외부 설정 | |
| 단일 24h | 모두 동일 | |

**User's choice:** code constant

---

## health() 응답 상태

| Option | Description | Selected |
|--------|-------------|----------|
| per-source: ok/stale/down + overall | 명확한 3단 enum | ✓ |
| boolean healthy + 상세 dict | 단순하지만 stale/down 구분 어려움 | |

**User's choice:** per-source enum

---

## health() 데이터 소스

| Option | Description | Selected |
|--------|-------------|----------|
| ingest_runs 테이블 우선 + heartbeat fallback | DB 액세스 빠름, vault만으로도 동작 | ✓ |
| heartbeat.md 우선 | vault 중심 | |

**User's choice:** ingest_runs 우선 + heartbeat fallback

---

## CI 게이트 측정

| Option | Description | Selected |
|--------|-------------|----------|
| fixture vault + testcontainers Postgres, N=20회 p95 | PR test에서 안정 측정 | ✓ |
| live vault + nightly | 머지 전 적용 안 됨 | |
| single-shot + 경고 임계 | 구현 소, 불안정 | |

**User's choice:** fixture + N=20

---

## get_portfolio_state 가격 포함

| Option | Description | Selected |
|--------|-------------|----------|
| 메타 only (ticker, qty, avg_cost, last_updated) | Claude가 별도 계산 | ✓ |
| 시세 + 평가액 결합 | 편리하지만 실패 모드 증가 | |

**User's choice:** 메타 only

---

## MCP-03 응답 토큰 예산

| Option | Description | Selected |
|--------|-------------|----------|
| 섹션별 명시 예산 | 정해진 % 분배 + truncate | |
| 8k 자동 truncation | 끝에서 잘라냄 | |
| Other: "응답토큰 제한 없이" | (사용자 자유 입력 — 후속 명확화 필요) | (재검토) |

**User's choice (1차):** "응답토큰 제한 없이" (free text)

**Follow-up (ROADMAP 충돌 해결):**

| Option | Description | Selected |
|--------|-------------|----------|
| 8k 게이트 유지, 우선순위 기반 truncate | events→notes→supply→valuation→private 역순 잘라냄 + truncated 플래그 | ✓ |
| MCP-10 wording 수정 (16k) | ROADMAP 완화 | |
| 토큰 게이트 완전 제거 | MCP-10 축소 | |

**User's final choice:** 8k 유지 + 우선순위 기반 truncation

---

## Claude's Discretion

- 신규 툴 모듈 분할 구조 (`tools/overview.py` 등) 세부
- `NoteFrontmatter` 정확한 필드 default 처리, alias resolver 위치
- testcontainers fixture 데이터 생성 스크립트 디테일
- snippet 헬퍼 위치 (`src/stock_mcp/snippets.py` 제안)
- 응답 토큰 측정 라이브러리 (`tiktoken cl100k_base` 제안)

## Deferred Ideas

- get_ticker_overview에 live 가격/평가액 직접 결합
- Multi-user visibility 컬럼
- MCP-03 응답 cache
- add_note `mode` 파라미터 (overwrite/create-only)
- graphify wiki/json 직접 활용 (Phase 7)
