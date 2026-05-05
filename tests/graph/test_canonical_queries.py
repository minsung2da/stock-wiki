"""GRAPH-03 D-19: 5 canonical queries return non-empty subgraphs on fixture vault.
README parity: tests/graph/test_canonical_queries.py imports the SAME functions
the vault/graph/README.md inline snippets define (or imports from
src/graph/canonical.py if Plan 04 extracts them)."""

import pytest


@pytest.mark.skip(reason="Plan 04 Task 1 — Q1 Positions × 30d events SQL")
def test_q1_positions_recent_events_non_empty():
    """portfolio.holdings + edges (mentions_ticker | filing_event | note_ticker)
    + documents.first_seen_at >= today-30d returns >=1 row when fixture vault has
    a portfolio holding with at least one recent doc edge."""
    raise NotImplementedError


@pytest.mark.skip(reason="Plan 04 Task 1 — Q2 Catalyst chain BFS")
def test_q2_catalyst_chain_non_empty():
    """Recursive CTE over event_event edges from a seed event_id returns chain
    of length >=1 when fixture has 2+ same-corp_code docs within 90d."""
    raise NotImplementedError


@pytest.mark.skip(reason="Plan 04 Task 1 — Q3 Sector filing clusters")
def test_q3_sector_filings_non_empty():
    """Join edges ts(ticker_sector) with edges mt(mentions_ticker) + documents
    returns >=1 row for a sector with >=1 entity in fixture."""
    raise NotImplementedError


@pytest.mark.skip(reason="Plan 04 Task 1 — Q4 Supersedes chain")
def test_q4_supersedes_chain_non_empty_or_xfail_if_no_correction_field():
    """If probe-findings.md FOUND DART correction field, fixture has supersedes
    edge → recursive walk returns chain. Else xfail.

    Per probe-findings.md (2026-05-05): MISSING. Plan 04 Task 1 must xfail
    with reason='deferred quick task — DART correction field not yet wired'."""
    raise NotImplementedError


@pytest.mark.skip(reason="Plan 04 Task 1 — Q5 Notes ↔ events around ticker")
def test_q5_notes_events_non_empty():
    """For ticker with >=1 note_ticker edge AND >=1 mentions_ticker edge in
    fixture, function returns dict with both `notes` and `events` non-empty."""
    raise NotImplementedError


@pytest.mark.skip(reason="Plan 04 Task 2 — README snippets parity")
def test_readme_parity_imports_match_snippets():
    """vault/graph/README.md inline Python blocks parse and define the same
    function names as src/graph/canonical.py (q1_positions_recent_events,
    q2_catalyst_chain, q3_sector_filings, q4_supersedes_chain, q5_notes_events).
    Implementation: extract code blocks via regex, compile via ast.parse, collect
    FunctionDef names, compare to canonical.__all__."""
    raise NotImplementedError
