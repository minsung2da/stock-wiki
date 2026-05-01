"""``get_recent_events`` MCP tool — chronological timeline by ticker (MCP-04, D-05).

Returns up to 50 ``EventRow`` items (DART filings + news articles + KIND notices)
for a given ticker since an ISO date. Two-step pattern (D-08): rows carry
``id`` + ``snippet_200ch`` + ``vault_path`` only — full body must be fetched
via ``get_filing(id=...)``.

Snippets prefer ``_derived.summary`` (Phase 5 enrichment) and fall back to the
first 200 chars of the body, wrapped in ``<vault_excerpt>`` per D-08 /
INGEST-09 trust marker. Frontmatter is re-read from disk at ``vault_path``
(the ``documents`` table stores body only — there is no JSONB frontmatter
column). If the file is missing or malformed, fields gracefully degrade
(type=None, title=body[:80]).
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import sqlalchemy as sa

from db.engine import get_engine
from db.entity import resolve_entity

from ..errors import ErrorCode, StructuredError, to_error_response
from ..logging import log_tool_call
from ..models import EventRow, EventTimeline
from ..snippets import build_snippet
from .search import mcp

__all__ = ["EVENTS_LIMIT", "get_recent_events"]


EVENTS_LIMIT = 50  # D-05 cap

_TITLE_FALLBACK_CHARS = 80


def _read_disk_frontmatter(vault_path: str) -> dict:
    """Best-effort frontmatter read. Returns {} if file missing/malformed."""
    try:
        if not Path(vault_path).exists():
            return {}
        from shared.frontmatter import read_frontmatter

        fm_model, _body = read_frontmatter(vault_path)
        return fm_model.model_dump(by_alias=True, exclude_none=True)
    except Exception:  # noqa: BLE001 — defensive: never block timeline on FM
        return {}


def get_recent_events(ticker: str, since: str) -> EventTimeline | dict:
    """Recent disclosure / news / KIND events for a ticker (MCP-04, JUDGE-04).

    Returns a chronological (DESC by ``first_seen_at``) list of up to 50
    events for the given ticker since an ISO date. Each row carries an ``id``
    (sha256 of the document body — feed back into ``get_filing(id=...)`` to
    materialize the full body) plus a 200-char ``<vault_excerpt>``-wrapped
    snippet, source, type, title, and citable ``vault_path``.

    ### Behavior contract
    - ``ticker``: 6-digit KRX ticker (e.g. ``"005930"``) **or** 8-digit DART
      ``corp_code`` (e.g. ``"00126380"``); both forms resolve to the same
      entity via ``resolve_entity``.
    - ``since``: ISO ``YYYY-MM-DD`` date (inclusive lower bound on
      ``first_seen_at``). Wrong-format strings (``"2026/04/01"``, garbage)
      raise ``INVALID_DATE`` rather than silently returning all events.
    - Source filter: ``documents.source IN ('dart', 'news', 'kind')`` —
      excludes ``'note'`` (memos), ``'krx'`` (price data), and ``'macro'``.
    - Order: ``first_seen_at DESC``. Hard cap at 50 rows (D-05).
    - Two-step pattern (D-08): rows never inline body. Callers fetch full
      text through ``get_filing(id=...)``.

    ### Response shape
    Returns ``EventTimeline`` with:
    - ``events``: list of ``EventRow`` — each carries ``id``, ``source``,
      ``date`` (ISO YYYY-MM-DD from ``first_seen_at``), ``type``
      (``_derived.event_type`` or None), ``title`` (provenance.company_name
      or first 80 body chars), ``snippet_200ch`` (wrapped in
      ``<vault_excerpt>``; uses ``_derived.summary`` when present, else
      ``body[:200]``), and ``vault_path``.
    - ``truncation_applied``: list of human-readable notes (e.g. ``"50-row
      cap"`` if the query returned the maximum).

    ### Errors
    Returns ``{"error": {"code": ..., "message": ..., "details": {...}}}`` —
    never raises. Codes:
    - ``INVALID_TICKER``: ticker not resolvable via ``resolve_entity``.
    - ``INVALID_DATE``: ``since`` is not parseable as ISO YYYY-MM-DD.
    - ``DB_UNAVAILABLE``: Postgres unreachable.
    - ``INTERNAL``: unexpected failure (string truncated to 200 chars).

    ### Performance budget
    p95 latency < 3s. Response size < 8k tokens at 50 rows × 200-char
    snippets — well below the per-tool token guard.
    """
    t0 = time.perf_counter()
    args_log = {"ticker": ticker, "since": since}
    try:
        # Validate `since` first — fail fast before any DB work.
        try:
            since_date = date.fromisoformat(since)
        except (ValueError, TypeError) as e:
            raise StructuredError(
                ErrorCode.INVALID_DATE,
                "since must be ISO YYYY-MM-DD",
                details={"since": since, "parse_error": str(e)[:120]},
            ) from e

        engine = get_engine()
        entity = resolve_entity(engine, ticker)
        if entity is None:
            raise StructuredError(
                ErrorCode.INVALID_TICKER,
                f"unknown ticker: {ticker}",
                details={"ticker": ticker},
            )
        corp_code = entity.corp_code

        with engine.connect() as conn:
            rows = (
                conn.execute(
                    sa.text(
                        "SELECT d.id, d.source, d.vault_path, d.first_seen_at, d.body "
                        "FROM documents d "
                        "WHERE d.corp_code = :corp_code "
                        "AND d.source IN ('dart', 'news', 'kind') "
                        "AND d.first_seen_at >= :since "
                        "ORDER BY d.first_seen_at DESC "
                        f"LIMIT {EVENTS_LIMIT}"
                    ),
                    {"corp_code": corp_code, "since": since_date},
                )
                .mappings()
                .all()
            )

        events: list[EventRow] = []
        for row in rows:
            body = row["body"] or ""
            fm = _read_disk_frontmatter(row["vault_path"])
            derived = fm.get("_derived") or fm.get("derived") or {}
            provenance = fm.get("provenance") or {}
            event_type = derived.get("event_type")
            summary = derived.get("summary")
            title = provenance.get("company_name") or (body[:_TITLE_FALLBACK_CHARS] if body else "")
            snippet = build_snippet(body, summary)
            first_seen = row["first_seen_at"]
            event_date = (
                first_seen.date().isoformat()
                if hasattr(first_seen, "date")
                else str(first_seen)[:10]
            )
            events.append(
                EventRow(
                    id=row["id"],
                    source=row["source"],
                    date=event_date,
                    type=event_type,
                    title=title,
                    snippet_200ch=snippet,
                    vault_path=row["vault_path"],
                )
            )

        truncation: list[str] = []
        if len(events) >= EVENTS_LIMIT:
            truncation.append(f"{EVENTS_LIMIT}-row cap")

        result = EventTimeline(events=events, truncation_applied=truncation)
        latency = int((time.perf_counter() - t0) * 1000)
        log_tool_call(
            "get_recent_events",
            args_log,
            latency,
            len(result.model_dump_json()) // 4,
        )
        return result
    except StructuredError as e:
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(e)
        log_tool_call("get_recent_events", args_log, latency, 0, error=err["error"])
        return err
    except Exception as e:  # noqa: BLE001 — D-21 catch-all
        wrapped = StructuredError(ErrorCode.INTERNAL, str(e)[:200])
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(wrapped)
        log_tool_call("get_recent_events", args_log, latency, 0, error=err["error"])
        return err


mcp.tool()(get_recent_events)
