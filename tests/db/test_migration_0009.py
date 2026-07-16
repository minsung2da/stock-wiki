"""Phase 5 Plan 05-01 Task 3 — schema-shape + behavior regression for migration 0009.

Migration 0009 makes ``decision_cards`` able to hold briefing rows (SC#2) WITHOUT
breaking the single-ticker analysis-card invariant:

  * ADD ``report_type TEXT NULL`` + ``report_date DATE NULL``.
  * ALTER ``corp_code`` DROP NOT NULL.
  * CHECK ``ck_decision_cards_report_type`` — the two known kinds (or NULL).
  * CHECK ``ck_decision_cards_corp_or_report`` — a non-briefing row still requires
    corp_code (the analysis-card FK invariant, T-05-01-01).
  * PARTIAL INDEX ``ix_decision_cards_report`` on ``(report_type, report_date)``
    ``WHERE report_type IS NOT NULL``.

Coverage map:
* test_migration_0009_roundtrip        — up→down→up (columns/corp_code NOT NULL flip both ways)
* test_migration_0009_check_constraints— both partial CHECKs present + correct predicate
* test_migration_0009_partial_index    — ix_decision_cards_report is partial on report_type
* test_briefing_row_null_corp_insert   — NULL-corp briefing row INSERTs OK (SC#2)
* test_null_corp_analysis_card_rejected— NULL-corp analysis card REJECTED (T-05-01-01)

The roundtrip test mutates the SESSION schema; it ALWAYS restores head in a
``finally`` (mirrors tests/test_migration.py::test_downgrade_then_upgrade_idempotent)
so tests that run afterward see a fully-migrated DB. All tests are ``db``-marked.
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.db


def _alembic_cfg() -> Config:
    url = os.environ["DATABASE_URL"]
    cfg = Config("src/db/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


# ---------------------------------------------------------------------------
# up → down → up roundtrip: columns + corp_code nullability flip both ways
# ---------------------------------------------------------------------------


def test_migration_0009_roundtrip(pg_engine) -> None:
    """0009 adds report_type/report_date + relaxes corp_code; downgrade restores 0008.

    The session fixture already applied head (0009). Assert the 0009 shape, then
    downgrade to 0008 (columns gone, corp_code NOT NULL restored), then upgrade
    back to 0009 (columns present, corp_code nullable). Always restore head.
    """
    cfg = _alembic_cfg()

    def _cols() -> dict:
        return {c["name"]: c for c in inspect(pg_engine).get_columns("decision_cards")}

    try:
        # Currently at 0009 (session fixture ran `upgrade head`).
        cols = _cols()
        assert "report_type" in cols and "report_date" in cols
        assert cols["corp_code"]["nullable"] is True

        # Downgrade to 0008: the two columns disappear and corp_code is NOT NULL again.
        command.downgrade(cfg, "0008")
        cols = _cols()
        assert "report_type" not in cols, "report_type survived downgrade"
        assert "report_date" not in cols, "report_date survived downgrade"
        assert cols["corp_code"]["nullable"] is False, "corp_code NOT NULL not restored"
        idx = {i["name"] for i in inspect(pg_engine).get_indexes("decision_cards")}
        assert "ix_decision_cards_report" not in idx, "partial index survived downgrade"

        # Re-upgrade to 0009: columns back, corp_code nullable again.
        command.upgrade(cfg, "0009")
        cols = _cols()
        assert "report_type" in cols and "report_date" in cols
        assert cols["corp_code"]["nullable"] is True
    finally:
        # Always leave the session engine fully migrated for subsequent tests.
        command.upgrade(cfg, "head")


# ---------------------------------------------------------------------------
# Both partial CHECK constraints present with the correct predicates
# ---------------------------------------------------------------------------


def test_migration_0009_check_constraints(pg_engine) -> None:
    """ck_decision_cards_report_type + ck_decision_cards_corp_or_report exist."""
    with pg_engine.connect() as conn:
        report_type_ck = conn.execute(
            sa.text(
                "SELECT pg_get_constraintdef(c.oid) "
                "FROM pg_constraint c "
                "WHERE c.conrelid = 'decision_cards'::regclass "
                "  AND c.contype = 'c' "
                "  AND c.conname = 'ck_decision_cards_report_type'"
            )
        ).scalar()
        corp_or_report_ck = conn.execute(
            sa.text(
                "SELECT pg_get_constraintdef(c.oid) "
                "FROM pg_constraint c "
                "WHERE c.conrelid = 'decision_cards'::regclass "
                "  AND c.contype = 'c' "
                "  AND c.conname = 'ck_decision_cards_corp_or_report'"
            )
        ).scalar()

    assert report_type_ck is not None, "ck_decision_cards_report_type missing"
    for kind in ("daily_briefing", "weekly_briefing"):
        assert kind in report_type_ck, f"missing {kind!r} in {report_type_ck}"

    assert corp_or_report_ck is not None, "ck_decision_cards_corp_or_report missing"
    # pg normalizes to CHECK ((report_type IS NOT NULL) OR (corp_code IS NOT NULL)).
    assert "report_type" in corp_or_report_ck
    assert "corp_code" in corp_or_report_ck
    assert "IS NOT NULL" in corp_or_report_ck


# ---------------------------------------------------------------------------
# Partial index over briefing rows only
# ---------------------------------------------------------------------------


def test_migration_0009_partial_index(pg_engine) -> None:
    """ix_decision_cards_report is a partial (report_type, report_date) index."""
    with pg_engine.connect() as conn:
        idxdef = conn.execute(
            sa.text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'decision_cards' "
                "  AND indexname = 'ix_decision_cards_report'"
            )
        ).scalar()
    assert idxdef is not None, "ix_decision_cards_report missing"
    assert "report_type" in idxdef and "report_date" in idxdef, idxdef
    # Partial predicate over only briefing rows.
    assert "report_type IS NOT NULL" in idxdef, f"index is not partial: {idxdef}"


# ---------------------------------------------------------------------------
# Behavior — the analysis-card invariant (T-05-01-01)
# ---------------------------------------------------------------------------

_INSERT_BRIEFING_SQL = sa.text(
    "INSERT INTO decision_cards "
    "(card_id, corp_code, ticker, report_type, report_date, "
    " generated_at, as_of, payload, body_md, expires_at) "
    "VALUES (:card_id, NULL, NULL, :report_type, :report_date, "
    "        :generated_at, :as_of, CAST(:payload AS jsonb), :body_md, :expires_at)"
)


def test_briefing_row_null_corp_insert_succeeds(pg_clean) -> None:
    """A briefing row (report_type set) with NULL corp_code INSERTs OK (SC#2)."""
    with pg_clean.begin() as conn:
        conn.execute(
            _INSERT_BRIEFING_SQL,
            {
                "card_id": "brief_daily_2026-07-16",
                "report_type": "daily_briefing",
                "report_date": "2026-07-16",
                "generated_at": "2026-07-16T17:00:00+09:00",
                "as_of": "2026-07-16T16:00:00+09:00",
                "payload": '{"entries": []}',
                "body_md": "오늘 유의미한 변화 없음",
                "expires_at": "2026-07-17T16:00:00+09:00",
            },
        )
    with pg_clean.connect() as conn:
        got = conn.execute(
            sa.text(
                "SELECT report_type, corp_code FROM decision_cards "
                "WHERE card_id = 'brief_daily_2026-07-16'"
            )
        ).one()
    assert got.report_type == "daily_briefing"
    assert got.corp_code is None


def test_null_corp_analysis_card_rejected(pg_clean) -> None:
    """An analysis card (report_type NULL) with NULL corp_code is REJECTED.

    ck_decision_cards_corp_or_report preserves the analysis-card FK invariant —
    a NULL-corp row can only exist as a briefing (T-05-01-01).
    """
    with pytest.raises(IntegrityError) as excinfo:
        with pg_clean.begin() as conn:
            conn.execute(
                _INSERT_BRIEFING_SQL,
                {
                    "card_id": "bad_null_corp_analysis",
                    "report_type": None,  # analysis card — corp_code is required
                    "report_date": None,
                    "generated_at": "2026-07-16T17:00:00+09:00",
                    "as_of": "2026-07-16T16:00:00+09:00",
                    "payload": '{"decision": {"stance": "HOLD"}}',
                    "body_md": "no corp — must be rejected",
                    "expires_at": "2026-07-17T16:00:00+09:00",
                },
            )
    assert "ck_decision_cards_corp_or_report" in str(excinfo.value)
