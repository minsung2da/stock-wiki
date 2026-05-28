# Phase 8: Vault Dashboards & Research Memo Templates — Research

**Researched:** 2026-05-06
**Domain:** Obsidian Dataview DQL, vault frontmatter schema design, ingest worker hook integration
**Confidence:** HIGH (CONTEXT.md가 의사결정을 잠근 상태 — 본 연구는 검증·구현 패턴 위주)

## Summary

Phase 8은 신규 데이터 모델/MCP 툴/그래프 작업 없이, **(a) Dataview 기반 자동 dashboard 3종**, **(b) ingest worker가 갱신하는 ticker hub 노트**, **(c) thesis/journal 등 메모 템플릿 + Pydantic frontmatter 검증**, **(d) `notes/private/**/*.md` 메모를 기존 ingest 파이프라인이 1차 사이클 안에 인덱싱**의 4축으로 구성된다. 핵심 신규 코드는 단 3 모듈 — `src/ingest/hub_builder.py`, `src/ingest/price_snapshot.py`, `src/ingest/parsers/note.py` — 이며 모두 기존 Phase 3/5/6 패턴(content_hash idempotent rebuild, Pydantic `extra=forbid`, zone integrity)을 그대로 차용한다.

CONTEXT.md(D-01~D-19)가 이미 거의 모든 구현 결정을 잠갔으므로 본 RESEARCH는 (1) 잠긴 결정의 외부 검증, (2) Dataview DQL 정확한 작성 패턴, (3) idempotency·인제스트 통합 함정을 정리하는 데 집중한다.

**Primary recommendation:** Phase 8 plan 분해는 **(P1) 템플릿+frontmatter 스키마+note 파서**, **(P2) hub_builder + price_snapshot + worker 훅**, **(P3) Dataview dashboards 3종 + plugin 부트스트랩**, **(P4) E2E "thesis 작성 → 1 ingest cycle → search 결과에 등장" 검증** 으로 가는 4-plan 분할이 자연스럽다.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Ticker Hub (DASH-04)**
- **D-01**: Hub 생성 트리거 = ingest worker 자동. 별도 CLI 없음. (`src/ingest/worker.py` 인덱싱 사이클 종료 시점에 훅)
- **D-02**: Hub 본문 = 100% 자동 생성/덮어쓰기. 사용자 자유 메모 zone 없음. 사용자 메모는 `notes/private/{ticker}/notes.md`로 분리.
- **D-03**: Hub 자동 섹션 구성 = frontmatter(`type: ticker_hub`, `ticker`, `corp_code`, `corp_name`, `sector`, `latest_price`, `market_cap`, `as_of`, `generated_at`, `content_hash`) + 본문(`최근 공시 10건` / `최근 뉴스 10건` / `가격 트렌드 30일 sparkline` / `Valuation` Phase 10 placeholder / `Private Notes` 링크).
- **D-04**: 재생성 정책 = 전체 ticker × idempotent. 매 갱신 시 전 ticker hub를 메모리에서 재구성. content_hash 비교로 변경분만 disk write. 변경 없는 hub는 mtime 보존.
- **D-05**: Hub 디렉토리 = `vault/ingested/by-ticker/{corp_code}.md` (corp_code 기반, ticker 별칭 사용 안 함).

**Portfolio/Watchlist Dashboards (DASH-01, DASH-02, DASH-03)**
- **D-06**: `dashboards/portfolio.md` SoT = `notes/private/portfolio.md`. Dashboard는 100% Dataview-only, frontmatter inline query로 portfolio.md 표를 읽어 렌더. 사용자 자유 메모 zone 없음.
- **D-07**: DASH-02 watchlist = `notes/private/portfolio.md`의 `## Watchlist` 표를 SoT로 공유. 별도 파일 분리 안 함.
- **D-08**: 평가액 데이터 흐름 = 일배치 가격 dump(`dashboards/_data/prices.md`, frontmatter `as_of` + ticker × `latest_close` 표) → Dataview inline join(holdings × prices) → `eval_value = shares × close` 컬럼 → dashboard 상단에 `as_of` 표시.
- **D-09**: DASH-03 = `vault/raw/{dart,news,kind}/**/*.md` frontmatter에서 `provenance.date` 이번 주(KST 월~일) AND `_derived.tickers ∈ holdings∪watchlist` 필터, `event_type` 우선순위(공시>거래정지>실적>뉴스)→날짜 desc 정렬, 표 컬럼: 날짜|ticker|event_type|title|source|link.

**Note Templates (NOTE-01, NOTE-02, NOTE-03)**
- **D-10**: 템플릿 디렉토리 = `templates/notes/`. 기존 `templates/portfolio.md`는 `templates/notes/portfolio.md`로 atomic 이동 (Phase 8 첫 task).
- **D-11**: 템플릿 파일 3개 git commit: `templates/notes/thesis.md`, `templates/notes/journal.md`, `templates/notes/portfolio.md`.
- **D-12**: 템플릿 = Plain markdown only. Templater 통합 안 함. 주된 작성 경로 = MCP `add_note`(Phase 6 D-09 + Phase 10 D-21 화이트리스트). 보조 경로 = Obsidian Templates **core plugin** + 사용자 직접 복사.
- **D-13**: Frontmatter 스키마 = Phase 10 D-20 베이스 + thesis 확장:
  ```yaml
  # 공통
  type: thesis | journal | conviction | note
  tickers: ["005930"]
  tags: [...]
  created: 2026-05-06T15:00:00+09:00
  updated: 2026-05-06T15:00:00+09:00
  author: "yamin"
  # thesis 전용 추가 필드
  kill_criteria: []                  # list[str]
  conviction: low | medium | high
  target_price: null                 # int|null, KRW
  ```
  journal/conviction/note는 공통 필드만.
