# Phase 3: One-Company Walking Skeleton - Context

**Gathered:** 2026-04-17
**Status:** Ready for planning

<domain>
## Phase Boundary

한 기업(삼성전자 `corp_code=00126380`) 대상으로 end-to-end 파이프라인 완성: DART 수집 → LLM-less 인제스트(content-hash dedup + bge-m3 임베딩 + mecab-ko BM25 토큰) → 하이브리드 검색(pgvector + VectorChord-BM25 + RRF) → FastMCP `search` 툴 → Claude Code의 vault citation 포함 답변. 데이터가 대량 축적되기 전에 설치해야 하는 방어선(프롬프트 인젝션 scaffolding, heartbeat, 임베딩 버전 추적)도 함께 구현. Phase 4 이후의 multi-source 확장은 이 스켈레톤 위에 얹는다.

</domain>

<decisions>
## Implementation Decisions

### DART Collection Scope
- **D-01:** 공시유형 A(정기) + B(주요사항)만 실제 수집. C(발행)·D(지분)은 `source_type` enum만 스캐폴딩 — Phase 4에서 확장.
- **D-02:** `--since` 기본값 = 오늘로부터 365일 전 (1년).
- **D-03:** `--max-docs=100` 캡 (Phase 3 한정). Phase 4에서 제거 예정.
- **D-04:** 첨부파일(PDF/HWP) 파싱 skip. 본문 텍스트만 vault/raw/dart/에 저장. PDF 원문은 Deferred (v2).

### Chunking Strategy
- **D-05:** 섹션 기본 + **섹션 > 1500 tokens이면 내부를 512/overlap 64 토큰으로 2차 분할**. bge-m3 tokenizer 기준.
- **D-06:** 소스별 parser 모듈 `src/ingest/parsers/{source}.py`. 공통 인터페이스:
  ```python
  def parse_sections(body: str, source: str) -> list[Section]
  # Section = {title: str, path: str, text: str, order: int}
  ```
- **D-07:** DART 정기보고서 = `dart-fss` TOC(목차) 기반 섹션 추출. DART 주요사항 = 전체 1섹션(짧으므로).
- **D-08:** `0002` Alembic migration으로 `chunks` 테이블에 `section_path TEXT NULL`, `section_index INT NULL` 컬럼 추가. 기존 `chunk_index INT`는 문서 전체 순서 유지.

### Hybrid Search Parameters
- **D-09:** RRF `k=60` 고정, dense/BM25 동등 가중. 튜닝은 v2 `recall@10 eval` 이후.
- **D-10:** `top_k=10` 기본값 (max=50). `excerpt_length=400 chars` 기본.
- **D-11:** 쿼리 임베딩 in-process LRU 캐시 (maxsize=256).
- **D-12:** 쿼리 BM25 토큰화 = 인덱스 토큰화. mecab-ko 동일 파이프라인.
- **D-13:** 구조화 필터 pre-vector-scan. pgvector 0.8 `iterative_scan=relaxed_order` 설정.
- **D-14:** `ticker` 필터는 `resolve_entity(ticker, as_of=date_range.end or today)`로 `corp_code` 변환 후 `entities.corp_code = :cc` 조인.

### Prompt Injection Defense (scaffolded, Phase 5에서 활성화)
- **D-15:** 3-layer scaffolding:
  - Layer 1: collector가 `provenance.trust_level` frontmatter 기록 (trusted/semi_trusted/adversarial)
  - Layer 2: `src/ingest/injection_defense.py::wrap_untrusted(body, source) -> str` 함수 + 단위 테스트 (실제 LLM 호출은 Phase 5)
  - Layer 3: `src/ingest/injection_defense.py::detect_injection_patterns(body) -> list[Match]` regex/pattern 매칭 + 단위 테스트
- **D-16:** XML 델리미터 포맷:
  ```
  <untrusted source="{source_slug}" trust="{trust_level}" doc_id="{sha256_prefix_8}">
  {body}
  </untrusted>
  ```
