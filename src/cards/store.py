"""src/cards/store.py — CRUD + briefing store for decision_cards.

The original four locked helpers (RESEARCH Discretion #4 / 02-CONTEXT.md) plus the
Phase-5 briefing surface (``save_briefing`` / ``get_briefing_row`` /
``list_cards_for_briefing`` / ``get_daily_briefings_in_range``), all typed and
parameterized — there is NO generic ``run_sql`` escape hatch (Veto #7): the only way
to touch ``decision_cards`` from app code is through these functions.

- ``save_card(engine, card, *, supersedes=None) -> str``
  INSERT the new card; if a supersede id is given, flip the prior row to
  ``status='superseded'`` + ``superseded_by`` in the SAME ``with engine.begin()``
  transaction (atomic — a crash never leaves a dangling chain; RESEARCH
  Discretion #2 / T-02-09). Returns ``card.card_id``.
- ``get_active(engine, corp_code) -> DecisionCard | None``
  Latest active, non-superseded card for a corp, reconstructed into a full typed
  ``DecisionCard`` (payload + body_md). Returning the whole object — not a
  payload-only projection — keeps Phase 3's ``view=payload|both`` a serialize-time
  ``exclude`` rather than a re-query (Veto #13 layering; RESEARCH Discretion #4).
- ``walk_supersedes(engine, card_id) -> list[DecisionCard]``
  The supersession chain starting at ``card_id``, newest → oldest (each card's
  ``supersedes`` pointer followed down the chain).
- ``invalidate(engine, card_id, reason) -> DecisionCard | None``
  Set ``status='invalidated'`` and write ``reason`` INTO the payload JSONB via
  ``jsonb_set(payload, '{invalidation_reason}', to_jsonb(:reason))`` — OQ-1: the
  reason lives in payload, NOT in a new column, so the SC#1 locked column set is
  untouched. Returns the updated card (whose ``.invalidation_reason == reason``;
  the reconstruct only round-trips because Plan 02 declared the optional
  ``invalidation_reason`` field — without it ``extra='forbid'`` would raise).

SQL safety (T-02-07 / T-02-08): every statement is a module-level ``text()``
constant bound with parameters; identifiers and the invalidation reason NEVER reach
SQL via f-string interpolation. ``reason`` crosses as a ``to_jsonb(:reason)`` bind.

JSONB binding (RESEARCH Pitfall #3): ``card.model_dump(mode="json")`` first emits
ISO-8601 datetimes, then the dict is ``json.dumps``-serialized and bound as TEXT cast
to JSONB by Postgres — datetimes never corrupt the payload.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, NamedTuple
from zoneinfo import ZoneInfo

from sqlalchemy import text

from .models import DecisionCard

# KST is the canonical business-day boundary for enumeration + invalidation stamps.
# ``generated_at``/``expires_at`` are timestamptz (+09:00), so a UTC ``::date`` drifts
# for late-KST rows — the enumeration SELECTs cast AT TIME ZONE 'Asia/Seoul' first
# (mirrors runner.py:72 / gate.py:73; Pitfall #3).
_KST = ZoneInfo("Asia/Seoul")

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    # Annotation-only import (store.py has ``from __future__ import annotations``):
    # NO runtime import, so there is no cards→briefing cycle. The runtime construction
    # of a ``BriefingRow`` (get_briefing_row / get_daily_briefings_in_range) uses a
    # function-local import instead.
    from briefing.models import BriefingRow

__all__ = [
    "save_card",
    "get_active",
    "walk_supersedes",
    "invalidate",
    "save_briefing",
    "get_briefing_row",
    "list_cards_for_briefing",
    "get_daily_briefings_in_range",
    "BriefingCandidates",
]

# Secondary depth cap for walk_supersedes. The ``seen`` set already guarantees
# termination on any true cycle; this is a belt-and-suspenders ceiling that bounds
# an unexpectedly long (but acyclic) chain. 100 supersessions for one corp would
# itself be an anomaly worth investigating.
_MAX_SUPERSEDE_DEPTH = 100

# Store-layer-only fields kept OUT of the payload JSONB:
#   - body_md: owned by its dedicated TEXT column (Veto #8/#13 — excluding it keeps the
#     default view="payload" projection compact instead of leaking the full body).
#   - status: owned by the decision_cards.status lifecycle column.
#   - invalidation_reason: written into payload by invalidate()'s jsonb_set, never at save.
#   - invalidated_at: likewise stamped by invalidate() (05-02); excluding it keeps a
#     freshly-saved payload free of a null invalidated_at (mirrors invalidation_reason).
# Excluding all four keeps a freshly-saved payload exactly the §3 schema; _row_to_card
# re-injects body_md + status from their columns on read.
_PAYLOAD_EXCLUDE = {"body_md", "status", "invalidation_reason", "invalidated_at"}


# --- SQL constants (bind params only — Veto #7, never f-string) ---------------

_INSERT_CARD_SQL = text(
    """
    INSERT INTO decision_cards (
        card_id, corp_code, ticker,
        generated_at, as_of,
        payload, body_md,
        status, supersedes, superseded_by,
        expires_at, schema_version
    ) VALUES (
        :card_id, :corp_code, :ticker,
        :generated_at, :as_of,
        CAST(:payload AS jsonb), :body_md,
        'active', :supersedes, NULL,
        :expires_at, :schema_version
    )
    """
)

_INSERT_BRIEFING_SQL = text(
    """
    INSERT INTO decision_cards (
        card_id, corp_code, ticker,
        report_type, report_date,
        generated_at, as_of,
        payload, body_md,
        status, expires_at
    ) VALUES (
        :card_id, NULL, NULL,
        :report_type, :report_date,
        :generated_at, :as_of,
        CAST(:payload AS jsonb), :body_md,
        'active', :expires_at
    )
    """
)

_SUPERSEDE_PRIOR_SQL = text(
    """
    UPDATE decision_cards
       SET status = 'superseded',
           superseded_by = :new
     WHERE card_id = :old
       AND status = 'active'
    """
)

_SELECT_ACTIVE_SQL = text(
    """
    SELECT payload, body_md, status, supersedes, superseded_by
      FROM decision_cards
     WHERE corp_code = :cc
       AND status = 'active'
       AND superseded_by IS NULL
     ORDER BY generated_at DESC, card_id DESC
     LIMIT 1
    """
)

_SELECT_BY_ID_SQL = text(
    """
    SELECT payload, body_md, status, supersedes, superseded_by
      FROM decision_cards
     WHERE card_id = :cid
    """
)

_INVALIDATE_SQL = text(
    """
    UPDATE decision_cards
       SET status = 'invalidated',
           payload = jsonb_set(
               jsonb_set(
                   payload,
                   '{invalidation_reason}', to_jsonb(CAST(:reason AS text))
               ),
               '{invalidated_at}', to_jsonb(CAST(:invalidated_at AS text))
           )
     WHERE card_id = :cid
       AND status <> 'invalidated'
    """
)

# --- Briefing read + date-D enumeration SQL (05-02) ---------------------------

_SELECT_BRIEFING_ROW_SQL = text(
    """
    SELECT payload, body_md
      FROM decision_cards
     WHERE report_type = :rt
       AND report_date = :d
       AND status = 'active'
     ORDER BY generated_at DESC
     LIMIT 1
    """
)

# The date-D collect set (SC#1 / D-02). Each SELECT excludes briefing rows
# (``report_type IS NULL``) so a briefing never enumerates itself, and binds the
# KST business day via ``:d``. ``generated_at``/``expires_at`` cast AT TIME ZONE
# 'Asia/Seoul' first (Pitfall #3). A REFRESH preserves ``generated_at`` (gate.py
# invariant), so a refreshed card does NOT re-appear as newly-generated.
_SELECT_NEWLY_GENERATED_SQL = text(
    """
    SELECT payload, body_md, status
      FROM decision_cards
     WHERE (generated_at AT TIME ZONE 'Asia/Seoul')::date = :d
       AND status = 'active'
       AND report_type IS NULL
     ORDER BY generated_at DESC, card_id DESC
    """
)

_SELECT_EXPIRING_SQL = text(
    """
    SELECT payload, body_md, status
      FROM decision_cards
     WHERE (expires_at AT TIME ZONE 'Asia/Seoul')::date = :d
       AND status = 'active'
       AND report_type IS NULL
     ORDER BY generated_at DESC, card_id DESC
    """
)

_SELECT_INVALIDATED_SQL = text(
    """
    SELECT payload, body_md, status
      FROM decision_cards
     WHERE (CAST(payload->>'invalidated_at' AS timestamptz)
                AT TIME ZONE 'Asia/Seoul')::date = :d
       AND report_type IS NULL
     ORDER BY generated_at DESC, card_id DESC
    """
)

_SELECT_DAILIES_IN_RANGE_SQL = text(
    """
    SELECT payload, body_md
      FROM decision_cards
     WHERE report_type = 'daily_briefing'
       AND report_date BETWEEN :s AND :e
     ORDER BY report_date
    """
)


class BriefingCandidates(NamedTuple):
    """The date-D collect set for a daily briefing (SC#1).

    Three disjoint buckets of analysis cards (never briefing rows):
    ``newly_generated`` (a FULL debate wrote a new ``generated_at`` today),
    ``expiring`` (``expires_at`` falls today, still active), and ``invalidated``
    (``invalidate()`` stamped ``invalidated_at`` today). All KST-bounded.
    """

    newly_generated: list[DecisionCard]
    expiring: list[DecisionCard]
    invalidated: list[DecisionCard]


def _row_to_card(
    payload: dict[str, Any], body_md: str, status: str | None
) -> DecisionCard:
    """Reconstruct a ``DecisionCard`` from a stored row.

    ``body_md`` lives in its own column (Veto #8 — whole-card TEXT, never chunked)
    and ``status`` lives in the ``decision_cards.status`` lifecycle column (NOT the
    §3 payload), so both are merged back into the payload dict before validation —
    this is what lets the returned card surface ``.status`` (e.g. ``'invalidated'``).
    The payload may also already carry ``invalidation_reason`` (after ``invalidate``);
    the Plan-02 optional fields accept both under ``extra='forbid'``.
    """
    # ``body_md`` and ``status`` are intentionally injected from their dedicated
    # columns (they are excluded from the stored payload — see ``_PAYLOAD_EXCLUDE``),
    # so these explicit keys are the SOLE source for them, not a same-named override.
    data = {**payload, "body_md": body_md, "status": status}
    return DecisionCard.model_validate(data)


def save_card(
    engine: Engine,
    card: DecisionCard,
    *,
    supersedes: str | None = None,
) -> str:
    """Insert ``card`` (and atomically supersede a prior card if asked).

    The full ``card.model_dump(mode="json")`` is stored in the ``payload`` JSONB so
    ``get_active`` / ``walk_supersedes`` can reconstruct the whole typed object. The
    top-level columns (``generated_at``/``as_of``/``expires_at``/``schema_version``)
    are bound from the card — there is no server_default for the data-meaningful
    timestamps (OQ-2).

    If a supersede id is supplied (the ``supersedes`` keyword), the prior row is
    flipped to ``status='superseded'`` with ``superseded_by = card.card_id`` in the
    SAME transaction as the INSERT. The INSERT-new-then-UPDATE-old order satisfies
    the self-referential FK without ``use_alter``; the ``AND status='active'`` guard
    on the UPDATE makes it idempotent and prevents clobbering an already-invalidated
    prior card (RESEARCH Discretion #2 / T-02-09).

    Args:
        engine: SQLAlchemy engine (psycopg3).
        card: the typed ``DecisionCard`` to persist.
        supersedes: ``card_id`` of the prior card this one replaces, or ``None``.

    Returns:
        ``card.card_id``.
    """
    # The supersede id comes solely from the keyword arg; the DecisionCard model
    # (extra="forbid") declares no `supersedes` field to fall back on.
    effective_supersedes = supersedes

    payload = card.model_dump(mode="json", exclude=_PAYLOAD_EXCLUDE)
    params: dict[str, Any] = {
        "card_id": card.card_id,
        "corp_code": card.corp_code,
        "ticker": card.ticker,
        "generated_at": card.generated_at,
        "as_of": card.as_of,
        "payload": json.dumps(payload),
        "body_md": card.body_md,
        "supersedes": effective_supersedes,
        "expires_at": card.expires_at,
        "schema_version": card.schema_version,
    }

    with engine.begin() as conn:
        conn.execute(_INSERT_CARD_SQL, params)
        if effective_supersedes is not None:
            conn.execute(
                _SUPERSEDE_PRIOR_SQL,
                {"new": card.card_id, "old": effective_supersedes},
            )
    return card.card_id


def save_briefing(engine: Engine, row: BriefingRow) -> str:
    """Insert a briefing row (NULL corp_code/ticker) and return its ``card_id``.

    A SEPARATE write path from ``save_card`` (05-RESEARCH §THE LANDMINE): a briefing
    is not a ``DecisionCard`` and has no single corp, so this binds
    ``corp_code``/``ticker`` to NULL and sets ``report_type``/``report_date`` — the
    two columns migration 0009 added. There is NO supersede branch: a briefing never
    supersedes an analysis card. ``status`` is ``'active'`` and ``schema_version`` is
    left to the column server_default.

    The payload is bound via ``json.dumps(row.payload)`` → ``CAST(:payload AS jsonb)``
    (the same TEXT-cast bind as ``save_card`` — Pitfall #3, datetimes never corrupt),
    NEVER the raw dict. The payload is expected to be self-describing (carry the
    scalar metadata) so ``get_briefing_row`` can reconstruct a ``BriefingRow`` from it.

    Args:
        engine: SQLAlchemy engine (psycopg3).
        row: the typed ``BriefingRow`` to persist.

    Returns:
        ``row.card_id``.
    """
    params: dict[str, Any] = {
        "card_id": row.card_id,
        "report_type": row.report_type,
        "report_date": row.report_date,
        "generated_at": row.generated_at,
        "as_of": row.as_of,
        "payload": json.dumps(row.payload),
        "body_md": row.body_md,
        "expires_at": row.expires_at,
    }
    with engine.begin() as conn:
        conn.execute(_INSERT_BRIEFING_SQL, params)
    return row.card_id


def get_active(engine: Engine, corp_code: str) -> DecisionCard | None:
    """Return the latest active, non-superseded card for ``corp_code``.

    ``SELECT ... WHERE corp_code=:cc AND status='active' AND superseded_by IS NULL
    ORDER BY generated_at DESC LIMIT 1``, reconstructed into a full typed
    ``DecisionCard`` (payload + body_md). Returns ``None`` when no active card
    exists for the corp.
    """
    with engine.begin() as conn:
        row = conn.execute(_SELECT_ACTIVE_SQL, {"cc": corp_code}).first()
    if row is None:
        return None
    return _row_to_card(row.payload, row.body_md, row.status)


def walk_supersedes(engine: Engine, card_id: str) -> list[DecisionCard]:
    """Return the supersession chain starting at ``card_id``, newest → oldest.

    Begins at ``card_id`` and follows each card's ``supersedes`` pointer down the
    chain, so the returned list is ordered ``[card_id, its predecessor, ...,
    oldest]``. Cards anywhere in the chain that have been invalidated reconstruct
    fine — their payload carries ``invalidation_reason``, which the Plan-02 optional
    field accepts under ``extra='forbid'``. A depth guard (max 100) prevents an
    accidental cycle from looping forever.

    Returns an empty list if ``card_id`` does not exist.
    """
    chain: list[DecisionCard] = []
    seen: set[str] = set()
    current: str | None = card_id

    with engine.begin() as conn:
        while (
            current is not None
            and current not in seen
            and len(chain) < _MAX_SUPERSEDE_DEPTH
        ):
            seen.add(current)
            row = conn.execute(_SELECT_BY_ID_SQL, {"cid": current}).first()
            if row is None:
                break
            chain.append(_row_to_card(row.payload, row.body_md, row.status))
            current = row.supersedes
    return chain


def invalidate(engine: Engine, card_id: str, reason: str) -> DecisionCard | None:
    """Invalidate ``card_id`` and stamp ``reason`` + ``invalidated_at`` into payload.

    Sets ``status='invalidated'`` and writes BOTH ``reason`` and a KST ISO-8601
    ``invalidated_at`` timestamp into the payload via nested
    ``jsonb_set`` (OQ-1 option a — both live inside payload; NO new column, so the
    SC#1 column set is untouched). The ``invalidated_at`` stamp is what makes
    "invalidated on date D" queryable by ``list_cards_for_briefing`` (05-02). Re-selects
    and returns the updated ``DecisionCard`` (with ``.status == 'invalidated'``,
    ``.invalidation_reason == reason``, and ``.invalidated_at`` set).

    The UPDATE carries ``AND status <> 'invalidated'`` so the call is idempotent and
    chain-safe: re-invalidating an already-invalidated card is a no-op (``rowcount==0``
    → returns ``None``) that does NOT clobber the original ``invalidation_reason``.
    A currently-``active`` or ``superseded`` card CAN be invalidated — the
    ``active → invalidated`` and ``superseded → invalidated`` transitions are both
    intended (an invalidated card may legitimately sit mid-chain). Returns ``None`` if
    no card with that id existed OR the card was already invalidated.

    The reconstruct round-trips ONLY because Plan 02 declared the optional
    ``invalidation_reason`` field — the payload now contains that key, which
    ``extra='forbid'`` would otherwise reject.
    """
    with engine.begin() as conn:
        result = conn.execute(
            _INVALIDATE_SQL,
            {
                "cid": card_id,
                "reason": reason,
                # KST ISO stamp so "invalidated on date D" is queryable by
                # list_cards_for_briefing (05-RESEARCH OQ1 option a — payload, no column).
                "invalidated_at": datetime.now(_KST).isoformat(),
            },
        )
        if result.rowcount == 0:
            return None
        row = conn.execute(_SELECT_BY_ID_SQL, {"cid": card_id}).first()
    if row is None:
        return None
    return _row_to_card(row.payload, row.body_md, row.status)


def _row_to_briefing(payload: dict[str, Any], body_md: str) -> BriefingRow:
    """Reconstruct a ``BriefingRow`` from a stored briefing row.

    The scalar fields (``card_id``/``report_type``/``report_date``/``generated_at``/
    ``as_of``/``expires_at``) come from the self-describing ``payload`` (05-02 write
    contract); ``body_md`` comes from its dedicated column. Pydantic coerces the
    payload's ISO-8601 date/datetime strings back into ``date``/``datetime``.
    """
    # Runtime import (not module-level TYPE_CHECKING) — briefing.models imports nothing
    # from cards, so this is safe; the local import keeps the store's import graph clean.
    from briefing.models import BriefingRow

    return BriefingRow(
        card_id=payload["card_id"],
        report_type=payload["report_type"],
        report_date=payload["report_date"],
        generated_at=payload["generated_at"],
        as_of=payload["as_of"],
        expires_at=payload["expires_at"],
        payload=payload,
        body_md=body_md,
    )


def get_briefing_row(
    engine: Engine, report_type: str, report_date: date
) -> BriefingRow | None:
    """Return the active briefing row for ``(report_type, report_date)`` or ``None``.

    The delegate the ``get_briefing`` MCP tool will call (SC#5): the tool inlines NO
    ``text()`` (the SC#3 AST guard forbids it), so all briefing SELECT SQL lives here.
    ``SELECT payload, body_md ... ORDER BY generated_at DESC LIMIT 1`` picks the newest
    active row for the date, reconstructed into a full typed ``BriefingRow`` from the
    self-describing payload.
    """
    with engine.begin() as conn:
        row = conn.execute(
            _SELECT_BRIEFING_ROW_SQL, {"rt": report_type, "d": report_date}
        ).first()
    if row is None:
        return None
    return _row_to_briefing(row.payload, row.body_md)


def list_cards_for_briefing(engine: Engine, on_date: date) -> BriefingCandidates:
    """Enumerate the date-D collect set for a daily briefing (SC#1 / D-02).

    Three parameterized, KST-bounded SELECTs — newly-generated, expiring, and
    invalidated analysis cards for ``on_date`` — each excluding briefing rows
    (``report_type IS NULL``). Returns the three buckets as a ``BriefingCandidates``
    NamedTuple. This is the enumeration helper 05-RESEARCH flagged as missing; the
    daily module diffs each card via ``get_active`` + ``walk_supersedes`` (no new
    store code needed for the diff read).
    """
    with engine.begin() as conn:
        newly = [
            _row_to_card(r.payload, r.body_md, r.status)
            for r in conn.execute(_SELECT_NEWLY_GENERATED_SQL, {"d": on_date})
        ]
        expiring = [
            _row_to_card(r.payload, r.body_md, r.status)
            for r in conn.execute(_SELECT_EXPIRING_SQL, {"d": on_date})
        ]
        invalidated = [
            _row_to_card(r.payload, r.body_md, r.status)
            for r in conn.execute(_SELECT_INVALIDATED_SQL, {"d": on_date})
        ]
    return BriefingCandidates(
        newly_generated=newly, expiring=expiring, invalidated=invalidated
    )


def get_daily_briefings_in_range(
    engine: Engine, start_date: date, end_date: date
) -> list[BriefingRow]:
    """Return the ``daily_briefing`` rows in ``[start_date, end_date]``, date-ordered.

    The weekly roll-up's source (SC#4): the weekly reads these pre-materialized daily
    payloads and aggregates per-ticker NET change — it never recomputes a daily. Rows
    are reconstructed into typed ``BriefingRow`` objects, ordered by ``report_date``.
    """
    with engine.begin() as conn:
        rows = conn.execute(
            _SELECT_DAILIES_IN_RANGE_SQL, {"s": start_date, "e": end_date}
        ).all()
    return [_row_to_briefing(r.payload, r.body_md) for r in rows]
