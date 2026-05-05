"""GRAPH-01 D-22: Phase 6 get_related continues to work and now returns richer
neighbor sets when Phase 7 edges are populated."""

import pytest


@pytest.mark.skip(reason="Plan 04 Task 3 — fill fixture with Phase 7 edges, run get_related")
def test_get_related_returns_phase7_edge_types():
    """After running edges.populate() on the fixture vault, calling
    stock_mcp.tools.related.get_related(<some_doc_id>, depth=1) returns at least
    one neighbor whose edge_type is in {'mentions_ticker','filing_event',
    'ticker_sector','note_ticker','event_event','supersedes'} — the new 6-value
    enum, not the old 'mentions'/'references'/'precedes'/'same_sector' from
    tests/stock_mcp/conftest.py _seed_test_edges."""
    raise NotImplementedError
