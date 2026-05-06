# Phase 8: Vault Dashboards & Research Memo Templates — Context

**Gathered:** 2026-05-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Obsidian vault에 사용자의 일일 진입점(`dashboards/portfolio.md`, `dashboards/watchlist.md`, `dashboards/events-this-week.md`)과 티커별 hub 노트(`vault/ingested/by-ticker/{corp_code}.md`)를 자동 생성하고, thesis/journal 노트의 **템플릿 + frontmatter 스키마 + Pydantic 검증**을 git에 커밋한다. 메모 콘텐츠는 모두 `notes/private/` overlay(.gitignored)에 적재되며, frontmatter 필드는 Postgres ingest 인덱스에 1차 동기화 사이클 안에 반영되어 `search` MCP 결과에 raw 문서와 동등하게 등장한다.

이 페이즈가 만지지 않는 것:
- `notes/private/` 콘텐츠 자체 작성(사용자 또는 MCP `add_note`가 수행)
- 신규 raw 수집기, 그래프 edge 추가, MCP 신규 툴(Phase 10 D-23이 별도 처리)
- Phase 10 valuation/supply-demand 신호 산출(hub의 valuation 섹션은 Phase 10 D-12 hook 자리만 마련)
- 일배치 systemd.timer 등록(Phase 9 OPS-01)

</domain>

<decisions>
## Implementation Decisions

### Ticker Hub (DASH-04)

- **D-01:** **Hub 생성 트리거 = ingest worker 자동.** 신규 ticker가 처음 등장하거나 기존 ticker에 새 문서가 인덱싱될 때, ingest worker(`src/ingest/worker.py`)가 hub 갱신 훅을 호출. 별도 CLI 트리거 없음. (Phase 9 OPS-01 일배치 추가 시 자연스럽게 함께 도는 형태)
- **D-02:** **Hub 본문 = 100% 자동 생성/덮어쓰기.** 사용자 자유 메모 zone 없음. 사용자 메모는 별도 파일 `notes/private/{ticker}/notes.md`로 분리(Phase 10 D-18에 이미 정의). Hub는 매 재생성 시 통째로 교체.
- **D-03:** **Hub 자동 섹션 구성:**
  ```
  ---
  type: ticker_hub
  ticker: "005930"
  corp_code: "00126380"
  corp_name: "삼성전자"
  sector: "반도체"
  latest_price: 72000
  market_cap: 430000000000000
  as_of: 2026-05-05
  generated_at: 2026-05-06T03:00:00+09:00
  content_hash: <sha256>
  ---

  # {corp_name} ({ticker})

  > Auto-generated. Edit `notes/private/{ticker}/notes.md` for personal memos.

  ## 최근 공시 (10건)
  ## 최근 뉴스 (10건)
  ## 가격 트렌드 (30일 sparkline)
  ## Valuation  ← Phase 10 D-12 hook (dataview placeholder)
  ## Private Notes
  - [[notes/private/{ticker}/thesis.md]]
  - [[notes/private/{ticker}/conviction.md]]
  - [[notes/private/{ticker}/notes.md]]
  ```
  Sparkline은 ASCII/유니코드 블록 또는 Dataview inline 표(30일 종가). Valuation 섹션은 Phase 10이 채우는 dataview 코드블록 placeholder만 마련.
- **D-04:** **재생성 정책 = 전체 ticker × idempotent.** 매 갱신 시 전 ticker hub를 메모리에서 재구성. content_hash 비교로 변경분만 디스크 write. 변경 없는 hub는 mtime 보존 → git diff/Obsidian sync 노이즈 최소.
- **D-05:** **Hub 디렉토리 = `vault/ingested/by-ticker/{corp_code}.md`** (REQUIREMENTS DASH-04 wording 그대로). corp_code 기반 — Phase 2 D-01 corp_code as PK 정합. 파일명에 ticker 별칭 사용 안 함.

