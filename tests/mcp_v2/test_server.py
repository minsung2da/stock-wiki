"""SC#1 — the FastMCP server registers EXACTLY the 10 locked tools over stdio.

No DB needed: importing ``mcp_v2.server`` side-effect-imports every tool module so
each ``mcp.tool(...)(fn)`` registration runs; the assertion reads the registered
names off the shared instance. This is the SC#1 gate (Plan 03-06 wires the server
that flips ``test_no_run_sql_guard::test_only_locked_tools_registered`` from skip to
enforced).

``__main__`` wiring (the stdio ``mcp.run(transport="stdio")`` entry point + the
stderr-only fail-fast) is asserted structurally here (no subprocess) — exercising
the real stdio loop would block, and the registration + transport call are the
load-bearing pieces.
"""

from __future__ import annotations

import ast
import asyncio
import pathlib

# The 10 LOCKED tool names (mirrors test_no_run_sql_guard.LOCKED_TOOL_NAMES).
LOCKED_TOOL_NAMES = frozenset(
    {
        "get_filing",
        "search_filings",
        "ohlcv_range",
        "flow_range",
        "peer_view",
        "hybrid_search",
        "get_note",
        "get_decision_card",
        "list_portfolio",
        "get_briefing",
    }
)

_SRC_MCP_V2 = pathlib.Path(__file__).resolve().parents[2] / "src" / "mcp_v2"


def _registered_names() -> set[str]:
    from mcp_v2.server import mcp

    return set(asyncio.run(mcp.get_tools()).keys())


def test_all_tools_registered() -> None:
    """SC#1: the shared mcp registers EXACTLY the 10 locked tools, nothing else."""
    names = _registered_names()
    assert names == set(LOCKED_TOOL_NAMES), (
        f"unexpected tool surface: extra={names - set(LOCKED_TOOL_NAMES)} "
        f"missing={set(LOCKED_TOOL_NAMES) - names}"
    )


def test_server_exports_check_db_connection() -> None:
    """server.py exports a callable _check_db_connection fail-fast probe."""
    from mcp_v2 import server

    assert hasattr(server, "_check_db_connection")
    assert callable(server._check_db_connection)


def test_main_runs_stdio_transport() -> None:
    """__main__.main calls mcp.run(transport='stdio') (SC#1 stdio boot).

    Structural assertion via AST — running main() would start the blocking stdio
    loop. Confirms the entry point invokes mcp.run with the stdio transport.
    """
    main_py = (_SRC_MCP_V2 / "__main__.py").read_text(encoding="utf-8")
    tree = ast.parse(main_py)
    run_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
    ]
    assert run_calls, "__main__ must call mcp.run(...)"
    # The transport kwarg must be 'stdio'.
    transports = [
        kw.value.value
        for call in run_calls
        for kw in call.keywords
        if kw.arg == "transport" and isinstance(kw.value, ast.Constant)
    ]
    assert "stdio" in transports, "mcp.run must use transport='stdio'"


def test_main_logs_to_stderr_only() -> None:
    """Pitfall 7: every print() in __main__ targets sys.stderr (never stdout).

    A stray stdout write corrupts the JSON-RPC protocol frame. AST-walk asserts no
    ``print(...)`` lacks a ``file=...stderr`` keyword.
    """
    main_py = (_SRC_MCP_V2 / "__main__.py").read_text(encoding="utf-8")
    tree = ast.parse(main_py)
    bad_prints: list[int] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ):
            continue
        file_kw = next((kw for kw in node.keywords if kw.arg == "file"), None)
        if file_kw is None:
            bad_prints.append(node.lineno)
            continue
        # file= must reference stderr (sys.stderr).
        target = file_kw.value
        is_stderr = isinstance(target, ast.Attribute) and target.attr == "stderr"
        if not is_stderr:
            bad_prints.append(node.lineno)
    assert not bad_prints, f"print() to non-stderr in __main__ at lines {bad_prints}"
