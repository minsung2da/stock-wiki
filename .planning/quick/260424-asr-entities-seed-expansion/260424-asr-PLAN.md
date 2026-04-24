---
type: quick
task: entities seed expansion
created: 2026-04-24
files_modified:
  - src/db/seed_entities.py
  - tests/db/test_seed_entities.py
---

# Quick: entities seed expansion from portfolio.md

## Objective

Seed `entities` (and corresponding `entity_aliases` ticker rows) from the tickers
listed in `vault/notes/portfolio.md` (holdings + watchlist union) so that
`collect_krx` no longer returns `missing_entity` for scope tickers.

**Surfaced by Phase 4 live smoke run (2026-04-24):** `entities` contained only
005930 (seeded by Phase 3 DART collector). 000660 (SK하이닉스 — watchlist)
triggered Plan 02's fail-soft path (correct behavior, wrong data state).

## Root truths

- `upsert_entity(engine, corp_code, canonical_name, ticker, market)` already
  exists in `src/db/entity.py:157` and is idempotent (`ON CONFLICT (corp_code)
  DO UPDATE`) — no migration needed.
- `dart_fss.get_corp_list().find_by_stock_code(ticker) -> Corp` resolves
  6-digit ticker → `(corp_code, corp_name, stock_code)` via the official
  OpenDART corp list. Verified live 2026-04-24: `000660` → `00164779 SK하이닉스`,
  `035420` → `00266961 NAVER`.
- `Portfolio.load(vault_root).scope_tickers()` returns `watchlist + holdings`.

## Task 1 — Create `src/db/seed_entities.py`

<read_first>
- src/db/entity.py (upsert_entity signature at line 157)
- src/db/seed_name_aliases.py (pattern to mirror — same filename convention,
  same `if __name__ == "__main__"` entry, same `get_engine()` import)
- src/shared/portfolio.py (Portfolio.load + scope_tickers — the tickers to seed)
- src/collectors/dart/client.py (find_corp helper; find_by_stock_code not wrapped
  but we can call via dart_fss.get_corp_list() directly or add a sibling helper)
</read_first>

<action>
Create `src/db/seed_entities.py` with:

```python
"""One-shot seeder: insert an entities row for every ticker in
vault/notes/portfolio.md (holdings ∪ watchlist) via OpenDART corp lookup.

Runs once per new machine / once per new watchlist addition. Idempotent:
`upsert_entity` uses ON CONFLICT. Missing DART corp for a ticker is logged
and skipped (doesn't abort the batch).

Operational command:
    uv run python -m src.db.seed_entities              # reads DATABASE_URL + DART_API_KEY
    uv run python -m src.db.seed_entities --vault vault
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from sqlalchemy.engine import Engine

from collectors.dart import client as dart_client
from db.engine import get_engine
from db.entity import upsert_entity
from shared.portfolio import Portfolio

log = logging.getLogger(__name__)


def seed_entities_from_portfolio(engine: Engine, vault_root: Path) -> tuple[int, list[str]]:
    """Seed entities for every ticker in portfolio scope.

    Returns (upserted_count, failed_tickers). Failures are tickers with no
    matching DART corp; they do not abort the batch.
    """
    portfolio = Portfolio.load(vault_root)
    tickers = sorted(set(portfolio.scope_tickers()))

    import dart_fss

    dart_client.init()
    corp_list = dart_fss.get_corp_list()

    upserted = 0
    failed: list[str] = []
    for ticker in tickers:
        try:
            corp = corp_list.find_by_stock_code(ticker)
        except Exception as exc:
            log.warning("dart_fss lookup failed for ticker=%s: %s", ticker, exc)
            failed.append(ticker)
            continue
        if corp is None:
            log.warning("no DART corp for ticker=%s", ticker)
            failed.append(ticker)
            continue
        upsert_entity(
            engine,
            corp_code=corp.corp_code,
            canonical_name=corp.corp_name,
            ticker=corp.stock_code,
            market=None,
        )
        upserted += 1
    return upserted, failed


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Seed entities from portfolio.md via OpenDART.")
    parser.add_argument("--vault", default="vault", help="Vault root (default: vault)")
    args = parser.parse_args()

    up, failed = seed_entities_from_portfolio(get_engine(), Path(args.vault))
    print(f"seed_entities: upserted {up} rows; failed {len(failed)}: {failed}")
    sys.exit(0 if not failed else 1)
```
</action>

