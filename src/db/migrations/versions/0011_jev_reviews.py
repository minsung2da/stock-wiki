"""Add isolated Jev shadow review audit records; leave decision cards unchanged."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jev_reviews",
        sa.Column("review_id", sa.String(36), primary_key=True),
        sa.Column("task", sa.Text, nullable=False),
        sa.Column("subject_id", sa.Text, nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("prompt_version", sa.Text, nullable=False),
        sa.Column("mode", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("threshold", sa.Float, nullable=False),
        sa.Column("input_payload", postgresql.JSONB, nullable=False),
        sa.Column("result_payload", postgresql.JSONB, nullable=False),
        sa.Column("request_id", sa.Text),
        sa.Column("usage", postgresql.JSONB),
        sa.Column("error_code", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('completed', 'error')", name="ck_jev_reviews_status"),
        sa.CheckConstraint("mode IN ('off', 'shadow')", name="ck_jev_reviews_mode"),
        sa.CheckConstraint("threshold >= 0 AND threshold <= 1", name="ck_jev_reviews_threshold"),
    )
    op.create_index(
        "ix_jev_reviews_lookup", "jev_reviews", ["task", "subject_id", "input_hash", "status"]
    )
    op.create_index("ix_jev_reviews_created", "jev_reviews", ["created_at"])


def downgrade() -> None:
    op.drop_table("jev_reviews")
