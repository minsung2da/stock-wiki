"""Tests for ``ingest.rebuild`` (Phase 3 Plan 06 — Task 1; STORE-05, D-25/28/29).

* R0 snapshot of empty DB returns zeros
* R1 dry-run prints plan and does NOT touch DB
* R2 TTY + no --yes + user 'n' -> aborted
* R3 TTY + no --yes + user 'y' -> proceeds
* R4 --yes skips prompt regardless of TTY
* R5 downgrade('base') then upgrade('head') both called (D-25 order)
* R6 programmatic == CLI result shape
* R7 idempotence: ingest_run -> snapshot -> rebuild -> snapshot yields identical
    document ids + chunk counts per document (embedding values allowed to vary)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from ingest import rebuild as rebuild_mod
from ingest import worker as worker_mod
from shared.frontmatter import FrontMatter, ProvenanceBlock, write_frontmatter

# ---------- Fakes shared with test_ingest_worker.py ----------


class _FakeEmbedder:
    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self.dim for _ in texts]


def _fake_tokenize_ko(text: str) -> list[int]:
    if not text:
        return [0]
    return [ord(c) & 0x7FFFFFFF for c in text[:16]]


class _DummyTok:
    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:  # noqa: ARG002
        return list(range(len(text)))

    def decode(self, ids: list[int]) -> str:
        return " ".join(str(i) for i in ids)


@pytest.fixture
def fast_env(monkeypatch: pytest.MonkeyPatch):
    tok = _DummyTok()
    monkeypatch.setattr("ingest.chunking._get_tok", lambda: tok)
    fake_emb = _FakeEmbedder()
    monkeypatch.setattr(worker_mod, "Embedder", lambda *a, **kw: fake_emb)
    monkeypatch.setattr(worker_mod, "tokenize_ko", _fake_tokenize_ko)
    return fake_emb


def _seed_vault_doc(vault_root: Path, rcept_no: str, body: str) -> Path:
    year = "2026"
    path = vault_root / "raw" / "dart" / year / f"{rcept_no}_00126380.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = FrontMatter(
        provenance=ProvenanceBlock(
            source="dart",
            source_id=rcept_no,
            source_url=f"https://example.invalid/{rcept_no}",
            date="2026-04-17",
            fetched_at=datetime.now(UTC),
            content_hash="deadbeef",
            corp_code="00126380",
            ticker="005930",
            lang="ko",
            trust_level="trusted",
        )
    )
    write_frontmatter(str(path), fm, body)
    return path


# ---------- R0: snapshot ----------


def test_R0_snapshot_of_empty_db(pg_clean: Engine) -> None:
    snap = rebuild_mod.snapshot_db(pg_clean)
    assert snap == {"documents": 0, "chunks": 0, "distinct_embedding_models": []}


# ---------- R1: dry-run ----------


def test_R1_dry_run_does_not_touch_db(
    pg_clean: Engine,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    fast_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_vault_doc(tmp_path, "20260101000001", "body one")
    _seed_vault_doc(tmp_path, "20260101000002", "body two")

    import ingest.rebuild as rb_mod

    mock_down = MagicMock()
    mock_up = MagicMock()
    # monkeypatch restores the original alembic.command.downgrade / upgrade
    # automatically at test teardown — critical because later tests
    # (test_migration.py) call these functions directly.
    monkeypatch.setattr(rb_mod.command, "downgrade", mock_down)
    monkeypatch.setattr(rb_mod.command, "upgrade", mock_up)

    result = rebuild_mod.rebuild_from_vault(tmp_path, pg_clean, dry_run=True, assume_yes=True)

    assert result["dry_run"] is True
    assert result["would_process_files"] == 2
    out = capsys.readouterr().out
    assert "Would wipe" in out
    assert "Would process: 2" in out
    mock_down.assert_not_called()
    mock_up.assert_not_called()


# ---------- R2/R3: TTY prompt behavior ----------


def test_R2_tty_without_yes_user_n_aborts(
    pg_clean: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fast_env
) -> None:
    import ingest.rebuild as rb_mod

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    mock_down = MagicMock()
    monkeypatch.setattr(rb_mod.command, "downgrade", mock_down)

    result = rebuild_mod.rebuild_from_vault(tmp_path, pg_clean, assume_yes=False)
    assert result["aborted"] is True
    mock_down.assert_not_called()


def test_R4_assume_yes_skips_prompt(
    pg_clean: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fast_env
) -> None:
    """--yes must skip even when isatty() returns True."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def fail_input(*a, **kw):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("input() was called despite assume_yes=True")

    monkeypatch.setattr("builtins.input", fail_input)

    # Uses real alembic on the pg_clean engine — D-25 round-trip against live DB.
    result = rebuild_mod.rebuild_from_vault(tmp_path, pg_clean, assume_yes=True)
    assert "aborted" not in result
    assert result["rebuilt"]["documents"] == 0


