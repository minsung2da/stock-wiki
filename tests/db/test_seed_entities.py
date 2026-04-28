"""Tests for seed_entities — monkeypatches dart_fss so tests run offline."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import text

from db.seed_entities import seed_entities_from_portfolio


def _write_portfolio(repo_root: Path, holdings: list[str], watchlist: list[str]) -> None:
    # Phase 6 P-01: portfolio at <repo_root>/notes/private/portfolio.md
    (repo_root / "notes" / "private").mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    if holdings:
        lines.append("holdings:")
        for t in holdings:
            lines.append(f'  - ticker: "{t}"')
            lines.append("    qty: 1")
            lines.append("    avg_cost: 0")
    else:
        lines.append("holdings: []")
    if watchlist:
        lines.append("watchlist:")
        for t in watchlist:
            lines.append(f'  - "{t}"')
    else:
        lines.append("watchlist: []")
    lines.append("---")
    (repo_root / "notes" / "private" / "portfolio.md").write_text("\n".join(lines))


class _FakeCorpList:
    def __init__(self, mapping: dict[str, tuple[str, str]]):
        self._m = mapping

    def find_by_stock_code(self, ticker: str):
        if ticker not in self._m:
            return None
        corp_code, corp_name = self._m[ticker]
        return SimpleNamespace(corp_code=corp_code, corp_name=corp_name, stock_code=ticker)


def test_seed_entities_upserts_each_ticker(vault_tmp: Path, seeded_engine, monkeypatch):
    _write_portfolio(vault_tmp, holdings=["005930"], watchlist=["000660", "035420"])

    mapping = {
        "005930": ("00126380", "삼성전자"),
        "000660": ("00164779", "SK하이닉스"),
        "035420": ("00266961", "NAVER"),
    }
    import dart_fss

    monkeypatch.setattr(dart_fss, "get_corp_list", lambda: _FakeCorpList(mapping))
    from collectors.dart import client as dc

    monkeypatch.setattr(dc, "get_client", lambda: None)

    up, failed = seed_entities_from_portfolio(seeded_engine, vault_tmp)
    assert up == 3
    assert failed == []

    with seeded_engine.connect() as c:
        rows = c.execute(
            text("SELECT corp_code, current_ticker FROM entities ORDER BY current_ticker")
        ).all()
    codes = {(r.corp_code, r.current_ticker) for r in rows}
    assert ("00126380", "005930") in codes
    assert ("00164779", "000660") in codes
    assert ("00266961", "035420") in codes


def test_seed_entities_skips_missing_dart_corp(vault_tmp: Path, seeded_engine, monkeypatch):
    _write_portfolio(vault_tmp, holdings=["005930"], watchlist=["999999"])

    mapping = {"005930": ("00126380", "삼성전자")}  # 999999 intentionally missing
    import dart_fss

    monkeypatch.setattr(dart_fss, "get_corp_list", lambda: _FakeCorpList(mapping))
    from collectors.dart import client as dc

    monkeypatch.setattr(dc, "get_client", lambda: None)

    up, failed = seed_entities_from_portfolio(seeded_engine, vault_tmp)
    assert up == 1
    assert failed == ["999999"]


def test_seed_entities_idempotent_rerun(vault_tmp: Path, seeded_engine, monkeypatch):
    _write_portfolio(vault_tmp, holdings=["005930"], watchlist=[])

    import dart_fss

    mapping = {"005930": ("00126380", "삼성전자")}
    monkeypatch.setattr(dart_fss, "get_corp_list", lambda: _FakeCorpList(mapping))
    from collectors.dart import client as dc

    monkeypatch.setattr(dc, "get_client", lambda: None)

    up1, _ = seed_entities_from_portfolio(seeded_engine, vault_tmp)
    up2, _ = seed_entities_from_portfolio(seeded_engine, vault_tmp)
    assert up1 == 1 and up2 == 1  # upsert counts both, but table has 1 row

    with seeded_engine.connect() as c:
        cnt = c.execute(
            text("SELECT COUNT(*) FROM entities WHERE current_ticker='005930'")
        ).scalar()
    assert cnt == 1
