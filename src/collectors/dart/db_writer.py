"""DART db_writer — Plan 01-07 (Phase 1 Wave 2).

Single public function: ``upsert_dart_filing``.

Replaces the Markdown writer (writer.py) for DART regular A/B filings.
Whole responsibility is one row in the ``filings`` table per ``rcept_no``,
with the WHOLE filing body stored verbatim in ``filings.body_md TEXT`` —
**no pre-chunking** at insert time.

Hard Veto #8 — DART body_md MUST be stored as a single TEXT blob (no
chunk table writes here). The ``chunks`` table remains dormant in Phase 1;
Phase 3 owns narrative-search rebuild.

Hard Veto #6 — ``filings.body_embedding halfvec(1024)`` is left NULL on
insert. Phase 3 populates embeddings from a separate pipeline. We never
import ``sentence-transformers`` or ``mecab-ko`` from this module.

DART vs KIND precedence on ``event_type``:
- ``upsert_dart_filing`` HARD-CODES ``event_type = NULL`` because DART
  regular filings (pblntf_ty A/B) carry no event classifier.
- KIND (plan 01-05) uses ``upsert_kind_filing`` for pblntf_ty='I' filings;
  that writer sets ``event_type`` from the KIND scraper. If both writers
  hit the same ``rcept_no`` (rare — DART regular's list_ab_filings filters
  pblntf_ty='A'/'B' only), the latter UPSERT wins. In practice this
  collision is empty because the pblntf_ty filters are disjoint.

SQL safety:
- ``rcept_no`` regex-pre-filtered ``^[0-9]{14}$``.
- ``corp_code`` regex-pre-filtered ``^[0-9]{8}$``.
- ``ticker`` (when not None) regex-pre-filtered ``^[0-9]{6}$``.
- ``pblntf_ty`` must be in {'A','B'} for this writer.
- All values flow through SQLAlchemy bind params; no f-string SQL.

Idempotency / change-detection (matches the macro/krx pattern):
- ``content_hash = sha256(normalize_body(body_md))`` (same algorithm used
  by every collector — shared.content_hash.normalize_body).
- Load-then-classify: SELECT the existing content_hash; if it matches the
  computed hash, the call is idempotent (only ``last_seen_at`` bumps).
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import text

from shared.content_hash import normalize_body

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_RCEPT_NO_RE = re.compile(r"^[0-9]{14}$")
_CORP_CODE_RE = re.compile(r"^[0-9]{8}$")
_TICKER_RE = re.compile(r"^[0-9]{6}$")
_ALLOWED_PBLNTF_TY = frozenset({"A", "B"})

__all__ = ["upsert_dart_filing"]


_UPSERT_SQL = text(
    """
    INSERT INTO filings
      (rcept_no, corp_code, ticker, filed_at, report_nm, pblntf_ty,
       event_type, source_url, content_hash, body_md, fetched_at)
    VALUES
      (:rcept_no, :corp_code, :ticker, :filed_at, :report_nm, :pblntf_ty,
       NULL, :source_url, :content_hash, :body_md, now())
    ON CONFLICT (rcept_no) DO UPDATE SET
      body_md = EXCLUDED.body_md,
      content_hash = EXCLUDED.content_hash,
      report_nm = EXCLUDED.report_nm,
      ticker = COALESCE(EXCLUDED.ticker, filings.ticker),
      last_seen_at = now()
    """
)

_BUMP_LAST_SEEN_SQL = text(
    "UPDATE filings SET last_seen_at = now() WHERE rcept_no = :r"
)

_SELECT_EXISTING_HASH_SQL = text(
    "SELECT content_hash FROM filings WHERE rcept_no = :r"
)


def upsert_dart_filing(
    engine: Engine,
    *,
    rcept_no: str,
    corp_code: str,
    ticker: str | None,
    filed_at: datetime,
    report_nm: str,
    pblntf_ty: str,
    body_md: str,
    source_url: str,
) -> Literal["inserted", "updated", "skipped"]:
    """UPSERT one DART filing row.

    Args:
        engine: SQLAlchemy engine (psycopg3).
        rcept_no: 14-digit DART receipt number (PK).
        corp_code: 8-digit DART corp code — must already exist in
            ``entities`` (FK CASCADE). Caller is responsible for the
            entity row (the DART collector upserts the entity post-run).
        ticker: 6-digit KRX ticker or None when DART has no stock_code
            (rare for pblntf_ty A/B but possible).
        filed_at: TIMESTAMPTZ — DART collector composes from rcept_dt at
            KST close (15:30 Asia/Seoul).
        report_nm: filing title (e.g. '분기보고서').
        pblntf_ty: 'A' (정기) or 'B' (주요사항). 'I' (KIND) routes through
            ``collectors.kind.db_writer.upsert_kind_filing`` instead.
        body_md: WHOLE filing body text. Stored verbatim — NO chunking
            applied here (Veto #8).
        source_url: canonical DART filing URL.

    Returns:
        ``"inserted"`` — no row with this rcept_no existed; freshly written.
        ``"updated"`` — row existed; body changed (content_hash differs).
        ``"skipped"`` — row existed with identical content_hash; only
                       ``last_seen_at`` was bumped.

    Raises:
        ValueError: on shape violations (rcept_no/corp_code/ticker/pblntf_ty).
        sqlalchemy.exc.IntegrityError: if corp_code FK is unsatisfied (no
            entity row exists yet).
    """
    if not _RCEPT_NO_RE.match(rcept_no):
        raise ValueError(
            f"upsert_dart_filing: bad rcept_no (need 14 ASCII digits): {rcept_no!r}"
        )
    if not _CORP_CODE_RE.match(corp_code):
        raise ValueError(
            f"upsert_dart_filing: bad corp_code (need 8 ASCII digits): {corp_code!r}"
        )
    if ticker is not None and not _TICKER_RE.match(ticker):
        raise ValueError(
            f"upsert_dart_filing: bad ticker (need 6 ASCII digits or None): {ticker!r}"
        )
    if pblntf_ty not in _ALLOWED_PBLNTF_TY:
        raise ValueError(
            f"upsert_dart_filing: bad pblntf_ty (need 'A' or 'B'): {pblntf_ty!r}"
        )

    # Compute content_hash on normalized body (same algorithm as other
    # collectors via shared.content_hash.normalize_body).
    content_hash = hashlib.sha256(
        normalize_body(body_md).encode("utf-8")
    ).hexdigest()

    params = {
        "rcept_no": rcept_no,
        "corp_code": corp_code,
        "ticker": ticker,
        "filed_at": filed_at,
        "report_nm": report_nm,
        "pblntf_ty": pblntf_ty,
        "source_url": source_url,
        "content_hash": content_hash,
        "body_md": body_md,
    }

    with engine.begin() as conn:
        existing = conn.execute(
            _SELECT_EXISTING_HASH_SQL, {"r": rcept_no}
        ).scalar()
        if existing is None:
            outcome: Literal["inserted", "updated", "skipped"] = "inserted"
        elif existing != content_hash:
            outcome = "updated"
        else:
            conn.execute(_BUMP_LAST_SEEN_SQL, {"r": rcept_no})
            return "skipped"
        conn.execute(_UPSERT_SQL, params)
    return outcome
