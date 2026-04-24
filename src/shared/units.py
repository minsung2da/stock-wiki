"""KRW normalization utility (D-09 value_krw computation).

Pure function. No I/O, no state. Called from the Routines enrichment skill
post-LLM validation to populate NumericFact.value_krw. Non-KRW units return
None — no silent FX conversion.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

KRW_MULTIPLIERS: Mapping[str, float] = MappingProxyType(
    {
        "KRW원": 1.0,
        "KRW백만": 1e6,
        "KRW억": 1e8,
        "KRW조": 1e12,
    }
)


def normalize_to_krw(value: float, unit: str) -> float | None:
    """Convert (value, unit) to KRW원. Returns None for non-KRW units.

    Pure function: deterministic, no I/O. FX conversions (USD->KRW etc.)
    are intentionally NOT performed here — non-KRW units yield None so the
    caller can decide downstream (currently: leave value_krw=None).

    Args:
        value: Raw numeric value reported in `unit`.
        unit: One of the 13 Literal units from NumericFact.unit. Defensive
            for any str (unknown unit -> None).

    Returns:
        Float KRW원 amount or None.
    """
    mult = KRW_MULTIPLIERS.get(unit)
    if mult is None:
        return None
    return float(value) * mult
