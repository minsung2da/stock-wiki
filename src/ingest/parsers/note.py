"""Phase 8 — parser for ``notes/private/**/*.md`` user memos (D-15).

Dispatches by frontmatter ``type`` to ``ThesisFrontmatter`` (thesis) or
``NoteFrontmatter`` (journal/conviction/note/unknown). Validation failures
record ``note_schema_violation`` in ``review_flags`` and continue body
indexing — exceptions are NEVER raised (Phase 5 D-11 + Phase 8 D-15).

Pure: no DB writes, no network. Caller (ingest worker) owns persistence.

CI guard COLL-07: this module MUST NOT import ``anthropic`` or ``openai``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import frontmatter as pyfm
from pydantic import ValidationError

from shared.frontmatter import NOTE_MODEL_BY_TYPE, NoteFrontmatter

__all__ = ["ParsedNote", "parse_note"]


@dataclass
class ParsedNote:
    """Result of parsing a single ``notes/private/**/*.md`` file."""

    path: Path
    note_type: str  # "thesis" | "journal" | "conviction" | "note" | <unknown>
    frontmatter: NoteFrontmatter | None  # None when validation fails
    body: str
    review_flags: list[str] = field(default_factory=list)


def parse_note(path: Path) -> ParsedNote:
    """Parse a ``notes/private/**/*.md`` file. Pure: no DB writes.

    Returns:
        ParsedNote with ``frontmatter=None`` and ``review_flags=['note_schema_violation']``
        when Pydantic validation fails. Body is always populated so the ingest
        pipeline can still embed and BM25-index the content (D-15).
    """
    post = pyfm.load(str(path))
    meta = dict(post.metadata or {})
    body = post.content or ""
    note_type = str(meta.get("type", "note"))
    model_cls = NOTE_MODEL_BY_TYPE.get(note_type, NoteFrontmatter)
    flags: list[str] = []
    validated: NoteFrontmatter | None
    try:
        validated = model_cls.model_validate(meta)
    except ValidationError:
        validated = None
        flags.append("note_schema_violation")
    return ParsedNote(
        path=path,
        note_type=note_type,
        frontmatter=validated,
        body=body,
        review_flags=flags,
    )
