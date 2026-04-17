"""Pydantic models for the stock-mcp search tool (D-22, JUDGE-04)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = ["DateRange", "SearchHit", "SearchResult"]


class DateRange(BaseModel):
    """ISO YYYY-MM-DD half-open range [start, end)."""

    model_config = ConfigDict(extra="forbid")
    start: str | None = None
    end: str | None = None


class SearchHit(BaseModel):
    """A single retrieval hit (JUDGE-04: vault_path citation required)."""

    model_config = ConfigDict(extra="forbid")
    vault_path: str
    excerpt: str
    frontmatter_ref: dict
    score: float
    source: str
    doc_id: str


class SearchResult(BaseModel):
    """Response envelope returned by the ``search`` MCP tool."""

    model_config = ConfigDict(extra="forbid")
    hits: list[SearchHit]
    query: str
    mode: str
    total: int
