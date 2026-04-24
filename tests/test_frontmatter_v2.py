"""Phase 5 DerivedBlock v2 schema tests (additive, backwards-compatible)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.frontmatter import (
    DerivedBlock,
    FrontMatter,
    IngestStateBlock,
    NumericFact,
    ProvenanceBlock,
    ReviewFlag,
    SentimentBlock,
    read_frontmatter,
    write_frontmatter,
)


def _prov() -> ProvenanceBlock:
    return ProvenanceBlock(source="news", content_hash="a" * 64, lang="ko")


def test_round_trip_v2_full_shape(tmp_path):
    """Full v2 DerivedBlock round-trips through write/read_frontmatter."""
    fm_model = FrontMatter(
        provenance=_prov(),
        ingest_state=IngestStateBlock(),
        derived=DerivedBlock(
            tickers=["005930"],
            event_type="earnings_release",
            catalysts=["어닝 서프라이즈"],
            sentiment=SentimentBlock(
                label="bullish",
                bullish_score=0.72,
                rationale="영업이익 전년비 증가",
                scope="outcome",
            ),
            numeric_facts=[
                NumericFact(
                    key="영업이익",
                    value=4.2,
                    unit="KRW조",
                    value_krw=4.2e12,
                    source_span="4조 2,000억 원",
                    offset=45,
                ),
            ],
            summary="삼성전자 4Q 어닝 서프라이즈",
            review_flags=[ReviewFlag(flag="self_inconsistent", detail="demo", fact_key="영업이익")],
            skip_reason=None,
        ),
    )
    path = tmp_path / "doc.md"
    write_frontmatter(str(path), fm_model, "body text")
    round_tripped, body = read_frontmatter(str(path))
    assert body.strip() == "body text"
    assert round_tripped.model_dump(by_alias=True, exclude_none=True) == fm_model.model_dump(
        by_alias=True, exclude_none=True
    )


def test_legacy_phase3_shape_still_validates(tmp_path):
    """Legacy YAML (no review_flags / no skip_reason / minimal NumericFact+SentimentBlock) loads."""
    path = tmp_path / "legacy.md"
    path.write_text(
        "---\n"
        "provenance:\n"
        "  source: news\n"
        "  content_hash: " + "b" * 64 + "\n"
        "  lang: ko\n"
        "ingest_state: {}\n"
        "_derived:\n"
        '  tickers: ["000660"]\n'
        "  event_type: earnings_release\n"
        "  sentiment:\n"
        "    label: neutral\n"
        "    bullish_score: 0.5\n"
        "  numeric_facts:\n"
        "    - key: 매출액\n"
        "      value: 100.0\n"
        "      unit: KRW조\n"
        "---\nbody\n",
        encoding="utf-8",
    )
    model, _ = read_frontmatter(str(path))
    assert model.derived.review_flags == []
    assert model.derived.skip_reason is None
    assert model.derived.numeric_facts[0].value_krw is None


def test_unknown_event_type_rejected():
    with pytest.raises(ValidationError):
        DerivedBlock(event_type="foo_bar")


def test_unknown_sentiment_label_rejected():
    with pytest.raises(ValidationError):
        SentimentBlock(label="mildly_bullish")


def test_free_string_unit_rejected():
    with pytest.raises(ValidationError):
        NumericFact(key="x", value=1.0, unit="KRW")


def test_review_flag_unknown_rejected():
    with pytest.raises(ValidationError):
        ReviewFlag(flag="bogus", detail="x")


def test_review_flag_valid_all_nine():
    for flag in (
        "numeric_echo_mismatch",
        "numeric_sanity_violation",
        "dart_structured_disagreement",
        "self_inconsistent",
        "oversize_skipped",
        "prompt_injection_suspected",
        "sentiment_score_label_mismatch",
        "agent_zone_violation",
        "merge_conflict",
    ):
        ReviewFlag(flag=flag, detail="ok")  # must not raise


def test_skip_reason_literal():
    DerivedBlock(skip_reason="oversize")  # ok
    with pytest.raises(ValidationError):
        DerivedBlock(skip_reason="later")
