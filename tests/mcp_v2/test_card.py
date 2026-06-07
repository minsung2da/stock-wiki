"""DB-marked tests for get_decision_card (Plan 03-04 Task 2, Veto #13).

Asserts the payload-default body_md exclusion (Veto #13), the view='both' D-03
wrap, the D-01 no-active-card empty model, and the InvalidArgument cases. Seeds a
real active card via ``cards.store.save_card`` into the same container the tool
reads through ``get_engine()`` (the session fixture sets ``DATABASE_URL``).
"""

from __future__ import annotations

import pytest

from cards import store
from cards.models import DecisionCard
from mcp_v2.errors import InvalidArgument
from mcp_v2.tools.card import get_decision_card

pytestmark = pytest.mark.db


# The redesign §3 card transcribed minimally (corp_code/ticker match the
# mcp_v2 seeded_engine entity). Carries a body_md so view='both' has something
# to wrap.
def _card_dict(card_id: str = "card_005930_t2") -> dict:
    return {
        "card_id": card_id,
        "corp_code": "00126380",
        "ticker": "005930",
        "generated_at": "2026-05-28T17:42+09:00",
        "as_of": "2026-05-28T16:00+09:00",
        "schema_version": 1,
        "decision": {
            "stance": "HOLD",
            "conviction": 0.55,
            "horizon_days": 30,
            "price_ref": 71200,
            "invalidation_triggers": ["HBM3E qual fails"],
        },
        "key_claims": [],
        "contradictions": [],
        "assumptions": ["DRAM ASP holds"],
        "numeric_facts": {},
        "evidence_weights": {},
        "guards_passed": [],
        "expires_at": "2026-06-15T00:00+09:00",
        "body_md": "# 삼성전자 (005930) — HOLD\n\nHBM3E qualification catalyst pending.\n",
    }


def _save(engine, card_dict: dict) -> None:
    store.save_card(engine, DecisionCard.model_validate(card_dict))


def test_view_payload_excludes_body_md(seeded_engine):
    """Veto #13: default view='payload' drops body_md from the card dict."""
    _save(seeded_engine, _card_dict())

    result = get_decision_card("00126380")  # default view

    assert result.found is True
    assert result.card is not None
    # Veto #13: NO body_md key in the payload projection.
    assert "body_md" not in result.card
    # but the payload fields ARE present
    assert result.card["card_id"] == "card_005930_t2"
    assert result.card["decision"]["stance"] == "HOLD"


def test_view_both_includes_wrapped_body(seeded_engine):
    """view='both' includes body_md wrapped in <untrusted source=card>."""
    _save(seeded_engine, _card_dict("card_005930_both"))

    result = get_decision_card("00126380", view="both")

    assert result.found is True
    assert result.card is not None
    body = result.card["body_md"]
    assert body.startswith('<untrusted source="card" ref="card_005930_both">')
    assert body.endswith("</untrusted>")
    # the original body content is preserved UNCHANGED inside the delimiter
    assert "HBM3E qualification catalyst pending." in body
    # clean body → no injection flag attached
    assert result.card["injection_suspected"] is False


def test_no_active_card_returns_found_false(seeded_engine):
    """D-01: no active card is a normal empty model, never raises."""
    result = get_decision_card("00126380")
    assert result.found is False
    assert result.card is None
    assert result.corp_code == "00126380"


def test_bad_corp_code_raises_invalid_argument(seeded_engine):
    with pytest.raises(InvalidArgument):
        get_decision_card("abc")
    with pytest.raises(InvalidArgument):
        get_decision_card("123")  # too short


def test_bad_view_raises_invalid_argument(seeded_engine):
    with pytest.raises(InvalidArgument):
        get_decision_card("00126380", view="full")
    with pytest.raises(InvalidArgument):
        get_decision_card("00126380", view="")
