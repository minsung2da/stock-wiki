"""DecisionCard model unit tests: SC#3 round-trip + SC#5 hard-veto rejections.

Round-trip semantics (SC#3, OQ-3 / Pitfall #4) are SEMANTIC equality through
``model_dump(mode="json")`` — NOT byte-identical YAML. tz offsets and int-vs-float
must survive the dump/reparse cycle.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cards.models import DecisionCard


def test_round_trip(decision_card_yaml: dict) -> None:
    """SC#3: the §3 YAML validates and round-trips through model_dump(mode='json')."""
    card = DecisionCard.model_validate(decision_card_yaml)
    reparsed = DecisionCard.model_validate(card.model_dump(mode="json"))
    assert reparsed == card


def test_missing_expiry_rejected(decision_card_yaml: dict) -> None:
    """SC#5 (Veto #2): a card with no expires_at is rejected at the model boundary."""
    bad = {**decision_card_yaml}
    bad.pop("expires_at")
    with pytest.raises(ValidationError):
        DecisionCard.model_validate(bad)


def test_empty_assumptions_rejected(decision_card_yaml: dict) -> None:
    """SC#5 (Veto #2): a card with empty assumptions[] is rejected."""
    bad = {**decision_card_yaml, "assumptions": []}
    with pytest.raises(ValidationError):
        DecisionCard.model_validate(bad)


def test_extra_key_rejected(decision_card_yaml: dict) -> None:
    """ASVS V5 (T-02-04): an unknown top-level key is rejected (extra='forbid')."""
    bad = {**decision_card_yaml, "totally_unknown_field": "x"}
    with pytest.raises(ValidationError):
        DecisionCard.model_validate(bad)


def test_numeric_facts_types_preserved(decision_card_yaml: dict) -> None:
    """Pitfall #4: int stays int and float stays float across the round-trip."""
    card = DecisionCard.model_validate(decision_card_yaml)
    reparsed = DecisionCard.model_validate(card.model_dump(mode="json"))
    assert reparsed.numeric_facts["market_cap_krw"] == 425000000000000
    assert isinstance(reparsed.numeric_facts["market_cap_krw"], int)
    assert reparsed.numeric_facts["pe_ttm"] == 17.2
    assert isinstance(reparsed.numeric_facts["pe_ttm"], float)


def test_invalidation_reason_optional(decision_card_yaml: dict) -> None:
    """The optional invalidation_reason: defaults None, and a payload that DOES
    carry it validates under extra='forbid' (guards Plan 03 invalidate/walk reconstruct).
    """
    # (a) Fixture has no invalidation_reason key → defaults to None and round-trips.
    card = DecisionCard.model_validate(decision_card_yaml)
    assert card.invalidation_reason is None
    reparsed = DecisionCard.model_validate(card.model_dump(mode="json"))
    assert reparsed == card

    # (b) A payload that DOES include invalidation_reason (the post-jsonb_set shape
    # Plan 03 invalidate() produces) validates cleanly — extra='forbid' does NOT trip.
    with_reason = DecisionCard.model_validate(
        {**decision_card_yaml, "invalidation_reason": "expired thesis"}
    )
    assert with_reason.invalidation_reason == "expired thesis"
