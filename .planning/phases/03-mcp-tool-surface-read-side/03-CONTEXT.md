# Phase 3: MCP Tool Surface (Read-Side) - Context

**Gathered:** 2026-06-01
**Status:** Ready for planning
**Source:** discuss-phase (gsd-discuss-phase 3)

<domain>
## Phase Boundary

`src/mcp_v2/` 신규 모듈 — FastMCP 2.x **stdio** 서버로 read-side 타입드 도구 surface를 제공한다.
삭제된 v1.0 `src/stock_mcp/`(archive에만 존재)를 대체한다. `.mcp.json`이 서버를 등록한다.

**도구 10종 (ROADMAP SC#2에 lock — 이름·반환 타입 변경 금지):**
`get_filing`, `search_filings`, `ohlcv_range`, `flow_range`, `peer_view`, `hybrid_search`,
`get_note`, `get_decision_card`, `list_portfolio`, `get_briefing`.

핵심 원칙(redesign §2 line 195): **모든 도구는 typed Pydantic row 반환, chunk 반환 금지.
Claude가 code-execution으로 작은 Python을 짜서 도구들을 조합한다** (Anthropic "Code Execution
with MCP", 98.7% 토큰 절감).

이 phase는 **WHAT(도구 10종 이름·시그니처·반환 타입, FastMCP/stdio, run_sql 금지, hybrid_search
narrative-only+RRF k=60, get_decision_card payload 기본)**을 ROADMAP SC#1-5 + redesign §2에서
lock으로 받고, **HOW(에러/빈결과 표현, search 반환 모양, injection 방어 정책, 결과 한도)**를 이
CONTEXT.md에서 결정한다.

Depends on Phase 1 (filings/news/ohlcv/macro_series/notes 데이터) + Phase 2 (decision_cards).
</domain>

<decisions>
## Implementation Decisions

### 영역 1 — 도구 에러 / 빈결과 표현 (Veto #7: fail loud)

- **D-01:** **빈결과 = 정상 빈 모델, 실패 = typed 예외.** 데이터가 없을 뿐인 정상 케이스
  (조회 결과 0건)는 빈 list/`None` 필드를 가진 **정상 Pydantic 모델**로 반환한다. 진짜 실패
  (존재하지 않는 ticker/corp_code, DB 오류, 잘못된 인자)는 **typed 예외**(예: `McpToolError`
  계층)를 raise한다 — FastMCP가 이를 MCP error 응답으로 변환한다.
- **근거:** Veto #7 — silent SQL/도구 실패가 finance-agent 환각의 ~60%. "no data"(정상)와
  "error"(loud)를 코드 레벨에서 명확히 구분. `None`으로 둘 다 뭉개지 않는다.
- **시사:** 각 도구의 반환 타입 Pydantic 모델은 "빈 상태"를 표현 가능해야 함(빈 컬렉션 OK).
  에러 메시지는 호출자가 무엇을 고쳐야 하는지 알 수 있게 구체적으로(어떤 인자가 잘못됐는지).

### 영역 2 — hybrid_search 반환 모양 (references vs blobs)

- **D-02:** **참조 + 스니펫만.** `hybrid_search`는 매치당 **ID + RRF score + 짧은 스니펫**만
  반환한다. body_md 전문은 포함하지 않는다 — 에이전트가 필요한 매치에 대해서만
  `get_filing(rcept_no)` / `get_note(path)`로 전문을 별도 fetch한다.
- **근거:** redesign §2 line 91 "expose MCP servers as code APIs returning *references*, not
  blobs" (98.7% 토큰 절감). 검색은 "후보 선별"용, 전문 dump는 선별 후 별도 단계.
- **시사:** hybrid_search 반환 모델 = `list[SearchHit]` 형태 (각 hit: source_type, id/path,
  rrf_score, snippet, 매치된 source). 스니펫 길이(±N자)는 planner/research discretion.

### 영역 3 — Prompt-injection 방어 정책 (SC#5)

- **D-03:** **항상 XML delimiter 래핑 + 패턴 매치 시 플래그 후 통과 (차단 안 함).** 모든
  narrative 본문은 XML delimiter로 감싸서 반환한다. prefilter 패턴에 걸리면 해당 본문을
  **차단하지 않고**, 반환 모델 메타데이터에 경고 플래그(예: `injection_suspected: true` +
  매치 사유)를 달아 통과시킨다.
- **적용 범위:** narrative 본문을 반환하는 모든 도구 — `get_filing`(body_md),
  `get_note`(content_md), `hybrid_search`(스니펫). 순수 숫자 도구(ohlcv/flow/peer)와
  구조화 derived 필드는 대상 아님.
- **근거:** 차단(block)은 정상 DART 사업보고서/뉴스가 naive 필터에 걸려 사라지는
  false-negative 위험이 큼. 살균(strip)은 원문 훼손 → 숫자 verbatim checksum(Veto)과 충돌.
  래핑+플래그가 "사람/상위 에이전트가 감사 가능하되 정상 데이터는 손실 없음"의 균형점.
- **시사:** 구체적 prefilter 패턴 세트와 XML delimiter 포맷은 planner/research가 결정
  (prompt-injection 패턴 best practice 조사).

### 영역 4 — 기본 결과 한도 / 범위 캡

- **D-04:** **합리적 기본값 + 명시 `limit` 인자. 하드 캡보다 "호출자가 범위 명시"가 원칙.**
  - `ohlcv_range` / `flow_range`: 호출자가 `from_date`/`to_date`를 **필수**로 명시 (하드 상한
    없음 — 범위는 호출자 책임).
  - `search_filings`: 기본 `limit=50`, `limit` 인자로 조정 가능. `filed_at DESC` 정렬.
  - `hybrid_search`: 기본 top-10 (RRF k=60 합성 후), `limit` 인자 가능.
  - `get_filing` / `get_note` / `get_decision_card`: 단건.
- **근거:** 토큰 예산 보호와 유연성의 균형. 무제한은 실수로 폭주, 엄격 하드 캡은 대량 조회 시
  여러 번 호출 강제. 기본값으로 보호하되 호출자가 명시적으로 늘릴 수 있게.

### Claude's Discretion (planner / research에 위임)

사용자 선호 없음 — RESEARCH best-practice 확인 후 planner 결정:

1. **`src/mcp_v2/` 모듈 구조** — `server.py` + `tools/` + `models.py`(반환 Pydantic) +
   `errors.py` 분리 여부. archive `src/stock_mcp/`(errors.py/models.py/snippets.py/server.py/
   tools/ 구조)를 참조 패턴으로 — 단 `search_vault`/run_sql류는 가져오지 않는다.
2. **hybrid_search 스니펫 길이(±N자)** + 스니펫 추출 방식(매치 주변 윈도우 vs 본문 head).
3. **prefilter 패턴 세트 + XML delimiter 포맷** (injection 방어 — best practice 조사).
4. **RRF k=60 구현 디테일** (k=60은 SC#4 lock) + pgvector dense + VectorChord-BM25 결합 SQL.
   Phase 1/2의 `body_tsv` config 및 `body_emb halfvec(1024)` 패턴 재사용.
5. **`.mcp.json` 등록 + stdio 서버 기동** 방식 (Claude Code config / systemd 등).
6. **각 도구 반환 Pydantic 모델 정의** (빈 상태 표현 가능하게 — D-01).
7. **`peer_view` "동종업종 median PER/PBR/ROE" 계산** — `entities.sector` 그룹핑 + 재무 소스.
8. **`get_decision_card`가 `src/cards/store.get_active`를 wrapping** — view="payload"(기본)|
   "both" serialize-time exclude (Phase 2에서 get_active가 full DecisionCard 반환하도록 설계됨).
9. **`get_briefing` 구현 시점** — ROADMAP SC#2는 Phase 3 도구로 나열하나 briefing row(report_type)
   는 Phase 5. Phase 3에서는 decision_cards를 조회해 **현재는 빈 결과**(report_type 컬럼/데이터
   부재를 D-01의 "빈 모델"로 처리) 반환하는 형태로 구현 가능. 완전 wiring은 Phase 5. planner 판단.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner) MUST read these before acting.**

### Architecture / Design (authoritative)
- `.planning/research/redesign-2026-05.md` §2 — **PRIMARY.** Data refinement shape, MCP tool
  surface 표(line 181-195), code-execution-with-MCP 패턴(typed rows not chunks), anti-patterns
  (line 197-201: no embedding numbers / no run_sql / no pre-chunking). DB schema sketch
  (entities/filings/news/ohlcv/macro_series/notes/decision_cards) line 95-179.
- `.planning/research/redesign-2026-05.md` §3 — decision_card payload schema (`get_decision_card`
  반환 구조).
- `.planning/research/redesign-2026-05.md` §4 — frontmatter+body 패턴, `get_decision_card`
  payload-only default 근거.
- `.planning/research/redesign-2026-05.md` §6 — architecture diagram, 도구가 "3. 데이터 정제"
  위치.
- `.planning/research/redesign-2026-05.md` §8 Sources — Anthropic Code Execution with MCP,
  FinAI Data Assistant (arXiv 2510.14162), FastMCP.

### Project-wide constraints
- `CLAUDE.md` Hard Vetoes — **#6** (숫자 embedding 금지, hybrid_search 숫자 테이블 제외),
  **#7** (run_sql escape hatch 금지 — CI 가드, 모든 도구 typed Pydantic 함수),
  **#8** (DART 본문 pre-chunking 금지 — get_filing 전체 body_md),
  **#13** (get_decision_card default = payload만, view="both" 명시 시에만 body_md).
- `CLAUDE.md` Conventions — Python 3.12, strict mypy, Pydantic v2, MCP 도구 네이밍 규약
  (`get_*` 단일 entity, `search_*` structured filter, `*_range` 시계열, `hybrid_*` narrative).

### Roadmap lock
- `.planning/ROADMAP.md` Phase 3 (line 105-132) — Goal, Depends on, Success Criteria SC#1-5
  (모듈/서버, 도구 10종, run_sql 금지+CI 가드, hybrid_search narrative-only, injection 방어).

### Code to build on / reference
- `src/cards/store.py` — `get_active(engine, corp_code)`가 full typed `DecisionCard` 반환.
  `get_decision_card`가 이를 wrapping (view=payload|both는 serialize-time exclude).
- `src/cards/models.py` — `DecisionCard` Pydantic 모델 (get_decision_card 반환 타입).
- `src/db/entity_models.py` + `src/db/migrations/versions/0006_phase01_domain_tables.py`,
  `0007_decision_cards.py` — 도구들이 조회하는 테이블 (entities, filings, news, ohlcv,
  macro_series, notes, decision_cards). `_HalfVec` UserDefinedType, body_tsv/body_emb 패턴.
- `archive/llm-wiki-2026-04:src/stock_mcp/` — **대체 대상 v1.0 surface** (git archive 브랜치).
  구조 참조용(errors.py / models.py / snippets.py / server.py / tools/) — `search_vault`/
  run_sql류 패턴은 가져오지 않음. `git show archive/llm-wiki-2026-04:src/stock_mcp/<file>`.

### External docs
- Anthropic "Code Execution with MCP" (Nov 2025) —
  https://www.anthropic.com/engineering/code-execution-with-mcp (references-not-blobs 근거).
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/cards/store.get_active` — `get_decision_card`의 핵심; full typed DecisionCard 반환하므로
  view 분기는 serialize-time `model_dump(exclude=...)`로 처리 (Phase 2에서 의도적으로 설계됨).
- `src/db/entity_models.py` ORM + `_HalfVec` 타입 — 도구 쿼리/모델에 재사용.
- Phase 1 narrative 테이블 (filings/news/notes: `body_md` + `body_tsv` + `body_emb halfvec(1024)`)
  — hybrid_search의 dense+BM25 RRF 대상. `decision_cards`/`ohlcv`/`macro_series`는 **제외**.

### Established Patterns
- **Typed Pydantic 반환** (Phase 2 DecisionCard) — 모든 도구가 따름.
- **파라미터화된 `text()` SQL** (store.py — Veto #7) — 도구 SQL도 동일, f-string/run_sql 금지.
- **strict mypy + Python 3.12 + Pydantic v2** (전 phase 공통).
- **`uv`는 Bash PATH에 없음** — 테스트는 `.venv/Scripts/python.exe -m pytest`로 실행.

### Integration Points
- 도구는 Phase 1(filings/news/ohlcv/macro/notes) + Phase 2(decision_cards) 테이블을 read.
- `.mcp.json`이 stdio 서버 등록 → Claude Code에서 도구 호출.
- Phase 4 analysis runner(Bull/Bear/Judge)가 이 도구들을 evidence 수집에 사용.
- `get_note`/`list_portfolio`는 `notes/private/`(gitignored, on-disk) 화이트리스트 read-only.
</code_context>

<specifics>
## Specific Ideas / References

- **hybrid_search**: RRF k=60 (SC#4 lock), narrative-only — `filings.body_md` / `news.body_md` /
  `notes.content_md`만. `ohlcv` / `macro_series` / `decision_cards` 대상 호출 **금지** (SC#4, Veto #6).
- **get_decision_card**: payload-only 기본, `view="both"` 옵션 시 body_md 포함 (Veto #13).
  `latest=true` 기본 (corp_code의 최신 active 카드).
- **get_note**: `notes/private/` 화이트리스트, read-only, path-traversal 방어 필수.
- **list_portfolio**: `notes/private/portfolio.md` 파싱.
- **도구 네이밍 규약 준수**: `get_*`(단일), `search_*`(filter), `*_range`(시계열), `hybrid_*`(narrative).
- **CI 가드**: `run_sql`/임의 SQL 실행 도구가 추가되지 않았는지 검증하는 테스트(SC#3).
</specifics>

<deferred>
## Deferred Ideas

논의 중 surface된 비-Phase-3 아이디어 / 후속 phase 의존:

- **`get_briefing` 완전 wiring** — briefing row(report_type 컬럼 + 데이터)는 Phase 5 산출물.
  Phase 3는 빈 결과 반환 형태로만 구현(D-01 빈 모델), 완전 동작은 Phase 5. (Claude Discretion #9)
- **decision_cards 의미 검색** — Phase 2에서 `body_embedding` 미추가(narrative 검색 제외 lock).
  Phase 4가 카드 간 의미 검색이 필요해지면 `ALTER TABLE`로 도입 (Phase 2 deferred 이어받음).
- **쓰기-side MCP 도구** (save_card 등 노출) — 이 phase는 **read-side만**. 쓰기는 Phase 4
  analysis runner가 `src/cards/store`를 직접 호출 (MCP 경유 아님). 명시적 out-of-scope.
- **write/action 도구 (KIS 주문 등)** — Phase 6+ action layer.

### Out of Scope for Phase 3
- decision_cards/ohlcv/macro_series에 대한 hybrid_search 호출 (Veto #6, SC#4)
- run_sql / 임의 SQL escape hatch (Veto #7, SC#3)
- DART 본문 pre-chunking (Veto #8 — 전체 body_md 반환)
- analysis runner / 3-role debate (Phase 4)
- briefing 생성 (Phase 5 — Phase 3는 조회 도구만)
- KIS auto-trade (Phase 6)
</deferred>

---

*Phase: 03-mcp-tool-surface-read-side*
*Context gathered: 2026-06-01 via /gsd-discuss-phase 3*
