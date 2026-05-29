"""KRX db_writer unit tests — Plan 01-04 Task 1 behavior contract.

upsert_ohlcv contract:
- Returns 'inserted' | 'updated' | 'skipped'
- Plain `dict` inputs for OHLCV row, optional flow_row, optional short_row
- COALESCE pattern on short_volume/short_balance/corp_code so a same-day
  fresh fetch (e.g. T+2 short fill-in) NEVER overwrites populated short
  columns with NULL
- OHLCV (open/high/low/close/volume) ALWAYS overwritten (price corrections
  do happen)
- 'skipped' means no value would change (fetched_at is preserved — the
  optimization vs blindly UPDATE-ing every call)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from collectors.krx import db_writer

pytestmark = pytest.mark.db


# ----- Helpers -----


def _seed_entity(engine, corp_code: str = "00126380", ticker: str = "005930") -> None:
    """Insert one (entities, entity_aliases) row for FK satisfaction."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entities (corp_code, canonical_name, current_ticker, market) "
                "VALUES (:cc, :name, :t, 'KOSPI') ON CONFLICT (corp_code) DO NOTHING"
            ),
            {"cc": corp_code, "name": "삼성전자", "t": ticker},
        )


def _row(engine, ticker: str, trade_date: date):
    """SELECT the single ohlcv row for assertion."""
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT ticker, trade_date, open, high, low, close, volume, "
                "trading_value, foreign_net, inst_net, retail_net, "
                "short_volume, short_balance, corp_code, fetched_at "
                "FROM ohlcv WHERE ticker=:t AND trade_date=:d"
            ),
            {"t": ticker, "d": trade_date},
        ).first()


_BASE_OHLCV = {
    "open": Decimal("70000"),
    "high": Decimal("71000"),
    "low": Decimal("69500"),
    "close": Decimal("70500"),
    "volume": 12345678,
}

_BASE_FLOW = {
    "trading_value": 870000000000,
    "foreign_net": 12000000000,
    "inst_net": -3000000000,
    "retail_net": -9000000000,
}

_BASE_SHORT = {"short_volume": 1234567, "short_balance": 87000000000}


# ----- Tests -----


def test_upsert_ohlcv_inserts_fresh(pg_clean) -> None:
    _seed_entity(pg_clean)

    outcome = db_writer.upsert_ohlcv(
        pg_clean,
        ticker="005930",
        trade_date=date(2026, 4, 17),
        corp_code="00126380",
        ohlcv_row=_BASE_OHLCV,
        flow_row=_BASE_FLOW,
        short_row=_BASE_SHORT,
    )
    assert outcome == "inserted"

    row = _row(pg_clean, "005930", date(2026, 4, 17))
    assert row is not None
    assert row.open == Decimal("70000.0000")
    assert row.close == Decimal("70500.0000")
    assert row.volume == 12345678
    assert row.trading_value == 870000000000
    assert row.short_volume == 1234567
    assert row.corp_code == "00126380"


def test_upsert_ohlcv_idempotent_same_values(pg_clean) -> None:
    _seed_entity(pg_clean)

    db_writer.upsert_ohlcv(
        pg_clean,
        ticker="005930",
        trade_date=date(2026, 4, 17),
        corp_code="00126380",
        ohlcv_row=_BASE_OHLCV,
        flow_row=_BASE_FLOW,
        short_row=_BASE_SHORT,
    )
    row1 = _row(pg_clean, "005930", date(2026, 4, 17))
    fetched1 = row1.fetched_at

    outcome2 = db_writer.upsert_ohlcv(
        pg_clean,
        ticker="005930",
        trade_date=date(2026, 4, 17),
        corp_code="00126380",
        ohlcv_row=_BASE_OHLCV,
        flow_row=_BASE_FLOW,
        short_row=_BASE_SHORT,
    )
    assert outcome2 == "skipped"

    row2 = _row(pg_clean, "005930", date(2026, 4, 17))
    # fetched_at MUST NOT bump on skip — this is the optimization
    assert row2.fetched_at == fetched1


def test_upsert_ohlcv_short_fillin(pg_clean) -> None:
    """T+2 COALESCE pattern: short_row=None on D, populated D+2; OHLCV
    columns NOT touched, only short columns filled.
    """
    _seed_entity(pg_clean)

    # Day 1: short data not yet available (T-day)
    db_writer.upsert_ohlcv(
        pg_clean,
        ticker="005930",
        trade_date=date(2026, 4, 17),
        corp_code="00126380",
        ohlcv_row=_BASE_OHLCV,
        flow_row=_BASE_FLOW,
        short_row=None,
    )
    row1 = _row(pg_clean, "005930", date(2026, 4, 17))
    assert row1.short_volume is None
    assert row1.short_balance is None
    assert row1.close == Decimal("70500.0000")

    # Day 3 (T+2): short numbers arrive; OHLCV unchanged
    outcome = db_writer.upsert_ohlcv(
        pg_clean,
        ticker="005930",
        trade_date=date(2026, 4, 17),
        corp_code="00126380",
        ohlcv_row=_BASE_OHLCV,
        flow_row=_BASE_FLOW,
        short_row={"short_volume": 5000, "short_balance": 12000},
    )
    assert outcome == "updated"

    row2 = _row(pg_clean, "005930", date(2026, 4, 17))
    assert row2.short_volume == 5000
    assert row2.short_balance == 12000
    # OHLCV preserved
    assert row2.open == Decimal("70000.0000")
    assert row2.close == Decimal("70500.0000")
    assert row2.volume == 12345678


