"""Phase 6: relax edges.edge_type CHECK so test fixtures can insert non-supersedes edges.

Phase 7 (GRAPH-01) will redefine the edge taxonomy; until then we drop the
CHECK so Phase 6 fixture corpus + tests for `get_related` can use realistic
edge_type values (mentions, references, precedes, same_sector, supersedes).

The original constraint name from migration 0001 is `ck_edge_type_phase2`.
We use IF EXISTS so re-running upgrade is idempotent.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-28
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE edges DROP CONSTRAINT IF EXISTS ck_edge_type_phase2")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE edges ADD CONSTRAINT ck_edge_type_phase2 "
        "CHECK (edge_type IN ('supersedes'))"
    )
