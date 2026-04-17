import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


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


# Tables created by Phase 2 migration (Plan 02). Listed here so pg_clean is
# ready for Plan 02/03 tests without further conftest edits.
_PHASE2_TABLES = (
    "ingest_runs",
    "events",
    "edges",
    "chunks",
    "documents",
    "entity_aliases",
    "entities",
)


@pytest.fixture
def pg_clean(pg_engine: Engine) -> Engine:
    """Function-scoped: TRUNCATE Phase 2 tables if they exist, then return the engine."""
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
        to_truncate = [t for t in _PHASE2_TABLES if t in existing]
        if to_truncate:
            # Trusted constant list — not user input; safe f-string composition.
            conn.execute(sa.text(f"TRUNCATE {', '.join(to_truncate)} RESTART IDENTITY CASCADE"))
    return pg_engine
