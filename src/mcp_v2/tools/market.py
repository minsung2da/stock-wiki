"""``ohlcv_range`` + ``flow_range`` + ``peer_view`` — the numeric market read tools.

Three tools registered on the shared ``mcp`` instance (Veto #6 — pure numeric,
NO injection wrap, NO embedding):

- :func:`ohlcv_range` — daily OHLCV+volume bars for a ticker over a REQUIRED
  ``from_date``/``to_date`` window (D-04 — caller owns the range, no hard cap).
- :func:`flow_range` — daily investor-flow rows (foreign/institutional/retail net
  + short) for a ticker over the same REQUIRED window.
- :func:`peer_view` — same-sector median for ``metric`` ∈ {per, pbr, roe},
  ``percentile_cont(0.5) WITHIN GROUP`` over the ``fundamentals`` table joined to
  ``entities.sector`` (D-06). No same-sector peers → ``PeerView(median=None,
  n=0)`` (D-01 empty model).

SQL discipline (Veto #7 / SC#3 AST guard): every statement is a module-level
``text()`` constant bound with parameters — NO f-string SQL. ``peer_view`` selects
the metric column via a FIXED per-metric ``text()`` constant chosen from an
allow-list map (NOT user-string interpolation), so the metric arg can never reach
SQL as a raw column name.

Input validation (V5): ``ticker`` (6 ASCII digits) / ``corp_code`` (8 ASCII
digits) are regex pre-filtered before any DB round-trip; ticker existence is
confirmed via :func:`db.entity.resolve_entity` (→ ``EntityNotFound``).
"""

from __future__ import annotations

import re

from mcp.types import ToolAnnotations
from sqlalchemy import text

from db.engine import get_engine
from db.entity import resolve_entity

from .._mcp import mcp
from ..errors import EntityNotFound, InvalidArgument
from ..models import FlowRange, FlowRow, OhlcvBar, OhlcvRange, PeerView

__all__ = ["ohlcv_range", "flow_range", "peer_view"]

# ASCII-only digit pre-filters (str.isdigit accepts superscripts — close that
# loophole). ticker is the 6-digit KRX ticker; corp_code is the 8-digit DART code.
_TICKER_RE = re.compile(r"^[0-9]{6}$")
_CORP_CODE_RE = re.compile(r"^[0-9]{8}$")

# Allow-listed peer metrics. The metric arg is validated against this set; the
# actual SQL column is chosen from a FIXED per-metric text() constant below — the
# metric string NEVER reaches SQL as a column name (SC#3 / T-metric-sql).
_PEER_METRICS: frozenset[str] = frozenset({"per", "pbr", "roe"})


# --- SQL constants (bind params only — Veto #7, never f-string) ---------------

_OHLCV_RANGE_SQL = text(
    """
    SELECT trade_date, open, high, low, close, volume, trading_value
      FROM ohlcv
     WHERE ticker = :t
       AND trade_date >= :from_date
       AND trade_date <= :to_date
     ORDER BY trade_date
    """
)

_FLOW_RANGE_SQL = text(
    """
    SELECT trade_date, foreign_net, inst_net, retail_net,
           short_volume, short_balance
      FROM ohlcv
     WHERE ticker = :t
       AND trade_date >= :from_date
       AND trade_date <= :to_date
     ORDER BY trade_date
    """
)

# One FIXED text() constant per metric — the column name is hard-coded inside each
# string literal (never interpolated from the user-supplied metric). The metric
# arg only SELECTS which pre-built constant runs. This is what keeps the SC#3 AST
# guard satisfied (every text() arg is a string constant / module-level name).
_PEER_VIEW_PER_SQL = text(
    """
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY fnd.per) AS median,
           count(fnd.per) AS n
      FROM fundamentals fnd
      JOIN entities e ON e.corp_code = fnd.corp_code
     WHERE e.sector = (SELECT sector FROM entities WHERE corp_code = :cc)
       AND e.sector IS NOT NULL
       AND fnd.per IS NOT NULL
    """
)

_PEER_VIEW_PBR_SQL = text(
    """
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY fnd.pbr) AS median,
           count(fnd.pbr) AS n
      FROM fundamentals fnd
      JOIN entities e ON e.corp_code = fnd.corp_code
     WHERE e.sector = (SELECT sector FROM entities WHERE corp_code = :cc)
       AND e.sector IS NOT NULL
       AND fnd.pbr IS NOT NULL
    """
)

_PEER_VIEW_ROE_SQL = text(
    """
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY fnd.roe) AS median,
           count(fnd.roe) AS n
      FROM fundamentals fnd
      JOIN entities e ON e.corp_code = fnd.corp_code
     WHERE e.sector = (SELECT sector FROM entities WHERE corp_code = :cc)
       AND e.sector IS NOT NULL
       AND fnd.roe IS NOT NULL
    """
)

# metric → the fixed pre-built text() constant (NOT a column-name string).
_PEER_VIEW_SQL_BY_METRIC = {
    "per": _PEER_VIEW_PER_SQL,
    "pbr": _PEER_VIEW_PBR_SQL,
    "roe": _PEER_VIEW_ROE_SQL,
}

_SECTOR_OF_SQL = text("SELECT sector FROM entities WHERE corp_code = :cc")


def _isoformat(value: object) -> str:
    """ISO-8601 string for a DB date/datetime."""
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        return iso()
    return str(value)


def _to_float(value: object) -> float | None:
    """Coerce a Decimal/int/None DB numeric to float|None."""
    if value is None:
        return None
    return float(value)  # type: ignore[arg-type]


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)  # type: ignore[arg-type]


