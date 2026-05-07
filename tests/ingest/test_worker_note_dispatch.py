"""Phase 8 Plan 04 Task 1 — worker.py private_note dispatch test.

Verifies that ``process_document`` (or ``ingest_run``) routes
``notes/private/**/*.md`` files through the parse_note path and INSERTs
documents rows with source='private_note', note_type=<frontmatter type>.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter as pyfm
import pytest
import sqlalchemy as sa


class _StubEmbedder:
    def encode(self, texts):
        return [[0.0] * 1024 for _ in texts]


def _write_thesis(path: Path, *, tickers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "type": "thesis",
        "tickers": tickers,
        "tags": ["semiconductor"],
        "created": "2026-05-06T15:00:00+09:00",
        "updated": "2026-05-06T15:00:00+09:00",
        "author": "yamin",
        "kill_criteria": ["HBM 수요 둔화"],
        "conviction": "high",
        "target_price": 95000,
    }
    post = pyfm.Post("# 삼성전자 Thesis\nHBM 수요 견조. 매수.\n")
    post.metadata = meta
    path.write_text(pyfm.dumps(post), encoding="utf-8")


def test_private_note_inserts_with_note_type(pg_clean, tmp_path: Path, monkeypatch) -> None:
    """notes/private/<ticker>/thesis.md → documents row with source='private_note', note_type='thesis'."""
    # Stub embedder import so bge-m3 doesn't load.
    from ingest import worker as worker_mod

    monkeypatch.setattr(worker_mod, "Embedder", _StubEmbedder)

    note_path = tmp_path / "notes" / "private" / "005930" / "thesis.md"
    _write_thesis(note_path, tickers=["005930"])

    # Need at least one ingestible doc — but ingest_run scans <vault_root>/raw.
    # We need worker to scan notes/private too. Put a sentinel raw doc to verify
    # ingest still runs cleanly even with no raw files.
    (tmp_path / "raw").mkdir(exist_ok=True)

    worker_mod.ingest_run(vault_root=tmp_path, engine=pg_clean, embedder=_StubEmbedder())

    # Now verify a private_note row exists.
    with pg_clean.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT vault_path, source, note_type FROM documents "
                "WHERE source = 'private_note'"
            )
        ).all()
    assert len(rows) == 1, f"expected 1 private_note row, got {len(rows)}"
    row = rows[0]
    assert row.note_type == "thesis"
    assert "notes/private/005930/thesis.md" in row.vault_path
