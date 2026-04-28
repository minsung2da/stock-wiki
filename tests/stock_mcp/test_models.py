"""Phase 6 Plan 06-02 Task 1: response model tests.

Six behaviors per plan:
  1. OverviewResponse defaults: valuation/supply_demand/private_thesis all None.
  2. extra='forbid' rejects unknown fields.
  3. HealthResponse round-trips via model_dump_json with status='down'.
  4. PortfolioRow accepts qty=None and avg_cost=None (watchlist case).
  5. FilingResponse with body_chars=300_000 + truncated=True is valid.
  6. ErrorCode.INVALID_DATE serializes to 'INVALID_DATE' (covered in test_errors.py).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from stock_mcp.models import (
    AddNoteResponse,
    EventRow,
    EventTimeline,
    FilingResponse,
    HealthResponse,
    OverviewResponse,
    PortfolioRow,
    PortfolioState,
    RelatedRow,
    RelatedSet,
    SourceHealth,
)


def test_overview_response_phase10_placeholders_default_none() -> None:
    o = OverviewResponse(ticker="005930")
    assert o.valuation is None
    assert o.supply_demand is None
    assert o.private_thesis is None
    assert o.events == []
    assert o.related_notes == []
    assert o.truncation_applied == []
    assert o.corp_code is None
    assert o.portfolio is None


def test_overview_response_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        OverviewResponse(ticker="005930", foo="bar")  # type: ignore[call-arg]


def test_health_response_down_round_trip() -> None:
    ts = datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC)
    src = SourceHealth(status="down", last_error="connection refused")
    db = SourceHealth(status="ok", age_hours=0.1)
    h = HealthResponse(overall="down", sources={"dart": src}, db=db, timestamp=ts)
    j = h.model_dump_json()
    h2 = HealthResponse.model_validate_json(j)
    assert h2.overall == "down"
    assert h2.sources["dart"].status == "down"
    assert h2.sources["dart"].last_error == "connection refused"
    assert h2.db.status == "ok"


def test_portfolio_row_watchlist_case_qty_none() -> None:
    r = PortfolioRow(ticker="000660")
    assert r.qty is None
    assert r.avg_cost is None
    assert r.tags == []
    assert r.note is None


def test_filing_response_truncated_large_body() -> None:
    body = "x" * 200_000
    f = FilingResponse(
        id="20260101000001",
        vault_path="vault/raw/dart/2026/foo.md",
        frontmatter={"provenance": {"source": "dart"}},
        body=body,
        body_chars=300_000,
        truncated=True,
    )
    assert len(f.body) == 200_000
    assert f.body_chars == 300_000
    assert f.truncated is True


def test_event_timeline_truncation_default() -> None:
    er = EventRow(
        id="evt-1",
        source="news",
        date="2026-04-28",
        title="제목",
        snippet_200ch="<vault_excerpt>요약</vault_excerpt>",
        vault_path="vault/raw/news/2026/foo.md",
    )
    t = EventTimeline(events=[er])
    assert t.truncation_applied == []


def test_event_row_source_literal_rejects_invalid() -> None:
    with pytest.raises(ValidationError):
        EventRow(
            id="x",
            source="invalid_source",  # type: ignore[arg-type]
            date="2026-04-28",
            title="t",
            snippet_200ch="",
            vault_path="vault/raw/dart/x.md",
        )


def test_portfolio_state_holdings_and_watchlist() -> None:
    held = PortfolioRow(ticker="005930", qty=10.0, avg_cost=70000.0)
    watch = PortfolioRow(ticker="000660")
    s = PortfolioState(
        holdings=[held],
        watchlist=[watch],
        source_path="notes/private/portfolio.md",
        last_modified=datetime(2026, 4, 28, tzinfo=UTC),
    )
    assert s.holdings[0].qty == 10.0
    assert s.watchlist[0].avg_cost is None


def test_related_set_empty_default() -> None:
    rs = RelatedSet(related=[])
    assert rs.truncation_applied == []


def test_related_row_optional_fields() -> None:
    r = RelatedRow(id="ent-1", edge_type="mentions", depth=1)
    assert r.vault_path is None
    assert r.snippet_200ch is None


def test_add_note_response_action_literal() -> None:
    resp = AddNoteResponse(
        vault_path="notes/private/journal/2026-04-28.md",
        action="created",
        idempotent=False,
    )
    assert resp.action == "created"
    with pytest.raises(ValidationError):
        AddNoteResponse(
            vault_path="x",
            action="overwritten",  # type: ignore[arg-type]
            idempotent=False,
        )


def test_source_health_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        SourceHealth(status="ok", unknown_field=1)  # type: ignore[call-arg]
