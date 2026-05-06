"""Phase 7.1 SC-3 auto-verification: 2-hop in-memory BFS vs SQL recursive CTE.

Builds a 100-node fixture (chain + sparse cross edges) in both Postgres
``edges`` and a graph.json on disk, then asserts:

1. (Correctness) ``graph_query(bfs, depth=2)`` and ``get_related(depth=2)``
   surface the same expected 2-hop document set.
2. (Latency) ``graph_query`` 2-hop median latency < SQL recursive CTE 2-hop
   median latency.
3. (Budget gate) ``graph_query`` 2-hop median latency < 500ms (absolute).

Phase 7 verification gap-2 auto-guard. Median over N=30 trials with cache
pre-warmed; numbers printed to stdout for SUMMARY capture.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from statistics import median

import sqlalchemy as sa


def _build_100_node_fixture(pg_engine, vault_graph_dir: Path) -> dict:
    """Insert 100 documents + chain/cross edges, mirror them in graph.json.

    Topology:
        chain: doc[i] -- filing_event --> doc[i+1] (i=0..98)
        cross: doc[0]->doc[5], doc[10]->doc[15], doc[20]->doc[25] (event_event)

    Expected 2-hop set from doc[0]: {doc[1] (1-hop), doc[2] (chain 2-hop),
    doc[5] (cross 1-hop), doc[6] (cross→chain 2-hop)}. Returns the start id
    plus the expected document subset that BOTH traversals must include.
    """
    with pg_engine.begin() as conn:
        conn.execute(
            sa.text(
                "TRUNCATE edges, chunks, documents, entity_aliases, entities "
                "RESTART IDENTITY CASCADE"
            )
        )

    doc_ids = [
        hashlib.sha256(f"perf-doc-{i}".encode()).hexdigest()
        for i in range(100)
    ]
    now = datetime.now(UTC)
    with pg_engine.begin() as conn:
        for i, did in enumerate(doc_ids):
            conn.execute(
                sa.text(
                    "INSERT INTO documents (id, body, source, vault_path, "
                    "first_seen_at, last_seen_at) "
                    "VALUES (:id, 'b', 'dart', :vp, :now, :now)"
                ),
                {
                    "id": did,
                    "vp": f"vault/raw/dart/2026/perf-{i}.md",
                    "now": now,
                },
            )
        # Chain via filing_event (document → document allowed).
        edges_to_insert = []
        for i in range(99):
            edges_to_insert.append(
                {
                    "st": "document",
                    "si": doc_ids[i],
                    "dt": "document",
                    "di": doc_ids[i + 1],
                    "et": "filing_event",
                    "tag": "INFERRED",
                }
            )
        # Cross edges (event_event also allowed for doc→doc).
        for i in (0, 10, 20):
            edges_to_insert.append(
                {
                    "st": "document",
                    "si": doc_ids[i],
                    "dt": "document",
                    "di": doc_ids[i + 5],
                    "et": "event_event",
                    "tag": "INFERRED",
                }
            )
        for e in edges_to_insert:
            conn.execute(
                sa.text(
                    "INSERT INTO edges (src_type, src_id, dst_type, dst_id, "
                    "edge_type, tag) "
                    "VALUES (:st, :si, :dt, :di, :et, :tag) "
                    "ON CONFLICT DO NOTHING"
                ),
                e,
            )

    # Mirror into graph.json.
    nodes = [
        {"id": did, "type": "document", "label": f"d{i}", "source_file": ""}
        for i, did in enumerate(doc_ids)
    ]
    links = []
    for i in range(99):
        links.append(
            {
                "source": doc_ids[i],
                "target": doc_ids[i + 1],
                "edge_type": "filing_event",
                "tag": "INFERRED",
            }
        )
    for i in (0, 10, 20):
        links.append(
            {
                "source": doc_ids[i],
                "target": doc_ids[i + 5],
                "edge_type": "event_event",
                "tag": "INFERRED",
            }
        )

    today_dir = vault_graph_dir / "2026-05-05"
    today_dir.mkdir(parents=True, exist_ok=True)
    (today_dir / "graph.json").write_text(
        json.dumps({"nodes": nodes, "links": links}),
        encoding="utf-8",
    )

    return {
        "start_doc_id": doc_ids[0],
        "expected_2hop_doc_ids": {doc_ids[1], doc_ids[2], doc_ids[5], doc_ids[6]},
    }


def _patch_cache(monkeypatch, vault_graph_dir: Path):
    """Inject a fresh GraphCache pointing to the perf fixture's vault/graph."""
    from stock_mcp.graph_cache import GraphCache, reset_graph_cache_singleton_for_tests
    import stock_mcp.tools.graph_query as gq_mod

    reset_graph_cache_singleton_for_tests()
    cache = GraphCache(vault_graph_dir, ttl_seconds=3600)
    monkeypatch.setattr(gq_mod, "get_graph_cache", lambda: cache)
    return cache


