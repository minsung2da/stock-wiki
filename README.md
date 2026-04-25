# Stock Wiki

한국 주식시장(KOSPI/KOSDAQ) 및 거시경제 정보를 **LLM이 읽기 좋은 지식 저장소**로 축적해,
Claude Code에서 매수/매도 판단의 근거를 즉시 받아볼 수 있도록 만드는 **개인용 위키 + MCP 서버**입니다.

> **한 줄 요약:** Markdown 파일이 유일한 source of truth이고, Postgres+pgvector는 그 위에 얹은 검색 인덱스이며,
> Claude Code는 FastMCP 프로토콜로 이 인덱스에 질의한다.

---

## 1. 이게 뭔지 (세 문장)

1. **수집기**(`stock collect ...`)가 DART·KRX·ECOS/FRED·뉴스·KIND에서 데이터를 가져와 `vault/raw/**/*.md` 파일로 적는다.
2. **인제스트 워커**(`stock ingest run`)가 그 파일들을 읽어 Postgres에 chunk + 임베딩 + BM25 토큰으로 올린다.
3. **stock-mcp 서버**(`stock-mcp`)가 FastMCP stdio로 붙어, Claude Code가 `search`·`get_ticker_overview` 등의 툴을 호출하면 DB에서 하이브리드 검색을 해 결과를 준다.

단방향 파이프라인 — 파일 → DB → Claude. DB가 날아가도 `vault/`에서 다시 만든다.

---

## 2. 아키텍처 한눈에

```
  외부 API·웹                         로컬 파일 (vault/)                           Postgres 17 (vchord-suite)
  ┌──────────────┐                    ┌────────────────────────┐                   ┌──────────────────────┐
  │ DART OpenAPI │ ── collect_dart ─→ │ raw/dart/{corp}/...    │                   │ entities             │
  │ KRX (pykrx)  │ ── collect_krx  ─→ │ raw/krx/YYYY-MM-DD/... │                   │ entity_aliases       │
  │ ECOS/FRED    │ ── collect_macro─→ │ raw/macro/{src}/...    │ ── ingest run ──→ │ documents (chunks)   │
  │ 한경/이데일리 │ ── collect_news ─→ │ raw/news/YYYY-MM/...    │                   │ chunks               │
  │ DART+KIND    │ ── collect_kind ─→ │ raw/kind/YYYY-MM/...   │                   │   · embedding (bge-m3)│
  │              │                    │                        │                   │   · bm25_tokens       │
  │              │                    │ notes/portfolio.md     │                   │                      │
  │              │                    │                        │                   └──────────────────────┘
  │              │                    │ ingested/_status/      │                            ▲
  │              │                    │   heartbeat.md         │                            │ SQL (hybrid search)
  │              │                    └────────────────────────┘                            │
  │              │                                                                          │
  │              │                                                   ┌────────────────────────┐
  │              │                                                   │ stock-mcp (FastMCP)    │ ←── stdio
  │              │                                                   │ tools: search, ...     │
  │              │                                                   └────────────────────────┘
  │              │                                                            ▲
  │              │                                                            │ MCP protocol
  └──────────────┘                                                   ┌────────────────────┐
                                                                     │ Claude Code (you)  │
                                                                     └────────────────────┘
```

### 왜 두 단계(수집기 vs 인제스트)인가

수집기는 **토큰 비용이 0**이다 (HTTP만 쓴다). 인제스트는 임베딩 계산이 있어 무겁다. 분리해두면:
- 수집기는 자주(매일) 돌아도 비용이 없다.
- 인제스트는 필요할 때만(예: 하루 한번) 돌린다.
- 파일이 중간에 끼어 있어서 수집 실패해도 기존 DB는 건드리지 않는다.
- `_derived` LLM 추출(Phase 5)은 이 **사이에** 끼어든다 — Claude Code **Routine**(`.claude/routines/enrich/`)이 매일 `vault/raw/**/*.md`를 읽어 frontmatter에 요약·이벤트타입·숫자를 적어 PR로 올리고 auto-merge. 인제스트는 `_derived` 채워진 frontmatter만 보면 된다. 운영 가이드: §5.1.

---

## 3. 디렉토리 구조

