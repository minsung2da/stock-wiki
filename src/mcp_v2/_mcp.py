"""The single shared FastMCP instance for stock-mcp-v2.

Every tool module (Plans 03-04/05/06) imports ``mcp`` from here and registers
its callable via ``@mcp.tool(...)``; ``server.py`` (Plan 03-06) imports the same
instance and calls ``mcp.run(transport="stdio")``. Keeping the instance in a tiny,
dependency-free module avoids a circular import between ``server.py`` (which must
side-effect-import the tool modules to register them) and the tool modules (which
must import ``mcp`` to decorate their callables).

``mask_error_details=True`` (VERIFIED against fastmcp 2.14.7 — the kwarg exists on
``FastMCP.__init__``): a raised :class:`~mcp_v2.errors.McpToolError` (a ``ToolError``
subclass) still surfaces its specific message to the client, while any *non*-ToolError
exception (an unexpected bug) is replaced with a generic message — the D-01 /
information-disclosure posture (RESEARCH A6, T-03-05).
"""

from __future__ import annotations

from fastmcp import FastMCP

__all__ = ["mcp"]

#: The shared FastMCP server instance. Named "stock-mcp-v2" (SC#1). Tool modules
#: register on this instance; ``server.py`` runs it over stdio.
mcp: FastMCP = FastMCP("stock-mcp-v2", mask_error_details=True)
