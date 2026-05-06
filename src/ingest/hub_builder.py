"""Phase 8 — ticker hub generator (DASH-04, D-01~D-05).

Called from ingest worker post-cycle (Plan 02 Task 3). Rebuilds all corp_code
hubs in memory, writes only those whose content_hash differs from the existing
file (D-04 idempotent rebuild).

Hub path: ``vault/ingested/by-ticker/{corp_code}.md`` (D-05 — corp_code-based,
never ticker-aliased).

Key design notes:
- ``render_hub`` is a pure function; the canonical hash payload EXCLUDES
  ``generated_at`` so re-rendering at different wall-clock times stays
  idempotent (Pitfall 1 from 08-RESEARCH).
- ``write_hub_if_changed`` cheap pre-checks the hash by substring match in
  the existing frontmatter. mtime is preserved when unchanged.
- ``run`` iterates the ``entities`` table; missing inputs are recorded as
  ``review_flags`` (Pitfall 5) — ingest must not crash on partial seed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy import text
from sqlalchemy.engine import Engine

KST = ZoneInfo("Asia/Seoul")


@dataclass
class HubInputs:
    """All data needed to render one ticker hub. Pure data carrier."""

    corp_code: str
    ticker: str
    corp_name: str
    sector: str | None
    latest_price: int | None
    market_cap: int | None
    as_of: date | None
    recent_filings: list[dict]  # [{date, title, vault_path}, ...] up to 10
    recent_news: list[dict]  # [{date, title, source, vault_path}, ...] up to 10
    price_30d: list[tuple[date, int]]  # last 30 trading-day closes


@dataclass
class HubResult:
    written: int = 0
    skipped: int = 0
    review_flags: list[dict[str, Any]] = field(default_factory=list)


def _sparkline(price_30d: list[tuple[date, int]]) -> str:
    """7-bin Unicode block sparkline. Returns em-dash on empty input."""
    if not price_30d:
        return "—"
    bars = "▁▂▃▄▅▆▇█"
    prices = [p for _, p in price_30d]
    lo, hi = min(prices), max(prices)
    span = max(hi - lo, 1)
    return "".join(bars[min(7, int((p - lo) / span * 7))] for p in prices)


def _escape_cell(s: str) -> str:
    """Escape pipe + newline for markdown table cell safety (T-08-02-01)."""
    return s.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _format_filings_section(filings: list[dict]) -> str:
    if not filings:
        return "_없음_\n"
    lines = ["| 날짜 | 제목 | 링크 |", "|---|---|---|"]
    for f in filings[:10]:
        title = _escape_cell(str(f.get("title", "")))
        lines.append(f"| {f.get('date', '')} | {title} | [[{f.get('vault_path', '')}]] |")
    return "\n".join(lines) + "\n"


def _format_news_section(news: list[dict]) -> str:
    if not news:
        return "_없음_\n"
    lines = ["| 날짜 | 제목 | 소스 | 링크 |", "|---|---|---|---|"]
    for n in news[:10]:
        title = _escape_cell(str(n.get("title", "")))
        source = _escape_cell(str(n.get("source", "")))
        lines.append(
            f"| {n.get('date', '')} | {title} | {source} | [[{n.get('vault_path', '')}]] |"
        )
    return "\n".join(lines) + "\n"


def _format_body(inp: HubInputs) -> str:
    """Canonical body (everything below the frontmatter). Goes INTO the hash."""
    spark = _sparkline(inp.price_30d)
    filings = _format_filings_section(inp.recent_filings)
    news = _format_news_section(inp.recent_news)
    return (
        f"# {inp.corp_name} ({inp.ticker})\n\n"
        f"> Auto-generated. Edit `notes/private/{inp.ticker}/notes.md` for personal memos.\n\n"
        f"## 최근 공시 (10건)\n{filings}\n"
        f"## 최근 뉴스 (10건)\n{news}\n"
        f"## 가격 트렌드 (30일)\n`{spark}`\n\n"
        f"## Valuation\n\n"
        f"```dataview\nLIST FROM \"\" WHERE valuation AND ticker = \"{inp.ticker}\"\n```\n"
        f"_(Phase 10 D-12 hook — placeholder)_\n\n"
        f"## Private Notes\n"
        f"- [[notes/private/{inp.ticker}/thesis.md]]\n"
        f"- [[notes/private/{inp.ticker}/conviction.md]]\n"
        f"- [[notes/private/{inp.ticker}/notes.md]]\n"
    )


def _canonical_payload(inp: HubInputs) -> str:
    """Hash payload — EXCLUDES generated_at + content_hash (Pitfall 1)."""
    fm_for_hash = {
        "type": "ticker_hub",
        "ticker": inp.ticker,
        "corp_code": inp.corp_code,
        "corp_name": inp.corp_name,
        "sector": inp.sector,
        "latest_price": inp.latest_price,
        "market_cap": inp.market_cap,
        "as_of": inp.as_of.isoformat() if inp.as_of else None,
    }
    return (
        yaml.safe_dump(fm_for_hash, sort_keys=True, allow_unicode=True)
        + _format_body(inp)
    )


def render_hub(inp: HubInputs) -> tuple[str, str]:
    """Pure function. Returns ``(full_markdown_body, content_hash)``.

    ``content_hash`` is sha256 over a canonical payload that excludes
    ``generated_at`` so two renders at different times are hash-identical.
    """
    # Path containment guard (T-08-02-03): corp_code must be 8 digits.
    if not (inp.corp_code.isdigit() and len(inp.corp_code) == 8):
        raise ValueError(f"corp_code must be 8 digits: {inp.corp_code!r}")

    payload = _canonical_payload(inp)
    content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    generated_at = datetime.now(KST).isoformat()
    full_fm = {
        "type": "ticker_hub",
        "ticker": inp.ticker,
        "corp_code": inp.corp_code,
        "corp_name": inp.corp_name,
        "sector": inp.sector,
        "latest_price": inp.latest_price,
        "market_cap": inp.market_cap,
        "as_of": inp.as_of.isoformat() if inp.as_of else None,
        "generated_at": generated_at,
        "content_hash": content_hash,
    }
    full = (
        "---\n"
        + yaml.safe_dump(full_fm, sort_keys=False, allow_unicode=True)
        + "---\n\n"
        + _format_body(inp)
    )
    return full, content_hash


def write_hub_if_changed(path: Path, body: str, content_hash: str) -> bool:
    """Write only if file missing or existing content_hash differs.

    Returns True iff disk was written. Preserves mtime on no-op (D-04).
    """
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if f"content_hash: {content_hash}" in existing:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)
    return True


def collect_inputs_for_corp(engine: Engine, corp_code: str) -> HubInputs | None:
    """Query DB for hub inputs. Returns None if corp_code missing in entities.

    Detailed implementation:
    - SELECT entity row (corp_name, ticker, sector_proxy from canonical_name).
    - SELECT recent filings (source='dart', ORDER BY first_seen_at DESC LIMIT 10).
    - SELECT recent news (source='news', ticker filter, LIMIT 10).
    - price_30d / latest_price / market_cap: best-effort from documents body
      parsing (KRX OHLCV) — Phase 8 keeps this minimal; richer wiring is
      Plan 02 Task 2 (price_snapshot.py) territory.

    Phase 8 note: this function is intentionally conservative — it returns
    None if the entity row is missing OR if no DART/news rows are found,
    letting ``run`` record a review_flag. Tests stub this function via
    ``unittest.mock.patch``.
    """
    with engine.begin() as conn:
        ent_row = conn.execute(
            text(
                "SELECT corp_code, COALESCE(canonical_name, '') AS corp_name "
                "FROM entities WHERE corp_code = :cc"
            ),
            {"cc": corp_code},
        ).first()
        if ent_row is None:
            return None
        ticker_row = conn.execute(
            text(
                "SELECT alias FROM entity_aliases "
                "WHERE corp_code = :cc AND kind = 'ticker' LIMIT 1"
            ),
            {"cc": corp_code},
        ).first()
        ticker = ticker_row[0] if ticker_row else corp_code[:6]

        filings = [
            {"date": str(r[0]), "title": r[1] or "", "vault_path": r[2] or ""}
            for r in conn.execute(
                text(
                    "SELECT first_seen_at::date, "
                    "       COALESCE(SUBSTRING(body FROM 1 FOR 80), '') AS title, "
                    "       vault_path "
                    "FROM documents WHERE source = 'dart' AND corp_code = :cc "
                    "ORDER BY first_seen_at DESC LIMIT 10"
                ),
                {"cc": corp_code},
            ).all()
        ]
        news = [
            {
                "date": str(r[0]),
                "title": r[1] or "",
                "source": "news",
                "vault_path": r[2] or "",
            }
            for r in conn.execute(
                text(
                    "SELECT first_seen_at::date, "
                    "       COALESCE(SUBSTRING(body FROM 1 FOR 80), '') AS title, "
                    "       vault_path "
                    "FROM documents WHERE source = 'news' AND corp_code = :cc "
                    "ORDER BY first_seen_at DESC LIMIT 10"
                ),
                {"cc": corp_code},
            ).all()
        ]
    return HubInputs(
        corp_code=corp_code,
        ticker=ticker,
        corp_name=ent_row[1],
        sector=None,
        latest_price=None,
        market_cap=None,
        as_of=None,
        recent_filings=filings,
        recent_news=news,
        price_30d=[],
    )


def run(engine: Engine, vault_root: Path, repo_root: Path) -> HubResult:
    """Entry from worker post-cycle. Iterates all ``entities`` rows.

    Per-entity failure isolation: a single missing-inputs corp_code is
    recorded under ``review_flags`` and the loop continues (Pitfall 5).
    """
    result = HubResult()
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT corp_code FROM entities")).all()
    corp_codes = [r[0] for r in rows]
    out_dir = vault_root / "ingested" / "by-ticker"
    for cc in corp_codes:
        try:
            inp = collect_inputs_for_corp(engine, cc)
        except Exception as exc:  # noqa: BLE001 — per-entity isolation
            result.review_flags.append(
                {"corp_code": cc, "flag": "hub_collect_failed", "error": str(exc)[:200]}
            )
            continue
        if inp is None:
            result.review_flags.append(
                {"corp_code": cc, "flag": "hub_inputs_missing"}
            )
            continue
        body, h = render_hub(inp)
        path = out_dir / f"{cc}.md"
        if write_hub_if_changed(path, body, h):
            result.written += 1
        else:
            result.skipped += 1
    return result