### Portfolio/Watchlist Dashboards (DASH-01, DASH-02)

- **D-06:** **`dashboards/portfolio.md` SoT = `notes/private/portfolio.md`** (Phase 1 D-03/D-05, Phase 10 P-01). Dashboard는 100% Dataview-only, frontmatter inline query로 portfolio.md 표를 읽어 렌더. 사용자 자유 메모 zone 없음.
- **D-07:** **DASH-02 watchlist = `notes/private/portfolio.md`의 `## Watchlist` 표를 SoT로 공유.** 별도 파일 분리 안 함. portfolio.md 한 파일에 holdings + watchlist 동시 관리(현 템플릿 구조 유지).
- **D-08:** **평가액(holdings × 현재가) 데이터 흐름:**
  - **Step 1 — 일배치 가격 dump:** ingest worker(또는 동일 훅에서) `dashboards/_data/prices.md` 파일을 갱신. Frontmatter에 `as_of` (전영업일 거래일자, KST), body에 ticker × `latest_close` 표. 이 파일은 `dashboards/_data/.gitignore` 또는 path 단위 gitignore(콘텐츠는 derived). hub의 `latest_price` frontmatter도 동일 소스에서 채움.
  - **Step 2 — 평가액 계산:** `dashboards/portfolio.md`의 Dataview 쿼리가 portfolio.md holdings × prices.md 가격을 inline join, `eval_value = shares × close` 컬럼으로 표시.
  - **Step 3 — Freshness:** dashboard 상단에 `dashboards/_data/prices.md` frontmatter `as_of` 표시 (예: "전영업일 종가 기준 2026-05-05").
- **D-09:** **DASH-03 events-this-week 집계:**
  - 데이터 출처: `vault/raw/{dart,news,kind}/**/*.md` 문서들의 frontmatter
  - 필터: `provenance.date`가 이번 주(월요일~일요일 KST) AND `_derived.tickers`가 `notes/private/portfolio.md`의 holdings∪watchlist에 포함
  - 정렬: `_derived.event_type` 우선순위(공시 > 거래정지 > 실적 > 뉴스) → 날짜 desc
  - 표시 컬럼: 날짜 | ticker | event_type | title | source | link
  - 100% Dataview 쿼리, 자유 메모 zone 없음

### Note Templates (NOTE-01, NOTE-02, NOTE-03)

- **D-10:** **템플릿 디렉토리 = `templates/notes/`** (Phase 10 P-03 정합). 기존 `templates/portfolio.md`는 `templates/notes/portfolio.md`로 이동(원본 deprecate, Phase 8 plan 첫 task로 atomic 이동).
- **D-11:** **템플릿 파일 (3개 git commit):**
  - `templates/notes/thesis.md` — NOTE-01용
  - `templates/notes/journal.md` — NOTE-02용
  - `templates/notes/portfolio.md` — `templates/portfolio.md` 이동분
- **D-12:** **템플릿 = Plain markdown only.** Templater 통합 안 함(Templater plugin 설치돼 있어도 의존 안 둠). 사용자가 새 노트 만드는 경로:
  - **(주된 경로)** MCP `add_note`(Phase 6 D-09 화이트리스트, Phase 10 D-21 확장: `notes/private/`)로 LLM이 frontmatter 채워 생성. "X 종목 thesis 메모해줘" 한 마디로 자동 적재.
  - (보조 경로) Obsidian Templates **core plugin**(Templater 아님, Obsidian 기본 제공)으로 템플릿 삽입 후 사용자가 frontmatter 수동 채움.
  - (보조 경로) 사용자 직접 복사.
