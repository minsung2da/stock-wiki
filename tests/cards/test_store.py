"""SC#4 integration tests for src/cards/store.py against live Postgres.

Exercises the four CRUD helpers end-to-end on a real Postgres 17 + vchord
testcontainer (via the ``seeded_engine`` fixture, which pre-inserts 삼성전자 /
00126380 / 005930 so the ``decision_cards.corp_code`` FK is satisfiable):

- save_card → get_active round-trip (incl. body_md)
- get_active returns None for an unseeded corp
- supersession ATOMICITY (RESEARCH Discretion #2 / T-02-09) — verified in a fresh
  connection so we only see committed state
- walk_supersedes ordered chain (newest → oldest)
- invalidate writes the reason into payload JSONB (OQ-1) and the RETURNED card has
  ``.status == 'invalidated'`` + ``.invalidation_reason == reason`` (this returned-
  object assertion is what proves the re-SELECT reconstruct does NOT raise under
  ``extra='forbid'`` — guarding the Plan-02 optional invalidation_reason field)
- walk_supersedes tolerates an invalidated card in the chain
- payload->'decision'->>'stance' survives the JSONB round-trip (Pitfall #3)

All test SQL uses bind params (never f-string interpolation).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from cards import (
    DecisionCard,
    get_active,
    invalidate,
    save_card,
    walk_supersedes,
)


def _make_card(
    decision_card_yaml: dict,
    *,
    card_id: str,
    generated_at: datetime | None = None,
) -> DecisionCard:
    """Build a distinct DecisionCard from the §3 oracle, overriding card_id/generated_at.

    Each card in a supersession chain needs a distinct ``card_id`` (PK) and a
    distinct ``generated_at`` so ``get_active``'s ``ORDER BY generated_at DESC``
    is deterministic.
    """
    data = dict(decision_card_yaml)
    data["card_id"] = card_id
    if generated_at is not None:
        data["generated_at"] = generated_at
    return DecisionCard.model_validate(data)


def test_save_and_get_active(seeded_engine, decision_card_yaml) -> None:
    card = _make_card(decision_card_yaml, card_id="card_A")
    returned_id = save_card(seeded_engine, card)
    assert returned_id == "card_A"

    fetched = get_active(seeded_engine, card.corp_code)
    assert fetched is not None
    assert isinstance(fetched, DecisionCard)
    assert fetched.card_id == "card_A"
    assert fetched.body_md == card.body_md
    # The fetched card carries the DB lifecycle status (a column, not part of the
    # authored §3 payload); the authored card was built with status=None.
    assert fetched.status == "active"
    # Full typed object round-trips (payload + body_md reconstruct == original),
    # excluding the DB-only lifecycle status column.
    assert fetched.model_dump(exclude={"status"}) == card.model_dump(
        exclude={"status"}
    )


def test_get_active_none(seeded_engine, decision_card_yaml) -> None:
    # Seed one card for the seeded corp, then query a DIFFERENT (unseeded) corp.
    save_card(seeded_engine, _make_card(decision_card_yaml, card_id="card_A"))
    assert get_active(seeded_engine, "99999999") is None


def test_supersession_atomic(seeded_engine, decision_card_yaml) -> None:
    base = datetime.fromisoformat("2026-05-28T17:42+09:00")
    card_a = _make_card(decision_card_yaml, card_id="card_A", generated_at=base)
    card_b = _make_card(
        decision_card_yaml,
        card_id="card_B",
        generated_at=base + timedelta(days=1),
    )

    save_card(seeded_engine, card_a)
    save_card(seeded_engine, card_b, supersedes="card_A")

    # Verify committed state in a FRESH connection — both effects must be visible.
    with seeded_engine.begin() as conn:
        rows = {
            r.card_id: r
            for r in conn.execute(
                text(
                    "SELECT card_id, status, superseded_by "
                    "FROM decision_cards WHERE card_id IN (:a, :b)"
                ),
                {"a": "card_A", "b": "card_B"},
            )
        }
    assert rows["card_A"].status == "superseded"
    assert rows["card_A"].superseded_by == "card_B"
    assert rows["card_B"].status == "active"
    assert rows["card_B"].superseded_by is None

    # get_active now returns B (the latest active, non-superseded card).
    active = get_active(seeded_engine, card_b.corp_code)
    assert active is not None
    assert active.card_id == "card_B"


def test_walk_supersedes(seeded_engine, decision_card_yaml) -> None:
    base = datetime.fromisoformat("2026-05-28T17:42+09:00")
    card_a = _make_card(decision_card_yaml, card_id="card_A", generated_at=base)
    card_b = _make_card(
        decision_card_yaml, card_id="card_B", generated_at=base + timedelta(days=1)
    )
    card_c = _make_card(
        decision_card_yaml, card_id="card_C", generated_at=base + timedelta(days=2)
    )

    save_card(seeded_engine, card_a)
    save_card(seeded_engine, card_b, supersedes="card_A")
    save_card(seeded_engine, card_c, supersedes="card_B")

    chain = walk_supersedes(seeded_engine, "card_C")
    assert [c.card_id for c in chain] == ["card_C", "card_B", "card_A"]
    assert all(isinstance(c, DecisionCard) for c in chain)


def test_invalidate(seeded_engine, decision_card_yaml) -> None:
    card_a = _make_card(decision_card_yaml, card_id="card_A")
    save_card(seeded_engine, card_a)

    updated = invalidate(seeded_engine, "card_A", "expired thesis")

    # The RETURNED object assertion proves the re-SELECT reconstruct did NOT raise
    # under extra='forbid' (relies on Plan 02's optional invalidation_reason field).
    assert updated is not None
    assert isinstance(updated, DecisionCard)
    assert updated.status == "invalidated"
    assert updated.invalidation_reason == "expired thesis"

    # DB row also shows the invalidated status + the reason in payload JSONB (OQ-1).
    with seeded_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT status, payload->>'invalidation_reason' AS reason "
                "FROM decision_cards WHERE card_id = :cid"
            ),
            {"cid": "card_A"},
        ).first()
    assert row is not None
    assert row.status == "invalidated"
    assert row.reason == "expired thesis"


def test_invalidate_missing_returns_none(seeded_engine, decision_card_yaml) -> None:
    assert invalidate(seeded_engine, "no_such_card", "n/a") is None


def test_walk_includes_invalidated(seeded_engine, decision_card_yaml) -> None:
    base = datetime.fromisoformat("2026-05-28T17:42+09:00")
    card_a = _make_card(decision_card_yaml, card_id="card_A", generated_at=base)
    card_b = _make_card(
        decision_card_yaml, card_id="card_B", generated_at=base + timedelta(days=1)
    )

    save_card(seeded_engine, card_a)
    save_card(seeded_engine, card_b, supersedes="card_A")

    # Invalidate the OLDEST card in the chain, then walk — reconstruct of the
    # invalidated card (payload now carries invalidation_reason) must NOT raise.
    invalidate(seeded_engine, "card_A", "thesis obsolete")

    chain = walk_supersedes(seeded_engine, "card_B")
    assert [c.card_id for c in chain] == ["card_B", "card_A"]
    # The invalidated card reconstructs with its reason intact.
    invalidated = chain[-1]
    assert invalidated.status == "invalidated"
    assert invalidated.invalidation_reason == "thesis obsolete"


def test_jsonb_payload_roundtrip(seeded_engine, decision_card_yaml) -> None:
    card = _make_card(decision_card_yaml, card_id="card_A")
    save_card(seeded_engine, card)

    with seeded_engine.begin() as conn:
        stance = conn.execute(
            text(
                "SELECT payload->'decision'->>'stance' "
                "FROM decision_cards WHERE card_id = :cid"
            ),
            {"cid": "card_A"},
        ).scalar()
    assert stance == card.decision.stance == "HOLD"
