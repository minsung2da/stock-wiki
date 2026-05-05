"""Phase 7 GRAPH-01: reinstate edges.edge_type CHECK with 6-value enum.

Phase 2 0001 created `ck_edge_type_phase2` allowing only 'supersedes'.
Phase 6 0003 dropped that CHECK so test fixtures could use ad-hoc edge_types.
Phase 7 reinstates a CHECK with the locked 6-value taxonomy from CONTEXT D-06.

Pre-validate (RESEARCH §Pattern 2): scan existing rows for any edge_type not
in the allowed set. If found, abort with a RuntimeError listing the offenders
so silent corruption is impossible. The Phase 6 fixture conftest is updated
in the same plan so the testcontainers DB is clean before this migration runs.

Constraint name change rationale: `ck_edge_type_phase2` was DROPPED by 0003
and not re-created by name; `ck_edge_type_phase7` is a fresh constraint so
0003 downgrade cannot collide.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

ALLOWED = (
    "mentions_ticker",
    "filing_event",
    "note_ticker",
    "event_event",
    "ticker_sector",
    "supersedes",
)


def upgrade() -> None:
    bind = op.get_bind()
    bad = (
        bind.execute(
            sa.text("SELECT DISTINCT edge_type FROM edges WHERE edge_type <> ALL(:allowed)"),
            {"allowed": list(ALLOWED)},
        )
        .scalars()
        .all()
    )
    if bad:
        raise RuntimeError(
            f"Migration 0004 blocked: edges contains illegal edge_type values: "
            f"{sorted(bad)}. Either DELETE these rows, run "
            f"`stock ingest edges --rebuild` to repopulate, or extend ALLOWED."
        )
    op.execute(
        "ALTER TABLE edges ADD CONSTRAINT ck_edge_type_phase7 "
        "CHECK (edge_type IN ("
        "'mentions_ticker','filing_event','note_ticker',"
        "'event_event','ticker_sector','supersedes'"
        "))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE edges DROP CONSTRAINT IF EXISTS ck_edge_type_phase7")
