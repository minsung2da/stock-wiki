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


def test_unknown_field_does_not_crash_parse() -> None:
    """D-15 (Phase 8): NoteFrontmatter must allow extra keys so user free-form
    fields (e.g. ``mood``) do not crash ingest. Schema violations on KNOWN
    fields are caught downstream by ``parse_note`` and recorded as
    ``note_schema_violation`` review_flags (Pitfall 4 avoidance).
    """
    nf = NoteFrontmatter(type="note", mood="excited")  # type: ignore[call-arg]
    assert nf.type == "note"


def test_journal_uses_base_model() -> None:
    """D-13: journal type uses NoteFrontmatter directly (no thesis-only fields)."""
    nf = NoteFrontmatter(
        type="journal",
        tickers=[],
        tags=[],
        author="yamin",
    )
    assert nf.type == "journal"
    assert nf.author == "yamin"


def test_invalid_type_literal_rejected() -> None:
    with pytest.raises(ValidationError):
        NoteFrontmatter(type="invalid_kind")  # type: ignore[arg-type]


def test_default_author() -> None:
    nf = NoteFrontmatter(type="note")
    assert nf.author == "yamin"
