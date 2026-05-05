# Phase 7: Graph Layer & graphify Integration - Context

**Gathered:** 2026-05-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 6의 `get_related`(MCP-06)가 SQL `edges` 테이블만으로 동작하도록 만들어둔 위에, **인제스트가 실제로 typed edges를 채우게 만들고**, **graphify로 vault 정기 스냅샷을 생성**하며, **3-5개의 캐노니컬 서브그래프 쿼리**를 문서화하여 graphify 출력이 "supernova"가 아닌 실제 투자 판단 질문에 답하도록 만든다.

**이 페이즈가 딜리버하는 것:**
1. `src/ingest/edges.py` post-pass 모듈 — `stock ingest` worker batch 끝에서 자동 호출 (GRAPH-01)
2. 6개 `edge_type` enum 확정 + Alembic 마이그레이션으로 CHECK 재추가 (GRAPH-01)
3. EXTRACTED / INFERRED / AMBIGUOUS `tag` 정책 (per-edge-type policy table)
4. `stock graph snapshot` CLI — `graphifyy` Python API를 직접 import하여 실행 (GRAPH-02)
5. `vault/graph/{YYYY-MM-DD KST}/{index.html, graph.json, GRAPH_REPORT.md}` 일배치 스냅샷
6. `vault/graph/README.md` — 5개 캐노니컬 쿼리 (산문 + 실행 가능한 Python snippet) (GRAPH-03)
7. graphify 입력 scope: `vault/notes/` ∪ `notes/private/` + `vault/raw/` 의 source-tunable 윈도우 (config.json)
8. Snapshot 보존: 최근 14개 dated dir만 유지, 나머지 자동 prune, `.gitignore`에 추가

**경계 — 이 페이즈가 다루지 않는 것:**
- 신규 MCP 툴 (`query_graph` 등) — Phase 9 JUDGE 영역 또는 별도 deferred (Phase 6 deferred 항목 그대로 유지)
- Dataview 대시보드, thesis/journal 템플릿 — Phase 8
- 일배치 systemd.timer / Task Scheduler 등록 — Phase 9 OPS-01 (Phase 7은 `stock graph snapshot` CLI까지만)
- Body-text NER 기반 `mentions_ticker` 보강 — Phase 8 폴리시 또는 deferred (Phase 7은 frontmatter `tickers:` 필드만)
- 신규 edge type (`macro_sector` 등) — locked taxonomy 변경 불가, 새 edge는 새 phase 마이그레이션
- Multi-user / visibility 권한 — Phase 10 deferred 그대로
- graphify `--mcp` 통합 (graphify를 별도 MCP 서버로 composition) — out of scope

</domain>

<prerequisites>
## Cross-Phase Prerequisites

| ID | 영역 | 상태 | Phase 7에서의 작업 |
|---|---|---|---|
| **P-01** | Phase 2 D-06 `edges` 스키마 (`tag` 컬럼 reserved) | 결정 완료 | tag 컬럼에 EXTRACTED/INFERRED 채우는 정책 코드화 |
| **P-02** | Migration 0003 — `ck_edge_type_phase2` DROP | 완료 (Phase 6) | Phase 7 마이그레이션이 새 CHECK 재추가 (6개 edge_type) |
| **P-03** | Phase 5 `_derived.events` 출력 | 완료 | event_event 정렬·precedes 엣지 derivation 입력으로 사용 (read-only) |
| **P-04** | Phase 6 `get_related` SQL 동작 | 완료 | 본 페이즈가 edges를 채워서 `get_related`가 실제 결과 반환 (회귀 테스트로 확인) |
| **P-05** | Phase 4 portfolio (`notes/private/portfolio.md`) | 완료 (Phase 6 P-01) | "Positions × 30d events" 쿼리가 portfolio 읽음 |

</prerequisites>

<decisions>
## Implementation Decisions

### Edge Population Pipeline (D-01 ~ D-05)

