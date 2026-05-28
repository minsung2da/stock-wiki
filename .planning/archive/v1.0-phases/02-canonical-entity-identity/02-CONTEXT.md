# Phase 2: Canonical Entity Identity - Context

**Gathered:** 2026-04-17
**Status:** Ready for planning

<domain>
## Phase Boundary

DART `corp_code`(8자리)를 모든 엔티티의 캐노니컬 키로 고정한 스키마 레이어 구현. 6개 핵심 테이블(`documents`, `chunks`, `entities`, `edges`, `events`, `ingest_runs`)의 Alembic 마이그레이션, content-hash 기반 문서 dedup, 엔티티 이력/alias/supersedes 체인 추적, 시간 기반 엔티티 해결 헬퍼(`resolve_entity`)를 인제스트 시작 전에 고정한다. 한국 시장 특성(종목 개명, 분할, 티커 재활용, 기재정정)을 구조적으로 흡수할 수 있어야 Phase 3 이후 재인제스트를 피할 수 있다.

</domain>

<decisions>
## Implementation Decisions

### Entity Alias History Model
- **D-01:** 엔티티 이력은 별도 `entity_aliases` 테이블로 정규화. JSONB/단일테이블 거부.
- **D-02:** `entity_aliases` 컬럼: `id BIGSERIAL`, `corp_code CHAR(8) REFERENCES entities(corp_code)`, `kind TEXT CHECK(kind IN ('name','ticker','eng_name'))`, `value TEXT NOT NULL`, `valid_from DATE NOT NULL`, `valid_to DATE NULL` (NULL = current), `created_at TIMESTAMPTZ DEFAULT now()`.
- **D-03:** 인덱스: `(kind, value, valid_from, valid_to)` — ticker 재활용·개명 lookup 모두 처리.
- **D-04:** `entities` 테이블은 현재 상태만 저장: `corp_code (PK)`, `canonical_name`, `current_ticker`, `sector`, `market` (KOSPI/KOSDAQ), `listed_at`, `delisted_at NULL`.

### Supersedes Edge Storage
- **D-05:** 기재정정 체인은 `edges` 테이블에만 기록. `documents`에 self-reference 컬럼을 두지 않는다.
- **D-06:** `edges` 스키마: `id BIGSERIAL`, `src_type TEXT`, `src_id TEXT`, `dst_type TEXT`, `dst_id TEXT`, `edge_type TEXT NOT NULL`, `tag TEXT NULL` (EXTRACTED/INFERRED/AMBIGUOUS for Phase 7), `created_at TIMESTAMPTZ DEFAULT now()`. 복합 유니크: `(src_type, src_id, dst_type, dst_id, edge_type)`.
- **D-07:** 최신 문서 조회는 재귀 CTE로 supersedes 체인을 역추적. Phase 6 `get_filing(id)` 툴에서 명시적으로 "이 문서의 최종 정정본" 의미를 처리.
- **D-08:** Phase 2에서 등록할 엣지 타입: `supersedes`. 나머지(ticker→filing 등)는 Phase 7에서 추가.

### `resolve_entity` Temporal Semantics
- **D-09:** 단일 축(valid-time only). `as_of` 파라미터는 "실세계 그 시점의 엔티티 상태"를 의미.
- **D-10:** 쿼리 형태:
  ```sql
  SELECT corp_code FROM entity_aliases
  WHERE kind = :kind AND value = :value
    AND valid_from <= :as_of
    AND (valid_to IS NULL OR valid_to > :as_of)
  LIMIT 1
  ```
- **D-11:** `resolve_entity(ticker_or_corp_code: str, as_of: date | None = None) -> Entity | None`. `as_of=None`일 때 현재(`valid_to IS NULL`)만 조회.
- **D-12:** 8자리면 corp_code, 6자리면 ticker로 자동 분기. 둘 다 미스매치면 None 반환.

### Content-Hash Dedup
- **D-13:** `documents.id = sha256(normalized_body)`. `body` 정의: 수집된 원문에서 YAML frontmatter(`---` 블록) 제거 후 본문만.
- **D-14:** 정규화: `\r\n` → `\n`, trailing whitespace 제거, 파일 끝 개행 1개로 통일. 추가 정규화(예: HTML 공백 축약)는 하지 않음 — DART·뉴스 원문이 안정적.
- **D-15:** 충돌 시 동작: Upsert.
  ```sql
  INSERT INTO documents (id, body, source, vault_path, source_url, last_seen_at, source_urls)
  VALUES (...)
  ON CONFLICT (id) DO UPDATE SET
    last_seen_at = EXCLUDED.last_seen_at,
    source_urls = array_append(documents.source_urls, EXCLUDED.source_url)
    WHERE NOT (EXCLUDED.source_url = ANY(documents.source_urls))
  ```
- **D-16:** `documents` 컬럼: `id CHAR(64) PRIMARY KEY` (hex sha256), `body TEXT NOT NULL`, `source TEXT NOT NULL`, `vault_path TEXT NOT NULL`, `source_url TEXT NULL` (최초 URL), `source_urls TEXT[] NULL` (누적 URL), `first_seen_at TIMESTAMPTZ DEFAULT now()`, `last_seen_at TIMESTAMPTZ DEFAULT now()`.

