"""``get_briefing`` — daily/weekly briefing read (Phase-5 wired to the store).

A briefing lives in ``decision_cards`` as a NULL-corp row with
``report_type ∈ {'daily_briefing', 'weekly_briefing'}`` (migration 0009) and a
``report_date`` DATE column. Phase 5 wires this tool to actually read that row via
:func:`cards.store.get_briefing_row` — the public ``type`` maps to the stored
``report_type`` and the ``date`` param matches ``report_date`` (the timezone-safe
equality path). An empty DB (no row for that date/type) is a NORMAL empty result:
``Briefing(found=False, entries=[])`` — never an error (D-01).

This module performs NO direct SQL — the SELECT is delegated to ``cards.store`` so
the SC#3 run-sql AST guard finds no ``text()`` here (mirrors ``card.py``).

Veto #13 (filter-before-context): :class:`~mcp_v2.models.Briefing` has NO
``body_md`` field, so this tool returns the structured ``entries`` ONLY — the full
human-readable 6-column table stays in the DB row and never reaches context.

Faults: an :class:`~mcp_v2.errors.InvalidArgument` for a ``type`` outside
``{"daily", "weekly"}`` or a ``date`` that is not ISO-8601 (validated before any DB
access — ASVS V5).
"""

from __future__ import annotations

from datetime import date as _date

from mcp.types import ToolAnnotations

from cards import store
from db.engine import get_engine

from .._mcp import mcp
from ..errors import InvalidArgument
from ..models import Briefing

__all__ = ["get_briefing"]

_VALID_TYPES = ("daily", "weekly")
# Public type -> stored report_type (the two briefing kinds migration 0009 allows).
_REPORT_TYPE = {"daily": "daily_briefing", "weekly": "weekly_briefing"}


def get_briefing(date: str, type: str = "daily") -> Briefing:
    """Return the briefing for ``date`` — reads the stored row via the store delegate.

    Maps the public ``type`` to the stored ``report_type``, validates ``date`` as
    ISO-8601, and delegates the SELECT to :func:`cards.store.get_briefing_row`
    (no inline SQL — SC#3). Returns the structured ``entries`` only (Veto #13 —
    the ``body_md`` table stays in the row).

    Args:
        date: the briefing date, an ISO-8601 ``YYYY-MM-DD`` string. Matched against
            the row's ``report_date`` DATE column (timezone-safe equality).
        type: ``"daily"`` (default) or ``"weekly"``.

    Returns:
        :class:`Briefing` — ``found=True`` with ``entries`` when a row exists for
        ``(report_type, report_date)``; otherwise ``found=False, entries=[]`` (D-01
        empty model, never an error).

    Raises:
        InvalidArgument: ``type`` is not in {"daily", "weekly"}, or ``date`` is not a
            valid ISO-8601 ``YYYY-MM-DD`` string (both checked before any DB access).
    """
    if type not in _VALID_TYPES:
        raise InvalidArgument("type must be 'daily' or 'weekly'")
    # ASVS V5: validate the date shape BEFORE it reaches the report_date bind.
    try:
        parsed_date = _date.fromisoformat(date)
    except ValueError as exc:
        raise InvalidArgument("date must be ISO-8601 (YYYY-MM-DD)") from exc

    report_type = _REPORT_TYPE[type]
    row = store.get_briefing_row(get_engine(), report_type, parsed_date)
    # Veto #13: return entries ONLY — the Briefing model has no body_md field, so
    # the full table never reaches context.
    return Briefing(
        date=date,
        type=type,
        found=row is not None,
        entries=(row.payload["entries"] if row is not None else []),
    )


# Register on the shared mcp via the call form (keeps get_briefing a plain
# callable for in-process callers; see filing.py for the rationale).
mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(get_briefing)