- **D-01:** **Post-pass 단일 모듈** — `src/ingest/edges.py`에 `populate(doc_ids: list[str], session)` 함수 단일 진입점. 모든 edge derivation 로직(ticker_sector, mentions_ticker, note_ticker, filing_event, event_event, supersedes)을 한 모듈에 모아 재현·디버깅·backfill을 단순화. 파서는 documents/chunks 만 책임지고 edges는 일절 안 만짐.
- **D-02:** **Idempotency = `INSERT ... ON CONFLICT DO NOTHING`** on Phase 2 D-06 composite UNIQUE `(src_type, src_id, dst_type, dst_id, edge_type)`. 재실행은 안전한 no-op, 자동 삭제 없음, append-only audit trail. 엣지 로직 변경 시에는 명시적 `stock ingest edges --rebuild` (truncate + repopulate, 별도 task).
- **D-03:** **자동 invocation** — `src/ingest/worker.py`의 batch 종료 hook에서 `edges.populate(committed_doc_ids, session)`를 호출. 신규 문서가 1 ingest cycle 내에 edges 반영. CLI 트리거(`stock ingest edges --rebuild`)는 backfill·테스트 용도로 별도 제공.
- **D-04:** **실패 정책 = soft-fail + `ingest_runs` warning** — edge pass 예외는 catch하여 `ingest_runs` row의 `extra` JSONB에 `edges_warning` 키로 기록 (Phase 3 OPS-03 패턴 재사용). documents/chunks 커밋은 유지. `health()`가 degraded edges 상태 가시화. 단일 buggy edge 규칙이 전체 ingest를 막지 않게 함.
- **D-05:** **관측성** — 각 edge pass 종료 시 `ingest_runs` row 작성. `source='edges'`, `extra` JSONB에 `{inserted: int, skipped_conflict: int, failed_per_type: {edge_type: count}}`. `vault/ingested/_status/heartbeat.md`(Phase 3 INGEST-12)도 동일 카운트 반영. 별도 `edge_runs` 테이블은 안 만듦 (단순성).

### Edge Taxonomy & Tag Policy (D-06 ~ D-09)

- **D-06:** **`edge_type` enum (6 values)** — Phase 7 Alembic 마이그레이션이 다음 CHECK 재추가:
  ```sql
  CHECK (edge_type IN (
    'mentions_ticker',   -- (filing|news|kind) → ticker  : 본문/타이틀에서 언급
    'filing_event',      -- filing/news → event          : Phase 5 _derived.events 기반
    'note_ticker',       -- note → ticker                : note frontmatter tickers[]
    'event_event',       -- event → event                : 동일 ticker 시간 순서 precedes
    'ticker_sector',     -- ticker → sector              : entities 메타에서 도출
    'supersedes'         -- filing → filing              : Phase 2 기재정정 체인 (기존 유지)
  ))
  ```
  ROADMAP §145 6개 + Phase 2 supersedes 정확히. 새 edge type은 새 마이그레이션 강제 — 사일런트 typo 방지(Phase 6 fixture에서 5종 임의 값 들어간 사례 재발 방지).
- **D-07:** **Tag policy (per-edge-type)** — 코드 상수 `EDGE_TAG_POLICY: dict[str, Literal["EXTRACTED","INFERRED","AMBIGUOUS"]]`:
  ```python
  EDGE_TAG_POLICY = {
      "mentions_ticker": "EXTRACTED",   # frontmatter/regex 결정론적
      "ticker_sector":   "EXTRACTED",   # entities.sector_code 결정론적
      "note_ticker":     "EXTRACTED",   # frontmatter tickers[]
      "supersedes":      "EXTRACTED",   # DART rcept_no chain
      "filing_event":    "INFERRED",    # Phase 5 LLM _derived.events
      "event_event":     "INFERRED",    # 시간 순서 + 90d window 휴리스틱
  }
  ```
  AMBIGUOUS는 ingest에서 절대 사용 안 함 — graphify 출력(`graph.json` edges)에서만 등장 (graphify 자체 라벨링 그대로 신뢰).
- **D-08:** **`note_ticker` source = frontmatter `tickers:` 필드 only**. Body NER는 Phase 7 범위 아님. 단, 본문에 ticker 패턴(`\d{6}` 또는 corp_code)이 있으나 frontmatter에 없으면 `ingest_runs.extra.edges_warning.unmatched_body_tickers`에 누적(deferred로 폴리시 강화 시 사용). `add_note`(Phase 6 D-11)가 이미 `resolve_entity`로 정규화하므로 ticker 표기 통일성 보장.
- **D-09:** **`event_event` derivation = same-ticker temporal precedence**. 동일 `entities.corp_code`에 대해 `_derived.events`를 date 정렬, 90일 슬라이딩 윈도우 안에서 인접한 event 쌍에 `event_event` precedes 엣지 생성. `tag='INFERRED'`. LLM 호출 없음, 결정론적, 테스트 용이. 명시적 `caused_by` 라벨링은 deferred (Phase 5 contract 변경 회피).

### graphify Invocation, Scope & Retention (D-10 ~ D-15)

