"""tests/briefing/test_daily.py — generate_daily_briefing orchestrator (Task 3, SC#1/6).

DB-backed: seeds analysis cards through ``store.save_card`` on the ≥11-ticker
``briefing_engine`` fixture, then asserts the persisted ``daily_briefing`` row.
"""

from __future__ import annotations

from datetime import date

import pytest

from briefing.daily import generate_daily_briefing
from cards import store

# The KST date the shared ``make_card`` factory stamps generated_at with (conftest).
_ON_DATE = date(2026, 7, 16)


@pytest.mark.db
def test_truncates_to_ten(briefing_engine, seeded_entities, make_card):
    # 11 first-ever high-conviction cards -> 11 new_high_conviction events -> truncate to 10.
    for corp, ticker in seeded_entities:
        store.save_card(
            briefing_engine,
            make_card(corp_code=corp, ticker=ticker, stance="BUY", conviction=0.85),
        )
    row = generate_daily_briefing(_ON_DATE, engine=briefing_engine, held_tickers=set())
    assert len(row.payload["entries"]) == 10


@pytest.mark.db
def test_no_change_writes_short_row(briefing_engine):
    # An empty collect-set (no cards on this date) STILL writes a real row (SC#6).
    on_date = date(2020, 1, 1)
    row = generate_daily_briefing(on_date, engine=briefing_engine, held_tickers=set())
    assert row.payload["entries"] == []
    assert row.body_md == "오늘 유의미한 변화 없음"
    found = store.get_briefing_row(briefing_engine, "daily_briefing", on_date)
    assert found is not None
    assert found.payload["entries"] == []


@pytest.mark.db
def test_persisted_row_is_daily_briefing(briefing_engine, seeded_entities, make_card):
    corp, ticker = seeded_entities[0]
    store.save_card(
        briefing_engine,
        make_card(corp_code=corp, ticker=ticker, stance="BUY", conviction=0.9),
    )
    row = generate_daily_briefing(_ON_DATE, engine=briefing_engine, held_tickers=set())
    assert row.report_type == "daily_briefing"
    assert row.report_date == _ON_DATE
    assert len(row.payload["entries"]) == 1
    assert row.payload["entries"][0]["ticker"] == ticker
    # The stored row is readable back through the store delegate (self-describing payload).
    found = store.get_briefing_row(briefing_engine, "daily_briefing", _ON_DATE)
    assert found is not None
    assert found.card_id == row.card_id


@pytest.mark.db
def test_stance_flip_over_superseded_prior(briefing_engine, seeded_entities, make_card):
    # A HOLD active superseding a SELL prior surfaces as a stance_flip entry (D-02).
    corp, ticker = seeded_entities[1]
    prior = make_card(
        corp_code=corp, ticker=ticker, stance="SELL", conviction=0.6, card_id="prior_x"
    )
    store.save_card(briefing_engine, prior)
    active = make_card(
        corp_code=corp, ticker=ticker, stance="HOLD", conviction=0.6, card_id="active_x"
    )
    store.save_card(briefing_engine, active, supersedes=prior.card_id)
    row = generate_daily_briefing(_ON_DATE, engine=briefing_engine, held_tickers=set())
    entries = {e["ticker"]: e for e in row.payload["entries"]}
    assert entries[ticker]["event_class"] == "stance_flip"
    assert entries[ticker]["change"] == "SELL→HOLD"


def test_generate_daily_briefing_is_exported():
    from briefing import generate_daily_briefing as exported

    assert exported is generate_daily_briefing
