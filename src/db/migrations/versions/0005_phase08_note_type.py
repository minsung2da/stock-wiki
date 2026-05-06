"""Phase 8 — add documents.note_type column for memo dispatch (D-15).

NOTE-03 indexes ``notes/private/**/*.md`` thesis/journal/conviction/note memos
into the documents table. ``note_type`` mirrors the frontmatter ``type`` so
the search MCP tool can filter (e.g. "show me my thesis notes for 005930").

Existing rows whose ``source = 'private_note'`` are backfilled to ``'note'``
(the safe D-15 default). Non-private documents stay NULL — they have no
note_type semantics.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("note_type", sa.Text, nullable=True),
    )
    op.create_index("ix_documents_note_type", "documents", ["note_type"])
    # Backfill: existing private_note rows default to 'note' (D-15).
    op.execute(
        "UPDATE documents SET note_type = 'note' "
        "WHERE source = 'private_note' AND note_type IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_documents_note_type", table_name="documents")
    op.drop_column("documents", "note_type")
