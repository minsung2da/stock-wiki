"""src/briefing — Phase 5 daily/weekly briefing renderer.

The digest layer over ``decision_cards``: change detection, deterministic
prioritization (≤10), the 6-column ``body_md`` table render, and the weekly NET
roll-up. A briefing is persisted as a NULL-corp ``decision_cards`` row
(``report_type='daily_briefing'`` | ``'weekly_briefing'``) via
``cards.store.save_briefing`` and read back through the ``get_briefing`` MCP tool —
it is NOT a ``DecisionCard`` (05-RESEARCH §THE LANDMINE / Pitfall #1: a digest has no
single corp/ticker and — Veto #1/#4 — no stance/conviction).

Later plans (05-03 daily, 05-05 weekly) append their public export lines here; for
now this package exposes only the ``BriefingRow`` typed contract (``briefing.models``).
"""

from __future__ import annotations
