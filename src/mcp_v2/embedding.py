"""bge-m3 embedder wrapper (Phase 3 Wave-0 leaf — ported from archive ingest/embedder.py).

Loads ``BAAI/bge-m3`` via sentence-transformers once (lazy singleton) and
exposes:

- ``EMBEDDING_MODEL_VERSION``: string constant identifying the model + revision
  used for an embedding (carry-over of the archive's chunks.embedding_model
  versioning; reused by the Wave-0 backfill so a model bump is detectable).
- ``Embedder``: class with ``.encode(texts)`` returning L2-normalized 1024-d
  vectors as plain Python lists.
- ``get_default_embedder()``: lazy process-wide singleton accessor.
- ``encode_query(q)``: LRU-cached (maxsize=256) query-time encoder returning a
  tuple (hashable for downstream caching).

CLAUDE.md §4 / Hard Veto locks sentence-transformers in-process — no Ollama, no
LLM server, no API embedding service. The first ``Embedder()`` construction
downloads ~2GB of bge-m3 weights to the HuggingFace cache; subsequent loads are
cached. The ``from sentence_transformers import SentenceTransformer`` import is
kept lazy inside ``__init__`` so callers that only need ``EMBEDDING_MODEL_VERSION``
(e.g. version checks, the AST guard) never pull torch/transformers.

Hard Veto #6 reminder: this leaf embeds NARRATIVE text only. The backfill that
calls it never feeds numeric tables (ohlcv/macro/fundamentals) through here.
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
    """Thin wrapper around ``sentence_transformers.SentenceTransformer('BAAI/bge-m3')``."""

    def __init__(self, device: str = "cpu") -> None:
        # Lazy import — avoids pulling torch/transformers when only the version
        # constant is needed (version checks, the SC#3 AST guard, migrations).
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
    """Encode a single query string with an in-process LRU cache (maxsize=256).

    Returns a tuple for hashability (downstream layers can key on it).
    """
    return tuple(get_default_embedder().encode([q])[0])
