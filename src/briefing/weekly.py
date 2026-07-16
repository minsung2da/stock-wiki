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

from datetime import date, timedelta

from .models import BriefingRow

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
