"""Latest published metric values, periods, observation dates and preservation."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from collectors.fundamentals import market_snapshot
from collectors.fundamentals.db_writer import upsert_market_snapshot


@pytest.fixture
def snapshot_payload(monkeypatch):
    basic = {"itemCode": "005930", "localTradedAt": "2026-09-23T15:30:00+09:00"}
    payload = {
        "itemCode": "005930",
        "totalInfos": [
            {"code": "per", "value": "12.85배", "valueDesc": "2026.06."},
            {"code": "pbr", "value": "3.33배", "valueDesc": "2026.06."},
            {"code": "eps", "value": "-22,292원", "valueDesc": "2026.06."},
            {"code": "bps", "value": "86,052원", "valueDesc": "2026.06."},
            {"code": "dividendYieldRatio", "value": "0.58%", "valueDesc": "2025.12."},
            {"code": "dividend", "value": "0원", "valueDesc": "2025.12."},
        ],
    }

    class Response:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self.data

    monkeypatch.setattr(
        market_snapshot.requests,
        "get",
        lambda url, **kwargs: Response(basic if url.endswith("/basic") else payload),
    )
    return basic, payload


def test_values_units_periods_and_real_market_date(snapshot_payload):
    result = market_snapshot.fetch_market_snapshot("005930")
    assert result.values == {
        "per": Decimal("12.85"),
        "pbr": Decimal("3.33"),
        "eps": Decimal("-22292"),
        "bps": Decimal("86052"),
        "dividend_yield": Decimal("0.58"),
        "dps": Decimal("0"),
    }
    assert result.market_asof == date(2026, 9, 23)
    assert result.metric_periods["eps"] == "2026.06."
    assert result.metric_periods["dps"] == "2025.12."


@pytest.mark.parametrize("raw", ["-", "N/A", "NaN", "Infinity"])
def test_missing_not_zero(snapshot_payload, raw):
    snapshot_payload[1]["totalInfos"][0]["value"] = raw
    assert market_snapshot.fetch_market_snapshot("005930").values["per"] is None


@pytest.mark.parametrize("change", ["ticker", "future", "duplicate"])
def test_invalid_source_scope(snapshot_payload, change):
    basic, payload = snapshot_payload
    if change == "ticker":
        payload["itemCode"] = "000660"
    elif change == "future":
        basic["localTradedAt"] = "2099-01-01T12:00:00+09:00"
    else:
        payload["totalInfos"].append(payload["totalInfos"][0])
    with pytest.raises(ValueError):
        market_snapshot.fetch_market_snapshot("005930")


def test_snapshot_writer_dates_periods_and_roe_preservation(pg_clean):
    with pg_clean.begin() as conn:
        conn.execute(text("DELETE FROM fundamentals"))
        conn.execute(
            text(
                "INSERT INTO fundamentals(ticker,fdate,per,roe,roe_source,source) "
                "VALUES ('005930','2026-09-23',10,0.1,'old-roe','old'),"
                "('005930','2026-09-24',NULL,0.2,'new-roe','roe-only')"
            )
        )
    snapshot = market_snapshot.MarketSnapshot(
        {
            "per": Decimal("12.85"),
            "pbr": Decimal("3.33"),
            "eps": Decimal("22292"),
            "bps": Decimal("86052"),
            "dividend_yield": None,
            "dps": None,
        },
        date(2026, 9, 23),
        {"per": "2026.06."},
        "current-provider",
        datetime(2026, 9, 24, 0, 0, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="backdated"):
        upsert_market_snapshot(
            pg_clean, ticker="005930", fdate=date(2026, 9, 23), corp_code=None, snapshot=snapshot
        )
    assert (
        upsert_market_snapshot(
            pg_clean, ticker="005930", fdate=date(2026, 9, 24), corp_code=None, snapshot=snapshot
        )
        == "updated"
    )
    assert (
        upsert_market_snapshot(
            pg_clean, ticker="005930", fdate=date(2026, 9, 24), corp_code=None, snapshot=snapshot
        )
        == "skipped"
    )
    with pg_clean.connect() as conn:
        rows = conn.execute(text("SELECT * FROM fundamentals ORDER BY fdate")).mappings().all()
    assert rows[0]["per"] == Decimal("10")
    assert rows[0]["roe_source"] == "old-roe"
    assert rows[1]["roe"] == Decimal("0.2")
    assert rows[1]["roe_source"] == "new-roe"
    assert rows[1]["market_asof"] == date(2026, 9, 23)
    assert rows[1]["metric_periods"] == {"per": "2026.06."}
