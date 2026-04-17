# Stock Wiki — Claude-Powered Korean Market Knowledge Base

## What This Is

한국 주식시장(KOSPI/KOSDAQ) 및 거시경제 정보를 수집·구조화·그래프화하여, Claude Code에서 stock-mcp를 통해 질의했을 때 매수/매도 판단에 필요한 근거를 즉시 제시할 수 있도록 만드는 개인·소규모 팀(2~5명)용 지식 베이스다. Karpathy의 llm-wiki 철학(인간이 아닌 LLM이 쓰고 읽는 지식 저장소) 위에서, 기존 Obsidian vault를 그대로 확장해 Markdown + frontmatter를 단일 원본(source of truth)으로 사용하고, Postgres + pgvector를 하이브리드 검색(시맨틱 + BM25) 인덱스로 얹은 gbrain-style 아키텍처를 따른다. graphify로 문서·노트 전반을 인터랙티브 그래프로 엮어 "무엇이 쓰여 있나"뿐 아니라 "왜 그 판단에 이르렀나"까지 추적 가능한 형태로 남긴다.

## Core Value

**Claude Code에서 보유·관심 종목을 질의했을 때, 최신 공시·뉴스·가격·본인 리서치 메모를 종합한 근거 있는 매수/매도 판단을 즉시 받을 수 있다.** 나머지는 모두 이 한 가지를 가능하게 하기 위한 수단이다.

## Requirements

### Validated

(아직 없음 — 첫 밀스톤 출하 후 검증)

### Active

- [ ] 한국 증시 raw 데이터를 일배치 스크립트(토큰 소비 없음)로 수집하여 vault에 Markdown+frontmatter로 적재
- [ ] DART 공시, 네이버/다음 증권, 경제·금융 뉴스 매체, 증권사 리포트, 거시지표(한은·FED·환율·원자재)를 소스별로 수집 가능
- [ ] 수집된 raw 문서를 인제스트 파이프라인이 읽고 속성(ticker, 이벤트 유형, 재무 수치, 감성, 카탈리스트 등)을 frontmatter로 자동 추출
- [ ] Postgres + pgvector에 문서 임베딩·구조화 메타데이터·문서 간 엣지를 저장하고 하이브리드 검색(dense + BM25)으로 조회 가능
- [ ] graphify로 vault 전체를 인터랙티브 그래프로 변환(종목↔섹터↔공시↔뉴스↔본인 메모의 연결 추적)
- [ ] stock-mcp 서버(MCP 프로토콜)로 Claude Code에서 vault·DB·그래프를 도구로 노출
- [ ] 포트폴리오 대시보드 노트(보유 종목 상태·최근 이벤트·판단 근거 요약)가 vault 안에 자동 생성·갱신
- [ ] Claude Code 세션 안에서 "종목 X 리서치", "포트폴리오 모니터링", "매도 후보 제안" 질의에 근거 포함 답변 제공
- [ ] LLM 비용 최소화: 수집은 순수 스크립트, 인제스트는 로컬 임베딩/로컬 LLM 우선, 최종 판단만 Claude Code 세션 내 LLM 사용

### Out of Scope

- 미국/글로벌 시장 전면 지원 — 한국 시장 집중(거시지표만 글로벌 포함) · v2 이후 검토
- 암호화폐 데이터 — 범위 희석 방지 · 별도 프로젝트로 분리
- 실시간/틱 단위 가격 데이터 — 일배치로 충분하고 비용·복잡도 과다
- 자동 주문 실행(autotrading) — 판단 보조가 목표이지 집행은 안 함 · 법·리스크 이슈
- 공개 웹 서비스 배포 — 2~5명 내부 사용 · 인증·확장성 설계 회피
- 실시간 크롤링을 매 질의마다 수행 — 인제스트된 vault만 참조하여 세션 토큰 절약

## Context

**기존 자산:**
- 현재 디렉토리(`/mnt/c/Users/minsu/workspace/stock`)에 이미 Obsidian vault가 설정되어 있음(`.obsidian/`, `환영합니다!.md`)
- `.venv/`가 존재 — Python 환경 선호 시사
- `.graphify_detect.json`, `.graphify_python` — graphify 연동 준비 표식

