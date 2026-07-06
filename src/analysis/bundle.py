"""D-02 ``EvidenceBundle`` — the fixed, reproducible, pre-fetched evidence snapshot.

Step (a) of SC#2's flow. ``build_bundle(engine, corp_code, as_of)`` assembles ALL
evidence for one ticker ONCE via the Phase-3 in-process MCP tools
(``search_filings`` / ``get_filing`` / ``ohlcv_range`` / ``flow_range`` /
``peer_view`` / ``hybrid_search`` / ``get_note``) and hands the SAME bundle
identically to Bull/Bear/Judge — the sub-agents never call tools themselves (D-02).

Why one fixed bundle:
- **Reproducibility** — same ``(corp_code, as_of)`` on the same DB ⇒ equal bundle
  ⇒ equal card (the anchor for Phase-8 CPCV eval).
- **Fair debate** — Bull/Bear are blind to each other but argue over the SAME facts.
- **Easy numeric checksum** — the source bodies are in hand for the D-03 verbatim
  value-equivalence gate (``checksum.py``).

Injection wrapping (D-03): every narrative body arrives from the tools ALREADY
wrapped in the ``<untrusted source="..." ref="...">`` XML delimiter. This module
PRESERVES those delimiters verbatim — it never re-wraps, strips, or truncates a body
mid-content (stripping would corrupt the numeric checksum; T-04-07).

Bounded serialization (T-04-08 DoS/cost): :meth:`EvidenceBundle.to_stdin` emits a
deterministic string capped at :data:`_STDIN_CHAR_CAP`, dropping oldest / lowest-weight
WHOLE narrative bodies first — never a partial body — so the model context / cost stay
bounded.

Veto discipline: NO ``run_sql`` escape hatch (Veto #7 — only the typed tools); whole
``body_md`` per filing (Veto #8 — no chunking); numeric ranges stay typed (Veto #6).
The window/limit constants below are ``[ASSUMED]`` (Discretion #3); Phase 8 tunes them.
"""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Engine

from db.entity import resolve_entity
from mcp_v2.models import (
    FlowRange,
    NoteContent,
    OhlcvRange,
    PeerView,
    SearchHit,
)
from mcp_v2.tools.filing import get_filing, search_filings
from mcp_v2.tools.market import flow_range, ohlcv_range, peer_view
from mcp_v2.tools.note import get_note
from mcp_v2.tools.search import hybrid_search

__all__ = ["EvidenceBundle", "FilingHitBody", "NarrativeRef", "build_bundle"]

# --- Per-ticker collection windows / limits (Discretion #3, all [ASSUMED]) -----
# Look back this many days for recent filings; keep the top-K most recent WHOLE
# bodies (Veto #8). OHLCV over ~90d, flow over ~30d (Veto #5 corroboration).
_FILING_LOOKBACK_DAYS = 180  # [ASSUMED]
_TOP_K_FILINGS = 5  # [ASSUMED]
_OHLCV_LOOKBACK_DAYS = 90  # [ASSUMED]
_FLOW_LOOKBACK_DAYS = 30  # [ASSUMED]
_HYBRID_LOOKBACK_DAYS = 30  # [ASSUMED]
_HYBRID_HIT_COUNT = 5  # [ASSUMED]
_PEER_METRICS: tuple[str, ...] = ("per", "pbr", "roe")

# Total serialization cap (Discretion #3, [ASSUMED]) — keeps the stdin bundle well
# inside the 200K model window and bounds per-call cost (RESEARCH Pitfall 1/4).
_STDIN_CHAR_CAP = 100_000  # [ASSUMED]

# Catalyst terms appended to the entity name for the hybrid narrative search.
_CATALYST_TERMS = "실적 공시 수주 계약 가이던스"


class NarrativeRef(BaseModel):
    """A full narrative body re-fetched for a hybrid hit (filing or note).

    ``body`` is already ``<untrusted>``-wrapped by the source tool (D-03) and is
    stored verbatim. Numeric/news hits carry no re-fetched body (there is no
    whole-body news tool), so they live only in ``EvidenceBundle.hybrid_hits``.
    """

    model_config = ConfigDict(extra="forbid")

    source_type: str  # "filing" | "note"
    ref: str  # rcept_no or note path
    body: str  # already wrapped via injection.wrap_untrusted (D-03)


