"""Local fixtures for tests/cards.

`decision_card_yaml` — the redesign §3 decision_card YAML
(``.planning/research/redesign-2026-05.md`` lines 236-294) transcribed verbatim as a
Python dict. This dict IS the SC#3 round-trip oracle:
``DecisionCard.model_validate(decision_card_yaml)`` must succeed and round-trip. The §3
YAML carries no ``body_md`` (it is the human-render of the payload), so a minimal
non-empty markdown string is added here.

`seeded_engine` — re-declared from ``tests/db/conftest.py:44-62`` because conftest
scoping is per-directory. Seeds 삼성전자 / 00126380 / 005930 into ``entities`` +
``entity_aliases`` so the ``decision_cards.corp_code`` FK is satisfiable. Plan 03's
``test_store.py`` consumes it.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text


@pytest.fixture
def decision_card_yaml() -> dict:
    """The redesign §3 decision_card transcribed verbatim (SC#3 round-trip oracle).

    `numeric_facts` deliberately mixes an int (``market_cap_krw``) and floats
    (``pe_ttm``, ``foreign_ownership_pct``) to guard the int-vs-float round-trip
    (Pitfall #4). `body_md` is added (not in §3 YAML) as a minimal non-empty string.
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


@pytest.fixture
def seeded_engine(pg_clean):
    """pg_clean with 삼성전자/005930 pre-inserted (entities + ticker+name aliases).

    Re-declared from tests/db/conftest.py (conftest scoping is per-directory). The
    seeded corp_code 00126380 / ticker 005930 match decision_card_yaml so the
    decision_cards.corp_code FK is satisfiable in Plan 03's test_store.py.
    """
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
