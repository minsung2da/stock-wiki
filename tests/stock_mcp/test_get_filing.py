"""Tests for the ``get_filing`` MCP tool (Plan 06-04 Task 1, MCP-07/D-07)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from stock_mcp.tools.filing import BODY_TRUNCATE_AT, get_filing


def _first_doc(engine: Engine) -> tuple[str, str, str]:
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT id, vault_path, body FROM documents "
                "WHERE source = 'dart' ORDER BY id LIMIT 1"
            )
        ).first()
    assert row is not None, "fixture must contain at least one DART document"
    return row.id, row.vault_path, row.body


def test_get_filing_returns_full_body(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    engine, _vault_root, _repo_root = mcp_vault_engine
    doc_id, vault_path, body = _first_doc(engine)

    result = get_filing(id=doc_id)

    # Not an error envelope.
    assert hasattr(result, "id"), f"unexpected error response: {result!r}"
    assert result.id == doc_id
    assert result.vault_path == vault_path
    assert isinstance(result.frontmatter, dict)
    assert "provenance" in result.frontmatter
    assert result.body == body
    assert result.body_chars == len(body)
    assert result.truncated is False


def test_get_filing_unknown_id_returns_not_found(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    engine, _vault_root, _repo_root = mcp_vault_engine  # ensure fixture spun up
    _ = engine

    result = get_filing(id="0" * 64)

    assert isinstance(result, dict), f"expected error envelope, got {result!r}"
    assert result["error"]["code"] == "NOT_FOUND"


def test_get_filing_garbage_id_returns_not_found(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    engine, _vault_root, _repo_root = mcp_vault_engine
    _ = engine

    result = get_filing(id="not-a-sha256")

    assert isinstance(result, dict)
    assert result["error"]["code"] == "NOT_FOUND"


def test_get_filing_truncates_oversize_body(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    engine, _vault_root, _repo_root = mcp_vault_engine
    big_body = "x" * (BODY_TRUNCATE_AT + 50_000)
    big_id = hashlib.sha256(b"oversize-fixture-doc").hexdigest()

    # Insert a synthetic oversize doc directly. Use a vault_path under repo_root
    # so any later reader could find it; we don't need an on-disk file because
    # get_filing reads body from the DB and only frontmatter from disk (best
    # effort — missing frontmatter file just yields {}).
    fake_vault_path = str(_repo_root / "vault" / "raw" / "synthetic" / f"{big_id}.md")
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO documents (id, body, source, vault_path) "
                    "VALUES (:id, :body, :source, :vp)"
                ),
                {"id": big_id, "body": big_body, "source": "dart", "vp": fake_vault_path},
            )

        result = get_filing(id=big_id)
        assert hasattr(result, "id"), f"unexpected error: {result!r}"
        assert result.truncated is True
        assert result.body_chars == len(big_body)
        assert len(result.body) == BODY_TRUNCATE_AT
    finally:
        with engine.begin() as conn:
            conn.execute(
                sa.text("DELETE FROM documents WHERE id = :id"),
                {"id": big_id},
            )


def test_get_filing_docstring_has_four_sections(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    _ = mcp_vault_engine  # fixture not strictly required, but keeps test cohesion
    doc = get_filing.__doc__ or ""
    for section in (
        "### Behavior contract",
        "### Response shape",
        "### Errors",
        "### Performance budget",
    ):
        assert section in doc, f"missing docstring section: {section}"
