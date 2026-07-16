"""tests/briefing/test_priority.py — dict-keyed prioritize + held-first (Task 2, D-01).

The CRITICAL contract: ``_priority_key`` operates on a FLAT entry-DICT (ticker /
event_class / conviction), never a ``ChangeEvent`` / ``.card`` attribute — so the weekly
(05-05) reuses the SAME callable over ``payload["entries"]`` where no ``DecisionCard``
object exists (SC#4 no-recompute).
"""

from __future__ import annotations

from briefing.daily import (
    ChangeEvent,
    _priority_key,
    load_held_tickers,
    prioritize,
)


def _event(
    make_card,
    *,
    corp: str,
    ticker: str,
    event_class: str = "stance_flip",
    conviction: float = 0.5,
    change: str = "A→B",
) -> ChangeEvent:
    card = make_card(
        corp_code=corp,
        ticker=ticker,
        stance="HOLD",
        conviction=conviction,
        card_id=f"c_{ticker}",
    )
    return ChangeEvent(card=card, event_class=event_class, change=change)


def test_priority_key_is_dict_keyed():
    # A plain flat dict (the shape weekly reads back from payload["entries"]) — the key
    # MUST NOT access any attribute (no .card / .decision).
    entry = {"ticker": "000001", "event_class": "stance_flip", "conviction": 0.5}
    key = _priority_key(entry, set())
    assert isinstance(key, tuple)
    assert len(key) == 3
    assert key == (1, 0, -0.5)
    # Held membership flips tier 1 to 0.
    assert _priority_key(entry, {"000001"}) == (0, 0, -0.5)


def test_held_first(make_card):
    events = [
        _event(
            make_card, corp="00000001", ticker="000001",
            event_class="new_high_conviction", conviction=0.9, change="new",
        ),
        _event(
            make_card, corp="00000002", ticker="000002",
            event_class="stance_flip", conviction=0.4, change="A→B",
        ),
    ]
    # 000001 held ranks first despite a lower-priority event class + higher conviction.
    entries = prioritize(events, {"000001"})
    assert entries[0]["ticker"] == "000001"


def test_event_class_order(make_card):
    events = [
        _event(make_card, corp="00000004", ticker="000004",
               event_class="new_high_conviction", conviction=0.9, change="new"),
        _event(make_card, corp="00000003", ticker="000003",
               event_class="expired_invalidated", conviction=0.9, change="expired"),
        _event(make_card, corp="00000002", ticker="000002",
               event_class="new_contradiction", conviction=0.9, change="+1 contradictions"),
        _event(make_card, corp="00000001", ticker="000001",
               event_class="stance_flip", conviction=0.9, change="A→B"),
    ]
    entries = prioritize(events, set())
    assert [e["event_class"] for e in entries] == [
        "stance_flip",
        "new_contradiction",
        "expired_invalidated",
        "new_high_conviction",
    ]


def test_conviction_desc_within_class(make_card):
    events = [
        _event(make_card, corp="00000001", ticker="000001",
               event_class="stance_flip", conviction=0.4, change="A→B"),
        _event(make_card, corp="00000002", ticker="000002",
               event_class="stance_flip", conviction=0.9, change="A→B"),
    ]
    entries = prioritize(events, set())
    assert [e["conviction"] for e in entries] == [0.9, 0.4]


def test_truncates_to_ten(make_card):
    events = [
        _event(make_card, corp=f"{i:08d}", ticker=f"{i:06d}",
               event_class="stance_flip", conviction=0.5, change="A→B")
        for i in range(1, 13)  # 12 candidate events
    ]
    entries = prioritize(events, set())
    assert len(entries) == 10


def test_no_portfolio():
    # portfolio.md is absent in this repo → the held tier collapses to set(), never crashes.
    held = load_held_tickers()
    assert held == set()


def test_no_portfolio_sort_still_deterministic(make_card):
    events = [
        _event(make_card, corp="00000002", ticker="000002",
               event_class="new_contradiction", conviction=0.5, change="+1 contradictions"),
        _event(make_card, corp="00000001", ticker="000001",
               event_class="stance_flip", conviction=0.5, change="A→B"),
    ]
    entries = prioritize(events, load_held_tickers())
    assert [e["ticker"] for e in entries] == ["000001", "000002"]