- **D-10:** **`stock graph snapshot` CLI 서브커맨드** — `graphifyy` PyPI 패키지를 Python API로 직접 import하여 실행. 이유: (a) `vault/graph/{YYYY-MM-DD KST}/` 출력 경로·산출물 검증·prune까지 단일 트랜잭션, (b) Phase 9 scheduler가 외부 binary 경로/PATH 불확실성 없이 `uv run stock graph snapshot` 한 줄 호출, (c) 입력 scope curation(아래 D-12)을 우리 코드에서 직접 하기 좋음. 트레이드오프: graphify CLI의 풍부한 audit trail/UX는 일부 잃지만, 우리는 산출물(`graph.json`, `GRAPH_REPORT.md`) 검증으로 보완.
- **D-11:** **graphify 모드** — 첫 구현은 `mode='deep'` 고정 (richer INFERRED edges). `--update`(incremental) 지원은 D-15와 함께 v2. directed graph 사용(`directed=True`): `news_article --mentions--> ticker` 방향 보존이 catalyst chain 분석에 필요.
- **D-12:** **입력 scope = `vault/notes/` ∪ `notes/private/` + `vault/raw/` curated window**. `vault/raw/` 전체를 그대로 던지면 supernova(ROADMAP §145 경고). 대신 source별 윈도우를 `config.json`에서 튜닝:
  ```json
  {
    "graphify": {
      "raw_windows_days": {
        "dart": 365,
        "news": 30,
        "kind": 90,
        "macro": 180
      }
    }
  }
  ```
  코드 상수가 아닌 config.json을 택한 이유: 사용자가 vault 성장 추이에 따라 다른 source는 줄이고 DART는 늘리는 식 튜닝이 빈번할 것으로 예상. CLI는 config 읽어 해당 디렉터리에서 mtime 또는 frontmatter `published`/`rcept_dt` 기준 window 안 파일만 임시 staging 디렉터리로 심볼릭 링크 후 graphify 호출.
- **D-13:** **출력 위치 = `vault/graph/{YYYY-MM-DD KST}/`**. KST 날짜 사용(Phase 5 D-08 등 timezone 정책과 일관). graphify 산출물: `index.html`, `graph.json`, `GRAPH_REPORT.md` 필수, `graph.svg`/`graphml`은 optional flag로 향후 추가.
- **D-14:** **Snapshot 보존 = 최근 N=14 dated dir만 유지**. `stock graph snapshot` 실행 시 `vault/graph/` 안 dated dir 목록을 mtime 정렬 후 14개 초과분 자동 삭제. 14일치 trend 비교는 가능, 디스크 무한 증가 방지. `vault/graph/`는 `.gitignore`에 추가 (vault에서 항상 재생성 가능 — PROJECT 비-잠금-인 원칙).
- **D-15:** **Incremental rebuild** — 첫 구현은 항상 full rebuild. `--update` 옵션은 corpus가 커진 후 측정 후 결정 (deferred). graphify의 `--update`가 우리 staging 디렉터리 패턴과 호환되는지 검증 필요.

### Canonical Subgraph Queries (D-16 ~ D-20)

- **D-16:** **5개 캐노니컬 쿼리 확정** — `vault/graph/README.md`에 다음 순서로 문서화:
  1. **Q1 — Positions × last-30-day events**: portfolio holdings의 각 ticker에 대해 30일 이내 `_derived.events` + DART 필링 서브그래프. "포트폴리오 오늘 어때?" 직답.
  2. **Q2 — Catalyst chain for ticker X**: 주어진 ticker의 최신 event부터 `event_event` precedes 엣지 역방향 BFS (90d). "왜 지금 이 상태인가?" 시간 lens.
  3. **Q3 — Sector filing clusters**: 주어진 sector_code의 N일 내 모든 filings + tickers, community detection. 섹터 차원 테마 가시화.
  4. **Q4 — Supersedes chain**: 주어진 DART 필링부터 `supersedes` 엣지 역방향 walk. 기재정정 audit "이게 최신본인가?" 체크.
  5. **Q5 — Notes ↔ events around ticker X**: 주어진 ticker에 연결된 user notes/theses(`note_ticker`)와 최근 events(`filing_event`)를 같이 보여줌. user research ↔ raw evidence 연결 — 프로젝트 핵심 가치(근거 있는 매수/매도 판단) 직결.
