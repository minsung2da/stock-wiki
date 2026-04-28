"""Smoke test for the session-scoped mcp_vault_engine fixture (Plan 06-03 Task 3).

Verifies that downstream Plans 06-04..06-09 can rely on the fixture having
ingested the corpus, seeded edges, and recorded ingest_runs.
"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import Engine


def test_session_fixture_yields_engine_with_documents(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    engine, vault_root, repo_root = mcp_vault_engine

    # Tree layout sanity.
    assert vault_root.is_dir(), f"vault_root missing: {vault_root}"
    assert (repo_root / "notes" / "private" / "portfolio.md").exists()

    with engine.connect() as conn:
        n_docs = conn.execute(sa.text("SELECT COUNT(*) FROM documents")).scalar_one()
        n_corp = conn.execute(
            sa.text("SELECT COUNT(DISTINCT corp_code) FROM documents WHERE corp_code IS NOT NULL")
        ).scalar_one()
        n_edges = conn.execute(sa.text("SELECT COUNT(*) FROM edges")).scalar_one()
        n_runs = conn.execute(sa.text("SELECT COUNT(*) FROM ingest_runs")).scalar_one()

    assert n_docs >= 90, f"expected ≥90 documents, got {n_docs}"
    assert n_corp >= 5, f"expected ≥5 distinct corp_codes, got {n_corp}"
    assert n_edges >= 2, f"expected ≥2 edges, got {n_edges}"
    assert n_runs >= 5, f"expected ≥5 ingest_runs rows, got {n_runs}"
