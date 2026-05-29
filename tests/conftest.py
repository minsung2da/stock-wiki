import os
import re
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

_SAFE_TABLE_RE = re.compile(r"^[a-z_]+$")


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """Temporary vault directory for test files."""
    return tmp_path


SAMPLE_YAML = (
    "---\n"
    "provenance:\n"
    "  source: dart\n"
    '  source_id: "20260416000523"\n'
    '  content_hash: "sha256:abc123def456"\n'
    '  corp_code: "00126380"\n'
    '  ticker: "005930"\n'
    "  lang: ko\n"
    "ingest_state:\n"
    "  processed: false\n"
    "_derived:\n"
    "  tickers: []\n"
    "  catalysts: []\n"
    "---\n"
    "Test document body for Samsung Electronics disclosure.\n"
)


@pytest.fixture
def sample_yaml() -> str:
    return SAMPLE_YAML


@pytest.fixture
def sample_md_file(tmp_vault: Path, sample_yaml: str) -> Path:
    """Create a temporary markdown file with frontmatter."""
    md_file = tmp_vault / "test_doc.md"
    md_file.write_text(sample_yaml, encoding="utf-8")
    return md_file


@pytest.fixture(scope="session")
def pg_engine() -> Engine:
    """Session-scoped Postgres container with vchord extensions.

    Uses the same image as docker-compose.yml so extensions are present.
    Runs alembic upgrade head once per session.
    """
    from alembic import command
    from alembic.config import Config
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer(
        "tensorchord/vchord-suite:pg17-latest",
        username="test",
        password="test",
        dbname="test",
    ) as pg:
        raw_url = pg.get_connection_url()
        # Force psycopg3 driver (testcontainers may emit postgresql:// or
        # postgresql+psycopg2:// depending on version; normalize both).
        if raw_url.startswith("postgresql+psycopg2://"):
            url = raw_url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
        elif raw_url.startswith("postgresql://"):
            url = raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
        else:
            url = raw_url
        # Alembic env.py reads DATABASE_URL from env
        os.environ["DATABASE_URL"] = url
        cfg = Config("src/db/alembic.ini")
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        engine = create_engine(url, future=True)
        try:
            yield engine
        finally:
            engine.dispose()


# Tables present in the live schema after `alembic upgrade head`. Listed in
# TRUNCATE-safe order: child tables (with FKs into the others) come first so
# `TRUNCATE ... CASCADE` cannot blow up on dependency cycles.
#
# Phase 1 (migration 0006) added the six v2.0 domain tables. The Phase 2
# dormant tables (documents/chunks/edges/ingest_runs) remain — Q3 Option B —
# and `events_legacy` is the renamed Phase 2 events table. All are TRUNCATEd
# for hygiene even though most stay empty.
_LIVE_TABLES = (
    # Phase 1 observability — independent of FK graph, safe to truncate first
    "collector_runs",
    # Phase 1 KIND classifier — FKs into filings, must precede filings
    "events",
    # Phase 1 body-bearing tables
    "news",
    "filings",
    # Phase 1 pure numeric tables — no FK chains into the others
    "ohlcv",
    "macro_series",
    # Renamed legacy table from migration 0001 (empty post-shutdown, but
    # TRUNCATE keeps cross-test hygiene)
    "events_legacy",
    # Phase 2 dormant tables — kept per Q3 Option B
    "ingest_runs",
    "edges",
    "chunks",
    "documents",
    # Phase 2 entity tables (entities is the FK target of nearly everything)
    "entity_aliases",
    "entities",
)


@pytest.fixture
def pg_clean(pg_engine: Engine) -> Engine:
    """Function-scoped: TRUNCATE live-schema tables if they exist, then return the engine."""
    with pg_engine.begin() as conn:
        # Tables may not exist yet in this plan — guard with information_schema check.
        existing = {
            r[0]
            for r in conn.execute(
                sa.text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
            )
        }
        to_truncate = [t for t in _LIVE_TABLES if t in existing]
        for tbl in to_truncate:
            # Assert safe identifier before interpolation: guards against future
            # _LIVE_TABLES entries that contain SQL metacharacters.
            assert _SAFE_TABLE_RE.match(tbl), f"unsafe table name: {tbl!r}"
            conn.execute(sa.text(f"TRUNCATE {tbl} RESTART IDENTITY CASCADE"))
    return pg_engine


@pytest.fixture
def pg_with_chunks_row(pg_clean: Engine) -> Engine:
    """Insert one documents + chunks row for Phase 3 probe/integration tests.

    Uses a dummy 1024-d zero vector for `chunks.embedding` and a short INT[]
    for `chunks.bm25_tokens` so the vchord_bm25 cast probe has live data to
    exercise.
    """
    doc_id = "a" * 64
    with pg_clean.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO documents (id, body, source, vault_path) "
                "VALUES (:id, :body, :source, :vault_path)"
            ),
            {"id": doc_id, "body": "x", "source": "dart", "vault_path": "vault/raw/dart/test.md"},
        )
        # Build a pgvector literal: '[0,0,...,0]' (1024 zeros).
        zero_vec = "[" + ",".join(["0"] * 1024) + "]"
        conn.execute(
            sa.text(
                "INSERT INTO chunks (document_id, ord, text, embedding, bm25_tokens) "
                "VALUES (:doc_id, :ord, :text, CAST(:emb AS vector), "
                "CAST(:toks AS int[]))"
            ),
            {
                "doc_id": doc_id,
                "ord": 0,
                "text": "probe chunk",
                "emb": zero_vec,
                "toks": [1, 2, 3],
            },
        )
    return pg_clean
