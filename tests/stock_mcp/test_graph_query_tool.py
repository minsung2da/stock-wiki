"""Phase 7.1 Plan 03 Task 2 — graph_query MCP tool.

Tests for bfs / community / god_nodes modes, depth clamp (DoS guard),
and D-21 catch-all error mapping. Uses an in-memory networkx.DiGraph
stub injected via monkeypatch so no DB or vault file is touched.
"""

from __future__ import annotations

import networkx as nx
import pytest


def _seed_graph() -> nx.DiGraph:
    """Build a small 6-node DiGraph for traversal tests.

    Topology:
        doc1 -> doc2 -> doc3 -> doc4
        doc1 -> ticker1
        doc2 -> ticker2
    Communities: {doc1, doc2, ticker1, ticker2} = 1; {doc3, doc4} = 2.
    """
    G = nx.DiGraph()
    G.add_node("doc1", type="document", label="Doc 1", community=1)
    G.add_node("doc2", type="document", label="Doc 2", community=1)
    G.add_node("doc3", type="document", label="Doc 3", community=2)
    G.add_node("doc4", type="document", label="Doc 4", community=2)
    G.add_node("ticker1", type="ticker", label="삼성전자", community=1)
    G.add_node("ticker2", type="ticker", label="SK하이닉스", community=1)
    G.add_edge("doc1", "doc2", edge_type="filing_event", tag="EXTRACTED")
    G.add_edge("doc2", "doc3", edge_type="filing_event", tag="INFERRED")
    G.add_edge("doc3", "doc4", edge_type="supersedes", tag="EXTRACTED")
    G.add_edge("doc1", "ticker1", edge_type="mentions_ticker", tag="EXTRACTED")
    G.add_edge("doc2", "ticker2", edge_type="mentions_ticker", tag="EXTRACTED")
    return G


@pytest.fixture
def stub_cache(monkeypatch):
    """Inject a stub graph cache returning the seeded DiGraph."""
    import stock_mcp.tools.graph_query as gq_mod
    G = _seed_graph()

    class _StubCache:
        def get(self) -> nx.DiGraph:
            return G

    stub = _StubCache()
    monkeypatch.setattr(gq_mod, "get_graph_cache", lambda: stub)
    return G


def test_bfs_returns_2hop_neighbors(stub_cache):
    from stock_mcp.tools.graph_query import graph_query
    result = graph_query(mode="bfs", start_id="doc1", depth=2)

    # Must return a Pydantic model (not error dict).
    assert hasattr(result, "mode")
    assert result.mode == "bfs"
    ids = {n.id for n in result.nodes}
    # 1-hop: doc2, ticker1; 2-hop: doc3, ticker2
    assert {"doc2", "ticker1", "doc3", "ticker2"} <= ids
    # depth attribute is populated
    depth_by_id = {n.id: n.depth for n in result.nodes}
    assert depth_by_id["doc2"] == 1
    assert depth_by_id["ticker1"] == 1
    assert depth_by_id["doc3"] == 2


def test_community_lookup(stub_cache):
    from stock_mcp.tools.graph_query import graph_query
    result = graph_query(mode="community", node_id="doc1")

    assert result.mode == "community"
    assert len(result.communities) == 1
    comm = result.communities[0]
    assert comm.community_id == 1
    assert {"doc1", "doc2", "ticker1", "ticker2"} <= set(comm.members)


def test_god_nodes_top_k(stub_cache):
    from stock_mcp.tools.graph_query import graph_query
    result = graph_query(mode="god_nodes", top_k=3)

    assert result.mode == "god_nodes"
    assert len(result.nodes) == 3
    # doc1 has degree 2 (out: doc2, ticker1), doc2 has degree 3 (in: doc1; out: doc3, ticker2)
    # doc2 should be the highest-degree node.
    top_id = result.nodes[0].id
    assert top_id == "doc2"


def test_depth_clamped_to_5(stub_cache):
    from stock_mcp.tools.graph_query import graph_query, MAX_DEPTH
    result = graph_query(mode="bfs", start_id="doc1", depth=99)

    assert result.mode == "bfs"
    # truncation note recorded
    assert any(f"depth-clamped to {MAX_DEPTH}" in t for t in result.truncation_applied)


def test_unknown_start_id_returns_not_found(stub_cache):
    from stock_mcp.tools.graph_query import graph_query
    result = graph_query(mode="bfs", start_id="does-not-exist", depth=2)

    # Error envelope, not Pydantic model
    assert isinstance(result, dict)
    assert result["error"]["code"] == "NOT_FOUND"


def test_graph_missing_returns_not_found(monkeypatch):
    """When the cache itself raises NOT_FOUND, the tool maps it cleanly."""
    import stock_mcp.tools.graph_query as gq_mod
    from stock_mcp.errors import ErrorCode, StructuredError

    class _BrokenCache:
        def get(self):
            raise StructuredError(ErrorCode.NOT_FOUND, "no graph snapshot found")

    monkeypatch.setattr(gq_mod, "get_graph_cache", lambda: _BrokenCache())

    from stock_mcp.tools.graph_query import graph_query
    result = graph_query(mode="bfs", start_id="doc1", depth=2)

    assert isinstance(result, dict)
    assert result["error"]["code"] == "NOT_FOUND"


def test_invalid_mode_returns_error(stub_cache):
    from stock_mcp.tools.graph_query import graph_query
    # Bypass type check at runtime — pydantic Literal check happens at result
    # construction; the mode dispatch falls into the "unknown mode" branch.
    result = graph_query(mode="not_a_mode", start_id="doc1")  # type: ignore[arg-type]

    assert isinstance(result, dict)
    assert result["error"]["code"] == "INTERNAL"


def test_bfs_missing_start_id_returns_error(stub_cache):
    """bfs mode without start_id → INTERNAL error response (no raise)."""
    from stock_mcp.tools.graph_query import graph_query
    result = graph_query(mode="bfs", depth=2)
    assert isinstance(result, dict)
    assert result["error"]["code"] == "INTERNAL"
