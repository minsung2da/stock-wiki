"""Phase 7 GRAPH-01: typed-edge population pipeline (post-pass).

Single-module per CONTEXT D-01. Called from src/ingest/worker.py batch tail
with the committed doc_ids and the same SQL connection (D-04 soft-fail policy
requires sharing the connection so document commits survive edge failures).

Edge taxonomy (CONTEXT D-06, locked):
    mentions_ticker (EXTRACTED)  document → ticker
    note_ticker     (EXTRACTED)  document(note) → ticker
    ticker_sector   (EXTRACTED)  ticker → sector
    supersedes      (EXTRACTED)  document(amendment) → document(original)
    filing_event    (INFERRED)   document → event(synth id)
    event_event     (INFERRED)   event(prev) → event(curr) within 90d

Event ID convention (Plan 02 lock-in to bypass empty `events` table — RESEARCH
Pitfall 1): ``{corp_code}-{event_type}-{first_seen_at.isoformat()}``. The
`events` table is intentionally NOT INSERTed by this module; `events` ETL is
deferred to a follow-up quick task. Q1-Q5 canonical queries (Plan 04) operate
on edges + documents directly.

Failure policy (D-04): exceptions inside _derive_* are caught and recorded in
counters['failed_per_type'][edge_type] truncated to 200 chars (V7 ASVS — no
PII leakage to ingest_runs). Other derivations continue.

Supersedes status (probe-findings.md, 2026-05-05): MISSING — no DART filing
in the current vault carries any correction marker, and the DART writer does
not surface one. ``_derive_supersedes`` is therefore a soft no-op that
increments ``counters['supersedes_skipped_no_field']`` for observability.
A follow-up quick task (post Phase 7) will extend
``src/collectors/dart/writer.py`` to populate the correction field; once that
ships, this module's supersedes derivation can be switched to active.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from itertools import groupby
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy.engine import Connection

logger = logging.getLogger(__name__)

EDGE_TAG_POLICY: dict[str, Literal["EXTRACTED", "INFERRED"]] = {
    "mentions_ticker": "EXTRACTED",
    "ticker_sector": "EXTRACTED",
    "note_ticker": "EXTRACTED",
    "supersedes": "EXTRACTED",
    "filing_event": "INFERRED",
    "event_event": "INFERRED",
}

_INSERT_EDGE_SQL = sa.text(
    "INSERT INTO edges (src_type, src_id, dst_type, dst_id, edge_type, tag) "
    "VALUES (:st, :si, :dt, :di, :et, :tag) "
    "ON CONFLICT ON CONSTRAINT uq_edge_endpoints DO NOTHING"
)

_TICKER_RE = re.compile(r"^[0-9]{6}$")
_CORP_CODE_RE = re.compile(r"^[0-9]{8}$")

__all__ = ["EDGE_TAG_POLICY", "populate"]


def _emit(
    conn: Connection,
    st: str,
    si: str,
    dt: str,
    di: str,
    et: str,
    counters: dict[str, Any],
) -> None:
    """Insert one edge with policy-determined tag. Updates counters in place."""
    if not si or not di:
        return  # defensive: empty endpoint means upstream extraction failed
    res = conn.execute(
        _INSERT_EDGE_SQL,
        {
            "st": st,
            "si": si,
            "dt": dt,
            "di": di,
            "et": et,
            "tag": EDGE_TAG_POLICY[et],
        },
    )
    if res.rowcount and res.rowcount > 0:
        counters["inserted"] += 1
    else:
        counters["skipped_conflict"] += 1


def _event_id(corp_code: str, event_type: str, first_seen_at: datetime) -> str:
    """Synthetic event id: ``{corp_code}-{event_type}-{ISO timestamp}``.

    Avoids dependency on the empty ``events`` table — RESEARCH Pitfall 1.
    """
    return f"{corp_code}-{event_type}-{first_seen_at.isoformat()}"


def _derive_ticker_sector(doc_ids: list[str], conn: Connection, counters: dict[str, Any]) -> None:
    """For each entity with non-null sector AND non-null current_ticker,
    emit (ticker → sector). Corpus-wide (not doc_ids-scoped) because sectors
    are entity-level metadata; idempotency makes repeated runs safe.
    """
    rows = conn.execute(
        sa.text(
            "SELECT current_ticker, sector FROM entities "
            "WHERE current_ticker IS NOT NULL AND sector IS NOT NULL"
        )
    ).all()
    for ticker, sector in rows:
        if not _TICKER_RE.match(ticker or ""):
            continue
        _emit(conn, "ticker", ticker, "sector", sector, "ticker_sector", counters)


def _is_note_path(vault_path: str, source: str) -> bool:
    return source == "note" or "/vault/notes/" in vault_path or "/notes/private/" in vault_path


def _derive_mentions_ticker(doc_ids: list[str], conn: Connection, counters: dict[str, Any]) -> None:
    """News docs whose ProvenanceBlock.tickers list has TickerRef entries
    produce mentions_ticker edges. DART docs with corp_code map via entities
    to current_ticker. Note docs are excluded (handled by _derive_note_ticker).
    """
    if not doc_ids:
        return
    from shared.frontmatter import read_frontmatter

    rows = (
        conn.execute(
            sa.text("SELECT id, vault_path, source, corp_code FROM documents WHERE id = ANY(:ids)"),
            {"ids": doc_ids},
        )
        .mappings()
        .all()
    )
    for r in rows:
        if _is_note_path(r["vault_path"], r["source"]):
            continue
        # ProvenanceBlock.tickers (news) is list[TickerRef] | None
        try:
            fm, _body = read_frontmatter(r["vault_path"])
            prov_tickers = fm.provenance.tickers or []
        except Exception:
            prov_tickers = []
        for tref in prov_tickers:
            ticker = getattr(tref, "ticker", None)
            if ticker and _TICKER_RE.match(ticker):
                _emit(
                    conn,
                    "document",
                    r["id"],
                    "ticker",
                    ticker,
                    "mentions_ticker",
                    counters,
                )
        # DART corp_code → ticker fallback: emit mentions edge to current_ticker
        if r["source"] == "dart" and r["corp_code"]:
            t = conn.execute(
                sa.text("SELECT current_ticker FROM entities WHERE corp_code=:cc"),
                {"cc": r["corp_code"]},
            ).scalar()
            if t and _TICKER_RE.match(t):
                _emit(
                    conn,
                    "document",
                    r["id"],
                    "ticker",
                    t,
                    "mentions_ticker",
                    counters,
                )


def _derive_note_ticker(doc_ids: list[str], conn: Connection, counters: dict[str, Any]) -> None:
    """Notes (source='note' OR vault_path under vault/notes/ or notes/private/)
    with frontmatter ``_derived.tickers`` produce one note_ticker edge per
    ticker. Body NER explicitly excluded (D-08); body-only matches recorded in
    counters['unmatched_body_tickers'] dict {ticker: count}.
    """
    if not doc_ids:
        return
    from shared.frontmatter import read_frontmatter

    rows = (
        conn.execute(
            sa.text("SELECT id, vault_path, source FROM documents WHERE id = ANY(:ids)"),
            {"ids": doc_ids},
        )
        .mappings()
        .all()
    )
    for r in rows:
        if not _is_note_path(r["vault_path"], r["source"]):
            continue
        try:
            fm, body = read_frontmatter(r["vault_path"])
        except Exception:
            continue
        tickers = list(fm.derived.tickers or [])
        for t in tickers:
            if _TICKER_RE.match(t):
                _emit(
                    conn,
                    "document",
                    r["id"],
                    "ticker",
                    t,
                    "note_ticker",
                    counters,
                )
        # Body-text scan for unmatched_body_tickers counter only (no edge).
        for m in re.findall(r"\b\d{6}\b", body or ""):
            if m not in tickers:
                counters["unmatched_body_tickers"][m] = (
                    counters["unmatched_body_tickers"].get(m, 0) + 1
                )


def _derive_supersedes(doc_ids: list[str], conn: Connection, counters: dict[str, Any]) -> None:
    """DART correction-of chain (MISSING path).

    Probe-findings.md (2026-05-05) confirmed the DART writer does not yet
    populate any correction-related frontmatter field, and no sampled DART
    vault filing carries one. This is a soft no-op: increment the counter so
    observability sees the gap, then return. Filed as a follow-up quick task
    to extend ``src/collectors/dart/writer.py`` (parse ``[기재정정]`` prefix
    in ``Report.report_nm`` + the embedded "정정 대상 보고서" rcept_no, OR
    call OpenDART's ``notice_search`` with ``pblntf_detail_ty='I001'`` for
    correction relationships). Once that ships, swap this body for the FOUND
    template — endpoint convention is amendment → original (locked in PLAN).
    """
    counters["supersedes_skipped_no_field"] = counters.get("supersedes_skipped_no_field", 0) + (
        len(doc_ids) if doc_ids else 0
    )


def _derive_filing_event(doc_ids: list[str], conn: Connection, counters: dict[str, Any]) -> None:
    """For each doc with documents.corp_code IS NOT NULL AND _derived.event_type
    IS NOT NULL, emit (document → event) where event_id is synthetic.

    Reads ``_derived.event_type`` from frontmatter. RESEARCH Pitfall 2: the
    field is SINGULAR (``event_type``), not a list (``events``).
    """
    if not doc_ids:
        return
    from shared.frontmatter import read_frontmatter

    rows = (
        conn.execute(
            sa.text(
                "SELECT id, vault_path, corp_code, first_seen_at FROM documents "
                "WHERE id = ANY(:ids) AND corp_code IS NOT NULL"
            ),
            {"ids": doc_ids},
        )
        .mappings()
        .all()
    )
    for r in rows:
        if not _CORP_CODE_RE.match(r["corp_code"] or ""):
            continue
        try:
            fm, _body = read_frontmatter(r["vault_path"])
            et = fm.derived.event_type
        except Exception:
            et = None
        if et is None:
            continue
        eid = _event_id(r["corp_code"], et, r["first_seen_at"])
        _emit(conn, "document", r["id"], "event", eid, "filing_event", counters)


def _derive_event_event(doc_ids: list[str], conn: Connection, counters: dict[str, Any]) -> None:
    """Same-corp_code temporal precedence within 90-day sliding window (D-09).

    Operates on the FULL corpus (not just doc_ids) because a new doc may
    create an edge with a previously-existing doc.

    Implementation: one SELECT for the corpus, then read_frontmatter once per
    row (no LATERAL placeholder, no N+1 re-query). For each adjacent pair
    within the same corp_code where 0 < delta_days <= 90, emit one edge from
    the earlier event_id to the later event_id.
    """
    from shared.frontmatter import read_frontmatter

    rows = (
        conn.execute(
            sa.text(
                "SELECT id, corp_code, first_seen_at, vault_path "
                "  FROM documents "
                " WHERE corp_code IS NOT NULL "
                " ORDER BY corp_code, first_seen_at"
            )
        )
        .mappings()
        .all()
    )

    enriched: list[dict[str, Any]] = []
    for r in rows:
        try:
            fm, _body = read_frontmatter(r["vault_path"])
            et = fm.derived.event_type
        except Exception:
            et = None
        if et is None:
            continue
        if not _CORP_CODE_RE.match(r["corp_code"] or ""):
            continue
        enriched.append(
            {
                "corp_code": r["corp_code"],
                "first_seen_at": r["first_seen_at"],
                "event_type": et,
            }
        )

    for corp_code, group in groupby(enriched, key=lambda x: x["corp_code"]):
        events = sorted(group, key=lambda x: x["first_seen_at"])
        for prev, curr in zip(events[:-1], events[1:], strict=False):
            delta = curr["first_seen_at"] - prev["first_seen_at"]
            if isinstance(delta, timedelta):
                days = delta.days
            else:
                days = (curr["first_seen_at"].date() - prev["first_seen_at"].date()).days
            if 0 < days <= 90:
                prev_eid = _event_id(corp_code, prev["event_type"], prev["first_seen_at"])
                curr_eid = _event_id(corp_code, curr["event_type"], curr["first_seen_at"])
                _emit(conn, "event", prev_eid, "event", curr_eid, "event_event", counters)


_DERIVATIONS: tuple[tuple[str, Any], ...] = (
    ("ticker_sector", _derive_ticker_sector),
    ("mentions_ticker", _derive_mentions_ticker),
    ("note_ticker", _derive_note_ticker),
    ("supersedes", _derive_supersedes),
    ("filing_event", _derive_filing_event),
    ("event_event", _derive_event_event),
)


def populate(doc_ids: list[str], conn: Connection) -> dict[str, Any]:
    """Phase 7 GRAPH-01 entry point. Called by src/ingest/worker.py batch tail
    (D-03). Idempotent (D-02). Soft-fail per derivation (D-04).

    Returns a counters dict:
      - inserted (int): rows newly inserted into edges
      - skipped_conflict (int): ON CONFLICT no-ops (idempotency hits)
      - failed_per_type (dict[str, str]): edge_type -> truncated exception text
      - unmatched_body_tickers (dict[str, int]): note body ticker hits not in
        the frontmatter list (no edge emitted; observed only)
      - supersedes_skipped_no_field (int): DART probe MISSING — Plan 02 no-op
    """
    counters: dict[str, Any] = {
        "inserted": 0,
        "skipped_conflict": 0,
        "failed_per_type": {},
        "unmatched_body_tickers": {},
    }
    for edge_type, fn in _DERIVATIONS:
        try:
            fn(doc_ids, conn, counters)
        except Exception as exc:  # noqa: BLE001 — D-04 soft-fail
            counters["failed_per_type"][edge_type] = str(exc)[:200]
            logger.exception("edge derivation failed: %s", edge_type)
    return counters
