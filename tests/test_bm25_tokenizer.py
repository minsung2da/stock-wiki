"""Tests for src/ingest/tokenizer.py (mecab-ko → int32 IDs, D-12, INGEST-11)."""

from __future__ import annotations

from ingest.tokenizer import tokenize_ko


def test_tokenize_ko_emits_int_list() -> None:
    ids = tokenize_ko("삼성전자 2026년 매출 증가")
    assert isinstance(ids, list)
    assert len(ids) > 0
    for i in ids:
        assert isinstance(i, int)
        assert 0 <= i < 2**31


def test_tokenize_ko_deterministic() -> None:
    text = "삼성전자 반도체 부문 실적 개선"
    assert tokenize_ko(text) == tokenize_ko(text)


def test_tokenize_ko_content_only() -> None:
    # In a real sentence, josa/endings are correctly POS-tagged (JKG/JX/EC/EP)
    # and filtered out. Content nouns from a pared-down variant must all
    # appear in the full-sentence tokenization.
    full = tokenize_ko("삼성전자의 실적은 증가하였다")
    content_only = tokenize_ko("삼성전자 실적 증가")
    # Every content-noun ID from the stripped version is present in the full
    # sentence tokenization — proves josa filtering does not drop nouns.
    assert set(content_only).issubset(set(full))
    # And the full tokenization contains no more than a handful of tokens
    # above the content-only baseline (VV/XSV stems may add a little noise
    # but josa/endings should not inflate the set).
    assert len(full) <= len(content_only) + 2


def test_tokenize_ko_empty_returns_empty() -> None:
    assert tokenize_ko("") == []


def test_tokenize_ko_query_matches_index() -> None:
    # D-12: query uses the same pipeline as index. A query term that appears
    # verbatim in a document must produce at least one overlapping token ID.
    doc = "삼성전자 2026년 1분기 실적 발표"
    q = "삼성전자 실적"
    doc_ids = tokenize_ko(doc)
    q_ids = tokenize_ko(q)
    assert len(set(doc_ids) & set(q_ids)) >= 2
