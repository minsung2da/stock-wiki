"""Plan 01-08 Task 2 — observability wiring across all 5 collectors.

Each collector MUST call ``shared.run_log.record_collector_run`` exactly
once per ``collect_*`` invocation, in addition to the existing structured
``collector_run_complete`` log line.

These integration tests assert the DB-row sink (the log sink is already
covered by per-collector tests under tests/collectors/<src>/). We don't
care about the per-source extras shape here — Task 1's unit tests already
verify the helper's JSONB round-trip; here we verify only that ONE row
lands in ``collector_runs`` for each source after a successful collect.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.db


_PORTFOLIO_005930 = (
    "---\n"
    "holdings:\n"
    '  - ticker: "005930"\n'
    "    qty: 1\n"
    "    avg_cost: 70000\n"
    "watchlist: []\n"
    "---\n"
    "# Portfolio\n"
)


def _write_portfolio(tmp_path: Path, content: str = _PORTFOLIO_005930) -> None:
    p = tmp_path / "notes" / "private"
    p.mkdir(parents=True, exist_ok=True)
    (p / "portfolio.md").write_text(content, encoding="utf-8")


def _count_runs(engine, source: str) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM collector_runs WHERE source = :s"),
                {"s": source},
            ).scalar()
        )


def _select_run(engine, source: str) -> dict[str, Any]:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT source, elapsed_ms, stats, extra "
                "FROM collector_runs WHERE source = :s "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"s": source},
        ).one()
    return {
        "source": row.source,
        "elapsed_ms": row.elapsed_ms,
        "stats": row.stats,
        "extra": row.extra,
    }


# ------------- macro ----------------------------------------------------------


def test_collect_macro_writes_collector_runs_row(pg_clean, monkeypatch):
    """After a successful collect_macro, exactly one collector_runs row exists."""
    from collectors.macro import client as macro_client
    from collectors.macro import collect_macro
    from collectors.macro import fetcher as macro_fetcher

    monkeypatch.setenv("ECOS_API_KEY", "x")
    monkeypatch.setenv("FRED_API_KEY", "y")
    monkeypatch.setattr(macro_client, "ecos_client", lambda: object())
    monkeypatch.setattr(macro_client, "fred_client", lambda: object())
    monkeypatch.setattr(
        macro_fetcher,
        "fetch_ecos_series",
        lambda api, series_id, cycle, item_code, **kw: [
            {"date": date(2026, 1, 1), "value": 3.0}
        ],
    )
    monkeypatch.setattr(
        macro_fetcher,
        "fetch_fred_series",
        lambda fred, series_id, **kw: [{"date": date(2026, 1, 1), "value": 4.0}],
    )

    catalog = Path(__file__).resolve().parents[2] / ".planning" / "macro_series.yaml"
    collect_macro(engine=pg_clean, catalog_path=catalog)

    assert _count_runs(pg_clean, "macro") == 1
    row = _select_run(pg_clean, "macro")
    assert row["elapsed_ms"] >= 0
    assert "inserted" in row["stats"]


# ------------- krx ------------------------------------------------------------


def test_collect_krx_writes_collector_runs_row(pg_clean_with_entities, tmp_path, monkeypatch):
    """KRX run produces one collector_runs row regardless of per-ticker outcome."""
    from collectors.krx import collect_krx
    from collectors.krx import fetcher as krx_fetcher

    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)
    # Empty pykrx response → holiday path; still emits one collector_runs row.
    monkeypatch.setattr(
        krx_fetcher,
        "fetch_ohlcv",
        lambda t, d: pd.DataFrame(columns=["시가", "고가", "저가", "종가", "거래량"]),
    )
    collect_krx(engine=pg_clean_with_entities, since="2026-04-16")

    assert _count_runs(pg_clean_with_entities, "krx") == 1


# ------------- news -----------------------------------------------------------


def test_collect_news_writes_collector_runs_row(pg_clean_with_entities, tmp_path, monkeypatch):
    """News run produces one collector_runs row even when no RSS items match."""
    from collectors.news import client as news_client
    from collectors.news import collect_news
    from collectors.news import matcher

    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)
    # No RSS bodies → no items processed, but the run still completes and
    # must emit a single collector_runs row.
    monkeypatch.setattr(news_client, "fetch_rss_feed", lambda url: b"")
    # Bypass the alias-seeded guard (R-09); fixture seeds entities only.
    monkeypatch.setattr(matcher, "assert_aliases_seeded", lambda engine: None)
    monkeypatch.setattr(matcher, "load_scoped_aliases", lambda engine, scope: {})

    collect_news(engine=pg_clean_with_entities)

    assert _count_runs(pg_clean_with_entities, "news") == 1


# ------------- kind -----------------------------------------------------------


def test_collect_kind_writes_collector_runs_row(pg_clean_with_entities, tmp_path, monkeypatch):
    """KIND run produces one collector_runs row even with an empty DART feed."""
    from collectors.kind import collect_kind

    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "collectors.kind.dart_events.fetch_exchange_events",
        lambda *, bgn_de, end_de: [],
    )
    collect_kind(engine=pg_clean_with_entities)

    assert _count_runs(pg_clean_with_entities, "kind") == 1


# ------------- dart -----------------------------------------------------------


def test_collect_dart_writes_collector_runs_row(pg_clean_with_entities, monkeypatch):
    """DART run produces one collector_runs row even with empty filings list."""
    from collectors.dart import client as dart_client
    from collectors.dart import collect_dart
    from collectors.dart import fetcher as dart_fetcher

    # Mock dart-fss client to return a corp object with attributes
    class _Corp:
        stock_code = "005930"
        corp_name = "Samsung Electronics"

    monkeypatch.setattr(dart_client, "get_client", lambda: object())
    monkeypatch.setattr(dart_client, "find_corp", lambda corp_code: _Corp())
    # Empty filings list → no per-filing UPSERTs, but the run still emits
    # one collector_runs row.
    monkeypatch.setattr(dart_fetcher, "list_ab_filings", lambda corp_code, since, max_docs: [])

    collect_dart(corp_code="00126380", since="2026-01-01", engine=pg_clean_with_entities)

    assert _count_runs(pg_clean_with_entities, "dart") == 1


# ------------- shared fixture ------------------------------------------------


@pytest.fixture
def pg_clean_with_entities(pg_clean, monkeypatch):
    """pg_clean + seed entities row for 005930 so FK resolution succeeds.

    Several collectors (krx, news, kind, dart) need an entities row to
    process a ticker without falling into the missing_entity branch.
    """
    with pg_clean.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entities (corp_code, current_ticker, canonical_name) "
                "VALUES (:cc, :t, :n) "
                "ON CONFLICT (corp_code) DO NOTHING"
            ),
            {
                "cc": "00126380",
                "t": "005930",
                "n": "Samsung Electronics",
            },
        )
        conn.execute(
            text(
                "INSERT INTO entity_aliases (corp_code, kind, value, valid_from) "
                "VALUES (:cc, 'ticker', :v, :vf)"
            ),
            {"cc": "00126380", "v": "005930", "vf": date(2000, 1, 1)},
        )
    return pg_clean
