"""Korean tokenizer for BM25 indexing + query (D-12, INGEST-11, Pattern 4).

Uses python-mecab-ko to segment text, keeps only content POS tags
(NNG, NNP, SL, SN), and hashes each surface form to a stable int32 ID
via BLAKE2s (4-byte digest masked to the positive int32 range).

D-12 contract: the SAME function is used for both ingest-time and
query-time tokenization. Hash-based vocab IDs avoid a separate vocab
table in Phase 3; VectorChord-BM25 computes IDF from the INT[] array
contents at query time.
"""

from __future__ import annotations

import hashlib

import mecab

__all__ = ["tokenize_ko"]


_mc = mecab.MeCab()

# Content POS tags — NNG (noun), NNP (proper noun), SL (foreign/latin),
# SN (number). Josa/endings (JKS/JKO/JX/EF/EC) are dropped.
_CONTENT_POS: frozenset[str] = frozenset({"NNG", "NNP", "SL", "SN"})


def _token_id(surface: str) -> int:
    """Blake2s 4-byte digest masked to positive int32."""
    digest = hashlib.blake2s(surface.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") & 0x7FFFFFFF


def tokenize_ko(text: str) -> list[int]:
    """Tokenize Korean text → list of stable int32 IDs (content POS only).

    Empty input returns an empty list. Non-content tokens (josa, endings,
    punctuation) are filtered out.
    """
    if not text:
        return []
    ids: list[int] = []
    for tok in _mc.parse(text):
        pos = tok.feature.pos
        if pos in _CONTENT_POS:
            ids.append(_token_id(tok.surface.lower()))
    return ids