```
stock/
├── src/
│   ├── cli/               # `stock` CLI 진입점 (argparse)
│   │   ├── __main__.py    # subparser 구성
│   │   └── commands.py    # 각 subcommand 핸들러
│   │
│   ├── collectors/        # 외부 소스 → vault/raw/*.md (토큰 비용 0)
│   │   ├── dart/          # Open DART API · dart-fss 래퍼
│   │   ├── krx/           # pykrx OHLCV + 투자자 수급 + 공매도 잔고
│   │   ├── macro/         # ECOS (PublicDataReader) + FRED (fredapi)
│   │   ├── news/          # RSS + trafilatura + alias matching
│   │   └── kind/          # DART pblntf_ty="I" 거래소공시 + KIND 스크레이핑
│   │
│   ├── db/                # SQLAlchemy engine, Alembic migrations, seed 스크립트
│   │   ├── engine.py      # get_engine() — .env의 DATABASE_URL 사용
│   │   ├── entity.py      # resolve_entity, upsert_entity, resolve_entity_by_alias
│   │   ├── seed_entities.py       # portfolio.md → entities 테이블
│   │   ├── seed_name_aliases.py   # entities → entity_aliases (뉴스 매칭용)
│   │   └── migrations/versions/*.py   # Alembic schema
│   │
│   ├── ingest/            # vault/raw/*.md → Postgres (임베딩 + BM25)
│   │   ├── worker.py      # 메인 파이프라인
│   │   ├── parsers/       # DART TOC 파싱 등
│   │   ├── chunking.py    # 문서 → chunk 분할
│   │   ├── embedder.py    # sentence-transformers(bge-m3, 1024-d) 로컬 호출
│   │   ├── tokenizer.py   # mecab-ko → BM25 토큰 배열
│   │   ├── heartbeat.py   # source별 run 타임스탬프 기록
│   │   └── injection_defense.py  # LLM 프롬프트 인젝션 차단 (semi_trusted 문서용)
│   │
│   ├── stock_mcp/         # FastMCP stdio 서버 (Claude Code 대상)
│   │   ├── __main__.py    # `stock-mcp` 진입점
│   │   ├── server.py      # DB health check + tool registration
│   │   ├── search_core.py # pgvector + VectorChord-BM25 RRF 융합 검색
│   │   └── tools/         # @mcp.tool 데코레이터 달린 함수들
│   │
│   └── shared/
│       ├── portfolio.py   # vault/notes/portfolio.md 로더 (Pydantic)
│       ├── frontmatter.py # ProvenanceBlock (trust_level, tickers, observations, ...)
│       └── content_hash.py # sha256 기반 멱등 키
│
├── vault/                 # source of truth — 모두 git에 커밋
│   ├── notes/
│   │   └── portfolio.md   # holdings + watchlist YAML frontmatter
│   ├── raw/               # 수집기 출력 (Markdown + frontmatter)
│   └── ingested/_status/
│       └── heartbeat.md   # 마지막 수집/인제스트 타임스탬프
│
├── .planning/             # GSD(Get-Shit-Done) 워크플로우 메타
│   ├── ROADMAP.md         # 9개 페이즈 계획
│   ├── PROJECT.md         # 프로젝트 전체 비전
│   ├── REQUIREMENTS.md    # COLL-01, INGEST-01, MCP-01 같은 요구사항 ID
│   ├── STATE.md           # 현재 진행 상태
│   ├── config.json        # 모델 선택, 기능 플래그
│   ├── macro_series.yaml  # 수집할 ECOS/FRED 시리즈 카탈로그
│   └── phases/NN-name/    # 각 페이즈의 CONTEXT / PLAN / SUMMARY / VERIFICATION
│
├── tests/                 # pytest (80%+ 커버리지 목표)
│   ├── collectors/        # 각 수집기 단위/통합 테스트
│   ├── db/                # entity + seed 테스트
│   ├── fixtures/          # 오프라인 테스트용 API 응답 캡처
│   └── test_cli_*.py
│
├── scripts/
│   └── init-extensions.sql  # Postgres 확장: vector, vchord_bm25, pg_trgm
│
├── docker-compose.yml     # Postgres 17 + pgvector + vchord_bm25 (tensorchord/vchord-suite)
├── pyproject.toml         # uv 의존성 (base + collectors + ingest + mcp + dev 그룹)
├── CLAUDE.md              # Claude Code용 프로젝트 규칙 (기술 스택 결정, 코딩 규약)
└── README.md              # 이 파일
```

