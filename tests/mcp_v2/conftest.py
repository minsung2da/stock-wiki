"""Fixtures for tests/mcp_v2 — Plan 03-02 Task 3 (per-dir conftest scoping).

Re-declares the live-Postgres fixtures the MCP-tool tests need (the session
``pg_engine`` lives in the top-level ``tests/conftest.py``; ``pg_clean`` and
``seeded_engine`` are re-declared here because per-directory conftests do not
inherit sibling-directory function fixtures).

Adds ``seeded_narrative_engine`` — seeds ``filings``, ``news``, and ``notes``
rows with NON-NULL ``body_tsv`` / ``body_embedding`` (or ``content_emb``) /
``bm25_tokens`` so the Wave-2 ``hybrid_search`` tests (Plan 06) have searchable
data without re-running the embedding backfill. A deterministic constant
halfvec literal stands in for bge-m3 (no model download).
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

# A deterministic, non-zero 1024-d halfvec literal — stands in for a bge-m3
# vector so the dense column is unambiguously non-NULL. Same value for every
# seeded row (ranking is irrelevant to the seed; presence of a vector is).
_SEED_VEC_LITERAL = "[" + ",".join(["0.01"] * 1024) + "]"
_SEED_TOKENS = [101, 202, 303]
_KST = ZoneInfo("Asia/Seoul")


@pytest.fixture
def seeded_engine(pg_clean):
    """pg_clean with 삼성전자 / 00126380 / 005930 pre-seeded (entities + aliases)."""
    with pg_clean.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entities (corp_code, canonical_name, current_ticker, market) "
                "VALUES ('00126380', '삼성전자', '005930', 'KOSPI')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO entity_aliases (corp_code, kind, value, valid_from, valid_to) "
                "VALUES ('00126380', 'ticker', '005930', :vf, NULL), "
                "       ('00126380', 'name',   '삼성전자', :vf, NULL)"
            ),
            {"vf": date(2020, 1, 1)},
        )
    return pg_clean


@pytest.fixture
def seeded_narrative_engine(seeded_engine):
    """seeded_engine + one filings + one news + one note row, each with non-NULL
    body_tsv / (body_embedding|content_emb) / bm25_tokens — searchable corpus for
    hybrid_search tests (Plan 06)."""
    eng = seeded_engine
    with eng.begin() as conn:
        # filings
        conn.execute(
            text(
                "INSERT INTO filings "
                "(rcept_no, corp_code, ticker, filed_at, report_nm, pblntf_ty, "
                " source_url, content_hash, body_md, body_tsv, body_embedding, bm25_tokens, "
                " fetched_at) "
                "VALUES "
                "(:r, '00126380', '005930', :f, :nm, 'A', :url, :h, :body, "
                " to_tsvector('simple', :body), CAST(:vec AS halfvec), :toks, now())"
            ),
            {
                "r": "20260520000001",
                "f": datetime(2026, 5, 20, 15, 30, tzinfo=_KST),
                "nm": "분기보고서",
                "url": "https://dart.fss.or.kr/x?rcpNo=20260520000001",
                "h": "f" * 64,
                "body": "# 분기보고서\n\n삼성전자 반도체 영업이익 증가.\n",
                "vec": _SEED_VEC_LITERAL,
                "toks": _SEED_TOKENS,
            },
        )
        # news — note the column is `tickers` (TEXT[]), not `ticker`.
        conn.execute(
            text(
                "INSERT INTO news "
                "(url_hash, url, outlet, corp_code, tickers, published_at, title, "
                " content_hash, body_md, body_tsv, body_embedding, bm25_tokens) "
                "VALUES "
                "(:uh, :url, :outlet, '00126380', :tickers, :pub, :title, :h, :body, "
                " to_tsvector('simple', :body), CAST(:vec AS halfvec), :toks)"
            ),
            {
                "uh": "a" * 64,
                "url": "https://news.example.com/a",
                "outlet": "한경",
                "tickers": ["005930"],
                "pub": datetime(2026, 5, 21, 9, 0, tzinfo=_KST),
                "title": "삼성전자 실적 개선",
                "h": "b" * 64,
                "body": "삼성전자 영업이익 컨센서스 상회.\n",
                "vec": _SEED_VEC_LITERAL,
                "toks": _SEED_TOKENS,
            },
        )
        # note (content_emb instead of body_embedding)
        conn.execute(
            text(
                "INSERT INTO notes "
                "(path, corp_code, content_md, content_hash, updated_at, "
                " body_tsv, content_emb, bm25_tokens) "
                "VALUES "
                "(:p, '00126380', :body, :h, now(), "
                " to_tsvector('simple', :body), CAST(:vec AS halfvec), :toks)"
            ),
            {
                "p": "notes/private/samsung.md",
                "body": "# 삼성전자 thesis\n\n반도체 사이클 회복 전망.\n",
                "h": "c" * 64,
                "vec": _SEED_VEC_LITERAL,
                "toks": _SEED_TOKENS,
            },
        )
    return eng