- **D-14**: 검증 = `src/shared/frontmatter.py`에 `NoteFrontmatter` 베이스(Phase 6 D-11). Phase 8은 `ThesisFrontmatter(NoteFrontmatter)` subclass 추가. ingest 파이프라인이 `notes/private/**/*.md` 파싱 시 모델로 검증, 실패 시 `review_flags`에 `note_schema_violation` 기록.
- **D-15**: Ingest 인덱싱 = `notes/private/**/*.md`의 4종 모두 embedding + BM25 + chunks 인덱싱. `provenance.source = "private_note"`, `documents.note_type = type` 컬럼 추가(또는 frontmatter zone). search 결과에 raw 문서와 동등 등장.

**Dataview Bootstrap**
- **D-16**: `.obsidian/community-plugins.json`에 `"dataview"` 추가 + `.obsidian/plugins/dataview/data.json` 권장 설정 커밋.
- **D-17**: 권장 설정 = `enableDataviewJs: false`, `enableInlineDataview: true`, `enableInlineDataviewJs: false`, `renderNullAs: "—"`, `warnOnEmptyResult: true`, `refreshEnabled: true`, `refreshInterval: 2500`.
- **D-18**: DQL only, DataviewJS 미사용 (보안/단순성).
- **D-19**: Dataview 미설치 fallback 없음. README/QUICKSTART에 안내 한 줄. 별도 검증 CLI 없음.

### Claude's Discretion

- Dashboard 노트 본문의 마크다운 헤더 wording, 표 컬럼 순서
- Sparkline 렌더 방식(유니코드 블록 vs ASCII)
- DQL 쿼리의 정확한 LIMIT/SORT 표현
- ingest worker 안에서 hub 갱신 훅의 정확한 위치/모듈 분리
- `dashboards/_data/prices.md` 외 추가 derived 파일이 필요해질 경우 동일 디렉토리에 추가
- Hub 30일 sparkline 데이터 소스(KRX OHLCV 직접 vs prices.md 누적 vs 별도 cache)

### Deferred Ideas (OUT OF SCOPE)

- Body-text NER `mentions_ticker` 보강 — Phase 7 deferred
- 다중 사용자 visibility 격리 (`chunks.visibility`) — Phase 10 deferred
- Dashboard 위젯/시각화 강화 (charts.js, advanced sparkline) — v2
- Templater 통합 자동화 — D-12 명시적 거부
- Hub Phase 10 valuation 섹션 실제 쿼리 — Phase 10 D-12 책임 (Phase 8은 placeholder만)
- Hub incremental 재생성 최적화 — D-04 전체 재생성 채택, ticker 수천 단위에서 v2 검토
- `stock vault check-deps` CLI — D-19에서 거부
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description (REQUIREMENTS.md) | Research Support |
|----|------------------------------|------------------|
| DASH-01 | `dashboards/portfolio.md`가 보유 종목·평가액·최근 이벤트 요약을 Dataview 쿼리로 자동 표시 | §Architecture Patterns "Dashboard 1: portfolio.md" + §Code Examples DQL 스니펫 + D-06/D-08 |
| DASH-02 | `dashboards/watchlist.md`가 관심 종목 상태를 표시 | §Architecture Patterns "Dashboard 2: watchlist.md" + D-07 (portfolio.md `## Watchlist` 표 공유) |
| DASH-03 | `dashboards/events-this-week.md`가 이번 주 주요 공시·뉴스·거래정지 집계 | §Architecture Patterns "Dashboard 3: events-this-week.md" + D-09 + DQL FLATTEN 패턴 |
| DASH-04 | 티커별 hub 노트(`ingested/by-ticker/{corp_code}.md`) 자동 생성 | §Architecture Patterns "hub_builder" + D-01~D-05 + idempotent rebuild 패턴 (Phase 3 차용) |
| NOTE-01 | `templates/notes/thesis.md` + `notes/private/{ticker}/thesis.md` 생성, kill criteria 포함 | §Code Examples thesis template + D-13 ThesisFrontmatter |
| NOTE-02 | `templates/notes/journal.md` + `notes/private/journal/YYYY-MM-DD.md` | §Code Examples journal template + D-13 공통 스키마 |
| NOTE-03 | 메모 frontmatter `tickers[]`, `tags[]`, `created`, `author` DB 인덱싱 | §Architecture Patterns "Note ingest path" + D-14/D-15 + Phase 5 review_flags 패턴 |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Vault SoT 원칙:** Markdown + YAML frontmatter가 유일한 source of truth. DB는 인덱스·캐시. → Hub와 derived dashboards(`_data/prices.md`)도 vault에서 항상 재생성 가능해야 함. **Plan 시 `dashboards/_data/`는 .gitignore 등록 필수**.
- **Layer 규칙:** `collectors/` → raw만. `_derived` 추출은 Claude Schedule이 수행. **Phase 8은 `ingest/`에 Hub 빌더 추가 — collectors가 아님 (가격 dump도 ingest 훅에서, 별도 collector 신규 추가 없음).**
- **`anthropic`/`openai` import 금지:** `src/ingest/`, `src/collectors/`. Phase 8 신규 모듈(`hub_builder.py`, `price_snapshot.py`, `parsers/note.py`)도 동일. CI guard COLL-07 적용.
- **GSD 워크플로우 강제:** Edit/Write 전 GSD 진입점 통과. Phase 8 plan들은 `/gsd-execute-phase`로 실행.
- **한글 응답:** 모든 응답 한글 작성, 코드/경로/기술 용어는 원문.

## Standard Stack

### Core (이미 설치됨, 신규 의존성 없음)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `obsidian-dataview` | ≥ 0.5 (latest 0.5.x) | Dashboard DQL 렌더 | CLAUDE.md §7.1 강제. Phase 8 산출물 가시성의 유일한 경로 (D-19 fallback 없음) |
| `pydantic` v2 | (기존) | NoteFrontmatter / ThesisFrontmatter 검증 | Phase 1/5에서 이미 채택, `extra=forbid` 패턴 정착 |
| `python-frontmatter` | (기존) | YAML zone 분리 read/write | `src/shared/frontmatter.py` 이미 사용 |
| `sentence-transformers` (bge-m3) | (기존) | 메모 본문 임베딩 (D-15) | Phase 3에서 채택, ingest worker 재사용 |
| `mecab-ko` (`python-mecab-ko`) | (기존) | 메모 본문 BM25 토큰 (D-15) | Phase 3에서 채택, ingest worker 재사용 |

