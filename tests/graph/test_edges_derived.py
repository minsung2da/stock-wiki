"""GRAPH-01: INFERRED edge derivations (filing_event, event_event 90-day window).
RESEARCH §Pitfall 1 + §"event_event derivation"."""

import pytest


@pytest.mark.skip(
    reason="Plan 02 Task 2 — _derive_filing_event uses _derived.event_type single field"
)
def test_filing_event_from_derived_event_type_single_field():
    """Document with _derived.event_type='earnings_release' produces edge
    (document, doc_id, event, '<corp_code>-earnings_release-<first_seen_at>',
    'filing_event', 'INFERRED'). RESEARCH Pitfall 2: there is no _derived.events
    LIST — only the singular event_type field. The event id convention is
    '{corp_code}-{event_type}-{first_seen_at_iso}' (Plan 02 finalises)."""
    raise NotImplementedError


@pytest.mark.skip(reason="Plan 02 Task 2 — _derive_event_event 90-day sliding window")
def test_event_event_within_90_days():
    """Three docs same corp_code, dates D, D+30, D+125. Adjacent pairs:
      - (D → D+30) gets event_event edge (delta=30, within 0<delta<=90)
      - (D+30 → D+125) does NOT get edge (delta=95, exceeds 90).
    Boundary rule per RESEARCH §event_event derivation: 0 < delta <= 90 inclusive."""
    raise NotImplementedError
