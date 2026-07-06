"""D-03 / SC#3 numeric-checksum tests (pure-function, no DB).

Analog: tests/test_number_extraction.py / test_number_sanity.py / test_units.py —
table-of-cases pure-fn style. The checksum drops any LLM-emitted numeric fact that is
NOT value-equivalent (after Korean-unit normalization) to some span in the source
body_md, recording each dropped fact in a warnings string (Veto #1/#4: "실패 = drop
the fact").
"""

from __future__ import annotations

import pytest

from analysis.checksum import checksum_facts, fact_supported

# The three Korean-unit spellings of the SAME magnitude (4.25e13 KRW원). D-03's core
# guarantee: any claim form verifies against a body holding ANY one of these forms.
_JO_BODY = "매출액 42.5조원 달성."
_DIGIT_BODY = "매출액 42,500,000,000,000원 달성."
_EOK_BODY = "매출액 425000억원 달성."
_EQUIV_BODIES = [_JO_BODY, _DIGIT_BODY, _EOK_BODY]
_EQUIV_CLAIMS = [(42.5, "KRW조"), (42_500_000_000_000, "KRW원"), (425_000, "KRW억")]


class TestFactSupported:
    def test_krw_jo_claim_matches_plain_digit_span(self) -> None:
        # 42.5조원 (claim) ≡ 42,500,000,000,000원 (source) — both normalize to 4.25e13.
        body = "당기 매출액은 42,500,000,000,000원 입니다."
        assert fact_supported(42.5, "KRW조", body) is True

    def test_krw_eok_claim_matches_jo_span(self) -> None:
        # 425000억 (claim) ≡ 42.5조원 (source) — both normalize to 4.25e13.
        body = "매출액 42.5조원 달성."
        assert fact_supported(425000, "KRW억", body) is True

    def test_pct_claim_matches_pct_span(self) -> None:
        body = "영업이익률은 17.2%를 기록했습니다."
        assert fact_supported(17.2, "pct", body) is True

    def test_value_absent_from_body_is_not_supported(self) -> None:
        body = "매출액 42.5조원 달성."
        assert fact_supported(99.9, "KRW조", body) is False


class TestChecksumFacts:
    def test_keeps_supported_and_drops_unverifiable(self) -> None:
        body = "매출액 42.5조원, 영업이익률 17.2%."
        facts = [
            {"key": "revenue_krw", "value": 42.5, "unit": "KRW조", "source_ref": "dart:1"},
            {"key": "op_margin_pct", "value": 17.2, "unit": "pct", "source_ref": "dart:1"},
            {"key": "phantom_krw", "value": 88.8, "unit": "KRW조", "source_ref": "dart:1"},
        ]
        kept, warnings = checksum_facts(facts, body)
        assert kept == {"revenue_krw": 42.5, "op_margin_pct": 17.2}
        assert len(warnings) == 1
        assert "phantom_krw" in warnings[0]

    def test_kept_preserves_int_vs_float_and_names_dropped_key(self) -> None:
        body = "매출액 42.5조원."
        facts = [
            {"key": "market_cap", "value": 42_500_000_000_000, "unit": "KRW원"},  # int
            {"key": "bogus_ratio", "value": 250.0, "unit": "pct"},  # not in body → drop
        ]
        kept, warnings = checksum_facts(facts, body)
        # Stored shape dict[str, float|int]; the int value must NOT drift to float.
        assert kept == {"market_cap": 42_500_000_000_000}
        assert isinstance(kept["market_cap"], int)
        # Exactly one warning, naming the dropped key + its value/unit.
        assert warnings == ["bogus_ratio=250.0pct: not verifiable in source"]


class TestThreeWayEquivalence:
    """42.5조원 ≡ 42,500,000,000,000 ≡ 425000억 — every claim form verifies against a
    body holding any one form (D-03 value-equivalence, the 3×3 matrix)."""

    @pytest.mark.parametrize("body", _EQUIV_BODIES)
    @pytest.mark.parametrize(("value", "unit"), _EQUIV_CLAIMS)
    def test_all_forms_cross_verify(self, value: float, unit: str, body: str) -> None:
        assert fact_supported(value, unit, body) is True


class TestUnitFamilies:
    def test_multiplier_claim_matches_multiplier_span(self) -> None:
        body = "PER은 3.5배 수준입니다."
        assert fact_supported(3.5, "multiplier", body) is True

    def test_clear_non_match_is_dropped(self) -> None:
        body = "PER은 3.5배 수준입니다."
        kept, warnings = checksum_facts(
            [{"key": "per", "value": 99.0, "unit": "multiplier"}], body
        )
        assert kept == {}
        assert warnings == ["per=99.0multiplier: not verifiable in source"]


class TestToleranceBoundary:
    def test_just_inside_tolerance_supported(self) -> None:
        # rel diff 0.4/100.4 ≈ 0.00398 ≤ 0.005 → supported.
        assert fact_supported(100.0, "pct", "지표 100.4%") is True

    def test_just_outside_tolerance_dropped(self) -> None:
        # rel diff 0.6/100.6 ≈ 0.00596 > 0.005 → not supported.
        assert fact_supported(100.0, "pct", "지표 100.6%") is False


class TestAgainstRealFilingBody:
    """At least one case run against a realistic body (real_filing_body fixture)."""

    def test_jo_and_pct_facts_verify(self, real_filing_body: str) -> None:
        assert fact_supported(42.5, "KRW조", real_filing_body) is True
        assert fact_supported(17.2, "pct", real_filing_body) is True

    def test_checksum_drops_phantom_keeps_real(self, real_filing_body: str) -> None:
        facts = [
            {"key": "revenue_krw", "value": 42.5, "unit": "KRW조"},
            {"key": "op_margin_pct", "value": 17.2, "unit": "pct"},
            {"key": "phantom_pct", "value": 91.3, "unit": "pct"},
        ]
        kept, warnings = checksum_facts(facts, real_filing_body)
        assert kept == {"revenue_krw": 42.5, "op_margin_pct": 17.2}
        assert len(warnings) == 1
        assert "phantom_pct" in warnings[0]
