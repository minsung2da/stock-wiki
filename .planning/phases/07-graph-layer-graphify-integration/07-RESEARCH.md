# Phase 7: Graph Layer & graphify Integration - Research

**Researched:** 2026-05-05
**Domain:** typed-edge population pipeline + graphify (graphifyy PyPI) snapshot CLI + canonical SQL subgraph queries
**Confidence:** HIGH (taxonomy / Alembic / SQL recipes), MEDIUM-HIGH (graphifyy Python API surface — verified package, exact import paths via SKILL.md only), HIGH (event_event derivation algorithm)

## Summary

Phase 7은 기존 Phase 2~6에서 **스키마만 갖춰놓은 `edges` 테이블에 실제 typed 엣지를 채우고**, **graphify로 vault 스냅샷을 정기 생성**하며, **5개 캐노니컬 SQL 쿼리**를 README + CI smoke test로 영속화한다. CONTEXT.md(D-01~D-22)가 22개 결정을 모두 락-인했기 때문에 본 연구는 *대안 탐색이 아닌 구현 시 알아야 할 사실 검증*에 초점을 둔다.

핵심 발견 — 일부는 CONTEXT가 정한 가정과 코드 현실 사이의 미세한 불일치를 노출한다. 이 격차들은 plan 단계에서 명시적으로 다뤄져야 한다:

1. **`graphifyy` PyPI 최신 버전은 0.7.5 (2026-05-04 release)** — CLAUDE.md TechStack §8에 적힌 "v4 latest" / Phase 6 fixture에 적힌 "0.3.x" 모두 stale. SKILL.md는 v4 기준 API를 보여주지만 실제 0.7.5에 동일 함수 시그니처가 유지되는지는 plan-time 의존성 lock에서 확정해야 한다 [VERIFIED: pypi.org/pypi/graphifyy/json].
2. **`_derived.events` 라는 list 필드는 코드에 존재하지 않는다** — `DerivedBlock`은 `event_type: EventType | None`(단일) + `catalysts: list[str]`만 가짐 [VERIFIED: src/shared/frontmatter.py:184-185]. CONTEXT D-09는 "_derived.events를 date 정렬"이라고 가정하지만, 실제 입력은 (a) `events` 테이블(Phase 2 D-06) 또는 (b) `documents.first_seen_at` + `_derived.event_type`이어야 한다. → **Plan은 `events` 테이블에서 derive하는 SQL 경로 + Phase 2 events 테이블이 실제로 채워지는지 확인하는 검증 task를 포함**해야 한다.
3. **Phase 2 events 테이블도 현재 한 군데도 INSERT하지 않는다** [VERIFIED: `grep -rn "INSERT INTO events"` returns 0 hits]. → event_event derivation은 입력 부재로 빈 집합을 반환할 수 있다. Phase 7 plan은 (i) ingest 시 `_derived.event_type` non-null + `documents.corp_code` 조합으로 events 테이블 자체도 함께 채우거나 (ii) `documents` + `_derived` 직접 join으로 우회해야 함.
4. **supersedes 엣지도 현재 INSERT 흔적 없다** [VERIFIED: grep]. Phase 2 D-08이 "체인이 엣지로 저장된다"고 명시하지만 실제 collector(`src/collectors/dart/*`)에 supersedes 엣지 INSERT 코드가 없다. Phase 7 `edges.populate`가 DART rcept_no chain (frontmatter `correction_of`/`rcept_no_origin` 등)에서 derive해야 한다 — 입력 필드의 실제 존재 여부 확인 필요.
5. **`_derived.events` 가 만약 Phase 8/9에서 추가될 list 필드라면 새 마이그레이션 + 스키마 확장이 선행 조건**이 된다. CONTEXT가 이를 P-03 prerequisite로 "완료"라고 표기한 것은 부정확. plan-time에 사용자 확인 필요한 [ASSUMED] 항목.

**Primary recommendation:** 단일 모듈 `src/ingest/edges.py`에 6개 derivation 함수(deterministic 4 + INFERRED 2) + `populate(doc_ids, session)` 진입점 작성, Alembic 0004로 6-value CHECK 재추가(rows-violate 사전 검증 포함), `stock graph snapshot` CLI는 `graphifyy` 0.7.5를 Python API로 호출(`graphify.detect`/`build`/`cluster`/`export.to_html|to_json`/`report.generate` 모듈 chain — SKILL.md v4 패턴), staging 디렉터리 `vault/.graphify-staging/{KST}/`에 mtime/frontmatter 윈도우 파일을 심볼릭 링크하여 supernova 회피, 5개 캐노니컬 쿼리는 SQL on `edges`+`documents` join으로 README inline + `tests/graph/test_canonical_queries.py`가 fixture vault에서 non-empty 보장.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Edge Population Pipeline (D-01 ~ D-05)**
- **D-01:** Post-pass 단일 모듈 `src/ingest/edges.py` — `populate(doc_ids: list[str], session)` 단일 진입점. 6개 derivation 로직(ticker_sector / mentions_ticker / note_ticker / filing_event / event_event / supersedes) 한 모듈. 파서는 documents/chunks만 책임지고 edges는 일절 만들지 않는다.
- **D-02:** Idempotency = `INSERT ... ON CONFLICT DO NOTHING` on Phase 2 D-06 composite UNIQUE `(src_type, src_id, dst_type, dst_id, edge_type)`. 재실행 안전, append-only audit. 엣지 로직 변경 시 명시적 `stock ingest edges --rebuild` (truncate + repopulate, 별도 task).
- **D-03:** 자동 invocation — `src/ingest/worker.py` batch 종료 hook에서 `edges.populate(committed_doc_ids, session)`. CLI `stock ingest edges --rebuild`는 backfill·테스트 용도 별도 제공.
- **D-04:** 실패 정책 = soft-fail + `ingest_runs` warning. edge pass 예외는 catch → `ingest_runs.extra.edges_warning`. documents/chunks 커밋은 유지. `health()`가 degraded 상태 가시화. 단일 buggy 규칙이 전체 ingest를 막지 않게.
- **D-05:** 관측성 — 각 edge pass 종료 시 `ingest_runs` row, `source='edges'`, `extra` JSONB에 `{inserted, skipped_conflict, failed_per_type}`. `vault/ingested/_status/heartbeat.md` 동일 카운트 반영. 별도 `edge_runs` 테이블 안 만듦.

**Edge Taxonomy & Tag Policy (D-06 ~ D-09)**
- **D-06:** `edge_type` enum = 6 values: `mentions_ticker`, `filing_event`, `note_ticker`, `event_event`, `ticker_sector`, `supersedes`. Alembic 0004가 `CHECK (edge_type IN (...))` 재추가. 새 edge type은 새 마이그레이션 강제.
- **D-07:** Tag policy 코드 상수:
  ```python
  EDGE_TAG_POLICY = {
      "mentions_ticker": "EXTRACTED",
      "ticker_sector":   "EXTRACTED",
      "note_ticker":     "EXTRACTED",
      "supersedes":      "EXTRACTED",
      "filing_event":    "INFERRED",
      "event_event":     "INFERRED",
  }
  ```
  AMBIGUOUS는 ingest에서 사용 안 함 — graphify 출력에서만 등장.
- **D-08:** `note_ticker` source = frontmatter `tickers:` only. body NER는 out of scope. body에 `\d{6}`/corp_code 패턴이 있으나 frontmatter에 없으면 `ingest_runs.extra.edges_warning.unmatched_body_tickers`에 누적.
- **D-09:** `event_event` derivation = same-`corp_code` temporal precedence. date 정렬 + 90일 슬라이딩 윈도우, 인접 쌍에 `event_event` precedes 엣지 + tag='INFERRED'. LLM 호출 없음, 결정론적, 테스트 가능. `caused_by` 라벨링은 deferred.

**graphify Invocation, Scope & Retention (D-10 ~ D-15)**
- **D-10:** `stock graph snapshot` 서브커맨드 — `graphifyy` PyPI Python API 직접 import. CLI 외부 binary 의존 없음. 입력 scope curation을 우리 코드에서 직접.
- **D-11:** graphify 모드 = `mode='deep'` 고정 (richer INFERRED). `--update` 지원 v2. directed 그래프 (`directed=True`).
- **D-12:** 입력 scope = `vault/notes/` ∪ `notes/private/` + `vault/raw/` curated window. raw는 source별 윈도우 config:
  ```json
  {
    "graphify": {
      "raw_windows_days": {"dart": 365, "news": 30, "kind": 90, "macro": 180}
    }
  }
  ```
  CLI는 mtime 또는 frontmatter `published`/`rcept_dt` 기준 window 안 파일만 staging 디렉터리로 심볼릭 링크 후 graphify 호출.
