"""Separate market date, financial reporting periods and ROE report type."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fundamentals", sa.Column("market_asof", sa.Date(), nullable=True))
    op.add_column("fundamentals", sa.Column("metric_periods", postgresql.JSONB(), nullable=True))
    op.add_column("fundamentals", sa.Column("roe_report_code", sa.Text(), nullable=True))
    op.execute(
        "UPDATE fundamentals SET roe_report_code='11011' "
        "WHERE roe_source LIKE '%reprt_code=11011&%' AND roe IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("fundamentals", "roe_report_code")
    op.drop_column("fundamentals", "metric_periods")
    op.drop_column("fundamentals", "market_asof")
