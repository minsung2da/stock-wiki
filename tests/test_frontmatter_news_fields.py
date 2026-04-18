"""Tests for ProvenanceBlock additive fields (tickers/outlet/license_flag/observations).

Plans 03 (macro) and 04 (news) depend on these fields being optional additions
so existing Phase 3 DART/KRX/Macro/KIND writers keep validating.
"""

from __future__ import annotations

from datetime import date as date_type
from pathlib import Path

import pytest
from pydantic import ValidationError

from shared.frontmatter import (
    FrontMatter,
    Observation,
    ProvenanceBlock,
    TickerRef,
    read_frontmatter,
    write_frontmatter,
)


def test_legacy_provenance_without_new_fields(tmp_path: Path) -> None:
    prov = ProvenanceBlock(source="dart", corp_code="00126380", ticker="005930")
    fm = FrontMatter(provenance=prov)
    p = tmp_path / "legacy.md"
    write_frontmatter(str(p), fm, "body\n")
    back, body = read_frontmatter(str(p))
    assert back.provenance.source == "dart"
    assert back.provenance.tickers is None
    assert back.provenance.observations is None


def test_news_provenance_with_tickers_outlet_license(tmp_path: Path) -> None:
    prov = ProvenanceBlock(
        source="news",
        tickers=[{"corp_code": "00126380", "ticker": "005930", "name": "삼성전자"}],
        outlet="hankyung",
        license_flag="summary_only",
    )
    fm = FrontMatter(provenance=prov)
    p = tmp_path / "news.md"
    write_frontmatter(str(p), fm, "body\n")
    back, _ = read_frontmatter(str(p))
    assert back.provenance.outlet == "hankyung"
    assert back.provenance.license_flag == "summary_only"
    assert back.provenance.tickers is not None
    assert back.provenance.tickers[0].ticker == "005930"
    assert back.provenance.tickers[0].corp_code == "00126380"


def test_observations_roundtrip(tmp_path: Path) -> None:
    prov = ProvenanceBlock(
        source="ecos",
        observations=[{"date": "2026-04-15", "value": 4.28}],
    )
    fm = FrontMatter(provenance=prov)
    p = tmp_path / "obs.md"
    write_frontmatter(str(p), fm, "body\n")
    back, _ = read_frontmatter(str(p))
    assert back.provenance.observations is not None
    assert back.provenance.observations[0].value == 4.28
    assert back.provenance.observations[0].date == date_type(2026, 4, 15)


def test_invalid_license_flag_literal_raises() -> None:
    with pytest.raises(ValidationError):
        ProvenanceBlock(source="news", license_flag="arbitrary")  # type: ignore[arg-type]


def test_invalid_ticker_in_tickers_raises() -> None:
    with pytest.raises(ValidationError):
        ProvenanceBlock(source="news", tickers=[{"ticker": "5930"}])


def test_invalid_observation_date_raises() -> None:
    with pytest.raises(ValidationError):
        ProvenanceBlock(
            source="ecos",
            observations=[{"date": "not-a-date", "value": 1.0}],
        )


def test_ticker_ref_and_observation_models_direct() -> None:
    t = TickerRef(ticker="005930")
    assert t.ticker == "005930"
    assert t.corp_code is None
    o = Observation(date="2026-04-15", value=1.5)  # type: ignore[arg-type]
    assert o.value == 1.5