class FilingHitBody(BaseModel):
    """A whole-body filing pre-fetched into the bundle (Veto #8).

    ``body_md`` is stored verbatim as returned by ``get_filing`` — already wrapped in
    the ``<untrusted>`` delimiter (D-03).
    """

    model_config = ConfigDict(extra="forbid")

    rcept_no: str
    title: str | None = None
    filed_at: str | None = None
    event_type: str | None = None
    body_md: str  # already wrapped via injection.wrap_untrusted (D-03)
    injection_suspected: bool = False


class EvidenceBundle(BaseModel):
    """The fixed pre-fetched evidence for one ticker (D-02).

    Holds the typed tool outputs directly (reusing ``mcp_v2.models`` types) so the
    same ``(corp_code, as_of)`` inputs reconstruct an EQUAL bundle. Narrative bodies
    keep their ``<untrusted>`` delimiters; numeric ranges stay typed (Veto #6).
    """

    model_config = ConfigDict(extra="forbid")

    corp_code: str
    ticker: str
    as_of: str  # ISO ``YYYY-MM-DD`` data cutoff
    filings: list[FilingHitBody] = Field(default_factory=list)
    ohlcv: OhlcvRange
    flow: FlowRange
    peers: list[PeerView] = Field(default_factory=list)
    hybrid_hits: list[SearchHit] = Field(default_factory=list)
    hybrid_bodies: list[NarrativeRef] = Field(default_factory=list)
    portfolio_note: NoteContent | None = None

    def to_stdin(self) -> str:
        """Deterministic, bounded serialization for the sub-agent subprocess stdin.

        Emits each narrative body INSIDE its existing ``<untrusted>`` delimiter
        (never re-wrapped or stripped) plus compact structured text for the numeric
        ranges/peers. Enforces :data:`_STDIN_CHAR_CAP` by dropping the lowest-weight
        WHOLE narrative body first (never truncating mid-body). Stable for a fixed
        bundle (same bundle ⇒ same string).
        """
        header = (
            f"# EVIDENCE BUNDLE\n"
            f"corp_code: {self.corp_code}\n"
            f"ticker: {self.ticker}\n"
            f"as_of: {self.as_of}\n"
        )
        numeric = self._render_numeric()

        # Narrative blocks in priority order (highest weight first). The user thesis
        # note ranks top; then filings newest-first; then hybrid re-fetched bodies.
        # Greedy include under the remaining budget → drops lowest-weight WHOLE
        # bodies first (never a partial body). Numeric + header are always kept.
        blocks: list[str] = []
        if self.portfolio_note is not None:
            blocks.append(_narrative_block("user_thesis", self.portfolio_note.path,
                                           self.portfolio_note.content_md))
        for f in self.filings:  # already newest-first from search_filings
            blocks.append(_narrative_block("filing", f.rcept_no, f.body_md))
        for nb in self.hybrid_bodies:
            blocks.append(_narrative_block(nb.source_type, nb.ref, nb.body))

        budget = _STDIN_CHAR_CAP - len(header) - len(numeric)
        kept: list[str] = []
        used = 0
        for block in blocks:
            if used + len(block) <= budget:
                kept.append(block)
                used += len(block)
            # else: drop this WHOLE body (never mid-body) and keep scanning smaller ones
        return header + "".join(kept) + numeric

    def _render_numeric(self) -> str:
        """Compact structured text for the numeric ranges + peers (Veto #6)."""
        lines = ["\n## NUMERIC\n"]
        lines.append(f"### ohlcv {self.ohlcv.ticker} ({len(self.ohlcv.bars)} bars)\n")
        lines.append("date,open,high,low,close,volume\n")
        for b in self.ohlcv.bars:
            lines.append(f"{b.trade_date},{b.open},{b.high},{b.low},{b.close},{b.volume}\n")
        lines.append(f"### flow {self.flow.ticker} ({len(self.flow.rows)} rows)\n")
        lines.append("date,foreign_net,inst_net,retail_net\n")
        for r in self.flow.rows:
            lines.append(f"{r.trade_date},{r.foreign_net},{r.inst_net},{r.retail_net}\n")
        lines.append("### peers\n")
        for p in self.peers:
            lines.append(f"{p.metric}: median={p.median} n={p.n} sector={p.sector}\n")
        return "".join(lines)


def _narrative_block(source: str, ref: str, wrapped_body: str) -> str:
    """One narrative section: a heading + the already-wrapped body verbatim."""
    return f"\n## {source} {ref}\n{wrapped_body}\n"