**중요한 약속:**
- `vault/raw/` 는 수집기가 쓴다. 사람이 직접 편집하지 않는다.
- `vault/notes/` 는 사람이 쓴다. (Phase 6 이후 MCP `add_note` 도 쓴다.)
- `ingested/` 는 워커가 쓴다.
- DB는 언제든 `stock ingest rebuild` 로 `vault/` 에서 다시 만들 수 있다. 잠금-인 없음.

---

## 4. CLI 구조 (`stock` + `stock-mcp`)

### 4.1 `stock collect ...` — 수집

| 명령 | 하는 일 | 출력 |
|------|---------|------|
| `stock collect dart --corp-code 00126380 --since 2026-01-01` | Open DART에서 특정 기업 공시 N건 수집 | `vault/raw/dart/{corp_code}/{rcept_no}.md` |
| `stock collect krx [--since YYYY-MM-DD]` | portfolio의 모든 티커 → 당일 OHLCV + 투자자 수급 + 공매도 잔고 (3개 데이터 한 파일에 병합) | `vault/raw/krx/YYYY-MM-DD/{ticker}.md` |
| `stock collect news` | 한경 경제·증권 RSS + 이데일리 RSS → trafilatura로 본문 추출 → 첫 2문단만 저장 (저작권 정책) | `vault/raw/news/YYYY-MM/{outlet}_{url_hash8}.md` |
| `stock collect macro` | ECOS(기준금리, USD/KRW) + FRED(US 10Y, WTI) 최근 1년 observation append | `vault/raw/macro/ecos/{series}.md`, `vault/raw/macro/fred/{series}.md` |
| `stock collect kind` | DART 거래소공시(`pblntf_ty="I"`)에서 거래정지·관리종목·불성실공시 이벤트 분류 | `vault/raw/kind/YYYY-MM/{event_type}_{ticker}_{date}.md` |
| `stock collect all [--sources=a,b,...]` | 위 4개(또는 subset)를 in-process try/except로 격리 실행. 하나가 실패해도 나머지는 완주. stderr에 JSON 리포트, exit 0/1 | (각 수집기 출력 + `ingested/_status/heartbeat.md` 갱신) |

**핵심 속성:**
- 전부 **멱등(idempotent)** — 같은 데이터를 두 번 받아도 파일은 한 번만 쓴다 (`content_hash` 비교).
- **스코프 필터** — `vault/notes/portfolio.md`의 watchlist + holdings 티커만 처리.
- **trust_level** — 출처에 따라 frontmatter에 `trusted`(공시·거래소) 또는 `semi_trusted`(언론) 표시. `_derived` 추출 Routine(Phase 5)이 본문 wrapping(prompt-injection 방어)을 적용할지 결정하는 기준.
- **heartbeat** — 소스별 `last_run`/`last_failure` 타임스탬프를 `ingested/_status/heartbeat.md`에 YAML로 기록. Phase 6 health 툴이 읽음.

### 4.2 `stock ingest ...` — 인제스트

| 명령 | 하는 일 |
|------|---------|
| `stock ingest run` | `vault/raw/**/*.md` 스캔 → frontmatter 읽고 body 정규화 → sha256 dedup → parser → chunker → bge-m3 임베딩 → mecab-ko BM25 토큰 → Postgres에 upsert. 소스별 heartbeat(`source='ingest'`) 기록 |
| `stock ingest rebuild [--force-reembed] [--yes]` | documents + chunks 테이블 전체 wipe 후 재구축 |

### 4.3 `stock-mcp` — FastMCP 서버

```bash
uv run stock-mcp    # stdio 모드로 실행. Claude Code가 이걸 자기 MCP server list에 등록해서 씀.
```

Claude Code에 MCP server로 등록하면 `search`, `get_ticker_overview` 등의 툴이 Claude 쪽 toolbox에 나타난다.
시작 시 Postgres 연결 헬스체크 — 실패하면 stderr JSON 에러 + exit 1.