- **D-13:** 출력 = `vault/graph/{YYYY-MM-DD KST}/` — `index.html`, `graph.json`, `GRAPH_REPORT.md` 필수.
- **D-14:** Snapshot retention = 최근 N=14 dated dir만 유지, mtime 정렬 후 14개 초과분 자동 prune. `vault/graph/`는 `.gitignore` 추가.
- **D-15:** 첫 구현은 항상 full rebuild. `--update` deferred.

**Canonical Subgraph Queries (D-16 ~ D-20)**
- **D-16:** 5개 캐노니컬 쿼리 = Q1 Positions × 30d events / Q2 Catalyst chain BFS / Q3 Sector filing clusters / Q4 Supersedes chain / Q5 Notes ↔ events around ticker.
- **D-17:** 표현 = 산문 recipe + 실행 가능한 Python snippet (SQL on edges 또는 graphifyy API). MCP 신규 툴 추가 없음. SQL view 생성 안 함.
- **D-18:** Snippet 위치 = `vault/graph/README.md` inline. 각 snippet은 `repo_root()` + SQLAlchemy session 부트스트랩 짧은 prelude 포함.
- **D-19:** 검증 = Phase 7 verification에서 5개 쿼리를 현 corpus에 대해 실제 실행, non-empty + legible 서브그래프 확인. CI smoke test `tests/graph/test_canonical_queries.py`.
- **D-20:** Subgraph extraction = SQL on `edges` + `documents` join 우선. graphify 출력은 사람-친화 시각화 + community 라벨링 보너스.

**Cross-Phase Hooks (D-21 ~ D-22)**
- **D-21:** Phase 7은 `stock graph snapshot` CLI까지만. Phase 9 OPS-01에서 systemd.timer/Task Scheduler 등록.
- **D-22:** Phase 6 fixture vault에 Phase 7 edge 채워서 `get_related('005930-doc-001', depth=1)` 회귀 테스트 추가.

### Claude's Discretion
- Edges 모듈 분할 — `src/ingest/edges.py` 비대해지면 `src/ingest/edges/{deterministic.py, derived.py, __init__.py}`로 분리. **첫 구현은 단일 파일** (CONTEXT specifics 제안).
- README 톤 — 산문 한국어 + Python snippet 영어 변수명/주석 (CLAUDE.md 일관성).
- staging 디렉터리 정확한 경로 (`vault/.graphify-staging/{date}/`로 specifics 제안하나 final은 plan-time).
- config 파일 위치 — `.planning/config.json` vs 신규 `config/graphify.json`. **연구 권고: `config/graphify.json` 신규 (아래 "Config Location" 섹션 근거).**
- canonical SQL의 정확한 SELECT 형태·LIMIT (snippet 200줄 한도 내 자유 재량).

### Deferred Ideas (OUT OF SCOPE)
- `query_graph(question)` MCP 툴 (자연어 그래프 질의) — Phase 9 또는 별도.
- graphify `--mcp` 서버 composition (Option B) — out of scope.
- Body-text NER로 `mentions_ticker` 보강 — Phase 8 또는 9.
- Phase 5 LLM `caused_by` 명시 라벨링 — Phase 5 contract 변경 필요. Deferred.
- 신규 edge type (`macro_sector` 등) — locked taxonomy.
- Multi-user / chunks.visibility — Phase 10.
- Incremental graphify (`--update`) — corpus 성장 후 측정.
- SQL views 캐노니컬 쿼리 영속화 — snippet으로 충분.
- graphify SVG/GraphML/Neo4j export — optional flag, 필요 시.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **GRAPH-01** | 인제스트가 `edges` 테이블에 `ticker→filing`, `filing→event`, `note→ticker`, `event→event`, `ticker→sector` 엣지를 구축한다 | Standard Stack §"Edge Population", Architecture §"Single-module post-pass + 6 derivation functions", Code Examples §"INSERT … ON CONFLICT DO NOTHING + Alembic 0004 CHECK reinstate", Pitfall §"events 테이블 비어있을 가능성", §"DerivedBlock에 events list 없음" |
| **GRAPH-02** | graphify가 일배치 또는 수동 실행으로 vault 스냅샷을 생성하여 `vault/graph/{YYYY-MM-DD}/`에 `index.html`·`graph.json`·`GRAPH_REPORT.md`를 쓴다 | Standard Stack §"graphifyy 0.7.5", Architecture §"stock graph snapshot CLI", Code Examples §"Python API call chain", Don't Hand-Roll §"graphify CLI 우회 시 community detection 재구현 금지", Pitfall §"PyPI 0.3.x stale reference" |
| **GRAPH-03** | 3-5개의 캐노니컬 서브그래프 쿼리가 문서화되고 graphify wiki 출력에 링크된다 | Standard Stack §"SQL on edges+documents join", Architecture §"5 canonical queries Q1-Q5", Code Examples §"Q1 SQL skeleton" through "Q5 SQL skeleton", Validation Architecture §"test_canonical_queries.py" |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

핵심 디렉티브 (Phase 7과 직접 관련된 것만):

