"""src/briefing/weekly.py — Phase 5 weekly roll-up (SC#4 / D-07 / D-08).

The weekly is a genuine per-ticker NET-change digest over the week's <=7 daily
briefings — NOT a 7-day union. It reads each daily row's ``payload["entries"]`` (the
LOCKED FLAT-dict schema 05-03 persists), diffs each ticker's start-of-week state
against its end-of-week state, and DROPS tickers whose net change is nothing (an
intra-week flip-flop like BUY->HOLD->BUY nets out — D-07; the daily rows preserve the
detail). Missing dailies are rolled up best-effort with a coverage count (D-08).

SC#4 (no recompute on read): the aggregation runs ONCE at generation and the resulting
entries are PRE-MATERIALIZED into a ``report_type='weekly_briefing'`` row.
``get_briefing(type='weekly')`` (wired in 05-04) is a pure SELECT of that stored row —
it NEVER re-reads the 7 dailies, so the weekly is byte-stable even if the source dailies
are later mutated or deleted.

Because the entries are read back from JSONB as plain dicts (there is no ``DecisionCard``
object at weekly time — that would violate SC#4 no-recompute), ALL aggregation and
sorting operate on flat dicts. The daily's DICT-keyed ``_priority_key`` is reused
UNCHANGED over these net-entry dicts (no ``.card`` attribute access anywhere).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from cards import store
from db.engine import get_engine

from .daily import (
    _MAX_ENTRIES,
    _kst_close_on,
    _priority_key,
    load_held_tickers,
    render_body_md,
)
from .models import BriefingRow

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_log = logging.getLogger(__name__)
# KST business-day boundary (mirrors daily.py / runner.py:72). report_date/as_of/
# expires_at anchor on the KST close, never a naive date.today() (Pitfall #3).
_KST = ZoneInfo("Asia/Seoul")

# A full week is 7 daily briefings (D-08 coverage denominator). Best-effort: the weekly
# rolls up whatever exists and records the gap — it never blocks on a full 7.
_WEEK_DAYS = 7

# The minimum same-stance conviction move that counts as a NET change (D-07). Below this
# a same-stance drift nets to no-change and is dropped as noise. A small, decomposable,
# module-level constant — never a black-box score (Veto #4 spirit).
_CONVICTION_DELTA = 0.10


def aggregate_net(
    daily_rows: list[BriefingRow], *, week_start: date, week_end: date
) -> tuple[list[dict], dict]:
    """Compute the per-ticker NET change over the week + a best-effort coverage dict.

    Groups every ``payload["entries"]`` across the <=7 daily rows by ticker, preserving
    report_date order (``get_daily_briefings_in_range`` already returns the rows ordered
    by ``report_date``, so a ticker's entries accumulate earliest -> latest). For each
    ticker the start state is the EARLIEST entry's (stance, conviction) and the end state
    is the LATEST entry's. A ticker is a NET change iff its stance flipped OR its
    conviction moved by at least ``_CONVICTION_DELTA``; otherwise it nets to no-change and
    is DROPPED (an intra-week flip-flop like BUY->HOLD->BUY -> D-07). Each surviving entry
    is a FLAT dict in the SAME locked daily schema (so the reused ``_priority_key`` sorts
    it) plus an ``intra_week_events`` count of that ticker's daily entries.

    Coverage (D-08) counts the present dailies against the 7-day window and lists the
    missing dates — a missing day is a coverage gap, NOT a no-change ticker.

    Args:
        daily_rows: the week's daily ``BriefingRow`` objects, ordered by ``report_date``.
        week_start: the KST Monday the week begins.
        week_end: the KST anchor the week ends on (``get_briefing`` queries with this).

    Returns:
        ``(net_entries, coverage)`` — the FLAT net-change entry dicts (unsorted,
        untruncated) and the ``{"present", "expected", "missing_dates"}`` coverage dict.
    """
    # Group by ticker, preserving the earliest -> latest order the rows already carry.
    by_ticker: dict[str, list[dict]] = {}
    present_dates: set[date] = set()
    for row in daily_rows:
        present_dates.add(row.report_date)
        for entry in row.payload.get("entries", []):
            by_ticker.setdefault(entry["ticker"], []).append(entry)

    net_entries: list[dict] = []
    for ticker, entries in by_ticker.items():
        start = entries[0]
        end = entries[-1]
        start_stance, end_stance = start["stance"], end["stance"]
        start_conv, end_conv = start["conviction"], end["conviction"]

        stance_flipped = start_stance != end_stance
        conviction_moved = abs(end_conv - start_conv) >= _CONVICTION_DELTA
        if not stance_flipped and not conviction_moved:
            # Net no-change: an intra-week flip-flop / within-threshold drift (D-07).
            # The daily rows preserve the intra-week detail; the weekly drops it.
            continue

        change = (
            f"{start_stance}→{end_stance}"
            if stance_flipped
            else f"conviction {start_conv:.2f}→{end_conv:.2f}"
        )
        # A FLAT net entry in the LOCKED daily schema (so _priority_key + render_body_md
        # apply unchanged) + intra_week_events. stance/conviction/evidence/why_* carry
        # from the LATEST daily entry (the end-of-week state); event_class likewise so the
        # sort key has a valid rank.
        net_entries.append(
            {
                "ticker": ticker,
                "name": end.get("name"),
                "event_class": end["event_class"],
                "change": change,
                "evidence": end["evidence"],
                "stance": end_stance,
                "conviction": end_conv,
                "why_now": end["why_now"],
                "why_not": end["why_not"],
                "card_id": end["card_id"],
                "intra_week_events": len(entries),
            }
        )

    # D-08 coverage over the 7-day window from week_start. Missing != no-change.
    week_dates = [week_start + timedelta(days=i) for i in range(_WEEK_DAYS)]
    missing_dates = [d.isoformat() for d in week_dates if d not in present_dates]
    coverage = {
        "present": len(daily_rows),
        "expected": _WEEK_DAYS,
        "missing_dates": missing_dates,
    }
    return net_entries, coverage


def generate_weekly_briefing(
    week_anchor: date,
    *,
    engine: Engine | None = None,
    held_tickers: set[str] | None = None,
) -> BriefingRow:
    """Load the week's <=7 dailies -> NET-aggregate -> PRE-MATERIALIZE a weekly row (SC#4).

    ``week_anchor`` IS ``week_end`` — the date ``get_briefing(date, 'weekly')`` is queried
    with (05-RESEARCH A3). The week is the 7-day window ``[week_end-6d, week_end]``. Loads
    the daily payloads via ``store.get_daily_briefings_in_range`` (already ordered by
    ``report_date``), computes the per-ticker NET change via :func:`aggregate_net` (flat
    dicts), priority-sorts them with the daily's DICT-keyed ``_priority_key`` (no ``.card``
    access — there is no ``DecisionCard`` at weekly time, SC#4), truncates to <=10, and
    persists a ``report_type='weekly_briefing'`` row through ``store.save_briefing``.

    The entries are computed ONCE here and stored (pre-materialized). The read path
    (``get_briefing(weekly)``, wired in 05-04) is a pure SELECT of this row — it NEVER
    re-reads the 7 dailies, so the weekly is byte-stable even if the dailies are later
    mutated/deleted (SC#4 no recompute). The payload also carries ``source_reports`` (the
    <=7 daily pointers) and ``coverage`` (D-08). Even an empty week writes a real row
    (``entries=[]``) so ``get_briefing`` returns ``found=True`` — never an empty page.

    The payload is self-describing (carries ``card_id``/``report_type``/``report_date``/
    ``generated_at``/``as_of``/``expires_at`` as ISO strings) so ``store.get_briefing_row``
    reconstructs a ``BriefingRow`` from it alone (the 05-02 write contract).

    Args:
        week_anchor: the KST ``week_end`` the weekly covers (the ``get_briefing`` key).
        engine: SQLAlchemy engine; defaults to ``db.engine.get_engine()``.
        held_tickers: injected held set for tier-1 held-first; ``None`` loads
            ``portfolio.md`` (absent -> ``set()``, held tier collapses — D-01 degradation).

    Returns:
        The persisted weekly ``BriefingRow``.
    """
    engine = engine if engine is not None else get_engine()
    held = load_held_tickers(held_tickers=held_tickers)

    week_end = week_anchor
    week_start = week_end - timedelta(days=_WEEK_DAYS - 1)

    rows = store.get_daily_briefings_in_range(engine, week_start, week_end)
    net_entries, coverage = aggregate_net(rows, week_start=week_start, week_end=week_end)

    # Priority-sort the FLAT net-entry dicts with the SAME dict-keyed key the daily uses,
    # then truncate to <=10 (D-01 / SC#1). No attribute access — plain dicts only (SC#4).
    net_entries = sorted(net_entries, key=lambda e: _priority_key(e, held))[:_MAX_ENTRIES]

    generated_at = datetime.now(_KST)
    as_of = _kst_close_on(week_end)
    expires_at = _kst_close_on(week_end + timedelta(days=7))
    card_id = f"brief_weekly_{week_end.isoformat()}"

    source_reports = [
        {"date": r.report_date.isoformat(), "card_id": r.card_id} for r in rows
    ]

    payload: dict = {
        "card_id": card_id,
        "report_type": "weekly_briefing",
        "report_date": week_end.isoformat(),
        "generated_at": generated_at.isoformat(),
        "as_of": as_of.isoformat(),
        "expires_at": expires_at.isoformat(),
        "entries": net_entries,
        "source_reports": source_reports,
        "coverage": coverage,
    }

    row = BriefingRow(
        card_id=card_id,
        report_type="weekly_briefing",
        report_date=week_end,
        generated_at=generated_at,
        as_of=as_of,
        expires_at=expires_at,
        payload=payload,
        body_md=render_body_md(net_entries),
    )
    store.save_briefing(engine, row)
    _log.info(
        "weekly briefing generated",
        extra={
            "report_date": week_end.isoformat(),
            "entry_count": len(net_entries),
            "coverage": coverage,
        },
    )
    return row
