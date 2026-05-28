# Phase 6: Full MCP Tool Surface - Context

**Gathered:** 2026-04-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3에서 작동 중인 `search` 단일 툴(MCP-01/02) 위에, Claude Code 판단 워크플로우가 필요로 하는 **6개 read/write 툴**을 FastMCP 2.x stdio 서버에 추가한다.

이 페이즈가 **딜리버하는 것**:
1. `get_ticker_overview(ticker)` — events + portfolio + related notes 3축 통합 (MCP-03)
2. `get_recent_events(ticker, since)` — DART/news/KIND 통합 타임라인, ID-only (MCP-04)
3. `get_portfolio_state()` — `notes/private/portfolio.md` 메타 반환 (MCP-05)
4. `get_related(document_id, depth?)` — `edges` 테이블 기반 이웃 조회 (MCP-06)
5. `get_filing(id)` — ID 기반 two-step 패턴의 본문 조회 (MCP-07)
6. `add_note(path, body, frontmatter?)` — `vault/notes/` ∪ `notes/private/` 쓰기 (MCP-08)
7. `health()` — source별 상태(ok/stale/down) + DB 연결 (MCP-09)
8. CI 게이트: 각 툴 p95 latency < 5s, p95 response size < 8k tokens (MCP-10)

**경계 — 이 페이즈가 다루지 않는 것:**
- 신규 수집기·인제스트 변경 없음 (Phase 4/5 산출물 재활용)
- graphify 자체 통합·`vault/graph/` 생성은 Phase 7
- Dataview 대시보드(DASH-01~04), thesis/journal 템플릿(NOTE-01/02)은 Phase 8
- `get_valuation_context` / `get_supply_demand_signals` / `get_private_thesis` 신규 툴 3개는 Phase 10 D-23 책임 (Phase 6은 `get_ticker_overview` 응답에 nullable 자리만 마련)
- `search` MCP-02 시그니처는 그대로 유지 (Phase 10이 `source` enum에 `private_note` 추가는 Phase 10 책임)

</domain>

<prerequisites>
## Cross-Phase Prerequisites

| ID | 영역 | 상태 | Phase 6에서의 작업 |
|---|---|---|---|
| **P-01** | Phase 1 D-03 ↔ Phase 4 portfolio 경로 단일화 | 결정 완료 (Phase 10) | **Plan 첫 task: atomic cutover** — `vault/notes/portfolio.md` → `notes/private/portfolio.md` 이동 + `Portfolio.load(repo_root)` 시그니처 갱신 + fixtures/tests 갱신 + `.gitignore` 보강 |
| **P-02** | REQUIREMENTS MCP-03/05/08 wording | 갱신 완료 (Phase 10) | 없음 — 본 페이즈 plan은 갱신된 wording 기준 |
| **P-04** | Frontmatter 스키마 zone-safe 확장 | Phase 10 plan 책임 | Phase 6에는 영향 없음 (`add_note`는 `NoteFrontmatter`만 검증, provenance/ingest_state zone 미터치) |

</prerequisites>

<decisions>
## Implementation Decisions

### MCP-03 `get_ticker_overview` 구성과 Phase 10 인터페이스 (D-01 ~ D-04)

- **D-01:** **Phase 6 = nullable placeholder.** `OverviewResponse` Pydantic model에 `valuation: ValuationContext | None = None`, `supply_demand: SupplyDemandSignals | None = None`, `private_thesis: PrivateThesis | None = None` 필드를 미리 선언하되 항상 `None` 반환. 실제 조립 함수 호출은 Phase 10 D-23 신규 툴 구현 후 Phase 10 task에서 wiring. **장점:** Phase 6/10 인터페이스 파일(`models.py`)만 공유하고 구현은 독립, Pydantic 타입 안정성 보장, 재작업 최소화.
- **D-02:** **Phase 6 기본 3축**: `events` (get_recent_events 호출 결과 제한 set), `portfolio` (해당 ticker가 holdings에 있으면 그 row), `related_notes` (`search(source='note', ticker=X, top_k=5)` 결과). 단일 호출로 LLM이 1차 판단할 수 있는 최소 맥락 제공.
- **D-03:** `ticker` 파라미터는 6자리 KRX 코드 또는 `corp_code` 8자리 모두 허용 → 내부에서 `resolve_entity`(Phase 2)로 정규화. ticker recycling pitfall 회피.
- **D-04:** `as_of` 파라미터는 본 페이즈에서는 받지 않음 (Phase 10이 valuation/supply_demand 위해 별도 툴에서 받음). 기본은 항상 "현재".

