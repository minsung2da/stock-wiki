"""stock-mcp-v2 tool callables — one module per tool cluster.

Each module registers its tool callables on the shared ``mcp`` instance
(``from .._mcp import mcp``) via ``@mcp.tool(...)`` at import time. The package
itself is an empty marker on purpose: the *side-effect aggregation* that imports
every tool module (so every ``@mcp.tool`` decorator runs) lives in
``src/mcp_v2/server.py`` (Plan 06), NOT here. Importing this package alone
registers nothing — importing ``mcp_v2.tools.filing`` (etc.) is what registers a
tool. Keeping the aggregation out of ``__init__`` avoids dragging the whole tool
surface (and its DB/embedding imports) into anything that merely touches the
package path.
"""

from __future__ import annotations
