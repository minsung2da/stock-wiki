"""Fundamentals db_writer — Plan 03-05 (Phase 3 Wave 1).

Single public function: ``upsert_fundamentals``.

One row in the ``fundamentals`` table per (ticker, fdate). COALESCE preserves a
prior ``roe`` so a later pykrx-only refresh (which carries no ROE) NEVER
NULL-clobbers a dart-fss ROE that arrived on an earlier run — mirror of the KRX
T+2 short fill-in pattern (``collectors.krx.db_writer.upsert_ohlcv``).

Hard Veto #6 — ``fundamentals`` is pure NUMERIC (per/pbr/eps/bps/roe). NO body /
embedding columns ever pass through here (the table itself has none).

SQL safety (Veto #7):
- ticker is regex-pre-filtered ``^[0-9A-Z]{6}$`` (uppercase alphanumeric;
  admits KRX new-style short codes e.g. "0001A0"; raises ValueError before DB).
- All values flow through SQLAlchemy bind params; the SQL is a module-level
  ``text()`` constant; no f-string interpolation.
"""

from __future__ import annotations

import re
from datetime import date
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from collectors.fundamentals.dart_roe import RoeObservation
    from collectors.fundamentals.market_snapshot import MarketSnapshot

_TICKER_RE = re.compile(r"^[0-9A-Z]{6}$")

__all__ = ["upsert_fundamentals"]


_UPSERT_SQL = text(
    """
    INSERT INTO fundamentals (
        ticker, fdate,
        per, pbr, eps, bps, roe, dividend_yield, dps,
        corp_code, source, fetched_at
    ) VALUES (
        :ticker, :fdate,
        :per, :pbr, :eps, :bps, :roe, :dividend_yield, :dps,
        :corp_code, :source, now()
    )
    ON CONFLICT (ticker, fdate) DO UPDATE SET
        per        = EXCLUDED.per,
        pbr        = EXCLUDED.pbr,
        eps        = EXCLUDED.eps,
        bps        = EXCLUDED.bps,
        dividend_yield = EXCLUDED.dividend_yield,
        dps        = EXCLUDED.dps,
        roe        = COALESCE(EXCLUDED.roe, fundamentals.roe),
        corp_code  = COALESCE(EXCLUDED.corp_code, fundamentals.corp_code),
        source     = EXCLUDED.source,
        fetched_at = now()
    """
)

_SELECT_EXISTING_SQL = text(
    """
    SELECT per, pbr, eps, bps, roe, dividend_yield, dps, corp_code
    FROM fundamentals
    WHERE ticker = :t AND fdate = :d
    """
)


def _values_match_existing(existing, params: dict[str, Any]) -> bool:
    """Return True when the incoming params would change nothing.

    Mirrors the COALESCE semantics in the UPSERT SQL:
    - per/pbr/eps/bps always overwrite — any difference = change.
    - roe / corp_code use COALESCE(EXCLUDED.x, existing.x) — an incoming None on
      these NEVER changes state (the prior value is preserved).

    Postgres returns Decimal for NUMERIC columns; compare via Decimal cast so an
    incoming float matches an existing Decimal of equal value.
    """
    from decimal import Decimal

    for col in ("per", "pbr", "eps", "bps", "dividend_yield", "dps"):
        incoming = params[col]
        current = getattr(existing, col)
        if incoming is None and current is None:
            continue
        if incoming is None or current is None:
            return False
        if Decimal(str(incoming)) != current:
            return False

    # roe COALESCE: incoming None preserves existing → no change
    incoming_roe = params["roe"]
    if incoming_roe is not None:
        if existing.roe is None:
            return False  # incoming fills in a previously-NULL ROE
        if Decimal(str(incoming_roe)) != existing.roe:
            return False

    # corp_code COALESCE
    incoming_cc = params["corp_code"]
    if incoming_cc is not None:
        if existing.corp_code is None:
            return False
        if incoming_cc != existing.corp_code:
            return False

    return True


def upsert_fundamentals(
    engine: Engine,
    *,
    ticker: str,
    fdate: date,
    corp_code: str | None,
    per: float | None,
    pbr: float | None,
    eps: float | None,
    bps: float | None,
    roe: float | None,
    dividend_yield: float | None = None,
    dps: float | None = None,
    source: str = "fundamentals",
) -> Literal["inserted", "updated", "skipped"]:
    """Upsert one (ticker, fdate) row into the ``fundamentals`` table.

    Returns:
        "inserted" — no prior row existed; a fresh row was written.
        "updated"  — prior row existed; at least one column changed (including a
                     later ROE fill-in).
        "skipped"  — prior row existed and all incoming values match (after
                     COALESCE semantics applied). ``fetched_at`` is NOT bumped.

    Args:
        engine: SQLAlchemy engine (psycopg3).
        ticker: 6-char alphanumeric (uppercase) KRX short code; accepts
            new-style codes (e.g. "0001A0"). Raises ValueError if shape wrong.
        fdate: as-of date for the row.
        corp_code: 8-digit DART corp code, or None. COALESCE-preserved on update.
        per/pbr/eps/bps: pykrx valuation metrics (typed NUMERIC; None allowed).
        roe: dart-fss-derived ROE, or None. COALESCE-preserved on update so a
            pykrx-only refresh never NULL-clobbers it.
        source: provenance label (default "fundamentals").
    """
    if not _TICKER_RE.match(ticker):
        raise ValueError(f"bad ticker (need 6 ASCII alphanumeric uppercase): {ticker!r}")

    params: dict[str, Any] = {
        "ticker": ticker,
        "fdate": fdate,
        "per": per,
        "pbr": pbr,
        "eps": eps,
        "bps": bps,
        "roe": roe,
        "dividend_yield": dividend_yield,
        "dps": dps,
        "corp_code": corp_code,
        "source": source,
    }

    with engine.begin() as conn:
        existing = conn.execute(_SELECT_EXISTING_SQL, {"t": ticker, "d": fdate}).first()
        if existing is None:
            outcome: Literal["inserted", "updated", "skipped"] = "inserted"
        elif _values_match_existing(existing, params):
            return "skipped"
        else:
            outcome = "updated"
        conn.execute(_UPSERT_SQL, params)
    return outcome