### 4.4 Python 모듈 진입점 (시드 스크립트)

```bash
uv run python -m src.db.seed_entities         # portfolio.md → DART 조회 → entities 테이블 upsert
uv run python -m src.db.seed_name_aliases     # entities → entity_aliases (뉴스 매칭용)
```

둘 다 **멱등** — 여러 번 실행해도 안전. 새 티커를 portfolio.md에 추가하면 재실행.

---

## 5. First-time Setup (처음 clone한 뒤)

### 5.1 로컬 파이프라인 부트스트랩

```bash
# 1. Python 의존성
uv sync

# 2. Postgres 띄우기 (docker)
cp .env.example .env   # POSTGRES_PASSWORD, DART_API_KEY, ECOS_API_KEY, FRED_API_KEY 기입
docker compose up -d postgres

# 3. 스키마 마이그레이션
uv run alembic upgrade head

# 4. entities 시드 (portfolio.md 기반)
uv run python -m src.db.seed_entities

# 5. 이름 alias 시드 (뉴스 매칭용)
uv run python -m src.db.seed_name_aliases

# 6. 수집 확인
uv run stock collect all
```

단계 6의 JSON 리포트가 4개 source 모두 `"status":"ok"` 이면 로컬 세팅 완료.

### 5.2 Routines daily run 트리거 + auto-merge PR (Phase 5 산출물)

`_derived` 추출(요약·event_type·숫자·sentiment)은 로컬에서 돌리지 않고 **Claude Code Routine**이 하루 1회(22:00 UTC) 클라우드에서 돌려 PR로 vault에 커밋합니다. 본 저장소의 `.claude/routines/enrich/` 가 그 Routine의 모든 자산입니다.

| 자산 | 역할 |
|------|------|
| `.claude/routines/enrich/SKILL.md` | Routine이 매번 읽는 16-step 메인 프롬프트 (read → injection check → regex 후보 → LLM ×2 → `facts_equal` → Pydantic → numeric sanity → zone-integrity → write → PR) |
| `.claude/routines/enrich/prompts/derived_{dart_b,news,kind,macro}.md` | 소스별 sub-prompt |
| `.claude/routines/enrich/helpers/{facts_equal,walk,zone_integrity}.py` | 자기일관성·idempotency·zone-violation guard 헬퍼 |
| `.claude/routines/enrich/README.md` | **운영자 런북 — 아래의 권위있는 출처** |

**최초 1회 트리거 절차** (요약 — 정확한 단계는 `.claude/routines/enrich/README.md` 따라가기):

1. GitHub fine-grained PAT 생성 — `repo: stock` 단일 저장소, **Contents: RW + Pull requests: RW**, 만료 ≤ 90일.
2. `claude.ai/code/routines` → **New routine** → 이름 `stock-enrich-daily`.
   - Repository: 본 repo만 선택
   - Env: `GITHUB_TOKEN`(PAT), `DART_API_KEY`
   - Setup script: `uv sync --extra ingest --extra collectors --extra dev`
   - Trigger: Scheduled / daily / **22:00 UTC** (= 07:00 KST 다음날, D-02 cutoff 이후)
   - Allowed tools: Bash, Read, Edit, Write
   - Network allowlist: `api.dart.fss.or.kr`, `github.com`, `api.github.com`
3. 저장 후 **Run now** 1회 — 로그에서 PR 생성 확인.
4. GitHub repo 1회 설정:
   - Settings → General → Pull Requests → **Allow auto-merge** 체크
   - Settings → Branches → `main` rule: PR 필수 + status check 필수 + linear history 필수
   - Settings → Labels → `auto-merge` 라벨 신설
5. 첫 PR이 `auto-merge` 라벨로 올라오고, CI(import_guard + pytest) 통과 후 자동 merge되는지 확인.

상세(보안 caveat, 실패 대응표, PAT/DART 키 회전 일정)는 `.claude/routines/enrich/README.md`.

