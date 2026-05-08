"""Phase 8 Plan 04 Task 2 — NOTE-03 E2E.

Verifies the full pipeline: thesis written under ``notes/private/<ticker>/``
→ ingest_run cycle → search() returns the vault_path. Frontmatter fields
(tickers/tags/created/author) survive into the documents row, invalid thesis
still indexes the body but records ``note_schema_violation`` review_flag.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter as pyfm
import pytest
import sqlalchemy as sa


class _FakeEmbedder:
    dim = 1024

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self.dim for _ in texts]


def _fake_tokenize_ko(text: str) -> list[int]:
    if not text:
        return [0]
    return [ord(c) & 0x7FFFFFFF for c in text[:64]]


@pytest.fixture
def stub_embedder(monkeypatch):
    """Patch worker.Embedder + tokenize_ko + chunking._get_tok so bge-m3/mecab don't load."""
    from ingest import chunking as chunking_mod
    from ingest import worker as worker_mod

    class _DummyTok:
        def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:  # noqa: ARG002
            return list(range(len(text)))

        def decode(self, ids: list[int]) -> str:
            return " ".join(str(i) for i in ids)

    monkeypatch.setattr(worker_mod, "Embedder", lambda *a, **kw: _FakeEmbedder())
    monkeypatch.setattr(worker_mod, "tokenize_ko", _fake_tokenize_ko)
    monkeypatch.setattr(chunking_mod, "_get_tok", lambda: _DummyTok())
    return _FakeEmbedder()


def _write_thesis(repo_root: Path, ticker: str, body: str, *, conviction: str = "high") -> Path:
    notes_dir = repo_root / "notes" / "private" / ticker
    notes_dir.mkdir(parents=True, exist_ok=True)
    p = notes_dir / "thesis.md"
    meta = {
        "type": "thesis",
        "tickers": [ticker],
        "tags": ["semiconductor"],
        "created": "2026-05-06T15:00:00+09:00",
        "updated": "2026-05-06T15:00:00+09:00",
        "author": "yamin",
        "kill_criteria": ["HBM 수요 둔화"],
        "conviction": conviction,
        "target_price": 95000,
    }
    post = pyfm.Post(body)
    post.metadata = meta
    p.write_text(pyfm.dumps(post), encoding="utf-8")
    return p


def _write_journal(repo_root: Path, date_slug: str, body: str) -> Path:
    p = repo_root / "notes" / "private" / "journal" / f"{date_slug}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "type": "journal",
        "tickers": [],
        "tags": ["decision"],
        "author": "yamin",
        "created": "2026-05-06T15:00:00+09:00",
        "updated": "2026-05-06T15:00:00+09:00",
    }
    post = pyfm.Post(body)
    post.metadata = meta
    p.write_text(pyfm.dumps(post), encoding="utf-8")
    return p


def test_thesis_appears_in_search(pg_clean, tmp_path: Path, stub_embedder) -> None:
    """End-to-end: thesis written → ingest_run → search returns it."""
    from ingest import worker as worker_mod

    body = "# 삼성전자 Thesis\nHBM 수요 견조 — 매수 논거.\n"
    note_path = _write_thesis(tmp_path, "005930", body)
    (tmp_path / "raw").mkdir(exist_ok=True)

    worker_mod.ingest_run(vault_root=tmp_path, engine=pg_clean, embedder=stub_embedder)

    # Verify documents row landed.
    with pg_clean.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT vault_path, source, note_type FROM documents "
                "WHERE source = 'private_note'"
            )
        ).first()
    assert row is not None, "thesis should have created a documents row"
    assert row.note_type == "thesis"
    assert str(note_path) == row.vault_path or str(note_path).endswith(row.vault_path) or row.vault_path.endswith(str(note_path))

    # Verify chunks are in place (body was indexed).
    with pg_clean.connect() as conn:
        chunk_count = conn.execute(
            sa.text(
                "SELECT count(*) FROM chunks c JOIN documents d ON d.id = c.document_id "
                "WHERE d.source = 'private_note'"
            )
        ).scalar()
    assert chunk_count is not None and chunk_count >= 1, "thesis body must yield ≥1 chunk"


def test_thesis_frontmatter_indexed(pg_clean, tmp_path: Path, stub_embedder) -> None:
    """note_type column reflects frontmatter type; row source = private_note."""
    from ingest import worker as worker_mod

    note_path = _write_thesis(tmp_path, "005930", "# Thesis\n매수 논거.\n")
    (tmp_path / "raw").mkdir(exist_ok=True)

    worker_mod.ingest_run(vault_root=tmp_path, engine=pg_clean, embedder=stub_embedder)

    with pg_clean.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT note_type, source, vault_path FROM documents "
                "WHERE vault_path = :vp"
            ),
            {"vp": str(note_path)},
        ).first()
    assert row is not None
    assert row.source == "private_note"
    assert row.note_type == "thesis"


