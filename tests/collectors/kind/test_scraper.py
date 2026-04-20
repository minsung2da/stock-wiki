"""Unit tests for collectors.kind.scraper.parse_undisclosure_fragment."""

from __future__ import annotations

from pathlib import Path

import pytest

from collectors.kind.scraper import parse_undisclosure_fragment
from collectors.kind.selectors import ParseError

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures/kind"


def _load_eckr(name: str) -> str:
    return (FIXTURES / name).read_bytes().decode("euc-kr", errors="replace")


def test_parse_undisclosure_real_fixture():
    html = _load_eckr("undisclosure_ajax_page1.html")
    rows = parse_undisclosure_fragment(html)
    # Fixture has 15 data rows (page size).
    assert len(rows) >= 5, f"expected real rows, got {len(rows)}"
    first = rows[0]
    assert first["company_name"]
    assert first["event_date"]
    assert len(first["event_date"]) == 8
    assert first["event_date"].isdigit()


def test_parse_undisclosure_missing_table_raises():
    with pytest.raises(ParseError):
        parse_undisclosure_fragment("<html><body><p>no table here</p></body></html>")


def test_parse_undisclosure_empty_tbody_returns_empty_list():
    html = '<section><table class="list"><tbody></tbody></table></section>'
    assert parse_undisclosure_fragment(html) == []


def test_parse_undisclosure_malformed_row_raises():
    # A row with only one cell — less than required column count → ParseError.
    html = (
        '<section><table class="list"><tbody>'
        "<tr><td>only-one-cell</td></tr>"
        "</tbody></table></section>"
    )
    with pytest.raises(ParseError):
        parse_undisclosure_fragment(html)
