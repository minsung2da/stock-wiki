"""Tests for supersedes edges + recursive CTE walk (ENT-03)."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from tests.fixtures_loader import load_entity_fixture

# Walk supersedes chain forward from :starting_doc_id; terminal = last dst.
# Cycle guard: WHERE c.depth < 20 (threat T-02-13).
RECURSIVE_FINAL = sa.text("""
WITH RECURSIVE chain(src_id, dst_id, depth) AS (
    SELECT src_id, dst_id, 1
    FROM edges
    WHERE edge_type = 'supersedes' AND src_id = :starting_doc_id
  UNION ALL
    SELECT e.src_id, e.dst_id, c.depth + 1
    FROM edges e JOIN chain c ON e.src_id = c.dst_id
    WHERE e.edge_type = 'supersedes' AND c.depth < 20
)
SELECT dst_id FROM chain ORDER BY depth DESC LIMIT 1
""")


def test_amendment_returns_latest_doc(pg_clean):
    load_entity_fixture(pg_clean, "fixtures/entities/amendment_case.yaml")
    start = "0000000000000000000000000000000000000000000000000000000000000001"
    with pg_clean.connect() as conn:
        final = conn.execute(RECURSIVE_FINAL, {"starting_doc_id": start}).scalar()
    assert final == "0000000000000000000000000000000000000000000000000000000000000002"


def test_no_amendment_returns_none(pg_clean):
    load_entity_fixture(pg_clean, "fixtures/entities/amendment_case.yaml")
    # Doc id with no outgoing supersedes edge.
    start = "0000000000000000000000000000000000000000000000000000000000000099"
    with pg_clean.connect() as conn:
        final = conn.execute(RECURSIVE_FINAL, {"starting_doc_id": start}).scalar()
    assert final is None


def test_edge_unique_prevents_duplicate_insert(pg_clean):
    load_entity_fixture(pg_clean, "fixtures/entities/amendment_case.yaml")
    with pytest.raises(IntegrityError), pg_clean.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO edges (src_type, src_id, dst_type, dst_id, edge_type)
                VALUES ('document',
                        '0000000000000000000000000000000000000000000000000000000000000001',
                        'document',
                        '0000000000000000000000000000000000000000000000000000000000000002',
                        'supersedes')
                """
            )
        )