| Directive | 적용 |
|-----------|------|
| `collectors/`·`ingest/`에 `anthropic`/`openai` import 금지 (CI guard COLL-07) | edge derivation은 LLM 호출 없음 — D-09가 결정론적이어서 자연 충족. CI guard 통과 보장. |
| Markdown + frontmatter가 single source of truth, DB는 캐시 | `edges` 테이블도 캐시. `stock ingest edges --rebuild`로 vault에서 재생성 가능해야 함 (D-02). |
| `_derived` 추출은 외부 Claude Schedule 에이전트 (ingest venv 분리) | Phase 7 edge derivation은 ingest venv 내부에서 동작 — _derived는 input(read-only), edges는 output (DB only, frontmatter 미변경). |
| 임베딩은 sentence-transformers 직접, 로컬 LLM 없음 | edge derivation은 임베딩 사용 안 함 (모두 결정론적/SQL). |
| Korean BM25 등 한국어 처리 | edge derivation은 Korean text 처리 없음 (corp_code/ticker/sector 등 구조화 필드만). README 산문은 한국어. |
| Postgres 17 + pgvector + VectorChord-BM25 (네이티브 Docker) | 마이그레이션 0004는 native Postgres에서 ALTER TABLE — 표준. |
| 시간대 = KST (Phase 5 D-08 일관) | `vault/graph/{YYYY-MM-DD KST}/` 디렉터리명 (D-13), 14-day prune (D-14) 모두 KST 자정 기준. |
| Immutability (coding-style.md) | edge derivation 함수는 입력을 mutate하지 않고 새 SQL row 생성 — 자연 충족. |
| 파일 200-400줄 권장, 800 max | 단일 모듈 `edges.py`가 6개 derivation을 모두 포함하면 800 근접 가능 — specifics 제안의 분할 고려 (Claude's discretion). |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **graphifyy** | 0.7.5 (2026-05-04 release) | vault 스냅샷 graph + community detection + HTML/JSON/REPORT 생성 | 프로젝트 공식 graphify 통합 (CLAUDE.md §8 / SKILL.md). PyPI 패키지명 `graphifyy`(double-y), import는 `import graphify` [VERIFIED: pypi.org/pypi/graphifyy/0.7.5/json] |
| **SQLAlchemy** | 2.x (이미 의존성) | edges 테이블 INSERT/SELECT, 캐노니컬 쿼리 SQL 실행 | 프로젝트 표준 ORM/Core. `sa.text()` + bind params로 SQL injection 방지 |
| **Alembic** | (이미 의존성) | 마이그레이션 0004 — 6-value CHECK 재추가 | hand-written migrations only, target_metadata=None (Phase 2 컨벤션) |
| **PyYAML** | (이미 의존성) | config 파일 또는 frontmatter 파싱 (window 필터링 시 `published`/`rcept_dt` 추출용) | 표준 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **networkx** | (graphifyy 의존성으로 자동 설치) | graphify 내부 그래프 표현 — 직접 import 불필요 | graphify가 알아서 사용 |
| **pyvis** | (graphifyy 추정 의존성) | HTML 인터랙티브 시각화 — 직접 사용 안 함 | graphify 내부 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| graphifyy Python API | graphify CLI subprocess | CLI는 staging 디렉터리/output 검증/prune을 외부 프로세스로 분리 — D-10이 우리 코드 내 단일 트랜잭션 통제를 우선 |
| Single-module `edges.py` | `edges/{deterministic,derived}.py` 분할 | 첫 구현은 단일 (specifics 제안), 800줄 초과 시 plan-time 분할 |
| `.planning/config.json` 확장 | `config/graphify.json` 신규 | `.planning/config.json`은 GSD 워크플로우 메타데이터 ([VERIFIED: 직접 읽음 — `model_profile`, `commit_docs`, `git`, `workflow` 키만]); graphify 런타임 config는 별도 파일이 관심사 분리 측면에서 더 깨끗 — **본 연구 권고** |

**Installation:**
```bash
uv add graphifyy  # 0.7.5
# 또는 pyproject.toml의 collectors/ingest 그룹과 분리된 새 'graph' optional group으로 추가 권장
# (graphify는 ingest pipeline의 곁가지 — 분리된 venv면 ingest cold-start에 영향 없음)
```

**Version verification:**
```bash
$ curl -s https://pypi.org/pypi/graphifyy/json | jq -r '.info.version'
0.7.5
$ curl -s https://pypi.org/pypi/graphifyy/0.7.5/json | jq -r '.urls[0].upload_time'
2026-05-04T17:24:57
```
[VERIFIED: pypi.org] — 0.7.5 published 2026-05-04, 하루 전. requires_python `>=3.10` (프로젝트 3.12 호환).

**Notes on graphifyy version drift:**
- CLAUDE.md TechStack §8은 "v4 latest" — stale (현재 v5+ 출시 [CITED: github.com/safishamsi/graphify/blob/v5/README.md]).
- Phase 6 06-RESEARCH.md / 06-CONTEXT.md는 "0.3.14" 언급 — stale (현재 0.7.5).
- SKILL.md (`~/.claude/skills/graphify/SKILL.md`) 는 v4 기준 코드 패턴이지만 사용 함수(`graphify.detect.detect`, `graphify.build.build_from_json`, `graphify.cluster.cluster|score_all`, `graphify.analyze.god_nodes|surprising_connections|suggest_questions`, `graphify.report.generate`, `graphify.export.to_json|to_html|to_obsidian|to_canvas`, `graphify.cache.check_semantic_cache|save_semantic_cache`)는 0.3.14부터 반복적으로 사용된 안정 인터페이스 추정 — **plan-time에 `python -c "import graphify; help(graphify.build)"`로 0.7.5 시그니처 확인 task 필수** [ASSUMED for 0.7.5 stability].

## Architecture Patterns

### Recommended Project Structure

```
src/
├── ingest/
│   ├── edges.py             # 신규 — 6개 derivation 함수 + populate(doc_ids, session) 진입점
│   │                        # (specifics 제안: edges/{deterministic,derived}.py 분할은 800줄 초과 시)
│   └── worker.py            # 수정 — ingest_run 끝에 edges.populate() hook (D-03)
├── cli/
│   └── commands.py          # 수정 — cmd_graph_snapshot, cmd_ingest_edges_rebuild 추가
├── graph/                   # 신규 디렉터리 (Phase 7 신설)
│   ├── __init__.py
│   ├── snapshot.py          # graphifyy Python API wrapper, staging dir, 14-day prune
│   ├── window.py            # config 읽고 vault/raw/{source}/ window 파일 선별 + symlink
│   └── canonical.py         # (선택) 5개 SQL 쿼리를 함수로 캡슐화 — README snippet의 import 타깃
├── db/
│   └── migrations/versions/
│       └── 0004_phase07_edge_check.py  # 신규 — 6-value CHECK 재추가 + pre-validate
└── shared/
    └── (기존 — 변경 없음)

tests/
└── graph/                   # 신규 디렉터리
    ├── __init__.py
    ├── test_edges_deterministic.py      # ticker_sector / mentions_ticker / note_ticker / supersedes
    ├── test_edges_derived.py            # filing_event / event_event (90d window edge cases)
    ├── test_edges_idempotency.py        # ON CONFLICT DO NOTHING 재실행
    ├── test_canonical_queries.py        # D-19 — 5 snippets 모두 fixture corpus에서 non-empty
    ├── test_snapshot_cli.py             # graphifyy mock + 14-day prune
    └── test_get_related_regression.py   # D-22 — Phase 7 edge 채워서 회귀

vault/
├── graph/                   # 신규 — gitignored
│   ├── README.md            # 5 canonical queries (산문 + snippet)
│   ├── 2026-05-05/          # dated dir (KST)
│   │   ├── index.html
│   │   ├── graph.json
│   │   └── GRAPH_REPORT.md
│   └── ...                  # (최근 14개 유지)
└── .graphify-staging/       # 신규 — gitignored, 임시; snapshot 종료 후 cleanup
    └── 2026-05-05/          # symlink farm

config/
└── graphify.json            # 신규 — raw_windows_days
```

### Pattern 1: Single-module edge derivation with `populate(doc_ids, session)` entry point

**What:** 모든 edge 로직을 한 모듈에 모으고, ingest worker는 batch 끝에 함수 한 개만 호출.

**When to use:** D-01 락-인. 디버깅·재현·backfill을 한 곳에서.

**Example:**
```python
# Source: src/ingest/edges.py (신규 — Phase 7)
from __future__ import annotations
import logging
from typing import Literal
import sqlalchemy as sa
from sqlalchemy.engine import Connection

EDGE_TAG_POLICY: dict[str, Literal["EXTRACTED", "INFERRED"]] = {
    "mentions_ticker": "EXTRACTED",
    "ticker_sector":   "EXTRACTED",
    "note_ticker":     "EXTRACTED",
    "supersedes":      "EXTRACTED",
    "filing_event":    "INFERRED",
    "event_event":     "INFERRED",
}

_INSERT_EDGE_SQL = sa.text(
    "INSERT INTO edges (src_type, src_id, dst_type, dst_id, edge_type, tag) "
    "VALUES (:st, :si, :dt, :di, :et, :tag) "
    "ON CONFLICT (src_type, src_id, dst_type, dst_id, edge_type) DO NOTHING"
)

def _emit(conn: Connection, st: str, si: str, dt: str, di: str, et: str) -> int:
    """Returns 1 if newly inserted, 0 if conflict (idempotent — D-02)."""
    res = conn.execute(_INSERT_EDGE_SQL,
        {"st": st, "si": si, "dt": dt, "di": di, "et": et, "tag": EDGE_TAG_POLICY[et]})
    return res.rowcount or 0

def populate(doc_ids: list[str], conn: Connection) -> dict:
    """Phase 7 entry point. Called from worker batch end (D-03).
    Returns counters for ingest_runs.extra.edges_warning."""
    counters = {"inserted": 0, "skipped_conflict": 0, "failed_per_type": {}, "unmatched_body_tickers": []}
    for fn in (_derive_ticker_sector, _derive_mentions_ticker,
               _derive_note_ticker, _derive_supersedes,
               _derive_filing_event, _derive_event_event):
        edge_type = fn.__name__.removeprefix("_derive_")
        try:
            fn(doc_ids, conn, counters)
        except Exception as exc:  # D-04 soft-fail
            counters["failed_per_type"][edge_type] = str(exc)[:200]
            logging.exception("edge derivation failed: %s", edge_type)
    return counters
```

### Pattern 2: Alembic CHECK reinstatement (drop-then-add) with pre-validate

**What:** 0003에서 DROP된 CHECK를 0004에서 새 enum으로 ADD. 추가 전에 violating row가 없음을 확인.

**When to use:** Phase 7 edge taxonomy lock-in (D-06). Phase 6에서 fixture가 임의 5종 값(`mentions, references, precedes, same_sector, supersedes`)을 사용했으므로, **plan은 fixture를 새 enum으로 마이그레이트하는 일회성 task가 필요** — 단순히 CHECK만 추가하면 fixture INSERT가 실패한다.

**Example:**
```python
# Source: src/db/migrations/versions/0004_phase07_edge_check.py (신규)
"""Phase 7 GRAPH-01: reinstate edges.edge_type CHECK with 6-value enum.

Phase 2 0001이 'supersedes' only로 CHECK를 만들었고, Phase 6 0003이 fixture를 위해
DROP했다. Phase 7은 6-value enum으로 다시 ADD한다.

Pre-validate: violating rows가 있으면 마이그레이션 실패 (silent corruption 방지).

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-XX
"""
from __future__ import annotations
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

ALLOWED = ("mentions_ticker", "filing_event", "note_ticker",
           "event_event", "ticker_sector", "supersedes")

def upgrade() -> None:
    # Pre-validate (Pitfall: fixture/legacy rows can violate)
    bind = op.get_bind()
    bad = bind.execute(
        sa.text("SELECT DISTINCT edge_type FROM edges "
                "WHERE edge_type NOT IN :allowed"),
        {"allowed": ALLOWED}
    ).scalars().all()
    if bad:
        raise RuntimeError(
            f"Migration 0004 blocked: edges contains illegal edge_type values: {bad}. "
            f"Either DELETE these rows or extend the enum."
        )
    op.execute(
        "ALTER TABLE edges ADD CONSTRAINT ck_edge_type_phase7 "
        "CHECK (edge_type IN ('mentions_ticker','filing_event','note_ticker',"
        "'event_event','ticker_sector','supersedes'))"
    )

def downgrade() -> None:
    op.execute("ALTER TABLE edges DROP CONSTRAINT IF EXISTS ck_edge_type_phase7")
```

**Constraint name change rationale:** `ck_edge_type_phase2` (Phase 2) vs `ck_edge_type_phase7` (이번) — 같은 이름 재사용은 0003 downgrade가 빈 기존 CHECK를 다시 추가해 충돌 가능. 새 이름이 깔끔.

### Pattern 3: graphify Python API 호출 chain

**What:** SKILL.md v4 패턴을 production CLI로 캡슐화. `subprocess` 없이 `import graphify`로 직접 호출.

**When to use:** `stock graph snapshot` 진입점 (D-10).

**Example:**
```python
# Source: src/graph/snapshot.py (신규)
"""stock graph snapshot — Phase 7 GRAPH-02.

Calls graphifyy 0.7.5 Python API directly (D-10). Stages source files into a
symlink farm (D-12 windowed scope), invokes graphify deep+directed, writes
output to vault/graph/{KST_DATE}/, prunes oldest dirs beyond N=14.
"""
from __future__ import annotations
import json, os, shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ZoneInfo for KST — stdlib (Python 3.9+)
try:
    from zoneinfo import ZoneInfo
    KST = ZoneInfo("Asia/Seoul")
except ImportError:
    KST = timezone(timedelta(hours=9))  # fallback

KEEP_DATED_DIRS = 14  # D-14

def snapshot(repo_root: Path, config: dict) -> Path:
    today_kst = datetime.now(KST).date().isoformat()
    out_dir = repo_root / "vault" / "graph" / today_kst
    staging = repo_root / "vault" / ".graphify-staging" / today_kst
    out_dir.mkdir(parents=True, exist_ok=True)
    _build_staging(repo_root, staging, config)
    try:
        _run_graphify(staging, out_dir)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    _prune_old(out_dir.parent, KEEP_DATED_DIRS)
    return out_dir

def _run_graphify(input_dir: Path, out_dir: Path) -> None:
    """Reproduce SKILL.md v4 chain in-process with directed=True, deep mode."""
    from graphify.detect import detect
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.analyze import god_nodes, surprising_connections, suggest_questions
    from graphify.report import generate
    from graphify.export import to_json, to_html

    detection = detect(input_dir)  # returns dict; SKILL.md Step 2
    # NOTE: Phase 7 v1 skips Part B (semantic LLM extraction) since deep
    # extraction needs subagent dispatch — for unattended `stock graph snapshot`
    # we rely on AST-only structural extraction. Semantic LLM is via separate
    # `/graphify` invocation by the user. Plan-time decision: confirm whether
    # Phase 7 must include semantic extraction or AST-only is acceptable.
    # ... (extraction details — see SKILL.md Step 3 Part A for AST-only path)

    extraction = _extract_ast_only(detection)  # graphify.extract.collect_files + extract
    G = build_from_json(extraction)  # directed support inside build_from_json
    communities = cluster(G)
    cohesion = score_all(G, communities)
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    labels = {cid: f"Community {cid}" for cid in communities}  # placeholder labels
    questions = suggest_questions(G, communities, labels)
    tokens = {"input": 0, "output": 0}

    # Write outputs to vault/graph/{date}/
    to_json(G, communities, str(out_dir / "graph.json"))
    to_html(G, communities, str(out_dir / "index.html"), community_labels=labels)
    report = generate(G, communities, cohesion, labels, gods, surprises,
                     detection, tokens, str(input_dir),
                     suggested_questions=questions)
    (out_dir / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")

def _prune_old(graph_dir: Path, keep: int) -> int:
    """Keep most-recent N dated dirs by mtime; remove the rest. Atomic per-dir."""
    dated = [d for d in graph_dir.iterdir()
             if d.is_dir() and not d.name.startswith(".")]
    dated.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for d in dated[keep:]:
        shutil.rmtree(d, ignore_errors=True)
        removed += 1
    return removed
```

**Caveat — semantic vs AST-only:** SKILL.md Step 3 Part B는 LLM subagent dispatch (`Agent` tool) — 이는 인터랙티브 Claude 세션에서만 가능. `stock graph snapshot`은 **unattended**(Phase 9 scheduler 호출)이므로 LLM 호출 없는 AST-only(Step 3 Part A) 경로만 가능. 의미 그래프는 사용자가 별도로 `/graphify` 인터랙티브 실행. **Plan은 이를 명확히 README에 적어야 함.**

### Pattern 4: Staging directory + symlink farm for windowed scope (D-12)

**What:** vault/raw/ 전체를 graphify에 던지지 않고 윈도우 안 파일만 임시 staging으로 심볼릭 링크.

**Example:**
```python
# Source: src/graph/window.py (신규)
def build_staging(repo_root: Path, staging: Path, config: dict) -> None:
    """Create symlink farm at staging/ pointing into vault/notes, notes/private,
    and vault/raw/{source}/ files within configured days window."""
    staging.mkdir(parents=True, exist_ok=True)
    # Always-included: notes
    for src in (repo_root / "vault" / "notes", repo_root / "notes" / "private"):
        if src.exists():
            (staging / src.relative_to(repo_root)).symlink_to(src,
                target_is_directory=True)
    # Source-windowed: raw
    windows = config.get("graphify", {}).get("raw_windows_days", {})
    for source_name, days in windows.items():
        cutoff = datetime.now(KST) - timedelta(days=days)
        src_root = repo_root / "vault" / "raw" / source_name
        if not src_root.exists():
            continue
        target_root = staging / "raw" / source_name
        target_root.mkdir(parents=True)
        for f in src_root.rglob("*.md"):
            if datetime.fromtimestamp(f.stat().st_mtime, tz=KST) >= cutoff:
                rel = f.relative_to(src_root)
                tgt = target_root / rel
                tgt.parent.mkdir(parents=True, exist_ok=True)
                tgt.symlink_to(f)
```

**Cross-platform note (D-12):** Windows 심볼릭 링크는 admin 권한 또는 Developer Mode 필요. WSL native path 사용 시 (FOUND-04 권장) Linux symlink 정상 동작. Windows-only 사용자는 D-12 fallback으로 file copy 필요 — 본 프로젝트는 WSL 우선이므로 symlink primary, copy fallback 명시 권장.

### Pattern 5: SQL canonical query on edges + documents join (D-20)

**What:** graphify 출력 의존 없이 DB만으로 5 쿼리 작동.

**See "Code Examples" 섹션의 Q1~Q5 SQL skeleton.**

### Anti-Patterns to Avoid

- **edges에 frontmatter write 시도:** edges 테이블만 INSERT, frontmatter 미변경. STORE-06 zone integrity 보호.
- **edges.populate에서 새 transaction 시작:** worker가 이미 batch 트랜잭션 안 — 같은 connection을 받아 재사용해야 D-04 soft-fail이 documents 커밋을 보존.
- **graphify CLI subprocess.run으로 호출:** D-10이 Python API 직접 import 명시. subprocess는 PATH·환경 격리 비용.
- **vault/raw 전체 graphify 입력:** ROADMAP §145 supernova 경고. D-12 windowed staging 필수.
- **prune 도중 새 snapshot 시작:** snapshot 실행은 single-process (CLI 한 번 호출). race-condition 방어는 lockfile 또는 pid file 권장 — Phase 9 scheduler가 동시 실행 안 하면 unnecessary; plan-time 재량.
- **dated dir 이름에 timezone suffix 포함:** D-13 `{YYYY-MM-DD KST}` 산문이지만, 디렉터리명 공백·non-ASCII는 도구 호환성 문제 — `2026-05-05` plain ISO date 권장 + README에 "all dates KST" 명시.
- **DELETE FROM edges WHERE …로 stale edge 청소:** D-02 append-only. 수동 truncate/rebuild만 (`stock ingest edges --rebuild`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Community detection / clustering | 직접 구현 (Louvain·Leiden 등) | `graphify.cluster.cluster` | NetworkX + datasketch 기반 graphify 내장. 직접 구현은 Phase 7 스코프 폭증 |
| Interactive HTML graph viewer | pyvis/d3 직접 wrap | `graphify.export.to_html` | graphify가 5000-node 한도까지 자동 처리, community 색상도 자동 |
| GRAPH_REPORT.md format | 직접 markdown 생성 | `graphify.report.generate` | 일관된 audit trail format, EXTRACTED/INFERRED/AMBIGUOUS 자동 라벨링 |
| KST 시간 계산 | dateutil 또는 manual `+09:00` | `zoneinfo.ZoneInfo("Asia/Seoul")` | stdlib (Python 3.9+), 프로젝트 3.12 보장 |
| `_derived.event_type` → `events` 테이블 ETL | 새 SQL view | (검토 필요) `events` 테이블 직접 INSERT | **CRITICAL: Phase 2 events 테이블이 현재 비어있음 — Phase 7 plan은 이를 채우는 task 또는 우회 결정 필요** |
| Korean BM25 / 임베딩 | — | (Phase 7 무관 — edges 도메인) | edge derivation은 구조화 필드(corp_code/ticker)만 사용 |
| Atomic dir write | tempfile + os.replace 매번 | (graphify 자체 처리) | graphify가 outdir 직접 쓰므로 우리는 outdir 검증만 |

**Key insight:** Phase 7의 진짜 위험은 graphify를 재구현하는 것이 아니라 **graphify 입력을 잘못 준비해서 supernova/garbage-in을 만드는 것** — D-12 windowing이 핵심.

## Runtime State Inventory

> Phase 7은 신규 마이그레이션 + 신규 모듈 추가 위주의 추가형 phase로 rename/rebrand는 없음. 다만 `edges` 테이블의 *데이터 의미* 변경 (Phase 2/Phase 6 fixture row가 새 CHECK enum과 충돌 가능) 이 mini-rename 성격이라 점검.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **edges 테이블 fixture rows** — Phase 6 fixture가 5개 임의 edge_type(`mentions, references, precedes, same_sector, supersedes`)을 사용. Phase 7 `ck_edge_type_phase7`(6 values)과 충돌. fixture의 `references` / `same_sector` / `mentions` / `precedes`는 새 이름(`mentions_ticker` / `ticker_sector` / `event_event`)과 mismatch [VERIFIED: 0003 docstring lines 5-6, fixture corpus 직접 확인 필요] | **데이터 마이그레이션** task 필요: (1) 0004 upgrade 전에 fixture rebuild 또는 (2) 0004에 `UPDATE edges SET edge_type = CASE …` 매핑. 둘 중 plan-time 결정. fixture가 build-from-vault라면 vault 재인덱스로 자동 정리도 가능. |
| Live service config | None — Phase 7은 외부 서비스 등록 없음 (Phase 9 OPS-01에서 systemd.timer / Task Scheduler가 별개 task로 진행) | None |
| OS-registered state | None — Phase 7은 CLI ship까지만 (D-21) | None |
| Secrets/env vars | **None — verified by grep**: graphifyy는 LLM API 호출 없음 (AST-only mode), 외부 API key 불필요. Phase 7 새 secret 추가 없음 | None |
| Build artifacts | **uv.lock 갱신** — graphifyy 추가 시 lock 재생성. `pyproject.toml`의 dependency group 결정(`ingest` vs 신규 `graph`) 필요 — graph가 분리 venv면 ingest cold-start 영향 0 | Plan-time pyproject.toml 수정 task |

**The canonical question — "After every file in the repo is updated, what runtime systems still have the old string cached, stored, or registered?":** Phase 7은 rename phase가 아니므로 직접 적용 안 됨. 단 fixture row의 `edge_type` 값이 *문자열 변경*인 점에서 mini-rename. 0004 마이그레이션의 pre-validate 절이 이를 감지하므로 sliently corrupt 가능성은 차단.

## Common Pitfalls

### Pitfall 1: events 테이블이 비어있어 filing_event/event_event derivation이 빈 집합 반환

**What goes wrong:** Phase 2 D-06이 `events` 테이블을 만들었지만 [VERIFIED: grep `INSERT INTO events`는 zero hit] 어떤 코드도 INSERT하지 않는다. Phase 5 routine이 `_derived.event_type`만 frontmatter에 쓰고 `events` 테이블은 채우지 않는 것으로 추정.

**Why it happens:** Phase 5 D-08이 `event_type` enum을 frontmatter 필드로 정의했지만, frontmatter→DB events 테이블 ETL을 ingest worker가 수행하는지 명시되지 않음. CONTEXT D-09는 "_derived.events" (list 필드)를 정렬 입력으로 가정하지만 실제 스키마는 `event_type: EventType | None` (단일).

**How to avoid:** Plan-time 명시 task — (a) `_derived.event_type` non-null + `documents.first_seen_at`(또는 `_derived.event_date` 신설) 조합으로 events 테이블도 ingest 시 채우는 작은 ETL, **OR** (b) `event_event` derivation을 events 테이블 우회하고 `documents JOIN _derived` 직접 활용. (b)가 더 단순.

**Warning signs:** Phase 7 verification 단계 D-19에서 Q2(catalyst chain)가 모든 ticker에 대해 빈 결과 반환 → events derivation이 데이터 없음 → 본 pitfall 발현.

### Pitfall 2: `_derived.events` (list) 필드가 schema에 존재하지 않음

**What goes wrong:** CONTEXT D-09 텍스트는 "동일 entities.corp_code에 대해 `_derived.events`를 date 정렬"이라고 적었으나, `DerivedBlock`에는 `event_type: EventType | None` (단일) + `catalysts: list[str]`만 있음 [VERIFIED: src/shared/frontmatter.py:178-191].

**Why it happens:** CONTEXT 작성 시 `_derived.events` 라는 list 필드를 가정한 것 같음 — Phase 5 schema 검토 누락.

**How to avoid:** event_event derivation 입력으로 (i) `documents` join `_derived.event_type` (filing 1개당 event_type 1개) 또는 (ii) `events` 테이블(채워진다는 가정 하에) 사용. **plan-time 사용자 확인 필요한 [ASSUMED] 영역.**

**Warning signs:** edges.py 구현 중 "어디서 events list를 읽어야 하지?" 라는 막힘.

### Pitfall 3: supersedes 엣지 INSERT 코드가 어디에도 없음

**What goes wrong:** Phase 2 D-08 명세상 "기재정정 체인 → 엣지" 이지만 [VERIFIED: grep `supersedes`는 migration·CHECK·테스트 외에 INSERT 흔적 없음] DART collector나 ingest worker에 supersedes INSERT가 부재.

**Why it happens:** Phase 2 진행 시 스키마/CHECK만 깔고 실제 채우는 로직은 추후로 미뤘는데 잊혀진 듯. Phase 7 D-06 enum 6개에 `supersedes`가 포함되므로 이 phase가 책임.

**How to avoid:** `_derive_supersedes(doc_ids, conn, counters)` 함수가 DART frontmatter의 정정 관계 표시 필드(`correction_of_rcept_no` 또는 유사)를 읽어 INSERT. **plan-time에 DART collector frontmatter 실제 필드명 확인 task 필수** — `src/collectors/dart/writer.py` 또는 fixture vault 샘플 점검.

**Warning signs:** Q4 (Supersedes chain) 캐노니컬 쿼리가 모든 corp_code에 대해 빈 결과.

### Pitfall 4: graphifyy 0.7.5 API가 SKILL.md v4 패턴과 미세하게 다를 수 있음

**What goes wrong:** SKILL.md는 graphifyy v4 (≈0.3.x) 시기 작성. v5+ (0.7.5)에서 함수 시그니처·반환 타입이 미묘하게 변경됐을 수 있음.

**Why it happens:** 메이저 버전 점프(v4→v5).

**How to avoid:** Plan-time Wave 0 probe task — `python -c "import graphify; print(dir(graphify.build))"` + 핵심 함수 5개 (detect, build_from_json, cluster, to_json, generate) 시그니처 확인. v4 패턴과 다르면 plan에 어댑터 task 추가.

**Warning signs:** snapshot.py 첫 실행 시 `TypeError: ...() got an unexpected keyword argument`.

### Pitfall 5: Windows symlink permission

**What goes wrong:** D-12 staging 디렉터리는 symlink로 vault 파일을 가리킴. Windows에서는 admin 권한·Developer Mode 없으면 symlink 생성 실패.

**How to avoid:** WSL 사용 (FOUND-04 권장 경로) — Linux symlink 무권한. Windows-only 사용자는 fallback `shutil.copy` (느리지만 호환). **plan은 시도-실패-fallback 패턴 또는 OS detect 필요.**

**Warning signs:** `OSError: symbolic link privilege not held` (Windows).

### Pitfall 6: `vault/graph/{YYYY-MM-DD KST}/` 디렉터리 이름의 공백·non-ASCII

**What goes wrong:** D-13 명세 그대로 `2026-05-05 KST` (공백 포함) 디렉터리명 만들면 일부 도구가 깨짐 (graphify URL encoding, Obsidian internal links).

**How to avoid:** 디렉터리명은 `2026-05-05` plain ISO, README 또는 `_meta.json`에 "all dates KST 자정 기준" 명시. CONTEXT D-13의 `{YYYY-MM-DD KST}`는 *시간대 의도*를 나타내는 spec 표기 — 실제 디렉터리명에 "KST" 문자열 포함은 plan-time 재량으로 단순 ISO date 권장.

### Pitfall 7: 14-day prune이 새로운 snapshot 도중 race condition

**What goes wrong:** snapshot 시작 → prune 실행 → 동시에 다른 프로세스가 새 snapshot 시작하면 partial state.

**How to avoid:** Phase 7 deferred — Phase 9 scheduler가 single-instance lock을 갖도록 등록. 그동안 manual `stock graph snapshot`은 사용자 책임.

**Warning signs:** 동일 KST 날짜에 두 번 snapshot 실행 시 `OSError: [Errno 39] Directory not empty` 또는 partial dir.

### Pitfall 8: `ingest_runs.extra` JSONB가 너무 큼

**What goes wrong:** D-05가 카운터 + `unmatched_body_tickers` 누적을 JSONB로. 큰 corpus에서 unmatched ticker 수십만이면 row 폭증.

**How to avoid:** `unmatched_body_tickers`는 list가 아니라 `{ticker: count}` dict + 상한 (예: top 100만 보존) — plan-time 재량.

## Code Examples

### Q1 — Positions × last-30-day events (SQL on edges + documents)

```python
# Source: vault/graph/README.md inline + tests/graph/test_canonical_queries.py
"""Q1: 포트폴리오 holdings의 각 ticker에 대해 30일 이내 events + DART 필링 서브그래프.

질문: '내 포지션 오늘 어때?' — 보유 종목 각각의 최근 한 달 자료 한 페이지로 집약.
"""
from datetime import date, timedelta
import sqlalchemy as sa
from db.engine import get_engine
from shared.portfolio import Portfolio
from stock_mcp.repo_root import repo_root

def q1_positions_recent_events(days: int = 30) -> list[dict]:
    portfolio = Portfolio.load(repo_root())
    tickers = [h.ticker for h in portfolio.holdings]
    if not tickers:
        return []
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(sa.text("""
            SELECT e.src_id AS ticker, e.dst_id AS document_id, e.edge_type,
                   d.vault_path, d.first_seen_at, d.source
              FROM edges e
              JOIN documents d ON d.id = e.dst_id AND e.dst_type = 'document'
             WHERE e.src_type = 'ticker'
               AND e.src_id = ANY(:tickers)
               AND e.edge_type IN ('mentions_ticker', 'filing_event', 'note_ticker')
               AND d.first_seen_at >= :cutoff
             ORDER BY d.first_seen_at DESC
        """), {"tickers": tickers, "cutoff": date.today() - timedelta(days=days)}).mappings().all()
    return [dict(r) for r in rows]
```

**Note:** 위 SQL은 `mentions_ticker` 엣지 방향이 `document → ticker`라고 가정. **directed-graph 방향 합의는 plan-time 결정**: D-11의 `directed=True`는 `news_article → ticker` 의도라고 CONTEXT에 적혀있으므로 src=document, dst=ticker. Q1 SQL은 *역방향* (ticker → 이 ticker를 mention하는 documents) 이 더 자연스러움 — 양방향 인덱스 활용 가능 (`ix_edges_src` + `ix_edges_dst` 둘 다 존재).

### Q2 — Catalyst chain BFS for ticker X

```python
def q2_catalyst_chain(ticker: str, days: int = 90) -> list[dict]:
    """주어진 ticker의 최신 event부터 event_event precedes 엣지 역방향 BFS (90d).
    질문: '왜 지금 이 상태인가?' — 인과 추적."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(sa.text("""
            WITH RECURSIVE chain AS (
                -- seed: 가장 최근 event_event src 노드
                SELECT src_id, dst_id, 1 AS depth
                  FROM edges
                 WHERE edge_type = 'event_event'
                   AND src_id LIKE :prefix  -- corp_code prefix in event id
                UNION
                SELECT e.src_id, e.dst_id, c.depth + 1
                  FROM edges e
                  JOIN chain c ON e.dst_id = c.src_id
                 WHERE e.edge_type = 'event_event'
                   AND c.depth < 10
            )
            SELECT * FROM chain ORDER BY depth
        """), {"prefix": f"{ticker}-%"}).mappings().all()
    return [dict(r) for r in rows]
```

### Q3 — Sector filing clusters

```python
def q3_sector_filings(sector_code: str, days: int = 14) -> list[dict]:
    """주어진 sector_code의 N일 내 모든 filings + tickers."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(sa.text("""
            SELECT ts.src_id AS ticker, e.canonical_name, mt.dst_id AS document_id,
                   d.vault_path, d.first_seen_at
              FROM edges ts
              JOIN entities e ON e.current_ticker = ts.src_id
              JOIN edges mt ON mt.dst_id = ts.src_id
                            AND mt.dst_type = 'ticker'
                            AND mt.edge_type = 'mentions_ticker'
              JOIN documents d ON d.id = mt.src_id
             WHERE ts.edge_type = 'ticker_sector'
               AND ts.dst_id = :sector
               AND d.first_seen_at >= now() - :interval::interval
             ORDER BY d.first_seen_at DESC
        """), {"sector": sector_code, "interval": f"{days} days"}).mappings().all()
    return [dict(r) for r in rows]
```

### Q4 — Supersedes chain

```python
def q4_supersedes_chain(rcept_no: str) -> list[dict]:
    """주어진 DART rcept_no부터 supersedes 엣지 역방향 walk. 최신본 audit."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(sa.text("""
            WITH RECURSIVE chain AS (
                SELECT src_id, dst_id, 0 AS depth FROM edges
                 WHERE edge_type = 'supersedes' AND src_id = :seed
                UNION
                SELECT e.src_id, e.dst_id, c.depth + 1
                  FROM edges e
                  JOIN chain c ON e.dst_id = c.src_id
                 WHERE e.edge_type = 'supersedes' AND c.depth < 10
            )
            SELECT c.depth, c.src_id, c.dst_id, d.vault_path
              FROM chain c LEFT JOIN documents d ON d.id = c.src_id
             ORDER BY c.depth
        """), {"seed": rcept_no}).mappings().all()
    return [dict(r) for r in rows]
```

### Q5 — Notes ↔ events around ticker X

```python
def q5_notes_events(ticker: str, days: int = 60) -> dict:
    """user research ↔ raw evidence 연결."""
    engine = get_engine()
    with engine.connect() as conn:
        notes = conn.execute(sa.text("""
            SELECT e.src_id AS note_id, d.vault_path, d.first_seen_at
              FROM edges e JOIN documents d ON d.id = e.src_id
             WHERE e.edge_type = 'note_ticker' AND e.dst_id = :ticker
        """), {"ticker": ticker}).mappings().all()
        events = conn.execute(sa.text("""
            SELECT e.src_id AS doc_id, e.dst_id AS event_id,
                   d.vault_path, d.first_seen_at
              FROM edges e JOIN documents d ON d.id = e.src_id
              JOIN edges mt ON mt.src_id = e.src_id AND mt.dst_id = :ticker
                            AND mt.edge_type = 'mentions_ticker'
             WHERE e.edge_type = 'filing_event'
               AND d.first_seen_at >= now() - :interval::interval
        """), {"ticker": ticker, "interval": f"{days} days"}).mappings().all()
    return {"notes": [dict(r) for r in notes], "events": [dict(r) for r in events]}
```

**모든 Q1~Q5 공통 caveat:** `edges` 테이블의 `src_id`/`dst_id`는 type-tagged opaque text. ticker는 6-digit string, document는 sha256 hex, event는 ID 컨벤션 plan-time 결정 필요 (예: `"{corp_code}-{event_type}-{occurred_at}"`).

### event_event derivation (D-09) — 90-day sliding window

```python
def _derive_event_event(doc_ids: list[str], conn: Connection, counters: dict) -> None:
    """D-09: same-corp_code temporal precedence within 90-day sliding window."""
    # NOTE: 입력 데이터 소스는 plan-time 결정 (events 테이블 vs documents+_derived)
    # 아래는 documents.corp_code + d.first_seen_at 우회 경로 예시:
    rows = conn.execute(sa.text("""
        SELECT d.id, d.corp_code, d.first_seen_at
          FROM documents d
         WHERE d.corp_code IS NOT NULL
           AND d.id = ANY(:doc_ids)
         ORDER BY d.corp_code, d.first_seen_at
    """), {"doc_ids": doc_ids}).mappings().all()

    # Group by corp_code, pair adjacent within 90d
    from itertools import groupby
    for corp_code, group_iter in groupby(rows, key=lambda r: r["corp_code"]):
        events = list(group_iter)
        for prev, curr in zip(events[:-1], events[1:]):
            delta = (curr["first_seen_at"] - prev["first_seen_at"]).days
            if 0 < delta <= 90:
                counters["inserted"] += _emit(conn, "document", prev["id"],
                    "document", curr["id"], "event_event")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| graphify v4 (≈0.3.x) — SKILL.md 작성 시기 | graphifyy 0.7.5 (PyPI) | 2026-05-04 | 함수 시그니처 minor drift 가능, plan Wave-0 probe 필요 |
| Phase 2 `ck_edge_type_phase2` (`'supersedes'` only) | Phase 7 `ck_edge_type_phase7` (6 values) | this phase | edge_type 락-인, fixture migrate 필요 |
| Phase 6 fixture row의 5 임의 edge_type | 6-value enum으로 정합 | this phase | fixture rebuild 또는 0004 데이터 마이그레이션 |
| `get_related` SQL-only (Phase 6 D-06) | `get_related` SQL + Phase 7 채워진 edges | this phase | 동작은 동일, 결과는 풍부 |

**Deprecated/outdated:**
- CLAUDE.md TechStack §8의 "graphify v4 latest" 표기 — v5+ (0.7.5) 출시. 본 phase 종료 시 해당 라인 갱신 권장.
- Phase 6 06-RESEARCH.md의 graphifyy 0.3.14 reference — 0.7.5로 정정.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | graphifyy 0.7.5 함수 시그니처가 SKILL.md v4 패턴과 호환 (detect / build_from_json / cluster / score_all / god_nodes / surprising_connections / suggest_questions / generate / to_json / to_html) | Standard Stack, Pattern 3 | snapshot.py가 첫 실행에서 TypeError; Plan은 Wave-0 probe task 필수 |
| A2 | Phase 5 `_derived.event_type` 단일 필드가 Phase 7 event_event/filing_event derivation의 입력으로 사용 가능 (CONTEXT의 "_derived.events" list는 typo로 간주) | Pitfall 2, Code Examples | derivation 입력 부재; plan-time 사용자 확인 필수 |
| A3 | Phase 2 events 테이블이 비어있어도 documents+_derived 우회 derivation으로 Q1~Q5 작동 | Pitfall 1, Code Examples | events 테이블 ETL을 Phase 7이 또한 책임져야 할 수 있음 |
| A4 | DART frontmatter에 `correction_of` 또는 `rcept_no_origin` 등 supersedes 관계 필드가 존재 | Pitfall 3 | _derive_supersedes 입력 없음; Phase 7가 collector 수정도 책임 |
| A5 | graphify Python API 호출이 unattended 환경에서 LLM subagent dispatch 없이 AST-only로 작동 가능 | Pattern 3 caveat | snapshot이 LLM 토큰 0 약속 위반; Phase 9 scheduler 무인 실행 불가 |
| A6 | `.planning/config.json`이 GSD 메타이고 graphify 런타임 config는 별도 파일이 깨끗하다는 판단 | Standard Stack alternatives | 사용자가 단일 config 선호 시 본 phase가 .planning/config.json 확장 |
| A7 | Phase 6 fixture corpus의 임의 edge_type 5종이 vault rebuild로 자동 정정될 수 있음 (vault가 source of truth) | Runtime State Inventory, Pitfall | 0004 pre-validate 실패 → fixture rebuild 또는 명시 마이그레이션 |
| A8 | `notes/private/` symlink가 graphify 입력으로 안전하게 포함되어도 git 커밋에는 영향 없음 (notes/private/는 gitignored, vault/graph/도 gitignored) | Pattern 4 | 우연한 leak — gitignore 검증 task 필요 |

**Empty assumption table?** No — 8개 assumed claim. 모두 plan-time 사용자 확인 또는 Wave-0 probe로 해소.

## Open Questions

1. **`_derived.events` (list) 의도가 무엇이었나?**
   - What we know: CONTEXT D-09 텍스트는 list를 가정. DerivedBlock은 단일 `event_type`.
   - What's unclear: Phase 5 schema 확장 의도였는지, 단순 typo인지.
   - Recommendation: Plan 또는 discuss-phase에서 사용자 확인. typo면 single-field 우회로, 확장 의도면 별도 마이그레이션 task.

2. **events 테이블을 누가 채우나?**
   - What we know: Phase 2 D-06 스키마, INSERT 코드 부재.
   - What's unclear: Phase 5 routine이 채워야 하는데 누락? Phase 7가 책임?
   - Recommendation: 우선 Phase 7는 events 우회 (documents+_derived 직접 join), 이후 별도 quick task로 events 테이블 ETL.

3. **supersedes 엣지의 source frontmatter 필드명?**
   - What we know: DART 기재정정 metadata 어딘가 있어야 함.
   - What's unclear: 정확한 필드명·shape (`correction_of_rcept_no`? `rcept_no_origin`? nested `revisions`?).
   - Recommendation: Wave-0 probe — `find vault/raw/dart/ -name '*.md' | head -3 | xargs grep -l '정정\|correction'` 후 frontmatter 확인.

4. **Phase 6 fixture rebuild 정책?**
   - What we know: 0003이 fixture를 위해 CHECK 드롭. fixture row의 5 임의 edge_type.
   - What's unclear: fixture가 매번 vault rebuild로 만들어지는지, 정적 dump인지.
   - Recommendation: Plan-time `tests/fixtures/mcp-vault/` 검토.

5. **directed graph edge 방향 합의?**
   - What we know: D-11 `directed=True`, CONTEXT가 "news_article → ticker" 표기.
   - What's unclear: `mentions_ticker`는 doc→ticker, 그러나 `note_ticker`도 동일 방향? `filing_event`는 doc→event? `event_event`는 prev→curr (시간순)?
   - Recommendation: Plan에서 6 edge 모두 방향 표 명시.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| graphifyy | `stock graph snapshot` (D-10) | ✗ (현재 미설치) | — | uv add graphifyy로 설치; CI guard COLL-07이 ingest venv에 anthropic 없는지 검증 — graphifyy는 anthropic deps 없음 (verified — `requires_dist`에 networkx/datasketch/tree-sitter 등만, anthropic/openai 없음 [VERIFIED: pypi.org 메타데이터]) |
| Postgres 17 + pgvector + VectorChord-BM25 | 마이그레이션 0004, 캐노니컬 SQL | ✓ | 17 | — |
| Python 3.12 | 프로젝트 표준 | ✓ | 3.12 | graphifyy requires `>=3.10` 호환 |
| `zoneinfo.ZoneInfo("Asia/Seoul")` | KST 디렉터리명 | ✓ | stdlib 3.9+ | — |
| testcontainers Postgres | tests/graph/* | ✓ (Phase 2부터) | — | — |
| WSL native path (FOUND-04) | symlink farm (D-12) | ✓ (권장 환경) | — | Windows-only면 file copy fallback |

**Missing dependencies with no fallback:** 없음.

**Missing dependencies with fallback:** graphifyy 미설치 → `uv add graphifyy`로 plan task에서 추가.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (이미 의존성, Phase 2부터 사용) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (또는 `pytest.ini` 확인) |
| Quick run command | `uv run pytest tests/graph/ -x` |
| Full suite command | `uv run pytest -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GRAPH-01 | edges 테이블에 6 type 엣지가 ingest run 후 채워진다 | unit | `uv run pytest tests/graph/test_edges_deterministic.py -x` | ❌ Wave 0 |
| GRAPH-01 | filing_event/event_event 결정론적 derivation (90d window) | unit | `uv run pytest tests/graph/test_edges_derived.py -x` | ❌ Wave 0 |
| GRAPH-01 | INSERT … ON CONFLICT DO NOTHING — 재실행 idempotent | unit | `uv run pytest tests/graph/test_edges_idempotency.py -x` | ❌ Wave 0 |
| GRAPH-01 | edge_type CHECK 6-value enum (마이그레이션 0004) | unit | `uv run pytest tests/db/test_migration_0004.py -x` | ❌ Wave 0 |
| GRAPH-01 | get_related 회귀 — Phase 6 SQL 동작 + 새 edges (D-22) | integration | `uv run pytest tests/graph/test_get_related_regression.py -x` | ❌ Wave 0 |
| GRAPH-02 | `stock graph snapshot` CLI가 vault/graph/{date}/ 생성 + 14-day prune | integration | `uv run pytest tests/graph/test_snapshot_cli.py -x` | ❌ Wave 0 (graphifyy mocked) |
| GRAPH-02 | window staging — config raw_windows_days 적용 | unit | `uv run pytest tests/graph/test_window.py -x` | ❌ Wave 0 |
| GRAPH-03 | 5 canonical Python snippets가 fixture vault에서 non-empty | smoke | `uv run pytest tests/graph/test_canonical_queries.py -x` | ❌ Wave 0 |
| GRAPH-03 | README.md inline snippet이 import 가능한 함수 형태와 동치 | unit | `uv run pytest tests/graph/test_canonical_queries.py::test_readme_parity -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/graph/ -x` (~수 초)
- **Per wave merge:** `uv run pytest -x` (전체 스위트)
- **Phase gate:** Full suite green + manual `uv run stock graph snapshot` once → vault/graph/{today}/index.html 브라우저 열림 확인

### Wave 0 Gaps
- [ ] `tests/graph/__init__.py`
- [ ] `tests/graph/conftest.py` — fixture vault + edge fixtures + graphifyy mock
- [ ] `tests/graph/test_edges_deterministic.py` — covers GRAPH-01 (ticker_sector, mentions_ticker, note_ticker, supersedes)
- [ ] `tests/graph/test_edges_derived.py` — covers GRAPH-01 (filing_event, event_event 90d window)
- [ ] `tests/graph/test_edges_idempotency.py` — covers GRAPH-01 (ON CONFLICT)
- [ ] `tests/graph/test_get_related_regression.py` — covers GRAPH-01 D-22
- [ ] `tests/graph/test_snapshot_cli.py` — covers GRAPH-02 (graphifyy mocked, prune 검증)
- [ ] `tests/graph/test_window.py` — covers GRAPH-02 D-12
- [ ] `tests/graph/test_canonical_queries.py` — covers GRAPH-03 D-19
- [ ] `tests/db/test_migration_0004.py` — covers GRAPH-01 (CHECK 재추가, pre-validate)
- [ ] graphifyy 설치 — `uv add graphifyy`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | edges는 server-side computation, 외부 인증 없음 |
| V3 Session Management | no | — |
| V4 Access Control | no | edges DB write는 기존 ingest와 동일 신뢰 영역 |
| V5 Input Validation | yes | corp_code/ticker는 ENT-01 정규식 검증(8자리/6자리 ASCII)이 db.entity 모듈에서 이미 강제 [VERIFIED: src/db/entity.py:22-23] — edges 도 동일 helper 재사용 |
| V6 Cryptography | no | sha256 document_id는 dedup primitive (기존 Phase 2) |
| V7 Error Handling | yes | D-04 soft-fail이 PII 누출 방지를 위해 `[:200]` truncate; ingest_runs.error 칼럼은 server-side only |
| V8 Data Protection | no | edges는 metadata only, no body |
| V11 BOLA | no | — |
| V12 Files | yes | D-12 staging symlink — `notes/private/` 포함 가능. `vault/graph/`는 gitignored, 그러나 graphify HTML 출력에 private 노드 라벨 leak 가능 — plan-time 권장: `index.html`은 gitignored 위치(vault/graph/) 라서 안전, 그러나 외부 공유 시 리뷰 필요 |

### Known Threat Patterns for {Postgres + Python ingest}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection on edge_type / src_id | Tampering | SQLAlchemy `text()` + bind params (Phase 2 WR-03 재확인) — 모든 INSERT/SELECT |
| Symlink traversal escape (`vault/.graphify-staging`가 `/etc/passwd` 가리키도록 조작) | Tampering | symlink 생성은 우리 코드만, 사용자 입력 받지 않음 (target = vault/raw 안 파일만). graphify가 따라가는 symlink 경계는 `vault/.graphify-staging/` 안 — 외부 fs 접근 path traversal 가능성 낮음 |
| `vault/graph/` 출력에 private notes content leak | Information Disclosure | `vault/graph/`는 gitignored (D-14). 외부 공유 전 manual 리뷰 |
| graphifyy 패키지 supply-chain | Tampering | uv.lock으로 hash pin |
| 마이그레이션 0004 도중 partial state | Tampering | Pre-validate가 violating row 발견 시 raise — abort 안전 |
| 14-day prune이 valid snapshot 삭제 | Denial of Service | snapshot은 regenerable (vault SoT), 손실 영향 limited; mtime 정렬이 신뢰할 수 있는 OS contract |

## Sources

### Primary (HIGH confidence)
- `~/.claude/skills/graphify/SKILL.md` — graphify Python API 호출 chain (v4, 0.3.x baseline) — v5+ 일부 drift 가능 [READ]
- pypi.org/pypi/graphifyy/json — 0.7.5 latest, 2026-05-04 release, requires_python>=3.10, requires_dist 목록 [VERIFIED via curl]
- `src/db/migrations/versions/0001_phase02_initial_schema.py` lines 130-159 — edges 스키마 (composite UNIQUE + tag 컬럼 + ck_edge_type_phase2) [READ]
- `src/db/migrations/versions/0003_relax_edges_check_for_phase6.py` — DROP CHECK 패턴 [READ]
- `src/shared/frontmatter.py` lines 149-205 — DerivedBlock 실제 shape (event_type 단일, events list 부재) [READ]
- `src/db/entity.py` lines 22-23 — corp_code/ticker 정규식 [READ]
- `src/ingest/worker.py` — ingest_run hook 위치 [READ]
- `src/stock_mcp/tools/related.py` — get_related 현 구현 (depth-clamped recursive CTE) [READ]
- `src/stock_mcp/repo_root.py` — repo_root() helper [READ]
- `src/ingest/heartbeat.py` — record_source_run + extra dict 패턴 [READ]
- `.planning/phases/07-graph-layer-graphify-integration/07-CONTEXT.md` — D-01~D-22 lock-in [READ]
- `.planning/REQUIREMENTS.md` — GRAPH-01/02/03 [READ]
- `.planning/ROADMAP.md` Phase 7 — goal/success criteria [READ]
- `.planning/config.json` — GSD config 실제 형태 (model_profile/commit_docs/git/workflow만) [READ]

### Secondary (MEDIUM confidence)
- github.com/safishamsi/graphify/blob/v5/README.md — v5 latest README [CITED — not fetched in detail; SKILL.md v4 패턴과 drift 가능성 인지]
- `.gitignore` lines for graphify-out/ — vault/graph/ 추가 필요 [READ]

### Tertiary (LOW confidence — needs validation)
- "events 테이블이 현재 비어있다" — `grep -rn "INSERT INTO events"` zero hit으로 추정. Phase 5 routine이 ingest venv 외부에서 events INSERT를 수행하는지 확인 필요.

## Metadata

**Confidence breakdown:**
- Standard stack (graphifyy 0.7.5, SQLAlchemy, Alembic): HIGH — PyPI verified, version pinned
- Architecture (단일 모듈 edges.py + populate(), Alembic 0004 pre-validate, snapshot.py + window.py + 14-day prune): HIGH — CONTEXT 결정 + 코드 정찰 일치
- Pitfalls 1-3 (events 테이블 비어있음, _derived.events list 부재, supersedes INSERT 부재): HIGH (sources verified via grep)
- Pitfall 4 (graphifyy 0.7.5 vs SKILL.md v4 API drift): MEDIUM-HIGH — SKILL.md v4 패턴이 안정 추정이지만 plan-time probe 필수
- Code examples (Q1-Q5 SQL): HIGH on structure, MEDIUM on exact column names (id 컨벤션 plan-time 결정)
- Validation architecture (test 파일 매핑): HIGH — 표준 pytest + testcontainers 패턴 재사용
- Security: HIGH — 표준 SQL injection 방어 (Phase 2 WR-03) 재적용, edge가 metadata-only

**Research date:** 2026-05-05
**Valid until:** 2026-06-05 (graphifyy 빠른 릴리스 cycle 고려 — 0.7.5는 릴리스 1일차이므로 patch 버전 빠르게 변할 수 있음; 30일 review 권장)