- **D-17:** **표현 형식 = 산문 recipe + 실행 가능한 Python snippet** — 각 쿼리 섹션은 (a) 한국어 자연어 질문, (b) 어떤 노드/엣지를 따라가는지 산문 설명, (c) 그대로 복사해 실행 가능한 Python snippet (SQL on `edges` 테이블 또는 `graphifyy` API 호출). MCP 툴 신규 추가 없이 작동. SQL view 생성은 안 함 (마이그레이션 부담 회피, snippet으로 충분).
- **D-18:** **Snippet 위치** — `vault/graph/README.md` 내부에 inline (vault에서 사용자가 즉시 보고 실행). 각 snippet은 `repo_root()` 헬퍼(Phase 6) + SQLAlchemy session 부트스트랩 짧은 prelude 포함. 5개 모두 200줄 이내 README 안에 들어갈 사이즈.
- **D-19:** **검증 의무** — Phase 7 verification에서 5개 쿼리를 현 corpus에 대해 실제로 실행, 각 쿼리가 non-empty + legible 서브그래프 반환을 확인 (ROADMAP §151). README의 snippet이 그대로 실행되는지 CI smoke test로 보호 (`tests/graph/test_canonical_queries.py`).
- **D-20:** **Subgraph extraction 책임** — Q1~Q5 모두 우선 SQL on `edges` + `documents` join으로 구현(graphify 출력 의존 없음, DB만 있어도 동작). graphify 출력은 사람-친화 시각화(HTML)와 community 라벨링만 보너스로 사용. 이는 Phase 6 D-06 정책(`get_related`는 `edges`만)과 일관.

### Cross-Phase Hooks (D-21 ~ D-22)

- **D-21:** **Phase 9 scheduler hookup 명세** — Phase 7은 `stock graph snapshot` CLI까지만 ship. Phase 9 OPS-01에서 systemd.timer / Task Scheduler가 daily-batch 직후(KST 18:30 정도) 본 명령을 실행하도록 등록. Phase 7 README에 "Phase 9에서 scheduler 등록 예정" 명시.
- **D-22:** **`get_related` 회귀 테스트** — Phase 6 fixture vault에 Phase 7 edge 채워서 실행하는 회귀 테스트 추가 — `get_related('005930-doc-001', depth=1)`가 실제 ticker_sector / mentions_ticker / supersedes 엣지를 반환함을 확인. Phase 6의 SQL-only 동작을 deprecate하지 않음(여전히 fallback).

### Folded Todos
없음 (todo backlog 매칭 항목 없음 — 검증 후 추가 시 update).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Boundary & Roadmap
- `.planning/ROADMAP.md` §"Phase 7: Graph Layer & graphify Integration" — goal·success criteria·requirement IDs
- `.planning/REQUIREMENTS.md` GRAPH-01, GRAPH-02, GRAPH-03
- `.planning/STATE.md` — 현 진행 상태 (Phase 6 완료 직후)

### Cross-Phase Decisions (반드시 준수)
- `.planning/phases/01-load-bearing-foundation/01-CONTEXT.md` — D-01 (vault 디렉터리 구조, `graph/`는 vault 하위로 이동되었음을 본 페이즈가 확정), D-05 (.gitignore 정책 — `vault/graph/` 추가)
- `.planning/phases/02-canonical-entity-identity/02-CONTEXT.md` — D-05/D-06 (edges 스키마, `tag` 컬럼, composite UNIQUE), D-08 (supersedes 체인)
- `.planning/phases/03-one-company-walking-skeleton/03-CONTEXT.md` — D-21 (stdout 보호, dict 에러), OPS-03 ingest_runs 패턴
- `.planning/phases/05-claude-schedule-enrichment-with-korean-number-safety/05-CONTEXT.md` — D-08 (event_type enum), `_derived.events` 스키마 (event_event derivation 입력)
- `.planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md` — D-06 (`get_related`는 SQL `edges`만 — Phase 7과 독립), deferred "graphify wiki/json output" (본 페이즈 책임)

### Codebase Patterns (필독)
- `src/db/entity.py` — `Edge` ORM 모델 (Phase 2 D-06)
- `src/db/migrations/versions/0003_relax_edges_check_for_phase6.py` — DROP CHECK 이력; Phase 7 마이그레이션이 새 CHECK 재추가
- `src/ingest/worker.py` — batch 종료 hook 위치, `ingest_runs` 작성 패턴
- `src/ingest/heartbeat.py` — `read_sources` 헬퍼 (edges source 추가)
- `src/shared/portfolio.py` — `Portfolio.load(repo_root)` (Q1 입력)
- `src/shared/repo_root.py` — `repo_root()` 헬퍼 (snippet에서 사용)
- `src/stock_mcp/tools/related.py` — `get_related` 구현 (회귀 테스트 대상)
- `src/cli/commands.py` — `stock` CLI 서브커맨드 등록 패턴 (`stock graph snapshot` 추가 위치)

