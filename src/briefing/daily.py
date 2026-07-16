"""src/briefing/daily.py — Phase 5 daily briefing generator (SC#1/2/3/6, D-01..D-06).

The heart of Phase 5: collect only what CHANGED across ``decision_cards``, rank by
urgency-of-human-review, render the ROADMAP-locked 6-column table, and persist a
``report_type='daily_briefing'`` row. Fully deterministic and LLM-free — every field is
extracted directly from card structure (D-06), so the render is pure string assembly
(this module imports NO ``subagents`` / no anthropic/openai, unlike ``analysis.runner``).

Change detection (D-02): the diff baseline is the prior active card in the supersession
chain — ``get_active`` + ``walk_supersedes(...)[1]``. A first-ever card counts only if it
is high-conviction (>= 0.8; D-03); a first card below 0.8 is noise and excluded.

The LOCKED payload ``entries[]`` are FLAT dicts and the sort key ``_priority_key`` is
DICT-keyed (never touches a ``ChangeEvent`` / ``.card`` attribute) so the weekly roll-up
(05-05) reuses ``_priority_key`` unchanged over ``payload["entries"]`` read back from the
store (SC#4 no-recompute enabler).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from cards import store
from db.engine import get_engine
from shared.portfolio import Portfolio, PortfolioLoadError

from .models import BriefingRow

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from cards.models import Contradiction, DecisionCard, KeyClaim

_log = logging.getLogger(__name__)
# KST is the canonical business-day boundary (mirrors runner.py:72 / gate.py:73). Never
# a naive date.today() — generated_at/expires_at are timestamptz +09:00 (Pitfall #3).
_KST = ZoneInfo("Asia/Seoul")

# Repo root for the optional portfolio.md load: src/briefing/daily.py -> parents[2].
_REPO_ROOT = Path(__file__).resolve().parents[2]

# D-01 event-class order (tier 2 of the sort key): a stance flip (the AI's read reversed)
# is the highest-signal event, above a strong-but-unchanged card. Reused UNCHANGED by the
# weekly (05-05) over the flat payload entries — hence a module-level dict, not an enum.
_EVENT_CLASS_RANK: dict[str, int] = {
    "stance_flip": 0,
    "new_contradiction": 1,
    "expired_invalidated": 2,
    "new_high_conviction": 3,
}

# key_claim ranking for the 근거 / Why-now cell: weight first, then confidence desc (D-06).
_WEIGHT_RANK: dict[str, int] = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "CONTEXT": 3}

# The ROADMAP-locked 6-column table (SC#3 / D-04). The header is asserted verbatim.
_TABLE_HEADER = "종목 | 변화 | 근거 | 제안 | Why now | Why not"
_TABLE_SEP = "--- | --- | --- | --- | --- | ---"
# SC#6 — a no-change day still renders a one-line body (never an empty page).
_EMPTY_BODY = "오늘 유의미한 변화 없음"

_MAX_ENTRIES = 10
# Rendered when a cell has no source value (empty key_claims / contradictions).
_DASH = "—"


class ChangeEvent(NamedTuple):
    """An INTERNAL diff result — NOT persisted, NOT the sort-key shape.

    Wraps the changed ``card`` plus its ``event_class`` and the human ``change`` delta
    string. ``build_entry`` maps it to the LOCKED flat entry-dict; the sort key operates
    on that dict, never on this object (so the weekly reuses ``_priority_key`` unchanged).
    """

    card: DecisionCard
    event_class: str
    change: str


# ---------------------------------------------------------------------------
# Task 1 — change detection (D-02 baseline, D-03 first-card, contradiction delta)
# ---------------------------------------------------------------------------
def _contradiction_key(c: Contradiction) -> tuple[str, str]:
    """Deterministic identity for a contradiction set-delta (RESEARCH A5)."""
    return (c.bull, c.bear_claim)


def _contradiction_delta(
    active: list[Contradiction], prior: list[Contradiction]
) -> int:
    """Count contradictions present in ``active`` but not in ``prior`` (by identity key)."""
    prior_keys = {_contradiction_key(c) for c in prior}
    return sum(1 for c in active if _contradiction_key(c) not in prior_keys)


def classify_change(
    active: DecisionCard, prior: DecisionCard | None
) -> ChangeEvent | None:
    """Classify the change of ``active`` vs its immediately-prior card (D-02/D-03).

    Precedence follows the D-01 event order: ``stance_flip`` > ``new_contradiction`` >
    ``new_high_conviction`` (``expired_invalidated`` is decided by the collect-set bucket
    in ``generate_daily_briefing``, not here). Returns ``None`` when nothing changed:

    - ``prior`` present: a stance flip (``PRIOR→NEW``), else a positive contradiction
      set-delta (``+N contradictions``), else ``None``. A conviction-only drift is NOT a
      change (RESEARCH A4 — no conviction event class).
    - ``prior`` absent (first-ever card): ``new_high_conviction`` iff conviction >= 0.8
      (``new (conv 0.83)``); a first card below 0.8 is noise → ``None`` (D-03).
    """
    if prior is not None:
        if active.decision.stance != prior.decision.stance:
            change = f"{prior.decision.stance}→{active.decision.stance}"
            return ChangeEvent(card=active, event_class="stance_flip", change=change)
        delta = _contradiction_delta(active.contradictions, prior.contradictions)
        if delta > 0:
            return ChangeEvent(
                card=active,
                event_class="new_contradiction",
                change=f"+{delta} contradictions",
            )
        return None

    # First-ever card (chain length 1): only high-conviction counts (D-03).
    if active.decision.conviction >= 0.8:
        change = f"new (conv {active.decision.conviction:.2f})"
        return ChangeEvent(
            card=active, event_class="new_high_conviction", change=change
        )
    return None


# ---------------------------------------------------------------------------
# Task 2 — build_entry + dict-keyed prioritization (D-01) + body_md render (D-04/05/06)
# ---------------------------------------------------------------------------
def _top_key_claim(card: DecisionCard) -> KeyClaim | None:
    """The leading key_claim: weight HIGH>MEDIUM>LOW>CONTEXT then confidence desc (D-06)."""
    if not card.key_claims:
        return None
    return sorted(
        card.key_claims,
        key=lambda kc: (_WEIGHT_RANK.get(kc.weight, 99), -kc.confidence),
    )[0]


def build_entry(event: ChangeEvent) -> dict:
    """Map a ``ChangeEvent`` to the LOCKED FLAT entry-dict (daily AND weekly sort shape).

    Keys (contract reused verbatim by 05-05): ``ticker``, ``name`` (optional, ``None`` —
    a card carries no entity name), ``event_class``, ``change`` (the delta string),
    ``evidence`` + ``why_now`` (both the top-ranked key_claim.text — the catalyst, D-06),
    ``stance`` + ``conviction`` (from the card decision — the 제안 source, D-05),
    ``why_not`` (the top contradiction's ``bear_claim`` or ``—`` when none, D-06), and
    ``card_id``. Every value is JSON-serializable so the store round-trips it as payload.
    """
    card = event.card
    top = _top_key_claim(card)
    evidence = top.text if top is not None else _DASH
    why_not = card.contradictions[0].bear_claim if card.contradictions else _DASH
    return {
        "ticker": card.ticker,
        "name": None,
        "event_class": event.event_class,
        "change": event.change,
        "evidence": evidence,
        "stance": card.decision.stance,
        "conviction": card.decision.conviction,
        "why_now": evidence,
        "why_not": why_not,
        "card_id": card.card_id,
    }


def _priority_key(entry: dict, held_tickers: set[str]) -> tuple[int, int, float]:
    """The D-01 3-level sort key over a FLAT entry-DICT — NEVER a ``ChangeEvent``/attribute.

    ``(held_rank, event_class_rank, -conviction)``: tier 1 held-first, tier 2 event class
    (``_EVENT_CLASS_RANK``), tier 3 conviction descending. This exact callable is imported
    and reused by the weekly (05-05) over ``payload["entries"]`` read back from the store,
    where NO ``DecisionCard`` object exists — so it must touch only dict keys (SC#4).
    """
    return (
        0 if entry["ticker"] in held_tickers else 1,
        _EVENT_CLASS_RANK[entry["event_class"]],
        -entry["conviction"],
    )


def load_held_tickers(*, held_tickers: set[str] | None = None) -> set[str]:
    """Resolve the held-ticker set for tier-1 held-first — NEVER raises (D-01 degradation).

    Returns the injected ``held_tickers`` if given (tests seed holdings without a real
    file); otherwise loads ``notes/private/portfolio.md``. A missing/malformed file
    (``PortfolioLoadError`` / ``ValidationError``) collapses the held tier to ``set()`` so
    every entry gets held_rank=1 and the sort stays deterministic on tiers 2+3 — the file
    is gitignored/absent until Phase 6, so this is the normal path today.
    """
    if held_tickers is not None:
        return set(held_tickers)
    try:
        portfolio = Portfolio.load(_REPO_ROOT)
    except (PortfolioLoadError, ValidationError):
        return set()
    return {h.ticker for h in portfolio.holdings}


def render_body_md(entries: list[dict]) -> str:
    """Render the ROADMAP-locked 6-column ``body_md`` table over the flat entry-dicts.

    Header is EXACTLY ``종목 | 변화 | 근거 | 제안 | Why now | Why not`` (SC#3 / D-04). The
    제안 cell is ``f"{stance} ({conviction:.2f})"`` — a bare stance label + conviction, NO
    forecast/target (D-05 / Veto #1). An empty ``entries`` renders the one-line no-change
    message (SC#6) instead of a header-only page.
    """
    if not entries:
        return _EMPTY_BODY
    lines = [_TABLE_HEADER, _TABLE_SEP]
    for e in entries:
        stance_cell = f"{e['stance']} ({e['conviction']:.2f})"
        name = e.get("name")
        jong = f"{e['ticker']} {name}" if name else e["ticker"]
        lines.append(
            f"{jong} | {e['change']} | {e['evidence']} | {stance_cell} | "
            f"{e['why_now']} | {e['why_not']}"
        )
    return "\n".join(lines)


def prioritize(events: list[ChangeEvent], held_tickers: set[str]) -> list[dict]:
    """Build the flat entry-dicts FIRST, THEN sort them, THEN truncate to <=10 (D-01/SC#1).

    ``build_entry`` runs before the sort so the SAME dict-keyed ``_priority_key`` is what
    orders both the daily (here) and the weekly (05-05, over payload rows) — there is no
    ``.card`` access anywhere in the sort.
    """
    entries = [build_entry(e) for e in events]
    entries.sort(key=lambda e: _priority_key(e, held_tickers))
    return entries[:_MAX_ENTRIES]


# ---------------------------------------------------------------------------
# Task 3 — generate_daily_briefing orchestrator + no-change short row (SC#6)
# ---------------------------------------------------------------------------
def _kst_close_on(d: date) -> datetime:
    """The 16:00 KST close on ``d`` — the timezone-safe as_of/expires anchor (Pitfall #3)."""
    return datetime(d.year, d.month, d.day, 16, 0, tzinfo=_KST)


def _keep_highest(
    mapping: dict[str, ChangeEvent], corp_code: str, event: ChangeEvent
) -> None:
    """Dedupe by corp, keeping the highest-priority (lowest-rank) event class (D-01)."""
    existing = mapping.get(corp_code)
    if existing is None or (
        _EVENT_CLASS_RANK[event.event_class]
        < _EVENT_CLASS_RANK[existing.event_class]
    ):
        mapping[corp_code] = event


def generate_daily_briefing(
    on_date: date,
    *,
    engine: Engine | None = None,
    held_tickers: set[str] | None = None,
) -> BriefingRow:
    """Collect -> classify -> prioritize -> render -> persist a ``daily_briefing`` row.

    Enumerates the date-D collect set via ``store.list_cards_for_briefing``: each
    newly-generated card is diffed against its D-02 supersession-chain baseline
    (``get_active`` + ``walk_supersedes(...)[1]``) through ``classify_change``; each
    expiring/invalidated card becomes an ``expired_invalidated`` event. Events are deduped
    per corp (highest-priority class wins), prioritized+truncated to <=10 flat entries,
    and persisted through ``store.save_briefing`` (SC#1/2). Deterministic + LLM-free (D-06).

    SC#6: even an EMPTY collect-set writes a real row (``entries=[]``, a one-line body) so
    ``get_briefing`` returns ``found=True`` — never an empty page. The payload is
    self-describing (carries ``card_id``/``report_type``/``report_date``/``generated_at``/
    ``as_of``/``expires_at``) so ``store.get_briefing_row`` reconstructs a ``BriefingRow``
    from it (the 05-02 write contract).

    Args:
        on_date: the KST business date the briefing covers.
        engine: SQLAlchemy engine; defaults to ``db.engine.get_engine()``.
        held_tickers: injected held set for tier-1 held-first; ``None`` loads
            ``portfolio.md`` (absent → ``set()``, held tier collapses — D-01 degradation).

    Returns:
        The persisted ``BriefingRow``.
    """
    engine = engine if engine is not None else get_engine()
    held = load_held_tickers(held_tickers=held_tickers)

    candidates = store.list_cards_for_briefing(engine, on_date)

    events_by_corp: dict[str, ChangeEvent] = {}
    for card in candidates.newly_generated:
        active = store.get_active(engine, card.corp_code)
        if active is None:
            continue
        chain = store.walk_supersedes(engine, active.card_id)
        prior = chain[1] if len(chain) >= 2 else None
        event = classify_change(active, prior)
        if event is not None:
            _keep_highest(events_by_corp, card.corp_code, event)

    for card in candidates.expiring:
        _keep_highest(
            events_by_corp,
            card.corp_code,
            ChangeEvent(card=card, event_class="expired_invalidated", change="expired"),
        )
    for card in candidates.invalidated:
        _keep_highest(
            events_by_corp,
            card.corp_code,
            ChangeEvent(
                card=card, event_class="expired_invalidated", change="invalidated"
            ),
        )

    entries = prioritize(list(events_by_corp.values()), held)

    generated_at = datetime.now(_KST)
    as_of = _kst_close_on(on_date)
    expires_at = _kst_close_on(on_date + timedelta(days=1))
    card_id = f"brief_daily_{on_date.isoformat()}"

    # Self-describing payload (05-02 contract) — get_briefing_row/get_daily_briefings_in_
    # range reconstruct the BriefingRow scalars FROM this dict, so every scalar rides here
    # as an ISO string (json.dumps-safe). ``entries`` is the LOCKED weekly-reuse shape.
    payload: dict = {
        "card_id": card_id,
        "report_type": "daily_briefing",
        "report_date": on_date.isoformat(),
        "generated_at": generated_at.isoformat(),
        "as_of": as_of.isoformat(),
        "expires_at": expires_at.isoformat(),
        "entries": entries,
        "generated_for": on_date.isoformat(),
    }

    row = BriefingRow(
        card_id=card_id,
        report_type="daily_briefing",
        report_date=on_date,
        generated_at=generated_at,
        as_of=as_of,
        expires_at=expires_at,
        payload=payload,
        body_md=render_body_md(entries),
    )
    store.save_briefing(engine, row)
    _log.info(
        "daily briefing generated",
        extra={"report_date": on_date.isoformat(), "entry_count": len(entries)},
    )
    return row
