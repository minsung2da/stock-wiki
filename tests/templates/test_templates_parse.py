"""Phase 8 Plan 08-01 Task 2: Note templates parse with Pydantic (D-10, D-13)."""

from __future__ import annotations

from pathlib import Path

import frontmatter as pyfm

from shared.frontmatter import NoteFrontmatter, ThesisFrontmatter

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_meta(rel: str) -> dict:
    path = REPO_ROOT / rel
    post = pyfm.load(str(path))
    return dict(post.metadata or {})


def test_thesis_template_parses_with_thesis_model() -> None:
    """templates/notes/thesis.md frontmatter validates as ThesisFrontmatter."""
    meta = _load_meta("templates/notes/thesis.md")
    tf = ThesisFrontmatter.model_validate(meta)
    assert tf.type == "thesis"
    assert isinstance(tf.kill_criteria, list)
    assert tf.conviction in {"low", "medium", "high"}


def test_journal_template_parses_with_note_model() -> None:
    """templates/notes/journal.md frontmatter validates as NoteFrontmatter."""
    meta = _load_meta("templates/notes/journal.md")
    nf = NoteFrontmatter.model_validate(meta)
    assert nf.type == "journal"


def test_portfolio_template_moved() -> None:
    """D-10: templates/portfolio.md → templates/notes/portfolio.md (git mv)."""
    assert (REPO_ROOT / "templates" / "notes" / "portfolio.md").exists()
    assert not (REPO_ROOT / "templates" / "portfolio.md").exists()


def test_thesis_has_required_sections() -> None:
    """thesis body has the 4 placeholder sections (D-13 RESEARCH §Code Examples)."""
    body = (REPO_ROOT / "templates" / "notes" / "thesis.md").read_text(encoding="utf-8")
    for section in ("## 투자 논리", "## 핵심 가정", "## Kill Criteria", "## 모니터링 지표"):
        assert section in body, f"missing section: {section}"