<acceptance_criteria>
- `grep -q "def seed_entities_from_portfolio" src/db/seed_entities.py`
- `grep -q "find_by_stock_code" src/db/seed_entities.py`
- `grep -q "upsert_entity" src/db/seed_entities.py`
- `grep -q 'if __name__ == "__main__"' src/db/seed_entities.py`
- `uv run python -c "from db.seed_entities import seed_entities_from_portfolio"` exits 0
- Module is runnable: `uv run python -m src.db.seed_entities --help` exits 0
</acceptance_criteria>

## Task 2 — Unit test

<read_first>
- tests/collectors/conftest.py (seeded_engine, vault_tmp fixtures)
- tests/test_entity_alias.py (upsert_entity test patterns)
</read_first>

<action>
Create `tests/db/__init__.py` (empty) + `tests/db/test_seed_entities.py`:

```python
"""Tests for seed_entities — monkeypatches dart_fss so tests run offline."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import text

from db.seed_entities import seed_entities_from_portfolio


def _write_portfolio(vault_root: Path, holdings: list[str], watchlist: list[str]) -> None:
    (vault_root / "notes").mkdir(parents=True, exist_ok=True)
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
    (vault_root / "notes/portfolio.md").write_text("\n".join(lines))


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

    monkeypatch.setattr(dc, "init", lambda: None)

    up, failed = seed_entities_from_portfolio(seeded_engine, vault_tmp)
    assert up == 3
    assert failed == []

    with seeded_engine.connect() as c:
        rows = c.execute(text("SELECT corp_code, current_ticker FROM entities ORDER BY current_ticker")).all()
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

    monkeypatch.setattr(dc, "init", lambda: None)

    up, failed = seed_entities_from_portfolio(seeded_engine, vault_tmp)
    assert up == 1
    assert failed == ["999999"]


def test_seed_entities_idempotent_rerun(vault_tmp: Path, seeded_engine, monkeypatch):
    _write_portfolio(vault_tmp, holdings=["005930"], watchlist=[])

    import dart_fss

    mapping = {"005930": ("00126380", "삼성전자")}
    monkeypatch.setattr(dart_fss, "get_corp_list", lambda: _FakeCorpList(mapping))
    from collectors.dart import client as dc

    monkeypatch.setattr(dc, "init", lambda: None)

    up1, _ = seed_entities_from_portfolio(seeded_engine, vault_tmp)
    up2, _ = seed_entities_from_portfolio(seeded_engine, vault_tmp)
    assert up1 == 1 and up2 == 1  # upsert counts both, but table has 1 row

    with seeded_engine.connect() as c:
        cnt = c.execute(text("SELECT COUNT(*) FROM entities WHERE current_ticker='005930'")).scalar()
    assert cnt == 1
```
</action>

<acceptance_criteria>
- `uv run pytest tests/db/test_seed_entities.py -x -q` exits 0
- 3 tests pass
</acceptance_criteria>

## Task 3 — Live seed + documentation

<action>
1. Run live: `uv run python -m src.db.seed_entities` (with DART_API_KEY + DATABASE_URL in env). Expect `upserted >= 2` for current portfolio.md (005930 + 000660).

2. Verify: query entities table → both rows present.

3. Re-run `uv run stock collect krx` — expect 0 missing_entity failures for seeded tickers.

4. Update `CLAUDE.md` §First-time Setup to add a new step 4.5 (after seed_name_aliases):
   ```
   4.5. **entities 테이블 seed** (portfolio.md 기반)
   ```bash
   uv run python -m src.db.seed_entities
   ```
   ```

   watchlist·holdings에 티커가 추가될 때마다 재실행. 신규 티커만 OpenDART 조회.
5. Commit atomically:
   - `feat(quick-260424): add seed_entities from portfolio.md`
   - `test(quick-260424): seed_entities unit tests`
   - `docs(quick-260424): document entities seed step in First-time Setup`
</action>

<acceptance_criteria>
- `entities` table has ≥2 rows after live run (005930 + 000660)
- `uv run stock collect krx` exit code: 0 (status="ok", failed_count=0) for current portfolio
- CLAUDE.md contains "seed_entities" string
- 3 commits in git log with `quick-260424` prefix
</acceptance_criteria>
