"""Local fixtures for tests/briefing (Phase 5).

The existing ``tests/cards/conftest.py::seeded_engine`` seeds ONLY 삼성전자/005930 —
but the SC#1 truncation (>10 entries) and multi-ticker priority/diff tests need ≥11
distinct tickers with active cards + superseded chains (05-RESEARCH §Wave 0 Gaps).
This conftest provides:

- ``SEEDED_ENTITIES`` / ``seeded_entities`` — 11 distinct (corp_code, ticker) pairs so
  the ``decision_cards.corp_code`` FK is satisfiable for any of them.
- ``briefing_engine`` — ``pg_clean`` with those 11 entities + their ticker/name aliases
  pre-inserted (loops the ``tests/cards/conftest.py`` INSERT idiom).
- ``make_card`` — a factory (fixture returning a callable) that builds a valid
  ``DecisionCard`` for any seeded ticker without a real ``portfolio.md`` or the §3 YAML
  oracle, so daily/priority/diff tests can stand up ≥11 active cards + chains.

All seed SQL uses bind params (never f-string interpolation).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from cards.models import DecisionCard

_KST = ZoneInfo("Asia/Seoul")

# 11 distinct (corp_code, ticker) pairs — one more than the SC#1 truncation cap (10),
# so the daily truncation test has a genuine >10 candidate set. corp_code is 8 digits
# (^[0-9]{8}$), ticker is 6 digits (^[0-9A-Z]{6}$).
SEEDED_ENTITIES: list[tuple[str, str]] = [
    (f"{i:08d}", f"{i:06d}") for i in range(1, 12)
]


@pytest.fixture
def seeded_entities() -> list[tuple[str, str]]:
    """The canonical (corp_code, ticker) seed set (≥11 distinct tickers)."""
    return list(SEEDED_ENTITIES)


@pytest.fixture
def briefing_engine(pg_clean):
    """``pg_clean`` with 11 distinct entities + ticker/name aliases pre-inserted.

    Each ``SEEDED_ENTITIES`` pair becomes an ``entities`` row plus a ``ticker`` and a
    ``name`` alias, so a ``DecisionCard`` for any of the 11 corps satisfies the
    ``decision_cards.corp_code`` FK.
    """
    with pg_clean.begin() as conn:
        for corp_code, ticker in SEEDED_ENTITIES:
            name = f"엔티티{ticker}"
            conn.execute(
                text(
                    "INSERT INTO entities (corp_code, canonical_name, current_ticker, market) "
                    "VALUES (:cc, :nm, :tk, 'KOSPI')"
                ),
                {"cc": corp_code, "nm": name, "tk": ticker},
            )
            conn.execute(
                text(
                    "INSERT INTO entity_aliases (corp_code, kind, value, valid_from, valid_to) "
                    "VALUES (:cc, 'ticker', :tk, :vf, NULL), "
                    "       (:cc, 'name',   :nm, :vf, NULL)"
                ),
                {"cc": corp_code, "tk": ticker, "nm": name, "vf": date(2020, 1, 1)},
            )
    return pg_clean


def _default_dt(kind: str) -> datetime:
    base = datetime(2026, 7, 16, tzinfo=_KST)
    return {
        "generated_at": base.replace(hour=17, minute=42),
        "as_of": base.replace(hour=16, minute=0),
        "expires_at": base.replace(hour=0, minute=0) + timedelta(days=30),
    }[kind]


@pytest.fixture
def make_card():
    """Return a factory building a valid ``DecisionCard`` for a seeded ticker.

    Usage::

        card = make_card(corp_code="00000001", ticker="000001",
                         stance="SELL", conviction=0.83)

    ``card_id`` defaults to ``card_{ticker}_{generated_at.date()}`` but is overridable
    (a supersession chain for one ticker needs distinct PKs). ``contradictions`` and
    ``key_claims`` accept raw dicts; every other §3-required field is filled with a
    minimal valid value.
    """

    def _make(
        *,
        corp_code: str,
        ticker: str,
        stance: str = "HOLD",
        conviction: float = 0.55,
        contradictions: list[dict] | None = None,
        key_claims: list[dict] | None = None,
        generated_at: datetime | None = None,
        as_of: datetime | None = None,
        expires_at: datetime | None = None,
        card_id: str | None = None,
    ) -> DecisionCard:
        gen = generated_at if generated_at is not None else _default_dt("generated_at")
        aof = as_of if as_of is not None else _default_dt("as_of")
        exp = expires_at if expires_at is not None else _default_dt("expires_at")
        cid = card_id if card_id is not None else f"card_{ticker}_{gen.date().isoformat()}"
        return DecisionCard.model_validate(
            {
                "card_id": cid,
                "corp_code": corp_code,
                "ticker": ticker,
                "generated_at": gen,
                "as_of": aof,
                "schema_version": 1,
                "decision": {
                    "stance": stance,
                    "conviction": conviction,
                    "horizon_days": 30,
                },
                "key_claims": (
                    key_claims
                    if key_claims is not None
                    else [
                        {
                            "id": "c1",
                            "text": f"{ticker} catalyst",
                            "evidence_refs": ["dart:x"],
                            "weight": "HIGH",
                            "confidence": 0.7,
                        }
                    ]
                ),
                "contradictions": contradictions if contradictions is not None else [],
                "assumptions": [f"{ticker} baseline assumption holds"],
                "expires_at": exp,
                "body_md": f"# {ticker} — {stance}\n",
            }
        )

    return _make
