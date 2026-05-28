<!-- GSD:project-start source:.planning/research/redesign-2026-05.md -->
## Project

**stock — Claude-mediated Korean stock analysis system (Milestone v2.0)**

한국 주식시장(KOSPI/KOSDAQ) 데이터(공시·뉴스·가격·매크로)를 수집해 Postgres에 적재하고,
Claude Sonnet이 *근거 카드(decision_card)* 형태로 압축한 evidence를 사람에게 제시한다.
검증된 paper-trade 실적이 있는 종목에 한해 KIS API로 자동매매를 보조한다.

**v2.0 Core Value (변경됨):** AI는 **종목을 찍어주지 않는다.** AI는 매일 모은 공시·뉴스·가격을
근거 카드로 압축해 (출처·모순·만료조건 명시) 사람이 더 빨리, 더 discipline 있게 결정하도록
돕는다. 검증된 종목만 자동매매로 연결된다. — `Bloomberg ASKB / AlphaSense / Perplexity Finance`
공통 패턴.

**v1.0(폐기)와 차이**: Markdown vault가 source of truth였던 LLM-wiki 전략은 2026-04에 폐기되고
Postgres-direct로 재설계됨. v1.0 history는 git tag `pre-llm-wiki-shutdown` + 브랜치
`archive/llm-wiki-2026-04`에 보존. 설계 문서: `.planning/research/redesign-2026-05.md`
(authoritative architecture criteria).

---

## 🚫 Hard Vetoes (모든 코드 편집·작업 전에 검토)

**이 13개 항목은 협상 불가. 위반된 코드는 review에서 거부된다.**

### 분석 레이어
1. **AI한테 가격 예측 시키지 마라.** FinGPT 45-53% (≈동전 던지기). 우리 AI는 *evidence를 압축*하지
   *예측하지* 않는다. 출력은 항상 `decision_card` (근거 + 모순 + 만료조건) 형태.
2. **만료일 + assumptions[] 없는 thesis 작성·저장 금지.** Pydantic validator로 강제. 만료 없는 카드는
   thesis가 아니라 vibe.
3. **Contradictions[]는 1급 출력이다.** 모순을 숨기거나 silent하게 한쪽 채택 금지. 항상 명시.
4. **Black-box 점수 금지.** 모든 score / conviction은 cited evidence item들로 decompose 가능해야
   한다.
5. **Sentiment 단독 신호 금지.** 항상 DART/KRX/macro로 corroborate. Sentiment는 LOW weight 보조용.

### 데이터 레이어
6. **숫자를 embedding하지 마라.** OHLCV, 재무 line items, PER/PBR/ROE — 모두 typed 컬럼으로.
   Embedding은 *내러티브* (DART 본문, 뉴스, thesis 메모)에만.
7. **MCP에 `run_sql` 같은 임의 SQL escape hatch 금지.** 모든 도구는 타입드 Pydantic 함수.
   ~60%의 finance agent 환각이 silent SQL 실패에서 옴.
8. **DART 본문 pre-chunking 금지.** 전체 `body_md` 저장; chunk view는 sibling 테이블에. Claude
   200K context가 사업보고서 한 통 처리 가능.
9. **Markdown vault를 source of truth로 부활시키지 마라.** Postgres가 canonical. `notes/private/`
   (사용자 thesis 메모, gitignored) 만 disk 잔존 — 그 외 Markdown 모두 폐기됨.

### 액션 레이어
10. **Auto-trade에 circuit breaker 없으면 절대 ship 금지.** Gates A-D 모두 통과해야 KIS 호출.
    Gate C(human kill switch)는 default **disabled**, 종목별 명시적 opt-in 필요. Aidya 1년 내 청산
    선례.
11. **신규 전략 paper-shadow ≥30일 + Sharpe 신뢰구간이 0을 포함하지 않을 때만** live 가능.
    Composer/QuantConnect 검증된 패턴.
12. **백테스트는 CPCV+embargo로만.** Walk-forward 단독은 Sharpe 20-40% 과대평가. T+2 settlement +
    3일 buffer = 5일 embargo.

### 리포트 레이어
13. **`get_decision_card()` default는 payload만.** body_md는 `view="both"` 명시 시에만. Anthropic
    "filter before context" 가이드. 10-card 세션 토큰 5배 절약.

---

## Architecture Decision Criteria

전체 흐름 (다이어그램 기준):

