"""Phase 07.1 SC-3: ``graph_query`` MCP tool — BFS / community / god-nodes.

Operates over the in-memory ``networkx.DiGraph`` cached from
``vault/graph/<latest>/graph.json`` by ``stock_mcp.graph_cache.GraphCache``.
This is the accelerated path for multi-hop neighborhoods; the SQL recursive
CTE in ``tools/related.get_related`` remains the fallback when the graph
snapshot is stale or missing — the two tools coexist by design.

Threat-model mitigations (07.1-03 plan):
- T-7.1-03-01 (BFS depth DoS): hard cap depth = 5.
- T-7.1-03-04 (response-size DoS): hard cap nodes = 200.
- T-7.1-03-05 (exception leak corrupts MCP stdout): D-21 — every exception
  path returns ``to_error_response``, never raises.

No LLM dependencies. Reads only the cached graph + arguments.
"""

from __future__ import annotations

import time
from typing import Literal

import networkx as nx

from ..errors import ErrorCode, StructuredError, to_error_response
from ..graph_cache import get_graph_cache
from ..logging import log_tool_call
from ..models import GraphCommunity, GraphNode, GraphQueryResult
from .search import mcp

__all__ = ["MAX_DEPTH", "MAX_NODES", "graph_query"]

MAX_DEPTH = 5
MAX_NODES = 200


def _bfs(G: nx.DiGraph, start_id: str, depth: int) -> list[GraphNode]:
    """Reachable nodes within ``depth`` hops, excluding the start node."""
    if start_id not in G:
        raise StructuredError(
            ErrorCode.NOT_FOUND,
            f"node not in graph: {start_id}",
        )
    lengths = nx.single_source_shortest_path_length(
        G, source=start_id, cutoff=depth
    )
    out: list[GraphNode] = []
    for nid, dist in lengths.items():
        if nid == start_id:
            continue
        attrs = G.nodes[nid]
        out.append(
            GraphNode(
                id=nid,
                type=attrs.get("type"),
                label=attrs.get("label"),
                depth=dist,
            )
        )
    return out


def _community_of(G: nx.DiGraph, node_id: str) -> list[GraphCommunity]:
    """Community label + members for the node's cluster.

    Prefers ``community`` node attribute (graphify writes it via
    ``export.to_json``). Falls back to weakly-connected component when
    no per-node community label is present.
    """
    if node_id not in G:
        raise StructuredError(
            ErrorCode.NOT_FOUND,
            f"node not in graph: {node_id}",
        )
    cid = G.nodes[node_id].get("community")
    if cid is None:
        comp = nx.node_connected_component(G.to_undirected(), node_id)
        return [GraphCommunity(community_id="cc", members=sorted(comp)[:MAX_NODES])]
    members = [
        n for n, a in G.nodes(data=True) if a.get("community") == cid
    ]
    return [GraphCommunity(community_id=cid, members=members[:MAX_NODES])]


def _god_nodes(G: nx.DiGraph, top_k: int) -> list[GraphNode]:
    """Top-k highest-degree nodes (centrality proxy)."""
    if G.number_of_nodes() == 0:
        return []
    deg = sorted(G.degree(), key=lambda x: x[1], reverse=True)[:top_k]
    return [
        GraphNode(
            id=nid,
            type=G.nodes[nid].get("type"),
            label=G.nodes[nid].get("label"),
        )
        for nid, _ in deg
    ]


def graph_query(
    mode: Literal["bfs", "community", "god_nodes"],
    start_id: str | None = None,
    node_id: str | None = None,
    depth: int = 2,
    top_k: int = 10,
) -> GraphQueryResult | dict:
    """In-memory graph traversal over the latest ``vault/graph/<DATE>/graph.json``.

    ### Behavior contract
    - ``bfs(start_id, depth)``: up to ``depth``-hop reachable nodes (depth ≤ 5,
      response capped at 200 nodes). Each ``GraphNode.depth`` carries the
      shortest-path distance.
    - ``community(node_id)``: community label + member list for the node's
      cluster (uses ``community`` node attribute when present, else weakly-
      connected component as a coarse fallback).
    - ``god_nodes(top_k)``: top-k highest-degree nodes (centrality proxy,
      capped at 50).

    ### Performance
    2-hop traversal is measurably faster than ``tools/related.get_related``
    SQL recursive CTE — verified by
    ``tests/stock_mcp/test_graph_traversal_perf.py``.

    ### Errors
    Returns ``{"error": {"code": ..., "message": ..., "details": {...}}}`` —
    never raises (D-21). Codes:
    - ``NOT_FOUND``: graph snapshot missing or start/node id absent.
    - ``INTERNAL``: missing required arg, unknown mode, or unexpected failure.

    ### Performance budget
    p95 latency < 500ms at 100-node fixture. Response < 8k tokens at 200-node
    cap. DoS mitigation: depth ≤ 5, nodes ≤ 200 (T-7.1-03-01/-04).
    """
    t0 = time.perf_counter()
    args_log = {
        "mode": mode,
        "start_id": start_id,
        "node_id": node_id,
        "depth": depth,
        "top_k": top_k,
    }
    truncation: list[str] = []
    try:
        clamped = max(1, min(depth, MAX_DEPTH))
        if depth > MAX_DEPTH:
            truncation.append(f"depth-clamped to {MAX_DEPTH}")
        G = get_graph_cache().get()

        if mode == "bfs":
            if not start_id:
                raise StructuredError(
                    ErrorCode.INTERNAL,
                    "bfs mode requires start_id",
                )
            nodes = _bfs(G, start_id, clamped)
            if len(nodes) > MAX_NODES:
                nodes = nodes[:MAX_NODES]
                truncation.append(f"{MAX_NODES}-node cap")
            result = GraphQueryResult(
                mode=mode,
                nodes=nodes,
                truncation_applied=truncation,
            )
        elif mode == "community":
            if not node_id:
                raise StructuredError(
                    ErrorCode.INTERNAL,
                    "community mode requires node_id",
                )
            comms = _community_of(G, node_id)
            result = GraphQueryResult(
                mode=mode,
                communities=comms,
                truncation_applied=truncation,
            )
        elif mode == "god_nodes":
            nodes = _god_nodes(G, max(1, min(top_k, 50)))
            result = GraphQueryResult(
                mode=mode,
                nodes=nodes,
                truncation_applied=truncation,
            )
        else:
            raise StructuredError(
                ErrorCode.INTERNAL,
                f"unknown mode: {mode}",
            )

        latency = int((time.perf_counter() - t0) * 1000)
        log_tool_call(
            "graph_query",
            args_log,
            latency,
            len(result.model_dump_json()) // 4,
        )
        return result
    except StructuredError as e:
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(e)
        log_tool_call(
            "graph_query", args_log, latency, 0, error=err["error"]
        )
        return err
    except Exception as e:  # noqa: BLE001 — D-21 catch-all
        wrapped = StructuredError(ErrorCode.INTERNAL, str(e)[:200])
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(wrapped)
        log_tool_call(
            "graph_query", args_log, latency, 0, error=err["error"]
        )
        return err


mcp.tool()(graph_query)
