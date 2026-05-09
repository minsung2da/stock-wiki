# GAP-03 + GAP-04 Findings

**Investigated:** 2026-05-09
**Decision (GAP-03):** Option A (enum 확장) + 환각값 2건 1회성 마이그레이션
**Decision (GAP-04):** macro 단일-section parser 신설
**Files affected:**
- `src/shared/frontmatter.py` (EventType Literal에 `price_micro` 추가)
- `src/ingest/parsers/macro.py` (신설)
- `src/ingest/parsers/__init__.py` (macro dispatch)
- `vault/raw/dart/2026/*.md` 2건 (`event_type: disclosure` → `buyback_announcement`)
- `vault/raw/krx/2026-04-24/*.md` 2건 (`event_type: news_micro` → `price_micro`)
- `.claude/routines/enrich/prompts/derived_krx.md` (enum 정합 — `price_micro`가 EventType에 추가됨을 반영)

---

## 값 분포

`find vault/raw -name "*.md" -exec grep -h "^[[:space:]]*event_type:" {} \;` 결과:

```
      2 event_type: news_micro
      2 event_type: disclosure
```

총 4건이 `_derived.event_type` 값을 가짐. 매크로 4건(`vault/raw/macro/{ecos,fred}/*.md`)은 `event_type` 없음 (Pydantic 검증 통과 — Optional).

### 파일별 매핑

| 파일 | 현재 event_type | 도메인 의미 |
|---|---|---|
| `vault/raw/dart/2026/20260318001062_00126380.md` | `disclosure` | 자기주식 취득 결정 (PSU 보상) |
| `vault/raw/dart/2026/20260318001203_00126380.md` | `disclosure` | 자기주식 직원 지급 결정 |
| `vault/raw/krx/2026-04-24/000660.md` | `news_micro` | KRX 일일 종가/거래량 (SK하이닉스) |
| `vault/raw/krx/2026-04-24/005930.md` | `news_micro` | KRX 일일 종가/거래량 (삼성전자) |

## 출처 collector 식별

`grep -rn '"disclosure"' src/collectors/` → **0 hits** (collector 코드는 event_type을 직접 쓰지 않음)
`grep -rn '"news_micro"' src/` → **0 hits**

`event_type`은 **Claude Schedule enrichment 산출물** (`_derived` zone). 관련 프롬프트:

- `.claude/routines/enrich/prompts/derived_dart_b.md`
  - 명시된 enum: `{earnings_release, equity_issue, mergers_acquisitions, major_contract, board_change, ownership_change, buyback_announcement, dividend, other}`
  - **`disclosure`는 enum에 없음 → 모델 환각/일탈**
- `.claude/routines/enrich/prompts/derived_krx.md`
  - 명시: `event_type: price_micro` (always)
  - **vault 데이터(`news_micro`)와 prompt(`price_micro`) 불일치 → 두 번째 환각/오기**
  - 추가로 `price_micro`는 `EventType` Literal에 부재 → prompt-enum 양쪽 모두 drift
- `.claude/routines/enrich/prompts/derived_kind.md`, `derived_news.md` — 모두 D-08 enum과 정합 (vault/raw/kind, vault/raw/news 미존재로 영향 없음)

## 결정 (Decision)

Decision (GAP-03): Option A (enum 확장) + 환각값 2건 1회성 마이그레이션
Decision (GAP-04): Option A — macro 단일-section parser 신설

**채택 옵션: Option A (enum 확장) + 환각값 2건 1회성 마이그레이션**

### 이유

1. **`price_micro`는 KRX prompt가 명시적으로 지정한 의도된 카테고리**다. KRX collector가 매일 기록하는 일일 시세 마이크로 이벤트에 D-08 정규 enum 18개 어디에도 적합한 매핑이 없다(가장 가까운 `market_gossip`/`other`도 의미상 wrong). 따라서 enum 확장이 정직하다.

2. **`disclosure`는 prompt 어디에도 없는 명백한 LLM 환각**이다. enum 확장이 아닌 **올바른 D-08 카테고리로 마이그레이션** (자기주식 = `buyback_announcement`)이 의미적으로 정확하다.

3. **`news_micro`도 prompt에 없는 환각**이다. KRX prompt가 명시한 `price_micro`로 마이그레이션해야 한다 (즉, prompt 의도를 데이터에 반영).

4. enum 확장(1개: `price_micro`) + 환각 보정(2건 마이그레이션) 조합으로 양다리가 아닌 단일 결정. **모든 collector/prompt 의도와 정합**한 후, 향후 LLM 일탈은 regression test (test_event_type_enum_drift.py)가 차단.

### 변경 대상

#### 코드 (Task 2 GREEN)

- `src/shared/frontmatter.py` EventType Literal에 1개 값 추가:
  ```python
  # KRX (1) — Phase 8 GAP-03: enriched daily price events
  "price_micro",
  ```
  D-08 코멘트 블록에 위치 추가 (KIND 위 또는 KRX 신규 섹션).

#### Vault 데이터 마이그레이션 (Task 2 1회성)

| 파일 | Before | After |
|---|---|---|
| `vault/raw/dart/2026/20260318001062_00126380.md` | `event_type: disclosure` | `event_type: buyback_announcement` |
| `vault/raw/dart/2026/20260318001203_00126380.md` | `event_type: disclosure` | `event_type: buyback_announcement` |
| `vault/raw/krx/2026-04-24/000660.md` | `event_type: news_micro` | `event_type: price_micro` |
| `vault/raw/krx/2026-04-24/005930.md` | `event_type: news_micro` | `event_type: price_micro` |

#### 프롬프트 정합 (재발 방지)

- `.claude/routines/enrich/prompts/derived_krx.md`: `event_type: price_micro` 지시 유지 (이미 OK), enum 명시 보강.

#### Macro parser (GAP-04)

- `src/ingest/parsers/macro.py` 신설 — body strip → 단일 `Section(title="body", path="body", text=body.strip(), order=0)` 또는 빈 body 시 `[]`.
- `src/ingest/parsers/__init__.py` dispatch에 `if source == "macro"` 분기 추가.

## 후속 (Plan 범위 외)

- Phase 5 D-08 enum 코멘트 갱신 (Comment count 18 → 19).
- DART prompt에 "환각 금지: enum 외 값 생성 시 reject + retry" 가드 추가는 후속 enrichment hardening quick task로 분리.
