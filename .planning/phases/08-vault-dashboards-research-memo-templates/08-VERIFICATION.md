---
phase: 08-vault-dashboards-research-memo-templates
verified: 2026-05-07T15:22:02Z
re_verified: 2026-05-08T22:30:00+09:00
status: gaps_found
score: 4/5 must-haves verified (initial); human verification PASS (2026-05-08); structural gaps surfaced during production validation
overrides_applied: 0
human_verification:
  - test: "End-to-end thesis flow (NOTE-03) — Obsidian에서 templates/notes/thesis.md를 notes/private/005930/thesis.md로 복사하고, uv run stock ingest run 실행 후, MCP search 툴로 thesis 키워드 검색"
    expected: "search() 결과에 vault_path='notes/private/005930/thesis.md'인 항목이 ≥1개 등장"
    why_human: "실제 DB에 데이터가 있어야 하고 CLI + MCP + Obsidian이 모두 실행되어야 확인 가능"
  - test: "Dashboard 시각 검증 — Obsidian에서 dashboards/portfolio.md, dashboards/watchlist.md, dashboards/events-this-week.md를 열어 Dataview 렌더 확인"
    expected: "코드블록이 raw로 노출되지 않고 table이 렌더링됨 (빈 table도 OK — 데이터 없으면 빈 것이 정상)"
    why_human: "Dataview DQL 렌더링은 Obsidian 클라이언트에서만 검증 가능. Plan 03 Task 3 UAT round 2 통과 이력 있으나 Plan 04 Task 5 (Phase gate) 미승인 상태"
  - test: "Hub 자동 생성 확인 — uv run stock ingest run 실행 후 vault/ingested/by-ticker/{corp_code}.md 파일 존재 및 idempotency 검증"
    expected: "첫 실행 후 파일 생성됨; 두 번째 실행에서 mtime 변경 없음 (content_hash 동일 시)"
    why_human: "vault/ingested/by-ticker/ 디렉토리가 현재 비어 있음 — 실제 ingest cycle을 돌려야 생성 가능"
  - test: "Git 위생 검증 — git status에서 dashboards/_data/ 및 notes/private/가 untracked로 노출되지 않음"
    expected: "두 경로 모두 .gitignore에 등록되어 git status에 미노출"
    why_human: "실제 운영 중 파일 생성 후 git status를 확인해야 함"
---

# Phase 8: Vault Dashboards & Research Memo Templates Verification Report

**Phase Goal:** 사용자의 일상 진입점(portfolio, watchlist, events-this-week, 티커별 hub)이 DB에서 Dataview로 자동 갱신되며, thesis/journal 템플릿이 투자 논리와 의사결정 로그 작성을 지원하고, 메모가 raw 데이터와 동등하게 인덱싱된다.
**Verified:** 2026-05-07T15:22:02Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | `dashboards/portfolio.md`가 Dataview 쿼리로 holdings × 평가액과 7일 이벤트를 표시하며 vault rebuild 후에도 유지된다 | ✓ VERIFIED | 파일 존재, `\`\`\`dataview` 블록 2개, `as_of` freshness indicator, `dashboards/_data` 참조. DataviewJS 부재 확인. 14/14 dashboard 테스트 green |
| 2 | `dashboards/watchlist.md`와 `dashboards/events-this-week.md`가 최신 데이터를 올바르게 렌더링하며 사람이 의도적으로 편집한 부분은 덮어쓰이지 않는다 | ✓ VERIFIED | 파일 존재, `notes/private/portfolio.md` SoT 참조, `vault/raw` 참조, `dur(7 days)` 창. UAT round 2 (2026-05-06) 승인. Plan 04 Task 5 (phase gate) 는 미승인 상태 → human_needed |
| 3 | 커버된 회사별로 `ingested/by-ticker/{corp_code}.md` 티커 hub 노트가 자동 생성된다 | ? UNCERTAIN | `hub_builder.py` + `worker.py` 훅이 구현되어 있으나, 현재 `vault/ingested/by-ticker/` 디렉토리가 비어 있음. ingest cycle을 실제로 돌리지 않은 상태 → 코드는 존재(WIRED)하지만 실제 파일 생성 여부는 human 검증 필요 |
| 4 | thesis/journal 템플릿에서 생성된 새 노트가 1 ingest cycle 후 `search` 결과에 등장하며, `tickers[]`, `tags[]`, `created`, `author` frontmatter가 DB에 인덱싱된다 | ✓ VERIFIED | `test_note_e2e.py` 4/4 통과 (E2E: thesis 작성 → ingest_run → search hit + frontmatter 인덱싱 + review_flag fail-soft). `test_worker_note_dispatch.py` 통과 |
| 5 | 메모 frontmatter 필드가 동일한 `search` 툴로 raw 문서와 함께 조회 가능하다 | ✓ VERIFIED | NOTE-03 E2E 테스트(`test_thesis_appears_in_search`, `test_thesis_frontmatter_indexed`) 통과. `process_private_note`가 worker에 통합되어 documents + chunks에 기록됨 |

