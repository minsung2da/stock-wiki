"""src/analysis/gate.py — D-04 stance-change gate (SC#6).

The **deterministic, NO-LLM** decision of whether a ticker needs a full 3-role
Bull/Bear/Judge debate or just a cheap lightweight refresh. This is the
token-economics gate: steady-state HOLD reruns stay cheap (a REFRESH spends no
LLM), while event-driven (PEAD) tickers get re-debated the moment something
actually changes.

Full debate triggers (RESEARCH Discretion #5, all ``[ASSUMED]`` — need user
confirm; ``.planning/phases/04-analysis-runner-3-role-debate/04-RESEARCH.md``
lines 288-296):

- **first run** — no prior active card;
- **new filing/event** since ``prior.as_of`` (``search_filings``);
- **price spike** — |close-to-close return| ≥ 7% on any day, OR a day's volume ≥
  3× the trailing-20d average (``ohlcv_range``);
- **flow spike** — |foreign or inst net| ≥ 2× the trailing-20d stdev (``flow_range``);
- **near-expiry** — ``prior.expires_at − as_of ≤ 7 days`` (near-expiry is itself a
  FULL trigger, which is why :func:`lightweight_refresh` must NEVER extend expiry);
- **assumption break** — a ``key_claim.evidence_refs`` filing no longer resolves;
- **safety net** — ``as_of − prior.generated_at ≥ N`` days (default N = 14).

Otherwise → REFRESH (the no-trigger steady state).

Isolation guarantee (T-04-11, SC#6 "skip the debate"): this module imports NOTHING
from ``analysis.subagents`` / ``analysis.runner`` and spawns no subprocess — it
CANNOT reach the LLM. It reads the prior card via the Phase-2 typed store contract
and the market/filing signals via the SAME in-process Phase-3 tools ``bundle.py``
uses (``search_filings`` / ``ohlcv_range`` / ``flow_range``). There is no ``run_sql``
escape hatch (Veto #7) — only the typed tools + ``resolve_entity``.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final, Literal
from zoneinfo import ZoneInfo

from sqlalchemy.engine import Engine

from cards.models import DecisionCard
from db.entity import resolve_entity
from mcp_v2.errors import FilingNotFound, InvalidArgument
from mcp_v2.tools.filing import get_filing, search_filings
from mcp_v2.tools.market import flow_range, ohlcv_range

__all__ = ["FULL", "REFRESH", "GateDecision", "decide"]

# Gate outcomes. ``Final`` gives each the literal type ``Literal["FULL"]`` /
# ``Literal["REFRESH"]`` so they satisfy the ``GateDecision.action`` annotation
# under mypy strict.
FULL: Final = "FULL"
REFRESH: Final = "REFRESH"

# --- Trigger thresholds (Discretion #5, all [ASSUMED] — RESEARCH 288-296) -------
# Confirm with the user before Phase 8 tunes them. KRX daily limit is ±30%; 7% is a
# "material move" heuristic. N = 14d ≤ the typical 30-day horizon so no thesis ages
# a full horizon un-re-debated.
_PRICE_RETURN_THRESHOLD: Final = 0.07  # |close-to-close return| ≥ 7% → FULL  [ASSUMED]
_VOLUME_SPIKE_MULT: Final = 3.0  # daily volume ≥ 3× trailing-20d avg → FULL   [ASSUMED]
_FLOW_SIGMA_MULT: Final = 2.0  # |foreign|inst net| ≥ 2× trailing-20d stdev    [ASSUMED]
_TRAILING_WINDOW: Final = 20  # trailing-Nd window for the vol avg / flow stdev [ASSUMED]
_MIN_TRAILING: Final = 5  # need ≥ this many trailing bars before judging a spike [ASSUMED]
_NEAR_EXPIRY_DAYS: Final = 7  # prior.expires_at − as_of ≤ 7d → FULL (D-7)       [ASSUMED]
_SAFETY_NET_DAYS: Final = 14  # default N-day safety net                         [ASSUMED]
# Calendar days to look back so the numeric windows carry ≥ _TRAILING_WINDOW trading
# bars of trailing context before the first day being judged (~20 bars ≈ 4 weeks).
_TRAIL_LOOKBACK_DAYS: Final = 45  # [ASSUMED]

_KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class GateDecision:
    """The gate outcome: FULL (re-debate) or REFRESH (cheap re-validate).

    ``reasons`` carries every fired trigger (not just the first) for observability
    — an empty tuple means the no-trigger steady state that yields REFRESH.
    """

    action: Literal["FULL", "REFRESH"]
    reasons: tuple[str, ...] = ()

    @property
    def is_full(self) -> bool:
        return self.action == FULL


# --- datetime helpers ----------------------------------------------------------
def _as_aware(dt: datetime) -> datetime:
    """Treat a naive datetime as KST close so tz-aware card timestamps subtract
    cleanly. Card timestamps round-trip with ``+09:00`` already; this only rescues
    a caller that passes a naive ``as_of``."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=_KST)


