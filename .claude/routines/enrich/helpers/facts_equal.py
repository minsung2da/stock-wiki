"""D-16 self-consistency comparator reference implementation.

Compares two DerivedBlock instances from the self-consistency double-pass
(both at temperature=0). Returns True iff the structured decision-critical
fields match; prose (summary, rationale, source_span whitespace) is ignored.

Per RESEARCH.md §Validation Architecture §5 (resolves Claude's Discretion
item #1). Used by the Routines skill post-LLM step.
"""

from __future__ import annotations

from shared.frontmatter import DerivedBlock, NumericFact


def _fact_tuple(f: NumericFact) -> tuple:
    """(key, round(value,4), unit) — ignores source_span / offset / value_krw churn."""
    return (f.key, round(f.value, 4), f.unit)


def facts_equal(a: DerivedBlock, b: DerivedBlock) -> bool:
    """D-16 logical equality for self-consistency double-pass."""
    a_sent = a.sentiment.label if a.sentiment else None
    b_sent = b.sentiment.label if b.sentiment else None
    return (
        sorted(a.tickers) == sorted(b.tickers)
        and a.event_type == b.event_type
        and sorted(a.catalysts) == sorted(b.catalysts)
        and a_sent == b_sent
        and frozenset(_fact_tuple(f) for f in a.numeric_facts)
        == frozenset(_fact_tuple(f) for f in b.numeric_facts)
    )
