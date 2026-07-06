"""Base fixtures for tests/analysis — Phase 4 Wave 0 scaffold.

Per-directory conftest scoping: the session ``pg_engine`` + function ``pg_clean``
live in the top-level ``tests/conftest.py`` and ARE inherited here; only
sibling-directory fixtures (e.g. ``tests/cards``' ``seeded_engine``) are NOT, so the
ones this package needs are re-declared below (copying the working
``tests/mcp_v2/conftest.py`` / ``tests/cards/conftest.py`` shapes).

Three base fixtures every Phase-4 plan reuses (the sub-agent fake is intentionally
NOT here — it arrives with the subagents plan):

- ``seeded_engine``   — pg_clean with 삼성전자 / 00126380 / 005930 + a couple of
  filings carrying real ``body_md`` (Korean-unit numerics) for runner/checksum work.
  Tools read the same DB via ``get_engine()`` (``DATABASE_URL`` set by ``pg_engine``),
  so seeding this engine is sufficient — no ``get_engine`` monkeypatch needed.
- ``real_filing_body`` — a ``body_md`` string with ≥1 Korean-unit numeric (a 조/억
  amount and a % value) for the D-03 checksum tests (no DB required).
- ``card_oracle``     — the redesign §3 round-trip dict (verbatim from
  ``tests/cards/conftest.py``); ``DecisionCard.model_validate(card_oracle)`` succeeds.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

_KST = ZoneInfo("Asia/Seoul")

# Deterministic non-zero 1024-d halfvec + tokens — stand in for bge-m3 so the
# filings dense/BM25 columns are unambiguously non-NULL (ranking irrelevant to seed).
_SEED_VEC_LITERAL = "[" + ",".join(["0.01"] * 1024) + "]"
_SEED_TOKENS = [101, 202, 303]

# A body_md with Korean-unit numerics for the D-03 value-equivalence checksum:
# 42.5조원 (KRW조 → 4.25e13), 17.2% (pct), 5000억원 (KRW억 → 5e14... no: 5e11).
_FILING_BODY_1 = (
    "# 분기보고서\n\n"
    "당기 매출액은 42.5조원으로 전년 대비 증가하였습니다. "
    "영업이익률은 17.2%를 기록했습니다. "
    "영업이익은 5000억원 수준입니다.\n"
)
_FILING_BODY_2 = (
    "# 사업보고서\n\n"
    "해외 매출 비중은 68.4%이며, 배당성향 30% 유지 방침입니다.\n"
)


@pytest.fixture
def seeded_engine(pg_clean):
    """pg_clean + 삼성전자/00126380/005930 (entities + aliases) + two filings with
    real ``body_md`` (Korean-unit numerics). Re-declared per-directory."""
    eng = pg_clean
    with eng.begin() as conn:
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
        for rcept_no, filed, nm, body in (
            ("20260520000001", datetime(2026, 5, 20, 15, 30, tzinfo=_KST), "분기보고서", _FILING_BODY_1),
            ("20260415000002", datetime(2026, 4, 15, 15, 30, tzinfo=_KST), "사업보고서", _FILING_BODY_2),
        ):
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
                    "r": rcept_no,
                    "f": filed,
                    "nm": nm,
                    "url": f"https://dart.fss.or.kr/x?rcpNo={rcept_no}",
                    "h": rcept_no.ljust(64, "0"),
                    "body": body,
                    "vec": _SEED_VEC_LITERAL,
                    "toks": _SEED_TOKENS,
                },
            )
    return eng


@pytest.fixture
def real_filing_body() -> str:
    """A body_md carrying Korean-unit numerics (42.5조원 + 17.2% + 5000억원) for the
    D-03 checksum tests — a pure string, no DB needed."""
    return _FILING_BODY_1


@pytest.fixture
def card_oracle() -> dict:
    """The redesign §3 decision_card, verbatim (the SC#3 round-trip oracle).

    ``numeric_facts`` mixes an int (``market_cap_krw``) and floats (``pe_ttm``,
    ``foreign_ownership_pct``) to guard the int-vs-float round-trip. Copied from
    ``tests/cards/conftest.py`` (per-directory conftests do not cross-inherit).
    """
    return {
        "card_id": "card_005930_2026-05-28",
        "corp_code": "00126380",
        "ticker": "005930",
        "generated_at": "2026-05-28T17:42+09:00",
        "as_of": "2026-05-28T16:00+09:00",  # data cutoff (KST close)
        "schema_version": 1,
        "decision": {
            "stance": "HOLD",
            "conviction": 0.55,
            "horizon_days": 30,
            "price_ref": 71200,
            "invalidation_triggers": [
                "HBM3E NVIDIA qualification fails",
                "1Q26 메모리 ASP guidance < -10% QoQ",
            ],
        },
        "key_claims": [
            {
                "id": "c1",
                "text": "HBM3E 12-stack NVIDIA qualification near-term catalyst",
                "evidence_refs": ["dart:20260527000412", "news:hankyung:8821"],
                "weight": "HIGH",
                "confidence": 0.7,
            },
            {
                "id": "c2",
                "text": "Memory cycle bottom Q1 2026",
                "evidence_refs": ["macro:dramx:2026-05-27"],
                "weight": "MEDIUM",
                "confidence": 0.6,
            },
        ],
        "contradictions": [
            {
                "bull": "c1",
                "bear_evidence": "news:zdnet:9912",
                "bear_claim": "AMD MI300 시장 점유율 확대",
                "resolution": "downgraded conviction by 0.15",
            }
        ],
        "assumptions": [
            "DRAM contract ASP holds ≥ $X / Gb",
            "NVIDIA HBM3E qual decision arrives by 2026-06-15",
        ],
        "numeric_facts": {
            "market_cap_krw": 425000000000000,  # int — must NOT drift to float
            "pe_ttm": 17.2,
            "foreign_ownership_pct": 53.1,
        },
        "evidence_weights": {
            "dart": "HIGH",
            "krx_flow": "MEDIUM",
            "news_primary_kr": "MEDIUM",
            "user_thesis": "HIGH",
            "sentiment": "LOW",
            "price_action": "CONTEXT",
        },
        "guards_passed": [
            "position_size_ok",
            "daily_loss_under_2pct",
            "no_earnings_blackout",
            "no_unresolved_contradiction",
        ],
        "expires_at": "2026-06-15T00:00+09:00",  # MANDATORY — no untimed thesis
        "body_md": "# 삼성전자 (005930) — HOLD\n\nHBM3E qualification catalyst pending.\n",
    }
