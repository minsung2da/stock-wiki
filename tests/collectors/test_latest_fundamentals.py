"""Independent current-market and latest-ROE orchestration, without live providers."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest

import collectors.fundamentals as collector
from collectors.fundamentals.market_snapshot import MarketSnapshot


@pytest.fixture
def harness(monkeypatch):
    values = {
        "per": Decimal("12.5"),
        "pbr": Decimal("1.4"),
        "eps": Decimal("5600"),
        "bps": Decimal("50000"),
        "dividend_yield": Decimal("2.1"),
        "dps": Decimal("1416"),
    }
    periods = {key: "2025.12" if key in {"dividend_yield", "dps"} else "2026.06" for key in values}
    snapshot = MarketSnapshot(
        values=values,
        market_asof=date(2026, 9, 23),
        metric_periods=periods,
        source="naver:totalInfos",
        fetched_at=datetime(2026, 9, 24, tzinfo=UTC),
    )
    observation = SimpleNamespace(
        value=Decimal("0.1"),
        period_end=date(2026, 6, 30),
        source="dart:11012",
        report_code="11012",
        fetched_at=datetime(2026, 9, 24, tzinfo=UTC),
    )
    calls = {
        key: []
        for key in ("current", "krx", "latest_roe", "market_write", "krx_write", "roe_write", "run")
    }

    def current(ticker):
        calls["current"].append(ticker)
        return snapshot

    def historical(ticker, day):
        calls["krx"].append((ticker, day))
        return pd.DataFrame(
            [{"PER": 12.5, "PBR": 1.4, "EPS": 5600, "BPS": 50000, "DIV": 2.1, "DPS": 1416}]
        )

    def latest(corp_code, as_of):
        calls["latest_roe"].append((corp_code, as_of))
        return observation

    def writer(kind, outcome):
        def write(engine, **kwargs):
            calls[kind].append(kwargs)
            return outcome

        return write

    monkeypatch.setattr(collector, "_today_iso_krx", lambda: "2026-09-24")
    monkeypatch.setattr(
        collector.Portfolio, "load", lambda _: SimpleNamespace(scope_tickers=lambda: ["005930"])
    )
    monkeypatch.setattr(
        collector, "resolve_entity", lambda *_: SimpleNamespace(corp_code="00126380")
    )
    monkeypatch.setattr(
        collector,
        "record_collector_run",
        lambda *args, **kwargs: calls["run"].append((args, kwargs)),
    )
    monkeypatch.setattr(
        collector, "market_snapshot", SimpleNamespace(fetch_market_snapshot=current), raising=False
    )
    monkeypatch.setattr(collector.fetcher, "fetch_market_fundamental", historical)
    monkeypatch.setattr(collector.dart_roe, "fetch_latest_roe", latest, raising=False)
    monkeypatch.setattr(collector.dart_roe, "fetch_annual_roe", lambda *_: None)
    monkeypatch.setattr(
        collector.db_writer,
        "upsert_market_snapshot",
        writer("market_write", "inserted"),
        raising=False,
    )
    monkeypatch.setattr(collector.db_writer, "upsert_fundamentals", writer("krx_write", "inserted"))
    monkeypatch.setattr(collector.db_writer, "upsert_roe", writer("roe_write", "updated"))
    return SimpleNamespace(calls=calls, snapshot=snapshot, observation=observation, engine=object())


@pytest.mark.parametrize("since", [None, "2026-09-24"])
def test_today_preserves_all_six_metrics_and_distinct_periods(harness, since):
    result = collector.collect_fundamentals(engine=harness.engine, since=since)
    calls = harness.calls
    assert calls["current"] == ["005930"] and calls["krx"] == []
    assert calls["market_write"][0] == {
        "ticker": "005930",
        "fdate": date(2026, 9, 24),
        "corp_code": "00126380",
        "snapshot": harness.snapshot,
    }
    assert len(harness.snapshot.values) == 6
    assert harness.snapshot.metric_periods["per"] == "2026.06"
    assert harness.snapshot.metric_periods["dividend_yield"] == "2025.12"
    assert harness.snapshot.market_asof == date(2026, 9, 23)
    assert calls["latest_roe"] == [("00126380", date(2026, 9, 24))]
    assert calls["roe_write"][0]["observation"].report_code == "11012"
    assert result["total"] == result["inserted"] == 1
    assert result["updated"] == 0 and result["failed"] == []
    assert result["roe"]["available"] == 1 and len(calls["run"]) == 1


def test_historical_date_never_uses_current_snapshot(harness):
    harness.observation.period_end = date(2025, 12, 31)
    harness.observation.report_code = "11011"
    harness.observation.source = "dart:11011"
    result = collector.collect_fundamentals(engine=harness.engine, since="2026-04-17")
    assert harness.calls["current"] == harness.calls["market_write"] == []
    assert harness.calls["krx"] == [("005930", "20260417")]
    assert harness.calls["krx_write"][0]["fdate"] == date(2026, 4, 17)
    assert harness.calls["latest_roe"] == [("00126380", date(2026, 4, 17))]
    assert result["inserted"] == 1 and result["failed"] == []


def test_current_provider_failure_still_writes_roe(harness, monkeypatch, caplog):
    def unavailable(_ticker):
        raise RuntimeError("provider?key=SECRET")

    monkeypatch.setattr(collector.market_snapshot, "fetch_market_snapshot", unavailable)
    result = collector.collect_fundamentals(engine=harness.engine)
    assert harness.calls["market_write"] == harness.calls["krx_write"] == []
    assert len(harness.calls["roe_write"]) == 1
    assert result["updated"] == 1 and result["roe"]["available"] == 1
    assert len(result["failed"]) == 1
    assert "SECRET" not in str(result) + caplog.text


def test_latest_roe_failure_keeps_current_market_write(harness, monkeypatch, caplog):
    def unavailable(*_args):
        raise RuntimeError("provider?key=SECRET")

    monkeypatch.setattr(collector.dart_roe, "fetch_latest_roe", unavailable)
    result = collector.collect_fundamentals(engine=harness.engine)
    assert len(harness.calls["market_write"]) == 1 and harness.calls["roe_write"] == []
    assert result["inserted"] == 1 and result["roe"]["failed"] == 1
    assert "SECRET" not in str(result) + caplog.text
