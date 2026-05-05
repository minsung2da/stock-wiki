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
