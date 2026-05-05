"""Phase 7 GRAPH-03: 5 canonical subgraph queries (D-16 ~ D-20).

Each query operates on the ``edges`` + ``documents`` + ``entities`` tables only —
NOT the ``events`` table (RESEARCH §Pitfall 1: events table is empty in v1; the
event_event/filing_event derivations synthesize event ids inline, so queries
walk those synthetic ids through the edges table directly).

All queries return data structures (list[dict] or dict) that vault/graph/README.md
inline Python snippets exactly mirror by function name.

Direction conventions (Plan 02 lock-in):
    mentions_ticker: document → ticker
    note_ticker:     document(note) → ticker
    ticker_sector:   ticker        → sector
    supersedes:      doc(amendment) → doc(original)
    filing_event:    document       → event(synth_id)
    event_event:     event(prev)    → event(curr)

Cap: recursive CTEs use ``c.depth < 10`` (T-7-04-01 DoS mitigation).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import sqlalchemy as sa

from db.engine import get_engine
from shared.portfolio import Portfolio
from stock_mcp.repo_root import repo_root

__all__ = [
    "q1_positions_recent_events",
    "q2_catalyst_chain",
    "q3_sector_filings",
    "q4_supersedes_chain",
    "q5_notes_events",
]


def q1_positions_recent_events(days: int = 30) -> list[dict[str, Any]]:
    """Q1: 포트폴리오 holdings × 30일 이내 events·필링·노트 서브그래프.

    질문: '내 포지션 오늘 어때?'
    """
    portfolio = Portfolio.load(repo_root())
    tickers = [h.ticker for h in portfolio.holdings]
    if not tickers:
        return []
    cutoff = date.today() - timedelta(days=days)
    with get_engine().connect() as conn:
        rows = (
            conn.execute(
                sa.text(
                    """
                    SELECT e.dst_id     AS ticker,
                           e.src_id     AS document_id,
                           e.edge_type,
                           d.vault_path,
                           d.first_seen_at,
                           d.source
                      FROM edges e
                      JOIN documents d ON d.id = e.src_id AND e.src_type = 'document'
                     WHERE e.dst_type = 'ticker'
                       AND e.dst_id = ANY(:tickers)
                       AND e.edge_type IN ('mentions_ticker', 'filing_event', 'note_ticker')
                       AND d.first_seen_at >= :cutoff
                     ORDER BY d.first_seen_at DESC
                     LIMIT 200
                    """
                ),
                {"tickers": tickers, "cutoff": cutoff},
            )
            .mappings()
            .all()
        )
    return [dict(r) for r in rows]


def q2_catalyst_chain(ticker: str, days: int = 90) -> list[dict[str, Any]]:
    """Q2: 주어진 ticker의 event_event 체인 BFS (역방향 — 인과 추적).

    질문: '왜 지금 이 상태인가?'
    """
    if not ticker or len(ticker) != 6:
        return []
    with get_engine().connect() as conn:
        corp_code = conn.execute(
            sa.text("SELECT corp_code FROM entities WHERE current_ticker = :t"),
            {"t": ticker},
        ).scalar()
        if not corp_code:
            return []
        rows = (
            conn.execute(
                sa.text(
                    """
                    WITH RECURSIVE chain AS (
                        SELECT src_id, dst_id, 1 AS depth
                          FROM edges
                         WHERE edge_type = 'event_event'
                           AND src_id LIKE :prefix
                        UNION
                        SELECT e.src_id, e.dst_id, c.depth + 1
                          FROM edges e
                          JOIN chain c ON e.dst_id = c.src_id
                         WHERE e.edge_type = 'event_event'
                           AND c.depth < 10
                    )
                    SELECT depth, src_id, dst_id FROM chain ORDER BY depth
                    """
                ),
                {"prefix": f"{corp_code}-%"},
            )
            .mappings()
            .all()
        )
    return [dict(r) for r in rows]


def q3_sector_filings(sector_code: str, days: int = 14) -> list[dict[str, Any]]:
    """Q3: 주어진 sector_code의 N일 내 filings + tickers.

    질문: '이 섹터에서 무슨 일이 일어나고 있나?'
    """
    if not sector_code:
        return []
    cutoff = date.today() - timedelta(days=days)
    with get_engine().connect() as conn:
        rows = (
            conn.execute(
                sa.text(
                    """
                    SELECT ts.src_id AS ticker,
                           ent.canonical_name,
                           mt.src_id AS document_id,
                           d.vault_path,
                           d.first_seen_at
                      FROM edges ts
                      JOIN entities ent ON ent.current_ticker = ts.src_id
                      JOIN edges mt ON mt.dst_id = ts.src_id
                                    AND mt.dst_type = 'ticker'
                                    AND mt.edge_type = 'mentions_ticker'
                      JOIN documents d ON d.id = mt.src_id AND mt.src_type = 'document'
                     WHERE ts.edge_type = 'ticker_sector'
                       AND ts.dst_id = :sector
                       AND d.first_seen_at >= :cutoff
                     ORDER BY d.first_seen_at DESC
                     LIMIT 200
                    """
                ),
                {"sector": sector_code, "cutoff": cutoff},
            )
            .mappings()
            .all()
        )
    return [dict(r) for r in rows]


def q4_supersedes_chain(rcept_no: str) -> list[dict[str, Any]]:
    """Q4: 주어진 DART rcept_no 기준 supersedes 체인 walk. 최신본 audit.

    질문: '이게 최신본인가?'

    NB: probe-findings.md (2026-05-05) — DART writer does not yet emit a
    correction-of frontmatter field; ``_derive_supersedes`` runs as a soft
    no-op. Therefore Q4 currently returns [] for every input until the DART
    writer + ingest are extended (deferred quick task). The recursive walk
    code is committed up-front so the moment supersedes edges land, no schema
    or API change is needed downstream.
    """
    if not rcept_no:
        return []
    with get_engine().connect() as conn:
        seed = conn.execute(
            sa.text(
                """
                SELECT id FROM documents
                 WHERE source = 'dart' AND source_url LIKE :pat
                 LIMIT 1
                """
            ),
            {"pat": f"%{rcept_no}%"},
        ).scalar()
        if not seed:
            return []
        rows = (
            conn.execute(
                sa.text(
                    """
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
                    """
                ),
                {"seed": seed},
            )
            .mappings()
            .all()
        )
    return [dict(r) for r in rows]


def q5_notes_events(ticker: str, days: int = 60) -> dict[str, list[dict[str, Any]]]:
    """Q5: user research(notes) ↔ raw evidence(events) 연결.

    질문: '내 메모와 공시를 같이 보고 싶다.'
    """
    if not ticker:
        return {"notes": [], "events": []}
    cutoff = date.today() - timedelta(days=days)
    with get_engine().connect() as conn:
        notes = (
            conn.execute(
                sa.text(
                    """
                    SELECT e.src_id AS note_id,
                           d.vault_path,
                           d.first_seen_at
                      FROM edges e
                      JOIN documents d ON d.id = e.src_id
                     WHERE e.edge_type = 'note_ticker'
                       AND e.dst_id = :ticker
                     ORDER BY d.first_seen_at DESC
                     LIMIT 50
                    """
                ),
                {"ticker": ticker},
            )
            .mappings()
            .all()
        )
        events = (
            conn.execute(
                sa.text(
                    """
                    SELECT fe.src_id  AS document_id,
                           fe.dst_id  AS event_id,
                           d.vault_path,
                           d.first_seen_at
                      FROM edges fe
                      JOIN edges mt ON mt.src_id = fe.src_id
                                    AND mt.dst_id = :ticker
                                    AND mt.edge_type = 'mentions_ticker'
                      JOIN documents d ON d.id = fe.src_id
                     WHERE fe.edge_type = 'filing_event'
                       AND d.first_seen_at >= :cutoff
                     ORDER BY d.first_seen_at DESC
                     LIMIT 100
                    """
                ),
                {"ticker": ticker, "cutoff": cutoff},
            )
            .mappings()
            .all()
        )
    return {"notes": [dict(r) for r in notes], "events": [dict(r) for r in events]}