def test_upsert_ohlcv_short_fillin_does_not_clobber(pg_clean) -> None:
    """Once short_volume is populated, a later run with short_row=None
    MUST NOT NULL-out the existing value (COALESCE).
    """
    _seed_entity(pg_clean)

    # Populate short columns
    db_writer.upsert_ohlcv(
        pg_clean,
        ticker="005930",
        trade_date=date(2026, 4, 17),
        corp_code="00126380",
        ohlcv_row=_BASE_OHLCV,
        flow_row=_BASE_FLOW,
        short_row=_BASE_SHORT,
    )

    # Re-run with short_row=None — must preserve existing short data
    outcome = db_writer.upsert_ohlcv(
        pg_clean,
        ticker="005930",
        trade_date=date(2026, 4, 17),
        corp_code="00126380",
        ohlcv_row=_BASE_OHLCV,
        flow_row=_BASE_FLOW,
        short_row=None,
    )
    # All incoming values match existing (NULL short = no change) → skipped
    assert outcome == "skipped"
    row = _row(pg_clean, "005930", date(2026, 4, 17))
    assert row.short_volume == 1234567  # preserved
    assert row.short_balance == 87000000000


def test_upsert_ohlcv_price_correction(pg_clean) -> None:
    _seed_entity(pg_clean)

    db_writer.upsert_ohlcv(
        pg_clean,
        ticker="005930",
        trade_date=date(2026, 4, 17),
        corp_code="00126380",
        ohlcv_row=_BASE_OHLCV,
        flow_row=_BASE_FLOW,
        short_row=_BASE_SHORT,
    )

    corrected = dict(_BASE_OHLCV)
    corrected["close"] = Decimal("70800")

    outcome = db_writer.upsert_ohlcv(
        pg_clean,
        ticker="005930",
        trade_date=date(2026, 4, 17),
        corp_code="00126380",
        ohlcv_row=corrected,
        flow_row=_BASE_FLOW,
        short_row=_BASE_SHORT,
    )
    assert outcome == "updated"

    row = _row(pg_clean, "005930", date(2026, 4, 17))
    assert row.close == Decimal("70800.0000")
    assert row.open == Decimal("70000.0000")


def test_upsert_ohlcv_invalid_ticker(pg_clean) -> None:
    with pytest.raises(ValueError, match="ticker"):
        db_writer.upsert_ohlcv(
            pg_clean,
            ticker="abc123",
            trade_date=date(2026, 4, 17),
            corp_code="00126380",
            ohlcv_row=_BASE_OHLCV,
        )


def test_upsert_ohlcv_null_corp_code(pg_clean) -> None:
    """corp_code=None permitted (column is NULL-able)."""
    outcome = db_writer.upsert_ohlcv(
        pg_clean,
        ticker="005930",
        trade_date=date(2026, 4, 17),
        corp_code=None,
        ohlcv_row=_BASE_OHLCV,
        flow_row=_BASE_FLOW,
        short_row=_BASE_SHORT,
    )
    assert outcome == "inserted"

    row = _row(pg_clean, "005930", date(2026, 4, 17))
    assert row is not None
    assert row.corp_code is None


def test_upsert_ohlcv_fk_corp_code_set_null_on_entity_delete(pg_clean) -> None:
    """ohlcv.corp_code FK is ON DELETE SET NULL (per migration 0006)."""
    _seed_entity(pg_clean)

    db_writer.upsert_ohlcv(
        pg_clean,
        ticker="005930",
        trade_date=date(2026, 4, 17),
        corp_code="00126380",
        ohlcv_row=_BASE_OHLCV,
        flow_row=_BASE_FLOW,
        short_row=_BASE_SHORT,
    )

    with pg_clean.begin() as conn:
        conn.execute(text("DELETE FROM entities WHERE corp_code = '00126380'"))

    row = _row(pg_clean, "005930", date(2026, 4, 17))
    assert row is not None  # ohlcv row preserved
    assert row.corp_code is None  # FK set to NULL


def test_upsert_ohlcv_flow_row_optional(pg_clean) -> None:
    """flow_row=None permitted; those columns stay NULL."""
    _seed_entity(pg_clean)

    outcome = db_writer.upsert_ohlcv(
        pg_clean,
        ticker="005930",
        trade_date=date(2026, 4, 17),
        corp_code="00126380",
        ohlcv_row=_BASE_OHLCV,
        flow_row=None,
        short_row=None,
    )
    assert outcome == "inserted"
    row = _row(pg_clean, "005930", date(2026, 4, 17))
    assert row.trading_value is None
    assert row.foreign_net is None