def ohlcv_range(ticker: str, from_date: str, to_date: str) -> OhlcvRange:
    """Daily OHLCV+volume bars for ``ticker`` over [from_date, to_date] (inclusive).

    Pure numeric (Veto #6 — no injection wrap). ``from_date``/``to_date`` are
    REQUIRED ISO-8601 dates (D-04 — caller owns the window, no hard cap). Zero
    rows → ``OhlcvRange(ticker, bars=[])`` (D-01 empty model).

    Args:
        ticker: the 6-digit KRX ticker (must resolve to a known entity).
        from_date: inclusive lower bound (ISO-8601 ``YYYY-MM-DD``).
        to_date: inclusive upper bound (ISO-8601 ``YYYY-MM-DD``).

    Raises:
        InvalidArgument: ``ticker`` is not 6 ASCII digits.
        EntityNotFound: ``ticker`` does not resolve to a known entity.
    """
    if not _TICKER_RE.match(ticker):
        raise InvalidArgument("ticker must be 6 ASCII digits")

    engine = get_engine()
    if resolve_entity(engine, ticker) is None:
        raise EntityNotFound(f"no entity for ticker {ticker}")

    params = {"t": ticker, "from_date": from_date, "to_date": to_date}
    with engine.connect() as conn:
        rows = conn.execute(_OHLCV_RANGE_SQL, params).all()

    bars = [
        OhlcvBar(
            trade_date=_isoformat(row.trade_date),
            open=_to_float(row.open),
            high=_to_float(row.high),
            low=_to_float(row.low),
            close=_to_float(row.close),
            volume=_to_int(row.volume),
            trading_value=_to_float(row.trading_value),
        )
        for row in rows
    ]
    return OhlcvRange(ticker=ticker, bars=bars)


def flow_range(ticker: str, from_date: str, to_date: str) -> FlowRange:
    """Daily investor-flow rows for ``ticker`` over [from_date, to_date] (inclusive).

    Pure numeric (Veto #6 — no injection wrap). Same REQUIRED date semantics as
    :func:`ohlcv_range`. Zero rows → ``FlowRange(ticker, rows=[])`` (D-01).

    Args:
        ticker: the 6-digit KRX ticker (must resolve to a known entity).
        from_date: inclusive lower bound (ISO-8601 ``YYYY-MM-DD``).
        to_date: inclusive upper bound (ISO-8601 ``YYYY-MM-DD``).

    Raises:
        InvalidArgument: ``ticker`` is not 6 ASCII digits.
        EntityNotFound: ``ticker`` does not resolve to a known entity.
    """
    if not _TICKER_RE.match(ticker):
        raise InvalidArgument("ticker must be 6 ASCII digits")

    engine = get_engine()
    if resolve_entity(engine, ticker) is None:
        raise EntityNotFound(f"no entity for ticker {ticker}")

    params = {"t": ticker, "from_date": from_date, "to_date": to_date}
    with engine.connect() as conn:
        rows = conn.execute(_FLOW_RANGE_SQL, params).all()

    flow_rows = [
        FlowRow(
            trade_date=_isoformat(row.trade_date),
            foreign_net=_to_float(row.foreign_net),
            inst_net=_to_float(row.inst_net),
            retail_net=_to_float(row.retail_net),
            short_volume=_to_float(row.short_volume),
            short_balance=_to_float(row.short_balance),
        )
        for row in rows
    ]
    return FlowRange(ticker=ticker, rows=flow_rows)


def peer_view(corp_code: str, metric: str) -> PeerView:
    """Same-sector median of ``metric`` ∈ {per, pbr, roe} over ``fundamentals`` (D-06).

    Computes ``percentile_cont(0.5) WITHIN GROUP (ORDER BY fnd.<metric>)`` across
    every entity in the same ``entities.sector`` as ``corp_code`` that has the
    metric populated. ``n`` is the sample size (leaves room for a future weighted
    median, D-06). Pure numeric (Veto #6 — no injection wrap).

    No same-sector peers / metric NULL everywhere / sector is NULL →
    ``PeerView(metric, median=None, n=0)`` (D-01 empty model — NOT an error).

    Args:
        corp_code: the 8-digit DART corp code whose sector anchors the peer set.
        metric: one of ``"per"``, ``"pbr"``, ``"roe"``.

    Raises:
        InvalidArgument: ``corp_code`` is not 8 ASCII digits, or ``metric`` is
            not one of {per, pbr, roe}.
    """
    if not _CORP_CODE_RE.match(corp_code):
        raise InvalidArgument("corp_code must be 8 ASCII digits")
    if metric not in _PEER_METRICS:
        raise InvalidArgument(f"metric must be one of {sorted(_PEER_METRICS)}")

    sql = _PEER_VIEW_SQL_BY_METRIC[metric]
    engine = get_engine()
    with engine.connect() as conn:
        sector = conn.execute(_SECTOR_OF_SQL, {"cc": corp_code}).scalar()
        row = conn.execute(sql, {"cc": corp_code}).first()

    # percentile_cont over zero matching rows yields median=NULL, n=0 → empty model.
    median = _to_float(row.median) if row is not None else None
    n = _to_int(row.n) if row is not None else 0
    return PeerView(metric=metric, median=median, n=n or 0, sector=sector)


# Register on the shared mcp via the call form ``mcp.tool(...)(fn)`` (NOT the
# ``@mcp.tool`` decorator — that replaces the name with a non-callable
# FunctionTool, breaking in-process callers; see Plan 03-04 SUMMARY). All three
# are read-only numeric tools.
_READ_ONLY = ToolAnnotations(readOnlyHint=True)
mcp.tool(annotations=_READ_ONLY)(ohlcv_range)
mcp.tool(annotations=_READ_ONLY)(flow_range)
mcp.tool(annotations=_READ_ONLY)(peer_view)
