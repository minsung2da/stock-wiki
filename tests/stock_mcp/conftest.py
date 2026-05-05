"""Phase 6 Plan 06-03 — session-scoped MCP-vault fixture (Task 3).

Builds the integration-test scaffolding that downstream Plans 06-04..06-09
share:

- ``mcp_vault_engine`` (session): testcontainers Postgres (reused via
  ``pg_engine``) seeded with the ``tests/fixtures/mcp-vault/`` corpus,
  entity aliases, ingest_runs rows, and a small set of synthetic edges
  spanning real document_ids. Yields ``(engine, vault_root, repo_root)``.
- ``mcp_vault_isolated`` (function): per-test writable copy of the fixture
  tree under ``tmp_path``, with ``STOCK_REPO_ROOT`` set so tools that call
  ``stock_mcp.repo_root.repo_root()`` resolve to the isolated copy.

Embedder + Korean tokenizer are stubbed (FakeEmbedder + tiny tokenize fn) so
ingest never downloads bge-m3 / mecab-ko in CI.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

# Path to the committed fixture corpus.
_FIXTURE_SRC = Path(__file__).resolve().parents[1] / "fixtures" / "mcp-vault"


# 10 fixture tickers — kept in sync with scripts/build_mcp_vault_fixture.py.
# We seed entities/aliases directly (no dart-fss API calls in CI).
_FIXTURE_TICKERS: list[tuple[str, str, str]] = [
    ("005930", "00126380", "삼성전자"),
    ("000660", "00164779", "SK하이닉스"),
    ("035720", "00256598", "카카오"),
    ("035420", "00266961", "NAVER"),
    ("051910", "00356361", "LG화학"),
    ("207940", "00877059", "삼성바이오로직스"),
    ("068270", "00421196", "셀트리온"),
    ("323410", "01265262", "카카오뱅크"),
    ("373220", "01515323", "LG에너지솔루션"),
    ("247540", "00942976", "에코프로비엠"),
]


class _FakeEmbedder:
    """Deterministic 1024-d zero-vector embedder for fixture ingestion.

    Mirrors the helper used in tests/test_ingest_worker.py so the session
    fixture stays consistent with existing ingest tests.
    """

    dim = 1024

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self.dim for _ in texts]


def _fake_tokenize_ko(text: str) -> list[int]:
    if not text:
        return [0]
    return [ord(c) & 0x7FFFFFFF for c in text[:32]]


class _DummyTok:
    """Stub for ``ingest.chunking._get_tok`` (the chunker's tiktoken/mecab tok)."""

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:  # noqa: ARG002
        return list(range(len(text)))

    def decode(self, ids: list[int]) -> str:
        return " ".join(str(i) for i in ids)


def _seed_entities_direct(engine: Engine) -> None:
    """Seed entities + aliases for the 10 fixture tickers (skip dart-fss)."""
    from db.entity import upsert_entity

    for ticker, corp_code, name in _FIXTURE_TICKERS:
        upsert_entity(engine, corp_code=corp_code, canonical_name=name, ticker=ticker)


def _seed_test_edges(engine: Engine) -> None:
    """Insert synthetic edges between fixture documents.

    Phase 7: edge_type values now match the 6-value enum locked by Plan 07-02
    migration 0004 (ck_edge_type_phase7). Picks the first four DART
    document_ids by source='dart' and writes:
      - mentions_ticker (document → ticker '005930')
      - filing_event   (document → document)  -- repurposes a doc id as event id
      - supersedes     (document → document)
    All rows include the `tag` column per EDGE_TAG_POLICY (CONTEXT D-07).
    """
    with engine.begin() as conn:
        rows = conn.execute(
            sa.text("SELECT id FROM documents WHERE source = 'dart' ORDER BY id LIMIT 4")
        ).all()
        if len(rows) < 4:
            return  # no docs ingested; skip silently
        ids = [r.id for r in rows]
        # (src_type, src_id, dst_type, dst_id, edge_type, tag)
        # Preserve the 2-hop chain ids[0] -> ids[1] -> ids[3] required by
        # test_get_related_depth2_includes_two_hop, plus an extra direct
        # neighbor to satisfy ">= 2 direct edges" assertion.
        edge_specs = [
            ("document", ids[0], "document", ids[1], "filing_event", "INFERRED"),
            ("document", ids[0], "document", ids[2], "mentions_ticker", "EXTRACTED"),
            ("document", ids[1], "document", ids[3], "supersedes", "EXTRACTED"),
        ]
        for st, si, dt, di, et, tag in edge_specs:
            conn.execute(
                sa.text(
                    "INSERT INTO edges (src_type, src_id, dst_type, dst_id, edge_type, tag) "
                    "VALUES (:st, :si, :dt, :di, :et, :tag) "
                    "ON CONFLICT ON CONSTRAINT uq_edge_endpoints DO NOTHING"
                ),
                {"st": st, "si": si, "dt": dt, "di": di, "et": et, "tag": tag},
            )


def _seed_ingest_runs(engine: Engine) -> None:
    """Insert at least one ingest_runs row per source.

    Pitfall 3: ``ingest_runs`` is otherwise empty, so health() tests need
    realistic data — including one stale (>26h ago) row to exercise the stale
    path.
    """
    now = datetime.now(UTC)
    fresh = now - timedelta(minutes=30)
    stale = now - timedelta(hours=30)  # > 26h ago: triggers stale path
    rows = [
        ("dart", fresh),
        ("krx", fresh),
        ("news", fresh),
        ("kind", fresh),
        ("macro", stale),  # macro deliberately stale
    ]
    with engine.begin() as conn:
        for source, finished in rows:
            conn.execute(
                sa.text(
                    "INSERT INTO ingest_runs (started_at, finished_at, kind, source, stats) "
                    "VALUES (:started, :finished, 'collect', :source, "
                    'CAST(\'{"succeeded": 1, "failed": []}\' AS JSONB))'
                ),
                {
                    "started": finished - timedelta(minutes=1),
                    "finished": finished,
                    "source": source,
                },
            )


def _ingest_fixture_vault(engine: Engine, vault_root: Path, monkeypatch_targets: dict) -> None:
    """Run the ingest worker against the fixture vault using stub embedder/tokenizer.

    We patch the relevant modules in-process. Because this fixture is
    session-scoped and pytest's monkeypatch is function-scoped, we install the
    patches with ``setattr``/``setattr`` on the module objects directly and
    record the originals for teardown.
    """
    from ingest import chunking as chunking_mod
    from ingest import worker as worker_mod
    from ingest.parsers import Section
    from ingest.parsers import dart as dart_parser

    fake_embedder = _FakeEmbedder()
    fake_tok = _DummyTok()

    # Fallback parser: DART uses the real TOC parser; everything else
    # collapses to a single Section so news/kind/note bodies still ingest.
    # (Phase-3 parsers/__init__.py raises on unknown source by design.)
    _real_parse_sections = worker_mod.parse_sections

    def _fixture_parse_sections(body: str, source: str):
        if source == "dart":
            return dart_parser.parse_sections(body, source)
        return [Section(title="", path="", text=body, order=0)]

    monkeypatch_targets["chunking._get_tok"] = (chunking_mod, "_get_tok", chunking_mod._get_tok)
    monkeypatch_targets["worker.Embedder"] = (worker_mod, "Embedder", worker_mod.Embedder)
    monkeypatch_targets["worker.tokenize_ko"] = (
        worker_mod,
        "tokenize_ko",
        worker_mod.tokenize_ko,
    )
    monkeypatch_targets["worker.parse_sections"] = (
        worker_mod,
        "parse_sections",
        _real_parse_sections,
    )

    chunking_mod._get_tok = lambda: fake_tok  # type: ignore[assignment]
    worker_mod.Embedder = lambda *a, **kw: fake_embedder  # type: ignore[assignment]
    worker_mod.tokenize_ko = _fake_tokenize_ko  # type: ignore[assignment]
    worker_mod.parse_sections = _fixture_parse_sections  # type: ignore[assignment]

    # Run ingest. Use ingest_run() directly so we don't need the rebuild
    # downgrade/upgrade dance — pg_engine already ran alembic upgrade head.
    worker_mod.ingest_run(vault_root, engine, force_reembed=True, embedder=fake_embedder)


def _restore_patches(targets: dict) -> None:
    for _key, (mod, attr, original) in targets.items():
        setattr(mod, attr, original)


@pytest.fixture(scope="session")
def mcp_vault_engine(
    pg_engine: Engine, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[tuple[Engine, Path, Path]]:
    """Session fixture: bring up Postgres + ingest the mcp-vault corpus.

    Yields ``(engine, vault_root, repo_root)`` where:
      - ``engine`` is the session testcontainers Postgres (alembic-migrated).
      - ``repo_root`` is a tmp copy of the committed fixture (so write tests
        cannot dirty the committed tree).
      - ``vault_root = repo_root / "vault"``.

    Cost: ~one-time per pytest session (Pitfall 6).
    """
    # Materialize a session-scoped repo tree so tools that derive
    # repo_root() naturally see vault/, notes/, ingested/ siblings.
    session_root = tmp_path_factory.mktemp("mcp-vault-session")
    repo_root = session_root / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)

    # Mirror the committed fixture into <repo_root>/vault/{raw,ingested}/
    # and <repo_root>/notes/. The committed tree already mixes raw/, notes/,
    # and ingested/_status — copy each piece into the right place.
    vault_root = repo_root / "vault"
    vault_root.mkdir(parents=True, exist_ok=True)
    if (_FIXTURE_SRC / "raw").exists():
        shutil.copytree(_FIXTURE_SRC / "raw", vault_root / "raw")
    if (_FIXTURE_SRC / "ingested").exists():
        shutil.copytree(_FIXTURE_SRC / "ingested", vault_root / "ingested")
    if (_FIXTURE_SRC / "notes").exists():
        # Notes (incl. private/portfolio.md) live at <repo_root>/notes/, not vault/.
        shutil.copytree(_FIXTURE_SRC / "notes", repo_root / "notes")

    # 1) Seed entities + name aliases so resolve_entity works for fixture tickers.
    _seed_entities_direct(pg_engine)
    from db.seed_name_aliases import seed_name_aliases

    seed_name_aliases(pg_engine)

    # 2) Ingest the fixture vault under the patched embedder/tokenizer.
    patch_targets: dict = {}
    try:
        _ingest_fixture_vault(pg_engine, vault_root, patch_targets)
    finally:
        _restore_patches(patch_targets)

    # 3) Seed synthetic edges + ingest_runs rows for downstream tools.
    _seed_test_edges(pg_engine)
    _seed_ingest_runs(pg_engine)

    yield (pg_engine, vault_root, repo_root)


@pytest.fixture(scope="function")
def mcp_vault_isolated(
    mcp_vault_engine: tuple[Engine, Path, Path], tmp_path: Path
) -> Iterator[tuple[Engine, Path, Path]]:
    """Per-test writable copy of the mcp-vault fixture (used by add_note tests).

    Returns ``(engine, vault_root, repo_root)`` where ``vault_root`` and
    ``repo_root`` are freshly copied under ``tmp_path``. ``STOCK_REPO_ROOT``
    is set for the test's lifetime so ``stock_mcp.repo_root.repo_root()``
    resolves to the isolated copy automatically.
    """
    session_engine, _session_vault_root, session_repo_root = mcp_vault_engine
    dst_repo = tmp_path / "repo"
    shutil.copytree(session_repo_root, dst_repo)

    prev = os.environ.get("STOCK_REPO_ROOT")
    os.environ["STOCK_REPO_ROOT"] = str(dst_repo)
    try:
        yield (session_engine, dst_repo / "vault", dst_repo)
    finally:
        if prev is None:
            os.environ.pop("STOCK_REPO_ROOT", None)
        else:
            os.environ["STOCK_REPO_ROOT"] = prev


# Silence unused-imports linter for type-only references kept for readability.
_ = (date, sa)
