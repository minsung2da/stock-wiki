"""GRAPH-01: deterministic edge derivations (ticker_sector, mentions_ticker,
note_ticker, supersedes). RESEARCH §Pattern 1 + §Code Examples.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from ingest.edges import populate


def test_ticker_sector_emits_one_edge_per_entity_with_sector(pg_engine, seed_edges):
    """For each entity row with sector IS NOT NULL, exactly one edge is created
    with src_type='ticker', src_id=current_ticker, dst_type='sector',
    dst_id=sector, edge_type='ticker_sector', tag='EXTRACTED'."""
    seeded = seed_edges()
    with pg_engine.begin() as conn:
        counters = populate(seeded["doc_ids"], conn)

    assert counters["failed_per_type"] == {}, counters
    with pg_engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT src_type, src_id, dst_type, dst_id, tag FROM edges "
                "WHERE edge_type = 'ticker_sector'"
            )
        ).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.src_type == "ticker"
    assert row.src_id == seeded["samsung_ticker"]
    assert row.dst_type == "sector"
    assert row.dst_id == seeded["sector"]
    assert row.tag == "EXTRACTED"


def test_mentions_ticker_from_provenance_block(pg_engine, seed_edges):
    """News docs with provenance.tickers=[TickerRef(ticker='005930',...)] produce
    edge (document, doc_id, ticker, '005930', 'mentions_ticker', 'EXTRACTED').
    DART docs with corp_code also fall back through entities.current_ticker."""
    seeded = seed_edges()
    with pg_engine.begin() as conn:
        populate(seeded["doc_ids"], conn)

    with pg_engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT src_id, dst_id, tag FROM edges "
                "WHERE edge_type = 'mentions_ticker' "
                "ORDER BY src_id"
            )
        ).all()
    assert len(rows) >= 1
    # Every row must point to Samsung's ticker.
    for r in rows:
        assert r.dst_id == seeded["samsung_ticker"]
        assert r.tag == "EXTRACTED"
    # Both the news doc and the DART doc should have produced an edge.
    src_ids = {r.src_id for r in rows}
    assert len(src_ids) >= 2  # news + dart fallback


def test_note_ticker_from_frontmatter_tickers_only(pg_engine, seed_edges):
    """Notes with frontmatter `tickers: ['005930']` produce edge (document, doc_id,
    ticker, '005930', 'note_ticker', 'EXTRACTED'). Body-text mentions are NOT used
    (D-08); body-only matches accumulate in counters['unmatched_body_tickers']."""
    seeded = seed_edges()
    with pg_engine.begin() as conn:
        counters = populate(seeded["doc_ids"], conn)

    with pg_engine.connect() as conn:
        rows = conn.execute(
            sa.text("SELECT src_id, dst_id, tag FROM edges WHERE edge_type = 'note_ticker'")
        ).all()
    assert len(rows) == 1
    assert rows[0].dst_id == seeded["samsung_ticker"]
    assert rows[0].tag == "EXTRACTED"

    # Body has 000660 (a 6-digit ticker not in the frontmatter list) and 005930.
    # 005930 is in the frontmatter list, so it should NOT appear in the
    # unmatched_body_tickers dict; 000660 should.
    unmatched = counters["unmatched_body_tickers"]
    assert "000660" in unmatched
    assert unmatched["000660"] >= 1


@pytest.mark.xfail(
    reason=(
        "probe-findings.md MISSING — DART writer does not surface a correction "
        "field; deferred to a quick task. _derive_supersedes is a soft no-op "
        "increment of counters['supersedes_skipped_no_field']."
    ),
    strict=True,
)
def test_supersedes_from_dart_correction_field(pg_engine, seed_edges):
    """If probe-findings.md FOUND the DART correction field, this test creates two
    DART docs where doc_B has correction_of=doc_A.rcept_no, and asserts edge
    (document, doc_B, document, doc_A, 'supersedes', 'EXTRACTED').
    Per probe-findings.md (2026-05-05): MISSING — Plan 02 Task 2 ships the
    no-op path; this assertion fails by design until the DART writer is
    extended."""
    seeded = seed_edges()
    with pg_engine.begin() as conn:
        populate(seeded["doc_ids"], conn)
    with pg_engine.connect() as conn:
        count = conn.execute(
            sa.text("SELECT COUNT(*) FROM edges WHERE edge_type = 'supersedes'")
        ).scalar()
    # Must be 0 today; xfail flips on intentional failure.
    assert count >= 1, "no supersedes edges emitted (expected: probe MISSING)"


def test_supersedes_soft_noop_increments_counter(pg_engine, seed_edges):
    """Companion to the xfail above: assert the no-op contract holds today —
    populate() returns counters['supersedes_skipped_no_field'] >= 1 and zero
    supersedes edges are inserted."""
    seeded = seed_edges()
    with pg_engine.begin() as conn:
        counters = populate(seeded["doc_ids"], conn)

    assert counters.get("supersedes_skipped_no_field", 0) >= 1
    with pg_engine.connect() as conn:
        count = conn.execute(
            sa.text("SELECT COUNT(*) FROM edges WHERE edge_type = 'supersedes'")
        ).scalar()
    assert count == 0
