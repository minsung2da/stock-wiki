"""GRAPH-01: INFERRED edge derivations (filing_event, event_event 90-day window).
RESEARCH §Pitfall 1 + §"event_event derivation"."""

from __future__ import annotations

import sqlalchemy as sa

from ingest.edges import populate


def test_filing_event_from_derived_event_type_single_field(pg_engine, seed_edges):
    """Document with _derived.event_type='earnings_release' produces edge
    (document, doc_id, event, '<corp_code>-earnings_release-<first_seen_at>',
    'filing_event', 'INFERRED'). RESEARCH Pitfall 2: there is no
    _derived.events list — only the singular event_type field. The event id
    convention is '{corp_code}-{event_type}-{first_seen_at_iso}'."""
    seeded = seed_edges()
    with pg_engine.begin() as conn:
        populate(seeded["doc_ids"], conn)

    with pg_engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT src_type, dst_type, dst_id, tag FROM edges WHERE edge_type = 'filing_event'"
            )
        ).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.src_type == "document"
    assert row.dst_type == "event"
    # Event id format: {corp_code}-{event_type}-{ISO timestamp}
    assert row.dst_id.startswith(f"{seeded['samsung_corp']}-earnings_release-")
    assert row.tag == "INFERRED"


def test_event_event_within_90_days(pg_engine, seed_edges):
    """Two same-corp_code DART docs 30 days apart produce one event_event edge.
    Boundary rule per RESEARCH §event_event derivation: 0 < delta <= 90 inclusive.
    """
    seeded = seed_edges(with_event_chain=True)
    with pg_engine.begin() as conn:
        populate(seeded["doc_ids"], conn)

    with pg_engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT src_type, src_id, dst_type, dst_id, tag FROM edges "
                "WHERE edge_type = 'event_event'"
            )
        ).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.src_type == "event"
    assert row.dst_type == "event"
    # Earlier event (earnings_release) should be src; later (dividend) should be dst.
    assert "earnings_release" in row.src_id
    assert "dividend" in row.dst_id
    assert row.tag == "INFERRED"
