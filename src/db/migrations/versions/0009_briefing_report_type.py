"""Phase 5 — decision_cards: briefing rows (report_type / report_date).

Phase 5 stores each daily/weekly briefing as a ``decision_cards`` row
(SC#2). A briefing row lives in ``decision_cards`` but is NOT a
``DecisionCard`` — it has no single corp, no stance/conviction, no
per-ticker assumptions (05-RESEARCH §"THE LANDMINE"). This migration makes
the table able to hold such a row WITHOUT breaking the single-ticker
analysis-card invariant.

What this migration does
------------------------
  * ADD ``report_type TEXT NULL`` — the card KIND (NULL = an analysis card;
    ``'daily_briefing'`` / ``'weekly_briefing'`` = a briefing row). Orthogonal
    to ``status`` (the lifecycle column active/superseded/invalidated).
  * ADD ``report_date DATE NULL`` — the KST calendar date a briefing covers,
    matched by equality via ``get_briefing`` (timezone-safe, unlike a
    ``generated_at::date`` under UTC — 05-RESEARCH Pitfall #3).
  * ALTER ``corp_code`` DROP NOT NULL — a briefing row has no single corp.
  * CHECK ``ck_decision_cards_report_type`` — constrain ``report_type`` to the
    two known kinds (or NULL).
  * CHECK ``ck_decision_cards_corp_or_report`` — PRESERVE the analysis-card
    invariant: a non-briefing row (``report_type IS NULL``) STILL requires
    ``corp_code``. A briefing row cannot masquerade as an analysis card, and an
    analysis card cannot lose its corp_code (T-05-01-01).
  * PARTIAL INDEX ``ix_decision_cards_report`` on ``(report_type, report_date)``
    ``WHERE report_type IS NOT NULL`` — serves ``get_briefing``'s
    ``WHERE report_type=? AND report_date=?`` seek (mirrors the 0008 partial
    ``ix_notes_corp`` / ``ix_fundamentals_corp`` idiom).

Downgrade footgun (T-05-01-02)
------------------------------
Re-adding ``corp_code NOT NULL`` fails if any NULL-corp briefing rows exist.
``downgrade()`` therefore ``DELETE``s the briefing rows
(``report_type IS NOT NULL``) BEFORE ``ALTER COLUMN corp_code SET NOT NULL``.

No tsvector column is added or touched — PG17 ships no ``'korean'`` config and
the existing GENERATED ``'simple'`` ``body_tsv`` (0007) auto-covers the briefing
``body_md`` for free (05-RESEARCH Pitfall #2).

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # report_type = the card KIND (NULL = analysis card; a briefing sets one of
    # the two known values). report_date = the KST calendar date the briefing
    # covers (equality-matchable, timezone-safe).
    op.add_column("decision_cards", sa.Column("report_type", sa.Text, nullable=True))
    op.add_column("decision_cards", sa.Column("report_date", sa.Date, nullable=True))

    # Allow NULL corp_code for briefing rows (they have no single corp).
    op.alter_column("decision_cards", "corp_code", nullable=True)

    # Constrain report_type to the two known kinds (NULL = an analysis card).
    op.create_check_constraint(
        "ck_decision_cards_report_type",
        "decision_cards",
        "report_type IS NULL OR report_type IN ('daily_briefing','weekly_briefing')",
    )

    # PRESERVE the analysis-card invariant: a non-briefing row still requires
    # corp_code. A briefing row (report_type set) may have NULL corp_code.
    op.create_check_constraint(
        "ck_decision_cards_corp_or_report",
        "decision_cards",
        "report_type IS NOT NULL OR corp_code IS NOT NULL",
    )

    # Serve get_briefing's WHERE report_type=? AND report_date=? — partial index
    # over ONLY briefing rows (mirrors 0008's partial ix_notes_corp /
    # ix_fundamentals_corp).
    op.create_index(
        "ix_decision_cards_report",
        "decision_cards",
        ["report_type", "report_date"],
        postgresql_where=sa.text("report_type IS NOT NULL"),
    )


def downgrade() -> None:
    # Strict LIFO reversal. The DELETE MUST run before restoring corp_code
    # NOT NULL — NULL-corp briefing rows would otherwise fail the ALTER
    # (downgrade footgun, T-05-01-02).
    op.drop_index("ix_decision_cards_report", table_name="decision_cards")
    op.execute("DELETE FROM decision_cards WHERE report_type IS NOT NULL")
    op.drop_constraint("ck_decision_cards_corp_or_report", "decision_cards", type_="check")
    op.drop_constraint("ck_decision_cards_report_type", "decision_cards", type_="check")
    op.alter_column("decision_cards", "corp_code", nullable=False)
    op.drop_column("decision_cards", "report_date")
    op.drop_column("decision_cards", "report_type")
