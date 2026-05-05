"""Phase 7.1 Plan 01 — sql_to_graph.build_extraction unit tests.

RED → GREEN cycle for the SQL → graphify build_from_json adapter.

The adapter reads from the live edges + entities + documents tables
(populated by Phase 2/3/7 collectors + Phase 7 edges.populate) and emits a
``{"nodes": [...], "edges": [...], "input_tokens": 0, "output_tokens": 0}``
extraction dict. graphify v4 (graphify.build.build_from_json) consumes the
exact same shape with directed=True.

Key contract notes (from inspect of graphify.build.build_from_json):
  - node dict requires ``id`` (str) and uses ``source_file`` for provenance
    (NOT ``source`` — graphify warns on the legacy alias).
  - edge dict requires ``source`` (= src node id) + ``target`` (= dst node id);
    ``from``/``to`` are tolerated aliases. We emit the canonical pair.
  - extra keys on nodes/edges (type, label, edge_type, tag, weight) survive as
    networkx attributes after build_from_json.
"""

from __future__ import annotations

import networkx as nx
import pytest
import sqlalchemy as sa

import graphify.build as gbuild
from graph.sql_to_graph import build_extraction
from ingest.edges import populate as populate_edges


@pytest.fixture
def truncate_all(pg_engine):
    """Empty edges/documents/entities so test_empty_db_* gets a clean slate.

    pg_engine is session-scoped (root conftest) — without truncation, prior
    fixtures bleed in.
    """
    with pg_engine.begin() as conn:
        conn.execute(
            sa.text(
                "TRUNCATE edges, chunks, documents, entity_aliases, entities "
                "RESTART IDENTITY CASCADE"
            )
        )
    return pg_engine


def test_empty_db_returns_empty_extraction(truncate_all):
    """Empty DB → empty extraction. No exceptions, deterministic shape."""
    result = build_extraction(truncate_all)
    assert result == {
        "nodes": [],
        "edges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }


def test_empty_extraction_round_trips_through_build_from_json(truncate_all):
    """graphify.build.build_from_json must accept the empty extraction
    without raising and return a networkx.DiGraph."""
    result = build_extraction(truncate_all)
    G = gbuild.build_from_json(result, directed=True)
    assert isinstance(G, nx.DiGraph)
    assert G.number_of_nodes() == 0
    assert G.number_of_edges() == 0


def test_seed_edges_full_extraction(seed_edges, pg_engine):
    """All 6 edge_types from edges.populate() round-trip into the extraction.

    Validates:
      - documents/ticker/sector/event nodes are all materialised
      - mentions_ticker, note_ticker, ticker_sector, filing_event, event_event
        are all present
      - tag column is preserved per EDGE_TAG_POLICY
      - every node has the graphify-required keys
      - graphify.build.build_from_json returns a non-empty DiGraph (SC-1 seed)
    """
    seeded = seed_edges(with_event_chain=True)
    with pg_engine.begin() as conn:
        populate_edges(seeded["doc_ids"], conn)

    result = build_extraction(pg_engine)

    node_types = {n["type"] for n in result["nodes"]}
    assert {"document", "ticker", "sector", "event"} <= node_types

    edge_types = {e["edge_type"] for e in result["edges"]}
    assert {
        "mentions_ticker",
        "note_ticker",
        "ticker_sector",
        "filing_event",
        "event_event",
    } <= edge_types

    for e in result["edges"]:
        assert e["tag"] in {"EXTRACTED", "INFERRED"}
        if e["edge_type"] == "mentions_ticker":
            assert e["tag"] == "EXTRACTED"
        if e["edge_type"] == "filing_event":
            assert e["tag"] == "INFERRED"

    for n in result["nodes"]:
        assert {"id", "type", "label", "source_file"} <= set(n.keys())

    # graphify round-trip: SC-1 seed (graph.json populated with nodes/links).
    G = gbuild.build_from_json(result, directed=True)
    assert isinstance(G, nx.DiGraph)
    assert G.number_of_nodes() > 0
    assert G.number_of_edges() > 0


def test_ticker_label_uses_canonical_name(seed_edges, pg_engine):
    """ticker node label must come from entities.canonical_name when present."""
    seeded = seed_edges(with_event_chain=False)
    with pg_engine.begin() as conn:
        populate_edges(seeded["doc_ids"], conn)

    result = build_extraction(pg_engine)
    ticker_nodes = {n["id"]: n for n in result["nodes"] if n["type"] == "ticker"}
    assert seeded["samsung_ticker"] in ticker_nodes
    assert ticker_nodes[seeded["samsung_ticker"]]["label"] == "삼성전자"


def test_idempotent(seed_edges, pg_engine):
    """Calling build_extraction twice on the same DB returns the same id sets."""
    seeded = seed_edges(with_event_chain=True)
    with pg_engine.begin() as conn:
        populate_edges(seeded["doc_ids"], conn)

    r1 = build_extraction(pg_engine)
    r2 = build_extraction(pg_engine)

    ids1 = {n["id"] for n in r1["nodes"]}
    ids2 = {n["id"] for n in r2["nodes"]}
    assert ids1 == ids2

    edges1 = {(e["source"], e["target"], e["edge_type"]) for e in r1["edges"]}
    edges2 = {(e["source"], e["target"], e["edge_type"]) for e in r2["edges"]}
    assert edges1 == edges2
