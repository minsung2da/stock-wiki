"""Shared fixtures for tests/ingest/ — Phase 8 Plan 02 (D-04 hub_builder).

Provides `make_hub_inputs` factory used by hub_builder + price_snapshot tests.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from ingest.hub_builder import HubInputs


def _default_filings(n: int = 3) -> list[dict]:
    return [
        {
            "date": (date(2026, 5, 1) - timedelta(days=i)).isoformat(),
            "title": f"공시 제목 {i}",
            "vault_path": f"vault/raw/dart/2026-05-01/005930-2026000{i:04d}.md",
        }
        for i in range(n)
    ]


def _default_news(n: int = 3) -> list[dict]:
    return [
        {
            "date": (date(2026, 5, 1) - timedelta(days=i)).isoformat(),
            "title": f"뉴스 제목 {i}",
            "source": "hankyung",
            "vault_path": f"vault/raw/news/2026-05-01/hankyung-{i:04d}-005930.md",
        }
        for i in range(n)
    ]


def _default_prices_30d() -> list[tuple[date, int]]:
    base = date(2026, 4, 1)
    return [(base + timedelta(days=i), 70000 + (i * 100)) for i in range(30)]


@pytest.fixture
def make_hub_inputs():
    """Factory fixture: returns HubInputs with sensible defaults + overrides."""

    def _factory(**overrides: Any) -> HubInputs:
        defaults: dict[str, Any] = {
            "corp_code": "00126380",
            "ticker": "005930",
            "corp_name": "삼성전자",
            "sector": "반도체",
            "latest_price": 72000,
            "market_cap": 430_000_000_000_000,
            "as_of": date(2026, 5, 5),
            "recent_filings": _default_filings(),
            "recent_news": _default_news(),
            "price_30d": _default_prices_30d(),
        }
        defaults.update(overrides)
        return HubInputs(**defaults)

    return _factory
