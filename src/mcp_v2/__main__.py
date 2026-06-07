"""stock-mcp-v2 stdio entry point (``python -m mcp_v2``).

Boots the FastMCP 2.x stdio server registered in ``.mcp.json`` (Plan 03-01). On DB
unavailability the process prints a single diagnostic line to **stderr** and exits
non-zero so Claude Code sees a clean initialization failure.

Pitfall 7 — for an MCP stdio server, **stdout IS the JSON-RPC protocol stream**.
ALL diagnostic output (the fail-fast error line, any logging) MUST go to stderr;
only FastMCP writes the protocol to stdout. A stray ``print()`` to stdout corrupts
the JSON-RPC frame and breaks the client.
"""

from __future__ import annotations

import sys

from dotenv import find_dotenv, load_dotenv

from .errors import McpToolError


def main() -> None:
    """Load env, fail-fast on DB, then run the FastMCP server over stdio."""
    load_dotenv(find_dotenv(usecwd=True))

    # Import after load_dotenv so DATABASE_URL is in the environment for get_engine.
    from .server import _check_db_connection, mcp

    try:
        _check_db_connection()
    except McpToolError as e:
        # stderr ONLY — stdout is the JSON-RPC protocol (Pitfall 7).
        print(str(e), file=sys.stderr)
        sys.exit(1)

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
