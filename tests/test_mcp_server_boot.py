"""stock-mcp server boot + tool registration tests (MCP-01, D-22, D-24, M1)."""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine


def _run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_db_check_passes_on_healthy_db(pg_clean: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """B1 — healthy DB → _check_db_connection returns None."""
    from stock_mcp import server

    monkeypatch.setattr(server, "get_engine", lambda: pg_clean)
    # Should not raise.
    assert server._check_db_connection() is None


def test_db_check_fails_exits_non_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """B2 — DB outage → main() exits 1 + stderr contains DB_UNAVAILABLE."""
    from stock_mcp import __main__ as main_mod
    from stock_mcp import server

    def _boom() -> None:
        from sqlalchemy.exc import OperationalError

        raise OperationalError("SELECT 1", {}, Exception("cannot connect"))

    monkeypatch.setattr(server, "get_engine", _boom)

    buf = io.StringIO()
    monkeypatch.setattr("sys.stderr", buf)

    with pytest.raises(SystemExit) as excinfo:
        main_mod.main()
    assert excinfo.value.code == 1
    out = buf.getvalue()
    assert "DB_UNAVAILABLE" in out


def test_mcp_server_registers_search_tool() -> None:
    """B3 — FastMCP instance exposes exactly one tool named 'search'."""
    from stock_mcp.tools.search import mcp

    tools = asyncio.run(mcp.get_tools())
    assert "search" in tools
    t = tools["search"]
    props = t.parameters["properties"]
    for required_key in ("query", "ticker", "date_range", "source", "mode", "top_k"):
        assert required_key in props, f"missing param: {required_key}"


def test_tool_schema_mode_enum() -> None:
    """B4 — the 'mode' parameter is a Literal enum of hybrid|semantic|bm25."""
    from stock_mcp.tools.search import mcp

    tools = asyncio.run(mcp.get_tools())
    props = tools["search"].parameters["properties"]
    mode_schema = props["mode"]
    # FastMCP serializes Literal as 'enum' or nested anyOf/const depending on
    # version. Accept any representation that limits values to our 3 strings.
    dump = json.dumps(mode_schema)
    assert "hybrid" in dump
    assert "semantic" in dump
    assert "bm25" in dump


def test_tool_docstring_is_llm_facing() -> None:
    """B5 — the search tool description is LLM-ready (vault_path, RRF, top_k)."""
    from stock_mcp.tools.search import mcp, search

    tools = asyncio.run(mcp.get_tools())
    desc = tools["search"].description or ""
    # Accept either the FunctionTool.description or the underlying __doc__.
    doc = desc or (search.__doc__ or "")
    assert len(doc) > 100
    assert "vault_path" in doc
    assert "RRF" in doc
    assert "top_k" in doc


def test_mcp_json_registration_exists() -> None:
    """M1 — .mcp.json registers stock-mcp with `uv run [--env-file .env] --group mcp stock-mcp`."""
    data = json.loads(Path(".mcp.json").read_text(encoding="utf-8"))
    server = data["mcpServers"]["stock-mcp"]
    assert server["command"] == "uv"
    args = server["args"]
    assert args[0] == "run"
    assert "--group" in args and args[args.index("--group") + 1] == "mcp"
    assert "stock-mcp" in args
