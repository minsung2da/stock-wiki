"""``get_filing`` + ``search_filings`` — the DART filing read tools.

Two tools registered on the shared ``mcp`` instance:

- :func:`get_filing` — whole-body filing fetch by ``rcept_no``. Returns the
  ENTIRE stored ``body_md`` (Veto #8 — no chunking, no slicing) wrapped in the
  ``<untrusted>`` XML delimiter and flagged for injection markers (D-03/SC#5).
  A missing row raises :class:`~mcp_v2.errors.FilingNotFound`; a malformed
  ``rcept_no`` raises :class:`~mcp_v2.errors.InvalidArgument` BEFORE the DB is
  touched.
- :func:`search_filings` — metadata-only filing search by ``corp_code`` with
  optional ``event_type`` / ``since`` / ``until`` filters, ordered ``filed_at
  DESC``, default ``limit=50`` (D-04). Returns no body and applies NO injection
  wrap (metadata is structured, not narrative). Zero rows → an empty
  :class:`~mcp_v2.models.SearchFilingsResult` (``hits=[]``, D-01).

SQL discipline (Veto #7 / SC#3 AST guard): every statement below is a
module-level ``text()`` constant bound with parameters — NO f-string SQL. The
``since`` / ``until`` / ``event_type`` filters use NULL-cast guards so a single
parameterized statement covers all filter combinations (``CAST(:x AS …) IS NULL
OR col = …``) — no string concatenation.

Input validation (V5): ``rcept_no`` (14 ASCII digits) and ``corp_code`` (8 ASCII
digits) are regex pre-filtered before any DB round-trip; ``corp_code`` existence
is confirmed via :func:`db.entity.resolve_entity` (→ ``EntityNotFound``).
"""

from __future__ import annotations

import re

from mcp.types import ToolAnnotations
from sqlalchemy import text

from db.engine import get_engine
from db.entity import resolve_entity

from .. import injection
from .._mcp import mcp
from ..errors import EntityNotFound, FilingNotFound, InvalidArgument
from ..models import FilingDetail, FilingHit, SearchFilingsResult

__all__ = ["get_filing", "search_filings"]

# ASCII-only digit pre-filters (str.isdigit accepts superscripts — close that
# loophole). rcept_no is the 14-digit DART receipt number PK; corp_code is the
# 8-digit DART corp code.
_RCEPT_NO_RE = re.compile(r"^[0-9]{14}$")
_CORP_CODE_RE = re.compile(r"^[0-9]{8}$")

# Default page size for search_filings (D-04). search responses are bounded so a
# single corp's filing history never floods the context (T-03-07 DoS).
_DEFAULT_SEARCH_LIMIT = 50


# --- SQL constants (bind params only — Veto #7, never f-string) ---------------

_SELECT_FILING_SQL = text(
    """
    SELECT corp_code, ticker, filed_at, report_nm, event_type, source_url, body_md
      FROM filings
     WHERE rcept_no = :rcept_no
    """
)

# NULL-cast filter guards: each optional filter is a no-op when its bind is NULL,
# so ONE statement covers every (event_type / since / until) combination without
# building SQL by string concatenation. ``until`` is half-open (< :until) to keep
# day-boundary semantics unambiguous.
_SEARCH_FILINGS_SQL = text(
    """
    SELECT rcept_no, filed_at, report_nm, event_type, pblntf_ty
      FROM filings
     WHERE corp_code = :corp_code
       AND (CAST(:event_type AS text) IS NULL OR event_type = CAST(:event_type AS text))
       AND (CAST(:since AS timestamptz) IS NULL OR filed_at >= CAST(:since AS timestamptz))
       AND (CAST(:until AS timestamptz) IS NULL OR filed_at <  CAST(:until AS timestamptz))
     ORDER BY filed_at DESC
     LIMIT :limit
    """
)


def _isoformat(value: object) -> str | None:
    """ISO-8601 string for a DB datetime/date, or ``None``."""
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        return iso()
    return str(value)


