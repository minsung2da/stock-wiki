"""GRAPH-01 D-02: INSERT ... ON CONFLICT DO NOTHING — re-running edges.populate()
is a safe no-op."""

from __future__ import annotations

import sqlalchemy as sa

from ingest import edges as edges_mod
from ingest.edges import populate


def test_populate_twice_is_idempotent(pg_engine, seed_edges):
    """First call returns counters['inserted']>0. Second call on same doc_ids
    returns counters['inserted']==0 and counters['skipped_conflict']>=first_inserted."""
    seeded = seed_edges(with_event_chain=True)

    with pg_engine.begin() as conn:
        c1 = populate(seeded["doc_ids"], conn)
    assert c1["inserted"] > 0
    first_inserted = c1["inserted"]

    with pg_engine.connect() as conn:
        edges_count_after_first = conn.execute(sa.text("SELECT COUNT(*) FROM edges")).scalar()
    assert edges_count_after_first == first_inserted

    with pg_engine.begin() as conn:
        c2 = populate(seeded["doc_ids"], conn)
    assert c2["inserted"] == 0
    assert c2["skipped_conflict"] >= first_inserted

    with pg_engine.connect() as conn:
        edges_count_after_second = conn.execute(sa.text("SELECT COUNT(*) FROM edges")).scalar()
    assert edges_count_after_second == edges_count_after_first


def test_soft_fail_logs_to_failed_per_type(pg_engine, seed_edges, monkeypatch):
    """If one _derive_* function raises, populate() catches, fills
    counters['failed_per_type'][edge_type]=str(exc)[:200], and the OTHER
    derivations still run + commit. D-04."""
    seeded = seed_edges()

    def boom(*_args, **_kwargs):
        raise RuntimeError("synthetic boom for event_event")

    monkeypatch.setattr(edges_mod, "_derive_event_event", boom)
    # Re-bind the _DERIVATIONS table so the monkeypatched function is used.
    new_derivations = tuple(
        (et, boom if et == "event_event" else fn) for et, fn in edges_mod._DERIVATIONS
    )
    monkeypatch.setattr(edges_mod, "_DERIVATIONS", new_derivations)

    with pg_engine.begin() as conn:
        counters = populate(seeded["doc_ids"], conn)

    assert "event_event" in counters["failed_per_type"]
    assert "synthetic boom" in counters["failed_per_type"]["event_event"]
    # Truncation guard: must be <= 200 chars.
    assert len(counters["failed_per_type"]["event_event"]) <= 200
    # Other derivations must have run despite the failure.
    with pg_engine.connect() as conn:
        non_failed = conn.execute(
            sa.text("SELECT COUNT(*) FROM edges WHERE edge_type <> 'event_event'")
        ).scalar()
    assert non_failed > 0
    # Soft-fail: the populate() call did not raise.
    # (No assertion needed beyond the function having returned.)