### Two-step ID 패턴 일관성 (D-05 ~ D-08)

- **D-05:** **`get_recent_events(ticker, since)`**: 각 event 항목은 `{id, source, date, type, title, snippet_200ch, vault_path}`. 본문은 절대 inline 포함 안 함 — Claude가 필요 시 `get_filing(id)` 두 번째 호출. 8k 토큰 가드 충족 + JUDGE-04 vault_path 인용 보장.
- **D-06:** **`get_related(document_id, depth=1)`**: `{id, edge_type, depth, vault_path, snippet_200ch}` 리스트. `edges` 테이블 BFS, 기본 `depth=1`, 최대 `depth=2` 허용 (graphify 파일 의존 없음 — `edges` SQL 만으로 동작, Phase 7 graphify 통합과 독립).
- **D-07:** **`get_filing(id)`**: `documents.id` (sha256 content hash, Phase 2 D-01) 기반. 응답: `{id, vault_path, frontmatter, body, body_chars, truncated}`. 200K 자 초과 시 본문 truncate + `truncated=true` 플래그 (Phase 5 D-05 oversize 처리와 정합).
- **D-08:** **Snippet 생성 방법**: 각 문서의 `_derived.summary`(Phase 5 D-08) 존재 시 그것 사용 (≤200자), 없으면 `documents.body` 첫 200자. `<vault_excerpt>` XML 델리미터로 감싸 prompt-injection 방어 일관(Phase 3 INGEST-09).

### `add_note` 쓰기 정책 (D-09 ~ D-13)

- **D-09:** **Path 화이트리스트** = `vault/notes/` ∪ `notes/private/` 두 prefix만 허용. `raw/`, `ingested/`, `vault/raw/`, `dashboards/`, repo 루트 등 그 외 경로는 즉시 `WRITE_FORBIDDEN` 에러. 화이트리스트 검사는 path normalization 후 (`..` 차단, symlink resolve) 수행.
- **D-10:** **충돌 정책 = Append (default)**. path가 이미 존재하면:
  - body 앞에 구분자 추가: `\n\n---\n## {ISO timestamp KST}\n\n` + body
  - 기존 frontmatter는 유지하되 `updated` 필드만 현재 시각으로 갱신
  - `tickers`, `tags`는 frontmatter 인자로 들어왔다면 union (중복 제거)
  - **명시적 옵션 없음 (overwrite/create-only 미지원)** — 단순화 우선. 사용자가 직접 수정은 항상 자유 (vault는 Markdown).
- **D-11:** **Frontmatter 검증 = 필수**. Phase 8 NOTE-03 스키마 기반 `NoteFrontmatter` Pydantic model 도입 (이번 페이즈에서 작성):
  ```python
  class NoteFrontmatter(BaseModel):
      type: Literal["thesis", "journal", "conviction", "note"]
      tickers: list[str] = Field(default_factory=list)  # 6자리 또는 corp_code 허용
      tags: list[str] = Field(default_factory=list)
      created: datetime  # 자동 채움 (호출자 제공 시 그대로)
      updated: datetime  # 항상 현재 시각으로 자동 set
      author: str = "yamin"  # config 또는 환경변수에서 default
      conviction_score: float | None = None  # 0~1, conviction.md only
  ```
  - 호출자가 `type` 누락 시 `INVALID_FRONTMATTER` 에러
  - `created`, `updated`, `author`는 호출자 미제공 시 자동 채움
  - tickers는 `resolve_entity`로 정규화 (잘못된 ticker는 에러 아닌 warning + 그대로 저장)
