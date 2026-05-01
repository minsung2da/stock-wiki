"""Tests for the ``get_related`` MCP tool (Plan 06-05 Task 1, MCP-06/D-06)."""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from stock_mcp.tools.related import get_related


def _first_dart_doc_ids(engine: Engine, n: int = 4) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text("SELECT id FROM documents WHERE source = 'dart' ORDER BY id LIMIT :n"),
            {"n": n},
        ).all()
    return [r.id for r in rows]


def test_get_related_depth1_returns_direct_neighbors(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    engine, _vault_root, _repo_root = mcp_vault_engine
    _ = engine
    src_id = _first_dart_doc_ids(engine, 4)[0]

    result = get_related(document_id=src_id, depth=1)

    assert hasattr(result, "related"), f"unexpected error: {result!r}"
    # Conftest seeds at least 2 direct edges from ids[0] (ids[0]->ids[1] mentions,
    # ids[0]->ids[2] references).
    assert len(result.related) >= 2
    for row in result.related:
        assert row.depth == 1
        assert row.edge_type in {"mentions", "references", "supersedes"}
        assert isinstance(row.id, str) and len(row.id) > 0


def test_get_related_depth2_includes_two_hop(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    engine, _vault_root, _repo_root = mcp_vault_engine
    _ = engine
    src_id = _first_dart_doc_ids(engine, 4)[0]

    result = get_related(document_id=src_id, depth=2)

    assert hasattr(result, "related"), f"unexpected error: {result!r}"
    depths = {r.depth for r in result.related}
    # Conftest seeds ids[0]->ids[1] (depth=1) and ids[1]->ids[3] (depth=2 via ids[0]).
    assert 1 in depths
    assert 2 in depths


def test_get_related_clamps_depth_to_2(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    engine, _vault_root, _repo_root = mcp_vault_engine
    _ = engine
    src_id = _first_dart_doc_ids(engine, 4)[0]

    result = get_related(document_id=src_id, depth=5)

    assert hasattr(result, "related")
    max_depth = max((r.depth for r in result.related), default=0)
    assert max_depth <= 2


def test_get_related_unknown_document_returns_not_found(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    engine, _vault_root, _repo_root = mcp_vault_engine
    _ = engine

    result = get_related(document_id="0" * 64, depth=1)

    assert isinstance(result, dict), f"expected error envelope, got {result!r}"
    assert result["error"]["code"] == "NOT_FOUND"


def test_get_related_handles_cycles_without_infinite_loop(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    """Insert a cycle A->B + B->A (additional to existing seeded edges) and
    confirm get_related returns finite results bounded by depth, no recursion error."""
    engine, _vault_root, _repo_root = mcp_vault_engine
    ids = _first_dart_doc_ids(engine, 4)
    a, b = ids[0], ids[1]

    # Insert reverse edge B->A. ids[0]->ids[1] mentions is already seeded.
    cycle_inserted = False
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO edges (src_type, src_id, dst_type, dst_id, edge_type) "
                    "VALUES ('document', :src, 'document', :dst, 'mentions') "
                    "ON CONFLICT ON CONSTRAINT uq_edge_endpoints DO NOTHING"
                ),
                {"src": b, "dst": a},
            )
            cycle_inserted = True

        # depth=2 traversal must terminate.
        result = get_related(document_id=a, depth=2)
        assert hasattr(result, "related"), f"unexpected error: {result!r}"
        # All depths bounded.
        assert all(r.depth <= 2 for r in result.related)
        # Defensive cap (at most 100).
        assert len(result.related) <= 100
    finally:
        if cycle_inserted:
            with engine.begin() as conn:
                conn.execute(
                    sa.text(
                        "DELETE FROM edges WHERE src_type='document' AND src_id=:src "
                        "AND dst_type='document' AND dst_id=:dst AND edge_type='mentions'"
                    ),
                    {"src": b, "dst": a},
                )


def test_get_related_includes_snippet_and_vault_path_for_documents(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    engine, _vault_root, _repo_root = mcp_vault_engine
    _ = engine
    src_id = _first_dart_doc_ids(engine, 4)[0]

    result = get_related(document_id=src_id, depth=1)

    assert hasattr(result, "related")
    assert len(result.related) >= 1
    for row in result.related:
        # All seeded neighbors are documents; snippet + vault_path must be set.
        assert row.vault_path is not None
        assert row.snippet_200ch is not None
        assert "<vault_excerpt>" in row.snippet_200ch


def test_get_related_docstring_has_four_sections(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    _ = mcp_vault_engine
    doc = get_related.__doc__ or ""
    for section in (
        "### Behavior contract",
        "### Response shape",
        "### Errors",
        "### Performance budget",
    ):
        assert section in doc, f"missing docstring section: {section}"
