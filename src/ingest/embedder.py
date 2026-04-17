"""bge-m3 embedder wrapper (INGEST-10, INGEST-12, Pattern 3, D-11).

Loads ``BAAI/bge-m3`` via sentence-transformers once (lazy singleton) and
exposes:

- ``EMBEDDING_MODEL_VERSION``: string constant written to ``chunks.embedding_model``
  for INGEST-12 reuse/versioning.
- ``Embedder``: class with ``.encode(texts)`` returning L2-normalized 1024-d vectors.
- ``get_default_embedder()``: lazy singleton accessor.
- ``encode_query(q)``: LRU-cached (maxsize=256, D-11) query-time encoder returning
  a tuple (hashable for downstream caching).

CLAUDE.md §4 locks sentence-transformers in-process — no Ollama, no LLM server.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from sentence_transformers import SentenceTransformer


__all__ = [
    "EMBEDDING_MODEL_VERSION",
    "Embedder",
    "encode_query",
    "get_default_embedder",
]


EMBEDDING_MODEL_VERSION: str = "BAAI/bge-m3@v1"


class Embedder:
    """Thin wrapper around sentence_transformers.SentenceTransformer('BAAI/bge-m3')."""

    def __init__(self, device: str = "cpu") -> None:
        # Lazy import — avoids pulling torch/transformers when only the version
        # constant is needed (e.g. E3 test, migration tools).
        from sentence_transformers import SentenceTransformer

        self.model: SentenceTransformer = SentenceTransformer("BAAI/bge-m3", device=device)

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode a batch of texts → L2-normalized 1024-d vectors."""
        vecs = self.model.encode(texts, batch_size=16, normalize_embeddings=True)
        return vecs.tolist()


_default_embedder: Embedder | None = None


def get_default_embedder() -> Embedder:
    """Lazy process-wide singleton (loaded on first call)."""
    global _default_embedder
    if _default_embedder is None:
        _default_embedder = Embedder()
    return _default_embedder


@functools.lru_cache(maxsize=256)
def encode_query(q: str) -> tuple[float, ...]:
    """Encode a single query string with D-11 in-process LRU cache (maxsize=256).

    Returns a tuple for hashability (downstream layers can key on it).
    """
    return tuple(get_default_embedder().encode([q])[0])
