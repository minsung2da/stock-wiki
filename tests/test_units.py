"""Tests for shared.units.normalize_to_krw (D-09 value_krw computation)."""

from __future__ import annotations

import pytest

from shared.units import KRW_MULTIPLIERS, normalize_to_krw


@pytest.mark.parametrize(
    "value,unit,expected",
    [
        (1.0, "KRW원", 1.0),
        (1.0, "KRW백만", 1e6),
        (3.0, "KRW억", 3e8),
        (4.2, "KRW조", 4.2e12),
        (0.0, "KRW원", 0.0),
        (-5.0, "KRW억", -5e8),  # negatives preserved (e.g., 손실)
    ],
)
def test_krw_units_normalize(value, unit, expected):
    assert normalize_to_krw(value, unit) == expected


@pytest.mark.parametrize(
    "unit",
    ["USD", "EUR", "JPY", "pct", "bps", "multiplier", "shares", "days", "other"],
)
def test_non_krw_returns_none(unit):
    assert normalize_to_krw(100, unit) is None


def test_unknown_unit_returns_none():
    # Defensive: even if Pydantic Literal is bypassed, bogus str -> None (not KeyError).
    assert normalize_to_krw(100, "bogus_unit") is None
    assert normalize_to_krw(100, "") is None


def test_multipliers_frozen():
    """KRW_MULTIPLIERS is a MappingProxyType — mutation raises TypeError."""
    with pytest.raises(TypeError):
        KRW_MULTIPLIERS["KRW원"] = 2.0  # type: ignore[index]


def test_all_four_krw_units_present():
    assert set(KRW_MULTIPLIERS.keys()) == {"KRW원", "KRW백만", "KRW억", "KRW조"}
