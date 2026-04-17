"""Tests for src/ingest/chunking.py + src/ingest/parsers/dart.py (D-05/D-07/D-08)."""

from __future__ import annotations

import pytest

from ingest import chunking
from ingest.chunking import chunk_document
from ingest.parsers import parse_sections
from ingest.parsers.dart import Section


class _DummyTok:
    """Fake BAAI/bge-m3 tokenizer stand-in for deterministic, fast tests.

    encode(text) returns one ID per character; decode(ids) echoes a string of
    the same length so chunking math can be verified without a real model.
    """

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        return list(range(len(text)))

    def decode(self, ids: list[int]) -> str:
        return "x" * len(ids)


@pytest.fixture(autouse=True)
def _fake_tok(monkeypatch):
    monkeypatch.setattr(chunking, "_get_tok", lambda: _DummyTok())


# ---------- Chunking tests ----------


def test_chunk_single_short_section() -> None:
    sec = Section(title="A", path="A", text="x" * 200, order=0)
    chunks = chunk_document([sec])
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].section_index == 0
    assert chunks[0].section_path == "A"


def test_chunk_long_section_splits() -> None:
    sec = Section(title="A", path="A", text="x" * 3000, order=0)
    chunks = chunk_document([sec], max_tokens=1500, win=512, overlap=64)
    assert len(chunks) >= 5
    # section_index starts at 0 and is monotonic within the section
    sec_idxs = [c.section_index for c in chunks]
    assert sec_idxs[0] == 0
    assert sec_idxs == sorted(sec_idxs)
    # chunk_index monotonic
    chunk_idxs = [c.chunk_index for c in chunks]
    assert chunk_idxs == list(range(len(chunks)))


def test_multiple_sections_chunk_index_monotonic() -> None:
    sections = [
        Section(title="A", path="A", text="x" * 500, order=0),
        Section(title="B", path="B", text="x" * 2000, order=1),
        Section(title="C", path="C", text="x" * 800, order=2),
    ]
    chunks = chunk_document(sections, max_tokens=1500, win=512, overlap=64)
    # chunk_index monotonic per document (no reset)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    # section_index resets at each new section — group by section_path
    by_path: dict[str | None, list[int]] = {}
    for c in chunks:
        by_path.setdefault(c.section_path, []).append(c.section_index or 0)
    for path, idxs in by_path.items():
        assert idxs[0] == 0, f"section {path} should start at 0"
        assert idxs == sorted(idxs)


def test_section_path_preserved() -> None:
    sec = Section(title="T", path="I. Root/1. Child", text="x" * 2000, order=0)
    chunks = chunk_document([sec], max_tokens=1500, win=512, overlap=64)
    for c in chunks:
        assert c.section_path == "I. Root/1. Child"


# ---------- DART parser tests ----------


def test_dart_major_event_single_section() -> None:
    short_body = "2026년 1분기 실적 발표. 매출액 74.9조원."
    sections = parse_sections(short_body, "dart")
    assert len(sections) == 1
    assert sections[0].title == "(root)"
    assert sections[0].path == "(root)"
    assert sections[0].order == 0


def test_dart_regular_report_splits_by_toc() -> None:
    body = (
        "I. 회사의 개요\n"
        "1. 회사의 개요\n"
        "삼성전자 주식회사는 ...\n"
        "2. 회사의 연혁\n"
        "1969년 설립 ...\n"
        "II. 사업의 내용\n"
        "1. 사업의 개요\n"
        "반도체, 모바일, 가전 ...\n"
    )
    sections = parse_sections(body, "dart")
    assert len(sections) >= 2
    # At least one Section.path contains a hierarchical join via "/"
    assert any("/" in s.path for s in sections)


def test_parse_unknown_source_raises() -> None:
    with pytest.raises(ValueError):
        parse_sections("body text", "unsupported_source")


def test_parse_unknown_source_no_info_leak() -> None:
    # Info-disclosure guard T-3-15: the bad source value must not appear
    # in the error message.
    secret_source = "bad-source-DEADBEEF"
    try:
        parse_sections("x", secret_source)
    except ValueError as e:
        assert secret_source not in str(e)
