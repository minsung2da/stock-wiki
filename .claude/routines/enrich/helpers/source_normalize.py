"""Source-aware deterministic normalization of `_derived` after the LLM call.

Two enforcement rules backed by Phase-5 D-13 + UAT observation:

1. **D-13 (sentiment scope):** macro and kind documents MUST have
   ``sentiment = None``. Macro is not firm-specific; KIND's ``event_type``
   already encodes direction. The Routine's first run on 2026-04-26 showed
   Sonnet 4.6 setting non-null sentiment on 3 of 4 macro docs despite the
   prompt telling it to use ``null`` — instruction-following on null/empty
   constraints is a known LLM weakness, so we enforce it deterministically.

2. **KRX ticker seeding:** KRX docs always carry the ticker in
   ``provenance.ticker`` (the 6-digit code is in the filename + frontmatter).
   The LLM has no business re-extracting it from the body. If the LLM
   returned an empty ``tickers`` list, seed it from provenance.

This is a normalize step, not a validate step — it does not raise. Call it
between Pydantic validation (SKILL step 12) and zone-integrity assertion
(SKILL step 15) so the written ``_derived`` is the normalized version.

No LLM-SDK imports (COLL-07 spirit).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.frontmatter import DerivedBlock, ProvenanceBlock


_SENTIMENT_NULL_SOURCES: frozenset[str] = frozenset({"macro", "kind"})


def normalize_derived_for_source(
    derived: DerivedBlock, provenance: ProvenanceBlock
) -> DerivedBlock:
    """Apply source-aware deterministic overrides to a DerivedBlock.

    Args:
        derived: The DerivedBlock just produced by the LLM (already
            Pydantic-validated). Mutated in place AND returned.
        provenance: The document's ProvenanceBlock — read-only here.

    Returns:
        The same ``derived`` object with fields normalized:

        - ``derived.sentiment = None`` if ``provenance.source`` is
          ``"macro"`` or ``"kind"``.
        - ``derived.tickers = [provenance.ticker]`` if
          ``provenance.source == "krx"`` and ``provenance.ticker`` is set
          and ``derived.tickers`` is currently empty.

    Idempotent: calling twice returns the same result.
    """
    source = provenance.source
    if source in _SENTIMENT_NULL_SOURCES:
        derived.sentiment = None
    if source == "krx" and provenance.ticker and not derived.tickers:
        derived.tickers = [provenance.ticker]
    return derived
