"""Phase 8 GAP-04 — parse_sections dispatch contract.

Guards source dispatch (dart, macro) and the T-3-15 info-disclosure
hardening (unknown sources raise a generic ValueError that does NOT
interpolate user input).
"""

from __future__ import annotations

import pytest

from ingest.parsers import parse_sections


def test_macro_dispatched():
    sections = parse_sections("body text", "macro")
    assert len(sections) == 1


def test_dart_dispatched_unchanged():
    body = "# 제목\n## 1. 본문\ncontent\n"
    sections = parse_sections(body, "dart")
    # DART parser may emit one or more sections depending on TOC; smoke check.
    assert len(sections) >= 1


def test_unknown_source_generic_error():
    with pytest.raises(ValueError, match=r"^unsupported source for section parsing$"):
        parse_sections("x", "unknown_source")


def test_unknown_source_does_not_leak_input():
    # T-3-15 hardening: error message must NOT contain user-supplied source value.
    bad = "evil_source_<script>"
    with pytest.raises(ValueError) as exc:
        parse_sections("x", bad)
    assert bad not in str(exc.value)
