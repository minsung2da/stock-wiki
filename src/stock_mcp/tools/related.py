"""``get_related`` MCP tool — bounded BFS over the edges graph (MCP-06, D-06).

Walks ``edges`` rows whose source is a given document_id and returns the
reachable neighbors (document or non-document endpoints) up to ``depth`` hops
away — depth is hard-clamped to 2 to keep the recursive CTE bounded and the
response under the per-tool token budget.

Two-step pattern (D-08): each ``RelatedRow`` carries an ``id`` + a 200-char
``<vault_excerpt>``-wrapped snippet (when the destination is a document with
an ingested body); callers materialize the full body via
``get_filing(id=...)``. Non-document destinations (e.g. ticker nodes) return
``vault_path=None`` and ``snippet_200ch=None``.

Cycle safety: the recursive CTE uses ``UNION`` (not ``UNION ALL``) which
de-dupes (dst_type, dst_id, edge_type, depth) tuples — combined with the
hard depth cap this prevents infinite recursion on cyclic subgraphs (T-6-05-01).
"""

from __future__ import annotations

import time
from pathlib import Path

import sqlalchemy as sa

from db.engine import get_engine

from ..errors import ErrorCode, StructuredError, to_error_response
from ..logging import log_tool_call
from ..models import RelatedRow, RelatedSet
from ..snippets import build_snippet
from .search import mcp

__all__ = ["MAX_DEPTH", "RELATED_LIMIT", "get_related"]


MAX_DEPTH = 2  # Hard cap (T-6-05-01 DoS mitigation)
RELATED_LIMIT = 100  # Defensive response-row guard


def _read_disk_frontmatter(vault_path: str) -> dict:
    """Best-effort frontmatter read. Returns {} if file missing/malformed."""
    try:
        if not Path(vault_path).exists():
            return {}
        from shared.frontmatter import read_frontmatter

        fm_model, _body = read_frontmatter(vault_path)
        return fm_model.model_dump(by_alias=True, exclude_none=True)
    except Exception:  # noqa: BLE001 — defensive
        return {}