[VERIFIED: 기존 코드베이스 grep — `src/ingest/embedder.py`, `src/ingest/tokenizer.py`, `src/shared/frontmatter.py` 모두 존재]

### Supporting (Phase 8 신규)

| Module | Purpose | When |
|--------|---------|------|
| `src/ingest/hub_builder.py` (신규) | DB → ticker hub markdown 생성 + content_hash diff write | ingest 사이클 종료 후 호출 (`worker.py` 훅) |
| `src/ingest/price_snapshot.py` (신규) | DB → `dashboards/_data/prices.md` 갱신 (`as_of` + ticker×close 표) | hub_builder와 동일 위치에서 호출 |
| `src/ingest/parsers/note.py` (신규) | `notes/private/**/*.md` 파싱 + ThesisFrontmatter 디스패치 | worker가 source=`private_note` 분기 |
| `src/shared/frontmatter.py` (확장) | `NoteFrontmatter` (Phase 6 D-11이 도입 예정), `ThesisFrontmatter(NoteFrontmatter)` subclass | Plan 1에서 정의 후 Plan 2에서 ingest 연결 |

### Alternatives Considered (CONTEXT가 잠궜으나 기록)

| Instead of | Could Use | Tradeoff (왜 채택 안 함) |
|------------|-----------|--------------------------|
| ingest worker 자동 hub 갱신 (D-01) | 별도 `stock vault rebuild-hubs` CLI | 사용자가 명시적으로 호출하지 않으면 stale. D-01의 "함께 도는" 결정이 단순. |
| Hub 본문 100% 덮어쓰기 (D-02) | `<!-- AUTO:BEGIN -->...<!-- AUTO:END -->` 마커 + 자유 zone | 마커 무결성 검사 + zone collision 처리 코드 폭증. 사용자 메모는 `notes/private/{ticker}/notes.md`로 분리. |
| DQL only (D-18) | DataviewJS | XSS/실수 가능성, JS 안 쓰면 vault 신뢰 경계 단순. 평가액 inline join은 DQL FLATTEN으로 충분. |
| Pydantic ThesisFrontmatter subclass (D-14) | 단일 NoteFrontmatter + Optional 필드 | Subclass가 thesis-only 필드(kill_criteria/conviction/target_price)의 의도를 명확히 표현. Phase 5 ReviewFlag 패턴 정합. |
| `dashboards/_data/prices.md` derived 파일 (D-08) | Dataview가 직접 DB 조회 (DataviewJS) | D-18에서 거부. Markdown derived 캐시는 git diff 가시성 + DataviewJS 무사용 두 마리 토끼. |

**No installation step needed** — 기존 의존성으로 충분.

## Architecture Patterns

### Recommended Module Layout

```
src/
├── ingest/
│   ├── worker.py              # 기존 — Phase 8: 사이클 종료부에 hub_builder.run() + price_snapshot.run() 호출
│   ├── hub_builder.py         # 신규 — DB query → markdown render → content_hash diff write
│   ├── price_snapshot.py      # 신규 — DB OHLCV → dashboards/_data/prices.md 갱신
│   └── parsers/
│       ├── dart.py            # 기존
│       └── note.py            # 신규 — notes/private/**/*.md frontmatter 디스패치
├── shared/
│   └── frontmatter.py         # 확장 — NoteFrontmatter, ThesisFrontmatter
templates/
└── notes/                     # 신규 디렉토리 — D-10/D-11
    ├── thesis.md
    ├── journal.md
    └── portfolio.md           # 기존 templates/portfolio.md에서 atomic 이동
dashboards/
├── portfolio.md               # 신규 — DQL only
├── watchlist.md               # 신규 — DQL only
├── events-this-week.md        # 신규 — DQL only
└── _data/                     # 신규 — derived cache (.gitignore 권장)
    └── prices.md
vault/
└── ingested/
    └── by-ticker/             # 신규 — corp_code별 hub
        └── {corp_code}.md
.obsidian/
├── community-plugins.json     # 확장 — "dataview" 추가
└── plugins/
    └── dataview/
        └── data.json          # 신규 — D-17 권장 설정
```

### Pattern 1: Hub Idempotent Rebuild (Phase 3 차용)

**What:** 매 ingest 사이클 종료 후 전 ticker hub를 메모리에서 재구성, content_hash 비교 후 변경분만 disk write.
**When to use:** D-01 + D-04 결합. Phase 3 ingest의 `ON CONFLICT DO UPDATE` 패턴 연장.

```python
# src/ingest/hub_builder.py (스케치)
# Source: Phase 3 STORE-02 content-hash dedup 패턴 차용
def render_hub(corp_code: str, db_data: HubInputs) -> tuple[str, str]:
    """Return (markdown, content_hash). Pure function."""
    body = _format_hub_markdown(db_data)  # frontmatter zone + 4 sections
    content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return body, content_hash

def write_hub_if_changed(path: Path, body: str, content_hash: str) -> bool:
    """Write only if content_hash differs from existing. Preserves mtime when unchanged."""
    if path.exists():
        existing = read_frontmatter(path)
        if existing.get("content_hash") == content_hash:
            return False  # mtime 보존 — git/Obsidian sync 노이즈 회피
    atomic_write(path, body)  # tmp + rename
    return True
```

**Critical detail:** `content_hash`는 frontmatter `generated_at`을 **제외한** body 위에 계산해야 한다. 그렇지 않으면 매번 hash가 바뀌어 idempotency가 깨진다. → Phase 5 zone integrity SHA 패턴(yaml.safe_dump sort_keys=True 위 SHA) 정합. [CITED: STATE.md "Plan 05-08: Zone-integrity SHA256 over yaml.safe_dump(provenance)+yaml.safe_dump(ingest_state) — deterministic sort_keys=True payload"]

### Pattern 2: Dataview DQL with Nested Frontmatter

**What:** Phase 1 D-09 frontmatter zone 분리 → DQL는 dot notation 으로 nested 키 접근. `provenance.source`, `_derived.tickers`.
**When to use:** dashboard 3종 모두.