- **D-13:** **Frontmatter 스키마 = Phase 10 D-20 베이스 + thesis 확장 필드:**
  ```yaml
  # 공통 (D-20)
  type: thesis | journal | conviction | note
  tickers: ["005930"]
  tags: [...]
  created: 2026-05-06T15:00:00+09:00
  updated: 2026-05-06T15:00:00+09:00
  author: "yamin"

  # thesis 전용 추가 필드 (Phase 8)
  kill_criteria: []                  # list[str], 트리거 시 thesis 폐기 조건
  conviction: low | medium | high    # 확신도
  target_price: null                 # int|null, 목표가 (KRW)
  ```
  journal은 D-20 그대로(추가 필드 없음). conviction/note는 D-20 공통 필드만.
- **D-14:** **검증 = Pydantic `NoteFrontmatter` 모델** (Phase 6 D-11에서 도입 예정 위치 = `src/shared/frontmatter.py`). Phase 8은 thesis 확장 필드를 위해 `ThesisFrontmatter(NoteFrontmatter)` subclass 추가. ingest 파이프라인이 `notes/private/**/*.md` 파싱 시 이 모델로 검증, 실패 시 `review_flags`에 `note_schema_violation` 기록(Phase 5 D-11 정합).
- **D-15:** **Ingest 인덱싱 = D-22(Phase 10) 정합.** `notes/private/**/*.md`의 thesis/journal/conviction/note 4종 모두 embedding + BM25 + chunks 인덱싱. `provenance.source = "private_note"`, `documents.note_type = type` 컬럼 추가(또는 frontmatter zone). search 결과에 동등 등장.

### Dataview Bootstrap

- **D-16:** **Dataview plugin 부트스트랩 = `.obsidian/community-plugins.json`에 `"dataview"` 항목 추가 + `.obsidian/plugins/dataview/data.json`에 권장 설정 커밋.** 사용자가 vault 처음 열 때 Obsidian이 미설치 plugin 자동 설치 프롬프트.
- **D-17:** **Dataview 권장 설정** (`data.json`):
  ```json
  {
    "enableDataviewJs": false,
    "enableInlineDataview": true,
    "enableInlineDataviewJs": false,
    "renderNullAs": "—",
    "warnOnEmptyResult": true,
    "refreshEnabled": true,
    "refreshInterval": 2500
  }
  ```
  `enableDataviewJs: false` (D-18 정합), `enableInlineDataview: true` (D-08 inline 평가액 계산 필수).
- **D-18:** **DQL only, DataviewJS 미사용.** 모든 dashboard 쿼리는 평문 Dataview Query Language. JS 쿼리 미사용 — 보안/단순성/Phase 8 검증 가능성.
- **D-19:** **Dataview 미설치 fallback = 없음.** 미설치 시 Dataview 코드블록이 raw로 보이는 게 사용자 신호. README/QUICKSTART에 "Phase 8 산출물은 Dataview plugin 필요" 안내 한 줄 추가. 별도 검증 CLI 없음.

### Claude's Discretion

- Dashboard 노트 본문의 마크다운 헤더 wording, 표 컬럼 순서, sparkline 렌더 방식(유니코드 블록 vs ASCII), DQL 쿼리의 정확한 LIMIT/SORT 표현
- ingest worker 안에서 hub 갱신 훅의 정확한 위치/모듈 분리
- `dashboards/_data/prices.md` 외 추가 derived 파일이 필요해질 경우 동일 디렉토리에 추가(예: `_data/sectors.md`)
- Hub 30일 sparkline 데이터 소스(KRX OHLCV 직접 vs prices.md 누적 vs 별도 cache) — 단순성 우선

### Folded Todos

