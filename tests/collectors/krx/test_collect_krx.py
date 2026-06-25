"""collect_krx integration tests — Plan 01-04 + CAP-3 (bulk fetch).

Each test:
1. Materializes a temporary repo root via ``tmp_path`` with a
   ``notes/private/portfolio.md`` so ``Portfolio.load(Path("."))`` resolves.
2. Mocks the pykrx fetchers via ``monkeypatch``.
3. Invokes ``collect_krx`` and asserts both the returned stats dict AND
   the ``ohlcv`` table state via SQL.

CAP-3: OHLCV is now fetched whole-market once per run (``fetch_market_ohlcv``)
and filtered per ticker, instead of a per-ticker ``fetch_ohlcv`` scrape; entity
resolution is a single batch (``resolve_entities``). Investor-flow + short
balance stay per-ticker, so their isolation/fill-in tests are unchanged in
spirit.

Hard Veto #6 reminder: the ohlcv table is pure numeric; we never assert on
any body_md / embedding column because none exist on this table.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text

from collectors.krx import collect_krx
from collectors.krx import fetcher as krx_fetcher

pytestmark = pytest.mark.db

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "krx"


# ----- Fixture loaders -----


def _ohlcv() -> pd.DataFrame:
    return pd.read_json(FIXTURES / "ohlcv_005930.json")


def _flow() -> pd.DataFrame:
    return pd.read_json(FIXTURES / "trading_value_005930.json")


def _short() -> pd.DataFrame:
    return pd.read_json(FIXTURES / "shorting_balance_005930.json")


def _market_df(tickers) -> pd.DataFrame:
    """Whole-market OHLCV frame indexed by 6-digit ticker (CAP-3 bulk shape).

    Each ticker row reuses the single-name fixture's values, so close/volume
    assertions stay identical to the per-ticker era.
    """
    base = _ohlcv().iloc[0]  # Series: 시가/고가/저가/종가/거래량(/거래대금)
    cols = list(base.index)
    data = {c: [base[c] for _ in tickers] for c in cols}
    return pd.DataFrame(data, index=list(tickers))


def _empty_market() -> pd.DataFrame:
    """Non-trading-day whole-market frame (no rows → every ticker skipped)."""
    return pd.DataFrame()


# ----- Helpers -----


_SAMSUNG_PORTFOLIO = (
    "---\n"
    "holdings:\n"
    '  - ticker: "005930"\n'
    "    qty: 1\n"
    "    avg_cost: 70000\n"
    "watchlist: []\n"
    "---\n"
    "# Portfolio\n"
)


def _write_portfolio(tmp_path: Path, content: str = _SAMSUNG_PORTFOLIO) -> None:
    """Materialize tmp_path/notes/private/portfolio.md so Portfolio.load works."""
    p = tmp_path / "notes" / "private"
    p.mkdir(parents=True, exist_ok=True)
    (p / "portfolio.md").write_text(content, encoding="utf-8")


def _patch_market_success(monkeypatch, tickers) -> None:
    """Whole-market OHLCV contains ``tickers``; flow + short fixtures per ticker."""
    monkeypatch.setattr(krx_fetcher, "fetch_market_ohlcv", lambda d: _market_df(tickers))
    monkeypatch.setattr(krx_fetcher, "fetch_trading_value", lambda t, d: _flow())
    monkeypatch.setattr(krx_fetcher, "fetch_shorting_balance", lambda t, d: _short())


def _seed_hynix(engine) -> None:
    """Add SK하이닉스 (000660 / corp 00164779) so a second ticker resolves."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entities (corp_code, canonical_name, current_ticker, market) "
                "VALUES ('00164779', 'SK하이닉스', '000660', 'KOSPI')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO entity_aliases (corp_code, kind, value, valid_from, valid_to) "
                "VALUES ('00164779', 'ticker', '000660', :vf, NULL)"
            ),
            {"vf": date(2020, 1, 1)},
        )


def _count_ohlcv(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM ohlcv")).scalar_one()


def _ohlcv_row(engine, ticker: str, trade_date: date):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT ticker, trade_date, open, close, volume, "
                "trading_value, foreign_net, inst_net, retail_net, "
                "short_volume, short_balance, corp_code "
                "FROM ohlcv WHERE ticker=:t AND trade_date=:d"
            ),
            {"t": ticker, "d": trade_date},
        ).first()


# ----- Tests -----