- **D-17:** MCP `search` 응답 excerpt를 `<vault_excerpt source="..." path="..." doc_id="...">...</vault_excerpt>` 로 wrap (Claude-facing 방어).
- **D-18:** Pattern prefilter 초기 테이블 (영어+한국어):
  - `ignore (all )?(previous|prior|above) (instructions|prompts|rules)`
  - `</?(system|assistant|user|instructions|prompt)>`
  - `DAN mode|jailbreak|developer mode`
  - `role[- ]?play as|pretend (you are|to be) (admin|root|system)`
  - "이전 지시 무시", "관리자 모드", "시스템 프롬프트 출력"
  - 매칭 시: 로그 + frontmatter `ingest_state.injection_flags: [pattern_ids]` 기록 + LLM 투입 skip (Phase 5 enforcement).
- **D-19:** `trust_level` 분류:
  - `trusted`: DART API, 한은 ECOS, FRED → Phase 5에서 LLM 투입 허용
  - `semi_trusted`: 경제 매체 (한경·이데일리·서울경제) → 허용 + delimiter wrap
  - `adversarial`: 네이버 종목토론실 (Phase 4+) → LLM 투입 **금지** (INGEST-09), 검색엔 포함

### FastMCP Deployment
- **D-20:** `uv run stock-mcp` + `.mcp.json` 커밋. `pyproject.toml`의 `[project.scripts]`에 `stock-mcp = "stock_mcp.__main__:main"` 추가. 개발 시 `claude mcp add` 또는 `.mcp.json` 자동 로드.
- **D-21:** Structured error response: `{"error": {"code": "SEARCH_TIMEOUT"|"INVALID_TICKER"|"DB_UNAVAILABLE"|"EMBEDDING_FAILED"|..., "message": str, "details": {...}}}`. 예외 타입별 매핑. raise 금지 (traceback 노출 방지).
- **D-22:** `search` 툴 시그니처:
  ```python
  @mcp.tool()
  def search(
      query: str,
      ticker: str | None = None,
      date_range: DateRange | None = None,
      source: Literal["dart","news","note"] | None = None,
      mode: Literal["hybrid","semantic","bm25"] = "hybrid",
      top_k: int = 10,
  ) -> SearchResult
  ```
  docstring은 LLM-facing 행동 계약으로 작성(MCP-10 대비).
- **D-23:** stdout은 MCP 프로토콜 전용. stderr로 구조화 JSON 로그 (`.planning/logs/stock-mcp-YYYY-MM-DD.log` tee). 각 tool call 기록: `{tool, args, latency_ms, result_size_tokens, error?}`.
- **D-24:** 서버 시작 시 `_check_db_connection()` fail-fast. DB 연결 실패 → 프로세스 exit 1, Claude Code에 initialization error 전달.

### `ingest rebuild` Semantics
- **D-25:** Full wipe + rebuild 전략. `alembic downgrade base && alembic upgrade head` → vault 전체 재스캔 → 모든 문서 재처리. Incremental reconcile은 Phase 9 `ingest doctor`(OPS-04) 역할.
- **D-26:** Per-document transaction. 실패한 문서는 skip, 다음 문서 계속. 종료 시 구조화 리포트 `{total, succeeded, failed, errors: [{doc_path, error}]}` 출력 + heartbeat 기록.
- **D-27:** 임베딩 재사용 정책: `chunks.embedding_model == current EMBEDDING_MODEL_VERSION` AND `documents.content_hash unchanged` → 기존 embedding 재사용. 위반 시 재계산. `--force-reembed` 플래그로 강제 재계산.
- **D-28:** CLI: `stock ingest rebuild [--force-reembed] [--dry-run] [--yes]`. 대화형 확인 프롬프트 (TTY 한정) + `--yes`로 CI/cron 스킵.
- **D-29:** `test_rebuild_idempotent` 테스트: `ingest run → snapshot → ingest rebuild → snapshot 비교`. row counts + 주요 컬럼 일치 (embedding은 부동소수점 variance 허용).

