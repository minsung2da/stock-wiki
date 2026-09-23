"""Retain pykrx dividend yield (percent) and DPS (KRW/share)."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fundamentals", sa.Column("dividend_yield", sa.Numeric(18, 4), nullable=True))
    op.add_column("fundamentals", sa.Column("dps", sa.Numeric(20, 4), nullable=True))


def downgrade() -> None:
    op.drop_column("fundamentals", "dps")
    op.drop_column("fundamentals", "dividend_yield")
