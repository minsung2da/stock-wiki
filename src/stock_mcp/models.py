"""Pydantic models for stock-mcp tools (Phase 3 search + Phase 6 tool surface).

Phase 3: DateRange, SearchHit, SearchResult (D-22, JUDGE-04).
Phase 6 (Plan 06-02): Response models for the seven Wave-2/3 tools — get_ticker_overview,
get_recent_events, get_portfolio_state, get_related, get_filing, add_note, health.
All Phase 6 models pin extra='forbid' so callers cannot smuggle unknown fields.
Phase 10 placeholders (ValuationContext, SupplyDemandSignals, PrivateThesis) are empty
shells in Phase 6; Phase 10 fills their fields without breaking callers.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "DateRange",
    "SearchHit",
    "SearchResult",
    # Phase 6 placeholders
    "ValuationContext",
    "SupplyDemandSignals",
    "PrivateThesis",
    # Phase 6 events / portfolio / related / filing / note / health
    "EventRow",
    "EventTimeline",
    "PortfolioRow",
    "PortfolioState",
    "RelatedRow",
    "RelatedSet",
    "FilingResponse",
    "AddNoteResponse",
    "SourceHealth",
    "HealthResponse",
    "OverviewResponse",
]


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


# ---------------------------------------------------------------------------
# Phase 6 — Phase-10 placeholders (D-01).
# Empty Pydantic models so OverviewResponse.valuation/supply_demand/private_thesis
# can be typed `T | None = None` today and filled in Phase 10 without changing
# the OverviewResponse signature.
# ---------------------------------------------------------------------------


class ValuationContext(BaseModel):
    """Phase 10 placeholder. Empty in Phase 6; always None on tool responses."""

    model_config = ConfigDict(extra="forbid")


class SupplyDemandSignals(BaseModel):
    """Phase 10 placeholder. Empty in Phase 6; always None on tool responses."""

    model_config = ConfigDict(extra="forbid")


class PrivateThesis(BaseModel):
    """Phase 10 placeholder. Empty in Phase 6; always None on tool responses."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# MCP-04 — get_recent_events response (D-05)
# ---------------------------------------------------------------------------


class EventRow(BaseModel):
    """One timeline row (DART filing | news article | KIND notice)."""

    model_config = ConfigDict(extra="forbid")
    id: str
    source: Literal["dart", "news", "kind"]
    date: str  # ISO YYYY-MM-DD
    type: str | None = None
    title: str
    snippet_200ch: str  # already wrapped with <vault_excerpt>...</vault_excerpt>
    vault_path: str


class EventTimeline(BaseModel):
    """Response envelope for ``get_recent_events``."""

    model_config = ConfigDict(extra="forbid")
    events: list[EventRow]
    truncation_applied: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# MCP-05 — get_portfolio_state response (D-21)
# ---------------------------------------------------------------------------


class PortfolioRow(BaseModel):
    """One holding/watchlist row. qty/avg_cost are None for watchlist."""

    model_config = ConfigDict(extra="forbid")
    ticker: str
    corp_code: str | None = None
    qty: float | None = None
    avg_cost: float | None = None
    tags: list[str] = Field(default_factory=list)
    note: str | None = None


class PortfolioState(BaseModel):
    """Response envelope for ``get_portfolio_state``."""

    model_config = ConfigDict(extra="forbid")
    holdings: list[PortfolioRow]
    watchlist: list[PortfolioRow]
    source_path: str
    last_modified: datetime


# ---------------------------------------------------------------------------
# MCP-06 — get_related response (D-06)
# ---------------------------------------------------------------------------


class RelatedRow(BaseModel):
    """One related-entity row from graph/index traversal."""

    model_config = ConfigDict(extra="forbid")
    id: str
    edge_type: str
    depth: int
    vault_path: str | None = None
    snippet_200ch: str | None = None


class RelatedSet(BaseModel):
    """Response envelope for ``get_related``."""

    model_config = ConfigDict(extra="forbid")
    related: list[RelatedRow]
    truncation_applied: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# MCP-07 — get_filing response (D-07)
# ---------------------------------------------------------------------------


class FilingResponse(BaseModel):
    """Response envelope for ``get_filing``. body capped at 200_000 chars (D-07)."""

    model_config = ConfigDict(extra="forbid")
    id: str
    vault_path: str
    frontmatter: dict
    body: str
    body_chars: int  # original (untruncated) length
    truncated: bool


# ---------------------------------------------------------------------------
# MCP-08 — add_note response (D-10, D-13)
# ---------------------------------------------------------------------------


class AddNoteResponse(BaseModel):
    """Response envelope for ``add_note``. action='created' on first write,
    'appended' otherwise. idempotent=True when a duplicate write was a no-op."""

    model_config = ConfigDict(extra="forbid")
    vault_path: str
    action: Literal["created", "appended"]
    idempotent: bool


# ---------------------------------------------------------------------------
# MCP-09 — health response (D-15)
# ---------------------------------------------------------------------------


class SourceHealth(BaseModel):
    """Per-source health status."""

    model_config = ConfigDict(extra="forbid")
    status: Literal["ok", "stale", "down"]
    last_success: datetime | None = None
    age_hours: float | None = None
    last_error: str | None = None  # callers truncate to ≤200 chars


class HealthResponse(BaseModel):
    """Response envelope for ``health``. ``overall`` is the worst of all sources+db."""

    model_config = ConfigDict(extra="forbid")
    overall: Literal["ok", "stale", "down"]
    sources: dict[str, SourceHealth]
    db: SourceHealth
    timestamp: datetime


# ---------------------------------------------------------------------------
# MCP-03 — get_ticker_overview response (D-01, D-02, D-22)
# ---------------------------------------------------------------------------


class OverviewResponse(BaseModel):
    """Composite response for ``get_ticker_overview``.

    Phase 10 placeholder fields (valuation/supply_demand/private_thesis) are
    typed as Optional models and always serialized as None in Phase 6 (D-01).
    """

    model_config = ConfigDict(extra="forbid")
    ticker: str
    corp_code: str | None = None
    events: list[EventRow] = Field(default_factory=list)
    portfolio: PortfolioRow | None = None
    related_notes: list[SearchHit] = Field(default_factory=list)
    valuation: ValuationContext | None = None
    supply_demand: SupplyDemandSignals | None = None
    private_thesis: PrivateThesis | None = None
    truncation_applied: list[str] = Field(default_factory=list)