def get_related(document_id: str, depth: int = 1) -> RelatedSet | dict:
    """Walk the edges graph from a document up to ``depth`` hops (MCP-06, JUDGE-04).

    Returns up to 100 ``RelatedRow`` rows reachable from the given document_id
    via the ``edges`` table. Depth is hard-clamped to 2 — values > 2 silently
    fall back to 2; values < 1 fall back to 1. Recursive CTE with ``UNION``
    de-duplicates traversal so cyclic subgraphs (A→B→A) terminate cleanly.

    ### Behavior contract
    - ``document_id``: sha256 hex of a row in ``documents``. If no such row
      exists, returns ``NOT_FOUND``.
    - ``depth``: number of BFS hops; clamped to ``max(1, min(depth, 2))``.
    - Edge selection: any row in ``edges`` where ``(src_type, src_id) ==
      ('document', document_id)`` for the seed step; subsequent hops follow
      ``(src_type, src_id) == (prev.dst_type, prev.dst_id)``.
    - Result rows: when the destination is a document with an ingested body,
      ``vault_path`` and ``snippet_200ch`` are populated; otherwise both are
      None (the caller can still inspect ``id`` + ``edge_type`` + ``depth``).
    - Two-step pattern (D-08): rows never inline body. Use ``get_filing`` to
      materialize.

    ### Response shape
    Returns ``RelatedSet`` with:
    - ``related``: list of ``RelatedRow`` ordered by ``depth`` ASC, then
      ``edge_type`` ASC, then ``id`` ASC. Each row carries ``id``,
      ``edge_type``, ``depth`` (1 or 2), ``vault_path`` (or None) and
      ``snippet_200ch`` (or None).
    - ``truncation_applied``: list of human-readable notes (``"depth-clamped
      to 2"``, ``"100-row cap"``).

    ### Errors
    Returns ``{"error": {"code": ..., "message": ..., "details": {...}}}`` —
    never raises. Codes:
    - ``NOT_FOUND``: ``document_id`` does not match any documents row.
    - ``DB_UNAVAILABLE``: Postgres unreachable.
    - ``INTERNAL``: unexpected failure (string truncated to 200 chars).

    ### Performance budget
    p95 latency < 2s. Response < 8k tokens at 100 rows × 200-char snippets.
    DoS mitigation: depth ≤ 2, response ≤ 100 rows (T-6-05-01).
    """
    t0 = time.perf_counter()
    args_log = {"document_id": document_id, "depth": depth}
    truncation: list[str] = []
    try:
        # Clamp depth to [1, 2] (T-6-05-01).
        max_depth = max(1, min(depth, 2))
        if depth > MAX_DEPTH:
            truncation.append("depth-clamped to 2")

        engine = get_engine()
        with engine.connect() as conn:
            # Pre-flight: confirm document exists.
            existed = conn.execute(
                sa.text("SELECT 1 FROM documents WHERE id = :id"),
                {"id": document_id},
            ).first()
            if existed is None:
                raise StructuredError(
                    ErrorCode.NOT_FOUND,
                    f"document not found: id={document_id[:16]}...",
                    details={"document_id": document_id},
                )

            rows = (
                conn.execute(
                    sa.text(
                        """
                        WITH RECURSIVE related AS (
                            SELECT dst_type, dst_id, edge_type, 1 AS depth
                            FROM edges
                            WHERE src_type = 'document' AND src_id = :doc_id
                            UNION
                            SELECT e.dst_type, e.dst_id, e.edge_type, r.depth + 1
                            FROM edges e
                            JOIN related r ON e.src_type = r.dst_type
                                          AND e.src_id = r.dst_id
                            WHERE r.depth < :max_depth
                        )
                        SELECT r.dst_type, r.dst_id, r.edge_type, r.depth,
                               d.vault_path, d.body
                        FROM related r
                        LEFT JOIN documents d
                          ON r.dst_type = 'document' AND r.dst_id = d.id
                        ORDER BY r.depth, r.edge_type, r.dst_id
                        """
                    ),
                    {"doc_id": document_id, "max_depth": max_depth},
                )
                .mappings()
                .all()
            )

        related_rows: list[RelatedRow] = []
        for row in rows:
            is_doc = row["dst_type"] == "document"
            vault_path = row["vault_path"] if is_doc else None
            body = row["body"] if is_doc else None
            snippet: str | None = None
            if is_doc and body is not None and vault_path is not None:
                fm = _read_disk_frontmatter(vault_path)
                derived = fm.get("_derived") or fm.get("derived") or {}
                summary = derived.get("summary")
                snippet = build_snippet(body, summary)
            related_rows.append(
                RelatedRow(
                    id=row["dst_id"],
                    edge_type=row["edge_type"],
                    depth=int(row["depth"]),
                    vault_path=vault_path,
                    snippet_200ch=snippet,
                )
            )

        # Defensive cap (T-6-05-01).
        if len(related_rows) > RELATED_LIMIT:
            related_rows = related_rows[:RELATED_LIMIT]
            truncation.append(f"{RELATED_LIMIT}-row cap")

        result = RelatedSet(related=related_rows, truncation_applied=truncation)
        latency = int((time.perf_counter() - t0) * 1000)
        log_tool_call(
            "get_related",
            args_log,
            latency,
            len(result.model_dump_json()) // 4,
        )
        return result
    except StructuredError as e:
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(e)
        log_tool_call("get_related", args_log, latency, 0, error=err["error"])
        return err
    except Exception as e:  # noqa: BLE001 — D-21 catch-all
        wrapped = StructuredError(ErrorCode.INTERNAL, str(e)[:200])
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(wrapped)
        log_tool_call("get_related", args_log, latency, 0, error=err["error"])
        return err


mcp.tool()(get_related)