- **D-12:** **Path alias / 자동 mkdir**:
  - `path='journal/today'` 또는 `path='journal'` → `notes/private/journal/{YYYY-MM-DD KST}.md` 으로 자동 해석
  - `path='005930/thesis'` → `notes/private/005930/thesis.md`
  - 디렉터리가 없으면 자동 mkdir -p (화이트리스트 prefix 안에서만)
  - 명시적 `.md` 확장자 없으면 자동 추가
- **D-13:** **Append 멱등성**: 동일 ISO 타임스탬프 헤더 + 동일 body가 직전 append와 일치하면 skip + `idempotent=true` 플래그. 사용자가 같은 메모를 두 번 호출해도 중복 적재 안 됨.

### `health()` 응답과 임계값 (D-14 ~ D-17)

- **D-14:** **Source별 staleness 임계값 (code constant)**:
  ```python
  STALENESS_THRESHOLDS_HOURS = {
      "dart": 26,    # daily-batch + 2h 여유
      "krx": 26,     # daily-batch + 2h
      "news": 12,    # 일중 갱신 기대
      "macro": 26,   # daily-batch
      "kind": 26,    # daily-batch
  }
  ```
  코드 상수 (config.json 외부화 X) — 운영 중 빈번 변경 없음, fixture에서는 monkeypatch 가능.
- **D-15:** **응답 스키마 — per-source status enum**:
  ```python
  class SourceHealth(BaseModel):
      status: Literal["ok", "stale", "down"]
      last_success: datetime | None
      age_hours: float | None
      last_error: str | None  # 마지막 실패 메시지 (앞 200자)

  class HealthResponse(BaseModel):
      overall: Literal["ok", "stale", "down"]  # any down -> down, any stale -> stale, else ok
      sources: dict[str, SourceHealth]  # dart/krx/news/macro/kind
      db: SourceHealth  # status: ok/down (stale 없음), age_hours = NULL
      timestamp: datetime
  ```
- **D-16:** **데이터 소스 우선순위 = `ingest_runs` 테이블 (OPS-03) → `vault/ingested/_status/heartbeat.md` fallback**. SQL `SELECT source, MAX(end_at) FILTER (WHERE status='ok') AS last_success, MAX(end_at) AS last_attempt, ... FROM ingest_runs GROUP BY source`. DB 연결 실패 시 heartbeat.md (Phase 3 INGEST-12) 파싱으로 fallback — vault만 있어도 health 동작 보장 (단 `db.status='down'`).
- **D-17:** **DB connectivity 체크**: `_check_db_connection`(현존, server.py) 재사용. 실패 시 `db.status='down'` + `last_error`. 다른 source는 fallback 경로로 응답.

### CI 게이트 측정 (D-18 ~ D-20)

- **D-18:** **Fixture vault + testcontainers Postgres**. `tests/fixtures/mcp-vault/` 신규 디렉터리: 약 10개 ticker (현 watchlist 기반), 100개 문서 (DART 4유형 mix + 뉴스 + KIND + 메모). `pytest` fixture가 testcontainers로 Postgres 인스턴스 띄우고 alembic upgrade + ingest 후 MCP 툴 호출.
- **D-19:** **N=20회 반복으로 p95 측정**. 각 툴마다 대표 호출 1개 (예: `get_ticker_overview('005930')`), 20회 호출 → 응답 latency 분포 + 응답 dict의 `json.dumps()` 토큰 추정 (`tiktoken`의 cl100k_base 인코더로 길이 측정). p95 latency >5s 또는 p95 tokens >8k 시 `pytest.fail`.
- **D-20:** **CI 실행 위치**: PR test (필수, 평균 추가 시간 ~3분 예상). nightly 별도 안 함 (간단성 우선). 측정 결과는 `tests/perf/{tool_name}.json` 으로 저장, PR diff에서 회귀 검토 가능.

### `get_portfolio_state` 형태 (D-21)

