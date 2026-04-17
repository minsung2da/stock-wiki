"""Pydantic v2 models for the 3-zone frontmatter schema.

Zone 1 (provenance): Written by collectors at fetch time. Never overwritten by ingest.
Zone 2 (ingest_state): Written by ingest pipeline. Tracks processing state.
Zone 3 (_derived): LLM-extracted attributes. Regenerable; do not hand-edit.

Dataview queries use nested access: WHERE provenance.source = "dart" (per D-11).
"""

from __future__ import annotations

from datetime import datetime

import frontmatter as fm
from pydantic import BaseModel, Field, ValidationError


class ProvenanceBlock(BaseModel):
    """Zone 1: Written by collectors. Never overwritten by ingest."""

    source: str  # dart | naver | news | macro | krx | note | kind
    source_id: str | None = None
    source_url: str | None = None
    date: str | None = None
    fetched_at: datetime | None = None
    content_hash: str | None = None
    corp_code: str | None = None  # DART 8-digit canonical ID
    ticker: str | None = None  # KRX 6-digit convenience field
    lang: str = "ko"


class IngestStateBlock(BaseModel):
    """Zone 2: Written by ingest pipeline. Tracks processing state."""

    processed: bool = False
    processed_at: datetime | None = None
    embedding_model: str | None = None
    ingest_model: str | None = None
    ingest_version: int | None = None


class DerivedBlock(BaseModel):
    """Zone 3: LLM-extracted attributes. Regenerable; do not hand-edit."""

    tickers: list[str] = Field(default_factory=list)
    event_type: str | None = None
    catalysts: list[str] = Field(default_factory=list)
    sentiment: dict | None = None
    numeric_facts: list[dict] = Field(default_factory=list)
    summary: str | None = None


class FrontMatter(BaseModel):
    """Top-level frontmatter container. Maps to YAML 1:1 (per D-10).

    YAML key '_derived' maps to the 'derived' Python field via alias.
    Use model_dump(by_alias=True) to emit '_derived' key in YAML output.
    Use model_config populate_by_name=True to accept both 'derived' and '_derived'.
    """

    provenance: ProvenanceBlock
    ingest_state: IngestStateBlock = Field(default_factory=IngestStateBlock)
    derived: DerivedBlock = Field(default_factory=DerivedBlock, alias="_derived")

    model_config = {"populate_by_name": True}


def read_frontmatter(path: str) -> tuple[FrontMatter, str]:
    """Read a markdown file and parse its frontmatter into a Pydantic model.

    Returns:
        Tuple of (FrontMatter model, document body text).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If frontmatter YAML is malformed or fails schema validation.
    """
    try:
        post = fm.load(path)
    except Exception as exc:
        raise ValueError(f"Failed to load frontmatter from {path!r}: {exc}") from exc
    try:
        model = FrontMatter.model_validate(dict(post.metadata))
    except ValidationError as exc:
        raise ValueError(f"Frontmatter schema validation failed for {path!r}: {exc}") from exc
    return model, post.content


def write_frontmatter(path: str, model: FrontMatter, body: str) -> None:
    """Write a markdown file with validated frontmatter.

    Uses model_dump(by_alias=True, exclude_none=True) to emit '_derived'
    key and omit None values for clean YAML output.

    Content is fully computed before the file is opened, so a serialization
    error will not leave a zero-byte or partial file at path.
    """
    post = fm.Post(body)
    post.metadata = model.model_dump(by_alias=True, exclude_none=True)
    content = fm.dumps(post)  # Compute before opening file
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
