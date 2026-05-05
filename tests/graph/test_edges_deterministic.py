"""GRAPH-01: deterministic edge derivations (ticker_sector, mentions_ticker,
note_ticker, supersedes). RESEARCH §Pattern 1 + §Code Examples.
"""

import pytest


@pytest.mark.skip(reason="Plan 02 Task 2 — _derive_ticker_sector(doc_ids, conn, counters)")
def test_ticker_sector_emits_one_edge_per_entity_with_sector():
    """For each entity row with sector IS NOT NULL, exactly one edge is created
    with src_type='ticker', src_id=current_ticker, dst_type='sector',
    dst_id=sector, edge_type='ticker_sector', tag='EXTRACTED'."""
    raise NotImplementedError


@pytest.mark.skip(reason="Plan 02 Task 2 — _derive_mentions_ticker uses ProvenanceBlock.tickers")
def test_mentions_ticker_from_provenance_block():
    """News docs with provenance.tickers=[TickerRef(ticker='005930',...)] produce
    edge (document, doc_id, ticker, '005930', 'mentions_ticker', 'EXTRACTED')."""
    raise NotImplementedError


@pytest.mark.skip(reason="Plan 02 Task 2 — _derive_note_ticker reads frontmatter tickers[] (D-08)")
def test_note_ticker_from_frontmatter_tickers_only():
    """Notes with frontmatter `tickers: ['005930']` produce edge (document, doc_id,
    ticker, '005930', 'note_ticker', 'EXTRACTED'). Body-text mentions are NOT used
    (D-08); body-only matches accumulate in counters['unmatched_body_tickers'] dict."""
    raise NotImplementedError


@pytest.mark.skip(reason="Plan 02 Task 2 — _derive_supersedes (depends on probe-findings.md)")
def test_supersedes_from_dart_correction_field():
    """If probe-findings.md FOUND the DART correction field, this test creates two
    DART docs where doc_B has correction_of=doc_A.rcept_no, and asserts edge
    (document, doc_B, document, doc_A, 'supersedes', 'EXTRACTED').
    If probe-findings.md MISSING, test is xfail with reason='deferred quick task'.

    Per probe-findings.md (2026-05-05): MISSING — DART writer has no correction
    field. Plan 02 Task 2 must xfail this test with reason='deferred quick task'
    until the DART writer is extended."""
    raise NotImplementedError