- **D-21:** **메타 only 반환**. 시세/평가액 미포함. 응답:
  ```python
  class PortfolioRow(BaseModel):
      ticker: str
      corp_code: str | None
      qty: int | None  # 표기 단위는 portfolio.md 그대로
      avg_cost: float | None
      tags: list[str] = Field(default_factory=list)
      note: str | None  # portfolio.md 자유 메모

  class PortfolioState(BaseModel):
      holdings: list[PortfolioRow]
      watchlist: list[PortfolioRow]  # qty/avg_cost 보통 null
      source_path: str  # "notes/private/portfolio.md"
      last_modified: datetime
  ```
  평가액·평가손익 계산은 Claude가 별도 SQL/툴 호출로 수행 (책임 분리, MCP 툴 단순성 유지).

### MCP-03 응답 토큰 가드 전략 (D-22 ~ D-23)

- **D-22:** **8k 토큰 가드 유지** (ROADMAP MCP-10 그대로). 응답이 8k 임계 접근 시 **섹션별 우선순위 역순 truncation**:
  - 우선순위 (높음 → 낮음): `events` → `related_notes` → `portfolio` → `supply_demand` → `valuation` → `private_thesis`
  - 우선순위 낮은 섹션부터 잘라냄 (필드 자체를 `null` + `truncated_section: true` 메타 추가)
  - events/related_notes는 항목 단위 truncate (top_k 축소), 그 외는 섹션 단위 drop
  - 최종 응답에 `truncation_applied: list[str]` 메타 동봉 (어느 섹션이 잘렸는지 LLM에 명시)
- **D-23:** Phase 6 시점에는 valuation/supply_demand/private_thesis는 항상 `None`이라 실제 truncation은 events/related_notes만 발생. Phase 10이 채우면서 truncation 로직이 진가 발휘.

### Tool Docstring Contract (D-24)

- **D-24:** 모든 7개 툴 docstring은 Phase 3 `search` 툴(`tools/search.py`) 패턴을 그대로 따름:
  - 첫 줄 한 문장 요약 + 요구사항 ID 인용 (`(MCP-04, JUDGE-04)`)
  - `### Behavior contract` 섹션: 각 파라미터의 정확한 의미, 허용 값, 정규화 규칙
  - `### Response shape` 섹션: 응답 dict 키/타입을 산문으로 풀어 LLM이 모델 없이도 구조 추정 가능
  - `### Errors` 섹션: 가능한 에러 코드와 원인 (절대 `raise` past tool boundary 금지)
  - `### Performance budget` 섹션: p95 latency, 응답 토큰 한도

### Folded Todos
없음 (todo backlog 매칭 항목 없음 — 검증 후 추가 시 update).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Boundary & Roadmap
- `.planning/ROADMAP.md` §"Phase 6: Full MCP Tool Surface" — goal·success criteria·requirement IDs
- `.planning/REQUIREMENTS.md` MCP-03 ~ MCP-10 (특히 MCP-03/05/08 AMENDED 표기 확인)
- `.planning/STATE.md` — 현 진행 상태

### Cross-Phase Decisions (반드시 준수)
- `.planning/phases/01-load-bearing-foundation/01-CONTEXT.md` — D-03 (notes/private/ overlay), D-05 (.gitignore 정책), D-09 (frontmatter zone 분리)
- `.planning/phases/02-canonical-entity-identity/02-CONTEXT.md` — D-01 (corp_code as PK), D-08 (supersedes 체인), `resolve_entity` 헬퍼 위치
- `.planning/phases/03-one-company-walking-skeleton/03-CONTEXT.md` — D-21 (stdout JSON-RPC 보호 / 에러는 dict로), D-22 (search 응답 envelope), D-24 (DB fail-fast)
- `.planning/phases/04-multi-source-collector-coverage/04-CONTEXT.md` — D-01/D-03/D-04 AMENDED (`Portfolio.load(repo_root)`), heartbeat 위치
- `.planning/phases/05-claude-schedule-enrichment-with-korean-number-safety/05-CONTEXT.md` — D-07 (zone integrity), D-08 (event_type enum), D-11 (review_flags), summary 필드
- `.planning/phases/10-decision-context-coverage-peer-historical-valuation-supply-d/10-CONTEXT.md` — P-01 (portfolio cutover), D-21 (add_note whitelist 확장), D-23/D-24 (Phase 10 신규 툴 인터페이스)