**철학적 기반:**
- Karpathy llm-wiki: 위키는 사람이 아니라 LLM이 읽고 쓴다 — 포맷을 그에 맞춤
- llm-wiki Obsidian 플러그인(domleca): vault를 프라이빗 쿼리 가능 지식 베이스로 변환
- gbrain(Garry Tan, 2026-04): Git-tracked Markdown + Postgres+pgvector + Skills 3-layer — 본 프로젝트 참조 아키텍처
- graphify: Tree-sitter 정적 분석 + LLM 의미 추출로 코드·문서·논문·다이어그램을 인터랙티브 그래프화

**데이터 소스(한국 시장):**
- DART(전자공시) — `dart-fss`, `OpenDartReader` 파이썬 라이브러리
- 네이버 증권·다음 증권 — 크롤링(시세·종목개요·토론·뉴스)
- 경제·금융 매체 — 한경, 이데일리, 서울경제, 조선비즈 (RSS/스크래핑)
- 증권사 리포트 — 컨센서스 스냅샷, 거시지표는 한은·ECOS API·FRED
- 가격/재무: `pykrx`, `FinanceDataReader`, `yfinance`(글로벌 거시용)

**사용자·워크플로우:**
- 주 사용자: 본인 + 소규모 지인(2~5명)
- 주된 워크플로우: 포트폴리오 대시보드 중심의 주기적 리뷰 → 이벤트 드리븐 판단
- 최종 판단은 Claude가 vault 근거를 바탕으로 내림

## Constraints

- **Tech stack**: Python(수집·인제스트 스크립트, stock-mcp 서버) + Postgres/PGLite+pgvector(검색 인덱스) + Obsidian(사용자 인터페이스) + MCP 프로토콜 — gbrain·graphify 생태계와 호환
- **Storage**: Markdown + YAML frontmatter가 유일한 source of truth. DB는 인덱스·캐시이며 언제든 vault에서 재생성 가능해야 함 — 잠금-인 회피
- **Cost**: 수집에 LLM 토큰 0. `_derived` 추출은 Claude Max 구독 기반 Claude Schedule 에이전트가 수행(별도 API 과금 없음). 로컬 Ollama/Qwen/EXAONE는 사용하지 않음. 임베딩은 sentence-transformers로 로컬 직접 계산.
- **Scale**: 관심 종목 수십~수백 개, 연간 문서 수만 건 수준 — 엔터프라이즈 스케일 불필요
- **Privacy**: 로컬/개인 vault 기반. 공유는 git 저장소 협업 수준 — 공개 배포 고려 없음
- **Legal**: 크롤링 대상 robots.txt·이용약관 존중. 라이선스 불명확한 리포트 원문은 전문 저장 대신 요약·링크 권장
- **Language**: 수집 문서 다수 한국어 — 임베딩 모델은 다국어 지원 필수(bge-m3, multilingual-e5 등)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Obsidian vault를 source of truth로 유지(Markdown+frontmatter) | Karpathy llm-wiki 철학, 락인 방지, Obsidian 네이티브 그래프·링크 활용 | — Pending |
| 기존 현재 vault를 확장(새 vault 아님) | 사용자 기존 자산 보존, `.obsidian/` 설정 재사용 | — Pending |
| Postgres + pgvector로 하이브리드 검색 레이어 추가(gbrain 참조) | dense+BM25 검색, 구조화 쿼리, 그래프 엣지 저장 한번에 — PGLite로 시작해 Docker 없이 가볍게 | — Pending |
| 수집은 스크립트, 인제스트는 배치, Claude는 세션 내 판단만 | LLM 비용 최소화 원칙. Claude API 호출 빈도 최소화 | — Pending |
| stock-mcp는 Python(FastMCP) | .venv 기존 존재, dart-fss·pykrx·FinanceDataReader 등 한국 시장 라이브러리가 Python에 집중 | — Pending |
| graphify 활용해 vault를 인터랙티브 그래프로 변환 | "무엇이" + "왜"까지 추적 가능, 사용자 명시 요구 | — Pending |
| 인제스트 `_derived` 추출은 Claude Schedule 에이전트(git round-trip)가 수행, 임베딩은 sentence-transformers 로컬 직접 (No Ollama) | 사용자 Claude Max 구독 기반이라 별도 API 과금 없음, 로컬 GPU·Ollama 인프라 부담 제거, ingest venv `anthropic` 금지 원칙 유지 | Decided 2026-04-17 |
| 한국 시장 집중, 글로벌/암호화폐 제외 | v1 범위 희석 방지, 데이터 소스·도메인 지식 집중화 | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-17 after initialization*
