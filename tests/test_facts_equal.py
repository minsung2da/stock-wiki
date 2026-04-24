"""Tests for D-16 self-consistency comparator."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Import facts_equal from outside src/ (from .claude/routines/enrich/helpers/)
HELPER_PATH = Path(__file__).parent.parent / ".claude/routines/enrich/helpers/facts_equal.py"
spec = importlib.util.spec_from_file_location("facts_equal_mod", HELPER_PATH)
assert spec and spec.loader
facts_equal_mod = importlib.util.module_from_spec(spec)
sys.modules["facts_equal_mod"] = facts_equal_mod
spec.loader.exec_module(facts_equal_mod)
facts_equal = facts_equal_mod.facts_equal

from shared.frontmatter import DerivedBlock, NumericFact, SentimentBlock  # noqa: E402


def _d(**kwargs) -> DerivedBlock:
    return DerivedBlock(**kwargs)


def test_identical_blocks_equal():
    a = _d(
        tickers=["005930"],
        event_type="earnings_release",
        numeric_facts=[NumericFact(key="매출액", value=100.0, unit="KRW조")],
    )
    b = _d(
        tickers=["005930"],
        event_type="earnings_release",
        numeric_facts=[NumericFact(key="매출액", value=100.0, unit="KRW조")],
    )
    assert facts_equal(a, b)


def test_summary_difference_ignored():
    a = _d(summary="abc", tickers=["005930"])
    b = _d(summary="xyz", tickers=["005930"])
    assert facts_equal(a, b)


def test_rationale_difference_ignored():
    a = _d(sentiment=SentimentBlock(label="bullish", rationale="X"))
    b = _d(sentiment=SentimentBlock(label="bullish", rationale="Y"))
    assert facts_equal(a, b)


def test_event_type_difference_detected():
    a = _d(event_type="earnings_release")
    b = _d(event_type="equity_issue")
    assert not facts_equal(a, b)


def test_ticker_order_insensitive():
    a = _d(tickers=["005930", "000660"])
    b = _d(tickers=["000660", "005930"])
    assert facts_equal(a, b)


def test_sentiment_label_difference_detected():
    a = _d(sentiment=SentimentBlock(label="bullish"))
    b = _d(sentiment=SentimentBlock(label="bearish"))
    assert not facts_equal(a, b)


def test_numeric_fact_value_difference_detected():
    a = _d(numeric_facts=[NumericFact(key="매출액", value=100.0, unit="KRW조")])
    b = _d(numeric_facts=[NumericFact(key="매출액", value=101.0, unit="KRW조")])
    assert not facts_equal(a, b)


def test_numeric_fact_rounding_tolerance():
    a = _d(numeric_facts=[NumericFact(key="r", value=1.23456789, unit="pct")])
    b = _d(
        numeric_facts=[NumericFact(key="r", value=1.23454321, unit="pct")]
    )  # diff in 5th decimal
    assert facts_equal(a, b)  # round(_, 4) identical


def test_source_span_difference_ignored():
    a = _d(numeric_facts=[NumericFact(key="r", value=1.0, unit="pct", source_span="1%", offset=0)])
    b = _d(numeric_facts=[NumericFact(key="r", value=1.0, unit="pct", source_span=" 1%", offset=1)])
    assert facts_equal(a, b)
