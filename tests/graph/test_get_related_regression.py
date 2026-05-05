"""GRAPH-01 D-22: Phase 6 get_related continues to work and now returns
neighbors with the new 6-value Phase 7 edge_type enum (not the legacy
mentions/references/precedes/same_sector quartet)."""

from __future__ import annotations

import sys

from ingest.edges import populate
from stock_mcp.tools.related import get_related

PHASE7_ENUM = {
    "mentions_ticker",
    "filing_event",
    "note_ticker",
    "event_event",
    "ticker_sector",
    "supersedes",
}
LEGACY_ENUM = {"mentions", "references", "precedes", "same_sector"}


def test_get_related_returns_phase7_edge_types(seed_edges, pg_engine):
    """After Plan 02 edges.populate() runs against the seeded fixture, calling
    ``get_related(<doc_id>, depth=1)`` returns at least one RelatedRow whose
    edge_type is in the Phase 7 6-value enum, and never a legacy value."""
    seeded = seed_edges()
    assert seeded["doc_ids"], "seed_edges must produce at least one document"
    with pg_engine.begin() as conn:
        populate(seeded["doc_ids"], conn)

    seed_doc = seeded["doc_ids"][0]  # the DART filing
    result = get_related(seed_doc, depth=1)

    if isinstance(result, dict) and "error" in result:
        raise AssertionError(f"get_related returned error: {result}")

    edge_types = {row.edge_type for row in result.related}
    assert edge_types & PHASE7_ENUM, f"No Phase 7 edge_types in result; got {edge_types}"
    assert not (edge_types & LEGACY_ENUM), (
        f"Legacy edge_types still present: {edge_types & LEGACY_ENUM}"
    )


def test_get_related_does_not_regress_phase6_sql_only(seed_edges, pg_engine):
    """Phase 6 D-06: get_related uses SQL on edges only (no graphify dependency).
    Confirm by removing graphify modules from sys.modules and verifying the
    call still succeeds — proves SQL-only contract preserved."""
    seeded = seed_edges()
    with pg_engine.begin() as conn:
        populate(seeded["doc_ids"], conn)

    monkeypatched: dict[str, object] = {}
    for name in list(sys.modules):
        if name == "graphify" or name.startswith("graphify."):
            monkeypatched[name] = sys.modules.pop(name)
    try:
        result = get_related(seeded["doc_ids"][0], depth=1)
        assert not (isinstance(result, dict) and "error" in result), (
            f"get_related failed without graphify modules: {result}"
        )
    finally:
        sys.modules.update(monkeypatched)
