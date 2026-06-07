"""notes-ingest + narrative backfill DB tests — Plan 03-02 Task 2 (D-05).

Live-Postgres (`@pytest.mark.db`) against the session testcontainer. A
deterministic stub embedder (constant 1024-d vector) replaces bge-m3 so the
test never downloads the model. Uses the shared ``seeded_engine`` fixture
(삼성전자 / 00126380 / 005930 pre-seeded) for the filings FK.

Contracts asserted:
- ``ingest_notes`` writes a ``notes`` row with non-NULL content_emb + bm25_tokens
  + body_tsv, stores whole content_md verbatim (Veto #8), excludes portfolio.md,
  and records a ``notes_ingest`` collector_runs row.
- ``backfill_narrative`` fills a NULL filings body_embedding/bm25_tokens/body_tsv.
- re-ingest of an unchanged note is idempotent ("skipped").
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from collectors.notes_ingest import ingest_notes
from collectors.notes_ingest.backfill import backfill_narrative

pytestmark = pytest.mark.db


class _StubEmbedder:
    """Deterministic embedder — returns a constant non-zero 1024-d vector per text.

    Avoids the ~2GB bge-m3 download. The vector is non-zero so the halfvec column
    is unambiguously non-NULL and a CAST AS halfvec succeeds.
    """

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[0.01] * 1024 for _ in texts]


def _write_note(repo_root: Path, rel: str, body: str) -> Path:
    p = repo_root / "notes" / "private" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _seed_portfolio(repo_root: Path) -> None:
    """portfolio.md must be EXCLUDED from ingest (it is config, not a memo)."""
    p = repo_root / "notes" / "private" / "portfolio.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        '---\nholdings:\n  - ticker: "005930"\n    qty: 1\n    avg_cost: 70000\n---\n# Portfolio\n',
        encoding="utf-8",
    )


# ----- ingest_notes -----


def test_ingest_notes_writes_row_with_embedding_and_tokens(seeded_engine, tmp_path: Path):
    body = "# 삼성전자 thesis\n\n반도체 영업이익 개선 전망. 메모 본문 전체 저장.\n"
    _write_note(tmp_path, "samsung.md", body)
    _seed_portfolio(tmp_path)

    stats = ingest_notes(engine=seeded_engine, repo_root=tmp_path, embedder=_StubEmbedder())

    # portfolio.md excluded → exactly one memo ingested.
    assert stats["total"] == 1
    assert stats["inserted"] == 1
    assert stats["failed"] == []

    with seeded_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT path, content_md, content_emb, bm25_tokens, body_tsv, content_hash "
                "FROM notes WHERE path = :p"
            ),
            {"p": "notes/private/samsung.md"},
        ).first()
    assert row is not None
    # Whole content_md verbatim — Veto #8 (no chunking/slicing).
    assert row.content_md == body
    assert row.content_emb is not None
    assert row.bm25_tokens is not None and len(row.bm25_tokens) > 0
    assert row.body_tsv is not None
    assert len(row.content_hash) == 64


def test_ingest_notes_records_collector_run(seeded_engine, tmp_path: Path):
    _write_note(tmp_path, "note.md", "# memo\n\n삼성전자 메모\n")
    ingest_notes(engine=seeded_engine, repo_root=tmp_path, embedder=_StubEmbedder())

    with seeded_engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM collector_runs WHERE source = 'notes_ingest'")
        ).scalar()
    assert n == 1


def test_ingest_notes_idempotent_skip_on_unchanged(seeded_engine, tmp_path: Path):
    _write_note(tmp_path, "note.md", "# memo\n\n변경 없음 메모\n")
    first = ingest_notes(engine=seeded_engine, repo_root=tmp_path, embedder=_StubEmbedder())
    assert first["inserted"] == 1
    second = ingest_notes(engine=seeded_engine, repo_root=tmp_path, embedder=_StubEmbedder())
    assert second["skipped"] == 1
    assert second["inserted"] == 0


def test_ingest_notes_empty_dir_is_clean(seeded_engine, tmp_path: Path):
    # No notes/private dir at all → zero work, no failure.
    stats = ingest_notes(engine=seeded_engine, repo_root=tmp_path, embedder=_StubEmbedder())
    assert stats["total"] == 0
    assert stats["failed"] == []


# ----- backfill_narrative -----


def _insert_null_filing(engine, rcept_no: str, body: str) -> None:
    """Insert a filings row with NULL body_embedding/bm25_tokens (Phase 1 state)."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO filings "
                "(rcept_no, corp_code, ticker, filed_at, report_nm, pblntf_ty, "
                " source_url, content_hash, body_md, fetched_at) "
                "VALUES (:r, '00126380', '005930', :f, :nm, 'A', :url, :h, :body, now())"
            ),
            {
                "r": rcept_no,
                "f": datetime(2026, 5, 20, 15, 30, tzinfo=ZoneInfo("Asia/Seoul")),
                "nm": "분기보고서",
                "url": f"https://dart.fss.or.kr/x?rcpNo={rcept_no}",
                "h": "0" * 64,
                "body": body,
            },
        )


def test_backfill_narrative_fills_null_filing_embedding(seeded_engine):
    rcept_no = "20260520000001"
    _insert_null_filing(seeded_engine, rcept_no, "# 분기보고서\n\n삼성전자 영업이익 증가.\n")

    # Precondition: embedding/tokens NULL.
    with seeded_engine.connect() as conn:
        pre = conn.execute(
            text("SELECT body_embedding, bm25_tokens FROM filings WHERE rcept_no = :r"),
            {"r": rcept_no},
        ).first()
    assert pre.body_embedding is None
    assert pre.bm25_tokens is None

    stats = backfill_narrative(engine=seeded_engine, embedder=_StubEmbedder())
    assert stats["filings_updated"] == 1
    assert stats["total_updated"] == 1

    with seeded_engine.connect() as conn:
        post = conn.execute(
            text("SELECT body_embedding, bm25_tokens, body_tsv FROM filings WHERE rcept_no = :r"),
            {"r": rcept_no},
        ).first()
    assert post.body_embedding is not None
    assert post.bm25_tokens is not None and len(post.bm25_tokens) > 0
    assert post.body_tsv is not None


def test_backfill_narrative_noop_when_nothing_null(seeded_engine):
    # No filings/news rows at all → zero updates, no error.
    stats = backfill_narrative(engine=seeded_engine, embedder=_StubEmbedder())
    assert stats["total_updated"] == 0