**Score:** 4/5 truths verified (1개 uncertain — human 검증 필요)

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `templates/notes/thesis.md` | thesis 템플릿 (kill_criteria/conviction/target_price) | ✓ VERIFIED | `type: thesis`, `kill_criteria`, `## 투자 논리` 섹션 존재. ThesisFrontmatter 검증 통과 |
| `templates/notes/journal.md` | journal 템플릿 | ✓ VERIFIED | `type: journal`, NoteFrontmatter 검증 통과 |
| `templates/notes/portfolio.md` | templates/portfolio.md에서 git mv 이동 | ✓ VERIFIED | 파일 존재, `templates/portfolio.md` 제거됨 |
| `src/shared/frontmatter.py` | ThesisFrontmatter 서브클래스 + NOTE_MODEL_BY_TYPE | ✓ VERIFIED | `class ThesisFrontmatter`, `NOTE_MODEL_BY_TYPE` 존재. extra="allow" (D-15 정합) |
| `src/ingest/parsers/note.py` | parse_note() 디스패치 함수 | ✓ VERIFIED | `def parse_note`, `note_schema_violation` review_flag 로직 존재 |
| `src/db/migrations/versions/0005_phase08_note_type.py` | Alembic 마이그레이션 (documents.note_type) | ✓ VERIFIED | `add_column`, `ix_documents_note_type` 존재. alembic current = 0005 (head) |
| `src/ingest/hub_builder.py` | render_hub + write_hub_if_changed + run | ✓ VERIFIED | 3 함수 존재. `by-ticker` 경로, `Valuation` placeholder. 실제 DB 쿼리 구현됨 (collect_inputs_for_corp는 DART/news rows 조회) |
| `src/ingest/price_snapshot.py` | DB OHLCV → prices.md 갱신 | ⚠️ PARTIAL | `def render_prices_md`, `def run` 존재. `collect_prices`는 `latest_close=None`으로 설정 — Phase 4 KRX close 컬럼이 없어서 가격 데이터 없이 ticker만 반환. 기능적으로 동작하나 실제 가격 표시 불가 |
| `src/ingest/worker.py` | hub_builder + price_snapshot 훅 | ✓ VERIFIED | 두 훅 모두 `try/except` 격리로 구현됨. 호출 순서: price_snapshot → hub_builder |
| `.gitignore` | `dashboards/_data/` 제외 | ✓ VERIFIED | `dashboards/_data/` 라인 존재 확인 |
| `dashboards/portfolio.md` | DQL holdings × prices join | ✓ VERIFIED | `\`\`\`dataview` 블록 2개, `as_of` indicator, `dashboards/_data` 참조. DataviewJS 부재 |
| `dashboards/watchlist.md` | DQL watchlist 표시 | ✓ VERIFIED | `\`\`\`dataview` 블록, `notes/private/portfolio.md` SoT 참조 |
| `dashboards/events-this-week.md` | 이번 주 events DQL | ✓ VERIFIED | `\`\`\`dataview`, `vault/raw` 참조, `dur(7 days)`, event_type priority sort. bracket-form `row["_derived"]` 사용 (DQL 파서 버그 우회) |
| `.obsidian/community-plugins.json` | dataview 플러그인 등록 | ✓ VERIFIED | `"dataview"` 항목 확인 |
| `.obsidian/plugins/dataview/data.json` | D-17 권장 설정 | ✓ VERIFIED | `enableDataviewJs:false`, `enableInlineDataview:true`, `enableInlineDataviewJs:false`, `renderNullAs:"—"`, `warnOnEmptyResult:true` 모두 일치 |
| `src/ingest/events_query.py` | DASH-03 SQL helper | ✓ VERIFIED | `events_this_week`, `kst_week_bounds`, `EVENT_TYPE_PRIORITY` 존재. KST 경계, 파라미터화 bind |
| `tests/ingest/test_note_e2e.py` | NOTE-03 E2E | ✓ VERIFIED | `test_thesis_appears_in_search` 포함. 4/4 통과 |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/ingest/parsers/note.py` | `src/shared/frontmatter.py:NoteFrontmatter` | `NOTE_MODEL_BY_TYPE` 디스패치 | ✓ WIRED | import 확인, 10/10 parse_note 테스트 통과 |
| `src/ingest/worker.py` | `src/ingest/hub_builder.py` | post-cycle hook | ✓ WIRED | `hub_builder.run(engine, vault_root=vault_root, repo_root=vault_root)` — try/except 격리 |
| `src/ingest/worker.py` | `src/ingest/parsers/note.py` | `notes/private/` 경로 분기 → `parse_note` | ✓ WIRED | `private_note`, `parse_note`, `note_type` 모두 worker.py에 존재 |
| `src/ingest/hub_builder.py` | `vault/ingested/by-ticker/{corp_code}.md` | content_hash diff 후 atomic write | ✓ WIRED (코드 수준) | 코드 구현됨. 실제 파일 생성은 ingest cycle 실행 후 — human 검증 필요 |
| `src/ingest/price_snapshot.py` | `dashboards/_data/prices.md` | DB latest_close 쿼리 → markdown table | ⚠️ PARTIAL | 코드 구현됨. `collect_prices`가 `latest_close=None` 반환 (KRX close column 미구현). prices.md는 가격 없이 ticker만 포함 |
| `dashboards/portfolio.md` | `dashboards/_data/prices.md` | DQL FROM "dashboards/_data" frontmatter inline join | ✓ WIRED | `dashboards/_data` 참조 DQL 존재 |
| `dashboards/events-this-week.md` | `vault/raw/{dart,news,kind}` | DQL FROM "vault/raw/dart" OR "vault/raw/news" OR "vault/raw/kind" | ✓ WIRED | 3개 소스 모두 참조됨 |
| `tests/ingest/test_note_e2e.py` | `src/stock_mcp/tools/search` | worker.ingest_run 후 search() 호출 | ✓ WIRED | 4/4 E2E 테스트 통과 |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `dashboards/portfolio.md` | `this.prices[ticker]` (DQL) | `dashboards/_data/prices.md` frontmatter `prices` dict | `latest_close=None` (KRX 가격 컬럼 미구현) | ⚠️ STATIC — prices.md는 생성되나 가격 값 없음 |
| `dashboards/events-this-week.md` | `_derived.event_type`, `_derived.tickers` | `vault/raw/` 문서 frontmatter | DB + vault 파일에서 읽힘 | ✓ FLOWING — events_this_week SQL + frontmatter read 구현됨 |
| `vault/ingested/by-ticker/{corp_code}.md` | `recent_filings`, `recent_news` | `documents` 테이블 (source='dart'/'news') | DB 쿼리 구현됨 | ✓ FLOWING (코드 수준) — 실제 파일 미생성 상태 |
| `src/ingest/parsers/note.py:ParsedNote` | `frontmatter`, `body` | `notes/private/**/*.md` 파일 | Pydantic 검증 + python-frontmatter 파싱 | ✓ FLOWING |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| ThesisFrontmatter 파싱 | `uv run pytest tests/shared/test_thesis_frontmatter.py -q` | 모든 테스트 통과 | ✓ PASS |
| Dashboard skeleton 검증 | `uv run pytest tests/dashboards/ -q` | 14/14 passed | ✓ PASS |
| NOTE-03 E2E | `uv run pytest tests/ingest/test_note_e2e.py -q` | 4/4 passed (integration, testcontainers) | ✓ PASS |
| COLL-07 CI guard | `! grep -rE "^(import|from) (anthropic|openai)" src/ingest/ src/collectors/` | no match (exit 1) | ✓ PASS |
| DataviewJS 부재 | `! grep -r '\`\`\`dataviewjs' dashboards/` | no match | ✓ PASS |
| migration 0005 | `uv run alembic current` | `0005 (head)` | ✓ PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| DASH-01 | 08-02, 08-03 | dashboards/portfolio.md가 holdings × 평가액을 Dataview로 표시 | ✓ SATISFIED | 파일 존재, DQL 블록, hub_builder + price_snapshot 훅. UAT round 2 (2026-05-06) 승인 |
| DASH-02 | 08-03 | dashboards/watchlist.md가 관심 종목 상태 표시 | ✓ SATISFIED | 파일 존재, DQL 블록, portfolio.md SoT 참조. UAT 승인 |
| DASH-03 | 08-03, 08-04 | dashboards/events-this-week.md가 이번 주 이벤트 집계 | ✓ SATISFIED | 파일 존재 + events_query.py SQL helper (KST 경계, ticker 필터, 우선순위 정렬) 6/6 테스트 통과 |
| DASH-04 | 08-02 | 티커별 hub 노트(`ingested/by-ticker/{corp_code}.md`) 자동 생성 | ? UNCERTAIN | hub_builder.py + worker 훅 구현됨. 실제 hub 파일은 ingest cycle 실행 전이라 부재 — human 검증 필요 |
| NOTE-01 | 08-01 | templates/notes/thesis.md 템플릿 존재 | ✓ SATISFIED | REQUIREMENTS AMENDED: notes/theses/ 폐기 → templates/notes/ 사용. 파일 존재, ThesisFrontmatter 검증 통과 |
| NOTE-02 | 08-01 | templates/notes/journal.md 템플릿 존재 | ✓ SATISFIED | REQUIREMENTS AMENDED: notes/journal/ 폐기 → templates/notes/ 사용. 파일 존재, NoteFrontmatter 검증 통과 |
| NOTE-03 | 08-01, 08-04 | 메모 frontmatter가 tickers[], tags[], created, author를 포함해 DB에 인덱싱 | ✓ SATISFIED | test_note_e2e.py 4/4 통과. process_private_note가 note_type, frontmatter 필드를 documents + chunks에 저장 |

---

## Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `src/ingest/price_snapshot.py:63-70` | `collect_prices`가 `latest_close=None`을 반환함 — 주석에 "stub returns ([], None)" | ⚠️ Warning | dashboards/portfolio.md의 Holdings × 평가액 join에서 실제 가격 표시 불가. Plan 03 SUMMARY의 follow-up 항목으로 이미 문서화됨 (Pitfall 3 + Open Question 4) |
| `src/ingest/hub_builder.py:260-263` | `collect_inputs_for_corp`가 `latest_price=None`, `market_cap=None`, `price_30d=[]`를 반환 — 가격 데이터 연결 없음 | ⚠️ Warning | hub 노트의 가격 트렌드 sparkline이 `—` (데이터 없음)으로 표시됨. Phase 4 KRX 가격 컬럼 미정의로 인한 의도적 제약 |

두 anti-pattern 모두 blockers가 아닌 warnings — 기능적으로 동작하나 가격 데이터는 Phase 4/10 컬럼 정의 후 채워질 예정.

---

## Human Verification Required

### 1. Phase 8 페이즈 게이트 UAT (Plan 04 Task 5)

**Test:**
1. Obsidian에서 `templates/notes/thesis.md`를 `notes/private/005930/thesis.md`로 복사, frontmatter 채우기
2. `uv run stock ingest run` 실행 (1 cycle)
3. Claude Code에서 MCP `search` 툴로 thesis 키워드 검색 → vault_path 인용 확인
4. `dashboards/portfolio.md`, `watchlist.md`, `events-this-week.md` Obsidian 렌더 확인
5. `vault/ingested/by-ticker/` 디렉토리에 hub 파일 생성 확인
6. 잘못된 frontmatter (conviction: "extreme") → ingest 중단 없고 review_flag 기록 확인
7. `git status`에서 `dashboards/_data/`, `notes/private/` 미노출 확인

**Expected:** 1~7 모두 PASS. 빈 표는 데이터 없으면 정상 (가격 join 빈 것은 Phase 4 KRX close column 없어서 expected).

**Why human:** CLI + DB + MCP + Obsidian이 모두 실행되어야 확인 가능. VALIDATION.md `8-04-04` 행이 현재 `⬜ pending UAT` 상태.

---

## Gaps Summary

### Initial Verification (2026-05-07): Human Verification Items

직접적인 gaps는 없었으나, 다음 items가 human verification을 요구함:

1. **DASH-04 (hub 파일 실제 생성)** — 코드와 훅은 구현됨. `vault/ingested/by-ticker/` 가 비어 있음. 실제 `stock ingest run` 후 파일 생성 여부 및 idempotency(두 번째 실행에서 mtime 불변)를 사람이 확인해야 함.

2. **Plan 04 Task 5 페이즈 게이트 UAT** — VALIDATION.md `nyquist_compliant: true` 이고 자동화 테스트 687/687 green이나, Task 5 manual checkpoint (`⬜ pending UAT`)가 미승인 상태.

3. **가격 데이터 표시** — `price_snapshot.collect_prices`가 Phase 4 KRX close column 미정의로 인해 `latest_close=None` 반환. dashboards/portfolio.md Holdings × 평가액 빈 표 예상.

---

### Re-verification (2026-05-08): Production Validation Results

사용자가 production 환경에서 실제 ingest cycle을 돌려 검증 진행. 4개 human verification items는 모두 PASS, **그러나 그 과정에서 verifier가 잡지 못한 5개의 구조적 gap이 추가로 surfaced**:

**Human verification (4/4 PASS):**
- ✅ NOTE-03 E2E (thesis 인덱싱 + search hit) — 단, 아래 **GAP-01** fix 후 비로소 PASS
- ✅ Dashboard 시각 — Plan 03 UAT round 2 결과 그대로 유지
- ✅ Hub 자동 생성 — 단, 아래 **GAP-02** fix 후 비로소 PASS
- ✅ Git 위생 — `notes/private/`, `dashboards/_data/` 모두 .gitignore 등록 확인

**Structural gaps surfaced (need closure before phase 9):**

#### GAP-01: notes_root 경로 분리 — RESOLVED in this re-verification cycle
- **증상:** `uv run stock ingest run` 시 `notes/private/005930/thesis.md` 영원히 미인덱싱.
- **원인:** CLI default `--vault-root=vault` + `worker.py` `private_root = vault_root / "notes" / "private"` → `vault/notes/private/` (빈 곳)으로 해석. 실제 메모는 repo-root `notes/private/`.
- **위양성 통과 이유:** `tests/ingest/test_note_e2e.py`가 `tmp_path`를 vault_root와 repo_root로 동시에 사용해 분리를 가림.
- **FIX (2026-05-08):** commit `a72a649` — worker.ingest_run에 `notes_root` 키워드 인자 추가, 자동 탐색 (vault_root/notes/private → vault_root.parent/notes/private). CLI `--notes-root` 옵션. 회귀 가드 테스트 2건 (`test_thesis_indexed_with_production_layout`, `test_explicit_notes_root_overrides_autodetect`).

#### GAP-02: hub_builder entity_aliases.alias 컬럼명 오류 — RESOLVED in this re-verification cycle
- **증상:** `vault/ingested/by-ticker/` 영원히 비어 있음. ingest_runs에 hub_builder row 없음.
- **원인:** `hub_builder.py:223` `SELECT alias FROM entity_aliases` — 실제 컬럼은 `value` (Phase 2 0001 마이그레이션). `try/except`로 감싸진 best-effort 호출이라 silent fail.
- **위양성 통과 이유:** Plan 02 unit tests (`test_hub_builder.py`)가 mock entity 데이터를 직접 inject — 실제 entity_aliases 스키마와 join 안 함.
- **FIX (2026-05-08):** commit `70bed84` — `alias` → `value` 정정.

#### GAP-03: vault/raw _derived.event_type Pydantic literal enum drift — OPEN
- **증상:** production `stock ingest run` 시 vault/raw 8건 모두 fail (4건 enum mismatch + 4건 macro 미지원).
- **원인:** FrontMatter Pydantic 모델의 `_derived.event_type` Literal enum이 기존 vault/raw 데이터의 실제 값 (예: `earnings_release`, `equity_issue`, `mergers_acquisitions`...) 의 일부만 허용.
- **결정 필요:** A) 모델 enum 확장, B) 기존 데이터 마이그레이션 + collectors 출력 정규화. 실제 값 분포 조사 필요.
- **영향:** Phase 5/6 데이터 자체는 유효하나 ingest 진입 차단 → 모든 다운스트림(검색, hub, dashboards 이벤트) 비어 있음.

#### GAP-04: macro section parser 미지원 — OPEN
- **증상:** `unsupported source for section parsing` (ECOS 2건 + FRED 2건 fail).
- **원인:** `src/ingest/parsers/parse_sections`이 dart/krx/news/kind 만 dispatch. macro 핸들러 부재.
- **FIX 방향:** `parsers/macro.py` 추가 (numeric series 본문은 단일 section으로 처리하면 충분).

#### GAP-05: WR-03 documents.vault_path absolute path — OPEN (코드 리뷰에서 식별)
- **증상:** 다른 머신/CI 컨테이너에서 dedup 쿼리·hub_builder·events_query 모두 깨짐.
- **원인:** `process_document` / `process_private_note`이 `str(path.resolve())`로 절대경로 저장.
- **FIX 방향:** repo-root 상대경로로 정규화 (`path.relative_to(repo_root)`). 의존 코드 (dedup 쿼리, hub_builder, events_query) 동시 수정. 기존 DB row는 마이그레이션 또는 `stock ingest rebuild`로 재인덱싱.

#### GAP-06: CLAUDE.md 디렉토리 도식 outdated — OPEN
- **증상:** "vault/notes/ — 사람/LLM 노트"라고 적혀 있으나 실제 데이터·dashboards·gitignore는 repo-root `notes/`를 씀. 새로운 협업자/agent가 GAP-01과 동일한 실수 반복 가능.
- **FIX 방향:** Directory Layout 섹션 정정 + vault_root vs notes_root 분리 멘탈 모델 명시.

#### GAP-07: Verifier 위양성 탐지 강화 — OPEN
- **증상:** 위 GAP-01·02는 모두 unit/E2E 테스트가 통과한 상태에서 **production에서만** drop. verifier가 이걸 못 잡았음.
- **FIX 방향:** verifier 또는 CI에 production-realistic integration test 추가 (vault/raw + notes/private 분리 fixture, 실제 stock CLI 호출, vault_root != notes_root 강제).

#### GAP-08: 미사용 디렉토리 정리 — OPEN
- **목록 (조사 필요):**
  - `vault/notes/` — 빈 디렉토리. CLAUDE.md outdated 도식의 잔재. 사용처 없음.
  - `ingested/_status/` (repo root) vs `vault/ingested/_status/` — 후자가 실제 사용. 전자는 legacy.
  - 기타: `find . -type d -empty` 등으로 추가 식별.
- **FIX 방향:** rm -rf 후 .gitignore 정리. tracked였다면 git rm.

---

_Verified: 2026-05-07T15:22:02Z_
_Re-verified during production validation: 2026-05-08T22:30:00+09:00_
_Verifier: Claude (gsd-verifier) + user-driven UAT_
