"""D-03 / SC#3 numeric checksum — Korean-unit value-equivalence gate.

Pure Python. No LLM, no I/O.

The analysis brain compresses evidence; it never self-certifies its own numbers
(Veto #1/#4). Every numeric fact a sub-agent emits is UNTRUSTED until this module
confirms the value is derivable from the source ``body_md``. A fact whose value has
no value-equivalent span in the source is DROPPED and recorded in a warnings string
("실패 = drop the fact") — never silently kept.

D-03 deliberately chooses *value-equivalence* over the v1.0 exact at-offset echo-back
(``shared.number_sanity.check_echo_back``): Korean disclosures write the same magnitude
many ways (``42.5조원`` = ``42,500,000,000,000`` = ``425000억``), so an exact-string gate
mass-drops legitimately re-formatted values. We reuse the v1.0 normalization primitives
(``shared.units.normalize_to_krw`` + ``shared.number_extraction.extract_numeric_candidates``)
but compare on the normalized number within a relative tolerance.
"""

from __future__ import annotations

from typing import Any

from shared.number_extraction import NumericCandidate, extract_numeric_candidates
from shared.units import normalize_to_krw

__all__ = ["fact_supported", "checksum_facts"]

# Default relative tolerance (Discretion #4, [ASSUMED]). 0.5% absorbs rounded display
# (e.g. a body printing ``42.5조원`` for a precise 42,483,900,000,000) while staying tight
# enough that a genuinely wrong number does not slip through.
_DEFAULT_TOL = 0.005

# Trailing unit glyphs stripped off a candidate's raw_text before float()-ing. The
# numeric magnitude is recovered by pairing the stripped number with the candidate's
# ``guessed_unit`` (which drives the KRW multiplier), NOT by keeping the glyph.
_UNIT_GLYPHS = "조억백만원%배주포인트bps달러엔유로"


def _to_canonical(value: float, unit: str) -> float | None:
    """Normalize a (value, unit) pair to a single comparable number.

    KRW-family units (``KRW원``/``KRW백만``/``KRW억``/``KRW조``) collapse to KRW원 via
    ``normalize_to_krw``; every other unit (``pct``/``multiplier``/``shares``/foreign
    currency/``other``/…) keeps its raw scalar so pct-vs-pct and ×-vs-× compare directly.
    Returns ``None`` when a KRW unit is unrecognized (defensive — caller skips it).
    """
    if unit.startswith("KRW"):
        return normalize_to_krw(value, unit)
    return float(value)


def _candidate_canonical(cand: NumericCandidate) -> float | None:
    """Normalize one extracted source span the SAME way as the claim.

    Strips commas/whitespace and trailing unit glyphs, floats the remainder, then
    re-applies the candidate's ``guessed_unit``. Compound spans (e.g. ``42조5000억``)
    that do not float cleanly return ``None`` and are skipped — the plain single-denom
    forms elsewhere in the body carry the same magnitude.
    """
    cleaned = cand.raw_text.replace(",", "").replace(" ", "").rstrip(_UNIT_GLYPHS)
    try:
        num = float(cleaned)
    except ValueError:
        return None
    return _to_canonical(num, cand.guessed_unit)


def fact_supported(
    value: float,
    unit: str,
    body_md: str,
    tol: float = _DEFAULT_TOL,
) -> bool:
    """Return True iff the claimed (value, unit) is value-equivalent to some span in body.

    Normalizes the claim, scans ``body_md`` with ``extract_numeric_candidates`` (13 Korean
    unit families, whole body — Veto #8), normalizes each candidate identically, and matches
    on RELATIVE tolerance ``abs(c-target)/max(|c|,|target|,ε) <= tol``. The ``<untrusted>``
    wrapper on bundled narrative only adds delimiter lines (no inner bytes changed), so
    scanning the whole string is safe.
    """
    target = _to_canonical(value, unit)
    if target is None:
        return False
    for cand in extract_numeric_candidates(body_md):
        cv = _candidate_canonical(cand)
        if cv is None:
            continue
        if abs(cv - target) / max(abs(cv), abs(target), 1e-9) <= tol:
            return True
    return False


def checksum_facts(
    facts: list[dict[str, Any]],
    body_md: str,
    *,
    tol: float = _DEFAULT_TOL,
) -> tuple[dict[str, float | int], list[str]]:
    """Checksum the Judge's rich numeric facts against source; keep or drop each.

    ``facts`` are ``{key, value, unit, source_ref}`` dicts (the debate's rich shape). For
    each: if ``fact_supported`` holds, project ``{key: value}`` into the kept dict (the
    stored ``DecisionCard.numeric_facts`` shape ``dict[str, float | int]`` — the value's
    int/float type is preserved). Otherwise DROP it and append
    ``"{key}={value}{unit}: not verifiable in source"`` to the returned warnings list, so
    no dropped fact is silently lost (D-03 → ``DecisionCard.warnings``).

    Returns ``(kept, warnings)``. Pure — no I/O, no mutation of ``facts``.
    """
    kept: dict[str, float | int] = {}
    warnings: list[str] = []
    for fact in facts:
        key = fact["key"]
        value = fact["value"]
        unit = fact.get("unit", "")
        if fact_supported(value, unit, body_md, tol=tol):
            kept[key] = value
        else:
            warnings.append(f"{key}={value}{unit}: not verifiable in source")
    return kept, warnings
