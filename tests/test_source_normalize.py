"""Tests for source-aware deterministic normalization (Phase 5.1).

Backs the two enforcement rules surfaced by the first Routine run:
1. macro/kind sentiment → null (D-13)
2. KRX tickers → seed from provenance.ticker
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HELPER_PATH = Path(__file__).parent.parent / ".claude/routines/enrich/helpers/source_normalize.py"
spec = importlib.util.spec_from_file_location("source_normalize_mod", HELPER_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules["source_normalize_mod"] = mod
spec.loader.exec_module(mod)
normalize_derived_for_source = mod.normalize_derived_for_source

from shared.frontmatter import (  # noqa: E402
    DerivedBlock,
    NumericFact,
    ProvenanceBlock,
    SentimentBlock,
)


def _provenance(source: str, ticker: str | None = None) -> ProvenanceBlock:
    return ProvenanceBlock(
        source=source,
        ticker=ticker,
        content_hash="0" * 64,
        date="2026-04-26",
        fetched_at="2026-04-26T00:00:00Z",
        lang="ko",
    )


def _sentiment(label: str = "bullish") -> SentimentBlock:
    return SentimentBlock(label=label, bullish_score=0.7)


# ---- D-13 sentiment-null enforcement ----


def test_macro_sentiment_stripped_to_none():
    derived = DerivedBlock(sentiment=_sentiment("neutral"))
    out = normalize_derived_for_source(derived, _provenance("macro"))
    assert out.sentiment is None


def test_kind_sentiment_stripped_to_none():
    derived = DerivedBlock(sentiment=_sentiment("bearish"))
    out = normalize_derived_for_source(derived, _provenance("kind", ticker="005930"))
    assert out.sentiment is None


def test_dart_sentiment_preserved():
    sent = _sentiment("bullish")
    derived = DerivedBlock(sentiment=sent)
    out = normalize_derived_for_source(derived, _provenance("dart"))
    assert out.sentiment is sent


def test_news_sentiment_preserved():
    sent = _sentiment("neutral")
    derived = DerivedBlock(sentiment=sent)
    out = normalize_derived_for_source(derived, _provenance("news"))
    assert out.sentiment is sent


def test_macro_with_already_null_sentiment_stays_null():
    derived = DerivedBlock(sentiment=None)
    out = normalize_derived_for_source(derived, _provenance("macro"))
    assert out.sentiment is None


# ---- KRX deterministic ticker seed ----


def test_krx_empty_tickers_seeded_from_provenance():
    derived = DerivedBlock(tickers=[])
    out = normalize_derived_for_source(derived, _provenance("krx", ticker="005930"))
    assert out.tickers == ["005930"]


def test_krx_existing_tickers_not_overwritten():
    derived = DerivedBlock(tickers=["999999"])
    out = normalize_derived_for_source(derived, _provenance("krx", ticker="005930"))
    assert out.tickers == ["999999"]


def test_krx_no_provenance_ticker_no_seed():
    derived = DerivedBlock(tickers=[])
    out = normalize_derived_for_source(derived, _provenance("krx", ticker=None))
    assert out.tickers == []


def test_dart_tickers_not_seeded():
    derived = DerivedBlock(tickers=[])
    out = normalize_derived_for_source(derived, _provenance("dart", ticker="005930"))
    assert out.tickers == []


# ---- Combined / idempotency ----


def test_macro_and_krx_rules_independent():
    """A macro doc with a ticker shouldn't trigger ticker seeding (only krx does)."""
    sent = _sentiment("neutral")
    derived = DerivedBlock(tickers=[], sentiment=sent)
    out = normalize_derived_for_source(derived, _provenance("macro", ticker="005930"))
    assert out.sentiment is None
    assert out.tickers == []


def test_normalize_is_idempotent():
    derived = DerivedBlock(tickers=[], sentiment=_sentiment("bearish"))
    prov = _provenance("macro")
    out1 = normalize_derived_for_source(derived, prov)
    out2 = normalize_derived_for_source(out1, prov)
    assert out1 is out2
    assert out2.sentiment is None


def test_other_fields_untouched():
    """numeric_facts, catalysts, summary, event_type must not change."""
    fact = NumericFact(key="자산총계", value=1000, unit="KRW원", value_krw=1000)
    derived = DerivedBlock(
        catalysts=["기준금리 인상"],
        numeric_facts=[fact],
        summary="원/달러 환율 안정세",
        sentiment=_sentiment("neutral"),
    )
    out = normalize_derived_for_source(derived, _provenance("macro"))
    assert out.catalysts == ["기준금리 인상"]
    assert out.numeric_facts == [fact]
    assert out.summary == "원/달러 환율 안정세"
    assert out.sentiment is None  # only this changed