(없음 — `gsd-tools todo match-phase 8`이 0 hits)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 의존성 (앞선 페이즈 결정)
- `.planning/phases/01-load-bearing-foundation/01-CONTEXT.md` — D-03 (`notes/private/` overlay), D-04 (`templates/portfolio.md`), D-05 (portfolio SoT 경로), D-09 (frontmatter zone 분리)
- `.planning/phases/02-canonical-entity-identity/02-CONTEXT.md` — D-01 (corp_code as PK, hub 디렉토리 명명 근거)
- `.planning/phases/05-claude-schedule-enrichment-with-korean-number-safety/05-CONTEXT.md` — D-07 (zone integrity), D-08 (event_type enum, DASH-03 정렬 우선순위), D-11 (`review_flags` 정책)
- `.planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md` — D-09 (`add_note` 화이트리스트), D-10 (append 충돌 정책), D-11 (`NoteFrontmatter` Pydantic 도입 위치 = `src/shared/frontmatter.py`)
- `.planning/phases/07-graph-layer-graphify-integration/07-CONTEXT.md` — Phase 8 책임 경계(Dataview/templates만, 그래프 edge 추가 금지)
- `.planning/phases/10-decision-context-coverage-peer-historical-valuation-supply-d/10-CONTEXT.md` — P-01 (portfolio SoT cutover), P-03 (NOTE-01/02 wording 갱신, `templates/notes/` 디렉토리 신설), D-12 (hub valuation 섹션 hook), D-18 (`notes/private/` 디렉토리 구조), D-19 (Phase 8 분업 = 템플릿/스키마/검증만), D-20 (메모 frontmatter 스키마 베이스), D-21 (`add_note` 화이트리스트 확장), D-22 (private notes ingest 포함)

### 프로젝트 헌법
- `.planning/PROJECT.md` — Core value(4축 통합 판단), vault SoT 원칙
- `.planning/REQUIREMENTS.md` — DASH-01~04, NOTE-01~03 wording (NOTE-01/02 AMENDED 표시 확인), MCP-05 wording (portfolio 경로 단일화)
- `.planning/ROADMAP.md` §Phase 8 — Goal/Success Criteria/UI hint
- `CLAUDE.md` §7.3 Frontmatter schema, §7.1 Dataview required, §7.2 llm-wiki optional

### 기존 코드 (수정/확장 대상)
- `templates/portfolio.md` — D-10에 따라 `templates/notes/portfolio.md`로 이동
- `src/shared/frontmatter.py` (Phase 6 도입 예정) — `NoteFrontmatter` 모델, Phase 8이 `ThesisFrontmatter` subclass 추가
- `src/ingest/worker.py` — D-01 hub 갱신 훅 추가 위치
- `src/ingest/parsers/` — `note.py`(또는 등가) 추가, private notes frontmatter 파싱
- `.obsidian/community-plugins.json`, `.obsidian/plugins/dataview/data.json` — D-16/D-17 부트스트랩 대상

