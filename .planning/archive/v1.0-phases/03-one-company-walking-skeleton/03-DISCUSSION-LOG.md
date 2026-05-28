# Phase 3: One-Company Walking Skeleton - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.

**Date:** 2026-04-17
**Phase:** 03-one-company-walking-skeleton
**Areas discussed:** DART Collection Scope, Chunking Strategy, Hybrid Search Parameters, Prompt Injection Defense, FastMCP Deployment, `ingest rebuild` Semantics

---

## 1. DART Collection Scope

| Sub-decision | Options | Selected |
|---|---|---|
| 공시 유형 | A) 4 types all / B) A+B only / C) A only | B (A+B, C/D scaffolding) |
| `--since` 기본값 | 1 month / 1 year / 5 years | 1 year (365 days) |
| 문서 수 캡 | 없음 / 100 / 500 | `--max-docs=100` (Phase 3 한정) |
| 첨부파일 파싱 | 포함 / skip | skip (본문만) |

---

## 2. Chunking Strategy

| Sub-decision | Options | Selected |
|---|---|---|
| 단위 | A) 고정 512/64 / B) 문단 / C) 섹션 | C (섹션 기반) |
| 큰 섹션 처리 | A) >1500 tokens 시 2차 분할 / B) 잘라냄 / C) 항상 분할 | A (1500 tokens 임계치) |
| 소스별 정책 차이 | 있음 / 없음 | 있음 (source별 parser 모듈) |
| chunk_index 순서성 | 유지 / 미유지 | 유지 (문서 전체 순서) |

**Parser 정책:** DART 정기 = dart-fss TOC, DART 주요사항 = 전체 1섹션. 뉴스(Phase 4)는 별도 결정.
**Schema 변경:** 0002 migration으로 `chunks.section_path`, `section_index` 컬럼 추가.

---

## 3. Hybrid Search Parameters

| Sub-decision | Selected |
|---|---|
| RRF k | 60 고정 |
| dense/BM25 가중 | 동등 |
| top_k 기본 | 10 (max 50) |
| excerpt_length | 400 chars |
| 쿼리 임베딩 캐시 | in-process LRU (256) |
| 쿼리 BM25 토큰화 | mecab-ko (인덱스 동일) |
| 필터 순서 | SQL WHERE pre-vector-scan + iterative_scan=relaxed_order |
| ticker 필터 처리 | `resolve_entity(ticker, as_of=date_range.end)` → `corp_code` 조인 |

---

## 4. Prompt Injection Defense

**Approach:** 3-layer scaffolding (Phase 3에 framework 완성, LLM 투입은 Phase 5에서 활성화).

| Layer | Component | Phase 3 상태 |
|---|---|---|
| 1 | collector의 `trust_level` frontmatter | 활성 (DART=trusted 기록) |
| 2 | `wrap_untrusted(body, source)` 함수 + delimiter 포맷 | 구현 + 단위 테스트, 실제 호출은 Phase 5 |
| 3 | `detect_injection_patterns()` regex 매칭 + 로그 | 활성 (모든 문서 스캔, 플래그 기록) |

**Delimiter 포맷:** `<untrusted source="..." trust="..." doc_id="...">...</untrusted>`
**MCP 응답 포맷:** `<vault_excerpt source="..." path="..." doc_id="...">...</vault_excerpt>`
**trust_level:** trusted / semi_trusted / adversarial (adversarial은 Phase 5 LLM 투입 금지)

---

## 5. FastMCP Deployment

| Sub-decision | Selected |
|---|---|
| 실행 방식 | `uv run stock-mcp` + `.mcp.json` 커밋 |
| 에러 처리 | Structured error response (code + message + details), raise 금지 |
| `search` 기본 파라미터 | `mode='hybrid'`, `top_k=10` |
| 로깅 | stderr 구조화 JSON, `.planning/logs/stock-mcp-*.log` |
| Fail-fast | 서버 시작 시 `_check_db_connection()` |

---

## 6. `ingest rebuild` Semantics

| Sub-decision | Selected |
|---|---|
| 전략 | Full wipe + rebuild |
| Transaction 경계 | Per-document (실패한 것만 skip) |
| 임베딩 재사용 | model version + content_hash unchanged 시 재사용 |
| CLI | `stock ingest rebuild [--force-reembed] [--dry-run] [--yes]` |
| 멱등성 테스트 | `test_rebuild_idempotent` — rebuild 전후 row counts 일치 |

Incremental reconcile은 Phase 9 `ingest doctor`로 분리.
