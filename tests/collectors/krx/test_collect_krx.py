"""collect_krx integration tests — Plan 02 Task 2 behavior contract (COLL-02, R-03)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml
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


def _empty_ohlcv() -> pd.DataFrame:
    return pd.DataFrame(columns=["시가", "고가", "저가", "종가", "거래량"])


# ----- Helpers -----


def _seed_two_entities(engine) -> None:
    """Add SK하이닉스 (000660) to the seeded_engine which already has 005930."""
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


def _patch_fetchers_success(monkeypatch) -> None:
    """Both tickers return fixture DataFrames on every fetch."""
    monkeypatch.setattr(krx_fetcher, "fetch_ohlcv", lambda t, d: _ohlcv())
    monkeypatch.setattr(krx_fetcher, "fetch_trading_value", lambda t, d: _flow())
    monkeypatch.setattr(krx_fetcher, "fetch_shorting_balance", lambda t, d: _short())


def _read_heartbeat_krx(vault_root: Path) -> dict:
    """Read the `sources.krx` block from the vault heartbeat."""
    text_ = (vault_root / "ingested/_status/heartbeat.md").read_text(encoding="utf-8")
    end = text_.find("\n---", 3)
    meta = yaml.safe_load(text_[3:end]) or {}
    return meta.get("sources", {}).get("krx", {})


# ----- Tests -----


def test_collect_krx_writes_files_for_two_tickers(
    vault_tmp: Path, seeded_engine, monkeypatch
) -> None:
    _seed_two_entities(seeded_engine)
    _patch_fetchers_success(monkeypatch)

    stats = collect_krx(vault_root=vault_tmp, engine=seeded_engine, since="2026-04-17")

    assert stats["succeeded"] == 2
    assert stats["failed"] == []
    assert (vault_tmp / "raw/krx/2026-04-17/005930.md").exists()
    assert (vault_tmp / "raw/krx/2026-04-17/000660.md").exists()


def test_collect_krx_idempotent_rerun_all_skipped(
    vault_tmp: Path, seeded_engine, monkeypatch
) -> None:
    _seed_two_entities(seeded_engine)
    _patch_fetchers_success(monkeypatch)

    collect_krx(vault_root=vault_tmp, engine=seeded_engine, since="2026-04-17")
    mtime1 = (vault_tmp / "raw/krx/2026-04-17/005930.md").stat().st_mtime_ns

    stats2 = collect_krx(vault_root=vault_tmp, engine=seeded_engine, since="2026-04-17")
    mtime2 = (vault_tmp / "raw/krx/2026-04-17/005930.md").stat().st_mtime_ns

    assert stats2["skipped"] == 2
    assert stats2["succeeded"] == 0
    assert mtime1 == mtime2  # atomic write never replaced the file


def test_collect_krx_holiday_skip_records_heartbeat_extra(
    vault_tmp: Path, seeded_engine, monkeypatch
) -> None:
    _seed_two_entities(seeded_engine)
    # 005930 returns real data; 000660 returns empty (holiday-like)
    monkeypatch.setattr(
        krx_fetcher, "fetch_ohlcv", lambda t, d: _ohlcv() if t == "005930" else _empty_ohlcv()
    )
    monkeypatch.setattr(krx_fetcher, "fetch_trading_value", lambda t, d: _flow())
    monkeypatch.setattr(krx_fetcher, "fetch_shorting_balance", lambda t, d: _short())

    stats = collect_krx(vault_root=vault_tmp, engine=seeded_engine, since="2026-04-17")

    assert stats["succeeded"] == 1
    assert stats["skipped"] == 1
    assert not (vault_tmp / "raw/krx/2026-04-17/000660.md").exists()

    block = _read_heartbeat_krx(vault_tmp)
    assert block.get("skipped_holiday") is True
    assert "000660" in block.get("holiday_tickers", [])


def test_collect_krx_per_ticker_isolation_on_fetch_exception(
    vault_tmp: Path, seeded_engine, monkeypatch
) -> None:
    _seed_two_entities(seeded_engine)

    def _ohlcv_selective(t: str, d: str) -> pd.DataFrame:
        if t == "000660":
            raise RuntimeError("boom (simulated)")
        return _ohlcv()

    monkeypatch.setattr(krx_fetcher, "fetch_ohlcv", _ohlcv_selective)
    monkeypatch.setattr(krx_fetcher, "fetch_trading_value", lambda t, d: _flow())
    monkeypatch.setattr(krx_fetcher, "fetch_shorting_balance", lambda t, d: _short())

    # collector MUST NOT raise
    stats = collect_krx(vault_root=vault_tmp, engine=seeded_engine, since="2026-04-17")

    assert stats["succeeded"] == 1
    failed_tickers = [f["doc"] for f in stats["failed"]]
    assert "000660" in failed_tickers


def test_collect_krx_heartbeat_has_last_success(
    vault_tmp: Path, seeded_engine, monkeypatch
) -> None:
    _seed_two_entities(seeded_engine)
    _patch_fetchers_success(monkeypatch)

    collect_krx(vault_root=vault_tmp, engine=seeded_engine, since="2026-04-17")

    block = _read_heartbeat_krx(vault_tmp)
    assert "last_success" in block
    assert block["docs_processed"] == 2


def test_collect_krx_missing_entity_option_a(vault_tmp: Path, seeded_engine, monkeypatch) -> None:
    """R-03: unknown ticker → no file, stats['failed'] + heartbeat.extra.missing_entity."""
    # Rewrite portfolio to scope [005930, 999999] — 999999 has NO entities row.
    # Phase 6 P-01: portfolio lives at <repo_root>/notes/private/portfolio.md
    # where repo_root = vault_tmp.parent.
    (vault_tmp.parent / "notes" / "private" / "portfolio.md").write_text(
        "---\n"
        "holdings:\n"
        '  - ticker: "005930"\n'
        "    qty: 1\n"
        "    avg_cost: 70000\n"
        "watchlist:\n"
        '  - "999999"\n'
        "---\n"
        "# Portfolio\n",
        encoding="utf-8",
    )
    _patch_fetchers_success(monkeypatch)

    stats = collect_krx(vault_root=vault_tmp, engine=seeded_engine, since="2026-04-17")

    # 005930 should be written
    assert (vault_tmp / "raw/krx/2026-04-17/005930.md").exists()
    # 999999 should NOT be written
    assert not (vault_tmp / "raw/krx/2026-04-17/999999.md").exists()
    # stats['failed'] contains 999999 with missing_entity reason
    failed = {f["doc"]: f["error"] for f in stats["failed"]}
    assert failed.get("999999") == "missing_entity"
    # heartbeat extra.missing_entity lists it
    block = _read_heartbeat_krx(vault_tmp)
    assert "999999" in block.get("missing_entity", [])