### Codebase Patterns (필독)
- `src/stock_mcp/server.py` — FastMCP 서버 조립 + `_check_db_connection` fail-fast 헬퍼
- `src/stock_mcp/tools/search.py` — `@mcp.tool()` 데코레이터 패턴, docstring 형식, 에러 핸들링
- `src/stock_mcp/models.py` — Pydantic ConfigDict(extra="forbid") 패턴
- `src/stock_mcp/errors.py` — `ErrorCode` enum, `StructuredError`, `to_error_response`
- `src/stock_mcp/logging.py` — `log_tool_call` 데코레이터/헬퍼
- `src/stock_mcp/search_core.py` — DB 액세스 패턴 참고
- `src/shared/portfolio.py` (또는 등가) — `Portfolio.load` 시그니처
- `src/shared/frontmatter.py` — `FrontMatter`, `ProvenanceBlock`, `IngestStateBlock`, `DerivedBlock` (NoteFrontmatter는 본 페이즈에서 신규)
- `src/db/entity.py` — `documents`, `chunks`, `entities`, `edges`, `ingest_runs` 모델
- `src/db/seed_name_aliases.py` — alias seeding (R-09)

### External Specs
- FastMCP 2.x docs (CLAUDE.md TechStack §6) — tool registration, stdio transport
- ROADMAP success criteria: <8k tokens, <5s p95 latency, write-scope enforcement

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`mcp` instance** (`src/stock_mcp/tools/search.py`) — 재사용. 신규 툴은 `from .search import mcp` 후 `@mcp.tool()` 데코레이터.
- **`StructuredError` / `to_error_response`** — 모든 신규 툴 에러 핸들링에 그대로 적용. 신규 코드 추가: `WRITE_FORBIDDEN`, `INVALID_FRONTMATTER`, `PATH_NOT_FOUND`, `INVALID_TICKER` (이미 있음), `STALE_DATA` 등.
- **`log_tool_call`** — 모든 신규 툴에 동일 적용 (관측성).
- **`_check_db_connection`** — `health()` DB 체크에 재사용.
- **`resolve_entity(ticker_or_corp_code, as_of=...)`** (Phase 2) — ticker 정규화 일원화.
- **`hybrid_search`** (`search_core.py`) — `get_ticker_overview`의 related_notes 조회에 직접 사용.
- **testcontainers Postgres fixture** (Phase 2/3 테스트) — CI 게이트 테스트 setup 재사용.

### Established Patterns
- **stdio = JSON-RPC stream**: `print()`/`raise`가 protocol 깬다 — 모든 에러는 dict 반환 (D-21 search.py).
- **Pydantic `extra='forbid'`**: 응답 모델 불변 계약, 알 수 없는 필드 허용 안 함.
- **Frontmatter zone 분리**: `provenance` / `ingest_state` / `_derived` — `add_note`는 `_derived` 미터치, `NoteFrontmatter`는 별도 zone (단일 dict).
- **Content-hash dedup**: `documents.id = sha256(body)` (Phase 2 D-01) — `get_filing(id)`가 키로 그대로 사용.
- **`vault/raw/`는 collector + Phase 5 agent만 쓰기**, `vault/notes/` ∪ `notes/private/` 만 MCP 쓰기 허용.

### Integration Points
- **`.mcp.json`**: 신규 툴 등록 자동 (FastMCP `@mcp.tool()` side effect). 별도 manifest 갱신 없음.
- **`src/stock_mcp/server.py`**: 신규 툴 모듈을 import해 등록. `tools/__init__.py` 또는 server.py에 명시적 import 필요.
- **`alembic`**: 본 페이즈에서 신규 마이그레이션 없음 (Phase 10 P-04가 별도 처리).
- **`stock` CLI**: `stock-mcp serve` 등은 Phase 3 산출물 그대로 사용.