def get_filing(rcept_no: str) -> FilingDetail:
    """Fetch a single DART filing by its 14-digit ``rcept_no`` (whole body).

    Returns the ENTIRE stored ``body_md`` (Veto #8 — no chunking/slicing) wrapped
    in ``<untrusted source="dart" ref="...">…</untrusted>`` (D-03) with advisory
    ``injection_suspected`` / ``injection_flags`` metadata.

    Args:
        rcept_no: the 14-digit DART receipt number.

    Raises:
        InvalidArgument: ``rcept_no`` is not 14 ASCII digits.
        FilingNotFound: no filing row has that ``rcept_no``.
    """
    if not _RCEPT_NO_RE.match(rcept_no):
        raise InvalidArgument("rcept_no must be 14 ASCII digits")

    with get_engine().connect() as conn:
        row = conn.execute(_SELECT_FILING_SQL, {"rcept_no": rcept_no}).first()
    if row is None:
        raise FilingNotFound(f"no filing for rcept_no {rcept_no}")

    body = row.body_md  # whole body — Veto #8 (no slicing)
    flags = [h["pattern_id"] for h in injection.detect(body)]
    wrapped = injection.wrap_untrusted(body, "dart", rcept_no)
    return FilingDetail(
        rcept_no=rcept_no,
        corp_code=row.corp_code.strip(),
        title=row.report_nm,
        filed_at=_isoformat(row.filed_at),
        event_type=row.event_type,
        body_md=wrapped,
        injection_suspected=bool(flags),
        injection_flags=flags,
    )


def search_filings(
    corp_code: str,
    event_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = _DEFAULT_SEARCH_LIMIT,
) -> SearchFilingsResult:
    """Search a corp's filing metadata, newest first (``filed_at DESC``).

    Metadata only — NO body, NO injection wrap (the agent re-fetches a full body
    via :func:`get_filing` for hits it cares about). Zero matches return an empty
    :class:`SearchFilingsResult` (``hits=[]``, D-01), never an error.

    Args:
        corp_code: the 8-digit DART corp code (must resolve to a known entity).
        event_type: optional exact ``event_type`` filter (KIND classifier label).
        since: optional inclusive lower bound on ``filed_at`` (ISO-8601 string).
        until: optional exclusive upper bound on ``filed_at`` (ISO-8601 string).
        limit: max rows (D-04 default 50).

    Raises:
        InvalidArgument: ``corp_code`` is not 8 ASCII digits, or ``limit`` < 1.
        EntityNotFound: ``corp_code`` does not resolve to a known entity.
    """
    if not _CORP_CODE_RE.match(corp_code):
        raise InvalidArgument("corp_code must be 8 ASCII digits")
    if limit < 1:
        raise InvalidArgument("limit must be >= 1")

    engine = get_engine()
    if resolve_entity(engine, corp_code) is None:
        raise EntityNotFound(f"no entity for corp_code {corp_code}")

    params = {
        "corp_code": corp_code,
        "event_type": event_type,
        "since": since,
        "until": until,
        "limit": limit,
    }
    with engine.connect() as conn:
        rows = conn.execute(_SEARCH_FILINGS_SQL, params).all()

    hits = [
        FilingHit(
            rcept_no=row.rcept_no,
            corp_code=corp_code,
            title=row.report_nm,
            filed_at=_isoformat(row.filed_at),
            event_type=row.event_type,
        )
        for row in rows
    ]
    return SearchFilingsResult(corp_code=corp_code, hits=hits)


# Register on the shared mcp via the call form ``mcp.tool(...)(fn)`` rather than
# ``@mcp.tool`` decoration: the decorator REPLACES the name with a non-callable
# ``FunctionTool`` wrapper, which would break direct in-process calls (the
# analysis runner and the tests call these functions plainly). Registering by
# call leaves ``get_filing`` / ``search_filings`` as the plain callables while
# still adding them to the tool surface.
_READ_ONLY = ToolAnnotations(readOnlyHint=True)
mcp.tool(annotations=_READ_ONLY)(get_filing)
mcp.tool(annotations=_READ_ONLY)(search_filings)
