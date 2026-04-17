import tempfile
from pathlib import Path

import pytest


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
