"""Korean tokenizer for BM25 indexing + query (Phase 3 Wave-0 leaf — ported from
archive ingest/tokenizer.py).

Uses python-mecab-ko (import name ``mecab``) to segment text, keeps only content
POS tags (NNG, NNP, SL, SN), and hashes each surface form to a stable int32 ID
via BLAKE2s (4-byte digest masked to the positive int32 range).

Index/query parity contract: the SAME function tokenizes both at backfill/ingest
time and at query time. Hash-based vocab IDs avoid a separate vocab table;
VectorChord-BM25 computes IDF from the INT[] array contents at query time.

This is a schema-agnostic leaf — no DB. It depends on the ``ingest`` dependency
group (python-mecab-ko) re-added in Plan 03-01.
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
    punctuation) are filtered out. The same input always yields the same
    output (stable hashing — index/query parity).
    """
    if not text:
        return []
    ids: list[int] = []
    for tok in _mc.parse(text):
        pos = tok.feature.pos
        if pos in _CONTENT_POS:
            ids.append(_token_id(tok.surface.lower()))
    return ids