### 외부 명세
- Dataview plugin docs: https://blacksmithgu.github.io/obsidian-dataview/ — DQL 문법, inline query, frontmatter 인덱싱
- Obsidian Templates core plugin — 사용자 가이드 한 줄 (D-12 보조 경로)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/shared/portfolio.py` (Phase 4/Phase 6 cutover 결과) — `Portfolio.load(repo_root)`로 `notes/private/portfolio.md` 파싱. Dashboard ingest 훅이 평가액 계산용 가격 dump 시 같이 활용 가능.
- `src/shared/frontmatter.py` (Phase 6 신규) — `NoteFrontmatter` 베이스. Phase 8 `ThesisFrontmatter` subclass 위치.
- `src/ingest/parsers/dart.py` 등 — frontmatter parser 패턴, `note.py` 추가 시 동일 구조 따름.
- `src/ingest/embedder.py` — D-15 private notes 임베딩 재사용.

### Established Patterns
- **Frontmatter zone 분리** (Phase 1 D-09): `provenance` / `ingest_state` / `_derived` zone 간 cross-write 금지. 메모 노트의 사용자 입력은 frontmatter 최상위(`type`, `tickers`, `tags`, `created`, `updated`, `author`, `kill_criteria` 등) — zone 외부.
- **Pydantic 검증** (Phase 1, Phase 5): 모든 frontmatter는 모델 통과 → 위반 시 `review_flags`.
- **Idempotent rebuild** (Phase 3 ingest): content_hash 비교 후 변경분만 disk write. D-04 hub 재생성에 동일 패턴 차용.
- **Path 화이트리스트** (Phase 6 D-09): `add_note`는 `vault/notes/` ∪ `notes/private/`만 허용. Phase 8은 화이트리스트 변경 없음 — Phase 10 D-21이 이미 확장.

### Integration Points
- **Hub 갱신 훅:** `src/ingest/worker.py` 인덱싱 사이클 종료 시점에 `src/ingest/hub_builder.py`(신규) 호출. hub_builder가 DB에서 ticker별 최근 공시·뉴스·가격을 모아 markdown 생성, content_hash 비교 후 write.
- **가격 dump 훅:** 동일 위치에서 `src/ingest/price_snapshot.py`(신규)가 `dashboards/_data/prices.md` 갱신. KRX 종가 데이터는 Phase 4가 이미 DB에 적재.
- **Note frontmatter 검증:** `src/shared/frontmatter.py`에 `ThesisFrontmatter` subclass 추가. ingest worker가 `notes/private/**/*.md` 파일 만나면 `type` 필드로 디스패치.
- **Phase 10 D-12 hook:** hub의 `## Valuation` 섹션은 빈 dataview placeholder만 작성(예: `\`\`\`dataview\nLIST FROM "" WHERE valuation\n\`\`\``). Phase 10이 실제 쿼리로 교체.

</code_context>

<specifics>
## Specific Ideas

- Hub 30일 sparkline은 유니코드 블록(`▁▂▃▄▅▆▇█`) 7-bin 정규화로 한 줄 표현 시도(가독성). 단순 표가 충분하면 그것도 OK — Claude 재량.
- `dashboards/_data/` 디렉토리는 derived 캐시 모음(향후 sectors.md, signals.md 등 합류 가능). `.gitignore`에 추가 권장(콘텐츠는 vault/raw + DB에서 항상 재생성 가능 — Phase 1 SoT 원칙 정합).
- README QUICKSTART 한 줄 추가: "Open vault in Obsidian → install Dataview plugin when prompted (auto-prompted via .obsidian/community-plugins.json)".
- thesis 템플릿 본문에는 placeholder 섹션 4개 권장: `## 투자 논리`, `## 핵심 가정`, `## Kill Criteria`(frontmatter와 별개로 본문에서도 풀어 쓰기), `## 모니터링 지표`. 사용자가 자유롭게 수정.
- journal 템플릿 본문: `## 오늘의 의사결정`, `## 시장 관찰`, `## 다음 액션`. 일자별 cross-cut 기록.

</specifics>

<deferred>
## Deferred Ideas

- **Body-text NER 기반 `mentions_ticker` 보강** — Phase 7 deferred에 이미 명시. Phase 8 hub는 `_derived.tickers` frontmatter만 사용.
- **다중 사용자 visibility 격리(`chunks.visibility`)** — Phase 10 deferred. 본 페이즈도 개인 vault 가정.
- **Dashboard 위젯/시각화 강화** (charts.js, advanced sparkline) — v2. Phase 8은 Dataview 표 + 단순 sparkline 수준.
- **Templater 통합 자동화** — D-12에서 명시적 거부. v2에서 사용자 요청 있으면 재고려.
- **Hub의 Phase 10 valuation 섹션 실제 쿼리** — Phase 10 D-12 책임. Phase 8은 placeholder만.
- **Hub incremental 재생성 최적화** — D-04는 전체 재생성. ticker 수 수백 개 수준에서 부담 없음. 수천 단위로 늘면 v2 incremental 검토.
- **`stock vault check-deps` CLI** — D-19에서 거부. v2에서 Phase 9 OPS와 함께 재고려 가능.

</deferred>

---

*Phase: 08-vault-dashboards-research-memo-templates*
*Context gathered: 2026-05-06*