def _gate_ticker(engine: Engine, prior: DecisionCard) -> str:
    """The KRX ticker to read price/flow for.

    Prefers the entity's CURRENT ticker (handles a rename since the prior card was
    written); falls back to the prior card's stored ``ticker``.
    """
    entity = resolve_entity(engine, prior.corp_code)
    if entity is not None and entity.current_ticker is not None:
        return entity.current_ticker
    return prior.ticker


# --- individual triggers (each returns a reason string or None) ----------------
def _new_filing(corp_code: str, prior_as_of: datetime) -> str | None:
    """Any filing filed since ``prior.as_of`` → a change the prior card never saw.

    RESEARCH #5 verbatim: ``search_filings(corp_code, since=prior.as_of)`` with any
    hit is a trigger. In a real run the DB never holds filings dated after ``as_of``
    (collectors only fetch up to now), so no upper bound is needed.
    """
    result = search_filings(corp_code, since=prior_as_of.isoformat())
    if result.hits:
        newest = result.hits[0]
        return (
            f"new_filing: {len(result.hits)} filing(s) since "
            f"{prior_as_of.isoformat()} (newest {newest.rcept_no})"
        )
    return None


def _price_spike(ticker: str, prior_as_of: datetime, as_of: datetime) -> str | None:
    """|close-to-close| ≥ 7% on any new day, OR a new day's volume ≥ 3× trailing-20d avg.

    Fetches a window that starts ``_TRAIL_LOOKBACK_DAYS`` before ``as_of`` so the
    earliest day being judged still has trailing bars for the volume average; only
    days strictly after ``prior.as_of`` are judged (the rest are trailing context).
    """
    from_date = (as_of.date() - timedelta(days=_TRAIL_LOOKBACK_DAYS)).isoformat()
    rng = ohlcv_range(ticker, from_date, as_of.date().isoformat())
    bars = rng.bars
    since_date = prior_as_of.date()

    for i, bar in enumerate(bars):
        bd = date.fromisoformat(bar.trade_date[:10])
        if bd <= since_date:
            continue  # trailing-context day, not a "new" day since the prior card
        close = bar.close
        if close is None:
            continue

        # close-to-close return vs the immediately preceding bar
        if i > 0:
            prev = bars[i - 1].close
            if prev is not None and prev != 0:
                ret = abs(close - prev) / abs(prev)
                if ret >= _PRICE_RETURN_THRESHOLD:
                    return (
                        f"price_spike: |ret|={ret:.4f} ≥ {_PRICE_RETURN_THRESHOLD} "
                        f"on {bar.trade_date}"
                    )

        # volume spike vs the trailing-20d average
        vol = bar.volume
        trail = [
            b.volume for b in bars[max(0, i - _TRAILING_WINDOW) : i] if b.volume is not None
        ]
        if vol is not None and len(trail) >= _MIN_TRAILING:
            avg = statistics.fmean(trail)
            if avg > 0 and vol >= _VOLUME_SPIKE_MULT * avg:
                return (
                    f"volume_spike: vol={vol} ≥ {_VOLUME_SPIKE_MULT}× "
                    f"trailing-avg({avg:.0f}) on {bar.trade_date}"
                )
    return None


def _flow_spike(ticker: str, prior_as_of: datetime, as_of: datetime) -> str | None:
    """|foreign or inst net| ≥ 2× the trailing-20d stdev on any new day (Veto #5 corroboration)."""
    from_date = (as_of.date() - timedelta(days=_TRAIL_LOOKBACK_DAYS)).isoformat()
    rng = flow_range(ticker, from_date, as_of.date().isoformat())
    rows = rng.rows
    since_date = prior_as_of.date()

    for i, row in enumerate(rows):
        rd = date.fromisoformat(row.trade_date[:10])
        if rd <= since_date:
            continue
        for net, attr, label in (
            (row.foreign_net, "foreign_net", "foreign"),
            (row.inst_net, "inst_net", "inst"),
        ):
            if net is None:
                continue
            trail = [
                getattr(r, attr)
                for r in rows[max(0, i - _TRAILING_WINDOW) : i]
                if getattr(r, attr) is not None
            ]
            if len(trail) >= _MIN_TRAILING:
                sd = statistics.pstdev(trail)
                if sd > 0 and abs(net) >= _FLOW_SIGMA_MULT * sd:
                    return (
                        f"flow_spike: {label}_net={net} ≥ {_FLOW_SIGMA_MULT}σ "
                        f"(trailing-stdev={sd:.0f}) on {row.trade_date}"
                    )
    return None


