# Phase 8: Vault Dashboards & Research Memo Templates — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-06
**Phase:** 08-vault-dashboards-research-memo-templates
**Areas discussed:** Ticker hub, Portfolio eval data flow, Dashboards C-side, Note templates, Dataview bootstrap

---

## Area A — Ticker Hub (DASH-04)

### A1. 생성 주체/트리거

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | 별도 CLI `stock dashboard rebuild` (idempotent, systemd.timer 등록 가능) | |
| 2 | ingest worker 자동 (신규 ticker/문서 등장 시 hub 갱신) | ✓ |
| 3 | collector 후처리 hook (분산 책임, race condition 위험) | |

**User's choice:** Option 2

### A2. Hub 본문 구조 + 사용자 자유 영역

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | 100% 자동 생성/덮어쓰기. 헤더 + 최근 공시 10 + 뉴스 10 + 가격 sparkline + Phase 10 valuation hook + thesis/journal 링크. 사용자 메모는 별도 `notes/private/{ticker}/notes.md`로 분리 | ✓ |
| 2 | `<!-- USER:START -->...<!-- USER:END -->` zone만 보존 | |
| 3 | 최소 hub: 헤더 + 자동 링크 표만 | |

**User's choice:** Option 1

### A3. 재생성 범위/정책

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | 전체 ticker × idempotent 전체 재생성, content_hash 비교로 변경분만 disk write | ✓ |
| 2 | 변경된 ticker만 incremental | |

**User's choice:** Option 1

---

## Area B — DASH-01 평가액 데이터 흐름

### B1. 가격/평가액 캐시 위치

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | 티커 hub frontmatter에 `latest_price`/`as_of` 박기 + portfolio.md가 hub들 inline query | |
| 2 | 별도 `dashboards/_data/prices.md` 일배치 dump | ✓ |
| 3 | portfolio.md 자체에 가격 컬럼 갱신 (SoT 덮어쓰기 위험) | |

**User's choice:** Option 2

### B2. 평가액 계산 위치

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Dataview inline 계산 (`shares × price`) | ✓ |
| 2 | ingest worker가 portfolio.md frontmatter에 `evaluated_value` 박기 | |
| 3 | 별도 `dashboards/_data/portfolio_eval.md` 캐시 | |

**User's choice:** Option 1

### B3. 가격 신선도(freshness) 표기

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Frontmatter `as_of` 기반 ("전영업일 종가 기준 YYYY-MM-DD") | ✓ |
| 2 | 시간만 표시 (HH:MM) | |
| 3 | 신선도 표기 안 함 | |

**User's choice:** Option 1
**Notes:** B1=2 선택 따라 `as_of`는 hub가 아니라 `dashboards/_data/prices.md` frontmatter에서 읽도록 정합화.

---

## Area C — DASH-02/03 + 자유 메모 zone

### C1. DASH-02 watchlist 데이터 출처

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | `notes/private/portfolio.md`의 `## Watchlist` 표를 SoT로 사용 (단일 파일) | ✓ |
| 2 | 별도 `notes/private/watchlist.md` 분리 | |
| 3 | 티커 hub frontmatter `watchlist: true` 플래그 + Dataview FROM hub | |

**User's choice:** Option 1

### C2. DASH-03 events-this-week 집계 범위/강조

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | `vault/raw/{dart,news,kind}/` × 이번 주 × holdings∪watchlist 포함, event_type 우선순위 정렬 | ✓ |
| 2 | 모든 ticker × 이번 주 (노이즈 큼) | |
| 3 | holdings만 (watchlist 누락) | |

**User's choice:** Option 1

### C3. 사용자 자유 메모 zone 보호

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | dashboards 100% Dataview-only, 자유 메모 zone 없음. 메모는 `notes/private/journal/`로 분리 | ✓ |
| 2 | HTML 주석 zone 보존 (`<!-- USER:START/END -->`) | |
| 3 | dashboard 위쪽만 사용자 영역, 아래 Dataview 섹션 분리 | |

**User's choice:** Option 1

---

## Area D — 템플릿 사용성 (NOTE-01/02)

### D1. 새 thesis/journal 노트 생성 흐름

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Plain markdown 템플릿만. 사용자는 Obsidian Templates core plugin 또는 MCP `add_note`로 생성 | ✓ |
| 2 | Templater 스크립트 통합 (frontmatter 자동 채움) | |
| 3 | CLI `stock note new thesis 005930` | |

**User's choice:** Option 1

### D2. 템플릿 frontmatter 필드 (Phase 10 D-20 스키마 위에 추가)

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | D-20 그대로 + thesis만 `kill_criteria: []`, `conviction`, `target_price: null` | ✓ |
| 2 | 더 많은 필드 (entry_date, time_horizon, position_size_target) | |
| 3 | 최소 필드만 (type/tickers/created) | |

**User's choice:** Option 1

### D3. `templates/portfolio.md` 처리

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | `templates/notes/portfolio.md`로 이동 (P-03 정합) | ✓ |
| 2 | 그대로 유지 | |
| 3 | 양쪽 유지 | |

**User's choice:** Option 1

---

## Area E — Dataview 부트스트랩

### E1. 부트스트랩 방법

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | `.obsidian/community-plugins.json` + `data.json` 권장 설정 커밋. 사용자 vault 처음 열 때 Obsidian이 자동 설치 프롬프트 | ✓ |
| 2 | README 가이드만 | |
| 3 | `stock vault check-deps` CLI 강제 검증 | |

**User's choice:** Option 1

### E2. Dataview 미설치 fallback

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | fallback 없음 — README 안내 한 줄 | ✓ |
| 2 | dashboard 상단에 `> Requires Dataview plugin` 안내 | |

**User's choice:** Option 1

### E3. DataviewJS 사용 여부

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | DQL only, DataviewJS 미사용 | ✓ |
| 2 | 필요 시 DataviewJS 허용 | |

**User's choice:** Option 1
**Notes:** E1 권장 설정에서 `enableDataviewJs: false`로 정합화 (E3 정합).

---

## Claude's Discretion

- Dashboard 노트 본문의 마크다운 헤더 wording, 표 컬럼 순서
- Sparkline 렌더 방식 (유니코드 블록 vs ASCII vs 표)
- DQL 쿼리의 정확한 LIMIT/SORT 표현
- ingest worker 안에서 hub 갱신 훅의 정확한 위치/모듈 분리
- Hub 30일 sparkline 데이터 소스 (KRX OHLCV 직접 vs prices.md 누적 vs 별도 cache)
- `dashboards/_data/` 외 추가 derived 파일이 필요한 경우 동일 디렉토리 추가

## Deferred Ideas

- Body-text NER `mentions_ticker` 보강 (Phase 7 deferred 그대로)
- 다중 사용자 visibility 격리 (Phase 10 deferred 그대로)
- Dashboard 시각화 강화 (charts.js 등) — v2
- Templater 통합 자동화 — v2
- Hub valuation 섹션 실제 쿼리 — Phase 10 D-12 책임
- Hub incremental 재생성 최적화 — 수천 ticker 단위로 늘면 v2
- `stock vault check-deps` CLI — v2 Phase 9 OPS와 함께
