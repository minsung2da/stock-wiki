"""Tests for the mcp_v2 leaf utilities ported in Plan 03-02 Task 1.

These do NOT touch the DB and do NOT load bge-m3 (the embedder import only reads
the version constant; the model weights are never constructed here). Run with:

    .venv/Scripts/python.exe -m pytest tests/mcp_v2/test_tokenizer.py -x -q
"""

from __future__ import annotations

from mcp_v2.tokenizer import tokenize_ko


def test_tokenize_ko_returns_non_empty_int_list() -> None:
    """Korean content text tokenizes to a non-empty list[int]."""
    toks = tokenize_ko("삼성전자 영업이익")
    assert isinstance(toks, list)
    assert toks, "expected at least one content token"
    assert all(isinstance(t, int) for t in toks)
    # BLAKE2s 4-byte masked to positive int32 → every id fits [0, 2**31).
    assert all(0 <= t < 2**31 for t in toks)


def test_tokenize_ko_empty_input_returns_empty_list() -> None:
    """Empty input yields an empty list (no exception)."""
    assert tokenize_ko("") == []


def test_tokenize_ko_is_stable_across_calls() -> None:
    """Same input → identical output (stable hashing → index/query parity)."""
    text = "삼성전자 반도체 영업이익 영어 English 2026"
    first = tokenize_ko(text)
    second = tokenize_ko(text)
    assert first == second
    assert first, "expected content tokens for a mixed Korean/Latin/number string"


def test_tokenize_ko_drops_non_content_pos() -> None:
    """Non-content POS (attached josa, punctuation) contribute no tokens.

    mecab tags the attached 관형격 조사 '의' in '삼성전자의' as JKG (dropped) and
    the standalone marks as SY/SF (dropped). Only the two content nouns
    '삼성전자' (NNP) and '영업이익' (→ '영업' NNG + '이익' NNG) survive, so the
    josa-bearing phrase tokenizes to exactly the same content-token set as the
    de-josa'd phrase. Pure punctuation tokenizes to an empty list.
    """
    assert tokenize_ko("!!! ??? , .") == []
    # Attached josa is stripped: '삼성전자의 영업이익' yields the same content
    # tokens as '삼성전자 영업 이익' (no JKG '의' token leaks through).
    with_josa = tokenize_ko("삼성전자의 영업이익")
    without_josa = tokenize_ko("삼성전자 영업이익")
    assert with_josa == without_josa
    assert with_josa, "expected content nouns to survive"


def test_embedder_version_constant_imports_without_torch() -> None:
    """Importing the version constant must NOT eagerly load torch/bge-m3.

    The ``from sentence_transformers import SentenceTransformer`` import lives
    inside ``Embedder.__init__`` — so importing the module + reading the
    constant is cheap and torch-free.
    """
    import sys

    from mcp_v2.embedding import EMBEDDING_MODEL_VERSION, encode_query  # noqa: F401

    assert EMBEDDING_MODEL_VERSION == "BAAI/bge-m3@v1"
    # No Embedder() was constructed → sentence_transformers must not be imported
    # as a side effect of importing mcp_v2.embedding.
    assert "torch" not in sys.modules or "sentence_transformers" not in sys.modules