def _dart_ref_resolves(ref: str) -> bool:
    """Whether a ``key_claim`` evidence ref still resolves against current evidence.

    Only ``dart:<rcept_no>`` refs are cheaply verifiable via the typed filing tool
    (a missing filing raises ``FilingNotFound``; a malformed id raises
    ``InvalidArgument``). Non-dart refs (``news:`` / ``macro:`` / ``note:``) have no
    single-fetch existence tool here, so they are treated as still-resolving at the
    gate — :func:`lightweight_refresh` re-checks them on the cheap path.
    """
    if not ref.startswith("dart:"):
        return True
    rcept_no = ref.split(":", 1)[1]
    try:
        get_filing(rcept_no)
    except (FilingNotFound, InvalidArgument):
        return False
    return True


def _assumption_break(prior: DecisionCard) -> str | None:
    """A prior ``key_claim`` whose dart evidence no longer resolves = a broken assumption.

    RESEARCH #5: "an assumption no longer supported by current evidence" — the
    deterministic, LLM-free proxy is that the filing a claim cites still exists.
    """
    for claim in prior.key_claims:
        for ref in claim.evidence_refs:
            if not _dart_ref_resolves(ref):
                return (
                    f"assumption_break: evidence {ref} for claim {claim.id} "
                    "no longer resolves"
                )
    return None


def decide(
    engine: Engine,
    prior: DecisionCard | None,
    as_of: datetime,
    *,
    safety_net_days: int = _SAFETY_NET_DAYS,
) -> GateDecision:
    """Decide FULL vs REFRESH for one ticker from deterministic signals (D-04, NO LLM).

    Evaluates the full D-04 trigger set and returns :class:`GateDecision` — FULL with
    every fired reason if any trigger fires (or on first run), else REFRESH with an
    empty reason tuple (the no-trigger steady state). All triggers are read via the
    typed Phase-3 tools + the Phase-2 store contract; nothing here can reach the LLM.

    Args:
        engine: SQLAlchemy engine (used to resolve the current ticker).
        prior: the latest active card from ``store.get_active`` (``None`` on first run).
        as_of: the data cutoff (KST close) this run is deciding for.
        safety_net_days: force a FULL debate after this many days since the last full
            generation, even absent other triggers (default N = 14).

    Returns:
        ``GateDecision(FULL, reasons)`` when any trigger fires (reasons non-empty),
        otherwise ``GateDecision(REFRESH)``.
    """
    if prior is None:
        return GateDecision(FULL, ("first_run: no prior active card",))

    as_of = _as_aware(as_of)
    prior_as_of = _as_aware(prior.as_of)
    prior_generated = _as_aware(prior.generated_at)
    prior_expires = _as_aware(prior.expires_at)
    ticker = _gate_ticker(engine, prior)

    reasons: list[str] = []

    # Cheap timestamp triggers first (no DB round-trip).
    if prior_expires - as_of <= timedelta(days=_NEAR_EXPIRY_DAYS):
        reasons.append(
            f"near_expiry: expires_at {prior_expires.isoformat()} within "
            f"{_NEAR_EXPIRY_DAYS}d of as_of"
        )
    if as_of - prior_generated >= timedelta(days=safety_net_days):
        reasons.append(
            f"safety_net: {(as_of - prior_generated).days}d since last full debate "
            f"≥ {safety_net_days}d"
        )

    # Signal triggers (typed tools; each collected for observability).
    for reason in (
        _new_filing(prior.corp_code, prior_as_of),
        _price_spike(ticker, prior_as_of, as_of),
        _flow_spike(ticker, prior_as_of, as_of),
        _assumption_break(prior),
    ):
        if reason is not None:
            reasons.append(reason)

    if reasons:
        return GateDecision(FULL, tuple(reasons))
    return GateDecision(REFRESH)