**확인 신호:**
- `vault/raw/**/*.md` 의 `_derived:` 블록이 비어있던 문서에 `tickers/event_type/catalysts/numeric_facts/summary/sentiment` 가 채워진다.
- `ingested/_status/heartbeat.md` 의 `enrich.last_success` 가 갱신된다.
- Routine 실패가 `consecutive_failures ≥ 2` 가 되면 `backlog.md` 가 갱신되어 사람 리뷰로 빠진다.

---

## 6. 데이터 흐름 구체 예시

### 삼성전자 분기보고서를 수집해서 Claude가 참조하기까지

```
  t=0  사람이 vault/notes/portfolio.md 에 005930 추가
  t=1  uv run python -m src.db.seed_entities
       → DART OpenAPI에서 corp_code 00126380 조회
       → entities 테이블에 upsert, entity_aliases.ticker 에 '005930' 추가

  t=2  uv run stock collect dart --corp-code=00126380 --since=2026-01-01
       → dart-fss로 최근 공시 목록 → 본문 → vault/raw/dart/00126380/20260214000123.md
         (frontmatter: provenance.trust_level=trusted, source=dart, content_hash=sha256(...))

  t=3  uv run stock ingest run
       → src/ingest/worker.py 가 그 파일 읽음
       → parsers/dart.py 로 TOC 분리
       → chunking.py 로 1024-token 단위 split
       → embedder.py 로 bge-m3 임베딩 (로컬, GPU 없어도 OK)
       → tokenizer.py 로 mecab-ko BM25 토큰 추출
       → documents / chunks 테이블 INSERT
       → ingested/_status/heartbeat.md 갱신

  t=4  사용자가 Claude Code에서:
         "삼성전자 최근 분기 실적 중 반도체 부문만 알려줘"
       → Claude가 stock-mcp.search(query="삼성전자 반도체 부문", k=10) 호출
       → search_core.py 가 pgvector + VectorChord-BM25 hybrid(RRF) 검색
       → chunk 10개 반환 (각 chunk는 vault 경로 인용)
       → Claude가 답변 생성, "vault/raw/dart/00126380/20260214000123.md 참조" 표기
```

단방향, 누수 없음. 사람이 원하면 `vault/raw/dart/00126380/20260214000123.md` 를 직접 Obsidian으로 열어 읽을 수도 있다.

---

## 7. 핵심 설계 결정

### 7.1 Markdown + frontmatter가 source of truth

DB가 아니라 `vault/` 가 원본이다. 따라서:
- `rm -rf pgdata && stock ingest rebuild` 로 DB를 재생성할 수 있음.
- 사용자가 Obsidian에서 파일을 봐도 의미를 읽을 수 있음 (`|`구분자 markdown 테이블, Korean prose).
- git으로 히스토리 전부 추적.

### 7.2 수집기에서 LLM 금지

`src/collectors/` 와 `src/ingest/` 는 `anthropic`/`openai` import 금지 (CI guard: `tests/test_import_guard.py`).
- 이유: 수집 자체는 LLM이 필요없고, API 키 분실·토큰 폭주 리스크를 원천 차단.
- `_derived` 추출(Phase 5)은 **별도 프로세스**인 Claude Schedule agent가 담당. Claude Max 구독으로 토큰 비용 0.

### 7.3 `corp_code`가 primary key, `ticker`는 alias

- KRX 티커는 **재활용**된다 (상장폐지 후 몇 년 뒤 다른 회사에 같은 6자리가 배정됨).
- DART `corp_code`(8자리)는 영구 불변.
- `entities.corp_code` 가 PK. `entity_aliases` 에 `kind='ticker'`, `value='005930'`, `valid_from`, `valid_to` 로 역사 기록.
- 따라서 옛날 공시에서 "005930"이 지금 삼성전자가 아닌 시점도 안전하게 표현 가능.

### 7.4 하이브리드 검색 (pgvector + VectorChord-BM25)

- 의미 검색(임베딩)과 키워드 검색(BM25)은 장단점이 다름.
- VectorChord-BM25 extension이 Postgres 17에서 네이티브 BM25를 제공 (Elasticsearch 3x 빠름).
- RRF(Reciprocal Rank Fusion)로 두 결과를 합침.
- 한국어 BM25는 Python 쪽에서 mecab-ko로 미리 토큰화해서 배열로 저장 (DB 확장에 한글 analyzer 심는 복잡도 회피).