def test_invalid_thesis_still_indexed_with_review_flag(pg_clean, tmp_path: Path, stub_embedder) -> None:
    """conviction='extreme' (invalid Literal) → ingest still inserts; review_flag recorded."""
    from ingest import worker as worker_mod
    from ingest.parsers.note import parse_note

    note_path = _write_thesis(tmp_path, "005930", "본문 텍스트.", conviction="extreme")
    (tmp_path / "raw").mkdir(exist_ok=True)

    # Confirm parse_note records the review_flag (sanity).
    parsed = parse_note(note_path)
    assert "note_schema_violation" in parsed.review_flags

    # ingest_run must NOT raise.
    worker_mod.ingest_run(vault_root=tmp_path, engine=pg_clean, embedder=stub_embedder)

    with pg_clean.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT id, source, note_type FROM documents WHERE vault_path = :vp"
            ),
            {"vp": str(note_path)},
        ).first()
    assert row is not None, "invalid thesis must still be indexed (D-15 fail-soft)"
    assert row.source == "private_note"
    # note_type still equals the dispatched type even when validation fails.
    assert row.note_type == "thesis"


def test_thesis_indexed_with_production_layout(pg_clean, tmp_path: Path, stub_embedder) -> None:
    """Regression guard (Phase 8 gap fix 2026-05-08) — vault and notes split.

    Previously ingest_run derived ``private_root = vault_root / "notes" / "private"``
    which silently broke production where ``vault_root="vault"`` (collectors) but
    user memos live at repo-root ``notes/private/``. The original E2E tests
    masked this by using a single ``tmp_path`` as both vault_root and repo_root.
    This test forces the production split: ``<repo>/vault/`` for raw data,
    ``<repo>/notes/private/`` for memos. With the fix, the worker must auto-
    discover the repo-root notes directory via ``vault_root.parent``.
    """
    from ingest import worker as worker_mod

    repo_root = tmp_path
    vault_root = repo_root / "vault"
    (vault_root / "raw").mkdir(parents=True)

    notes_dir = repo_root / "notes" / "private" / "005930"
    notes_dir.mkdir(parents=True)
    note_path = notes_dir / "thesis.md"
    meta = {
        "type": "thesis",
        "tickers": ["005930"],
        "tags": ["semiconductor"],
        "created": "2026-05-08T00:00:00+09:00",
        "updated": "2026-05-08T00:00:00+09:00",
        "author": "yamin",
        "kill_criteria": ["HBM 둔화"],
        "conviction": "high",
        "target_price": 95000,
    }
    post = pyfm.Post("# Thesis\n매수 논거: HBM.\n")
    post.metadata = meta
    note_path.write_text(pyfm.dumps(post), encoding="utf-8")

    # No explicit notes_root — worker must auto-detect via vault_root.parent.
    worker_mod.ingest_run(vault_root=vault_root, engine=pg_clean, embedder=stub_embedder)

    with pg_clean.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT note_type, source FROM documents WHERE source='private_note'"
            )
        ).first()
    assert row is not None, (
        "thesis at repo-root notes/private must be discovered via vault_root.parent fallback"
    )
    assert row.note_type == "thesis"


def test_explicit_notes_root_overrides_autodetect(pg_clean, tmp_path: Path, stub_embedder) -> None:
    """Explicit notes_root parameter wins over auto-detection."""
    from ingest import worker as worker_mod

    vault_root = tmp_path / "vault"
    (vault_root / "raw").mkdir(parents=True)
    # Decoy thesis under vault/notes/private (would be auto-discovered if not overridden)
    decoy_dir = vault_root / "notes" / "private" / "005930"
    decoy_dir.mkdir(parents=True)
    decoy = decoy_dir / "thesis.md"
    meta = {"type": "thesis", "tickers": ["005930"], "created": "2026-05-08T00:00:00+09:00"}
    post = pyfm.Post("decoy")
    post.metadata = meta
    decoy.write_text(pyfm.dumps(post), encoding="utf-8")

    # Real thesis at custom path
    real_dir = tmp_path / "alt-notes" / "005930"
    real_dir.mkdir(parents=True)
    real = real_dir / "thesis.md"
    real_meta = {**meta, "tags": ["custom-path"]}
    post2 = pyfm.Post("real")
    post2.metadata = real_meta
    real.write_text(pyfm.dumps(post2), encoding="utf-8")

    worker_mod.ingest_run(
        vault_root=vault_root,
        notes_root=tmp_path / "alt-notes",
        engine=pg_clean,
        embedder=stub_embedder,
    )

    with pg_clean.connect() as conn:
        rows = conn.execute(
            sa.text("SELECT vault_path FROM documents WHERE source='private_note'")
        ).fetchall()
    paths = [r.vault_path for r in rows]
    assert any("alt-notes" in p for p in paths), "explicit notes_root must be scanned"
    assert not any("vault/notes" in p for p in paths), "decoy under vault/notes must NOT be scanned when explicit notes_root given"


def test_journal_indexed(pg_clean, tmp_path: Path, stub_embedder) -> None:
    """notes/private/journal/<date>.md → indexed with note_type='journal'."""
    from ingest import worker as worker_mod

    body = "# 2026-05-06 의사결정\n오늘은 매수 보류.\n"
    note_path = _write_journal(tmp_path, "2026-05-06", body)
    (tmp_path / "raw").mkdir(exist_ok=True)

    worker_mod.ingest_run(vault_root=tmp_path, engine=pg_clean, embedder=stub_embedder)

    with pg_clean.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT note_type, body FROM documents WHERE vault_path = :vp"
            ),
            {"vp": str(note_path)},
        ).first()
    assert row is not None
    assert row.note_type == "journal"
    assert "의사결정" in row.body
