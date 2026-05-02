"""Tests for the ``get_ticker_overview`` composite MCP tool (Plan 06-08, MCP-03)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from stock_mcp.models import (
    EventRow,
    OverviewResponse,
    PortfolioRow,
    SearchHit,
)
from stock_mcp.tools import events as events_mod
from stock_mcp.tools import overview as overview_mod
from stock_mcp.tools import portfolio as portfolio_mod
from stock_mcp.tools.overview import (
    EVENTS_CAP,
    TARGET_TOKENS,
    _apply_truncation,
    get_ticker_overview,
)


# --- fixture wiring ----------------------------------------------------------


@pytest.fixture
def wired_engine(
    mcp_vault_engine: tuple[Engine, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Engine, Path, Path]:
    """Force overview + sub-tools to use the testcontainer engine and isolated repo_root."""
    engine, vault_root, repo_root = mcp_vault_engine

    monkeypatch.setattr(overview_mod, "get_engine", lambda: engine)
    monkeypatch.setattr(events_mod, "get_engine", lambda: engine)
    monkeypatch.setattr(portfolio_mod, "get_engine", lambda: engine)
    monkeypatch.setenv("STOCK_REPO_ROOT", str(repo_root))
    return engine, vault_root, repo_root


# --- Tests -------------------------------------------------------------------


def test_holding_ticker_returns_three_axes(
    wired_engine: tuple[Engine, Path, Path],
) -> None:
    """Test 1: 005930 (a holding) returns events + portfolio + related_notes."""
    result = get_ticker_overview(ticker="005930")
    assert isinstance(result, OverviewResponse), f"unexpected error: {result!r}"
    assert result.ticker == "005930"
    assert result.corp_code == "00126380"
    assert len(result.events) <= EVENTS_CAP
    assert isinstance(result.portfolio, PortfolioRow)
    assert result.portfolio.ticker == "005930"
    assert result.portfolio.qty == 100
    assert isinstance(result.related_notes, list)
    assert len(result.related_notes) <= 5


def test_watchlist_only_ticker_returns_watchlist_row(
    wired_engine: tuple[Engine, Path, Path],
) -> None:
    """Test 2: 207940 is watchlist-only → portfolio row with qty=None."""
    result = get_ticker_overview(ticker="207940")
    assert isinstance(result, OverviewResponse), f"unexpected error: {result!r}"
    assert result.ticker == "207940"
    assert result.portfolio is not None
    assert result.portfolio.ticker == "207940"
    assert result.portfolio.qty is None
    assert result.portfolio.avg_cost is None


def test_eight_digit_corp_code_normalizes(
    wired_engine: tuple[Engine, Path, Path],
) -> None:
    """Test 3: 8-digit corp_code resolves to same 6-digit ticker response."""
    by_ticker = get_ticker_overview(ticker="005930")
    by_corp = get_ticker_overview(ticker="00126380")
    assert isinstance(by_ticker, OverviewResponse)
    assert isinstance(by_corp, OverviewResponse)
    assert by_ticker.ticker == by_corp.ticker == "005930"
    assert by_ticker.corp_code == by_corp.corp_code == "00126380"
    # Same event id-set (same entity).
    assert {e.id for e in by_ticker.events} == {e.id for e in by_corp.events}


def test_phase10_placeholders_are_none(
    wired_engine: tuple[Engine, Path, Path],
) -> None:
    """Test 4: valuation/supply_demand/private_thesis are present and None."""
    result = get_ticker_overview(ticker="005930")
    assert isinstance(result, OverviewResponse)
    dumped = result.model_dump()
    assert "valuation" in dumped and dumped["valuation"] is None
    assert "supply_demand" in dumped and dumped["supply_demand"] is None
    assert "private_thesis" in dumped and dumped["private_thesis"] is None


def test_unknown_ticker_returns_invalid_ticker(
    wired_engine: tuple[Engine, Path, Path],
) -> None:
    """Test 5: unresolvable ticker → INVALID_TICKER envelope."""
    result = get_ticker_overview(ticker="999999")
    assert isinstance(result, dict)
    assert result["error"]["code"] == "INVALID_TICKER"


def test_events_hard_capped_at_20(
    wired_engine: tuple[Engine, Path, Path],
) -> None:
    """Test 6: when >20 events exist for the ticker, only 20 are returned."""
    engine, _vault_root, _repo_root = wired_engine
    # Insert 30 synthetic news rows for 005930 (corp_code=00126380).
    inserted_ids: list[str] = []
    try:
        with engine.begin() as conn:
            for i in range(30):
                doc_id = f"a{i:063x}"
                inserted_ids.append(doc_id)
                conn.execute(
                    sa.text(
                        "INSERT INTO documents (id, body, source, vault_path, "
                        "corp_code, first_seen_at) "
                        "VALUES (:id, :body, 'news', :vp, :cc, :fs) "
                        "ON CONFLICT (id) DO NOTHING"
                    ),
                    {
                        "id": doc_id,
                        "body": f"overview synthetic body {i}",
                        "vp": f"vault/raw/synthetic-overview/{doc_id}.md",
                        "cc": "00126380",
                        "fs": f"2026-04-{(i % 28) + 1:02d}T00:00:00+00:00",
                    },
                )

        result = get_ticker_overview(ticker="005930")
        assert isinstance(result, OverviewResponse), f"unexpected error: {result!r}"
        assert len(result.events) == EVENTS_CAP
        assert any(t == "events:cap20" for t in result.truncation_applied)
    finally:
        with engine.begin() as conn:
            for doc_id in inserted_ids:
                conn.execute(
                    sa.text("DELETE FROM documents WHERE id = :id"),
                    {"id": doc_id},
                )


def test_apply_truncation_priority_order() -> None:
    """Test 7: truncation drops by priority — related_notes shrinks before events."""
    # Build an OverviewResponse big enough to bust 7000-token estimate.
    big_excerpt = "x" * 8000  # ~2000 tokens at 4 chars/token
    hits = [
        SearchHit(
            vault_path=f"vault/notes/note-{i}.md",
            excerpt=big_excerpt,
            frontmatter_ref={"source": "note"},
            score=0.5,
            source="note",
            doc_id=f"{i:064x}",
        )
        for i in range(5)
    ]
    events = [
        EventRow(
            id=f"{i:064x}",
            source="news",
            date="2026-04-01",
            type=None,
            title=f"event {i}",
            snippet_200ch=f"<vault_excerpt>{'y' * 180}</vault_excerpt>",
            vault_path=f"vault/raw/news/{i}.md",
        )
        for i in range(10)
    ]
    initial = OverviewResponse(
        ticker="005930",
        corp_code="00126380",
        events=events,
        portfolio=None,
        related_notes=hits,
        valuation=None,
        supply_demand=None,
        private_thesis=None,
        truncation_applied=[],
    )
    # Pre-condition: above the cap.
    assert (
        len(initial.model_dump_json()) // 4
    ) > TARGET_TOKENS, "test fixture must exceed soft cap"

    truncated = _apply_truncation(initial, TARGET_TOKENS)
    # Must end up under the cap (or hit no-progress floor).
    assert (len(truncated.model_dump_json()) // 4) <= TARGET_TOKENS or (
        truncated.events == [] and truncated.related_notes == []
    )
    # related_notes should be sacrificed before events (priority order).
    if truncated.events != events or truncated.related_notes != hits:
        applied = truncated.truncation_applied
        # First truncation step must be related_notes:* (related comes before events).
        first_axis_step = next(
            (a for a in applied if a.startswith(("related_notes:", "events:"))),
            None,
        )
        assert first_axis_step is not None
        assert first_axis_step.startswith("related_notes:"), (
            f"expected related_notes to shrink before events; saw {applied}"
        )


def test_docstring_has_four_sections(
    wired_engine: tuple[Engine, Path, Path],
) -> None:
    """Test 8: 4-section docstring contract (D-24)."""
    doc = get_ticker_overview.__doc__ or ""
    for section in (
        "### Behavior contract",
        "### Response shape",
        "### Errors",
        "### Performance budget",
    ):
        assert section in doc, f"missing docstring section: {section}"


def test_since_default_is_minus_90d_kst(
    wired_engine: tuple[Engine, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test 9: events axis derives `since` from now KST minus 90 days."""
    captured: list[dict] = []

    real_get_recent_events = events_mod.get_recent_events

    def _spy(ticker: str, since: str):
        captured.append({"ticker": ticker, "since": since})
        return real_get_recent_events(ticker=ticker, since=since)

    monkeypatch.setattr(overview_mod, "get_recent_events", _spy)
    result = get_ticker_overview(ticker="005930")
    assert isinstance(result, OverviewResponse)
    assert captured, "overview must call get_recent_events"
    since = captured[0]["since"]
    # ISO YYYY-MM-DD shape.
    from datetime import date as _date

    parsed = _date.fromisoformat(since)
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _ZI

    today_kst = _dt.now(_ZI("Asia/Seoul")).date()
    delta = (today_kst - parsed).days
    # Allow 89..91 to absorb midnight rollover edge.
    assert 89 <= delta <= 91, f"expected ~90-day lookback, got {delta} days"


def test_response_echoes_resolved_ticker_and_corp_code(
    wired_engine: tuple[Engine, Path, Path],
) -> None:
    """Test 10: response.ticker is 6-digit normalized; corp_code from entity."""
    by_corp = get_ticker_overview(ticker="00126380")
    assert isinstance(by_corp, OverviewResponse)
    assert by_corp.ticker == "005930"  # entity.current_ticker normalization.
    assert by_corp.corp_code == "00126380"
