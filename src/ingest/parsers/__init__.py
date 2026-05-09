"""Source-specific section parsers (D-06).

Each collector source registers a ``parse_sections(body, source)`` that
returns a list of Section objects. Plan 03 ships only the DART parser;
Plan 04+ may add ``news``, ``note``, etc.
"""

from __future__ import annotations

from .dart import Section

__all__ = ["parse_sections", "Section"]


def parse_sections(body: str, source: str) -> list[Section]:
    """Dispatch to the per-source parser.

    Unknown source raises ``ValueError`` with a GENERIC message that does
    NOT interpolate the user-supplied source value (info-disclosure
    hardening — threat T-3-15).
    """
    if source == "dart":
        from .dart import parse_sections as _parse

        return _parse(body, source)
    if source == "macro":
        from .macro import parse_sections as _parse

        return _parse(body, source)
    raise ValueError("unsupported source for section parsing")