### 7.5 수집기는 독립 프로세스 격리

`stock collect all` 은 4개 수집기를 각각 try/except로 감싼다. 한 API가 죽어도 나머지는 완주. 실패는 heartbeat에 기록. exit code 1은 "뭔가 실패했음"을 알리는 신호일 뿐, 파이프라인은 계속 돌아간다.

---

## 8. 페이즈별 진행 상황 (GSD 워크플로우)

이 프로젝트는 `.planning/` 기반 GSD(Get-Shit-Done) 워크플로우로 페이즈 단위로 구축되고 있습니다.

| # | 페이즈 | 상태 |
|---|--------|------|
| 1 | Load-Bearing Foundation | ✅ 완료 — repo · DB · vault · schema · 비용 가드 |
| 2 | Canonical Entity Identity | ✅ 완료 — corp_code PK · alias 히스토리 |
| 3 | One-Company Walking Skeleton | ✅ 완료 — 삼성전자로 end-to-end 증명 |
| 4 | Multi-Source Collector Coverage | ✅ 완료 — KRX · 뉴스 · 거시 · KIND 수집기 + `stock collect all` |
| 5 | Claude-Schedule Enrichment + Korean Number Safety | ✅ 코드 완료 — `.claude/routines/enrich/` Routine 트리(SKILL+4 prompts+3 helpers). **운영자 1회 deploy 필요** (§5.2) |
| 6 | **Full MCP Tool Surface** | 📋 다음 |
| 7 | Graph Layer & graphify Integration | 대기 |
| 8 | Vault Dashboards & Research Memo Templates | 대기 |
| 9 | Judgment Prompt Conventions & Ops Hardening | 대기 |

각 페이즈 상세는 `.planning/ROADMAP.md`, 페이즈 내 세부 계획은 `.planning/phases/NN-*/`.

---

## 9. 자주 쓰는 명령 치트시트

```bash
# 개발 중
uv run pytest tests/ -x -q                          # 전체 테스트
uv run pytest tests/collectors/krx/ -v              # 특정 수집기만
uv run ruff check src/ tests/                       # lint
uv run alembic revision --autogenerate -m "..."     # 새 마이그레이션

# 운영 중
uv run stock collect all                            # 매일 수집
uv run stock ingest run                             # 수집 후 인덱싱
uv run stock-mcp                                    # Claude Code MCP server 기동

# DB 살피기
docker exec -it stock-postgres psql -U stockwiki -d stockwiki
```

---

## 10. 현재 한계 · 알려진 이슈

- **Phase 5 Routine 미배포 시**: `_derived.summary`·`_derived.event_type` 같은 LLM 추출 frontmatter가 비어 있어, Claude는 뉴스에서 첫 2문단 원문만 얻음. §5.2 Routine을 트리거하면 자동으로 채워진다.
- **graphify 미적용**: 티커 ↔ 필링 ↔ 이벤트 엣지 시각화는 Phase 7 예정.
- **투자경고/투자위험 event_type**: KIND에서 픽스처는 확보했으나 파서 구현 미완. 백로그 V2-KIND-01.
- **entities seed 범위**: portfolio.md 기반 — watchlist 확장 시 `seed_entities` 재실행 필요 (CLAUDE.md §First-time Setup 4단계 참조).

---

## 11. 기술 스택 요약

- **Python 3.12** (3.13 미지원 — ML 의존성 대응 대기)
- **uv**(패키지·venv), **hatchling**(빌드)
- **Postgres 17** + `pgvector 0.8` + `vchord_bm25` (tensorchord/vchord-suite 이미지)
- 수집: `dart-fss`, `pykrx`, `PublicDataReader`, `fredapi`, `trafilatura`, `feedparser`, `requests`+`beautifulsoup4`
- 인제스트: `sentence-transformers`(bge-m3), `python-mecab-ko`, `SQLAlchemy`, `psycopg[binary]`, `pgvector`
- MCP: `FastMCP 2.x`(Python)
- 테스트: `pytest`, `pytest-httpx`, `responses`

더 자세한 선정 근거는 `CLAUDE.md` §Technology Stack 참조.
