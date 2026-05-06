"""Phase 7.1 Plan 03 Task 1 — GraphCache lazy loader + TTL invalidation.

Tests cover:
- Lazy load on first .get() call (file system not touched at __init__).
- Picks the most recent dated subdir (KST ISO sort).
- TTL-based reload when mtime changes.
- StructuredError(NOT_FOUND) when no graph snapshot exists.
- Tolerates both `links` and `edges` JSON keys (graphify.export.to_json
  emits `links`, but legacy or alternative writers may use `edges`).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from stock_mcp.errors import ErrorCode, StructuredError
from stock_mcp.graph_cache import GraphCache


def _write_graph_json(dir_path: Path, *, key: str = "links") -> Path:
    """Write a minimal graph.json with two nodes and one edge."""
    dir_path.mkdir(parents=True, exist_ok=True)
    data = {
        "nodes": [
            {"id": "doc1", "type": "document", "label": "Doc One"},
            {"id": "doc2", "type": "document", "label": "Doc Two"},
        ],
        key: [
            {
                "source": "doc1",
                "target": "doc2",
                "edge_type": "filing_event",
                "tag": "EXTRACTED",
            }
        ],
    }
    target = dir_path / "graph.json"
    target.write_text(json.dumps(data), encoding="utf-8")
    return target


def test_get_returns_digraph(tmp_path: Path) -> None:
    """First .get() call lazy-loads graph.json into networkx.DiGraph."""
    vault_graph = tmp_path / "vault" / "graph"
    _write_graph_json(vault_graph / "2026-05-05")

    cache = GraphCache(vault_graph, ttl_seconds=3600)
    G = cache.get()

    assert G.number_of_nodes() == 2
    assert G.number_of_edges() == 1
    assert "doc1" in G
    assert "doc2" in G
    assert G.has_edge("doc1", "doc2")


def test_picks_latest_dated_directory(tmp_path: Path) -> None:
    """When multiple dated dirs exist, the lexicographically latest wins."""
    vault_graph = tmp_path / "vault" / "graph"
    _write_graph_json(vault_graph / "2026-05-01")
    # Old graph has only one node so we can detect which one was loaded.
    old_path = vault_graph / "2026-05-01" / "graph.json"
    old_path.write_text(
        json.dumps({"nodes": [{"id": "old"}], "links": []}), encoding="utf-8"
    )
    _write_graph_json(vault_graph / "2026-05-03")
    _write_graph_json(vault_graph / "2026-05-05")  # latest

    cache = GraphCache(vault_graph, ttl_seconds=3600)
    G = cache.get()

    # 2026-05-05 has 2 nodes (doc1, doc2); old dir would have 1 node ("old").
    assert G.number_of_nodes() == 2
    assert "doc1" in G


def test_stale_after_ttl_reloads(tmp_path: Path) -> None:
    """After TTL expiry, mtime change triggers reload of the new graph."""
    vault_graph = tmp_path / "vault" / "graph"
    target = _write_graph_json(vault_graph / "2026-05-05")

    cache = GraphCache(vault_graph, ttl_seconds=1)
    G1 = cache.get()
    assert G1.number_of_nodes() == 2

    # Sleep past TTL and rewrite the file with a different shape + bumped mtime.
    time.sleep(1.2)
    new_data = {
        "nodes": [
            {"id": "doc1"},
            {"id": "doc2"},
            {"id": "doc3"},
        ],
        "links": [],
    }
    target.write_text(json.dumps(new_data), encoding="utf-8")
    # Force mtime forward (write may land within same second on some FS).
    future = time.time() + 5
    import os
    os.utime(target, (future, future))

    G2 = cache.get()
    assert G2.number_of_nodes() == 3
    assert "doc3" in G2


def test_no_graph_dir_raises_not_found(tmp_path: Path) -> None:
    """Missing vault/graph dir → StructuredError(NOT_FOUND), not raw FileNotFoundError."""
    vault_graph = tmp_path / "vault" / "graph"  # not created
    cache = GraphCache(vault_graph, ttl_seconds=3600)

    with pytest.raises(StructuredError) as exc_info:
        cache.get()
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_handles_link_or_edges_key(tmp_path: Path) -> None:
    """Both `{"links": [...]}` and `{"edges": [...]}` JSON shapes load."""
    vault_graph = tmp_path / "vault" / "graph"
    # Use 'edges' instead of 'links'.
    _write_graph_json(vault_graph / "2026-05-05", key="edges")

    cache = GraphCache(vault_graph, ttl_seconds=3600)
    G = cache.get()

    assert G.number_of_nodes() == 2
    assert G.has_edge("doc1", "doc2")
