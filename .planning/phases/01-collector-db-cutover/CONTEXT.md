# Phase 1 Context — Collector DB-Direct Cutover

**Milestone:** v2.0 (DB-direct redesign)
**Phase slug:** `01-collector-db-cutover`
**Status:** scaffolded, awaiting research → plan
**Created:** 2026-05-29

## Goal (verbatim from ROADMAP)

5개 collector(`dart`, `krx`, `news`, `macro`, `kind`)가 `vault/raw/*.md` 출력을 멈추고
Postgres 테이블에 직접 INSERT한다. `shared/heartbeat.py` no-op stub과 `--vault-root` CLI 인자도
제거한다.

## Success Criteria (verbatim from ROADMAP)

1. `uv run stock collect dart --corp-code=00126380 --since=2026-01-01`이 `filings` 테이블에 직접
   INSERT 한다. `vault/raw/` 디렉토리가 다시 생기지 않는다.
2. `krx`, `news`, `macro`, `kind` 모두 같은 패턴: 각자의 테이블(`ohlcv`, `news`, `macro_series`,
   `events`)에 직접 INSERT. content-hash 기반 dedup은 그대로 유지 (UPSERT ON CONFLICT).
3. `src/shared/heartbeat.py` no-op stub이 제거되고 collector 5개에서 import도 제거된다.
   실행 통계는 구조화된 로그(`logging.info(extra=...)`)로 stderr에만 남긴다.
4. `--vault-root` CLI 인자가 모든 subcommand에서 제거된다.
5. `tests/collectors/` 테스트 스위트가 INSERT 경로를 검증한다. Markdown 작성 stub은 모두 제거된다.
6. `stock-enrich-daily` routine은 이미 disable됨 — 추가 작업 없음.

## Driving Design Decisions

- `.planning/research/redesign-2026-05.md` §2 — "Postgres가 source of truth, Markdown 중간층 폐기"
- `.planning/research/redesign-2026-05.md` §2 schema sketch — domain-specific tables (`filings`,
  `news`, `ohlcv`, `macro_series`, `events`, `notes`, `decision_cards`) with narrative columns
  carrying `body_md TEXT` + `body_tsv tsvector` + `body_embedding halfvec(1024)`.
- **CLAUDE.md Hard Vetoes** (모두 적용):
  - Veto #6: 숫자 embedding 금지 — OHLCV/재무 수치는 typed 컬럼
  - Veto #8: DART pre-chunking 금지 — `body_md` 전체 저장
  - Veto #9: Markdown vault를 source of truth로 부활시키지 마라

## Current Codebase State (post-shutdown)

### Collectors (모두 `vault/raw/*.md` 출력 중)
- `src/collectors/dart/` — DART filings (dart-fss 래퍼)
- `src/collectors/krx/` — KRX OHLCV/flow/short (pykrx + FinanceDataReader)
- `src/collectors/news/` — RSS + trafilatura
- `src/collectors/macro/` — ECOS + FRED (PublicDataReader + fredapi)
- `src/collectors/kind/` — KIND 비정형 이벤트

각 collector는:
- `from shared.heartbeat import record_source_run` (no-op stub 호출 중)
- `vault_root` 인자 받음
- `writer.py` 모듈에 Markdown 작성 함수 보유

### DB schema (현재 마이그레이션 head 기준)

v1.0에서 만든 테이블이 잔존:
- `entities`, `entity_aliases` — entity identity (corp_code PK). **Phase 1에서 그대로 사용.**
- `documents` — content-hash PK, Markdown ingest 시 사용했던 테이블. 현재는 v2.0에서 *어떻게 할지
  open question* (drop? rename? coexist?).
- `chunks` — embedding 청크. 이번 Phase 범위 밖이지만 운명 결정 필요.
- `ingest_runs`, `edges`, `events` — 일부는 재사용 가능 (events는 KIND collector 용도 그대로 쓸 수
  있을지 검토 필요)
- `documents.section_path`, `chunks.embedding`, `chunks.bm25_tokens` — Phase 3 (MCP)에서 다시
  검토할 부분; Phase 1에서는 건드리지 않음.

마이그레이션 0001~0005 존재. **Phase 1은 0006부터.**

### CLI
- `src/cli/__main__.py` — collect 서브커맨드만 잔존 (ingest/sync/graph 삭제됨)
- `--vault-root` 인자가 모든 collect 서브커맨드에 존재 — 제거 대상

## Open Questions for Researcher

Researcher (`gsd-phase-researcher`)가 답해야 할 것:

### Q1. Domain table schemas (구체)
`redesign-2026-05.md` §2의 schema sketch를 구체화. 각 테이블의:
- 정확한 컬럼 타입 (TIMESTAMPTZ vs DATE, halfvec vs vector 등)
- PK / UNIQUE / FK 제약
- 인덱스 (조회 패턴에 맞는)
- 기존 v1.0 테이블과의 관계 (예: `filings.corp_code REFERENCES entities`)

