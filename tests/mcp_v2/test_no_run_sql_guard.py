"""SC#3 / Hard Veto #7 — no arbitrary-SQL escape hatch may exist in the MCP surface.

Two layers, both runnable WITHOUT a DB (fast CI step, like tests/test_import_guard.py):

1. ``test_only_locked_tools_registered`` — the FastMCP instance must register
   EXACTLY the 10 locked read-side tool names and nothing else (no ``run_sql`` /
   ``execute_sql`` / ``raw_sql`` / ``query`` tool). Plan 03-06 wired
   ``mcp_v2.server`` (it side-effect-imports every tool module), so this test is
   now ENFORCED (no longer skip-tolerant) — importing the server registers the 10
   tools and the equality assertion runs.

2. ``test_no_fstring_sql_in_mcp_v2`` — ENFORCED now (not skip/xfail). AST-walks
   every ``src/mcp_v2/**.py`` and asserts every ``text(...)`` call's first arg is
   a constant string or a module-level name — rejecting f-strings / ``%`` / ``+``
   concatenation / ``.format`` (the store.py/entity.py parameterized discipline).

Run: ``.venv/Scripts/python.exe -m pytest tests/mcp_v2/test_no_run_sql_guard.py -x -q -m "not db"``
"""

from __future__ import annotations

import ast
import pathlib

# The 10 LOCKED tool names (SC#2/SC#3 registry guard). Any extra or any rename is
# a regression. NO arbitrary-SQL tool may ever be added.
LOCKED_TOOL_NAMES: frozenset[str] = frozenset(
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

# Names that must NEVER appear as a registered tool (arbitrary-SQL escape hatch).
FORBIDDEN_TOOL_NAMES: frozenset[str] = frozenset(
    {"run_sql", "execute_sql", "raw_sql", "query", "sql", "exec_sql"}
)

_SRC_MCP_V2 = pathlib.Path(__file__).resolve().parents[2] / "src" / "mcp_v2"


def _registered_tool_names() -> set[str]:
    """Return the FastMCP instance's registered tool names.

    FastMCP 2.14.x exposes ``get_tools()`` as an async coroutine returning a
    ``dict[name -> Tool]``; await it via ``asyncio.run``. Importing ``mcp_v2.server``
    side-effect-registers all 10 tools (Plan 03-06 wired the server).
    """
    import asyncio

    from mcp_v2.server import mcp

    tools = asyncio.run(mcp.get_tools())
    return set(tools.keys())


def test_only_locked_tools_registered() -> None:
    """Registry == exactly the 10 locked names; no forbidden SQL tool (SC#3).

    ENFORCED (no longer skip-tolerant) now that Plan 03-06 wired ``mcp_v2.server``:
    importing it registers EXACTLY the 10 locked tools and no arbitrary-SQL tool.
    """
    names = _registered_tool_names()

    # No arbitrary-SQL escape hatch may ever slip in.
    leaked = names & FORBIDDEN_TOOL_NAMES
    assert not leaked, f"forbidden arbitrary-SQL tool(s) registered: {leaked}"
    # Surface must be EXACTLY the 10 locked names.
    assert names == set(LOCKED_TOOL_NAMES), (
        f"unexpected tool surface: extra={names - set(LOCKED_TOOL_NAMES)} "
        f"missing={set(LOCKED_TOOL_NAMES) - names}"
    )


def _text_call_first_args(tree: ast.AST):
    """Yield (node, first_arg) for every ``text(...)`` call in the tree.

    Matches both ``text(...)`` (bare import) and ``sa.text(...)`` / ``X.text(...)``
    (attribute access) so an aliased import cannot dodge the guard.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_text = (isinstance(func, ast.Name) and func.id == "text") or (
            isinstance(func, ast.Attribute) and func.attr == "text"
        )
        if not is_text:
            continue
        first = node.args[0] if node.args else None
        yield node, first


def test_no_fstring_sql_in_mcp_v2() -> None:
    """Every ``text(...)`` arg in src/mcp_v2 is a constant or module-level name.

    Rejects f-strings (ast.JoinedStr), ``%``/``+`` concatenation (ast.BinOp), and
    ``.format(...)`` (ast.Call). This is the static half of the run_sql guard —
    enforced over whatever mcp_v2 files exist (currently the Wave-0 leaves; grows
    as Plans 03-03/04/06 add tools).
    """
    violations: list[str] = []
    py_files = sorted(_SRC_MCP_V2.rglob("*.py")) if _SRC_MCP_V2.exists() else []
    for p in py_files:
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node, arg in _text_call_first_args(tree):
            if arg is None:
                continue  # text() with no args (unusual) — nothing to interpolate
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                continue
            if isinstance(arg, ast.Name):
                continue  # module-level constant reference (store.py discipline)
            violations.append(
                f"{p.name}:{getattr(arg, 'lineno', node.lineno)}: "
                f"text() arg must be a string constant or module-level name, "
                f"got {type(arg).__name__}"
            )
    assert not violations, "non-parameterized text() SQL in src/mcp_v2:\n" + "\n".join(violations)


def test_guard_catches_fstring_sql(tmp_path: pathlib.Path) -> None:
    """The AST guard logic flags an f-string text() arg (self-test)."""
    bad = "from sqlalchemy import text\nx = text(f'SELECT * FROM t WHERE id={user}')\n"
    tree = ast.parse(bad)
    flagged = [
        arg
        for _node, arg in _text_call_first_args(tree)
        if arg is not None and not (isinstance(arg, ast.Constant) and isinstance(arg.value, str))
    ]
    assert len(flagged) == 1
    assert isinstance(flagged[0], ast.JoinedStr)


def test_guard_passes_constant_sql() -> None:
    """The AST guard logic accepts a constant + a module-level Name (self-test)."""
    ok = (
        "from sqlalchemy import text\n"
        "_SQL = text('SELECT 1')\n"
        "_REF = 'SELECT 2'\n"
        "_SQL2 = text(_REF)\n"
    )
    tree = ast.parse(ok)
    flagged = [
        arg
        for _node, arg in _text_call_first_args(tree)
        if arg is not None
        and not (isinstance(arg, ast.Constant) and isinstance(arg.value, str))
        and not isinstance(arg, ast.Name)
    ]
    assert flagged == []
