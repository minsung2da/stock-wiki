"""Tests for D-15 stage 4 (echo-back) + D-18 (sanity rules)."""

from __future__ import annotations

from shared.frontmatter import NumericFact
from shared.number_sanity import SANITY_RULES, check_echo_back, check_sanity


# --- echo-back ---
def test_hallucinated_fact_flagged():
    body = "매출액은 4조 원이다."
    fact = NumericFact(
        key="매출액",
        value=5.0,
        unit="KRW조",
        source_span="5조 원",
        offset=4,  # offset points to "4조 원", not "5조 원"
    )
    assert check_echo_back(fact, body) == "numeric_echo_mismatch"


def test_echo_match_passes():
    body = "매출액은 4조 원이다."
    # body[4:4+len("4조 원")] == "4조 원"
    fact = NumericFact(
        key="매출액",
        value=4.0,
        unit="KRW조",
        source_span="4조 원",
        offset=4,
    )
    assert check_echo_back(fact, body) is None


def test_dart_structured_skipped():
    """source_span=None means DART structured path (D-14) — no echo check needed."""
    fact = NumericFact(key="매출액", value=65e12, unit="KRW원", value_krw=65e12)
    body = "irrelevant body"
    assert check_echo_back(fact, body) is None


def test_echo_out_of_bounds_flagged():
    body = "짧다"
    fact = NumericFact(
        key="매출액",
        value=1.0,
        unit="KRW조",
        source_span="4조 원",
        offset=100,  # far out of range
    )
    assert check_echo_back(fact, body) == "numeric_echo_mismatch"


# --- sanity ---
def test_sanity_out_of_range():
    fact = NumericFact(key="영업이익률", value=500.0, unit="pct")
    assert check_sanity(fact) == "numeric_sanity_violation"


def test_sanity_in_range():
    fact = NumericFact(key="영업이익률", value=15.0, unit="pct")
    assert check_sanity(fact) is None


def test_unit_mismatch_flagged():
    """Rule says PER is multiplier; LLM gave KRW원."""
    fact = NumericFact(key="PER", value=15.0, unit="KRW원", value_krw=15.0)
    assert check_sanity(fact) == "numeric_sanity_violation"


def test_unknown_key_passes():
    fact = NumericFact(key="foo_bar_ratio", value=9999.0, unit="pct")
    assert check_sanity(fact) is None


def test_krw_without_value_krw_flagged():
    """KRW-family rule requires populated value_krw."""
    fact = NumericFact(key="매출액", value=65.0, unit="KRW원", value_krw=None)
    assert check_sanity(fact) == "numeric_sanity_violation"


def test_krw_in_range():
    fact = NumericFact(key="매출액", value=65e12, unit="KRW원", value_krw=65e12)
    assert check_sanity(fact) is None


def test_kospi_out_of_range():
    # NumericFact.unit Literal doesn't include "index_pt"; KOSPI rule uses "other"
    fact = NumericFact(key="KOSPI", value=50000.0, unit="other")
    assert check_sanity(fact) == "numeric_sanity_violation"


def test_seed_size():
    assert len(SANITY_RULES) >= 20


def test_foreign_exchange_rule():
    """USD_KRW sanity rule exists and validates."""
    fact = NumericFact(key="USD_KRW", value=1400.0, unit="KRW원", value_krw=1400.0)
    assert check_sanity(fact) is None
    bad = NumericFact(key="USD_KRW", value=5000.0, unit="KRW원", value_krw=5000.0)
    assert check_sanity(bad) == "numeric_sanity_violation"
