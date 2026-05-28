---
phase: 08-vault-dashboards-research-memo-templates
plan: 05
subsystem: ingest
tags: [gap-closure, ingest-parsers, frontmatter-schema, regression-guard]
requires:
  - "src/shared/frontmatter.py:EventType Literal (Phase 5 D-08)"
  - "src/ingest/parsers/__init__.py:parse_sections dispatch (Phase 3)"
  - ".claude/routines/enrich/prompts/derived_krx.md:price_micro 의도"
provides:
  - "src/ingest/parsers/macro.py:parse_sections (단일-section)"
  - "src/shared/frontmatter.py:EventType + price_micro"
  - "tests/shared/test_event_type_enum_drift.py:regression guard"
affects:
  - "src/ingest/worker.py:process_document (macro source 더 이상 ValueError 안 던짐)"
  - "vault/raw/dart/2026/*.md, vault/raw/krx/2026-04-24/*.md (event_type 마이그레이션)"
tech_stack_added: []
patterns:
  - "단일-section parser 패턴 (Phase 8 worker.process_private_note 일관)"
  - "regression guard test (vault 데이터-enum drift 차단)"
key_files_created:
  - .planning/phases/08-vault-dashboards-research-memo-templates/08-05-FINDINGS.md
  - .planning/phases/08-vault-dashboards-research-memo-templates/deferred-items.md
  - src/ingest/parsers/macro.py
  - tests/ingest/parsers/test_macro.py
  - tests/ingest/parsers/test_parse_sections_dispatch.py
  - tests/shared/test_event_type_enum_drift.py
key_files_modified:
  - src/ingest/parsers/__init__.py
  - src/shared/frontmatter.py
  - vault/raw/dart/2026/20260318001062_00126380.md
  - vault/raw/dart/2026/20260318001203_00126380.md
  - vault/raw/krx/2026-04-24/000660.md
  - vault/raw/krx/2026-04-24/005930.md
key_decisions:
  - "GAP-03 → Option A: EventType Literal에 price_micro 추가 (KRX prompt 의도와 정합) + 환각값 2건 1회성 마이그레이션 (disclosure → buyback_announcement, news_micro → price_micro)"
  - "GAP-04 → macro 단일-section parser (DART처럼 TOC 분해하지 않음); empty body → 빈 list (worker가 zero-section 안전 스킵)"
  - "범위 외 schema drift (numeric_facts/sentiment shape)는 deferred-items.md에 기록 — 후속 plan/quick task로 분리"
metrics:
  duration_minutes: 22
  completed_date: 2026-05-09
---

# Phase 08 Plan 05: vault ingest 진입 차단 해제 (GAP-03 + GAP-04) Summary

**One-liner:** macro source 단일-section parser 신설 + EventType Literal `price_micro` 확장 + vault 환각 event_type 4건 마이그레이션으로 production `uv run stock ingest run`의 진입 차단(parse_sections / Pydantic validation) 해소.

## Tasks

### Task 1: vault/raw event_type 값 분포 조사 + 결정 기록 (FINDINGS.md)

- `find vault/raw -name "*.md" -exec grep "event_type:"` 결과 분석:
  - `disclosure × 2` (DART, prompt enum 외 환각)
  - `news_micro × 2` (KRX, prompt 의도는 `price_micro`)
  - macro 4건은 `event_type` 없음 (Optional 통과)
- `.claude/routines/enrich/prompts/derived_*.md` 프롬프트와 enum 비교 → `price_micro`는 KRX prompt 의도지만 enum 부재; `disclosure`/`news_micro`는 모델 환각.
- **결정 (Option A):** EventType에 `price_micro` 1개 추가 + 환각값 2건은 의미 정확한 D-08 enum으로 마이그레이션. (양다리 아님 — `price_micro`는 prompt 의도 보존, `disclosure`는 자기주식 도메인 의미상 `buyback_announcement`이 정답.)
- **Commit:** `962f06b`

### Task 2: macro parser + EventType drift 해소 (TDD)

**RED → GREEN → 회귀 검증:**

1. **RED:** 3개 테스트 파일 작성, 실행 → fail 확인
   - `test_macro.py` (parse_sections('macro') 단일-section 컨트랙트)
   - `test_parse_sections_dispatch.py` (dart/macro/unknown 디스패치 + T-3-15 입력 누출 방어)
   - `test_event_type_enum_drift.py` (vault → EventType regression guard)

