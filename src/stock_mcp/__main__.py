"""stock-mcp entry point (D-20, D-24, MCP-01).

`uv run stock-mcp` → runs a FastMCP 2.x stdio server. On DB unavailability
the process exits non-zero with a structured error line on stderr so
Claude Code sees a clean initialization failure.
"""

from __future__ import annotations

import json
import sys

from dotenv import find_dotenv, load_dotenv

from .errors import StructuredError, to_error_response


def main() -> None:
    load_dotenv(find_dotenv(usecwd=True))
    from .server import _check_db_connection, mcp

    try:
        _check_db_connection()
    except StructuredError as e:
        print(json.dumps(to_error_response(e)), file=sys.stderr)
        sys.exit(1)

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
