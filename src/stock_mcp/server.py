"""FastMCP server assembly for stock-mcp.

Importing this module registers the ``search`` tool (via the side-effect
import of ``stock_mcp.tools.search``) and exposes the shared ``mcp``
instance + the ``_check_db_connection`` fail-fast helper for the entry
point in ``__main__``.
"""

from __future__ import annotations

import sqlalchemy as sa

from db.engine import get_engine

from .errors import ErrorCode, StructuredError
from .tools.search import mcp  # re-export; import registers @mcp.tool

# Side-effect import: each module calls ``mcp.tool()(<callable>)`` at module
# scope, registering the Phase 6 tool surface on the shared FastMCP instance.
# Order is alphabetical for readability — registration order is irrelevant.
from .tools import (  # noqa: F401, E402  -- side-effect registration
    events,
    filing,
    health,
    notes,
    overview,
    portfolio,
    related,
)

__all__ = ["mcp", "_check_db_connection"]


def _check_db_connection() -> None:
    """D-24 fail-fast DB health check. Raises StructuredError on failure."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except Exception as e:  # noqa: BLE001 — map every failure to DB_UNAVAILABLE
        raise StructuredError(
            ErrorCode.DB_UNAVAILABLE,
            str(e)[:200],
        ) from e
