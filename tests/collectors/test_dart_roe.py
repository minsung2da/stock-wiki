"""Official ROE units, source validation and non-destructive enrichment."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import requests
from sqlalchemy import text

from collectors.fundamentals import dart_roe
from collectors.fundamentals.db_writer import upsert_roe


@pytest.fixture
def payload(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "secret-test-key")
    row = {
        "corp_code": "00126380",
        "bsns_year": "2025",
        "reprt_code": "11011",
        "idx_cl_code": "M210000",
        "idx_code": "M211550",
        "idx_nm": "ROE",
        "idx_val": "10.783",
        "stlm_dt": "2025-12-31",
    }
    data = {"status": "000", "list": [row]}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return data

    monkeypatch.setattr(dart_roe.requests, "get", lambda *args, **kwargs: Response())
    return data


@pytest.mark.parametrize("raw,expected", [("10.783", "0.10783"), ("0", "0"), ("-12.5", "-0.125")])
def test_official_percent_to_fraction(payload, raw, expected):
    payload["list"][0]["idx_val"] = raw
    result = dart_roe.fetch_annual_roe("00126380", 2025)
    assert result.value == Decimal(expected)
    assert result.period_end == date(2025, 12, 31)
    assert result.fetched_at.tzinfo is not None
    assert "secret-test-key" not in result.source
    assert "bsns_year=2025" in result.source


@pytest.mark.parametrize("raw", [None, "", "-"])
def test_unavailable_is_not_zero(payload, raw):
    payload["list"][0]["idx_val"] = raw
    assert dart_roe.fetch_annual_roe("00126380", 2025) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("corp_code", "99999999"),
        ("bsns_year", "2024"),
        ("reprt_code", "11012"),
        ("idx_val", "NaN"),
        ("idx_val", "Infinity"),
        ("stlm_dt", "2026-12-31"),
    ],
)
def test_reject_bad_scope_and_values(payload, field, value):
    payload["list"][0][field] = value
    with pytest.raises(ValueError):
        dart_roe.fetch_annual_roe("00126380", 2025)


def test_status_and_transport_errors_are_sanitized(payload, monkeypatch):
    payload["status"] = "013"
    assert dart_roe.fetch_annual_roe("00126380", 2025) is None
    payload["status"] = "020"
    with pytest.raises(RuntimeError, match="dart_roe_status_020"):
        dart_roe.fetch_annual_roe("00126380", 2025)

    def fail(*args, **kwargs):
        raise requests.RequestException("URL contains secret-test-key")

    monkeypatch.setattr(dart_roe.requests, "get", fail)
    with pytest.raises(RuntimeError) as error:
        dart_roe.fetch_annual_roe("00126380", 2025)
    assert "secret-test-key" not in str(error.value)


def test_roe_enrichment_preserves_other_metrics_and_source(pg_clean):
    with pg_clean.begin() as conn:
        conn.execute(text("DELETE FROM fundamentals"))
        conn.execute(
            text(
                "INSERT INTO fundamentals (ticker,fdate,per,pbr,eps,bps,dividend_yield,dps,source) "
                "VALUES ('005930','2026-09-23',10,2,300,1500,1.5,100,'original')"
            )
        )
        before = dict(
            conn.execute(text("SELECT * FROM fundamentals WHERE ticker='005930'")).mappings().one()
        )
    observation = dart_roe.RoeObservation(
        Decimal("0.10783"), date(2025, 12, 31), "official-test", datetime.now(UTC)
    )
    assert (
        upsert_roe(
            pg_clean,
            ticker="005930",
            fdate=date(2026, 9, 23),
            corp_code=None,
            observation=observation,
        )
        == "updated"
    )
    with pg_clean.connect() as conn:
        after = dict(
            conn.execute(text("SELECT * FROM fundamentals WHERE ticker='005930'")).mappings().one()
        )
    for key in before.keys() - {
        "roe",
        "roe_period_end",
        "roe_source",
        "roe_fetched_at",
        "roe_report_code",
    }:
        assert after[key] == before[key], key
    assert after["roe"] == Decimal("0.107830")
    assert after["roe_period_end"] == observation.period_end
    assert after["roe_report_code"] == "11011"
    assert (
        upsert_roe(
            pg_clean,
            ticker="005930",
            fdate=date(2026, 9, 23),
            corp_code=None,
            observation=observation,
        )
        == "skipped"
    )
    assert (
        upsert_roe(
            pg_clean,
            ticker="005930",
            fdate=date(2026, 9, 24),
            corp_code=None,
            observation=observation,
        )
        == "inserted"
    )


def _latest_api(monkeypatch, responses):
    monkeypatch.setenv("DART_API_KEY", "secret-test-key")
    calls = []
    periods = {"11013": "03-31", "11012": "06-30", "11014": "09-30", "11011": "12-31"}

    def get(url, *, params, timeout):
        key = (int(params["bsns_year"]), params["reprt_code"])
        calls.append(key)
        result = responses.get(key)
        if isinstance(result, Exception):
            raise result
        data = (
            {"status": "013"}
            if result is None
            else {
                "status": "000",
                "list": [
                    {
                        "corp_code": params["corp_code"],
                        "bsns_year": params["bsns_year"],
                        "reprt_code": key[1],
                        "idx_cl_code": "M210000",
                        "idx_code": "M211550",
                        "idx_nm": "ROE",
                        "idx_val": result,
                        "stlm_dt": f"{key[0]}-{periods[key[1]]}",
                    }
                ],
            }
        )

        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return data

        return Response()

    monkeypatch.setattr(dart_roe.requests, "get", get)
    return calls


def test_latest_selects_current_half_year(monkeypatch):
    calls = _latest_api(monkeypatch, {(2026, "11012"): "7.5", (2025, "11011"): "10"})
    result = dart_roe.fetch_latest_roe("00126380", date(2026, 9, 24))
    assert calls == [(2026, "11012")]
    assert result.value == Decimal("0.075")
    assert result.period_end == date(2026, 6, 30)
    assert result.report_code == "11012"
    assert "reprt_code=11012" in result.source


@pytest.mark.parametrize("period", [(2026, "11013"), (2025, "11011")])
def test_latest_falls_back_only_when_unavailable(monkeypatch, period):
    calls = _latest_api(monkeypatch, {period: "8"})
    result = dart_roe.fetch_latest_roe("00126380", date(2026, 9, 24))
    expected = [(2026, "11012"), (2026, "11013")]
    if period[0] == 2025:
        expected.append(period)
    assert calls == expected
    assert result.report_code == period[1]
    assert result.period_end.year == period[0]


def test_latest_does_not_fallback_on_provider_error(monkeypatch):
    calls = _latest_api(monkeypatch, {(2026, "11012"): requests.RequestException("secret")})
    with pytest.raises(RuntimeError, match="dart_roe_request_failed"):
        dart_roe.fetch_latest_roe("00126380", date(2026, 9, 24))
    assert calls == [(2026, "11012")]


@pytest.mark.parametrize(
    "as_of,expected",
    [
        (date(2026, 3, 30), (2025, "11011")),
        (date(2026, 3, 31), (2026, "11013")),
        (date(2026, 6, 30), (2026, "11012")),
        (date(2026, 9, 30), (2026, "11014")),
        (date(2026, 12, 31), (2026, "11011")),
    ],
)
def test_latest_closed_period_boundaries(monkeypatch, as_of, expected):
    calls = _latest_api(monkeypatch, {expected: "1"})
    result = dart_roe.fetch_latest_roe("00126380", as_of)
    assert calls == [expected]
    assert result.period_end <= as_of


def test_latest_rejects_mismatched_settlement_period(payload):
    row = payload["list"][0]
    row.update(bsns_year="2026", reprt_code="11012", stlm_dt="2026-12-31")
    with pytest.raises(ValueError, match="dart_roe_invalid_value"):
        dart_roe.fetch_latest_roe("00126380", date(2026, 9, 24))


def test_latest_exhausts_only_current_and_previous_year(monkeypatch):
    calls = _latest_api(monkeypatch, {})
    assert dart_roe.fetch_latest_roe("00126380", date(2026, 9, 24)) is None
    assert calls == [
        (2026, "11012"),
        (2026, "11013"),
        (2025, "11011"),
        (2025, "11014"),
        (2025, "11012"),
        (2025, "11013"),
    ]
