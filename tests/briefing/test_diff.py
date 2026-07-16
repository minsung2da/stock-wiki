"""tests/briefing/test_diff.py — classify_change change detection (Task 1, D-02/D-03).

Pure logic over two ``DecisionCard`` objects (the D-02 supersession-chain baseline is
resolved by the Task-3 orchestrator; here we feed ``active`` + ``prior`` directly).
No DB fixture needed — ``make_card`` builds a valid card without persisting.
"""

from __future__ import annotations

from briefing.daily import classify_change


def _contra(bull: str, bear_claim: str) -> dict:
    return {
        "bull": bull,
        "bear_evidence": "bear evidence",
        "bear_claim": bear_claim,
        "resolution": "unresolved",
    }


def test_stance_flip_hold_over_sell(make_card):
    prior = make_card(
        corp_code="00000001", ticker="000001", stance="SELL", conviction=0.5, card_id="p1"
    )
    active = make_card(
        corp_code="00000001", ticker="000001", stance="HOLD", conviction=0.5, card_id="a1"
    )
    event = classify_change(active, prior)
    assert event is not None
    assert event.event_class == "stance_flip"
    assert event.change == "SELL→HOLD"


def test_new_contradictions_delta(make_card):
    prior = make_card(
        corp_code="00000001", ticker="000001", stance="HOLD", contradictions=[], card_id="p2"
    )
    active = make_card(
        corp_code="00000001",
        ticker="000001",
        stance="HOLD",
        contradictions=[_contra("b1", "bc1"), _contra("b2", "bc2")],
        card_id="a2",
    )
    event = classify_change(active, prior)
    assert event is not None
    assert event.event_class == "new_contradiction"
    assert event.change == "+2 contradictions"


def test_contradiction_delta_counts_only_new(make_card):
    shared = _contra("b1", "bc1")
    prior = make_card(
        corp_code="00000001",
        ticker="000001",
        stance="HOLD",
        contradictions=[shared],
        card_id="p4",
    )
    active = make_card(
        corp_code="00000001",
        ticker="000001",
        stance="HOLD",
        contradictions=[shared, _contra("b2", "bc2")],
        card_id="a4",
    )
    event = classify_change(active, prior)
    assert event is not None
    assert event.change == "+1 contradictions"


def test_first_card_rule(make_card):
    # D-03: a first-ever card counts only if conviction >= 0.8.
    high = make_card(corp_code="00000001", ticker="000001", stance="BUY", conviction=0.83)
    event = classify_change(high, None)
    assert event is not None
    assert event.event_class == "new_high_conviction"
    assert event.change == "new (conv 0.83)"

    low = make_card(corp_code="00000002", ticker="000002", stance="HOLD", conviction=0.5)
    assert classify_change(low, None) is None


def test_no_change_returns_none(make_card):
    contras = [_contra("b1", "bc1")]
    prior = make_card(
        corp_code="00000001",
        ticker="000001",
        stance="HOLD",
        conviction=0.6,
        contradictions=contras,
        card_id="p3",
    )
    active = make_card(
        corp_code="00000001",
        ticker="000001",
        stance="HOLD",
        conviction=0.6,
        contradictions=contras,
        card_id="a3",
    )
    assert classify_change(active, prior) is None