### External Refs
- `~/.claude/skills/graphify/SKILL.md` — graphify 사용법, `graphifyy` PyPI, 모드 옵션, `--directed`/`--update`/`--obsidian` 등
- CLAUDE.md TechStack §8 — graphify 통합 권장 사항 (현재 Option A: `stock-mcp`가 `graph.json` 직접 read를 v2로 deferred — 본 페이즈는 Option A 미진입, 단순 디스크 산출물만)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`Edge` ORM** (`src/db/entity.py`) — Phase 2가 만들어둠. `tag` 컬럼 사용 가능.
- **`ingest_runs` 작성 헬퍼** — Phase 3 OPS-03 패턴, edges source 동일 형식.
- **`heartbeat.read_sources`** (Phase 6 dfeede9 absolute import 정정) — edges source row 추가.
- **`resolve_entity`** (Phase 2) — note_ticker / mentions_ticker 정규화에 그대로.
- **`Portfolio.load(repo_root)`** (Phase 4 D-01 / Phase 6 P-01) — Q1 snippet 입력.
- **`repo_root()`** (Phase 6 1fc16c4) — snippet 부트스트랩.
- **testcontainers Postgres fixture** (Phase 2/3) — Phase 7 테스트 setup 재사용.

### Established Patterns
- **`ingest_runs.extra` JSONB로 부수 카운트 누적** (Phase 5 D-23/D-24, Phase 4 hearbeat extension)
- **Soft-fail + warning row** (Phase 3, Phase 4 collector 패턴)
- **Pydantic `extra='forbid'`** — graphify wrapper 응답 모델 동일 적용
- **Migration 파일 명명** (`{NNNN}_phase{NN}_*.py`) — Phase 7은 `0004_phase07_edge_check.py`

### Integration Points
- `src/ingest/worker.py` batch 종료 — D-03 hook 위치
- `src/cli/commands.py` — `stock graph snapshot` 서브커맨드 등록
- `.gitignore` — `vault/graph/` 추가 (D-14)
- `config.json` 또는 `.planning/config.json` — graphify raw_windows_days (D-12). 기존 config 파일 위치 확인 필요 → researcher가 정확한 경로 결정.

</code_context>

<specifics>
## Specific Ideas

- **Edges 모듈 분할 제안**: `src/ingest/edges.py`가 비대해지면 `src/ingest/edges/{deterministic.py, derived.py, __init__.py}`로 분리 (deterministic = ticker_sector/note_ticker/mentions_ticker/supersedes; derived = filing_event/event_event). 첫 구현은 단일 파일.
- **graphify staging 디렉터리**: `vault/.graphify-staging/{YYYY-MM-DD KST}/` 같은 임시 디렉터리에 D-12 윈도우 안 파일을 심볼릭 링크 → graphify 호출 → 종료 후 staging 삭제. vault 자체를 건드리지 않음.
- **README.md 한국어 + 코드 영어**: 캐노니컬 쿼리 README는 산문은 한국어(질문 의도), Python snippet 변수명·주석은 영어. CLAUDE.md 톤과 일관.
- **CI smoke test**: `tests/graph/test_canonical_queries.py`가 fixture vault + testcontainers Postgres에서 5개 snippet을 직접 import + 실행, non-empty subgraph 보장. graphify CLI 자체는 무거우니 별도 nightly로 빼는 옵션 고려.

</specifics>

<deferred>
## Deferred Ideas

- **`query_graph(question)` MCP 툴** — Claude가 자연어로 graphify 질의. v2 (Phase 9 또는 별도 phase). Phase 7은 디스크 산출물 + Python snippet까지.
- **graphify `--mcp` 서버 composition** — graphify를 별도 MCP로 띄워 Claude Code에서 동시 사용. CLAUDE.md TechStack §8 Option B. Out of scope.
- **Body-text NER로 mentions_ticker 보강** — Phase 8 폴리시 또는 Phase 9 JUDGE.
- **Phase 5 LLM에 `caused_by` 명시 라벨링** — event_event 신호 강화. Phase 5 contract 변경 필요. Deferred.
- **`macro_sector` 등 신규 edge type** — locked taxonomy. 새 phase + 마이그레이션.
- **Multi-user / chunks.visibility** — Phase 10 deferred 그대로.
- **Incremental graphify (`--update`)** — corpus 성장 후 측정 후 결정.
- **SQL views로 캐노니컬 쿼리 영속화** — D-17에서 snippet으로 충분, view는 추가 마이그레이션 부담. v2.
- **graphify 출력 SVG/GraphML/Neo4j export** — optional flag, 필요 시 추가.

</deferred>

---

*Phase: 07-graph-layer-graphify-integration*
*Context gathered: 2026-05-05*
