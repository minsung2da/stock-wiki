"""Tests for analysis.rubric — decomposable conviction + Veto #5 cap + stance table.

Pure-function table tests (analog: tests/test_units.py). No DB, no LLM. These lock the
Veto #4 (conviction is a reproducible function of cited subscores + module-level weights)
and Veto #5 (no ≥0.8 without ≥2 independent HIGH/MEDIUM refs across ≥2 source families)
guarantees so the Wave-3 runner can consume them without re-deriving the veto logic.
"""

from __future__ import annotations

import pytest

from analysis import rubric
from cards.models import Decision

# --- helpers ---------------------------------------------------------------

_ALL_STANCES = set(Decision.model_fields["stance"].annotation.__args__)  # BUY/ADD/…

_ALL_AXES = {
    "fundamentals": 10.0,
    "catalyst": 10.0,
    "freshness": 10.0,
    "sizing": 10.0,
    "contradiction_penalty": 10.0,
}
_MAX_POS = {  # positive axes maxed, zero contradiction penalty → best case
    "fundamentals": 10.0,
    "catalyst": 10.0,
    "freshness": 10.0,
    "sizing": 10.0,
    "contradiction_penalty": 0.0,
}


def _strong_refs() -> list[dict]:
    """2 independent HIGH refs across 2 corroborating source families (Veto #5 satisfied)."""
    return [
        {"weight": "HIGH", "family": "DART"},
        {"weight": "HIGH", "family": "KRX"},
    ]


def _single_high_ref() -> list[dict]:
    """1 HIGH ref, single family — cannot satisfy the Veto #5 multi-source cap."""
    return [{"weight": "HIGH", "family": "DART"}]


# --- weight table ----------------------------------------------------------


def test_weights_are_the_five_assumed_axes():
    assert set(rubric.RUBRIC_WEIGHTS) == {
        "fundamentals",
        "catalyst",
        "freshness",
        "sizing",
        "contradiction_penalty",
    }
    assert rubric.RUBRIC_WEIGHTS["fundamentals"] == pytest.approx(0.30)
    assert rubric.RUBRIC_WEIGHTS["contradiction_penalty"] == pytest.approx(0.10)


# --- score_to_conviction ---------------------------------------------------


def test_all_zero_subscores_is_zero_conviction():
    assert rubric.score_to_conviction(
        dict.fromkeys(_ALL_AXES, 0.0), evidence_refs=_strong_refs()
    ) == pytest.approx(0.0)


def test_max_positive_no_penalty_is_near_one():
    # positive axes maxed, no contradictions → the top of the scale ("near 1.0").
    conv = rubric.score_to_conviction(_MAX_POS, evidence_refs=_strong_refs())
    assert conv >= 0.85


def test_all_ten_with_multisource_reaches_08():
    # {all 10} with 2×HIGH across 2 families → ≥ 0.8 (acceptance criterion 1).
    conv = rubric.score_to_conviction(_ALL_AXES, evidence_refs=_strong_refs())
    assert conv >= 0.8


def test_all_ten_single_high_is_capped_below_08():
    # Same subscores, only 1 HIGH ref → Veto #5 cap fires → strictly below 0.8.
    conv = rubric.score_to_conviction(_ALL_AXES, evidence_refs=_single_high_ref())
    assert conv < 0.8


def test_single_family_is_capped_below_08():
    # 2 HIGH refs but from the SAME family → not multi-source → capped.
    same_family = [
        {"weight": "HIGH", "family": "DART"},
        {"weight": "HIGH", "family": "DART"},
    ]
    assert rubric.score_to_conviction(_ALL_AXES, evidence_refs=same_family) < 0.8


def test_sentiment_only_can_never_reach_08():
    # Sentiment is NOT a corroborating family (Veto #5) — even many HIGH sentiment refs
    # cannot lift conviction to 0.8.
    sentiment_refs = [
        {"weight": "HIGH", "family": "sentiment"},
        {"weight": "HIGH", "family": "sentiment"},
        {"weight": "HIGH", "family": "sentiment"},
    ]
    assert rubric.score_to_conviction(_ALL_AXES, evidence_refs=sentiment_refs) < 0.8


