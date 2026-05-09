"""Phase 8 GAP-04 — macro source section parser.

ECOS/FRED 본문은 numeric series 표 + 짧은 메모 형태. DART처럼 TOC를 풀어내지
않고 단일 section으로 처리한다 (Phase 8 worker.process_private_note 패턴).
"""

from __future__ import annotations

from ingest.parsers import parse_sections


def test_macro_returns_single_section():
    body = "# Macro: 기준금리\n\n2026-04-26: 2.75%\n"
    sections = parse_sections(body, "macro")
    assert len(sections) == 1
    s = sections[0]
    assert s.title == "body"
    assert s.path == "body"
    assert s.order == 0
    assert s.text == body.strip()


def test_macro_empty_body_returns_empty_list():
    assert parse_sections("", "macro") == []
    assert parse_sections("   \n  ", "macro") == []