# ---------- R5: alembic call order ----------


def test_R5_alembic_downgrade_before_upgrade(
    pg_clean: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fast_env
) -> None:
    import ingest.rebuild as rb_mod

    calls: list[tuple[str, str]] = []

    def spy_downgrade(cfg, target):  # noqa: ANN001
        calls.append(("downgrade", target))

    def spy_upgrade(cfg, target):  # noqa: ANN001
        calls.append(("upgrade", target))

    monkeypatch.setattr(rb_mod.command, "downgrade", spy_downgrade)
    monkeypatch.setattr(rb_mod.command, "upgrade", spy_upgrade)

    # Also stub ingest_run to a no-op so we don't touch the live DB for SQL here.
    monkeypatch.setattr(rb_mod, "ingest_run", lambda *a, **kw: {"total": 0, "succeeded": 0})

    rebuild_mod.rebuild_from_vault(tmp_path, pg_clean, assume_yes=True)
    assert calls[0] == ("downgrade", "base")
    assert calls[1] == ("upgrade", "head")


# ---------- R7: idempotence end-to-end ----------


@pytest.mark.slow
def test_R7_rebuild_idempotent(pg_clean: Engine, tmp_path: Path, fast_env) -> None:
    """ingest_run -> snapshot -> rebuild -> snapshot. Document ids + chunk counts match (D-29)."""
    _seed_vault_doc(tmp_path, "20260101000001", "I. 개요\n삼성전자 본문 A.\n")
    _seed_vault_doc(tmp_path, "20260101000002", "II. 재무\n삼성전자 본문 B.\n")
    _seed_vault_doc(tmp_path, "20260101000003", "III. 공시\n삼성전자 본문 C.\n")

    stats1 = worker_mod.ingest_run(tmp_path, pg_clean)
    assert stats1["succeeded"] == 3

    def _doc_ids_and_chunk_counts(engine: Engine) -> dict[str, int]:
        with engine.connect() as conn:
            rows = conn.execute(
                sa.text(
                    "SELECT d.id, (SELECT count(*) FROM chunks c "
                    "WHERE c.document_id = d.id) FROM documents d"
                )
            ).all()
        return {r[0]: int(r[1]) for r in rows}

    before = _doc_ids_and_chunk_counts(pg_clean)
    assert len(before) == 3

    result = rebuild_mod.rebuild_from_vault(tmp_path, pg_clean, assume_yes=True)
    assert "aborted" not in result
    after = _doc_ids_and_chunk_counts(pg_clean)

    assert set(before.keys()) == set(after.keys())
    assert before == after  # chunk count per doc identical


# ---------- R6: programmatic shape ----------


def test_R6_programmatic_result_shape(pg_clean: Engine, tmp_path: Path, fast_env) -> None:
    result = rebuild_mod.rebuild_from_vault(tmp_path, pg_clean, assume_yes=True)
    assert set(result.keys()) >= {"wiped", "rebuilt", "ingest_stats"}
    assert "documents" in result["wiped"]
    assert "documents" in result["rebuilt"]
    assert "total" in result["ingest_stats"]
