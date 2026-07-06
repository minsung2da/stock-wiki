"""Judge rubric → conviction(0-1) + stance mapping (Discretion #1, Veto #4/#5).

Pure Python. No LLM, no I/O.

Two deterministic transforms turn the Judge's cited subscores into the numeric card
fields, keeping both auditable so any conviction/stance is REPRODUCIBLE from cited
inputs (Veto #4 — no black-box score):

- :func:`score_to_conviction` — ``clamp(Σ wᵢ·scoreᵢ / (10·Σwᵢ), 0, 1)`` over the five
  :data:`RUBRIC_WEIGHTS` axes, where the ``contradiction_penalty`` axis contributes
  NEGATIVELY, followed by the Veto #5 HARD CAP applied HERE in Python (never in a
  prompt): a conviction that would land ≥ 0.8 is clamped just below 0.8 unless the
  cited evidence carries ≥2 independent HIGH/MEDIUM refs spanning ≥2 corroborating
  source families (DART/KRX/macro/news/user_thesis). Sentiment is NOT a corroborating
  family, so sentiment-only support can never reach 0.8.
- :func:`derive_stance` — a pure table lookup over :data:`STANCE_TABLE` mapping the net
  Bull−Bear strength (bucketed) and current-holding to one of the six DecisionCard
  stances, with a sign guard so a constructive BUY/ADD is not issued when both the
  fundamentals and catalyst signs are negative.

The weights and stance table are ``[ASSUMED]`` defaults (RESEARCH A1) to be tuned in
Phase 8 eval; they live at module level precisely so that tuning is a one-line audit.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

__all__ = [
    "RUBRIC_WEIGHTS",
    "STANCE_TABLE",
    "CORROBORATING_FAMILIES",
    "score_to_conviction",
    "derive_stance",
]

# ---------------------------------------------------------------------------
# Rubric weights (RESEARCH Discretion #1, [ASSUMED] — tune in Phase 8). The
# ``contradiction_penalty`` axis subtracts; every other axis adds. Σ weights = 1.0.
# ---------------------------------------------------------------------------
RUBRIC_WEIGHTS: Mapping[str, float] = MappingProxyType(
    {
        "fundamentals": 0.30,
        "catalyst": 0.25,
        "freshness": 0.20,
        "sizing": 0.15,
        "contradiction_penalty": 0.10,  # NEGATIVE contribution
    }
)

# The one axis whose score subtracts from conviction.
_PENALTY_AXIS = "contradiction_penalty"

# Score scale each axis is graded on (0-10). Denominator uses this so a full-10 axis
# contributes its full weight.
_SCORE_MAX = 10.0

# Veto #5: a conviction at/above this threshold requires multi-source corroboration.
_VETO5_THRESHOLD = 0.8
# When the cap fires, conviction is pinned JUST below the threshold (not zeroed — the
# thesis may be strong, it simply cannot be *certified* ≥0.8 on thin corroboration).
_VETO5_CAP = 0.79

# Evidence weights that count toward corroboration, and the source families that count
# as *independent* (Veto #5). Sentiment is deliberately excluded — it can never
# corroborate a thesis to ≥0.8 on its own.
_CORROBORATING_WEIGHTS = frozenset({"HIGH", "MEDIUM"})
CORROBORATING_FAMILIES: frozenset[str] = frozenset(
    {"DART", "KRX", "macro", "news", "user_thesis"}
)


def _multi_source_corroborated(evidence_refs: list[dict]) -> bool:
    """True iff ≥2 independent HIGH/MEDIUM refs span ≥2 corroborating source families.

    Only HIGH/MEDIUM refs from a recognized corroborating family count; sentiment and
    LOW/CONTEXT refs are ignored. This is the Veto #5 gate.
    """
    strong = [
        r
        for r in evidence_refs
        if r.get("weight") in _CORROBORATING_WEIGHTS
        and r.get("family") in CORROBORATING_FAMILIES
    ]
    families = {r["family"] for r in strong}
    return len(strong) >= 2 and len(families) >= 2


def score_to_conviction(
    subscores: dict[str, float],
    *,
    evidence_refs: list[dict],
) -> float:
    """Map rubric subscores → conviction in ``[0, 1]`` (Veto #4 decomposable, Veto #5 cap).

    ``subscores`` maps each :data:`RUBRIC_WEIGHTS` axis to a 0-10 score (a missing axis
    defaults to 0.0). The raw conviction is
    ``clamp(Σ wᵢ·scoreᵢ / (10·Σwᵢ), 0, 1)`` with the ``contradiction_penalty`` axis
    subtracting. If the raw value would be ≥ 0.8 but ``evidence_refs`` do NOT satisfy
    :func:`_multi_source_corroborated`, the result is capped to just below 0.8 (Veto #5,
    enforced in Python — never in a prompt). The output is a pure, reproducible function
    of ``subscores`` + :data:`RUBRIC_WEIGHTS` (Veto #4 — no black-box).
    """
    total_w = sum(RUBRIC_WEIGHTS.values())
    weighted = 0.0
    for axis, weight in RUBRIC_WEIGHTS.items():
        score = float(subscores.get(axis, 0.0))
        if axis == _PENALTY_AXIS:
            weighted -= weight * score
        else:
            weighted += weight * score
    raw = weighted / (_SCORE_MAX * total_w)
    conviction = min(1.0, max(0.0, raw))
    if conviction >= _VETO5_THRESHOLD and not _multi_source_corroborated(evidence_refs):
        return _VETO5_CAP
    return conviction


# ---------------------------------------------------------------------------
# Stance table (RESEARCH Discretion #1, [ASSUMED]). Keyed on (net-strength bucket,
# currently_held) → a DecisionCard-valid stance. Auditable at module level so any
# stance is reproducible from its cited inputs (Veto #4).
# ---------------------------------------------------------------------------
STANCE_TABLE: Mapping[tuple[str, bool], str] = MappingProxyType(
    {
        # (net bucket, currently_held): stance
        ("strong_pos", False): "BUY",
        ("strong_pos", True): "ADD",
        ("weak_pos", False): "BUY",
        ("weak_pos", True): "ADD",
        ("neutral", False): "HOLD",
        ("neutral", True): "HOLD",
        ("weak_neg", False): "AVOID",
        ("weak_neg", True): "TRIM",
        ("strong_neg", False): "AVOID",
        ("strong_neg", True): "SELL",
    }
)

# Net Bull−Bear strength thresholds that define the buckets above.
_STRONG_POS = 0.5
_WEAK_POS = 0.15
_WEAK_NEG = -0.15
_STRONG_NEG = -0.5


def _net_bucket(net: float) -> str:
    """Bucket the net (bull_strength − bear_strength) into one of five strength bands."""
    if net >= _STRONG_POS:
        return "strong_pos"
    if net >= _WEAK_POS:
        return "weak_pos"
    if net > _WEAK_NEG:
        return "neutral"
    if net > _STRONG_NEG:
        return "weak_neg"
    return "strong_neg"


def derive_stance(
    bull_strength: float,
    bear_strength: float,
    fundamentals_sign: float,
    catalyst_sign: float,
    *,
    currently_held: bool,
) -> str:
    """Map debate strengths + signs → a DecisionCard stance (pure :data:`STANCE_TABLE` lookup).

    ``net = bull_strength − bear_strength`` is bucketed and looked up against
    :data:`STANCE_TABLE` together with ``currently_held``. A constructive BUY/ADD is then
    downgraded to HOLD when BOTH ``fundamentals_sign`` and ``catalyst_sign`` are negative
    (the Bull may have out-argued the Bear, but with no fundamental or catalyst support a
    fresh buy is not warranted). Always returns one of BUY/ADD/HOLD/TRIM/SELL/AVOID.
    """
    net = bull_strength - bear_strength
    stance = STANCE_TABLE[(_net_bucket(net), currently_held)]
    if stance in ("BUY", "ADD") and fundamentals_sign < 0 and catalyst_sign < 0:
        return "HOLD"
    return stance
