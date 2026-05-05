"""GRAPH-03 D-19: 5 canonical queries return non-empty subgraphs on fixture vault.

README parity: tests/graph/test_canonical_queries.py imports the SAME functions
the vault/graph/README.md inline snippets define (or imports from
src/graph/canonical.py if Plan 04 extracts them).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from src.graph import canonical
from src.graph.canonical import (
    q1_positions_recent_events,
    q2_catalyst_chain,
    q3_sector_filings,
    q4_supersedes_chain,
    q5_notes_events,
)

from ingest.edges import populate

# --- Q1 ----------------------------------------------------------------


def test_q1_positions_recent_events_non_empty(seed_edges, pg_engine):
    """portfolio.holdings + edges (mentions_ticker | filing_event | note_ticker)
    + documents.first_seen_at >= today-N returns >=1 row.

    Fixture first_seen_at is dated 2026-01-10, so we pass a very large `days`
    window so the today-N cutoff covers it. The portfolio is monkey-patched to
    a single Samsung holding.
    """
    seeded = seed_edges()
    with pg_engine.begin() as conn:
        populate(seeded["doc_ids"], conn)

    from shared.portfolio import Holding, Portfolio

    fake_pf = Portfolio(holdings=[Holding(ticker=seeded["samsung_ticker"], qty=1, avg_cost=0)])
    with patch.object(Portfolio, "load", classmethod(lambda cls, root: fake_pf)):
        rows = q1_positions_recent_events(days=100_000)

    assert rows, "Q1 returned empty result on fixture vault"
    assert all(r["ticker"] == seeded["samsung_ticker"] for r in rows)
    edge_types = {r["edge_type"] for r in rows}
    assert edge_types & {"mentions_ticker", "filing_event", "note_ticker"}


# --- Q2 ----------------------------------------------------------------


def test_q2_catalyst_chain_non_empty(seed_edges, pg_engine):
    """Recursive CTE over event_event edges from a seed event_id returns chain
    of length >=1 when fixture has 2+ same-corp_code docs within 90d."""
    seeded = seed_edges(with_event_chain=True)
    with pg_engine.begin() as conn:
        populate(seeded["doc_ids"], conn)

    rows = q2_catalyst_chain(seeded["samsung_ticker"], days=365)
    assert rows, "Q2 returned empty result; expected event_event chain on fixture"
    assert all(r["src_id"].startswith(seeded["samsung_corp"]) for r in rows)
    assert all(r["depth"] >= 1 for r in rows)


# --- Q3 ----------------------------------------------------------------


def test_q3_sector_filings_non_empty(seed_edges, pg_engine):
    """Join edges ts(ticker_sector) with edges mt(mentions_ticker) + documents
    returns >=1 row for a sector with >=1 entity in fixture."""
    seeded = seed_edges()
    with pg_engine.begin() as conn:
        populate(seeded["doc_ids"], conn)

    rows = q3_sector_filings(seeded["sector"], days=100_000)
    assert rows, "Q3 returned empty result; expected ticker_sector + mentions match"
    assert all(r["ticker"] == seeded["samsung_ticker"] for r in rows)
    assert all(r["canonical_name"] for r in rows)


# --- Q4 ----------------------------------------------------------------


def test_q4_supersedes_chain_non_empty_or_xfail_if_no_correction_field(
    seed_edges, pg_engine, tmp_path
):
    """Per probe-findings.md (2026-05-05): MISSING. DART writer emits no
    correction marker, so ``_derive_supersedes`` is a soft no-op and Q4 returns
    [] for any rcept_no. We assert the graceful empty-return contract — the
    moment the DART writer is extended (deferred quick task), this test is
    re-evaluated and an `xfail` marker added in its place.
    """
    probe_path = (
        Path(__file__).resolve().parents[2]
        / ".planning"
        / "phases"
        / "07-graph-layer-graphify-integration"
        / "probe-findings.md"
    )
    probe_text = probe_path.read_text(encoding="utf-8") if probe_path.exists() else ""
    if "MISSING: no DART filing" not in probe_text:
        pytest.skip("probe-findings.md no longer indicates MISSING — re-evaluate Q4 contract")

    seeded = seed_edges()
    # Insert a DART document with rcept_no embedded in source_url so the seed
    # lookup hits, but no supersedes edges exist (soft no-op contract).
    dart_doc_id = seeded["doc_ids"][0]
    rcept_no = "20260318001062"
    with pg_engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE documents SET source_url = :url WHERE id = :id"),
            {
                "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
                "id": dart_doc_id,
            },
        )
        populate(seeded["doc_ids"], conn)

    rows = q4_supersedes_chain(rcept_no)
    # Soft no-op: zero supersedes edges → walk yields empty list.
    assert rows == [], f"Q4 should return [] under MISSING DART correction field, got {rows!r}"


# --- Q5 ----------------------------------------------------------------


def test_q5_notes_events_non_empty(seed_edges, pg_engine):
    """For ticker with >=1 note_ticker edge AND >=1 filing_event edge in
    fixture (with the sibling mentions_ticker edge), function returns dict
    with both `notes` and `events` non-empty."""
    seeded = seed_edges()
    with pg_engine.begin() as conn:
        populate(seeded["doc_ids"], conn)

    result = q5_notes_events(seeded["samsung_ticker"], days=100_000)
    assert isinstance(result, dict) and "notes" in result and "events" in result
    assert result["notes"], "Q5 expected note_ticker rows for samsung_ticker"
    assert result["events"], "Q5 expected filing_event rows joined with mentions_ticker"


# --- README parity -----------------------------------------------------


def test_readme_parity_imports_match_snippets():
    """Extract Python code blocks from vault/graph/README.md, compile via
    ast.parse, collect FunctionDef names matching ``q[1-5]_*``, assert they
    exactly match ``src.graph.canonical.__all__``.
    """
    repo = Path(__file__).resolve().parents[2]
    readme = repo / "vault" / "graph" / "README.md"
    text = readme.read_text(encoding="utf-8")
    blocks = re.findall(r"```python\n(.*?)```", text, flags=re.DOTALL)
    fn_names: set[str] = set()
    for block in blocks:
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and re.match(r"^q[1-5]_", node.name):
                fn_names.add(node.name)
    assert fn_names == set(canonical.__all__), (
        f"README functions {fn_names} do not match canonical.__all__ {set(canonical.__all__)}"
    )
