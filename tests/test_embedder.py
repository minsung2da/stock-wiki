"""Tests for src/ingest/embedder.py (bge-m3, INGEST-10/INGEST-12, D-11)."""

from __future__ import annotations

import math
import os

import pytest


def test_embedding_model_version_constant() -> None:
    # E3: version constant should be importable without triggering model load.
    from ingest.embedder import EMBEDDING_MODEL_VERSION

    assert EMBEDDING_MODEL_VERSION == "BAAI/bge-m3@v1"


_HF_OFFLINE = os.environ.get("HF_HUB_OFFLINE") == "1"


@pytest.fixture(scope="session")
def warm_embedder():
    """Session-scoped fixture that pre-loads bge-m3 once."""
    if _HF_OFFLINE:
        pytest.skip("HF_HUB_OFFLINE=1 — bge-m3 model load skipped")
    from ingest.embedder import get_default_embedder

    return get_default_embedder()


@pytest.mark.slow
def test_embedder_shape_and_norm(warm_embedder) -> None:
    vecs = warm_embedder.encode(["삼성전자 2026년 1분기 실적"])
    assert len(vecs) == 1
    assert len(vecs[0]) == 1024
    norm = math.sqrt(sum(x * x for x in vecs[0]))
    assert 0.95 <= norm <= 1.05


@pytest.mark.slow
def test_embedder_batch_encode(warm_embedder) -> None:
    vecs = warm_embedder.encode(["a", "b", "c"])
    assert len(vecs) == 3
    assert all(len(v) == 1024 for v in vecs)


@pytest.mark.slow
def test_encode_query_lru_cache_hit(warm_embedder) -> None:
    from ingest.embedder import encode_query

    encode_query.cache_clear()
    _ = encode_query("삼성전자")
    _ = encode_query("삼성전자")
    info = encode_query.cache_info()
    assert info.hits >= 1