각 collector가 INSERT할 행의 shape를 collector별로 명세.

### Q2. Dedup 전략
content-hash 기반 dedup (현재 documents.id = sha256(body))은 유지하되:
- 새 도메인 테이블에서 어떤 컬럼을 dedup key로? (예: `filings.rcept_no` UNIQUE? `news.url_hash` UNIQUE?)
- UPSERT ON CONFLICT 패턴 — `last_seen_at` 같은 컬럼 갱신만? 또는 본문 재기록?
- 한 종목에 대해 같은 source/id로 들어온 신규 데이터는 어떻게 (`source_urls` array 같은 v1.0 패턴 유지 vs 단순)?

### Q3. Legacy `documents`/`chunks` 테이블 처리
Phase 1 범위에서 결정 필요:
- (A) DROP — Phase 3 (MCP)에서 다시 만들거나 새 narrative-검색 인덱스 구성
- (B) Leave dormant — 데이터 없이 빈 상태로 유지, Phase 3에서 재활용 검토
- (C) Rename to `legacy_documents_v1` — historical reference로 보관

권장안 + 근거 + Phase 3에 미치는 영향.

### Q4. 마이그레이션 순서
- 0006 (또는 더 잘게 쪼개서) 에서 신규 테이블 CREATE
- 기존 테이블 처리 (Q3 결정에 따라)
- testcontainer에서 검증 가능한지

### Q5. Heartbeat 대체 (observability)
현재: collectors가 `record_source_run("dart", stats, heartbeat_path=...)` 호출 → no-op.
이걸 제거하고 무엇으로 대체?
- 구조화 로깅 (`logging.info(extra={"source":"dart", "stats":...})`) ?
- DB 테이블 (`collector_runs(source, run_at, stats JSONB, errors JSONB)`) ?
- 둘 다? (logging은 즉시 stderr, DB는 history)

Phase 9 (Ops hardening) ops 대시보드가 결국 어디서 데이터를 빨아갈지 고려.

### Q6. CLI 변경
- `--vault-root` 제거 → 자리에 무엇? (없애도 되는지, config 파일로 옮기는지)
- `collect` 출력 (stdout JSON report)은 어떻게 변경? (현재는 vault 파일 경로 리스트, 변경 후엔
  inserted/updated row count?)
- `collect all`의 stderr report 구조 변경 필요?

### Q7. 테스트 전략
- 기존 `tests/collectors/`가 vault path 기반 검증 — DB 기반으로 어떻게 변경?
- testcontainer 사용? 아니면 SQLAlchemy in-memory SQLite? (pgvector/JSONB 의존성 때문에 sqlite는 어려울 듯)
- collector unit test의 dispatcher 패턴 (`_dispatch()` monkeypatching) 유지?

### Q8. 5 collector 리팩토링 순서 (walking skeleton 선정)
가장 단순한 것부터 → 나머지 reference로 사용. 후보:
- `macro` — 시계열 INSERT, 가장 단순
- `krx` — 일일 OHLCV INSERT, 빈도 높지만 column 수 적음
- `dart` — 본문 + embedding 필요, 가장 복잡
- `news` — 본문 + dedup + entity matching
- `kind` — 이벤트 분류 + DART 결합 → 가장 의존성 많음

권장 순서 + 근거.

### Q9. `vault/raw/` 자동 재생성 차단
현재 .gitignore에 `vault/raw/`. collector가 실수로 다시 만들 수 없도록 어떤 가드?
- writer.py 자체를 import-error로 만들기 (제거)
- runtime assertion (`assert not vault_root.exists() or ...`)
- 단순히 코드 경로 제거만으로 충분?

## Out of Scope (Phase 1 범위 외)

- `decision_cards` 테이블 — Phase 2
- MCP 서버 재구축 — Phase 3
- Sonnet 분석 runner — Phase 4
- Action layer / KIS 통합 — Phase 6+
- 평가 / 백테스트 — Phase 8
- Daily routine 스케줄 — Phase 9

## Constraints (hard)

- Hard Veto 13개 (CLAUDE.md) — 모두 적용
- Phase 1은 **collector ↔ Postgres만** — 다른 레이어 코드 추가 금지
- 새 마이그레이션은 idempotent (testcontainer 재실행 가능)
- 모든 새 코드는 `python-mecab-ko`, `sentence-transformers` 같은 무거운 의존성에 import-time
  접근 금지 (lazy import)
- `tests/test_import_guard.py` 갱신 — `src/collectors` 여전히 anthropic/openai import 금지

## Pointers

- ROADMAP: `.planning/ROADMAP.md` Phase 1 섹션
- Design doc: `.planning/research/redesign-2026-05.md` §2 (data shape)
- Hard Vetoes: `CLAUDE.md` 상단
- Codebase 상태: shutdown commit `daf3edf` 기준 / 이번 commit `ab91088`
- v1.0 reference: `git show archive/llm-wiki-2026-04:src/collectors/dart/__init__.py` 등
