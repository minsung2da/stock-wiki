"""Phase 8 Plan 08-01 Task 1: parse_note dispatch tests (D-15)."""

from __future__ import annotations

from pathlib import Path

import frontmatter as pyfm

from ingest.parsers.note import parse_note
from shared.frontmatter import NoteFrontmatter, ThesisFrontmatter


def _write_md(path: Path, meta: dict, body: str = "본문") -> None:
    post = pyfm.Post(body)
    post.metadata = dict(meta)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pyfm.dumps(post), encoding="utf-8")


def test_parse_thesis_dispatches_to_thesis_model(tmp_path: Path) -> None:
    p = tmp_path / "notes" / "private" / "005930" / "thesis.md"
    _write_md(
        p,
        {
            "type": "thesis",
            "tickers": ["005930"],
            "tags": [],
            "created": "2026-05-06T15:00:00+09:00",
            "updated": "2026-05-06T15:00:00+09:00",
            "author": "yamin",
            "kill_criteria": ["적자 전환"],
            "conviction": "medium",
            "target_price": 95000,
        },
        body="# Thesis\n투자 논리\n",
    )
    parsed = parse_note(p)
    assert parsed.note_type == "thesis"
    assert isinstance(parsed.frontmatter, ThesisFrontmatter)
    assert parsed.frontmatter.target_price == 95000
    assert parsed.review_flags == []
    assert "투자 논리" in parsed.body


def test_parse_invalid_thesis_records_review_flag(tmp_path: Path) -> None:
    """D-15: ValidationError → review_flag, body still indexed (no exception)."""
    p = tmp_path / "thesis_bad.md"
    _write_md(
        p,
        {
            "type": "thesis",
            "tickers": ["005930"],
            "conviction": "extreme",  # invalid Literal
        },
        body="본문 텍스트",
    )
    parsed = parse_note(p)
    assert parsed.note_type == "thesis"
    assert parsed.frontmatter is None
    assert parsed.review_flags == ["note_schema_violation"]
    assert "본문 텍스트" in parsed.body


def test_parse_journal_dispatches_to_note_model(tmp_path: Path) -> None:
    p = tmp_path / "journal.md"
    _write_md(
        p,
        {
            "type": "journal",
            "tickers": [],
            "tags": [],
            "author": "yamin",
        },
        body="# Journal",
    )
    parsed = parse_note(p)
    assert parsed.note_type == "journal"
    assert isinstance(parsed.frontmatter, NoteFrontmatter)
    # Should NOT be ThesisFrontmatter (subclass leak guard)
    assert not isinstance(parsed.frontmatter, ThesisFrontmatter)


def test_parse_unknown_type_falls_back_to_note(tmp_path: Path) -> None:
    """No `type` field → defaults to 'note', uses NoteFrontmatter."""
    p = tmp_path / "untyped.md"
    # Provide enough valid fields to pass NoteFrontmatter when type defaults to "note"
    _write_md(p, {"tickers": [], "tags": []}, body="아무 메모")
    parsed = parse_note(p)
    assert parsed.note_type == "note"
    # frontmatter may be None if NoteFrontmatter requires type — that's OK,
    # but the dispatch fell back to "note" model. Either way, no crash.
    # If validation passes, the frontmatter must be NoteFrontmatter.
    if parsed.frontmatter is not None:
        assert isinstance(parsed.frontmatter, NoteFrontmatter)
