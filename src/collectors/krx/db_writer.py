"""KRX db_writer — Plan 01-04 (Phase 1 Wave 1).

Single public function: ``upsert_ohlcv``.

Replaces the Markdown writer (writer.py). Whole responsibility is one row
in the ``ohlcv`` table per (ticker, trade_date), with COALESCE preservation
of T+2 short_volume/short_balance/corp_code so a stale follow-up fetch
NEVER NULL-clobbers existing data.

Hard Veto #6 — ``ohlcv`` is pure numeric. No body / embedding columns
ever pass through here (the table itself has none).

SQL safety:
- ticker is regex-pre-filtered ``^[0-9]{6}$`` (path-traversal class T-04-04
  carry-over from writer.py).
- All values flow through SQLAlchemy bind params; no f-string interpolation.
"""

from __future__ import annotations

import re
from datetime import date
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_TICKER_RE = re.compile(r"^[0-9]{6}$")

__all__ = ["upsert_ohlcv"]


_UPSERT_SQL = text(
    """
    INSERT INTO ohlcv (
        ticker, trade_date,
        open, high, low, close, volume,
        trading_value, foreign_net, inst_net, retail_net,
        short_volume, short_balance,
        corp_code, fetched_at
    ) VALUES (
        :ticker, :trade_date,
        :open, :high, :low, :close, :volume,
        :trading_value, :foreign_net, :inst_net, :retail_net,
        :short_volume, :short_balance,
        :corp_code, now()
    )
    ON CONFLICT (ticker, trade_date) DO UPDATE SET
        open          = EXCLUDED.open,
        high          = EXCLUDED.high,
        low           = EXCLUDED.low,
        close         = EXCLUDED.close,
        volume        = EXCLUDED.volume,
        trading_value = EXCLUDED.trading_value,
        foreign_net   = EXCLUDED.foreign_net,
        inst_net      = EXCLUDED.inst_net,
        retail_net    = EXCLUDED.retail_net,
        short_volume  = COALESCE(EXCLUDED.short_volume,  ohlcv.short_volume),
        short_balance = COALESCE(EXCLUDED.short_balance, ohlcv.short_balance),
        corp_code     = COALESCE(EXCLUDED.corp_code,     ohlcv.corp_code),
        fetched_at    = now()
    """
)

_SELECT_EXISTING_SQL = text(
    """
    SELECT open, high, low, close, volume,
           trading_value, foreign_net, inst_net, retail_net,
           short_volume, short_balance, corp_code
    FROM ohlcv
    WHERE ticker = :t AND trade_date = :d
    """
)


def _values_match_existing(existing, params: dict[str, Any]) -> bool:
    """Return True when the incoming params would change nothing.

    Mirrors the COALESCE pattern in the UPSERT SQL:
    - OHLCV (open/high/low/close/volume) always overwrites — so any
      difference here = change.
    - flow (trading_value/foreign_net/inst_net/retail_net) overwrites — any
      diff = change.
    - short_volume/short_balance/corp_code use COALESCE(EXCLUDED.x,
      existing.x) — if incoming is None, the column stays. So an incoming
      None on these three is NEVER a change.

    Comparing numerics: Postgres returns Decimal for NUMERIC, int for
    BIGINT. Cast incoming numbers to the same comparable shape.
    """
    # OHLCV: always overwritten
    for col in ("open", "high", "low", "close"):
        # Use Decimal arithmetic for NUMERIC columns. existing.x is a Decimal;
        # incoming may be Decimal, float, or int. Compare via Decimal cast.
        from decimal import Decimal

        if Decimal(str(params[col])) != getattr(existing, col):
            return False
    if int(params["volume"]) != int(existing.volume):
        return False

    # Flow: always overwritten (treat None on both sides as equal)
    for col in ("trading_value", "foreign_net", "inst_net", "retail_net"):
        incoming = params[col]
        current = getattr(existing, col)
        if incoming is None and current is None:
            continue
        if incoming is None or current is None:
            return False
        if int(incoming) != int(current):
            return False

    # COALESCE columns: incoming None never changes state
    for col in ("short_volume", "short_balance"):
        incoming = params[col]
        if incoming is None:
            continue  # COALESCE preserves existing; no change
        current = getattr(existing, col)
        if current is None:
            return False  # incoming has value, existing is NULL → fills in
        if int(incoming) != int(current):
            return False

    # corp_code COALESCE
    incoming_cc = params["corp_code"]
    if incoming_cc is not None:
        if existing.corp_code is None:
            return False
        if incoming_cc != existing.corp_code:
            return False

    return True


def upsert_ohlcv(
    engine: Engine,
    *,
    ticker: str,
    trade_date: date,
    corp_code: str | None,
    ohlcv_row: dict[str, Any],
    flow_row: dict[str, Any] | None = None,
    short_row: dict[str, Any] | None = None,
) -> Literal["inserted", "updated", "skipped"]:
    """Upsert one (ticker, trade_date) row into the ``ohlcv`` table.

    Returns:
        "inserted" — no prior row existed; a fresh row was written.
        "updated"  — prior row existed; at least one column changed
                     (including a T+2 short fill-in).
        "skipped"  — prior row existed and all incoming values match
                     (after COALESCE semantics applied). ``fetched_at`` is
                     NOT bumped in this case — this is the cheap-no-op
                     optimization that the Wave-2 collectors rely on.

    Args:
        engine: SQLAlchemy engine (psycopg3).
        ticker: 6-digit KRX ticker (raises ValueError if shape wrong).
        trade_date: business-day date for the row.
        corp_code: 8-digit DART corp code, or None. NULL on insert means
            "FK left dangling"; on update COALESCE preserves any existing
            value so a None on a later fetch doesn't clobber.
        ohlcv_row: ``{"open": Decimal|float, "high": ..., "low": ...,
                    "close": ..., "volume": int}`` — required.
        flow_row: ``{"trading_value": int|None, "foreign_net": int|None,
                    "inst_net": int|None, "retail_net": int|None}`` — optional.
                  Columns omitted from the dict are written as NULL.
        short_row: ``{"short_volume": int|None, "short_balance": int|None}``
                   — optional. Subject to COALESCE on update.
    """
    if not _TICKER_RE.match(ticker):
        raise ValueError(f"bad ticker (need 6 ASCII digits): {ticker!r}")

    flow = flow_row or {}
    short = short_row or {}

    params: dict[str, Any] = {
        "ticker": ticker,
        "trade_date": trade_date,
        "open": ohlcv_row["open"],
        "high": ohlcv_row["high"],
        "low": ohlcv_row["low"],
        "close": ohlcv_row["close"],
        "volume": int(ohlcv_row["volume"]),
        "trading_value": flow.get("trading_value"),
        "foreign_net": flow.get("foreign_net"),
        "inst_net": flow.get("inst_net"),
        "retail_net": flow.get("retail_net"),
        "short_volume": short.get("short_volume"),
        "short_balance": short.get("short_balance"),
        "corp_code": corp_code,
    }

    with engine.begin() as conn:
        existing = conn.execute(
            _SELECT_EXISTING_SQL, {"t": ticker, "d": trade_date}
        ).first()
        if existing is None:
            outcome: Literal["inserted", "updated", "skipped"] = "inserted"
        elif _values_match_existing(existing, params):
            return "skipped"
        else:
            outcome = "updated"
        conn.execute(_UPSERT_SQL, params)
    return outcome