def upsert_roe(
    engine: Engine,
    *,
    ticker: str,
    fdate: date,
    corp_code: str | None,
    observation: RoeObservation,
) -> Literal["inserted", "updated", "skipped"]:
    """Enrich ROE only: never overwrite daily market metrics or their source.

    fdate identifies the valuation row being enriched; roe_fetched_at identifies
    when the current published figure was actually acquired.
    """
    from decimal import Decimal

    if not _TICKER_RE.fullmatch(ticker):
        raise ValueError("invalid_roe_ticker")
    if not observation.value.is_finite() or observation.period_end > fdate:
        raise ValueError("invalid_roe_observation")
    value = observation.value.quantize(Decimal("0.000001"))
    params = {
        "ticker": ticker,
        "fdate": fdate,
        "corp_code": corp_code,
        "roe": value,
        "period": observation.period_end,
        "source": observation.source,
        "observed": observation.fetched_at,
        "report_code": observation.report_code,
    }
    with engine.begin() as conn:
        existing = (
            conn.execute(
                text(
                    "SELECT roe, roe_period_end, roe_source, roe_report_code FROM fundamentals "
                    "WHERE ticker=:ticker AND fdate=:fdate"
                ),
                params,
            )
            .mappings()
            .first()
        )
        if existing and (
            existing["roe"],
            existing["roe_period_end"],
            existing["roe_source"],
            existing["roe_report_code"],
        ) == (
            value,
            observation.period_end,
            observation.source,
            observation.report_code,
        ):
            return "skipped"
        conn.execute(
            text(
                "INSERT INTO fundamentals (ticker,fdate,corp_code,roe,roe_period_end,roe_source,"
                "roe_fetched_at,roe_report_code,source,fetched_at) VALUES "
                "(:ticker,:fdate,:corp_code,:roe,:period,:source,:observed,"
                ":report_code,'dart_roe',now()) "
                "ON CONFLICT (ticker,fdate) DO UPDATE SET roe=EXCLUDED.roe, "
                "roe_period_end=EXCLUDED.roe_period_end, roe_source=EXCLUDED.roe_source, "
                "roe_fetched_at=EXCLUDED.roe_fetched_at, "
                "roe_report_code=EXCLUDED.roe_report_code, "
                "corp_code=COALESCE(fundamentals.corp_code,EXCLUDED.corp_code)"
            ),
            params,
        )
    return "updated" if existing else "inserted"


def upsert_market_snapshot(
    engine: Engine,
    *,
    ticker: str,
    fdate: date,
    corp_code: str | None,
    snapshot: MarketSnapshot,
) -> Literal["inserted", "updated", "skipped"]:
    """Store today's observation without fabricating a historical price date."""
    import json
    from zoneinfo import ZoneInfo

    if not _TICKER_RE.fullmatch(ticker):
        raise ValueError("invalid_market_ticker")
    if (
        snapshot.fetched_at.tzinfo is None
        or fdate != snapshot.fetched_at.astimezone(ZoneInfo("Asia/Seoul")).date()
        or snapshot.market_asof > fdate
    ):
        raise ValueError("market_snapshot_cannot_be_backdated")
    fields = ("per", "pbr", "eps", "bps", "dividend_yield", "dps")
    params = {field: snapshot.values.get(field) for field in fields}
    params.update(
        ticker=ticker,
        fdate=fdate,
        corp_code=corp_code,
        source=snapshot.source,
        observed=snapshot.fetched_at,
        market_asof=snapshot.market_asof,
        periods=json.dumps(snapshot.metric_periods),
    )
    with engine.begin() as conn:
        existing = (
            conn.execute(
                text(
                    "SELECT per,pbr,eps,bps,dividend_yield,dps,source,market_asof,metric_periods "
                    "FROM fundamentals WHERE ticker=:ticker AND fdate=:fdate"
                ),
                params,
            )
            .mappings()
            .first()
        )
        if (
            existing
            and all(existing[field] == params[field] for field in fields)
            and existing["source"] == snapshot.source
            and existing["market_asof"] == snapshot.market_asof
            and existing["metric_periods"] == snapshot.metric_periods
        ):
            return "skipped"
        conn.execute(
            text(
                "INSERT INTO fundamentals (ticker,fdate,corp_code,per,pbr,eps,bps,"
                "dividend_yield,dps,"
                "source,fetched_at,market_asof,metric_periods) VALUES "
                "(:ticker,:fdate,:corp_code,:per,:pbr,:eps,:bps,:dividend_yield,:dps,"
                ":source,:observed,:market_asof,CAST(:periods AS jsonb)) "
                "ON CONFLICT (ticker,fdate) DO UPDATE SET per=EXCLUDED.per,pbr=EXCLUDED.pbr,"
                "eps=EXCLUDED.eps,bps=EXCLUDED.bps,dividend_yield=EXCLUDED.dividend_yield,dps=EXCLUDED.dps,"
                "source=EXCLUDED.source,fetched_at=EXCLUDED.fetched_at,market_asof=EXCLUDED.market_asof,"
                "metric_periods=EXCLUDED.metric_periods,"
                "corp_code=COALESCE(fundamentals.corp_code,EXCLUDED.corp_code)"
            ),
            params,
        )
    return "updated" if existing else "inserted"