```dataview
TABLE
  provenance.date AS "날짜",
  _derived.tickers AS "티커",
  _derived.event_type AS "이벤트",
  file.link AS "문서"
FROM "vault/raw/dart" OR "vault/raw/news" OR "vault/raw/kind"
WHERE provenance.date >= date(today) - dur(7 days)
  AND contains(_derived.tickers, this.holdings)
SORT provenance.date DESC
```

[VERIFIED: Dataview docs — TABLE/FROM/SORT 구조] [CITED: https://blacksmithgu.github.io/obsidian-dataview/queries/structure/]

**Critical pitfall:** `_derived.tickers`가 list 타입이면 `contains()` 또는 `FLATTEN`을 거쳐야 한다 (단일 row가 아닌 multi-ticker doc). [CITED: https://blacksmithgu.github.io/obsidian-dataview/queries/structure/ — FLATTEN clause]

### Pattern 3: Inline DQL Join (DASH-01 평가액)

**What:** D-08 평가액 계산 = portfolio.md holdings × prices.md inline join.

```dataview
TABLE WITHOUT ID
  ticker AS "티커",
  name AS "종목명",
  shares AS "수량",
  default(prices[ticker], 0) AS "현재가",
  shares * default(prices[ticker], 0) AS "평가액"
FROM "notes/private/portfolio.md"
FLATTEN file.lists AS holding
WHERE holding.section = "Holdings"
```

**Critical pitfall:** Dataview는 markdown 표를 **field 인덱싱하지 않는다**. → 두 가지 회피책 중 택1:
1. `notes/private/portfolio.md`의 holdings를 frontmatter `holdings:` 리스트(YAML)로도 미러 (D-06/Phase 1 D-05 정합 — Portfolio.load이 이미 markdown 표를 파싱하므로 mirror 불필요한지 plan 단계에서 검토)
2. `dashboards/_data/portfolio_holdings.md`도 derived로 매 ingest 시 dump (D-08 prices.md와 동일 패턴 확장)

→ **권장:** 옵션 2. `Portfolio.load`(`src/shared/portfolio.py`) 결과를 `dashboards/_data/portfolio_holdings.md` frontmatter에 dump → Dataview가 frontmatter list를 인덱싱하므로 join 가능. Claude 재량 영역(CONTEXT "추가 derived 파일 필요 시 동일 디렉토리에 추가")에 정합.

### Pattern 4: Note Ingest Path (NOTE-03)

**What:** `notes/private/**/*.md` → `parsers/note.py` 디스패치 → ThesisFrontmatter 검증 → 기존 chunking/embedder/tokenizer 재사용 → `documents.source = "private_note"`, `documents.note_type = frontmatter.type` 컬럼 INSERT.

```python
# src/ingest/parsers/note.py (스케치)
def parse_note(path: Path) -> ParsedNote:
    fm = read_frontmatter(path)
    note_type = fm.get("type", "note")
    model_cls = THESIS_MODEL_BY_TYPE.get(note_type, NoteFrontmatter)
    try:
        validated = model_cls.model_validate(fm)
    except ValidationError as e:
        # Phase 5 D-11 정합 — review_flags 기록, 본문 인덱싱은 계속
        record_review_flag(path, flag="note_schema_violation", detail=str(e))
        validated = None
    sections = [Section(title="", path=path.stem, text=path.read_text(), order=0)]
    return ParsedNote(frontmatter=validated, sections=sections, note_type=note_type)
```

**Migration needed:** `documents.note_type` 컬럼 추가 → Alembic 0005 (또는 Phase 6 0003 follow-up). Plan 시 검증.

### Anti-Patterns to Avoid

- **DataviewJS 사용** — D-18에서 명시적으로 금지. 보안/단순성.
- **Hub에 사용자 자유 메모 zone 추가** — D-02. 사용자 메모는 `notes/private/{ticker}/notes.md` 별도 파일.
- **`vault/raw/` 또는 `vault/ingested/`에 `add_note` write 허용** — Phase 6 D-09 화이트리스트 위반. Hub는 ingest worker만 write.
- **Hub `generated_at`을 content_hash 계산에 포함** — 매 사이클 hash 변경 → idempotency 파괴.
- **portfolio.md를 `templates/notes/`로 이동하면서 git history 단절** — `git mv` 사용 (atomic 이동).
- **`dashboards/_data/`를 git commit** — derived 캐시. .gitignore 등록 필수 (CLAUDE.md SoT 원칙).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Markdown 표 → 데이터 join | 자체 markdown table parser in Python | Frontmatter list + Dataview inline DQL | Dataview는 frontmatter list/object를 직접 인덱싱; 표는 인덱싱 안 함 |
| Frontmatter YAML 파싱 | `yaml.safe_load` 직접 | `src/shared/frontmatter.py` `read_frontmatter` | 3-zone 분리 + Pydantic 검증 + Phase 1 정합 이미 구현 |
| Hub content-hash idempotency | 자체 mtime 비교 + diff merge | sha256 over canonical body, body.startswith frontmatter excluded from hash | Phase 3 STORE-02 패턴 정확히 동일 |
| Atomic file write (race-free) | `open("w")` 직접 | 기존 `atomic_write` 헬퍼 (Phase 5 사용) | Windows/WSL 동시 수정 안전성 |
| Korean tokenization for memo BM25 | 자체 mecab wrapper | `src/ingest/tokenizer.py` `tokenize_ko` | 이미 검증된 mecab-ko 통합 |
| Memo 임베딩 | 새 모델 로드 | `src/ingest/embedder.py` `Embedder` | bge-m3 instance worker에서 공유 — 메모리 재로드 회피 |
| Dataview plugin auto-install | 자체 부트스트랩 스크립트 | `.obsidian/community-plugins.json`에 "dataview" 추가 | Obsidian이 vault 첫 오픈 시 자동 프롬프트 [VERIFIED: D-16 결정 + Obsidian 표준 동작] |

**Key insight:** Phase 8은 신규 라이브러리·새 인프라가 0에 가까운 페이즈다. 모든 신규 코드는 기존 ingest 파이프라인의 leaf utility를 호출하는 얇은 글루 코드로 끝나야 한다.

## Common Pitfalls

### Pitfall 1: Hub `generated_at` content_hash 오염
**What goes wrong:** Hub 매 사이클마다 hash가 바뀌어 disk write 발생 → git diff 노이즈 + Obsidian sync 노이즈.
**Why:** `generated_at: now()`을 hash 계산 페이로드에 포함시키면 발생.
**How to avoid:** content_hash는 (a) generated_at + content_hash 두 필드를 **제외한** frontmatter + body 위에 sha256. Phase 5 zone integrity SHA 패턴 그대로 차용. [CITED: STATE.md Plan 05-08]
**Warning signs:** `git status`에서 hub 파일이 매 ingest마다 modified로 잡힘.

### Pitfall 2: `notes/private/` ingest 시 `add_note` 화이트리스트 충돌 추정
**What goes wrong:** Phase 6 D-09 화이트리스트가 `vault/notes/`만 허용한다고 잘못 가정 → Phase 8에서 `notes/private/` 메모를 ingest 못 시킴.
**Why:** Phase 10 D-21이 화이트리스트를 `vault/notes/` ∪ `notes/private/`로 **이미 확장**했다 (CONTEXT 명시). Phase 8은 화이트리스트 변경 없음 — 기존 확장을 그대로 사용.
**How to avoid:** Plan 시 `src/stock_mcp/tools/add_note.py` (또는 등가) 화이트리스트 코드 grep으로 확인. `notes/private/`이 실제로 포함되어 있는지 검증. [VERIFIED 필요: 코드베이스에 Phase 10 D-21이 이미 적용되었는지 — Plan Wave 0 probe로 확인]

### Pitfall 3: Dataview가 markdown 표를 인덱싱 못 함
**What goes wrong:** `notes/private/portfolio.md`의 markdown 표 holdings를 dashboard에서 직접 join 시도 → 결과 비어 있음.
**Why:** Dataview는 frontmatter (YAML) + inline `key:: value` + tags + file metadata만 인덱싱. Markdown 표 셀은 인덱싱 안 됨.
**How to avoid:** Pattern 3 옵션 2 — `dashboards/_data/portfolio_holdings.md` derived 파일 추가 (frontmatter list).
**Warning signs:** DQL 결과가 항상 빈 표.

### Pitfall 4: Pydantic `extra=forbid` 위반으로 모든 메모 reject
**What goes wrong:** 사용자 또는 MCP `add_note`가 frontmatter에 추가 키(예: `mood`, `weather`)를 넣으면 ValidationError → 메모 전체가 인덱싱 거부.
**Why:** Phase 5에서 `extra=forbid` 채택했음. NoteFrontmatter도 같은 정책 따라가면 사용자 자유 필드를 막음.
**How to avoid:** D-15는 검증 실패 시 `review_flags`에 기록하고 **본문은 인덱싱 계속**한다고 명시. `extra=forbid`보다는 **Pydantic `extra="allow"` + 알려진 필드는 명시적 검증** 또는 `extra="forbid"` + try/except로 review_flags 기록. CONTEXT D-14 "실패 시 review_flags" 명시.
**Warning signs:** `vault/ingested/_status/heartbeat.md`에 `note_schema_violation` 카운트가 비정상적으로 높음.

### Pitfall 5: corp_code 미부여 ticker → hub 디렉토리 collision
**What goes wrong:** D-05 hub 경로 = `vault/ingested/by-ticker/{corp_code}.md`. corp_code 없는 신규 종목 또는 entity_aliases 시드 미흡 ticker는 hub 생성 불가.
**Why:** Phase 2 D-01 corp_code as PK 정합. portfolio.md watchlist에 ticker만 추가하고 entities seed가 안 됐으면 발생.
**How to avoid:** CLAUDE.md First-time Setup 4.5 (`uv run python -m src.db.seed_entities`)을 hub_builder가 시작할 때 검증. corp_code 미해결 ticker는 review_flags 기록 + 사용자 안내 (heartbeat).
**Warning signs:** 일부 watchlist ticker hub가 누락됨.

### Pitfall 6: `dashboards/_data/prices.md` git commit
**What goes wrong:** Derived 캐시인데 git에 들어가면 daily diff 폭주.
**Why:** D-08 prices.md는 일배치마다 갱신. 매일 N개 ticker 가격이 변경되어 git commit 만들어짐.
**How to avoid:** Plan 첫 task에서 `.gitignore`에 `dashboards/_data/` 추가. CLAUDE.md SoT 원칙 정합.
**Warning signs:** `git log dashboards/_data/`가 매일 커밋 표시.

### Pitfall 7: ingest 사이클 hub 갱신이 무거워짐
**What goes wrong:** D-04 "전체 ticker × idempotent" — 수십~수백 ticker 모두 매번 메모리 재구성 → 사이클 시간 증가.
**Why:** Phase 8은 incremental 최적화 deferred (CONTEXT). 수천 ticker로 가면 부담.
**How to avoid:** Plan 시 hub_builder 호출에 budget 측정(예: < 5초 / 100 ticker on fixture). 임계 초과 시 deferred 항목 v2 escalation. 현 스케일(수십~수백)에서는 비이슈.
**Warning signs:** ingest worker p95 latency가 hub 추가 후 30%+ 증가.

## Code Examples

### Example 1: thesis.md template

```markdown
---
type: thesis
tickers: ["005930"]
tags: []
created: 2026-05-06T15:00:00+09:00
updated: 2026-05-06T15:00:00+09:00
author: "yamin"
kill_criteria: []
conviction: medium
target_price: null
---

# {ticker} Thesis

## 투자 논리

(왜 매수했는가 — 1-3개 핵심 논리)

## 핵심 가정

- 가정 1
- 가정 2

## Kill Criteria

frontmatter `kill_criteria`와 같은 내용을 풀어 작성. 어떤 사실이 관측되면 thesis를 폐기하는가?

## 모니터링 지표

- DART 공시 키워드:
- 분기 실적 임계:
- 거시 환경 변수:
```

### Example 2: journal.md template

```markdown
---
type: journal
tickers: []
tags: []
created: 2026-05-06T15:00:00+09:00
updated: 2026-05-06T15:00:00+09:00
author: "yamin"
---

# {date} Journal

## 오늘의 의사결정

## 시장 관찰

## 다음 액션
```

### Example 3: dashboards/portfolio.md (DQL skeleton)

```markdown
---
title: Portfolio
---

> 가격 기준일: `= this.file.frontmatter.as_of` (자동 갱신)

## Holdings × 평가액

\`\`\`dataview
TABLE WITHOUT ID
  ticker AS "티커",
  name AS "종목명",
  shares AS "수량",
  avg_cost AS "평단",
  default(latest_close, "—") AS "현재가",
  shares * default(latest_close, 0) AS "평가액"
FROM "dashboards/_data"
WHERE file.name = "portfolio_holdings"
FLATTEN holdings AS h
\`\`\`

## 보유 종목 최근 7일 이벤트

\`\`\`dataview
TABLE provenance.date AS "날짜", _derived.event_type AS "이벤트", file.link AS "문서"
FROM "vault/raw"
WHERE provenance.date >= date(today) - dur(7 days)
  AND any(_derived.tickers, (t) => contains(this.holdings_tickers, t))
SORT provenance.date DESC
LIMIT 20
\`\`\`
```

[CITED: https://blacksmithgu.github.io/obsidian-dataview/queries/structure/ — DQL 구조]
[ASSUMED] 정확한 `any()`/`contains()` 표현은 plan 단계 Wave-0 probe로 fixture vault에서 검증해야 함. Dataview expression docs는 lambda를 지원하지만 한국어 ticker 리스트 패턴은 미검증.

### Example 4: hub frontmatter (D-03 그대로)

```yaml
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
content_hash: "sha256:abc123..."
---
```

[CITED: CONTEXT.md D-03]

## Runtime State Inventory

> rename/refactor 페이즈 아님 — 신규 디렉토리/파일 추가 위주. 단, `templates/portfolio.md` → `templates/notes/portfolio.md` atomic 이동 + `dashboards/_data/` 신규 디렉토리 등록 두 건은 runtime state 영향 있음.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — Phase 8은 신규 컬럼(`documents.note_type`)만 추가. 기존 row 마이그레이션은 Plan 시 backfill SQL 작성(NULL → "note" default). | Alembic migration + backfill UPDATE |
| Live service config | `.obsidian/community-plugins.json`에 "dataview" 추가 — Obsidian이 vault 처음 열 때 plugin 자동 설치 프롬프트. 사용자가 거부하면 dashboard raw 표시(D-19 fallback 의도). | git commit + README 안내 |
| OS-registered state | None — systemd.timer 등록은 Phase 9 OPS-01 책임. | none |
| Secrets/env vars | None — 신규 secret 없음. | none |
| Build artifacts | `templates/portfolio.md` 이동 시 import path 깨짐 검증 필요(현재는 import 대상이 아니므로 영향 없음 추정 — Plan Wave 0 grep으로 확인). `dashboards/_data/` 신규 — `.gitignore` 추가 필수. | grep `templates/portfolio.md` 참조 + .gitignore patch |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Postgres 17 + pgvector + VectorChord-BM25 | hub_builder DB query, note ingest | ✓ (Phase 1 OPS-06) | 17 | — |
| Python 3.12 + uv | 신규 모듈 | ✓ | 3.12 | — |
| `src/shared/portfolio.py` Portfolio.load | hub_builder가 holdings 읽을 때 | ✓ (Phase 4/6 cutover) | — | — |
| `src/shared/frontmatter.py` NoteFrontmatter | Phase 6 D-11이 도입 예정. **Phase 8 시작 시점에 존재 여부 Plan Wave 0 probe** | ⚠️ 검증 필요 | — | 없으면 Plan 1 첫 task로 NoteFrontmatter 도입 (Phase 6 D-11에서 떠받친 책임을 Phase 8에서 fulfill) |
| `src/ingest/embedder.py` Embedder, `tokenizer.py` tokenize_ko | 메모 인덱싱 | ✓ (Phase 3) | — | — |
| Obsidian + Dataview plugin (사용자 측) | Dashboard 가시성 | 사용자 환경 의존 | — | D-19 fallback 없음 — README 안내만 |

**Missing dependencies with no fallback:** 없음 (NoteFrontmatter 부재 시 Plan 1에서 함께 정의하면 됨).

**Missing dependencies with fallback:** Obsidian Dataview plugin — 사용자가 미설치 시 dashboard가 raw markdown으로 보임 (의도된 신호, D-19).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x (기존) |
| Config file | `pyproject.toml` (기존 `[tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest tests/ingest/test_hub_builder.py tests/ingest/test_price_snapshot.py tests/ingest/parsers/test_note.py tests/shared/test_frontmatter.py -x` |
| Full suite command | `uv run pytest -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DASH-01 | portfolio.md DQL이 holdings × prices join 표시 | manual-only (Obsidian 렌더 검증) + smoke(파일 존재+frontmatter parse) | `uv run pytest tests/dashboards/test_portfolio_dashboard_skeleton.py -x` | ❌ Wave 0 |
| DASH-02 | watchlist 표시 (portfolio.md ## Watchlist 공유) | manual-only + smoke | `uv run pytest tests/dashboards/test_watchlist_dashboard_skeleton.py -x` | ❌ Wave 0 |
| DASH-03 | events-this-week 7일 필터링 | unit (DQL 결과 fixture로 시뮬 X — 직접 query SQL 측 검증 어려움. 대안: hub_builder가 같은 SQL을 호출하는 helper 추출 → unit test) | `uv run pytest tests/ingest/test_events_query.py -x` | ❌ Wave 0 |
| DASH-04 | hub 자동 생성 + content_hash idempotent | unit (memory rebuild) + integration (worker 사이클 끝나면 hub 파일 존재) | `uv run pytest tests/ingest/test_hub_builder.py tests/ingest/test_worker_hub_hook.py -x` | ❌ Wave 0 |
| NOTE-01 | thesis 템플릿 + ThesisFrontmatter Pydantic 검증 | unit | `uv run pytest tests/shared/test_thesis_frontmatter.py -x` | ❌ Wave 0 |
| NOTE-02 | journal 템플릿 + NoteFrontmatter 검증 | unit | `uv run pytest tests/shared/test_note_frontmatter.py -x` | ❌ Wave 0 |
| NOTE-03 | `notes/private/foo.md` thesis → 1 ingest cycle 후 `search()`에 등장 | E2E integration (testcontainers Postgres + 실제 worker.run + search 호출) | `uv run pytest tests/ingest/test_note_e2e.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** Quick run command (Phase 8 신규 테스트만)
- **Per wave merge:** Full suite — `uv run pytest -x`
- **Phase gate:** Full suite green + 사용자가 Obsidian에서 dashboards 3종 시각 확인 (UI hint = yes, manual UAT 필요)

### Wave 0 Gaps

- [ ] `tests/ingest/test_hub_builder.py` — DASH-04 idempotent rebuild + content_hash 안정성
- [ ] `tests/ingest/test_price_snapshot.py` — D-08 prices.md 갱신 + as_of 정확성
- [ ] `tests/ingest/parsers/test_note.py` — note 파서 + ThesisFrontmatter 디스패치
- [ ] `tests/ingest/test_worker_hub_hook.py` — worker.py 사이클 종료 시 hub_builder.run + price_snapshot.run 호출 확인
- [ ] `tests/ingest/test_events_query.py` — DASH-03 이번 주 이벤트 SQL helper 단위 검증
- [ ] `tests/ingest/test_note_e2e.py` — E2E NOTE-03 (thesis 작성 → ingest → search hit)
- [ ] `tests/shared/test_thesis_frontmatter.py`, `tests/shared/test_note_frontmatter.py` — Pydantic 검증, review_flags 폴백
- [ ] `tests/dashboards/test_*_dashboard_skeleton.py` — 파일 존재 + frontmatter parse + DQL 코드블록 grep
- [ ] `tests/conftest.py` 또는 phase 전용 conftest — fixture vault에 `notes/private/sample-thesis.md` 추가
- [ ] Alembic migration 0005 (또는 다음 가용 번호) — `documents.note_type` 컬럼 + backfill

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Phase 8 신규 인증 surface 없음 — vault local |
| V3 Session Management | no | — |
| V4 Access Control | yes | `add_note` 화이트리스트 (Phase 6 D-09 + Phase 10 D-21 — 변경 없음). Hub 경로 (`vault/ingested/`)는 ingest worker만 write. **Plan 시 hub_builder가 `vault/ingested/by-ticker/` 외부에 절대 write 안 하도록 path containment 검증** |
| V5 Input Validation | yes | NoteFrontmatter / ThesisFrontmatter Pydantic 검증 (D-14). MCP `add_note` 경로 traversal 방어는 기존 (Phase 6) |
| V6 Cryptography | no | sha256 content_hash는 dedup primitive, security primitive 아님 (Phase 2 결정 정합) |

### Known Threat Patterns for {Obsidian + Dataview + ingest worker}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| 사용자가 `notes/private/`에 악성 frontmatter 삽입(거대 list, 무한 nesting) | DoS | Pydantic 검증 + body 크기 제한 (기존 `truncate` 200K char 정책 차용) |
| Markdown 본문 prompt injection (Claude가 search 결과로 메모를 읽을 때) | Tampering | 기존 `injection_defense.detect_injection_patterns` 적용 (Phase 3 INGEST-08). 메모는 `trust_level: trusted` (사용자 자신이 작성)이지만 일관성 위해 동일 패턴 통과 |
| Path traversal via `add_note(path="notes/private/../../etc/passwd")` | Tampering | Phase 6 화이트리스트 + symlink-resolve (Plan 06-06 이미 구현). Phase 8 변경 없음 |
| Hub overwrites user file (corp_code collision) | Integrity | hub 경로는 항상 `vault/ingested/by-ticker/{corp_code}.md` 정규화. corp_code 형식(8-digit) 검증. |
| `dashboards/_data/prices.md` 사용자가 직접 편집 후 ingest가 덮어씀 | Lost write | 파일 헤더에 "AUTO-GENERATED — DO NOT EDIT" 주석 + .gitignore (사용자 변경이 git에 안 잡혀 의도 신호) |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `src/shared/frontmatter.py`의 `NoteFrontmatter`가 Phase 6 D-11에서 도입되었거나 Phase 8 Plan 1에서 도입 가능 | Standard Stack, Pattern 4 | 만약 Phase 6에 누락되었으면 Phase 8 Plan 1이 추가 책임 떠안음 — 1 task 추가 (작은 영향) |
| A2 | Phase 6 `add_note` 화이트리스트가 Phase 10 D-21에 따라 `notes/private/`을 이미 포함 | Pitfall 2 | 미포함이면 Phase 8에서 화이트리스트 확장 추가 task 필요 — Plan Wave 0 grep으로 검증 |
| A3 | Dataview `any(list, lambda)` + `contains()` 표현이 한국어 ticker 6-digit 문자열 리스트에서 정확히 동작 | Code Examples 3 | Plan Wave 0 probe로 fixture vault에서 검증 필요. 미동작 시 FLATTEN으로 회피 가능 (성능 저하 약간) |
| A4 | Phase 8 hub_builder가 30일 sparkline용 OHLCV를 `chunks` 또는 별도 테이블이 아닌 `documents` (KRX raw markdown) frontmatter에서 추출 가능 | Architecture, hub_builder | KRX writer가 어떤 frontmatter 구조로 OHLCV를 저장하는지 Plan Wave 0에서 확인. `provenance.observations`(Phase 4 D-07)인지 별도 zone인지 확인 필요 |
| A5 | `documents.note_type` 컬럼 추가가 Phase 8 범위 내에서 새 Alembic migration로 가능 (Phase 10이 같은 컬럼을 도입하지 않음) | Pattern 4, Validation | Phase 10 D-22 "private notes ingest 포함"이 컬럼을 어디서 도입하는지 Plan 시 확인. 중복 마이그레이션 회피 |

## Open Questions

1. **`add_note` 화이트리스트 코드 위치 — Phase 10 D-21 적용 상태**
   - What we know: CONTEXT.md가 "Phase 10 D-21이 이미 확장"이라고 단정.
   - What's unclear: 코드가 실제로 patched 되었는지 (Phase 10 plan은 아직 미실행 상태일 수 있음 — STATE.md "Phase 10 Plan: Not started").
   - Recommendation: **Plan Wave 0 첫 단계에서 `grep -n "notes/private" src/stock_mcp/tools/`로 검증.** 미적용 시 Phase 8 Plan에 화이트리스트 patch task 추가 — 이는 Phase 10 D-21 작업과 충돌하지 않음 (idempotent grep + add).

2. **`documents.note_type` 컬럼 vs frontmatter zone**
   - What we know: D-15는 "컬럼 추가(또는 frontmatter zone)" 양자택일 명시.
   - What's unclear: 컬럼 추가 시 Phase 10 D-22와 충돌 여부. frontmatter zone-only 접근 시 SQL filter 효율 손실(JSONB 인덱스 필요).
   - Recommendation: **컬럼 추가 채택 권장.** `search()` filter (`source='private_note'`)은 기존 `documents.source` 컬럼(Phase 3에 존재)으로 가능하므로 `note_type`은 부가 정보. 단, Phase 10 D-22가 같은 컬럼을 이미 정의하면 마이그레이션 충돌 → Plan Wave 0에서 Phase 10 CONTEXT 확인.

3. **Hub 30일 sparkline 데이터 소스**
   - What we know: CONTEXT Claude 재량.
   - What's unclear: KRX raw markdown frontmatter의 OHLCV 누적 구조 (Phase 4).
   - Recommendation: **단순성 우선 — `dashboards/_data/prices.md`를 7일 → 30일로 확장**해서 hub_builder가 같은 derived 캐시 읽기. 별도 cache 추가 회피.

4. **`dashboards/_data/portfolio_holdings.md` derived 파일 추가 여부**
   - What we know: Pattern 3 분석에서 Dataview의 markdown 표 인덱싱 한계 발견.
   - What's unclear: `Portfolio.load()`가 이미 markdown 표를 파싱하므로, 그 결과를 Dataview로 보내는 다른 경로 존재 여부.
   - Recommendation: Plan Wave 0에서 Dataview fixture vault probe. 표 인덱싱 안 되면 derived 파일 추가(Claude 재량 영역).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `templates/portfolio.md` flat | `templates/notes/portfolio.md` | Phase 10 P-03 (CONTEXT D-10) | atomic git mv, history 보존 |
| MCP `add_note` 화이트리스트 = `vault/notes/`만 | + `notes/private/` 추가 | Phase 10 D-21 | Phase 8 메모 ingest path 가능 |
| 단일 portfolio SoT 모호 (dashboards vs notes/private) | `notes/private/portfolio.md` 단일 SoT | Phase 6 P-01 (06-01-portfolio-path-cutover) | Phase 8 dashboard가 notes/private/portfolio.md 참조 |
| Dataview JS 허용 | DQL only | Phase 8 D-18 | 보안/단순성 |

**Deprecated/outdated:**
- `notes/theses/` 디렉토리 — Phase 10 D-19 폐기, `notes/private/{ticker}/thesis.md` 사용 (REQUIREMENTS NOTE-01 AMENDED)
- `notes/journal/` 디렉토리 — Phase 10 D-19 폐기, `notes/private/journal/YYYY-MM-DD.md` 사용

## Sources

### Primary (HIGH confidence)
- `.planning/phases/08-vault-dashboards-research-memo-templates/08-CONTEXT.md` — D-01~D-19 의사결정 잠금
- `.planning/REQUIREMENTS.md` — DASH-01~04, NOTE-01~03 wording (NOTE-01/02 AMENDED)
- `.planning/ROADMAP.md` §Phase 8 — Goal/Success Criteria
- `.planning/STATE.md` — Phase 3/5/6/7 누적 결정 (content_hash, zone integrity SHA, Pydantic 패턴)
- `CLAUDE.md` — Tech stack, layer 규칙, GSD 강제
- 기존 코드: `src/shared/frontmatter.py`, `src/ingest/worker.py`, `src/ingest/parsers/dart.py`, `src/shared/portfolio.py`, `templates/portfolio.md`
- Dataview 공식 문서: https://blacksmithgu.github.io/obsidian-dataview/queries/structure/ — DQL TABLE/FROM/SORT 구조
- Dataview 공식 문서: https://blacksmithgu.github.io/obsidian-dataview/annotation/metadata-pages/ — frontmatter dot notation

### Secondary (MEDIUM confidence)
- Dataview FLATTEN 예제: https://s-blu.github.io/obsidian_dataview_example_vault/ — list 평탄화 패턴
- Forum: https://forum.obsidian.md/t/utilizing-dataview-queries-for-nested-frontmatter-yml-properties/69326 — nested key dot access 검증

### Tertiary (LOW confidence)
- (none — Phase 8 외부 검증 필요 항목 없음. 모든 결정이 CONTEXT 잠금 + 기존 코드베이스 패턴 차용으로 해결됨.)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — 신규 의존성 0, 기존 모듈 재사용
- Architecture: HIGH — Phase 3/5 패턴(content_hash, zone integrity SHA, Pydantic + review_flags) 차용
- Pitfalls: HIGH — 7개 모두 기존 코드베이스 컨벤션과 CONTEXT 결정에서 직접 도출
- Dataview DQL 정확도: MEDIUM — Wave 0 probe로 fixture vault에서 한국어 ticker 리스트 lambda 표현 검증 필요 (A3)

**Research date:** 2026-05-06
**Valid until:** 2026-06-05 (30일 — Dataview 0.5.x stable, Obsidian 안정 채널, Phase 9/10 변경 없을 시)
