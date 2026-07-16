"""Unit + DB tests for the weekly roll-up (Plan 05-05, SC#4 / D-07 / D-08).

The weekly aggregates the week's <=7 daily payloads into a per-ticker NET-change
digest, PRE-MATERIALIZES the entries into a ``report_type='weekly_briefing'`` row, and
records coverage. Two properties are load-bearing:

- **D-07 NET:** per-ticker start-of-week state vs end-of-week state; intra-week
  flip-flops (BUY->HOLD->BUY) net to no-change and are DROPPED; the count of intra-week
  events is kept.
- **D-08 best-effort coverage:** missing dailies are rolled up whatever exists with a
  ``coverage: {present, expected, missing_dates}``; a missing day is NOT a no-change.
- **SC#4 no-recompute:** ``get_briefing(week_end, 'weekly')`` returns the stored row
  unchanged even after the source dailies are mutated/deleted (a pure SELECT).

All net entries are FLAT dicts (the SAME locked daily entries[] schema), so the reused
DICT-keyed ``_priority_key`` sorts them without any ``.card`` attribute access.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from briefing.models import BriefingRow
from briefing.weekly import aggregate_net

_KST = ZoneInfo("Asia/Seoul")


def _entry(
    ticker: str,
    stance: str,
    conviction: float,
    *,
    event_class: str = "stance_flip",
    change: str = "x",
    card_id: str | None = None,
) -> dict:
    """One entry in the LOCKED flat daily-entry schema (05-03)."""
    return {
        "ticker": ticker,
        "name": None,
        "event_class": event_class,
        "change": change,
        "evidence": f"{ticker} evidence",
        "stance": stance,
        "conviction": conviction,
        "why_now": f"{ticker} catalyst",
        "why_not": f"{ticker} risk",
        "card_id": card_id or f"card_{ticker}_{stance}",
    }


def _daily_row(report_date: date, entries: list[dict]) -> BriefingRow:
    """A self-describing daily BriefingRow carrying ``entries`` (the weekly's input)."""
    card_id = f"brief_daily_{report_date.isoformat()}"
    gen = datetime(report_date.year, report_date.month, report_date.day, 17, 42, tzinfo=_KST)
    as_of = datetime(report_date.year, report_date.month, report_date.day, 16, 0, tzinfo=_KST)
    exp = as_of + timedelta(days=1)
    payload = {
        "card_id": card_id,
        "report_type": "daily_briefing",
        "report_date": report_date.isoformat(),
        "generated_at": gen.isoformat(),
        "as_of": as_of.isoformat(),
        "expires_at": exp.isoformat(),
        "entries": entries,
        "generated_for": report_date.isoformat(),
    }
    return BriefingRow(
        card_id=card_id,
        report_type="daily_briefing",
        report_date=report_date,
        generated_at=gen,
        as_of=as_of,
        expires_at=exp,
        payload=payload,
        body_md="daily body",
    )


# ---------------------------------------------------------------------------
# Task 1 — aggregate_net: NET per-ticker diff, flip-flop drop, coverage
# ---------------------------------------------------------------------------
def test_net_change():
    """D-07: a flip-flop nets out; a genuine start!=end is retained with the delta."""
    week_start = date(2026, 7, 13)
    week_end = date(2026, 7, 19)
    rows = [
        _daily_row(
            date(2026, 7, 13),
            [
                _entry("000001", "BUY", 0.70),  # ticker A start
                _entry("000002", "HOLD", 0.60),  # ticker B start
            ],
        ),
        _daily_row(
            date(2026, 7, 15),
            [_entry("000001", "HOLD", 0.65)],  # A intra-week flip
        ),
        _daily_row(
            date(2026, 7, 17),
            [
                _entry("000001", "BUY", 0.70),  # A back to BUY -> flip-flop (dropped)
                _entry("000002", "SELL", 0.80),  # B genuine HOLD->SELL
            ],
        ),
    ]

    net_entries, _coverage = aggregate_net(rows, week_start=week_start, week_end=week_end)

    tickers = {e["ticker"] for e in net_entries}
    assert "000001" not in tickers  # flip-flop BUY->HOLD->BUY nets to no-change (D-07)
    assert "000002" in tickers  # genuine start!=end retained

    b = next(e for e in net_entries if e["ticker"] == "000002")
    assert b["change"] == "HOLD→SELL"
    assert b["stance"] == "SELL"
    assert b["conviction"] == 0.80
    assert b["intra_week_events"] == 2  # HOLD(Mon) + SELL(Fri)
    # FLAT dict: the reused dict-keyed _priority_key reads these keys (no attribute access).
    assert "event_class" in b
    assert "conviction" in b


def test_net_change_conviction_move_retained_within_threshold_dropped():
    """A same-stance conviction move >= threshold is retained; a tiny move nets out."""
    week_start = date(2026, 7, 13)
    week_end = date(2026, 7, 19)
    rows = [
        _daily_row(
            date(2026, 7, 13),
            [
                _entry("000003", "HOLD", 0.40),  # big conviction mover start
                _entry("000004", "HOLD", 0.50),  # tiny mover start
            ],
        ),
        _daily_row(
            date(2026, 7, 17),
            [
                _entry("000003", "HOLD", 0.75),  # +0.35 >= 0.10 -> retained
                _entry("000004", "HOLD", 0.54),  # +0.04 < 0.10 -> dropped
            ],
        ),
    ]

    net_entries, _coverage = aggregate_net(rows, week_start=week_start, week_end=week_end)
    tickers = {e["ticker"] for e in net_entries}

    assert "000003" in tickers  # conviction move beyond threshold, same stance -> kept
    assert "000004" not in tickers  # within-threshold drift nets out
    mover = next(e for e in net_entries if e["ticker"] == "000003")
    assert mover["stance"] == "HOLD"
    assert mover["conviction"] == 0.75  # end-of-week conviction


def test_coverage():
    """D-08: 5 present / 2 missing -> coverage {present:5, expected:7} + 2 missing dates."""
    week_start = date(2026, 7, 13)
    week_end = date(2026, 7, 19)
    present = [date(2026, 7, d) for d in (13, 14, 15, 16, 17)]  # Mon-Fri present
    rows = [_daily_row(d, [_entry("000001", "HOLD", 0.60)]) for d in present]

    _net, coverage = aggregate_net(rows, week_start=week_start, week_end=week_end)

    assert coverage["present"] == 5
    assert coverage["expected"] == 7
    # Sat + Sun missing — a missing day is NOT a no-change ticker, only a coverage gap.
    assert coverage["missing_dates"] == ["2026-07-18", "2026-07-19"]
