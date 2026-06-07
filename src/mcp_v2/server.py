"""FastMCP server assembly for stock-mcp-v2 (SC#1).

Importing this module REGISTERS the full read-side tool surface on the shared
:data:`mcp_v2._mcp.mcp` instance by side-effect-importing every tool module — each
module calls ``mcp.tool(...)(<callable>)`` at import time. After this module is
imported, ``mcp.get_tools()`` holds EXACTLY the 10 locked tools (SC#1):

    get_filing, search_filings        (tools.filing)
    ohlcv_range, flow_range, peer_view (tools.market)
    hybrid_search                     (tools.search)
    get_note                          (tools.note)
    get_decision_card                 (tools.card)
    list_portfolio                    (tools.portfolio)
    get_briefing                      (tools.briefing)

The shared instance lives in ``_mcp.py`` (not here) to break the import cycle:
``server`` must side-effect-import the tool modules, and the tool modules must
import ``mcp`` to register on it. Importing ``_mcp`` in both places is acyclic.

Exports ``mcp`` (run by ``__main__``) and ``_check_db_connection`` (a fail-fast DB
health probe). NO arbitrary-SQL tool exists or may ever be added (SC#3 — guarded by
``tests/mcp_v2/test_no_run_sql_guard.py``).
"""

from __future__ import annotations

import sqlalchemy as sa

from db.engine import get_engine

from ._mcp import mcp
from .errors import DataBackendError

# Side-effect imports: each tool module registers its @mcp.tool callables on the
# shared ``mcp`` at import time. Order is irrelevant (alphabetical for readability).
# ``# noqa: F401`` — imported for the registration side effect, not for a name.
from .tools import (  # noqa: F401
    briefing,
    card,
    filing,
    market,
    note,
    portfolio,
    search,
)

__all__ = ["mcp", "_check_db_connection"]


def _check_db_connection() -> None:
    """Fail-fast DB health probe: ``SELECT 1`` against the configured engine.

    Raises :class:`~mcp_v2.errors.DataBackendError` (a ``ToolError`` subclass — NOT
    the archive's ``StructuredError`` dict pattern) on any failure, so ``__main__``
    can print a clean stderr line and exit non-zero before FastMCP starts the stdio
    protocol. Called once at server boot.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except Exception as e:  # noqa: BLE001 — map every failure to DataBackendError
        raise DataBackendError(f"database unavailable: {str(e)[:200]}") from e
