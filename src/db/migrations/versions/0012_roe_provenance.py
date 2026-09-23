"""Preserve ROE reporting period and source independently of daily valuation."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fundamentals", sa.Column("roe_period_end", sa.Date(), nullable=True))
    op.add_column("fundamentals", sa.Column("roe_source", sa.Text(), nullable=True))
    op.add_column(
        "fundamentals", sa.Column("roe_fetched_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("fundamentals", "roe_fetched_at")
    op.drop_column("fundamentals", "roe_source")
    op.drop_column("fundamentals", "roe_period_end")
