"""Phase 8 Plan 04 Task 1 — DASH-03 events_this_week SQL helper tests.

KST 월~일 범위, ticker filter (holdings∪watchlist), 정렬 우선순위
(공시 > 거래정지 > 실적 > 뉴스 → date desc).
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import frontmatter as pyfm
import pytest
import sqlalchemy as sa

from ingest.events_query import (
    EVENT_TYPE_PRIORITY,
    events_this_week,
    kst_week_bounds,
)

KST = ZoneInfo("Asia/Seoul")


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_doc(
    vault_root: Path,
    rel_path: str,
    *,
    source: str,
    tickers: list[str],
    event_type: str | None,
    title: str = "제목",
) -> Path:
    """Create a vault file with provenance + _derived frontmatter."""
    p = vault_root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    meta: dict = {
        "provenance": {
            "source": source,
            "title": title,
        },
        "_derived": {
            "tickers": list(tickers),
            "event_type": event_type,
        },
    }
    post = pyfm.Post("본문")
    post.metadata = meta
    p.write_text(pyfm.dumps(post), encoding="utf-8")
    return p


def _insert_document(
    engine,
    *,
    vault_path: Path,
    source: str,
    first_seen_at_kst: datetime,
    body: str = "본문",
) -> str:
    """INSERT a documents row. Returns doc_id (sha256 hex of body)."""
    doc_id = hashlib.sha256((body + str(vault_path)).encode("utf-8")).hexdigest()
    fsa_utc = first_seen_at_kst.astimezone(ZoneInfo("UTC"))
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO documents "
                "(id, body, source, vault_path, first_seen_at, last_seen_at) "
                "VALUES (:id, :body, :source, :vp, :fs, :ls)"
            ),
            {
                "id": doc_id,
                "body": body,
                "source": source,
                "vp": str(vault_path),
                "fs": fsa_utc,
                "ls": fsa_utc,
            },
        )
    return doc_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_kst_week_bounds_returns_monday_to_sunday() -> None:
    # 2026-05-06 is a Wednesday in KST → week monday=2026-05-04, sunday=2026-05-10
    monday, sunday = kst_week_bounds(date(2026, 5, 6))
    assert monday == date(2026, 5, 4)
    assert sunday == date(2026, 5, 10)
    assert monday.weekday() == 0  # Monday
    assert sunday.weekday() == 6  # Sunday


def test_event_type_priority_ordering() -> None:
    """Korean labels: 공시(1) > 거래정지(2) > 실적(3) > 뉴스(4)."""
    assert EVENT_TYPE_PRIORITY["공시"] == 1
    assert EVENT_TYPE_PRIORITY["거래정지"] == 2
    assert EVENT_TYPE_PRIORITY["실적"] == 3
    assert EVENT_TYPE_PRIORITY["뉴스"] == 4


def test_events_this_week_returns_within_kst_week(pg_clean, tmp_path: Path) -> None:
    """5 rows in this KST week + 2 rows in prior week → only 5 returned."""
    today = date(2026, 5, 6)  # Wednesday
    monday = date(2026, 5, 4)
    holdings = ["005930"]

    # 5 docs inside this week (monday..wednesday)
    for i in range(5):
        rel = f"raw/dart/2026-05/this-{i}.md"
        _write_doc(
            tmp_path,
            rel,
            source="dart",
            tickers=["005930"],
            event_type="공시",
            title=f"이번주 공시 {i}",
        )
        _insert_document(
            pg_clean,
            vault_path=tmp_path / rel,
            source="dart",
            first_seen_at_kst=datetime(2026, 5, 4 + (i % 3), 10, 0, tzinfo=KST),
        )

    # 2 docs in PRIOR week (monday-1, sunday-1)
    for i in range(2):
        rel = f"raw/dart/2026-04/prev-{i}.md"
        _write_doc(
            tmp_path,
            rel,
            source="dart",
            tickers=["005930"],
            event_type="공시",
        )
        _insert_document(
            pg_clean,
            vault_path=tmp_path / rel,
            source="dart",
            first_seen_at_kst=datetime(2026, 4, 27 + i, 10, 0, tzinfo=KST),
        )

    rows = events_this_week(
        pg_clean, holdings_tickers=holdings, today=today, vault_root=tmp_path
    )
    assert len(rows) == 5, f"expected 5 rows in this KST week, got {len(rows)}"


def test_events_filtered_by_ticker(pg_clean, tmp_path: Path) -> None:
    """Holdings = ['005930']; doc tagged only with 000660 → not returned."""
    today = date(2026, 5, 6)

    # match
    rel_match = "raw/dart/match.md"
    _write_doc(tmp_path, rel_match, source="dart", tickers=["005930"], event_type="공시")
    _insert_document(
        pg_clean,
        vault_path=tmp_path / rel_match,
        source="dart",
        first_seen_at_kst=datetime(2026, 5, 5, 10, 0, tzinfo=KST),
    )

    # no match (different ticker)
    rel_other = "raw/dart/other.md"
    _write_doc(tmp_path, rel_other, source="dart", tickers=["000660"], event_type="공시")
    _insert_document(
        pg_clean,
        vault_path=tmp_path / rel_other,
        source="dart",
        first_seen_at_kst=datetime(2026, 5, 5, 10, 0, tzinfo=KST),
    )

    rows = events_this_week(
        pg_clean, holdings_tickers=["005930"], today=today, vault_root=tmp_path
    )
    assert len(rows) == 1
    assert "match.md" in rows[0]["vault_path"]


def test_events_sort_priority(pg_clean, tmp_path: Path) -> None:
    """Same date, different event_types → ordered 공시→거래정지→실적→뉴스."""
    today = date(2026, 5, 6)
    same_day = datetime(2026, 5, 5, 10, 0, tzinfo=KST)

    # Insert in REVERSE priority order to ensure helper actually sorts.
    plan = [
        ("뉴스", "raw/news/d.md", "news"),
        ("실적", "raw/dart/c.md", "dart"),
        ("거래정지", "raw/kind/b.md", "kind"),
        ("공시", "raw/dart/a.md", "dart"),
    ]
    for et, rel, src in plan:
        _write_doc(tmp_path, rel, source=src, tickers=["005930"], event_type=et)
        _insert_document(
            pg_clean,
            vault_path=tmp_path / rel,
            source=src,
            first_seen_at_kst=same_day,
        )

    rows = events_this_week(
        pg_clean, holdings_tickers=["005930"], today=today, vault_root=tmp_path
    )
    assert [r["event_type"] for r in rows] == ["공시", "거래정지", "실적", "뉴스"]


def test_events_kst_week_boundary(pg_clean, tmp_path: Path) -> None:
    """Sunday 23:59 KST is in this week; Monday 00:00 KST next week is NOT."""
    today = date(2026, 5, 6)  # week 5/4 .. 5/10

    # Sunday 5/10 23:59 KST → this week
    rel_in = "raw/dart/sun-late.md"
    _write_doc(tmp_path, rel_in, source="dart", tickers=["005930"], event_type="공시")
    _insert_document(
        pg_clean,
        vault_path=tmp_path / rel_in,
        source="dart",
        first_seen_at_kst=datetime(2026, 5, 10, 23, 59, tzinfo=KST),
    )

    # Monday 5/11 00:00 KST → NEXT week
    rel_out = "raw/dart/mon-early.md"
    _write_doc(tmp_path, rel_out, source="dart", tickers=["005930"], event_type="공시")
    _insert_document(
        pg_clean,
        vault_path=tmp_path / rel_out,
        source="dart",
        first_seen_at_kst=datetime(2026, 5, 11, 0, 0, tzinfo=KST),
    )

    rows = events_this_week(
        pg_clean, holdings_tickers=["005930"], today=today, vault_root=tmp_path
    )
    paths = [r["vault_path"] for r in rows]
    assert any("sun-late.md" in p for p in paths)
    assert not any("mon-early.md" in p for p in paths)