def test_graph_query_bfs_matches_sql_recursive(tmp_path, pg_engine, monkeypatch):
    """graph_query(bfs, depth=2) and SQL get_related(depth=2) agree on 2-hop docs."""
    vault_graph = tmp_path / "vault" / "graph"
    fixture = _build_100_node_fixture(pg_engine, vault_graph)
    _patch_cache(monkeypatch, vault_graph)

    from stock_mcp.tools.graph_query import graph_query
    from stock_mcp.tools.related import get_related

    gq_result = graph_query(
        mode="bfs", start_id=fixture["start_doc_id"], depth=2
    )
    gq_doc_ids = {n.id for n in gq_result.nodes if n.type == "document"}

    related_result = get_related(fixture["start_doc_id"], depth=2)
    sql_doc_ids = {r.id for r in related_result.related}

    assert fixture["expected_2hop_doc_ids"] <= gq_doc_ids, (
        f"graph_query missed: "
        f"{fixture['expected_2hop_doc_ids'] - gq_doc_ids}"
    )
    assert fixture["expected_2hop_doc_ids"] <= sql_doc_ids, (
        f"SQL get_related missed: "
        f"{fixture['expected_2hop_doc_ids'] - sql_doc_ids}"
    )


def test_graph_query_2hop_faster_than_sql(tmp_path, pg_engine, monkeypatch):
    """In-memory 2-hop BFS median latency < SQL recursive CTE median latency.

    Hard absolute gate: graph_query 2-hop median < 500ms.
    """
    vault_graph = tmp_path / "vault" / "graph"
    fixture = _build_100_node_fixture(pg_engine, vault_graph)
    _patch_cache(monkeypatch, vault_graph)

    from stock_mcp.tools.graph_query import graph_query
    from stock_mcp.tools.related import get_related

    # Warm cache + connection pool.
    graph_query(mode="bfs", start_id=fixture["start_doc_id"], depth=2)
    get_related(fixture["start_doc_id"], depth=2)

    N = 30
    gq_times: list[float] = []
    sql_times: list[float] = []
    for _ in range(N):
        t0 = time.perf_counter()
        graph_query(mode="bfs", start_id=fixture["start_doc_id"], depth=2)
        gq_times.append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        get_related(fixture["start_doc_id"], depth=2)
        sql_times.append(time.perf_counter() - t0)

    gq_med_ms = median(gq_times) * 1000
    sql_med_ms = median(sql_times) * 1000
    print(
        f"\nperf: graph_query 2-hop median = {gq_med_ms:.2f}ms, "
        f"SQL recursive 2-hop median = {sql_med_ms:.2f}ms (N={N})"
    )

    # Absolute budget gate.
    assert gq_med_ms < 500, f"graph_query 2-hop too slow: {gq_med_ms:.2f}ms"
    # Ratio gate: in-memory must be at least as fast as SQL.
    assert gq_med_ms < sql_med_ms, (
        f"in-memory NOT faster than SQL: "
        f"gq={gq_med_ms:.2f}ms sql={sql_med_ms:.2f}ms — investigate"
    )