2. **GREEN:**
   - `src/ingest/parsers/macro.py` 신설: `body.strip()` 비면 `[]`, 그 외 단일 `Section(title="body", path="body", text=body.strip(), order=0)`
   - `src/ingest/parsers/__init__.py` dispatch에 `if source == "macro"` 분기 추가
   - `src/shared/frontmatter.py` EventType Literal에 `price_micro` 추가 (KRX 섹션 코멘트 포함)
   - vault 4건 마이그레이션 (수동 sed 대신 Read+Edit으로 정확 1줄 변경)

3. **Verify:**
   - `uv run pytest tests/ingest/parsers/test_macro.py tests/ingest/parsers/test_parse_sections_dispatch.py tests/shared/test_event_type_enum_drift.py` → 7/7 PASS
   - `uv run pytest tests/ingest/ tests/shared/` → 51/51 PASS (회귀 0건)

- **Commit:** `57b1e52`

## Decisions Made

| Decision | Rationale |
|---|---|
| Option A (enum 확장) | `price_micro`는 KRX prompt가 명시한 의도된 카테고리 — D-08 18 enum 어디에도 적합한 매핑 없음, 새 값 추가가 정직 |
| `disclosure` → `buyback_announcement` 마이그레이션 | DART prompt enum에 없는 환각, 도메인 의미는 자기주식 취득/처분 = buyback_announcement |
| `news_micro` → `price_micro` 마이그레이션 | KRX prompt가 명시한 정확 값으로 데이터 정합 |
| empty macro body → `[]` (zero sections) | Phase 8 `worker.process_private_note` 패턴 일관, worker가 zero-section 안전 스킵 |
| schema drift (numeric_facts/sentiment) deferred | plan 범위 외 — deferred-items.md에 기록, 후속 enrichment 정합 plan/quick task |

## Deviations from Plan

### Auto-fixed Issues

None — Plan 명세대로 실행. ruff-format이 자동 적용한 1줄 스타일 포매팅(`f""` quote 단순화)은 hook 차원 자동 변환이며 의미 변경 없음.

### Out-of-Scope Discoveries (Logged to deferred-items.md)

**[Discovered during Task 2 production rebuild simulation]** vault/raw 8건 중 4건의 `_derived` 블록이 GAP-03/04와 별개로 추가 schema drift를 가짐:
- `numeric_facts`: vault는 `{metric, value, unit, period}`, 스키마는 `{key, value, unit}` (extra=forbid)
- `sentiment`: vault는 bare string, 스키마는 `SentimentBlock` dict
- `_uncertain`: 스키마 외 필드

이는 Phase 5 D-08 Pydantic 스키마와 enrichment 프롬프트 간 형상 불일치이며 GAP-03/04 범위 밖. **SCOPE BOUNDARY** 적용하여 직접 수정하지 않고 `deferred-items.md`에 기록 (후속 `260509-prompt-schema-realign` 같은 quick task로 분리 권고).

## Verification Evidence

```
$ uv run pytest tests/ingest/parsers/test_macro.py \
    tests/ingest/parsers/test_parse_sections_dispatch.py \
    tests/shared/test_event_type_enum_drift.py
============================== 7 passed in 2.53s ===============================

$ uv run pytest tests/ingest/ tests/shared/
================== 51 passed, 1 warning in 226.99s (0:03:46) ===================
```

## Self-Check: PASSED

**Files:**
- FOUND: `.planning/phases/08-vault-dashboards-research-memo-templates/08-05-FINDINGS.md`
- FOUND: `src/ingest/parsers/macro.py`
- FOUND: `tests/ingest/parsers/test_macro.py`
- FOUND: `tests/ingest/parsers/test_parse_sections_dispatch.py`
- FOUND: `tests/shared/test_event_type_enum_drift.py`
- FOUND: `.planning/phases/08-vault-dashboards-research-memo-templates/deferred-items.md`

**Commits:**
- FOUND: `962f06b` (Task 1 — FINDINGS.md)
- FOUND: `57b1e52` (Task 2 — macro parser + EventType drift)
