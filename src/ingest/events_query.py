"""Phase 8 — SQL helpers backing dashboards/events-this-week.md (D-09).

Pure read-only helper. Returns events filtered by ticker overlap (holdings ∪
watchlist) and KST week range, sorted by event_type priority then date desc.

Reads ``_derived.tickers`` and ``_derived.event_type`` from frontmatter on
disk (mirrors edges.py pattern — no JSONB column on documents).

CI guard COLL-07: this module MUST NOT import ``anthropic`` or ``openai``.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
UTC = ZoneInfo("UTC")

# D-09 정렬 우선순위: 공시 > 거래정지 > 실적 > 뉴스 → date desc
EVENT_TYPE_PRIORITY: dict[str, int] = {
    "공시": 1,
    "거래정지": 2,
    "실적": 3,
    "뉴스": 4,
}
_DEFAULT_PRIORITY = 5  # unknown event_type sorts after all known categories

# Map English Pydantic EventType labels to Korean priority buckets so DART/news
# real-data ingest also sorts correctly. Keep additive — unknown English values
# fall back to _DEFAULT_PRIORITY.
_ENGLISH_TO_KOREAN: dict[str, str] = {
    "earnings_release": "실적",
    "equity_issue": "공시",
    "mergers_acquisitions": "공시",
    "major_contract": "공시",
    "board_change": "공시",
    "ownership_change": "공시",
    "buyback_announcement": "공시",
    "dividend": "공시",
    "suspension": "거래정지",
    "watchlist_designation": "거래정지",
    "unfaithful_disclosure": "거래정지",
    "delisting": "거래정지",
    "investment_caution": "거래정지",
    "investment_risk": "거래정지",
    "analyst_upgrade": "뉴스",
    "analyst_downgrade": "뉴스",
    "macro_commentary": "뉴스",
    "market_gossip": "뉴스",
}

_DEFAULT_LIMIT = 50  # T-08-04-03 — DoS guard


__all__ = [
    "EVENT_TYPE_PRIORITY",
    "kst_week_bounds",
    "kst_week_utc_bounds",
    "events_this_week",
]


def kst_week_bounds(today: date | None = None) -> tuple[date, date]:
    """Return (monday_kst, sunday_kst) inclusive for the KST week of ``today``."""
    d = today or datetime.now(KST).date()
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def kst_week_utc_bounds(today: date | None = None) -> tuple[datetime, datetime]:
    """Return (start_utc, end_utc) — half-open [start, end) covering KST monday
    00:00 through (sunday 23:59:59.999...) i.e. next monday 00:00 KST.
    """
    monday, _sunday = kst_week_bounds(today)
    start_kst = datetime(monday.year, monday.month, monday.day, 0, 0, tzinfo=KST)
    end_kst = start_kst + timedelta(days=7)
    return start_kst.astimezone(UTC), end_kst.astimezone(UTC)


def _priority_for(event_type: str | None) -> int:
    if event_type is None:
        return _DEFAULT_PRIORITY
    if event_type in EVENT_TYPE_PRIORITY:
        return EVENT_TYPE_PRIORITY[event_type]
    bucket = _ENGLISH_TO_KOREAN.get(event_type)
    if bucket is not None:
        return EVENT_TYPE_PRIORITY[bucket]
    return _DEFAULT_PRIORITY


def _read_derived(vault_path_value: str, vault_root: Path | None) -> tuple[list[str], str | None, str | None]:
    """Return (tickers, event_type, title) parsed from a vault file's frontmatter.

    Resolves ``vault_path_value`` against ``vault_root`` if relative. Returns
    ([], None, None) on read/parse failure (best-effort, mirrors edges.py).
    """
    p = Path(vault_path_value)
    if not p.is_absolute() and vault_root is not None:
        # Two paths to try: vault_root/vault_path AND vault_path treated as already-relative-to-vault.
        candidates = [vault_root / vault_path_value, Path(vault_path_value)]
    else:
        candidates = [p]
    for cand in candidates:
        if cand.exists():
            try:
                import frontmatter as pyfm

                post = pyfm.load(str(cand))
                meta = dict(post.metadata or {})
                derived = meta.get("_derived") or {}
                provenance = meta.get("provenance") or {}
                tickers_raw = derived.get("tickers") or []
                # tickers may be list[str] or list[{ticker:..}] — normalize.
                tickers: list[str] = []
                for t in tickers_raw:
                    if isinstance(t, str):
                        tickers.append(t)
                    elif isinstance(t, dict) and "ticker" in t:
                        tickers.append(str(t["ticker"]))
                event_type = derived.get("event_type")
                title = provenance.get("title")
                return tickers, event_type, title
            except Exception:  # noqa: BLE001 — best-effort
                logger.exception("events_query: frontmatter read failed for %s", cand)
                return [], None, None
    return [], None, None


def events_this_week(
    engine: Engine,
    holdings_tickers: list[str],
    *,
    today: date | None = None,
    vault_root: Path | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Return events for the current KST week, filtered by ticker overlap.

    SQL pulls candidate rows (source ∈ dart/news/kind, first_seen_at within
    KST monday..(next monday) range). Per-row frontmatter is read to obtain
    ``_derived.tickers`` and ``_derived.event_type``; rows whose tickers
    intersect ``holdings_tickers`` are kept and sorted by priority/date.

    Args:
        engine: SQLAlchemy engine.
        holdings_tickers: tickers (KRX 6-digit) the user wants to see events
            for. Empty list → no rows returned (no implicit firehose).
        today: anchor date in KST (defaults to ``datetime.now(KST).date()``).
        vault_root: base path used to resolve ``documents.vault_path`` if
            stored as relative. None → use vault_path verbatim.
        limit: max rows returned (T-08-04-03 DoS guard).

    Returns:
        list of dicts with keys: vault_path, source, first_seen_at, tickers,
        event_type, priority, title.
    """
    if not holdings_tickers:
        return []

    start_utc, end_utc = kst_week_utc_bounds(today)

    # Parameterized: SQL injection mitigation (T-08-04-02).
    # WR-02 (Phase 8): cap candidate rows on the SQL side so per-row FS reads
    # cannot grow unbounded with backfills/popular tickers. The cap is a soft
    # multiple of the requested limit (filtering by ticker overlap happens
    # after the FS pass), with a floor for tiny limits.
    sql = sa.text(
        "SELECT id, vault_path, source, first_seen_at "
        "  FROM documents "
        " WHERE source IN ('dart', 'news', 'kind') "
        "   AND first_seen_at >= :start_ts "
        "   AND first_seen_at <  :end_ts "
        " ORDER BY first_seen_at DESC "
        " LIMIT :hard_cap"
    )

    holdings_set = set(holdings_tickers)
    hard_cap = max(limit * 10, 500)

    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {"start_ts": start_utc, "end_ts": end_utc, "hard_cap": hard_cap},
        ).mappings().all()

    enriched: list[dict[str, Any]] = []
    for r in rows:
        tickers, event_type, title = _read_derived(r["vault_path"], vault_root)
        if not (set(tickers) & holdings_set):
            continue
        enriched.append(
            {
                "id": r["id"],
                "vault_path": r["vault_path"],
                "source": r["source"],
                "first_seen_at": r["first_seen_at"],
                "tickers": tickers,
                "event_type": event_type,
                "priority": _priority_for(event_type),
                "title": title,
            }
        )

    enriched.sort(key=lambda x: (x["priority"], -x["first_seen_at"].timestamp()))
    return enriched[:limit]
