"""Lossless mapping of the provider's six typed valuation fields."""
import pandas as pd
import pytest

from collectors.fundamentals import _coerce_fundamental_row


@pytest.mark.parametrize("value, expected", [(2.1, 2.1), (0, 0), (float("nan"), None), (None, None)])
def test_dividend_fields_are_preserved(value, expected):
    row = _coerce_fundamental_row(pd.DataFrame([{"DIV": value, "DPS": value}]))
    assert row["dividend_yield"] == expected
    assert row["dps"] == expected


def test_missing_dividends_are_null():
    row = _coerce_fundamental_row(pd.DataFrame([{"PER": 12.5}]))
    assert row["dividend_yield"] is None
    assert row["dps"] is None