### Claude's Discretion
- `collectors/dart/` 내부 파일 분할 (client wrapper, filing fetcher, frontmatter writer)
- `src/ingest/worker.py`의 처리 순서 (sequential vs asyncio) — Phase 3 스케일엔 sequential 충분
- mecab-ko 설치 방법 (`mecab-ko` Python 바인딩 vs 시스템 패키지) — 리서처가 실제 환경에 맞게 결정
- `search` MCP 툴의 docstring 세부 문구 (LLM-facing 계약)
- `0002` migration에서 `chunks` 기존 row(있다면)의 `section_path` 기본값 (NULL 허용)
- HNSW 인덱스 파라미터 (`m`, `ef_construction`) — Phase 3 스케일엔 pgvector 기본값 사용
- Phase 3의 `events` 테이블 활용 여부 — DART 주요사항에서 event 추출은 Phase 5 `_derived` 이후라 Phase 3는 row 없이 둠

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 1-2 Artifacts (Locked Foundation)
- `docker-compose.yml`, `scripts/init-extensions.sql` — Postgres 17 + vchord-suite 기동
- `src/db/migrations/versions/0001_phase02_initial_schema.py` — 7 테이블 + 인덱스
- `src/db/engine.py`, `src/db/entity.py`, `src/db/alembic.ini`
- `src/shared/content_hash.py` — sha256(frontmatter-stripped body)
- `src/shared/frontmatter.py` — Pydantic 3-zone 스키마 (provenance / ingest_state / _derived)
- `pyproject.toml` — dependency groups: collectors / ingest / mcp / db / dev
- `.planning/phases/02-canonical-entity-identity/02-03-SUMMARY.md` — `resolve_entity` 호출 규약

### Requirements
- `.planning/REQUIREMENTS.md` §Collection (COLL-01/06/08/09), §Ingestion (INGEST-01/08/09/10/11/12), §Storage (STORE-03/04/05/06), §Retrieval (RET-01/02/03), §MCP (MCP-01/02), §Judgment (JUDGE-04)

### Research
- `.planning/research/ARCHITECTURE.md` §Component Responsibilities (collectors→vault→ingest→DB→MCP), §Data Flow (one document end-to-end)
- `.planning/research/PITFALLS.md`:
  - Pitfall 1 (Claude API 비용 폭주) — Phase 3의 LLM-less 보장
  - Pitfall 3 (ticker identity loss) — `resolve_entity` 통한 해결
  - Pitfall 4 (프롬프트 인젝션) — D-15~D-19 scaffolding
- `.planning/research/STACK.md` §4 Embeddings (bge-m3), §3.3 BM25 (VectorChord-BM25 + mecab-ko tokenization)

