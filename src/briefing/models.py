"""src/briefing/models.py — the typed briefing-row contract (Phase 5, SC#2).

A briefing row lives in ``decision_cards`` (``report_type='daily_briefing'`` |
``'weekly_briefing'``) but is NOT a ``DecisionCard``: a digest has no single
``corp_code``/``ticker`` and — per Veto #1 (no price prediction) / Veto #4 (no
black-box score) — no ``stance``/``conviction``. Inventing those would be dishonest,
so ``BriefingRow`` is a SEPARATE model that carries ONLY what a digest legitimately
has: its row identity, the report kind/date, the KST timestamps, and the
``payload`` + ``body_md`` pair the store persists.

``extra='forbid'`` (ASVS V5 discipline, project-wide) rejects unknown keys before a
malformed payload could reach storage. This module MUST NOT import or extend
``DecisionCard`` (05-RESEARCH §THE LANDMINE / Pitfall #1 — the warning sign is any
Phase-5 code importing ``cards.models.DecisionCard`` to build a briefing).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class BriefingRow(BaseModel):
    """A daily/weekly briefing persisted as a NULL-corp ``decision_cards`` row.

    NOT a ``DecisionCard`` — it declares none of the five analysis-card required
    fields (``corp_code``, ``ticker``, ``decision``, ``assumptions`` ``min_length=1``,
    a per-ticker thesis). ``report_type`` is constrained to the two briefing kinds the
    migration-0009 ``ck_decision_cards_report_type`` CHECK allows.

    Fields:
        card_id: the ``decision_cards`` PK for this briefing row.
        report_type: ``'daily_briefing'`` or ``'weekly_briefing'``.
        report_date: the KST date the briefing covers (the timezone-safe DATE the
            ``get_briefing`` lookup matches by equality).
        generated_at: when the briefing was materialized (KST).
        as_of: the data cutoff the briefing reflects (KST close).
        expires_at: when this briefing goes stale (daily → next KST close; weekly →
            week_end + 7d).
        payload: the machine-readable digest (``{"entries": [...], ...}``). It is
            self-describing — it MUST carry the scalar metadata (``card_id``,
            ``report_type``, ``report_date``, ``generated_at``, ``as_of``,
            ``expires_at``) so ``cards.store.get_briefing_row`` can reconstruct this
            model from the stored ``payload`` alone.
        body_md: the human-readable 6-column table (SC#3), stored but NOT shipped to
            context by ``get_briefing`` (Veto #13).
    """

    model_config = ConfigDict(extra="forbid")

    card_id: str
    report_type: Literal["daily_briefing", "weekly_briefing"]
    report_date: date
    generated_at: datetime
    as_of: datetime
    expires_at: datetime
    payload: dict
    body_md: str
