"""Stage 4 of the D-15 numeric pipeline: echo-back + magnitude sanity.

Echo-back (D-15 stage 4a): verify LLM-provided source_span is a verbatim
substring at the claimed offset. Blocks hallucinated facts.

Sanity (D-18): declarative SANITY_RULES table of (key, unit, min, max).
Flags values outside common-sense ranges (e.g., 영업이익률 > 100%).

Pure functions, no I/O. Caller (Routines skill) maps returned flag strings
to ReviewFlag pydantic models.
"""

from __future__ import annotations

from typing import TypedDict

from shared.frontmatter import NumericFact


class SanityRule(TypedDict, total=False):
    unit: str  # expected NumericFact.unit
    min: float  # raw value min (non-KRW units)
    max: float
    min_krw: float  # for KRW-family, compared against value_krw
    max_krw: float


# Seed rules; grow as observations surface. Indexes (KOSPI/KOSDAQ) use the
# "other" unit because NumericFact.unit Literal does not include "index_pt".
SANITY_RULES: dict[str, SanityRule] = {
    # Income statement — value_krw required
    "매출액": {"unit": "KRW원", "min_krw": 1e8, "max_krw": 1e15},
    "영업이익": {"unit": "KRW원", "min_krw": -1e14, "max_krw": 1e14},
    "당기순이익": {"unit": "KRW원", "min_krw": -1e14, "max_krw": 1e14},
    # Balance sheet
    "자산총계": {"unit": "KRW원", "min_krw": 1e8, "max_krw": 1e16},
    "부채총계": {"unit": "KRW원", "min_krw": 0, "max_krw": 1e16},
    "자본총계": {"unit": "KRW원", "min_krw": -1e14, "max_krw": 1e16},
    # Ratios
    "영업이익률": {"unit": "pct", "min": -100, "max": 100},
    "순이익률": {"unit": "pct", "min": -100, "max": 100},
    "ROE": {"unit": "pct", "min": -200, "max": 200},
    "ROA": {"unit": "pct", "min": -100, "max": 100},
    "부채비율": {"unit": "pct", "min": 0, "max": 10000},
    "외국인지분율": {"unit": "pct", "min": 0, "max": 100},
    "PER": {"unit": "multiplier", "min": 0, "max": 1000},
    "PBR": {"unit": "multiplier", "min": 0, "max": 100},
    # YoY / QoQ growth
    "영업이익증가율_yoy": {"unit": "pct", "min": -1000, "max": 10000},
    "매출액증가율_yoy": {"unit": "pct", "min": -100, "max": 10000},
    # Prices
    "주가종가": {"unit": "KRW원", "min_krw": 1, "max_krw": 1e8},
    # Market indexes (unit="other" — see module note)
    "KOSPI": {"unit": "other", "min": 500, "max": 10000},
    "KOSDAQ": {"unit": "other", "min": 100, "max": 5000},
    # Macro
    "기준금리": {"unit": "pct", "min": 0, "max": 20},
    "USD_KRW": {"unit": "KRW원", "min_krw": 500, "max_krw": 3000},
    "US_10Y": {"unit": "pct", "min": 0, "max": 20},
    "WTI": {"unit": "USD", "min": 0, "max": 500},
}

assert len(SANITY_RULES) >= 20, "SANITY_RULES must seed at least 20 canonical keys (D-18)"


def check_echo_back(fact: NumericFact, body: str) -> str | None:
    """D-15 stage 4a: character-level echo-back verification.

    Returns:
        "numeric_echo_mismatch" if source_span is not the verbatim substring
        at the claimed offset. None if source_span/offset is absent (DART
        structured path per D-14) or match succeeds.

    Note: Python str slicing is codepoint-indexed — safe for Hangul (Pitfall 4).
    """
    if fact.source_span is None or fact.offset is None:
        return None
    end = fact.offset + len(fact.source_span)
    if fact.offset < 0 or end > len(body):
        return "numeric_echo_mismatch"
    if body[fact.offset : end] != fact.source_span:
        return "numeric_echo_mismatch"
    return None


def check_sanity(fact: NumericFact) -> str | None:
    """D-18 stage 4b: magnitude and unit-match sanity.

    Returns:
        "numeric_sanity_violation" on unit mismatch or out-of-range value.
        None for unknown keys (defensive pass — unknown is not an error).
    """
    rule = SANITY_RULES.get(fact.key)
    if rule is None:
        return None
    if rule.get("unit") != fact.unit:
        return "numeric_sanity_violation"
    # KRW-family check uses value_krw
    if "min_krw" in rule and "max_krw" in rule:
        v = fact.value_krw
        if v is None:
            return "numeric_sanity_violation"
        if v < rule["min_krw"] or v > rule["max_krw"]:
            return "numeric_sanity_violation"
        return None
    # Non-KRW scalar check
    if "min" in rule and "max" in rule and (fact.value < rule["min"] or fact.value > rule["max"]):
        return "numeric_sanity_violation"
    return None