def _shift(iso_day: str, days: int) -> str:
    """``iso_day`` (``YYYY-MM-DD``) shifted back by ``days`` → ISO string."""
    return (date.fromisoformat(iso_day) - timedelta(days=days)).isoformat()


def build_bundle(
    engine: Engine,
    corp_code: str,
    as_of: str,
    *,
    portfolio_note_path: str | None = None,
) -> EvidenceBundle:
    """Pre-fetch ALL evidence for ``corp_code`` as of ``as_of`` into one bundle (D-02).

    Assembles the fixed snapshot via the in-process Phase-3 tools; the returned
    bundle is handed identically to Bull/Bear/Judge (they call no tools). Same
    ``(corp_code, as_of)`` on the same DB ⇒ equal bundle (reproducibility).

    Args:
        engine: the SQLAlchemy engine (used for ``resolve_entity``; the tools reach
            the same DB via their own ``get_engine()``).
        corp_code: the 8-digit DART corp code.
        as_of: ISO ``YYYY-MM-DD`` data cutoff (KST close).
        portfolio_note_path: if the ticker is held, the ``notes/private/`` thesis
            path — its note is fetched and attached (only-if-held policy lives in the
            caller). ``None`` ⇒ no portfolio note.

    Raises:
        ValueError: ``corp_code`` does not resolve to an entity, or the entity has
            no current ticker (numeric market tools need one).
    """
    entity = resolve_entity(engine, corp_code)
    if entity is None:
        raise ValueError(f"build_bundle: unknown corp_code {corp_code!r}")
    if entity.current_ticker is None:
        raise ValueError(
            f"build_bundle: entity {corp_code!r} has no current ticker "
            "(cannot fetch ohlcv/flow)"
        )
    ticker = entity.current_ticker

    # (1) recent filings → whole wrapped bodies for the top-K most recent (Veto #8).
    search = search_filings(corp_code, since=_shift(as_of, _FILING_LOOKBACK_DAYS))
    filings: list[FilingHitBody] = []
    seen_rcept: set[str] = set()
    for hit in search.hits[:_TOP_K_FILINGS]:
        detail = get_filing(hit.rcept_no)
        seen_rcept.add(hit.rcept_no)
        filings.append(
            FilingHitBody(
                rcept_no=detail.rcept_no,
                title=detail.title,
                filed_at=detail.filed_at,
                event_type=detail.event_type,
                body_md=detail.body_md,
                injection_suspected=detail.injection_suspected,
            )
        )

    # (2) numeric corroboration (Veto #5) — typed, no wrap (Veto #6).
    ohlcv = ohlcv_range(ticker, _shift(as_of, _OHLCV_LOOKBACK_DAYS), as_of)
    flow = flow_range(ticker, _shift(as_of, _FLOW_LOOKBACK_DAYS), as_of)
    peers = [peer_view(corp_code, m) for m in _PEER_METRICS]

    # (3) narrative hybrid search (name + catalyst terms) → re-fetch full bodies for
    #     the filing/note hits that matter (news has no whole-body tool).
    query = f"{entity.canonical_name} {_CATALYST_TERMS}"
    result = hybrid_search(
        query,
        date_range=(_shift(as_of, _HYBRID_LOOKBACK_DAYS), as_of),
        limit=_HYBRID_HIT_COUNT,
    )
    hybrid_bodies: list[NarrativeRef] = []
    for hit in result.hits:
        if hit.source_type == "filing":
            if hit.id_or_path in seen_rcept:
                continue  # already have the whole body in `filings`
            seen_rcept.add(hit.id_or_path)
            detail = get_filing(hit.id_or_path)
            hybrid_bodies.append(
                NarrativeRef(source_type="filing", ref=detail.rcept_no, body=detail.body_md)
            )
        elif hit.source_type == "note":
            note = get_note(hit.id_or_path)
            hybrid_bodies.append(
                NarrativeRef(source_type="note", ref=note.path, body=note.content_md)
            )
        # news hits keep only the wrapped snippet already in `hybrid_hits`.

    # (4) portfolio thesis note only if held (caller supplies the path).
    portfolio_note: NoteContent | None = None
    if portfolio_note_path is not None:
        portfolio_note = get_note(portfolio_note_path)

    return EvidenceBundle(
        corp_code=corp_code,
        ticker=ticker,
        as_of=as_of,
        filings=filings,
        ohlcv=ohlcv,
        flow=flow,
        peers=peers,
        hybrid_hits=list(result.hits),
        hybrid_bodies=hybrid_bodies,
        portfolio_note=portfolio_note,
    )
