"""Phase 8 Plan 08-01 Task 1: ThesisFrontmatter Pydantic model tests (D-13)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.frontmatter import ThesisFrontmatter


def test_valid_thesis_parses() -> None:
    """D-13: thesis frontmatter with all fields parses + round-trips."""
    data = {
        "type": "thesis",
        "tickers": ["005930"],
        "tags": [],
        "created": "2026-05-06T15:00:00+09:00",
        "updated": "2026-05-06T15:00:00+09:00",
        "author": "yamin",
        "kill_criteria": ["분기 영업이익 -50%"],
        "conviction": "medium",
        "target_price": 95000,
    }
    tf = ThesisFrontmatter.model_validate(data)
    assert tf.type == "thesis"
    assert tf.tickers == ["005930"]
    assert tf.kill_criteria == ["분기 영업이익 -50%"]
    assert tf.conviction == "medium"
    assert tf.target_price == 95000
    assert tf.author == "yamin"


def test_conviction_literal_enforced() -> None:
    """D-13: conviction must be one of low/medium/high."""
    with pytest.raises(ValidationError):
        ThesisFrontmatter.model_validate(
            {"type": "thesis", "tickers": ["005930"], "conviction": "extreme"}
        )


def test_target_price_nullable() -> None:
    """D-13: target_price is Optional[int]."""
    tf = ThesisFrontmatter.model_validate(
        {"type": "thesis", "tickers": ["005930"], "target_price": None}
    )
    assert tf.target_price is None


def test_kill_criteria_default_empty_list() -> None:
    """D-13: kill_criteria defaults to []."""
    tf = ThesisFrontmatter.model_validate(
        {"type": "thesis", "tickers": ["005930"]}
    )
    assert tf.kill_criteria == []