</code_context>

<specifics>
## Specific Ideas

- **NoteFrontmatter 위치 제안**: `src/shared/frontmatter.py`에 추가 (기존 zone 모델과 같은 모듈, 일관성). Phase 8 NOTE-03이 본 모델을 그대로 ingest 인덱싱에 재사용.
- **Snippet 생성 헬퍼**: `_derived.summary` 우선 + body fallback 로직은 `src/stock_mcp/snippets.py` 같은 신규 모듈로 분리 (events/related/filing 모두 사용).
- **Tool 모듈 분할**: `tools/overview.py`, `tools/events.py`, `tools/portfolio.py`, `tools/related.py`, `tools/filing.py`, `tools/notes.py`, `tools/health.py` — 1 파일 1 툴 (Phase 3 search.py 패턴 유지, 200~400줄/파일 가이드).
- **CI fixture 재사용**: 가능하면 Phase 4 fixture 데이터를 확장 (중복 fixture 회피).
- **Two-step flow 문서화**: README 또는 `docs/mcp-tool-contract.md`에 "events list → get_filing(id)" 패턴을 LLM-facing prose로 명시 (Claude가 자연스럽게 chain).

</specifics>

<deferred>
## Deferred Ideas

- **`get_ticker_overview`에 시세/평가액 포함** → Phase 10이 valuation 채울 때 자연스럽게 다뤄짐 (별도 가격 결합 X).
- **Multi-user 권한 모델 (chunks.visibility)** → Phase 10 D-22 deferred 그대로 (v2).
- **Tool 동적 등록 / plugin 시스템** → out-of-scope, FastMCP 2.x stable 패턴 직접 사용.
- **MCP-03 응답 cache (TTL 5분)** → 측정 후 필요 시 V2.
- **add_note의 `mode` 파라미터 (overwrite/create-only)** → 사용자 needs 발생 시 추가, 본 페이즈는 append-only.
- **graphify wiki/json output 직접 활용** → Phase 7 책임. 본 페이즈 `get_related`는 SQL `edges`만 사용.

</deferred>

<post_completion>
## Post-Completion Notes

**Added:** 2026-05-05 (after phase shipped)

### L-01: MCP clients spawn servers with a clean environment
- **Symptom:** Claude Code `/mcp` showed `Failed to reconnect to stock-mcp`; server died ~1s after spawn because `_check_db_connection` failed without `DATABASE_URL`.
- **Cause:** Claude Code launches MCP servers with effectively `env -i` — `.env` does NOT auto-load even though `uv run` is the entrypoint. The DB-fail-fast guard (Phase 3 D-24) then aborts boot.
- **Fix (commit 040eba8):** `.mcp.json` command must pass `uv run --env-file .env stock-mcp serve` so secrets propagate without being baked into `.mcp.json` itself.
- **Apply to future phases:** Any new MCP entrypoint or env-dependent server must be validated by spawning from a *clean* shell (or via Claude Code itself), not just `uv run` from a developer terminal that already has `.env` sourced.

### L-02: Orchestrator probe is not a substitute for human UAT
- **Symptom:** HUMAN-UAT items were initially marked resolved based on an orchestrator probe (e3ff612), then reverted to pending (43b521c) because the probe didn't exercise the real Claude Code ↔ stdio handshake — which is exactly where L-01 was hiding.
- **Lesson:** A probe Claude can run autonomously verifies the *server* responds to JSON-RPC; it does NOT verify that a *real MCP client* (Claude Code, Claude Desktop) can spawn, authenticate, and call the tools end-to-end. Process gates that require "human UAT" must be exercised by a human in the actual client.
- **Apply to future phases:** When a phase has HUMAN-UAT criteria, no autonomous probe — however thorough — may close them. The verifier agent should treat orchestrator-only verification as `partial` until a human confirms in the real client.

</post_completion>

---

*Phase: 06-full-mcp-tool-surface*
*Context gathered: 2026-04-26*
*Post-completion notes added: 2026-05-05*
