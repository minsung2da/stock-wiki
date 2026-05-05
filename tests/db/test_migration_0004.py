"""GRAPH-01: Alembic 0004 reinstates 6-value CHECK on edges.edge_type."""

import pytest


@pytest.mark.skip(reason="Plan 02 Task 1 — clean DB migration 0004 succeeds")
def test_0004_upgrade_on_clean_db_succeeds(pg_engine):
    """Fresh DB → alembic upgrade head → ck_edge_type_phase7 exists in
    pg_constraint with definition CHECK (edge_type IN (... 6 values ...))."""
    raise NotImplementedError


@pytest.mark.skip(reason="Plan 02 Task 1 — pre-validate aborts on illegal rows")
def test_0004_aborts_when_illegal_edge_type_present(pg_engine):
    """Insert row with edge_type='references' BEFORE upgrade; upgrade raises
    RuntimeError mentioning 'references' and '0004 blocked'."""
    raise NotImplementedError


@pytest.mark.skip(reason="Plan 02 Task 1 — downgrade removes only the new constraint")
def test_0004_downgrade_drops_phase7_constraint(pg_engine):
    """upgrade head → downgrade -1: ck_edge_type_phase7 is gone, edges table
    still exists, no other constraints affected."""
    raise NotImplementedError
