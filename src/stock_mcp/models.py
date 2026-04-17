"""Pydantic models for the stock-mcp search tool (D-22, JUDGE-04)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

__all__ = ["DateRange", "SearchHit", "SearchResult"]


class DateRange(BaseModel):
    """ISO YYYY-MM-DD half-open range [start, end)."""

    model_config = ConfigDict(extra="forbid")
    start: str | None = None
    end: str | None = None

    @field_validator("start", "end", mode="before")
    @classmethod
    def _validate_iso_date(cls, v: object) -> object:
        if v is None:
            return v
        try:
            date.fromisoformat(str(v))
        except ValueError as exc:
            raise ValueError("date must be ISO YYYY-MM-DD") from exc
        return v

    @model_validator(mode="after")
    def _start_before_end(self) -> DateRange:
        if self.start and self.end and self.start > self.end:
            raise ValueError("start must be <= end")
        return self


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
