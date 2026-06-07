"""Pydantic v2 return models for the 10 stock-mcp-v2 read-side tools.

Every model is **empty-able** (D-01): a zero-row result is a valid construction of
the model — an empty ``list`` (``hits=[]`` / ``bars=[]`` / ``rows=[]`` /
``entries=[]``), ``found=False``, or ``median=None``. A tool returns one of these
empty models for "no data" and *raises* a :class:`~mcp_v2.errors.McpToolError`
subclass only for a genuine fault. Identifier fields (``ticker``, ``corp_code``,
``rcept_no``, ``path``, ``metric``, ``date``, ``type``) carry no default so the
return always echoes what was queried.

Discipline replicated from ``src/cards/models.py`` (the Phase-2 contract):
``model_config = ConfigDict(extra="forbid")`` on every model, ``Field(...)`` for
constraints, and the ASCII ``r"^[0-9]{6}$"`` (ticker) / ``r"^[0-9]{8}$"``
(corp_code) regexes — ASCII-only because ``str.isdigit`` accepts superscripts.

Narrative models (D-03 WRAP+FLAG): ``FilingDetail``, ``NoteContent``, and
``SearchHit`` carry the body **already wrapped** in the ``<untrusted>`` XML
delimiter plus an ``injection_suspected: bool`` flag and an ``injection_flags:
list[str]`` of matched pattern IDs. The body is NEVER blocked or stripped — the
flag is advisory metadata for the downstream LLM (see :mod:`mcp_v2.injection`).
Pure-numeric models (``OhlcvRange``/``FlowRange``/``PeerView``) carry no narrative
and no injection fields (Veto #6).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "FilingDetail",
    "FilingHit",
    "SearchFilingsResult",
    "OhlcvBar",
    "OhlcvRange",
    "FlowRow",
    "FlowRange",
    "PeerView",
    "SearchHit",
    "SearchResult",
    "NoteContent",
    "CardView",
    "Briefing",
    "PortfolioHolding",
    "PortfolioView",
]

_TICKER_PATTERN = r"^[0-9]{6}$"
_CORP_CODE_PATTERN = r"^[0-9]{8}$"


# --------------------------------------------------------------------------- #
# get_filing / search_filings
# --------------------------------------------------------------------------- #
class FilingDetail(BaseModel):
    """Whole-body DART filing (Veto #8 — full ``body_md``, no chunking).

    ``body_md`` is returned ALREADY wrapped in the ``<untrusted>`` XML delimiter
    (D-03). ``injection_suspected`` / ``injection_flags`` are advisory only — the
    body is never blocked or stripped. Single-row tool: no empty-list state.
    """

    model_config = ConfigDict(extra="forbid")

    rcept_no: str
    corp_code: str = Field(pattern=_CORP_CODE_PATTERN)
    title: str | None = None
    filed_at: str | None = None
    event_type: str | None = None
    body_md: str  # wrapped via injection.wrap_untrusted (D-03)
    injection_suspected: bool = False
    injection_flags: list[str] = Field(default_factory=list)


class FilingHit(BaseModel):
    """One filing metadata row from ``search_filings`` (no body — metadata only)."""

    model_config = ConfigDict(extra="forbid")

    rcept_no: str
    corp_code: str = Field(pattern=_CORP_CODE_PATTERN)
    title: str | None = None
    filed_at: str | None = None
    event_type: str | None = None


class SearchFilingsResult(BaseModel):
    """``search_filings`` result. ``hits=[]`` is the valid empty state (D-01)."""

    model_config = ConfigDict(extra="forbid")

    corp_code: str = Field(pattern=_CORP_CODE_PATTERN)
    hits: list[FilingHit] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# ohlcv_range / flow_range  (pure numeric — Veto #6, no injection fields)
# --------------------------------------------------------------------------- #
class OhlcvBar(BaseModel):
    """One daily OHLCV+volume bar."""

    model_config = ConfigDict(extra="forbid")

    trade_date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = None
    trading_value: float | None = None


class OhlcvRange(BaseModel):
    """``ohlcv_range`` result. ``bars=[]`` is the valid empty state (D-01)."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(pattern=_TICKER_PATTERN)
    bars: list[OhlcvBar] = Field(default_factory=list)


class FlowRow(BaseModel):
    """One daily investor-flow row (foreign/institutional/retail net + short)."""

    model_config = ConfigDict(extra="forbid")

    trade_date: str
    foreign_net: float | None = None
    inst_net: float | None = None
    retail_net: float | None = None
    short_volume: float | None = None
    short_balance: float | None = None


class FlowRange(BaseModel):
    """``flow_range`` result. ``rows=[]`` is the valid empty state (D-01)."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(pattern=_TICKER_PATTERN)
    rows: list[FlowRow] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# peer_view  (pure numeric — Veto #6)
# --------------------------------------------------------------------------- #
class PeerView(BaseModel):
    """Same-sector median for ``metric`` ∈ {per, pbr, roe}.

    ``median=None`` with ``n=0`` is the valid empty state (sector has no peers
    with the metric populated) — NOT an error (D-01).
    """

    model_config = ConfigDict(extra="forbid")

    metric: str
    median: float | None = None
    n: int = 0
    sector: str | None = None


# --------------------------------------------------------------------------- #
# hybrid_search  (D-02 references + snippet only, NO body_md)
# --------------------------------------------------------------------------- #
class SearchHit(BaseModel):
    """One RRF hit: id/path + score + snippet only (D-02 — never full body).

    ``snippet`` is returned ALREADY wrapped in the ``<untrusted>`` XML delimiter
    (D-03), with the advisory injection flags. The agent re-fetches the full body
    via ``get_filing`` / ``get_note`` for hits it cares about.
    """

    model_config = ConfigDict(extra="forbid")

    source_type: str  # "filing" | "news" | "note"
    id_or_path: str
    rrf_score: float
    snippet: str  # wrapped via injection.wrap_untrusted (D-03)
    injection_suspected: bool = False
    injection_flags: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    """``hybrid_search`` result. ``hits=[]`` is the valid empty state (D-01)."""

    model_config = ConfigDict(extra="forbid")

    hits: list[SearchHit] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# get_note  (D-03 narrative)
# --------------------------------------------------------------------------- #
class NoteContent(BaseModel):
    """A ``notes/private/`` memo, whole content wrapped (D-03). Single-row tool."""

    model_config = ConfigDict(extra="forbid")

    path: str
    content_md: str  # wrapped via injection.wrap_untrusted (D-03)
    injection_suspected: bool = False
    injection_flags: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# get_decision_card  (Veto #13 payload-default)
# --------------------------------------------------------------------------- #
class CardView(BaseModel):
    """``get_decision_card`` result. ``found=False`` (``card=None``) is the valid
    empty state — there is no active card (D-01), NOT a bad-corp_code error.
    """

    model_config = ConfigDict(extra="forbid")

    corp_code: str = Field(pattern=_CORP_CODE_PATTERN)
    found: bool = False
    card: dict | None = None


# --------------------------------------------------------------------------- #
# get_briefing  (Phase-5 wires data; Phase-3 returns empty model)
# --------------------------------------------------------------------------- #
class Briefing(BaseModel):
    """``get_briefing`` result. Phase 3 always returns ``found=False, entries=[]``
    (the ``report_type`` rows are produced in Phase 5) — honest empty model (D-01).
    """

    model_config = ConfigDict(extra="forbid")

    date: str
    type: str  # "daily" | "weekly"
    found: bool = False
    entries: list[dict] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# list_portfolio  (passthrough of shared.portfolio.Portfolio.load)
# --------------------------------------------------------------------------- #
class PortfolioHolding(BaseModel):
    """One held/watched ticker passthrough row."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(pattern=_TICKER_PATTERN)
    name: str | None = None
    avg_price: float | None = None
    quantity: float | None = None
    thesis: str | None = None
    auto_trade_enabled: bool = False


class PortfolioView(BaseModel):
    """``list_portfolio`` result. Empty ``holdings``/``watchlist`` is valid (D-01)."""

    model_config = ConfigDict(extra="forbid")

    holdings: list[PortfolioHolding] = Field(default_factory=list)
    watchlist: list[PortfolioHolding] = Field(default_factory=list)
