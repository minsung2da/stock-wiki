# Phase 4: Multi-Source Collector Coverage - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-18
**Phase:** 04-multi-source-collector-coverage
**Areas discussed:** Ticker scope, Vault layout per source, News 수집 정책, KIND 데이터 획득, Orchestration CLI, Macro 수집 빈도

---

## Gray area selection

| Option | Description | Selected |
|--------|-------------|----------|
| Ticker scope 소스 | 어디서 watchlist 읽는가 | ✓ |
| Vault layout per source | 파일 단위·경로 규칙 | ✓ |
| News 수집 정책 | RSS·스코프·저작권 | ✓ |
| KIND 데이터 획득 | API 부재 시 전략 | ✓ |

---

## Ticker scope

### Q1: 관심·보유 종목 목록 소스
| Option | Description | Selected |
|--------|-------------|----------|
| vault/notes/portfolio.md frontmatter | Dataview-ready, Phase 8 재사용 | ✓ |
| .env 하드코딩 | 단순, 편집 불편 | |
| .planning/tickers.yaml | vault 분리 | |
| CLI 인자만 | 설정 파일 없음 | |

### Q2: 프론트매터 스키마
| Option | Description | Selected |
|--------|-------------|----------|
| watchlist 티커 + holdings(티커) | 단순 | |
| holdings(ticker,qty,avg_cost) + watchlist | Phase 8 사전작업 | ✓ |
| tickers: [...] 단일 필드 | 스코프 최소화 | |
| Claude가 결정 | | |

### Q3: Git 공유 정책
| Option | Description | Selected |
|--------|-------------|----------|
| watchlist만 commit, holdings ignored | 팀 프라이버시 | |
| 전체 commit (개인 가정) | 단순 | |
| 전체 .gitignore | | ✓ (revised — KRX 질문 시 수정) |

**Notes:** KRX 레이아웃 질문 중 유저가 "portfolio.md .gitignore 해제하고 전체 다 공유"로 수정. 최종 결정 = 전체 commit (CONTEXT D-03).

---

## Vault layout

### Q4: KRX 레이아웃
| Option | Description | Selected |
|--------|-------------|----------|
| raw/krx/YYYY-MM-DD/{ticker}.md | 티커별 1파일/일 | ✓ |
| raw/krx/{ticker}/YYYY.md | 연단위 append | |
| raw/krx/YYYY-MM-DD/all.md | 일별 consolidated | |
| 세 소스 분리 파일 | | |

### Q5: 나머지 세 소스(news/macro/kind) 레이아웃
| Option | Description | Selected |
|--------|-------------|----------|
| 모두 그대로 (news=기사, macro=시리즈, kind=이벤트) | 추천 | ✓ |
| macro도 날짜폴더로 통일 | | |
| news 일별 consolidated | | |
| Claude가 결정 | | |

---

## News 수집 정책

### Q6: RSS·스코프
| Option | Description | Selected |
|--------|-------------|----------|
| 한경+이데일리, 통합 카테고리 + 본문 파싱 후 티커 매칭 | 높은 재현율 | ✓ |
| RSS 카테고리 필터만 | | |
| 세 매체 전부 | | |
| 한경만 MVP | | |

### Q7: 회사명 매칭 소스
| Option | Description | Selected |
|--------|-------------|----------|
| entities + aliases 테이블 DB 조회 | 정확·재사용 | ✓ |
| FinanceDataReader 런업 | | |
| .planning/ticker_aliases.yaml | | |
| DB 우선 + alias fallback | | |

### Q8: 저작권 친화 방식
| Option | Description | Selected |
|--------|-------------|----------|
| 전문 저장 안함, frontmatter + body=첫 2문단 | | ✓ |
| 전문 저장 + license_flag | | |
| 리드(첫 3문단)만 | | |
| Claude가 결정 | | |

---

## KIND 데이터 획득

### Q9: 데이터 획득 전략
| Option | Description | Selected |
|--------|-------------|----------|
| DART API + pykrx 상태 선호, 부족한 것만 KIND 스크레이핑 | 하이브리드 | ✓ |
| KIND 웹 스크레이핑 전면 | | |
| DART+pykrx만, 나머지 deferred | | |
| pykrx 상태만, 불성실공시 deferred | | |

### Q10: KIND 스크레이핑 허용 범위
| Option | Description | Selected |
|--------|-------------|----------|
| robots.txt 준수, 1 req/sec, UA 식별, content_hash 캐시 | | ✓ |
| 스크레이핑 전면 금지 | | |
| 픽스처 기반 스크레이핑 | | |

---

## Orchestration CLI

### Q11: CLI 구조
| Option | Description | Selected |
|--------|-------------|----------|
| stock collect <source> + stock collect all [--sources=a,b] | | ✓ |
| stock collect all + --only/--skip 플래그만 | | |
| Phase 3 dart 패턴 유지 + all 추가 | | |

### Q12: 부분 실패 종료 코드
| Option | Description | Selected |
|--------|-------------|----------|
| 1개라도 실패면 exit 1 + stderr JSON + heartbeat | | ✓ |
| 전부 실패일 때만 exit 1 | | |
| --strict 토글 | | |

---

## Macro 수집 빈도

### Q13: 실행 주기
| Option | Description | Selected |
|--------|-------------|----------|
| 매일 전체 시리즈 조회 + content_hash 멱등 | | ✓ |
| 시리즈별 frequency 메타 분리 실행 | | |
| 매일 전체 + stale_after_days 메타 | | |

**Notes:** 유저 — "token 사용하는게 아니라면 1번으로" — ECOS/FRED는 HTTP API만이라 LLM 토큰 무관. 확정.

---

## Claude's Discretion

- pykrx `get_market_status_by_ticker` 정확한 시그니처
- DART B(주요사항) 거래정지 필터링 기준
- trafilatura "문단" 경계 정의
- URL canonicalization (utm_*)
- news url_hash 길이
- collect_all 순차 vs 병렬

## Deferred Ideas

- 서울경제 RSS
- portfolio holdings 민감정보 분리 (Phase 8)
- body 길이 3-4문단 확장
- pykrx vs FinanceDataReader 교차검증
- KIND 그 외 이벤트 타입
- Macro series 확장
- 수집기 병렬화
- URL canonicalization 고도화
