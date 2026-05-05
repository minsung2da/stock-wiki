# Phase 7 — Canonical Subgraph Queries

이 디렉터리는 `stock graph snapshot`이 일배치 또는 수동 실행으로 생성하는
graphify 산출물(`<YYYY-MM-DD>/index.html`, `graph.json`, `GRAPH_REPORT.md`)을 담는다.
이 README는 **5개의 캐노니컬 서브그래프 쿼리**를 정의한다 — 산출물을 보지 않고도
DB(`edges` + `documents` + `entities`) 만으로 답할 수 있는 질문이며,
각 snippet은 그대로 복사해 `python -c` 또는 Jupyter 셀에서 실행 가능하다.

> **모든 날짜는 KST 자정 기준.** 디렉터리 이름은 ISO 형식
> (`2026-05-05` — 공백·"KST" suffix 없음). 시간대 의도는 본 README에 명시.
>
> **Phase 9 scheduler hookup 예정 (D-21):** systemd.timer 또는 Windows Task
> Scheduler에서 daily-batch 직후 `uv run stock graph snapshot`을 호출하도록
> 등록될 예정. Phase 7은 CLI까지만.

***

## Q1 — 내 포지션 오늘 어때?

`notes/private/portfolio.md`에 등록된 보유 종목 각각에 대해, 최근 N일(기본 30일)
이내의 mentions_ticker / filing_event / note_ticker 엣지를 모아 한 페이지로 집약.

```python
from datetime import date, timedelta
import sqlalchemy as sa
from db.engine import get_engine
from shared.portfolio import Portfolio
from stock_mcp.repo_root import repo_root


def q1_positions_recent_events(days: int = 30) -> list[dict]:
    portfolio = Portfolio.load(repo_root())
    tickers = [h.ticker for h in portfolio.holdings]
    if not tickers:
        return []
    cutoff = date.today() - timedelta(days=days)
    with get_engine().connect() as conn:
        rows = conn.execute(sa.text("""
            SELECT e.dst_id AS ticker, e.src_id AS document_id, e.edge_type,
                   d.vault_path, d.first_seen_at, d.source
              FROM edges e
              JOIN documents d ON d.id = e.src_id AND e.src_type = 'document'
             WHERE e.dst_type = 'ticker' AND e.dst_id = ANY(:tickers)
               AND e.edge_type IN ('mentions_ticker','filing_event','note_ticker')
               AND d.first_seen_at >= :cutoff
             ORDER BY d.first_seen_at DESC LIMIT 200
        """), {"tickers": tickers, "cutoff": cutoff}).mappings().all()
    return [dict(r) for r in rows]
```

***

## Q2 — 왜 지금 이 상태인가? (Catalyst chain)

같은 corp_code의 90일 윈도우 내 인접 이벤트 쌍에 부여된 `event_event` 엣지를
재귀 CTE로 walk. ticker → entities.corp_code lookup 후 `{corp_code}-` 접두사
event id로 시작점 결정. 깊이 cap=10 (T-7-04-01).

```python
from typing import Any
import sqlalchemy as sa
from db.engine import get_engine


def q2_catalyst_chain(ticker: str, days: int = 90) -> list[dict]:
    if not ticker or len(ticker) != 6:
        return []
    with get_engine().connect() as conn:
        corp_code = conn.execute(sa.text(
            "SELECT corp_code FROM entities WHERE current_ticker = :t"
        ), {"t": ticker}).scalar()
        if not corp_code:
            return []
        rows = conn.execute(sa.text("""
            WITH RECURSIVE chain AS (
                SELECT src_id, dst_id, 1 AS depth
                  FROM edges
                 WHERE edge_type = 'event_event'
                   AND src_id LIKE :prefix
                UNION
                SELECT e.src_id, e.dst_id, c.depth + 1
                  FROM edges e
                  JOIN chain c ON e.dst_id = c.src_id
                 WHERE e.edge_type = 'event_event' AND c.depth < 10
            )
            SELECT depth, src_id, dst_id FROM chain ORDER BY depth
        """), {"prefix": f"{corp_code}-%"}).mappings().all()
    return [dict(r) for r in rows]
```

***

## Q3 — 이 섹터에서 무슨 일이 일어나고 있나?

`ticker_sector` 엣지로 sector_code → tickers를 펼친 뒤, 각 ticker의
`mentions_ticker` 엣지로 N일 내 filings를 모음.

```python
from datetime import date, timedelta
import sqlalchemy as sa
from db.engine import get_engine


def q3_sector_filings(sector_code: str, days: int = 14) -> list[dict]:
    if not sector_code:
        return []
    cutoff = date.today() - timedelta(days=days)
    with get_engine().connect() as conn:
        rows = conn.execute(sa.text("""
            SELECT ts.src_id AS ticker, ent.canonical_name,
                   mt.src_id AS document_id, d.vault_path, d.first_seen_at
              FROM edges ts
              JOIN entities ent ON ent.current_ticker = ts.src_id
              JOIN edges mt ON mt.dst_id = ts.src_id
                            AND mt.dst_type = 'ticker'
                            AND mt.edge_type = 'mentions_ticker'
              JOIN documents d ON d.id = mt.src_id AND mt.src_type = 'document'
             WHERE ts.edge_type = 'ticker_sector'
               AND ts.dst_id = :sector
               AND d.first_seen_at >= :cutoff
             ORDER BY d.first_seen_at DESC LIMIT 200
        """), {"sector": sector_code, "cutoff": cutoff}).mappings().all()
    return [dict(r) for r in rows]
```

