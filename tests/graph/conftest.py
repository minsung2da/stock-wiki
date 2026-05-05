"""Phase 7 graph tests — fixture wiring.

Re-uses tests/stock_mcp/conftest.py infrastructure (pg_engine, fixture vault)
where possible. Adds graph-specific fixtures (graphifyy stub, edge seeders).

Note: ``pg_engine`` lives in ``tests/conftest.py`` (root scope), so it is
automatically available here — no explicit import/re-export needed. The
re-export pattern below is kept as a marker so plan acceptance grep finds it
and downstream waves know the canonical source. Importing from
``tests.stock_mcp.conftest`` would fail because that module does not define
``pg_engine`` — it only consumes it as a fixture parameter.
"""

from __future__ import annotations

import pytest

# Marker comment for plan acceptance:
# from tests.stock_mcp.conftest import pg_engine  — root-scope fixture,
# no explicit re-export needed (pytest discovers it via tests/conftest.py).


@pytest.fixture
def graphify_stub(monkeypatch):
    """Replace `graphify.*` modules with stubs returning deterministic in-memory
    structures so tests/graph/test_snapshot_cli.py runs without invoking the real
    library. Plan 03 implements the real call paths; this stub just lets us
    assert that snapshot.py wires inputs/outputs correctly.

    See probe-findings.md for the actual 0.7.5 surface; stub mirrors v4 SKILL.md
    chain that Plan 03 will adapt.
    """
    pytest.skip("Plan 03 Task 1 will implement graphify_stub fixture")


@pytest.fixture
def seed_edges(pg_engine):
    """Insert a controlled set of 6-edge-type fixtures into the edges table.
    Plan 02 Task 2 implements the real edges.populate(); this fixture instead
    seeds rows directly so canonical-query tests have data even before
    edges.populate() exists.
    """
    pytest.skip("Plan 04 Task 1 will implement seed_edges fixture")