def test_contradiction_penalty_strictly_lowers_conviction():
    # Strong corroboration + mid scores keeps raw < 0.8 so the cap never flattens the
    # sweep — conviction must strictly decrease as the penalty subscore rises.
    refs = _strong_refs()
    prev = None
    for pen in (0.0, 2.0, 5.0, 8.0, 10.0):
        sub = {
            "fundamentals": 6.0,
            "catalyst": 6.0,
            "freshness": 6.0,
            "sizing": 6.0,
            "contradiction_penalty": pen,
        }
        conv = rubric.score_to_conviction(sub, evidence_refs=refs)
        if prev is not None:
            assert conv < prev, (pen, conv, prev)
        prev = conv


def test_conviction_is_decomposable_from_subscores_and_weights():
    # Veto #4: reproduce the number by hand from RUBRIC_WEIGHTS (no black box).
    sub = {
        "fundamentals": 7.0,
        "catalyst": 5.0,
        "freshness": 4.0,
        "sizing": 6.0,
        "contradiction_penalty": 3.0,
    }
    w = rubric.RUBRIC_WEIGHTS
    numerator = (
        w["fundamentals"] * sub["fundamentals"]
        + w["catalyst"] * sub["catalyst"]
        + w["freshness"] * sub["freshness"]
        + w["sizing"] * sub["sizing"]
        - w["contradiction_penalty"] * sub["contradiction_penalty"]
    )
    expected = numerator / (10.0 * sum(w.values()))
    # raw is well below 0.8 here, so the cap does not apply.
    assert rubric.score_to_conviction(sub, evidence_refs=_strong_refs()) == pytest.approx(expected)


def test_conviction_clamped_to_unit_interval():
    conv = rubric.score_to_conviction(_MAX_POS, evidence_refs=_strong_refs())
    assert 0.0 <= conv <= 1.0
    zero = rubric.score_to_conviction(dict.fromkeys(_ALL_AXES, 0.0), evidence_refs=[])
    assert 0.0 <= zero <= 1.0


def test_missing_axis_defaults_to_zero():
    # A subscore dict missing an axis is treated as 0 for that axis (defensive).
    partial = {"fundamentals": 10.0}
    full = {**dict.fromkeys(_ALL_AXES, 0.0), "fundamentals": 10.0}
    assert rubric.score_to_conviction(partial, evidence_refs=[]) == pytest.approx(
        rubric.score_to_conviction(full, evidence_refs=[])
    )


# --- derive_stance ---------------------------------------------------------


def test_derive_stance_always_returns_valid_stance():
    for bull in (0.0, 0.3, 0.6, 0.9, 1.0):
        for bear in (0.0, 0.3, 0.6, 0.9, 1.0):
            for fsign in (-1.0, 0.0, 1.0):
                for csign in (-1.0, 0.0, 1.0):
                    for held in (True, False):
                        s = rubric.derive_stance(
                            bull, bear, fsign, csign, currently_held=held
                        )
                        assert s in _ALL_STANCES, (bull, bear, fsign, csign, held, s)


def test_derive_stance_strong_bull_buys_when_not_held():
    assert (
        rubric.derive_stance(1.0, 0.0, 1.0, 1.0, currently_held=False) == "BUY"
    )


def test_derive_stance_strong_bull_adds_when_held():
    assert rubric.derive_stance(1.0, 0.0, 1.0, 1.0, currently_held=True) == "ADD"


def test_derive_stance_strong_bear_sells_when_held():
    assert rubric.derive_stance(0.0, 1.0, -1.0, -1.0, currently_held=True) == "SELL"


def test_derive_stance_strong_bear_avoids_when_not_held():
    assert rubric.derive_stance(0.0, 1.0, -1.0, -1.0, currently_held=False) == "AVOID"


def test_derive_stance_balanced_is_hold():
    assert rubric.derive_stance(0.5, 0.5, 0.0, 0.0, currently_held=False) == "HOLD"


def test_derive_stance_buy_downgraded_when_signs_negative():
    # Bull "wins" the debate but both fundamentals AND catalyst are negative → not a
    # constructive buy; downgrade to HOLD (uses the sign inputs, not just net strength).
    assert (
        rubric.derive_stance(1.0, 0.0, -1.0, -1.0, currently_held=False) == "HOLD"
    )
