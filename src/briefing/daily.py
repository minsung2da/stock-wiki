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
from typing import TYPE_CHECKING, NamedTuple
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from cards.models import Contradiction, DecisionCard

_log = logging.getLogger(__name__)
# KST is the canonical business-day boundary (mirrors runner.py:72 / gate.py:73). Never
# a naive date.today() — generated_at/expires_at are timestamptz +09:00 (Pitfall #3).
_KST = ZoneInfo("Asia/Seoul")


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