***

## Q4 — 이게 최신본인가? (Supersedes chain)

DART rcept_no를 seed로 `supersedes` 엣지를 따라 재귀 walk. 깊이 cap=10.

```python
import sqlalchemy as sa
from db.engine import get_engine


def q4_supersedes_chain(rcept_no: str) -> list[dict]:
    if not rcept_no:
        return []
    with get_engine().connect() as conn:
        seed = conn.execute(sa.text("""
            SELECT id FROM documents
             WHERE source = 'dart' AND source_url LIKE :pat
             LIMIT 1
        """), {"pat": f"%{rcept_no}%"}).scalar()
        if not seed:
            return []
        rows = conn.execute(sa.text("""
            WITH RECURSIVE chain AS (
                SELECT src_id, dst_id, 0 AS depth
                  FROM edges
                 WHERE edge_type = 'supersedes' AND src_id = :seed
                UNION
                SELECT e.src_id, e.dst_id, c.depth + 1
                  FROM edges e
                  JOIN chain c ON e.dst_id = c.src_id
                 WHERE e.edge_type = 'supersedes' AND c.depth < 10
            )
            SELECT c.depth, c.src_id, c.dst_id, d.vault_path
              FROM chain c
              LEFT JOIN documents d ON d.id = c.src_id
             ORDER BY c.depth
        """), {"seed": seed}).mappings().all()
    return [dict(r) for r in rows]
```

> **NB:** 본 페이즈 시점에 `supersedes` 엣지를 채우는 데이터(DART 정정 frontmatter
> 필드)는 probe-findings.md의 결과에 따라 **MISSING** — `_derive_supersedes`는
> 소프트 no-op이며, 본 쿼리는 빈 list를 반환한다. 후속 quick task에서 DART writer를
> 확장하면 (a) `[기재정정]` prefix 파싱 또는 (b) OpenDART `notice_search`
> `pblntf_detail_ty='I001'` 조회로 정정 관계를 surface하여 supersedes 엣지가
> 자동 생성된다.

***

## Q5 — 내 메모 ↔ 공시 (Notes ↔ events)

같은 ticker에 연결된 `note_ticker` 엣지(user notes)와 `filing_event` 엣지(raw
evidence — 단, 같은 source 문서가 mentions_ticker 엣지도 보유한 경우만)를 병렬로
가져옴 — user research 가설과 raw evidence가 한 화면에 보임.

```python
from datetime import date, timedelta
import sqlalchemy as sa
from db.engine import get_engine


def q5_notes_events(ticker: str, days: int = 60) -> dict:
    if not ticker:
        return {"notes": [], "events": []}
    cutoff = date.today() - timedelta(days=days)
    with get_engine().connect() as conn:
        notes = conn.execute(sa.text("""
            SELECT e.src_id AS note_id, d.vault_path, d.first_seen_at
              FROM edges e
              JOIN documents d ON d.id = e.src_id
             WHERE e.edge_type = 'note_ticker' AND e.dst_id = :ticker
             ORDER BY d.first_seen_at DESC LIMIT 50
        """), {"ticker": ticker}).mappings().all()
        events = conn.execute(sa.text("""
            SELECT fe.src_id AS document_id, fe.dst_id AS event_id,
                   d.vault_path, d.first_seen_at
              FROM edges fe
              JOIN edges mt ON mt.src_id = fe.src_id
                            AND mt.dst_id = :ticker
                            AND mt.edge_type = 'mentions_ticker'
              JOIN documents d ON d.id = fe.src_id
             WHERE fe.edge_type = 'filing_event'
               AND d.first_seen_at >= :cutoff
             ORDER BY d.first_seen_at DESC LIMIT 100
        """), {"ticker": ticker, "cutoff": cutoff}).mappings().all()
    return {"notes": [dict(r) for r in notes], "events": [dict(r) for r in events]}
```

***

## 실행 방법

```bash
# 단일 함수 실행
uv run python -c "from src.graph.canonical import q1_positions_recent_events; print(q1_positions_recent_events(30))"

# CI smoke test (5 쿼리 모두 fixture vault에서 non-empty 보장)
uv run pytest tests/graph/test_canonical_queries.py -v
```

## graphify 산출물

`<YYYY-MM-DD>/index.html`을 Obsidian으로 드래그하거나 브라우저로 열면 vault 전체
인터랙티브 그래프가 표시된다. 5개 쿼리는 graphify 출력에 의존하지 않으며,
graphify 출력은 사람-친화 시각화 + community 라벨링 보너스로 활용한다 (D-20).
