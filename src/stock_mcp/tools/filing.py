"""``get_filing`` MCP tool — full document body fetch by sha256 id (MCP-07, D-07).

Returns the complete body of a single ``documents`` row keyed on the content-hash
``id`` (sha256 of the normalized body, set by the ingest worker per D-13/D-14).
The two-step pattern mandated by the UI-SPEC means list tools (search,
get_recent_events, get_related) NEVER inline body — callers materialize body
via this tool when they need full text.

Bodies above ``BODY_TRUNCATE_AT`` (200,000 chars) are truncated; ``body_chars``
always reports the original length and ``truncated`` flags whether the returned
body was cut.

Frontmatter is read from the markdown file at ``vault_path`` (the documents
table stores body only — no JSONB frontmatter column exists). If the file is
missing or malformed, ``frontmatter`` defaults to ``{}`` rather than raising:
the tool's contract is "best-effort frontmatter, body always returned".
"""

from __future__ import annotations

import time

import sqlalchemy as sa

from db.engine import get_engine

from ..errors import ErrorCode, StructuredError, to_error_response
from ..logging import log_tool_call
from ..models import FilingResponse
from .search import mcp

__all__ = ["BODY_TRUNCATE_AT", "get_filing"]


BODY_TRUNCATE_AT = 200_000


def _read_frontmatter_dict(vault_path: str) -> dict:
    """Best-effort frontmatter read from disk. Returns ``{}`` on any error."""
    try:
        from shared.frontmatter import read_frontmatter

        fm_model, _body = read_frontmatter(vault_path)
        return fm_model.model_dump(by_alias=True, exclude_none=True)
    except Exception:  # noqa: BLE001 — defensive: never block body return on FM
        return {}


def get_filing(id: str) -> FilingResponse | dict:
    """Full body of a single vault document by content-hash id (MCP-07, JUDGE-04).

    Returns the complete body of the document keyed on ``documents.id`` (sha256
    of the normalized body, Phase 2 D-13) along with its vault path and parsed
    frontmatter. Bodies above 200,000 characters are truncated; ``body_chars``
    always reports the original length and ``truncated`` flags whether the
    returned body was cut.

    ### Behavior contract
    - ``id``: content-hash sha256 (64 hex chars) — the same id returned by
      ``search``, ``get_recent_events``, and ``get_related`` list responses.
      Two-step pattern: list tools never inline body; callers fetch full body
      via this tool.
    - No filtering or pagination. One id → one document.
    - Frontmatter is re-read from ``vault_path`` on disk (the documents table
      stores body only). If the file is missing or malformed, ``frontmatter``
      degrades to an empty dict — body is still returned.

    ### Response shape
    Returns ``FilingResponse`` with:
    - ``id``: echo of input
    - ``vault_path``: citable path under ``vault/raw/...`` (for JUDGE-04)
    - ``frontmatter``: parsed frontmatter dict (provenance + ingest_state +
      _derived); empty dict on read failure
    - ``body``: document body, truncated at 200,000 chars when oversized
    - ``body_chars``: original (pre-truncation) length
    - ``truncated``: True iff body was cut

    ### Errors
    Returns ``{"error": {"code": ..., "message": ..., "details": {...}}}`` —
    never raises. Codes:
    - ``NOT_FOUND``: id does not match any documents row.
    - ``DB_UNAVAILABLE``: Postgres unreachable.
    - ``INTERNAL``: unexpected failure (string truncated to 200 chars).

    ### Performance budget
    p95 latency < 3s. Response size up to ~50,000 tokens (single 200K-char doc);
    well below the 8k-token guard for typical filings (≤30K chars).
    """
    t0 = time.perf_counter()
    args_log = {"id": id}
    try:
        engine = get_engine()
        with engine.connect() as conn:
            row = (
                conn.execute(
                    sa.text("SELECT id, body, vault_path FROM documents WHERE id = :id"),
                    {"id": id},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise StructuredError(
                ErrorCode.NOT_FOUND,
                f"document not found: id={id[:16]}...",
                details={"id": id},
            )
        body = row["body"] or ""
        body_chars = len(body)
        truncated = body_chars > BODY_TRUNCATE_AT
        if truncated:
            body = body[:BODY_TRUNCATE_AT]
        frontmatter = _read_frontmatter_dict(row["vault_path"])
        result = FilingResponse(
            id=row["id"],
            vault_path=row["vault_path"],
            frontmatter=frontmatter,
            body=body,
            body_chars=body_chars,
            truncated=truncated,
        )
        latency = int((time.perf_counter() - t0) * 1000)
        log_tool_call("get_filing", args_log, latency, len(result.model_dump_json()) // 4)
        return result
    except StructuredError as e:
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(e)
        log_tool_call("get_filing", args_log, latency, 0, error=err["error"])
        return err
    except Exception as e:  # noqa: BLE001 — D-21 catch-all
        wrapped = StructuredError(ErrorCode.INTERNAL, str(e)[:200])
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(wrapped)
        log_tool_call("get_filing", args_log, latency, 0, error=err["error"])
        return err


mcp.tool()(get_filing)