```
1. 수집 → 2. Postgres INSERT (Markdown 중간층 없음)
        ↓
3. 정제 = 타입드 MCP 도구 (숫자는 SQL, 글은 hybrid_search)
        ↓
4. 분석 = Bull/Bear/Judge 3-role sub-agent debate → decision_card
        ↓
5. 결과 저장 = decision_cards 테이블 (payload JSONB + body_md TEXT, 단일 row)
        ↓
   ├─→ 6. Action layer = Gates A-D + paper-shadow ≥30일
   │       └─→ 7-1. KIS Open API (실거래)
   │
   └─→ 7-2. Daily/Weekly briefing (top-N 변화만, 최대 10개)
              └─→ assumptions 만료 / 모순 발견 시 카드 자동 invalidate
```

### 주요 판단 기준 (요약)

| 결정 | v2.0 답 | 근거 |
|---|---|---|
| 데이터 저장 | Postgres 메인 + pgvector/BM25는 *내러티브만* | 의사결정 질문 ~80%가 수치/관계형 → SQL이 정확 |
| MCP 도구 | 타입드 함수 (`get_filing`, `ohlcv_range`, `hybrid_search`...) | Anthropic Code Execution with MCP (Nov 2025) — 토큰 98.7% 감소 |
| 분석 출력 | `decision_card` (BUY/HOLD/SELL + conviction + claims + contradictions + expires_at) | Bloomberg ASKB / AlphaSense / Perplexity 공통 패턴 |
| 분석 방법 | 3-role Bull/Bear/Judge sub-agent | reasoning quality scaffold (Sharpe 머신 X) |
| 백테스트 | CPCV + 5일 embargo | De Prado; walk-forward 단독은 Sharpe 과대평가 |
| 자동매매 | Gates A-D + paper-shadow ≥30일 | Composer/QuantConnect; default disabled per-ticker |
| 리포트 | payload JSONB + body_md (single row, machine default) | Anthropic structured output + filter-before-context |

자세한 근거·표·인용은 `.planning/research/redesign-2026-05.md` 참조.

---

## Tech Stack (v2.0 carry-over)

v1.0 research에서 검증된 stack을 그대로 사용한다 — 폐기된 건 LLM-wiki *전략*이지 tooling이 아니다.

| Layer | Pick | Notes |
|---|---|---|
| Python | CPython 3.12 | uv 관리 |
| DB | Postgres 17 (Docker) | docker-compose 유지 |
| Vector | pgvector 0.8 (`halfvec`) | bge-m3 1024-d |
| BM25 | VectorChord-BM25 | mecab-ko 한국어 tokenizer 전처리 |
| Embedding | bge-m3 via sentence-transformers (local) | 다국어, 8K context |
| Migrations | Alembic | `src/db/migrations/` |
| ORM | SQLAlchemy 2.x | |
| **MCP server** | FastMCP 2.x | v2.0: `src/mcp_v2/` (신규, 구 stock_mcp는 archive) |
| **Analysis brain** | Claude Sonnet 4.x via Claude Code | Max subscription, 자체 LLM 호출 X |
| Schedule | systemd.timer / Claude Schedule | |
| Action API | KIS (한국투자증권) Open API | `.env`에 키, 20 req/s rate limit |

### Data libraries (collectors)

| 소스 | 라이브러리 | Phase 1 변경 |
|---|---|---|
| DART (공시) | `dart-fss` | Markdown 출력 → Postgres INSERT 로 변경 |
| KRX (가격) | `pykrx` + `FinanceDataReader` | 동일 |
| 뉴스 | `requests` + `trafilatura` | 동일 |
| ECOS (한은) | `PublicDataReader` | 동일 |
| FRED 등 글로벌 | `fredapi` + `yfinance` | 동일 |

---

## Directory Layout (v2.0, post-shutdown)