def test_collect_krx_inserts_row(
    tmp_path: Path, seeded_engine, monkeypatch
) -> None:
    """One ticker in scope, fixture data → one ohlcv row inserted."""
    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_market_success(monkeypatch, ["005930"])

    stats = collect_krx(engine=seeded_engine, since="2026-04-17")

    assert stats["inserted"] == 1
    assert stats["updated"] == 0
    assert stats["skipped"] == 0
    assert stats["failed"] == []

    row = _ohlcv_row(seeded_engine, "005930", date(2026, 4, 17))
    assert row is not None
    assert row.close == pytest.approx(70500.0)
    assert row.corp_code == "00126380"


def test_collect_krx_missing_entity_isolation(
    tmp_path: Path, seeded_engine, monkeypatch
) -> None:
    """R-03: ticker missing from entities → stats.failed entry, no DB row."""
    _write_portfolio(
        tmp_path,
        "---\n"
        "holdings:\n"
        '  - ticker: "005930"\n'
        "    qty: 1\n"
        "    avg_cost: 70000\n"
        "watchlist:\n"
        '  - "999999"\n'
        "---\n"
        "# Portfolio\n",
    )
    monkeypatch.chdir(tmp_path)
    # Market frame carries BOTH tickers so 999999 reaches the entity check
    # (and fails it) instead of being skipped as a holiday.
    _patch_market_success(monkeypatch, ["005930", "999999"])

    stats = collect_krx(engine=seeded_engine, since="2026-04-17")

    assert stats["inserted"] == 1
    failed = {f["doc"]: f["error"] for f in stats["failed"]}
    assert failed.get("999999") == "missing_entity"

    assert _count_ohlcv(seeded_engine) == 1
    assert _ohlcv_row(seeded_engine, "005930", date(2026, 4, 17)) is not None
    assert _ohlcv_row(seeded_engine, "999999", date(2026, 4, 17)) is None


def test_collect_krx_holiday_skips(
    tmp_path: Path, seeded_engine, monkeypatch, caplog
) -> None:
    """Empty whole-market frame → no row, skipped++, no failed entry. Log
    surfaces extra.holiday_tickers."""
    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(krx_fetcher, "fetch_market_ohlcv", lambda d: _empty_market())
    monkeypatch.setattr(krx_fetcher, "fetch_trading_value", lambda t, d: _flow())
    monkeypatch.setattr(krx_fetcher, "fetch_shorting_balance", lambda t, d: _short())

    caplog.set_level(logging.INFO, logger="collectors.krx")
    stats = collect_krx(engine=seeded_engine, since="2026-04-17")

    assert stats["skipped"] == 1
    assert stats["inserted"] == 0
    assert stats["failed"] == []

    assert _count_ohlcv(seeded_engine) == 0

    complete = [r for r in caplog.records if r.message == "collector_run_complete"]
    assert complete, "expected a 'collector_run_complete' log record"
    extra = getattr(complete[-1], "extra", None) or {}
    assert "005930" in (extra.get("holiday_tickers") or [])


def test_collect_krx_idempotent_rerun(
    tmp_path: Path, seeded_engine, monkeypatch
) -> None:
    """Second call with identical data → skipped=1, no DB churn."""
    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_market_success(monkeypatch, ["005930"])

    stats1 = collect_krx(engine=seeded_engine, since="2026-04-17")
    assert stats1["inserted"] == 1

    stats2 = collect_krx(engine=seeded_engine, since="2026-04-17")
    assert stats2["inserted"] == 0
    assert stats2["updated"] == 0
    assert stats2["skipped"] == 1
    assert _count_ohlcv(seeded_engine) == 1


def test_collect_krx_short_t_plus_2_fill_in(
    tmp_path: Path, seeded_engine, monkeypatch
) -> None:
    """Run 1: short_row not yet available. Run 2: same date, short numbers
    arrive → 'updated'. DB row has short columns filled; OHLCV unchanged."""
    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(krx_fetcher, "fetch_market_ohlcv", lambda d: _market_df(["005930"]))
    monkeypatch.setattr(krx_fetcher, "fetch_trading_value", lambda t, d: _flow())
    # Run 1: empty short DataFrame (T-day)
    empty_short = pd.DataFrame(
        columns=["공매도잔고(주)", "상장주식수", "공매도금액", "시가총액", "비중"]
    )
    monkeypatch.setattr(krx_fetcher, "fetch_shorting_balance", lambda t, d: empty_short)

    stats1 = collect_krx(engine=seeded_engine, since="2026-04-17")
    assert stats1["inserted"] == 1

    row1 = _ohlcv_row(seeded_engine, "005930", date(2026, 4, 17))
    assert row1.short_volume is None
    assert row1.short_balance is None
    close1 = row1.close

    # Run 2 (T+2): short data arrives
    monkeypatch.setattr(krx_fetcher, "fetch_shorting_balance", lambda t, d: _short())

    stats2 = collect_krx(engine=seeded_engine, since="2026-04-17")
    assert stats2["updated"] == 1
    assert stats2["inserted"] == 0

    row2 = _ohlcv_row(seeded_engine, "005930", date(2026, 4, 17))
    assert row2.short_volume == 1234567
    assert row2.short_balance == 87000000000
    # OHLCV preserved through the fill-in
    assert row2.close == close1


