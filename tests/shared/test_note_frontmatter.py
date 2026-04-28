"""Phase 6 Plan 06-02 Task 2: NoteFrontmatter Pydantic model tests (D-11)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.frontmatter import NoteFrontmatter


def test_f1_valid_with_type_and_tickers_autofills_dates() -> None:
    nf = NoteFrontmatter(type="thesis", tickers=["005930"])
    assert nf.type == "thesis"
    assert nf.tickers == ["005930"]
    # auto-filled (created/updated) — both are datetimes
    assert nf.created is not None
    assert nf.updated is not None


def test_f2_missing_type_raises() -> None:
    with pytest.raises(ValidationError):
        NoteFrontmatter(tickers=["005930"])  # type: ignore[call-arg]


def test_f3_conviction_score_within_bounds() -> None:
    nf = NoteFrontmatter(type="conviction", conviction_score=0.7)
    assert nf.conviction_score == 0.7


def test_conviction_score_out_of_bounds_rejected() -> None:
    with pytest.raises(ValidationError):
        NoteFrontmatter(type="conviction", conviction_score=1.5)
    with pytest.raises(ValidationError):
        NoteFrontmatter(type="conviction", conviction_score=-0.1)


def test_extra_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        NoteFrontmatter(type="note", foo="bar")  # type: ignore[call-arg]


def test_invalid_type_literal_rejected() -> None:
    with pytest.raises(ValidationError):
        NoteFrontmatter(type="invalid_kind")  # type: ignore[arg-type]


def test_default_author() -> None:
    nf = NoteFrontmatter(type="note")
    assert nf.author == "yamin"
