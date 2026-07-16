"""SC#2 integration tests for the briefing store surface (05-02) against live Postgres.

Exercises the four new ``cards.store`` briefing helpers + the ``invalidate()``
``invalidated_at`` stamp end-to-end on a real Postgres 17 testcontainer (the
``briefing_engine`` fixture seeds ≥11 entities so any card's corp_code FK resolves):

- save_briefing → get_briefing_row round-trip: a NULL-corp ``daily_briefing`` row
  INSERTs and reads back with ``entries`` intact (SC#2).
- the analysis-card invariant: a NULL-corp row with ``report_type IS NULL`` is REJECTED
  by ``ck_decision_cards_corp_or_report`` (T-05-01-01, mirrored at the store boundary).
- list_cards_for_briefing buckets a newly-generated, an expiring, and an invalidated
  card into the right ``BriefingCandidates`` field for date D (SC#1 enumeration).
- get_daily_briefings_in_range returns the dailies within ``[start, end]`` ordered by
  ``report_date`` (the weekly source, SC#4).

All test SQL uses bind params (never f-string interpolation).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from briefing.models import BriefingRow
from cards.store import (
    get_briefing_row,
    get_daily_briefings_in_range,
    invalidate,
    list_cards_for_briefing,
    save_briefing,
    save_card,
)

pytestmark = pytest.mark.db

_KST = ZoneInfo("Asia/Seoul")


def _at(d: date, hour: int) -> datetime:
    """A KST-aware datetime at ``hour:00`` on date ``d``."""
    return datetime(d.year, d.month, d.day, hour, 0, tzinfo=_KST)


def _make_briefing_row(report_date: date, entries: list[dict]) -> BriefingRow:
    """Build a self-describing daily ``BriefingRow`` (payload carries its own metadata).

    ``get_briefing_row`` reconstructs the scalar fields FROM the payload, so the payload
    must carry ``card_id``/``report_type``/``report_date``/``generated_at``/``as_of``/
    ``expires_at`` (as ISO-8601 strings) alongside ``entries`` (05-02 write contract).
    """
    gen = _at(report_date, 17)
    aof = _at(report_date, 16)
    exp = gen + timedelta(days=1)
    card_id = f"brief_daily_{report_date.isoformat()}"
    payload = {
        "card_id": card_id,
        "report_type": "daily_briefing",
        "report_date": report_date.isoformat(),
        "generated_at": gen.isoformat(),
        "as_of": aof.isoformat(),
        "expires_at": exp.isoformat(),
        "entries": entries,
    }
    return BriefingRow(
        card_id=card_id,
        report_type="daily_briefing",
        report_date=report_date,
        generated_at=gen,
        as_of=aof,
        expires_at=exp,
        payload=payload,
        body_md="| 종목 | 변화 | 근거 | 제안 | Why now | Why not |\n",
    )


# --- (conftest) the shared multi-entity seed ----------------------------------


def test_conftest_seeds_at_least_11_tickers(seeded_entities) -> None:
    tickers = {tk for _, tk in seeded_entities}
    corps = {cc for cc, _ in seeded_entities}
    assert len(tickers) >= 11
    assert len(corps) >= 11


# --- (a) save_briefing → get_briefing_row round-trip (SC#2) --------------------


def test_save_briefing_null_corp_and_read_back(briefing_engine) -> None:
    d = date(2026, 7, 16)
    entries = [
        {"ticker": "000001", "change": "HOLD→SELL", "stance": "SELL", "conviction": 0.81},
        {"ticker": "000002", "change": "+2 contradictions", "stance": "HOLD", "conviction": 0.60},
    ]
    row = _make_briefing_row(d, entries)

    returned_id = save_briefing(briefing_engine, row)
    assert returned_id == row.card_id

    # The stored row is genuinely NULL-corp (SC#2 landmine).
    with briefing_engine.begin() as conn:
        stored = conn.execute(
            text(
                "SELECT corp_code, ticker, report_type, status "
                "FROM decision_cards WHERE card_id = :cid"
            ),
            {"cid": row.card_id},
        ).one()
    assert stored.corp_code is None
    assert stored.ticker is None
    assert stored.report_type == "daily_briefing"
    assert stored.status == "active"

    fetched = get_briefing_row(briefing_engine, "daily_briefing", d)
    assert fetched is not None
    assert isinstance(fetched, BriefingRow)
    assert fetched.report_type == "daily_briefing"
    assert fetched.report_date == d
    # entries survive the JSONB round-trip intact.
    assert fetched.payload["entries"] == entries


def test_get_briefing_row_none_on_empty_db(briefing_engine) -> None:
    assert get_briefing_row(briefing_engine, "daily_briefing", date(2026, 7, 16)) is None


def test_get_briefing_row_picks_newest_for_date(briefing_engine) -> None:
    """Two rows for the same date → the newest (later generated_at) wins."""
    d = date(2026, 7, 16)
    older = _make_briefing_row(d, [{"ticker": "000001", "change": "old"}])
    older = older.model_copy(
        update={
            "card_id": "brief_daily_old",
            "generated_at": _at(d, 8),
            "payload": {**older.payload, "card_id": "brief_daily_old",
                        "generated_at": _at(d, 8).isoformat(),
                        "entries": [{"ticker": "000001", "change": "old"}]},
        }
    )
    newer = _make_briefing_row(d, [{"ticker": "000001", "change": "new"}])
    newer = newer.model_copy(
        update={
            "card_id": "brief_daily_new",
            "generated_at": _at(d, 18),
            "payload": {**newer.payload, "card_id": "brief_daily_new",
                        "generated_at": _at(d, 18).isoformat(),
                        "entries": [{"ticker": "000001", "change": "new"}]},
        }
    )
    save_briefing(briefing_engine, older)
    save_briefing(briefing_engine, newer)

    fetched = get_briefing_row(briefing_engine, "daily_briefing", d)
    assert fetched is not None
    assert fetched.card_id == "brief_daily_new"
    assert fetched.payload["entries"] == [{"ticker": "000001", "change": "new"}]


# --- (b) analysis-card invariant at the store boundary (T-05-01-01) ------------

_INSERT_ANALYSIS_NULL_CORP_SQL = text(
    "INSERT INTO decision_cards "
    "(card_id, corp_code, ticker, report_type, report_date, "
    " generated_at, as_of, payload, body_md, expires_at) "
    "VALUES (:card_id, NULL, NULL, NULL, NULL, "
    "        :generated_at, :as_of, CAST(:payload AS jsonb), :body_md, :expires_at)"
)


def test_null_corp_analysis_card_rejected(briefing_engine) -> None:
    """A NULL-corp row with ``report_type IS NULL`` (an analysis card) is REJECTED.

    ``ck_decision_cards_corp_or_report`` keeps the analysis-card FK invariant — only a
    briefing row (``report_type`` set) may have a NULL corp_code.
    """
    with (
        pytest.raises(IntegrityError) as excinfo,
        briefing_engine.begin() as conn,
    ):
        conn.execute(
            _INSERT_ANALYSIS_NULL_CORP_SQL,
            {
                "card_id": "bad_null_corp_analysis",
                "generated_at": "2026-07-16T17:00:00+09:00",
                "as_of": "2026-07-16T16:00:00+09:00",
                "payload": '{"decision": {"stance": "HOLD"}}',
                "body_md": "no corp — must be rejected",
                "expires_at": "2026-08-15T00:00:00+09:00",
            },
        )
    assert "ck_decision_cards_corp_or_report" in str(excinfo.value)


# --- (c) list_cards_for_briefing enumeration buckets (SC#1) --------------------


def test_list_cards_for_briefing_buckets(briefing_engine, make_card) -> None:
    """A newly-generated, an expiring, and an invalidated card land in the right bucket."""
    # ``invalidate()`` stamps ``invalidated_at = now(KST)``, so anchor D to the real
    # KST "today" the invalidate call will record.
    D = datetime.now(_KST).date()

    newly = make_card(
        corp_code="00000001",
        ticker="000001",
        card_id="c_newly",
        generated_at=_at(D, 10),
        expires_at=_at(D + timedelta(days=30), 16),
    )
    save_card(briefing_engine, newly)

    expiring = make_card(
        corp_code="00000002",
        ticker="000002",
        card_id="c_expiring",
        generated_at=_at(D - timedelta(days=10), 10),
        expires_at=_at(D, 16),
    )
    save_card(briefing_engine, expiring)

    inv = make_card(
        corp_code="00000003",
        ticker="000003",
        card_id="c_inv",
        generated_at=_at(D - timedelta(days=5), 10),
        expires_at=_at(D + timedelta(days=30), 16),
    )
    save_card(briefing_engine, inv)
    invalidated_card = invalidate(briefing_engine, "c_inv", "thesis broke")
    assert invalidated_card is not None
    assert invalidated_card.status == "invalidated"
    assert invalidated_card.invalidation_reason == "thesis broke"
    assert invalidated_card.invalidated_at is not None  # 05-02 stamp

    candidates = list_cards_for_briefing(briefing_engine, D)
    newly_ids = {c.card_id for c in candidates.newly_generated}
    expiring_ids = {c.card_id for c in candidates.expiring}
    invalidated_ids = {c.card_id for c in candidates.invalidated}

    assert "c_newly" in newly_ids
    assert "c_expiring" in expiring_ids
    assert "c_inv" in invalidated_ids

    # The invalidated card is no longer active → not in the active-only buckets.
    assert "c_inv" not in newly_ids
    assert "c_inv" not in expiring_ids
    # The expiring card was generated 10 days ago → not newly-generated for D.
    assert "c_expiring" not in newly_ids


def test_list_cards_for_briefing_excludes_briefing_rows(briefing_engine) -> None:
    """A briefing row generated on D must NOT appear in the analysis-card buckets."""
    D = date(2026, 7, 16)
    save_briefing(briefing_engine, _make_briefing_row(D, [{"ticker": "000001"}]))

    candidates = list_cards_for_briefing(briefing_engine, D)
    all_ids = {
        c.card_id
        for bucket in (candidates.newly_generated, candidates.expiring, candidates.invalidated)
        for c in bucket
    }
    assert f"brief_daily_{D.isoformat()}" not in all_ids


# --- (d) get_daily_briefings_in_range (weekly source, SC#4) --------------------


def test_get_daily_briefings_in_range_ordered(briefing_engine) -> None:
    d1, d2, d3 = date(2026, 7, 10), date(2026, 7, 11), date(2026, 7, 12)
    # Insert out of order to prove the ORDER BY report_date.
    for d in (d3, d1, d2):
        row = _make_briefing_row(d, [{"ticker": "000001", "date": d.isoformat()}])
        save_briefing(briefing_engine, row)

    rows = get_daily_briefings_in_range(briefing_engine, d1, d2)
    assert [r.report_date for r in rows] == [d1, d2]
    # d3 is outside [d1, d2] → excluded.
    assert all(r.report_date <= d2 for r in rows)
    assert all(isinstance(r, BriefingRow) for r in rows)