### Tech Stack
- `CLAUDE.md` §1 Data Collection (dart-fss), §4 Embeddings (bge-m3 via sentence-transformers), §3.2 pgvector 0.8 (halfvec/binary_quantize), §3.3 VectorChord-BM25 + mecab-ko, §6 FastMCP 2.x

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/shared/content_hash.py::compute_content_hash(path)` — 수집기가 sha256 계산에 재사용
- `src/shared/frontmatter.py::read_frontmatter`, `write_frontmatter` — atomic write 보장
- `src/db/entity.py::resolve_entity` — 검색 필터의 ticker→corp_code 변환
- `src/db/engine.py::get_engine()` — 공유 SQLAlchemy engine
- `tests/conftest.py::pg_engine, pg_clean` — 통합 테스트 fixture

### Established Patterns
- TDD RED→GREEN cadence (Phase 1-2에서 확립)
- Pydantic v2 models + type hints strict
- SQLAlchemy text() + bind parameters only (f-string SQL 금지 — Phase 2 REVIEW WR-03에서 확정)
- 파일 <800 LOC, 함수 <50 LOC (golden-principles.md)
- Atomic write for vault files (tempfile + os.replace)

### Integration Points
- `src/collectors/dart/__init__.py` (신규) — `from collectors.dart import collect_dart`
- `src/ingest/worker.py` (신규) — vault 스캔 → chunks/embedding 생성
- `src/ingest/parsers/dart.py`, `src/ingest/parsers/news.py` (신규) — 섹션 파서
- `src/ingest/injection_defense.py` (신규) — wrap_untrusted + detect_injection_patterns
- `src/stock_mcp/__main__.py` (신규) — FastMCP 서버 entry, `.mcp.json` 등록
- `src/stock_mcp/tools/search.py` (신규) — MCP search tool
- `src/cli/__init__.py` (신규, 선택) — `stock` CLI entry (`collect`, `ingest run`, `ingest rebuild`)

</code_context>

<specifics>
## Specific Ideas

- **테스트 대상 기업**: 삼성전자 `corp_code=00126380`, ticker `005930` — 고정. Phase 3 성공기준 #6에서 "삼성전자 최근 공시 알려줘" 쿼리 데모에 사용.
- **DART API 키**: `.env`의 `DART_API_KEY` (Phase 1 .env.example에 추가 필요). dart-fss `set_api_key()` 호출.
- **Heartbeat 파일**: `vault/ingested/_status/heartbeat.md` — frontmatter만 있는 Markdown (YAML dict): `{sources: {dart: {last_run, last_success, last_failure, docs_processed}}, ...}`. 각 collector·ingest 실행 시 atomic update.
- **`ingest rebuild` dry-run 출력 예시**:
  ```
  Would wipe: 127 documents, 543 chunks
  Would process: 127 vault files
  Embedding model: BAAI/bge-m3 (1024-d)
  Expected time: ~3 min (CPU)
  ```
- **MCP error code 네이밍 컨벤션**: UPPER_SNAKE_CASE, 도메인 접두어 (`SEARCH_TIMEOUT`, `INGEST_DB_ERROR` 등)
- **Phase 3에 **ingest 실행**이 포함되는지 vs "scaffolded only"**: 실제로 삼성전자 ~40 docs를 수집→인제스트→검색 end-to-end 돌려야 JUDGE-04 성공기준 #6 충족. "smoke test"로 다음 명령이 CI/수동으로 green:
  1. `uv run stock collect dart --corp-code=00126380 --since=2025-04-17`
  2. `uv run stock ingest run`
  3. `uv run stock-mcp` (등록된 상태)
  4. Claude Code 세션에서 "삼성전자 최근 공시" 질의 → vault citation 포함 답변

</specifics>

<deferred>
## Deferred Ideas

- DART C(발행) + D(지분) 실제 수집 — Phase 4 scope
- 첨부파일(PDF/HWP) 파싱 — v2 (저작권 정리 후, Pitfall 10 관련)
- BM25 점수 dense 대비 가중치 튜닝 — v2 recall@10 eval 이후 (V2-QUAL-01)
- `ingest rebuild --incremental` — Phase 9 `ingest doctor`로 분리
- `health()` MCP 툴 — Phase 6 MCP-09
- mecab-ko 대안 (soynlp / kiwipiepy) 벤치마크 — Phase 5 research flag, V2-ING-01
- Dense 쿼리 LRU 캐시 maxsize 튜닝 — 사용 패턴 관찰 후
- Pattern prefilter 테이블 확장 — adversarial 소스(종목토론실) 실제 도입 후 (Phase 4+)
- `event_type` 자동 분류 (DART 주요사항 → events 테이블) — Phase 5 `_derived` 이후
- `chunks.embedding`의 halfvec 전환 — 데이터 >10k 이후 용량 문제 시 (v2)

</deferred>

---

*Phase: 03-one-company-walking-skeleton*
*Context gathered: 2026-04-17*