def test_collect_krx_no_engine_raises(tmp_path: Path, monkeypatch) -> None:
    """engine=None must raise — collector contract requires DB for FK lookup."""
    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(RuntimeError, match="engine"):
        collect_krx(engine=None, since="2026-04-17")


def test_collect_krx_no_markdown_written(
    tmp_path: Path, seeded_engine, monkeypatch
) -> None:
    """After collect_krx, no vault/raw/krx/ dir is created under cwd."""
    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_market_success(monkeypatch, ["005930"])

    collect_krx(engine=seeded_engine, since="2026-04-17")

    assert not (tmp_path / "vault" / "raw" / "krx").exists()
    assert not (tmp_path / "vault").exists() or not any(
        (tmp_path / "vault").rglob("*.md")
    )


def test_collect_krx_per_ticker_isolation_on_fetch_exception(
    tmp_path: Path, seeded_engine, monkeypatch
) -> None:
    """COLL-08: a per-ticker flow-fetch exception doesn't abort other tickers."""
    _seed_hynix(seeded_engine)

    _write_portfolio(
        tmp_path,
        "---\n"
        "holdings:\n"
        '  - ticker: "005930"\n'
        "    qty: 1\n"
        "    avg_cost: 70000\n"
        "watchlist:\n"
        '  - "000660"\n'
        "---\n"
        "# Portfolio\n",
    )
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        krx_fetcher, "fetch_market_ohlcv", lambda d: _market_df(["005930", "000660"])
    )

    def _flow_selective(t: str, d: str):
        if t == "000660":
            raise RuntimeError("boom (simulated)")
        return _flow()

    monkeypatch.setattr(krx_fetcher, "fetch_trading_value", _flow_selective)
    monkeypatch.setattr(krx_fetcher, "fetch_shorting_balance", lambda t, d: _short())

    # Must NOT raise
    stats = collect_krx(engine=seeded_engine, since="2026-04-17")

    assert stats["inserted"] == 1
    failed_tickers = [f["doc"] for f in stats["failed"]]
    assert "000660" in failed_tickers


def test_collect_krx_single_market_fetch_regardless_of_scope_size(
    tmp_path: Path, seeded_engine, monkeypatch
) -> None:
    """CAP-3 acceptance: OHLCV is fetched whole-market ONCE per run (independent
    of scope size), and the per-ticker fetch_ohlcv scrape is never called."""
    _seed_hynix(seeded_engine)
    _write_portfolio(
        tmp_path,
        "---\n"
        "holdings:\n"
        '  - ticker: "005930"\n'
        "    qty: 1\n"
        "    avg_cost: 70000\n"
        "watchlist:\n"
        '  - "000660"\n'
        "---\n"
        "# Portfolio\n",
    )
    monkeypatch.chdir(tmp_path)

    calls = {"market": 0}

    def _counting_market(d):
        calls["market"] += 1
        return _market_df(["005930", "000660"])

    monkeypatch.setattr(krx_fetcher, "fetch_market_ohlcv", _counting_market)
    monkeypatch.setattr(krx_fetcher, "fetch_trading_value", lambda t, d: _flow())
    monkeypatch.setattr(krx_fetcher, "fetch_shorting_balance", lambda t, d: _short())
    monkeypatch.setattr(
        krx_fetcher,
        "fetch_ohlcv",
        lambda *a, **k: pytest.fail("per-ticker fetch_ohlcv must not be called (CAP-3)"),
    )

    stats = collect_krx(engine=seeded_engine, since="2026-04-17")

    assert stats["inserted"] == 2
    assert calls["market"] == 1


def test_resolve_entities_batch(seeded_engine) -> None:
    """resolve_entities resolves tickers + corp_codes in one call; unknowns absent."""
    from db.entity import resolve_entities

    out = resolve_entities(seeded_engine, ["005930", "999999", "00126380"])

    assert set(out.keys()) == {"005930", "00126380"}
    assert out["005930"].corp_code == "00126380"
    assert out["00126380"].current_ticker == "005930"
