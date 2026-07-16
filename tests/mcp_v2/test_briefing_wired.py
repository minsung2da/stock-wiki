"""DB-backed wired tests for get_briefing (Plan 05-04 Task 2, SC#5 / Veto #13).

Supersedes the Phase-3 honest-empty guard (``test_portfolio_briefing.py``:
``test_get_briefing_positively_returns_empty_model`` /
``test_get_briefing_weekly_also_empty`` /
``test_get_briefing_does_not_reference_report_type``) — an EXPECTED replacement,
not a regression: now that Phase 5 added ``report_type``/``report_date`` (migration
0009) and wired ``get_briefing`` to :func:`cards.store.get_briefing_row`, the tool
reads a real row instead of returning a constant empty model.

Seeds a ``daily_briefing`` / ``weekly_briefing`` row via ``store.save_briefing``
into the same container the tool reads through ``get_engine()`` (the session
fixture sets ``DATABASE_URL``, exactly like ``test_card.py``), then asserts:

- a seeded row -> ``found=True`` with the stored ``entries`` (SC#5),
- an empty DB -> ``found=False, entries=[]`` (D-01 normal empty),
- the public ``type`` maps to the stored ``report_type`` (a weekly row does NOT
  satisfy a daily query),
- a bad ``type`` / non-ISO ``date`` -> ``InvalidArgument`` (before any DB access),
- ``test_no_body_leak`` — the ``Briefing`` model has NO ``body_md`` field, so the
  full 6-column table never reaches context (Veto #13 filter-before-context).
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from briefing.models import BriefingRow
from cards import store
from mcp_v2.errors import InvalidArgument
from mcp_v2.models import Briefing
from mcp_v2.tools.briefing import get_briefing

pytestmark = pytest.mark.db

_KST = ZoneInfo("Asia/Seoul")


def _entry(ticker: str = "005930") -> dict:
    """One entry in the LOCKED flat daily-entry schema (05-03)."""
    return {
        "ticker": ticker,
        "name": None,
        "event_class": "stance_flip",
        "change": "HOLD→SELL",
        "evidence": f"{ticker} HBM 수요 둔화",
        "stance": "SELL",
        "conviction": 0.83,
        "why_now": f"{ticker} HBM 수요 둔화",
        "why_not": "메모리 가격 반등 가능성",
        "card_id": f"card_{ticker}_2026-07-16",
    }


def _briefing_row(
    report_date: date,
    *,
    report_type: str = "daily_briefing",
    entries: list[dict] | None = None,
) -> BriefingRow:
    """A self-describing BriefingRow (the 05-02 write contract get_briefing_row reads)."""
    card_id = f"brief_{report_type}_{report_date.isoformat()}"
    gen = datetime(2026, 7, 16, 17, 42, tzinfo=_KST)
    as_of = datetime(2026, 7, 16, 16, 0, tzinfo=_KST)
    exp = datetime(2026, 7, 17, 16, 0, tzinfo=_KST)
    if entries is None:
        entries = [_entry()]
    payload = {
        "card_id": card_id,
        "report_type": report_type,
        "report_date": report_date.isoformat(),
        "generated_at": gen.isoformat(),
        "as_of": as_of.isoformat(),
        "expires_at": exp.isoformat(),
        "entries": entries,
        "generated_for": report_date.isoformat(),
    }
    return BriefingRow(
        card_id=card_id,
        report_type=report_type,  # type: ignore[arg-type]
        report_date=report_date,
        generated_at=gen,
        as_of=as_of,
        expires_at=exp,
        payload=payload,
        body_md="# 데일리 브리핑\n\n종목 | 변화 | 근거 | 제안 | Why now | Why not\n",
    )


def test_get_briefing_reads_daily_row_found_true(pg_clean):
    """SC#5: a seeded daily_briefing row is read back with found=True + entries."""
    d = date(2026, 7, 16)
    store.save_briefing(pg_clean, _briefing_row(d))

    result = get_briefing(d.isoformat(), "daily")

    assert result.found is True
    assert result.date == d.isoformat()
    assert result.type == "daily"
    assert len(result.entries) == 1
    assert result.entries[0]["ticker"] == "005930"
    assert result.entries[0]["stance"] == "SELL"
    assert result.entries[0]["event_class"] == "stance_flip"


def test_get_briefing_empty_db_found_false(pg_clean):
    """D-01: no row for the date is a NORMAL empty result, not an error."""
    result = get_briefing("2026-07-16", "daily")

    assert result.found is False
    assert result.entries == []
    assert result.type == "daily"


def test_get_briefing_weekly_reads_weekly_row(pg_clean):
    """The public type 'weekly' maps to report_type 'weekly_briefing'."""
    d = date(2026, 7, 12)
    store.save_briefing(pg_clean, _briefing_row(d, report_type="weekly_briefing"))

    result = get_briefing(d.isoformat(), "weekly")

    assert result.found is True
    assert result.type == "weekly"
    assert len(result.entries) == 1


def test_get_briefing_daily_does_not_read_weekly_row(pg_clean):
    """The type->report_type mapping is real: a weekly row must NOT answer a daily query."""
    d = date(2026, 7, 16)
    store.save_briefing(pg_clean, _briefing_row(d, report_type="weekly_briefing"))

    result = get_briefing(d.isoformat(), "daily")

    assert result.found is False
    assert result.entries == []


def test_get_briefing_bad_type_raises_invalid_argument(pg_clean):
    with pytest.raises(InvalidArgument):
        get_briefing("2026-07-16", type="monthly")
    with pytest.raises(InvalidArgument):
        get_briefing("2026-07-16", type="")


def test_get_briefing_bad_date_raises_invalid_argument(pg_clean):
    """ASVS V5: a non-ISO date is rejected before the report_date bind."""
    with pytest.raises(InvalidArgument):
        get_briefing("not-a-date", "daily")
    with pytest.raises(InvalidArgument):
        get_briefing("2026-13-99", "daily")


def test_no_body_leak():
    """Veto #13: the Briefing model has NO body_md field — entries only reach context."""
    assert "body_md" not in Briefing.model_fields
