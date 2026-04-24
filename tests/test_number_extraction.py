"""Tests for Stage 1 regex candidate extraction (D-15)."""

from __future__ import annotations

from pathlib import Path

from shared.number_extraction import (
    MAX_CANDIDATES_PER_DOC,
    extract_numeric_candidates,
)

FIXTURES = Path(__file__).parent / "fixtures" / "number_extraction"


def _read_body(name: str) -> str:
    raw = (FIXTURES / name).read_text(encoding="utf-8")
    # strip frontmatter
    _, _, body = raw.partition("---\n")
    _, _, body = body.partition("---\n")
    return body


def test_hankyung_compound_amount_extracted():
    body = _read_body("hankyung_sample.md")
    cands = extract_numeric_candidates(body, section_hint="news")
    spans = {c.raw_text for c in cands}
    assert "4조 2,000억 원" in spans
    assert "5.3%" in spans
    assert "15.2배" in spans
    assert "72,000원" in spans
    assert "100만 주" in spans


def test_hankyung_offsets_roundtrip():
    """Character offsets are codepoint-safe for Hangul (Pitfall 4)."""
    body = _read_body("hankyung_sample.md")
    cands = extract_numeric_candidates(body, section_hint="news")
    for c in cands:
        recovered = body[c.offset : c.offset + c.length]
        assert recovered == c.raw_text, (
            f"offset mismatch: expected {c.raw_text!r}, got {recovered!r}"
        )


def test_hankyung_guessed_units():
    body = _read_body("hankyung_sample.md")
    cands = extract_numeric_candidates(body, section_hint="news")
    by_text = {c.raw_text: c.guessed_unit for c in cands}
    assert by_text["4조 2,000억 원"] == "KRW조"
    assert by_text["5.3%"] == "pct"
    assert by_text["15.2배"] == "multiplier"
    assert by_text["100만 주"] == "shares"


def test_dart_narrative_units():
    body = _read_body("dart_narrative_sample.md")
    cands = extract_numeric_candidates(body, section_hint="dart")
    by_text = {c.raw_text: c.guessed_unit for c in cands}
    assert "12,345백만원" in by_text and by_text["12,345백만원"] == "KRW백만"
    assert "3,200억" in by_text and by_text["3,200억"] == "KRW억"
    assert "50bps" in by_text and by_text["50bps"] == "bps"


def test_context_and_sentence_populated():
    body = _read_body("hankyung_sample.md")
    cands = extract_numeric_candidates(body, section_hint="news")
    for c in cands:
        assert c.sentence_text  # non-empty
        # pre_context + raw_text + post_context should be a substring of sentence_text
        combined = c.pre_context + c.raw_text + c.post_context
        assert combined in c.sentence_text or c.raw_text in c.sentence_text


def test_candidate_overflow_trimmed():
    """Body with 200 numeric spans is trimmed to MAX_CANDIDATES_PER_DOC."""
    body = " ".join(f"{i}원" for i in range(200))
    cands = extract_numeric_candidates(body, section_hint="other")
    assert len(cands) <= MAX_CANDIDATES_PER_DOC


def test_empty_body_returns_empty_list():
    assert extract_numeric_candidates("", section_hint="news") == []
    assert extract_numeric_candidates("no numbers here 한글만", section_hint="news") == []
