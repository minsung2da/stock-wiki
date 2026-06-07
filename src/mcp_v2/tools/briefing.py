"""``get_briefing`` — daily/weekly briefing read (Phase-3 honest empty model).

Briefing rows are a Phase-5 deliverable: the ``decision_cards`` table has NO
``report_type`` column (migration 0007 locked 12 columns; Phase 5 adds it via its
own migration). Phase 3 therefore returns an HONEST empty model (D-01) — it does
NOT query for, reference, or fake a ``report_type`` row. This is the
"no data yet" shape, not a stub that pretends to have data.

The only fault this tool can raise is an :class:`~mcp_v2.errors.InvalidArgument`
for a ``type`` outside ``{"daily", "weekly"}``.
"""

from __future__ import annotations

from mcp.types import ToolAnnotations

from .._mcp import mcp
from ..errors import InvalidArgument
from ..models import Briefing

__all__ = ["get_briefing"]

_VALID_TYPES = ("daily", "weekly")


def get_briefing(date: str, type: str = "daily") -> Briefing:
    """Return the briefing for ``date`` — Phase 3 is always an empty model (D-01).

    Phase 5 will query ``decision_cards WHERE report_type=...``; that column does
    not exist yet, so there is genuinely nothing to return. This positively
    returns ``Briefing(found=False, entries=[])`` — NOT a faked row.

    Args:
        date: the briefing date (ISO-8601 string, echoed back unparsed this phase).
        type: ``"daily"`` (default) or ``"weekly"``.

    Returns:
        :class:`Briefing` with ``found=False`` and ``entries=[]`` (D-01 empty model).

    Raises:
        InvalidArgument: ``type`` is not in {"daily", "weekly"}.
    """
    if type not in _VALID_TYPES:
        raise InvalidArgument("type must be 'daily' or 'weekly'")
    # Phase 5 wires the data; Phase 3 is an honest empty model (no report_type query).
    return Briefing(date=date, type=type, found=False, entries=[])


# Register on the shared mcp via the call form (keeps get_briefing a plain
# callable for in-process callers; see filing.py for the rationale).
mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(get_briefing)