```
stock/
├── src/
│   ├── cli/              # stock collect dart|krx|news|macro|kind|all (collect만)
│   ├── collectors/       # 5개 collector — Phase 1에서 DB-direct로 재작성
│   ├── db/               # Postgres 스키마, 마이그레이션, ORM, seed
│   ├── shared/           # frontmatter(legacy), portfolio, content_hash, number_*, units
│   │                     # heartbeat.py = no-op stub (Phase 1에서 제거 예정)
│   └── orchestration/    # 빈 stub (재설계 시 사용)
│
│   ※ Phase 진행 중 신규: src/cards/, src/mcp_v2/, src/analysis/, src/briefing/,
│      src/action/, src/eval/
│
├── tests/                # collectors / db / shared / 일부 frontmatter 테스트만 잔존
├── notes/                # gitignored — 사용자 thesis/journal 전용
│   └── private/          # portfolio.md (보유·평단·thesis)
├── docs/                 # 프로젝트 문서 (kind-robots-snapshot 등)
├── fixtures/             # 테스트·시드 데이터
├── scripts/              # init-extensions.sql 등 운영 스크립트
├── .planning/            # GSD 워크플로우 산출물
│   ├── PROJECT.md
│   ├── ROADMAP.md        # ← v2.0 9-phase 로드맵
│   ├── STATE.md
│   ├── research/
│   │   └── redesign-2026-05.md   # ★ authoritative architecture criteria
│   └── phases/           # ← v1.0 phase 디렉토리들, historical reference 목적으로 잔존
├── docker-compose.yml    # Postgres 17 + pgvector + VectorChord-BM25
├── pyproject.toml        # collectors / db / dev dep group (mcp/ingest/graph는 삭제됨)
├── alembic.ini
└── CLAUDE.md             # 본 파일
```

**삭제된 v1.0 컴포넌트** (git history에서만 살아남음):
- `vault/`, `dashboards/`, `templates/`, `graph/`
- `src/stock_mcp/`, `src/ingest/`, `src/graph/`
- `.mcp.json` (v2.0에서 Phase 3 완료 시 재생성)
- `.obsidianignore`, `config/graphify.json`

---

## First-time Setup (v2.0)

```bash
# 1. Python deps
uv sync

# 2. .env (repo root)
DART_API_KEY=...           # https://opendart.fss.or.kr
ECOS_API_KEY=...           # https://ecos.bok.or.kr/api
FRED_API_KEY=...           # https://fred.stlouisfed.org/docs/api/api_key.html
KIS_APP_KEY=...            # https://apiportal.koreainvestment.com
KIS_APP_SECRET=...
KIS_ACCOUNT=...            # 8자리 + 2자리
DATABASE_URL=postgresql://stock:${POSTGRES_PASSWORD}@localhost:5432/stock
POSTGRES_PASSWORD=...

# 3. Postgres + 마이그레이션
docker compose up -d postgres
uv run alembic upgrade head

# 4. Entity seed (포트폴리오 기반)
uv run python -m src.db.seed_entities

# 5. (Phase 1 완료 후) collector smoke test
uv run stock collect dart --corp-code=00126380 --since=2026-01-01
```

---

## Working with This Codebase (Claude 지침)

**모든 code edit 전에 Hard Vetoes (위 13개) 검토.** 어떤 phase 작업이든 이 13개는 깨면 안 된다.

새 코드 작성 시:
1. `.planning/research/redesign-2026-05.md`의 해당 §를 먼저 확인 (architecture 결정 근거).
2. `.planning/ROADMAP.md`에서 해당 phase의 Success Criteria를 reference.
3. 의심스러우면 v1.0 archive 확인: `git show archive/llm-wiki-2026-04:<path>`.

특히 주의:
- **decision_card schema**는 `redesign-2026-05.md` §3에 lock됨. 임의 변경 금지 (Phase 2에서 정식 schema 결정 시까지).
- **MCP tool naming convention**: `get_*`(단일 entity), `search_*`(structured filter), `*_range`(시계열 범위), `hybrid_*`(narrative 검색만).
- **Numeric checksum**: Claude가 추출한 모든 숫자는 원문에 verbatim 등장해야 함. 실패 = drop the fact.

---

## Conventions

- Python: 3.12, snake_case, type hints (strict mypy), Pydantic v2 for all schemas
- 디렉토리: feature/domain별 분리 (file type별 X)
- 테스트: `tests/{collectors,db,shared,cards,mcp_v2,analysis,briefing,action,eval}/`
- 로그: 구조화된 `logging.info(extra={...})` — stderr; 사용자 출력은 stdout JSON
- Git: feature branch only, atomic commits, `git diff` 검토 후 commit
- 한국어 주석 OK. PR title은 영문 prefix (`feat:`, `fix:`, `chore:` 등)

---

## Architecture

See:
- `.planning/research/redesign-2026-05.md` — authoritative architecture rationale (§1-7)
- `.planning/ROADMAP.md` — 9-phase v2.0 roadmap

## Project Skills

No project skills found yet. Add to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`,
or `.github/skills/` with a `SKILL.md` index.

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work
- `/gsd-plan-phase` to plan a new phase before execute

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.

# userEmail
The user's email address is minsung3da@gmail.com.
