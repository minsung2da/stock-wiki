# Phase 1: Load-Bearing Foundation - Context

**Gathered:** 2026-04-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Postgres 17 컨테이너, vault 폴더 구조, Pydantic frontmatter 스키마, 시크릿 관리, 클라우드-LLM CI 가드를 데이터가 한 건도 쓰이기 전에 고정한다. 인제스트 후 되돌릴 수 없는 결정들(DB 선택, 엔티티 ID 준비, frontmatter zone 구조, vault 경로)을 이 phase에서 확정한다.

</domain>

<decisions>
## Implementation Decisions

### Repo Layout / Code Placement
- **D-01:** 코드는 `src/` 하위에 배치 (`src/collectors/`, `src/ingest/`, `src/stock_mcp/`, `src/db/`, `src/orchestration/`). Vault 데이터 디렉토리(`raw/`, `notes/`, `ingested/`, `dashboards/`, `graph/`)는 레포 루트에 유지.
- **D-02:** Obsidian vault 루트 = 레포 루트. `.obsidian/`, `환영합니다!.md` 보존. `src/`를 Obsidian 검색에서 제외 설정.

### Private Portfolio Overlay
- **D-03:** 프라이빗 포트폴리오 데이터는 `notes/private/` 경로에 저장하고 `.gitignore`에 추가 (로컬-only). git에 커밋되지 않음.
- **D-04:** 초기 세팅을 위해 `templates/portfolio.md` 템플릿 파일을 제공. git clone 후 사용자가 `notes/private/`에 복사해서 사용.
- **D-05:** `stock-mcp`의 `get_portfolio_state()`는 `notes/private/portfolio.md`를 읽음.

### WSL Path Migration
- **D-06:** Phase 1 시작 시 vault를 `/mnt/c/Users/minsu/workspace/stock/` → `~/stock/`으로 하드 마이그레이션. WSL 네이티브 파일시스템 사용으로 I/O 성능 확보.
- **D-07:** Obsidian은 Windows에서 `\\wsl$\Ubuntu\home\yamin\stock` (또는 해당 distro 경로)으로 vault를 재연결.
- **D-08:** 마이그레이션 스크립트(`scripts/migrate-to-wsl.sh`)를 제공하여 재현 가능하게 함.

### Frontmatter 3-Zone Structure
- **D-09:** Frontmatter 3개 구역을 YAML 중첩 딕셔너리로 표현:
  - `provenance:` — 수집 시 기록 (source, date, url, content_hash, corp_code, ticker)
  - `ingest_state:` — 인제스트 상태 (processed, processed_at, embedding_model)
  - `_derived:` — LLM 추출 속성 (tickers, event_type, catalysts, sentiment, numeric_facts, summary)
- **D-10:** Pydantic 모델이 중첩 구조에 1:1 매핑: `FrontMatter(provenance: ProvenanceBlock, ingest_state: IngestStateBlock, derived: DerivedBlock)`.
- **D-11:** Dataview 쿼리는 `WHERE provenance.source = "dart"` 형식 사용.

### Claude's Discretion
- pyproject.toml 구조 (단일 + dependency groups vs uv 워크스페이스) — Claude가 anthropic 격리 보장과 단순성을 고려하여 결정
- Docker 이미지 선택 (tensorchord/vchord vs custom Dockerfile) — 연구 단계에서 결정
- Pre-commit hook 프레임워크 선택 (gitleaks vs detect-secrets 등)
- CI 플랫폼 선택 (GitHub Actions vs pre-commit only)
- 테스트 프레임워크 및 fixture 구성

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Technology Stack
- `.planning/research/STACK.md` — 전체 기술 스택 결정 (Postgres 17, pgvector 0.8, VectorChord-BM25, bge-m3, FastMCP 2.x, uv, Python 3.12)
- `CLAUDE.md` §Technology Stack — STACK.md 요약 및 버전 호환성 노트

### Architecture
- `.planning/research/ARCHITECTURE.md` — 컴포넌트 다이어그램, 데이터 흐름, 경계 규칙 (collectors→vault→ingest→DB→MCP)

### Pitfalls
- `.planning/research/PITFALLS.md` — Pitfall 1 (Claude API 비용 폭주), Pitfall 2 (PGLite 동시성), Pitfall 4 (프롬프트 인젝션)이 Phase 1에 직접 해당

### Requirements
- `.planning/REQUIREMENTS.md` — FOUND-01~06, COLL-07, OPS-06이 Phase 1 범위

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `.venv/` — 기존 Python venv 존재 (uv로 재구성 예정)
- `.graphify_detect.json`, `.graphify_python` — graphify 연동 준비 표식
- `.obsidian/` — Obsidian 설정 (보존 대상)

### Established Patterns
- 아직 코드 없음. Phase 1이 모든 패턴의 시작점.

### Integration Points
- Obsidian이 레포 루트를 vault로 열고 있음 — 폴더 구조 변경 시 vault 경로 일관성 유지 필요
- Docker compose로 Postgres 기동 → `src/db/`에서 Alembic 마이그레이션 관리 (Phase 2)
- `src/` 하위 각 모듈이 독립 venv에서 실행 가능해야 함

</code_context>

<specifics>
## Specific Ideas

- WSL 마이그레이션 시 `\\wsl$\` 경로로 Obsidian 재연결 — distro명 자동 감지 포함
- `notes/private/`는 팀원마다 내용이 다르므로 충돌 없음 (gitignored)
- Frontmatter zone 접근을 Pydantic 모델로 강제하여 zone 간 cross-contamination 방지

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-load-bearing-foundation*
*Context gathered: 2026-04-17*
