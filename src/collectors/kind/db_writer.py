"""KIND db_writer — Plan 01-05 (Phase 1 Wave 2).

Two public functions:

- ``upsert_kind_filing`` writes the DART ``pblntf_ty='I'`` filing row.
  KIND filings carry empty ``body_md`` in Phase 1 — the full body backfill
  is a Phase 3 task (see RESEARCH.md Q1 / Q8 Wave-2A rationale).

- ``upsert_kind_event`` writes the KIND classifier row into ``events``.
  Events are immutable classifications (RESEARCH Q2): the UNIQUE constraint
  ``(event_type, ticker, event_date, source, source_id)`` means a same-key
  re-insertion returns ``'skipped'`` without touching the existing row.

Hard Vetoes enforced:
- #6 (no numeric embedding): ``events`` table is pure classifier — no
  body_md, no embedding columns on the table itself.
- #8 (no DART pre-chunking): ``filings.body_md`` is whole text (Phase 1
  KIND keeps it empty; Phase 3 backfill writes the full filing body).

SQL safety:
- rcept_no is regex-pre-filtered ``^[0-9]{14}$``.
- ticker is regex-pre-filtered ``^[0-9]{6}$``.
- event_type is validated against the 5-value enum imported from
  ``collectors.kind.sources.KindEventType`` (single source of truth).
- source is validated against ``{'dart', 'kind'}``.
- All values flow through SQLAlchemy bind parameters — no f-string
  interpolation into SQL.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import text

from collectors.kind.sources import KindEventType
from shared.content_hash import normalize_body

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

__all__ = ["upsert_kind_filing", "upsert_kind_event"]

_RCEPT_NO_RE = re.compile(r"^[0-9]{14}$")
_TICKER_RE = re.compile(r"^[0-9]{6}$")
_ALLOWED_EVENT_TYPES = frozenset(e.value for e in KindEventType)
_ALLOWED_SOURCES = frozenset({"dart", "kind"})


# ----- filings UPSERT -----

_SELECT_FILING_HASH_SQL = text(
    "SELECT content_hash FROM filings WHERE rcept_no = :r"
)

_BUMP_LAST_SEEN_SQL = text(
    "UPDATE filings SET last_seen_at = now() WHERE rcept_no = :r"
)

_UPSERT_FILING_SQL = text(
    """
    INSERT INTO filings (
        rcept_no, corp_code, ticker, filed_at, report_nm, pblntf_ty,
        event_type, source_url, content_hash, body_md, fetched_at,
        first_seen_at, last_seen_at
    ) VALUES (
        :rcept_no, :corp_code, :ticker, :filed_at, :report_nm, 'I',
        :event_type, :source_url, :content_hash, :body_md, now(),
        now(), now()
    )
    ON CONFLICT (rcept_no) DO UPDATE SET
        body_md = EXCLUDED.body_md,
        content_hash = EXCLUDED.content_hash,
        event_type = EXCLUDED.event_type,
        report_nm = EXCLUDED.report_nm,
        source_url = EXCLUDED.source_url,
        ticker = EXCLUDED.ticker,
        last_seen_at = now()
    """
)


def upsert_kind_filing(
    engine: Engine,
    *,
    rcept_no: str,
    corp_code: str,
    ticker: str | None,
    filed_at: datetime,
    report_nm: str,
    event_type: str,
    source_url: str,
    body_md: str = "",
) -> Literal["inserted", "updated", "skipped"]:
    """UPSERT into ``filings`` with ``pblntf_ty='I'`` (KIND classifier filings).

    Returns:
        ``'inserted'`` — no prior row; fresh row written.
        ``'updated'`` — prior row existed and content_hash differs (body_md
                        change). The whole columns set is overwritten with
                        EXCLUDED values and last_seen_at bumps.
        ``'skipped'`` — prior row exists with matching content_hash; only
                        last_seen_at bumps.

    ``body_md`` defaults to empty string. Phase 1 KIND filings have no body
    fetched (classifier needs only report_nm + source_url). Phase 3 backfill
    will populate body_md by re-fetching from DART.

    ``content_hash`` is computed as ``sha256(normalize_body(body_md))`` to
    stay consistent with the dart collector (01-07) which writes the same
    column. Two same-text bodies always hash identically across normalisations.
    """
    if not _RCEPT_NO_RE.match(rcept_no):
        raise ValueError(
            f"upsert_kind_filing: rcept_no must be 14 ASCII digits, got {rcept_no!r}"
        )
    if event_type not in _ALLOWED_EVENT_TYPES:
        raise ValueError(
            f"upsert_kind_filing: event_type {event_type!r} not in "
            f"{sorted(_ALLOWED_EVENT_TYPES)}"
        )

    content_hash = hashlib.sha256(
        normalize_body(body_md).encode("utf-8")
    ).hexdigest()

    params = {
        "rcept_no": rcept_no,
        "corp_code": corp_code,
        "ticker": ticker,
        "filed_at": filed_at,
        "report_nm": report_nm,
        "event_type": event_type,
        "source_url": source_url,
        "content_hash": content_hash,
        "body_md": body_md,
    }

    with engine.begin() as conn:
        existing = conn.execute(
            _SELECT_FILING_HASH_SQL, {"r": rcept_no}
        ).scalar()
        if existing is None:
            outcome: Literal["inserted", "updated", "skipped"] = "inserted"
        elif existing == content_hash:
            # Idempotent — bump last_seen_at only, skip the full UPSERT.
            conn.execute(_BUMP_LAST_SEEN_SQL, {"r": rcept_no})
            return "skipped"
        else:
            outcome = "updated"
        conn.execute(_UPSERT_FILING_SQL, params)
    return outcome


# ----- events INSERT -----

_INSERT_EVENT_SQL = text(
    """
    INSERT INTO events (
        event_type, ticker, event_date, corp_code, subtype, reason,
        source, source_id, source_url, filing_rcept_no, fetched_at
    ) VALUES (
        :event_type, :ticker, :event_date, :corp_code, :subtype, :reason,
        :source, :source_id, :source_url, :filing_rcept_no, now()
    )
    ON CONFLICT (event_type, ticker, event_date, source, source_id)
        DO NOTHING
    RETURNING id
    """
)


def upsert_kind_event(
    engine: Engine,
    *,
    event_type: str,
    ticker: str,
    event_date: date,
    source: str,
    source_id: str,
    source_url: str,
    corp_code: str | None = None,
    subtype: str | None = None,
    reason: str = "",
    filing_rcept_no: str | None = None,
) -> Literal["inserted", "skipped"]:
    """INSERT into ``events`` with ``ON CONFLICT DO NOTHING``.

    Returns:
        ``'inserted'`` — new row written.
        ``'skipped'`` — UNIQUE key collision; existing row left untouched.

    Events are immutable classifications (RESEARCH Q2). The UNIQUE constraint
    on ``(event_type, ticker, event_date, source, source_id)`` means cross-
    source duplicates (DART and KIND emitting the same unfaithful_disclosure)
    produce only ONE row — whichever wrote first wins.

    ``filing_rcept_no`` links DART-sourced events to their underlying
    ``filings`` row. For source='kind' events (KIND AJAX), this stays None —
    KIND-only events have no DART filing counterpart.
    """
    if event_type not in _ALLOWED_EVENT_TYPES:
        raise ValueError(
            f"upsert_kind_event: event_type {event_type!r} not in "
            f"{sorted(_ALLOWED_EVENT_TYPES)}"
        )
    if source not in _ALLOWED_SOURCES:
        raise ValueError(
            f"upsert_kind_event: source {source!r} not in {sorted(_ALLOWED_SOURCES)}"
        )
    if not _TICKER_RE.match(ticker):
        raise ValueError(
            f"upsert_kind_event: ticker must be 6 ASCII digits, got {ticker!r}"
        )

    params = {
        "event_type": event_type,
        "ticker": ticker,
        "event_date": event_date,
        "corp_code": corp_code,
        "subtype": subtype,
        "reason": reason,
        "source": source,
        "source_id": source_id,
        "source_url": source_url,
        "filing_rcept_no": filing_rcept_no,
    }

    with engine.begin() as conn:
        result = conn.execute(_INSERT_EVENT_SQL, params).first()
    return "inserted" if result is not None else "skipped"
