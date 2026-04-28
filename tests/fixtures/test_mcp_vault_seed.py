"""Sanity tests for the auto-generated mcp-vault test fixture (Plan 06-03 Task 2).

Verifies:
- The fixture corpus contains ≥10 distinct tickers and ≥100 markdown files.
- Every ``raw/`` markdown file has frontmatter that round-trips through
  ``shared.frontmatter.read_frontmatter`` (i.e., the FrontMatter Pydantic
  schema validates).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shared.frontmatter import read_frontmatter

FIXTURE_ROOT = Path(__file__).resolve().parent / "mcp-vault"


def _all_md_files() -> list[Path]:
    return sorted(FIXTURE_ROOT.rglob("*.md"))


def test_fixture_count() -> None:
    assert FIXTURE_ROOT.exists(), f"fixture not built at {FIXTURE_ROOT}"
    md_files = _all_md_files()
    assert len(md_files) >= 100, f"expected ≥100 docs, got {len(md_files)}"

    # Distinct tickers from raw/ frontmatter `provenance.ticker`.
    tickers: set[str] = set()
    for p in (FIXTURE_ROOT / "raw").rglob("*.md"):
        model, _ = read_frontmatter(str(p))
        if model.provenance.ticker:
            tickers.add(model.provenance.ticker)
    assert len(tickers) >= 10, f"expected ≥10 distinct tickers, got {len(tickers)}"


@pytest.mark.parametrize(
    "subdir",
    ["raw/dart", "raw/news", "raw/kind"],
)
def test_fixture_frontmatter_valid(subdir: str) -> None:
    base = FIXTURE_ROOT / subdir
    assert base.exists(), f"missing {base}"
    files = sorted(base.rglob("*.md"))
    assert files, f"no files under {base}"
    for p in files:
        # read_frontmatter raises ValueError on invalid schema.
        model, body = read_frontmatter(str(p))
        assert model.provenance.source in {"dart", "news", "kind"}
        assert body.strip(), f"empty body in {p}"
