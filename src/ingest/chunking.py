"""Section-aware chunking for the ingest worker (D-05, D-08, Pattern 2).

Two-pass algorithm:
1. Structural pass: one Chunk per Section (preserves DART TOC / news article
   structure as retrievable units).
2. Sliding-window pass: any Section that exceeds ``max_tokens`` (default 1500
   bge-m3 tokens per D-05) is re-split into ``win``-sized windows with
   ``overlap`` (defaults 512/64 per D-05) token overlap.

Index semantics (Open Question Q4):
- ``chunk_index``: monotonic per document (does NOT reset at section
  boundary). This keeps the existing ``chunks.chunk_index INT`` column
  consistent with Phase 2 semantics.
- ``section_index``: order WITHIN a section — resets to 0 at each new
  section. 0 for sections that fit in a single chunk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ingest.parsers.dart import Section

__all__ = ["Chunk", "chunk_document"]


_tok: Any | None = None


def _get_tok() -> Any:
    """Lazy-load the BAAI/bge-m3 tokenizer for token counting.

    Kept as a module-level accessor so tests can monkeypatch it with a
    fake tokenizer and avoid a 2GB model download on CI.
    """
    global _tok
    if _tok is None:
        from transformers import AutoTokenizer

        _tok = AutoTokenizer.from_pretrained("BAAI/bge-m3")
    return _tok


@dataclass
class Chunk:
    text: str
    chunk_index: int
    section_path: str | None
    section_index: int | None


def chunk_document(
    sections: list[Section],
    *,
    max_tokens: int = 1500,
    win: int = 512,
    overlap: int = 64,
) -> list[Chunk]:
    """Split sections into chunks respecting D-05 size/overlap bounds."""
    chunks: list[Chunk] = []
    tok = _get_tok()
    for sec in sections:
        ids = tok.encode(sec.text, add_special_tokens=False)
        if len(ids) <= max_tokens:
            chunks.append(Chunk(sec.text, len(chunks), sec.path, 0))
            continue
        step = win - overlap
        for i, start in enumerate(range(0, len(ids), step)):
            piece = tok.decode(ids[start : start + win])
            if not piece.strip():
                continue
            chunks.append(Chunk(piece, len(chunks), sec.path, i))
    return chunks
