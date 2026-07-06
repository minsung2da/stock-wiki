"""D-03 / SC#3 numeric-checksum tests (pure-function, no DB).

Analog: tests/test_number_extraction.py / test_number_sanity.py / test_units.py —
table-of-cases pure-fn style. The checksum drops any LLM-emitted numeric fact that is
NOT value-equivalent (after Korean-unit normalization) to some span in the source
body_md, recording each dropped fact in a warnings string (Veto #1/#4: "실패 = drop
the fact").
"""

from __future__ import annotations

from analysis.checksum import checksum_facts, fact_supported


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