### Claude's Discretion
- Alembic env.py 설정 (autogenerate vs explicit)
- 마이그레이션 파일 분할 전략 (one big migration vs 여러 개)
- `events`, `ingest_runs`, `chunks` 테이블의 상세 스키마 (Phase 3에서 구체화해도 됨, 여기서는 최소 뼈대만)
- `chunks` 테이블의 HNSW 인덱스 실제 생성 (Phase 3으로 위임해도 무방)
- pytest fixture에서 사용할 rename/split/ticker-recycling 케이스의 실제 기업 선정 (실제 DART 공시 케이스 권장)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 1 Artifacts (Locked Foundation)
- `docker-compose.yml` — Postgres 17 + vchord-suite 컨테이너 (이미 기동 가능)
- `scripts/init-extensions.sql` — pgvector, vchord_bm25, pg_trgm 로드
- `src/shared/frontmatter.py` — Pydantic 3-zone 스키마 (provenance / ingest_state / _derived)
- `pyproject.toml` — uv dependency groups; `db` 그룹에 Alembic 추가 필요
- `.planning/phases/01-load-bearing-foundation/01-SUMMARY.md` — 전 단계 결정사항

### Requirements
- `.planning/REQUIREMENTS.md` §Entity Model (ENT-01, ENT-02, ENT-03), §Storage (STORE-01, STORE-02)

### Research
- `.planning/research/ARCHITECTURE.md` §Component Responsibilities (db/ 소유권: DDL + query helpers, 네트워크/LLM 호출 없음)
- `.planning/research/PITFALLS.md` Pitfall 3 (ticker identity loss across corporate actions) — 이 phase의 주된 방어 대상

### Tech Stack
- `CLAUDE.md` §3.2 pgvector 0.8 (halfvec, binary_quantize) — Phase 2는 테이블 뼈대만, 실제 인덱스는 Phase 3
- Alembic 1.13+ (pyproject.toml db group 추가)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/db/__init__.py` — 빈 패키지, Alembic migrations 여기에 배치
- `src/shared/frontmatter.py` — frontmatter strip 로직 참고 (python-frontmatter 라이브러리 사용)
- `tests/conftest.py` — `tmp_vault`, `sample_yaml` fixture 존재. DB fixture 추가 필요 (pytest-postgresql 또는 testcontainers)

### Established Patterns
- pytest 기반 TDD (RED→GREEN, 10개 frontmatter 테스트가 참조 모범)
- Pydantic v2 모델 + type hints strict
- 3-zone frontmatter 경계 enforcement (Phase 3의 `STORE-06` 예고)

### Integration Points
- `collectors/` (Phase 3)가 `documents` 테이블에 INSERT — content-hash 계산 로직이 `src/shared/` 또는 `src/db/`에 공유 유틸로 필요
- `ingest/` (Phase 3)가 `chunks` 테이블에 embedding 저장 — Phase 2는 컬럼만 준비
- `src/shared/entity.py` 신규 모듈: `resolve_entity` 헬퍼 + 유틸

</code_context>

<specifics>
## Specific Ideas

- Fixture 케이스는 실제 시장 사례로 설계 권장:
  - **개명**: 예) "㈜삼성전자" → "삼성전자㈜" (공시 대상 상호변경 케이스)
  - **분할**: 2014-05-28 삼성전자 액면분할 (1:50), corp_code 유지, ticker 유지, 가격 시계열만 변경
  - **ticker 재활용**: 상장폐지 → 몇 년 후 다른 기업에 같은 6자리 부여 (KRX 사례 조사 필요)
  - **기재정정**: DART 동일 문서 rcept_no 다른 amendment 한 건
- `documents.id`는 64자 hex 문자열. UUID 대신 sha256 사용 이유: 콘텐츠 주소화 + re-fetch 시 자동 매핑
- `entity_aliases` 는 append-only 설계. 기존 row 업데이트 금지 (valid_to 설정만 허용). 감사 추적 자연스럽게 보존

</specifics>

<deferred>
## Deferred Ideas

- Bitemporal 모델(system-time + valid-time) — 2~5명 개인/팀 스케일엔 오버엔지니어링. 규제 감사 필요 시 v2+
- `events` 테이블의 이벤트 타입 확장 (수급 이상치, 가격 급등락) — Phase 4에서 collect_krx 붙일 때 구체화
- `chunks.embedding` HNSW 인덱스 실제 생성 — Phase 3 INGEST-10/STORE-03
- graphify 엣지 타입 전체 등록 (ticker→filing, filing→event 등) — Phase 7 GRAPH-01
- `documents.source_urls`를 별도 `document_sources` 테이블로 정규화 — 출처당 수집 시각/응답 헤더 추적 필요해질 때
- `entity_aliases` GIN 인덱스로 full-text alias 검색 — 한글 자모 분해 기반 fuzzy matching이 쿼리 패턴으로 굳어지면 추가

</deferred>

---

*Phase: 02-canonical-entity-identity*
*Context gathered: 2026-04-17*
