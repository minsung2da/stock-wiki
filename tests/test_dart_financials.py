"""Tests for D-14 LLM-free DART structured financials.

Uses recorded cassettes — no live DART API call. Cassette shape mirrors
dart-fss fs.extract() DataFrame-like output reduced to list-of-dicts.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from collectors.dart.financials import (
    LINE_ITEM_SYNONYMS,
    get_structured_financials,
)
from shared.frontmatter import NumericFact

FIXTURES = Path(__file__).parent / "fixtures" / "dart_financial_responses"


def _load_cassette(name: str) -> dict[str, pd.DataFrame]:
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return {k: pd.DataFrame(v) for k, v in raw.items()}


def test_samsung_canonical_labels_extracted():
    cassette = _load_cassette("samsung_2025q4.json")
    with patch("collectors.dart.financials._fs_extract", return_value=cassette):
        facts = get_structured_financials(corp_code="00126380", bgn_de="20250101")
    by_key = {f.key: f for f in facts}
    assert "매출액" in by_key
    assert by_key["매출액"].value == 300000000000000
    assert by_key["매출액"].unit == "KRW원"
    assert by_key["매출액"].value_krw == 300000000000000
    assert by_key["매출액"].source_span is None  # D-14: structured path
    assert by_key["매출액"].offset is None
    assert "자산총계" in by_key
    assert "영업이익" in by_key


def test_service_firm_synonym_resolved():
    """수익(매출액) should map to canonical 매출액."""
    cassette = _load_cassette("service_firm_synonym.json")
    with patch("collectors.dart.financials._fs_extract", return_value=cassette):
        facts = get_structured_financials(corp_code="00000001", bgn_de="20250101")
    keys = {f.key for f in facts}
    assert "매출액" in keys  # canonical, not "수익(매출액)"
    assert "영업이익" in keys  # from "영업이익(손실)"


def test_all_facts_are_valid_pydantic():
    cassette = _load_cassette("samsung_2025q4.json")
    with patch("collectors.dart.financials._fs_extract", return_value=cassette):
        facts = get_structured_financials(corp_code="00126380", bgn_de="20250101")
    for f in facts:
        assert isinstance(f, NumericFact)
        assert f.unit == "KRW원"
        assert f.value_krw == f.value
        assert f.source_span is None


def test_synonyms_table_has_min_20_canonical_keys():
    assert len(LINE_ITEM_SYNONYMS) >= 20


def test_synonyms_preserve_canonical_in_own_set():
    """Every canonical key must be in its own synonym set."""
    for canonical, synonyms in LINE_ITEM_SYNONYMS.items():
        assert canonical in synonyms, f"{canonical} missing from synonym set"


def test_no_llm_imports():
    """COLL-07: financials.py must not import anthropic/openai."""
    src = Path("src/collectors/dart/financials.py").read_text(encoding="utf-8")
    assert "import anthropic" not in src
    assert "import openai" not in src
    assert "from anthropic" not in src
    assert "from openai" not in src


def test_unmapped_labels_ignored():
    """Labels not in any synonym set are silently skipped."""
    cassette = {
        "bs": pd.DataFrame([{"label_ko": "기타비유동자산", "value": 1000}]),
        "is": pd.DataFrame([{"label_ko": "판매비와관리비인식", "value": 2000}]),
    }
    with patch("collectors.dart.financials._fs_extract", return_value=cassette):
        facts = get_structured_financials(corp_code="00000002", bgn_de="20250101")
    assert facts == []  # nothing canonical
