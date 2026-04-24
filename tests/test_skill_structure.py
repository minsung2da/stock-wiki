"""Skill structure tests — SKILL.md frontmatter parseable, required sections present."""

from __future__ import annotations

from pathlib import Path

import yaml

SKILL_ROOT = Path(".claude/routines/enrich")


def _parse_frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} missing frontmatter"
    end = text.find("\n---", 4)
    assert end != -1, f"{path} unclosed frontmatter"
    fm = yaml.safe_load(text[4:end])
    body = text[end + 4 :]
    return fm, body


def test_skill_md_frontmatter_parseable():
    fm, body = _parse_frontmatter(SKILL_ROOT / "SKILL.md")
    assert fm["name"] == "stock-enrich"
    assert "description" in fm
    assert "allowed-tools" in fm


def test_skill_md_required_sections_present():
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    for header in (
        "## Pre-flight",
        "## Per-document loop",
        "## Post-loop",
        "## Git commit + push + PR",
        "## Failure handling",
    ):
        assert header in text, f"missing section: {header}"


def test_skill_md_mentions_character_level():
    """Pitfall 4: terminology must be 'character-level', not 'byte-level'."""
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "character-level echo-back" in text
    assert "byte-level echo-back" not in text  # old misleading term


def test_skill_md_mentions_facts_equal():
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "facts_equal" in text


def test_skill_md_mentions_zone_integrity():
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "zone_integrity" in text or "assert_zones_unchanged" in text


def test_all_four_prompts_exist():
    for name in ("derived_dart_b", "derived_news", "derived_kind", "derived_macro"):
        p = SKILL_ROOT / "prompts" / f"{name}.md"
        assert p.exists(), f"missing prompt: {p}"


def test_prompts_have_frontmatter():
    for name in ("derived_dart_b", "derived_news", "derived_kind", "derived_macro"):
        fm, _ = _parse_frontmatter(SKILL_ROOT / "prompts" / f"{name}.md")
        assert "source" in fm, f"{name}.md missing source field"


def test_kind_and_macro_prompts_force_sentiment_null():
    """D-13: KIND and macro prompts must instruct sentiment=null."""
    for name in ("derived_kind", "derived_macro"):
        text = (SKILL_ROOT / "prompts" / f"{name}.md").read_text(encoding="utf-8")
        assert "sentiment" in text.lower() and "null" in text.lower()
        # D-13 enforcement line
        assert "MUST be null" in text or "must be null" in text


def test_readme_covers_required_runbook_items():
    text = (SKILL_ROOT / "README.md").read_text(encoding="utf-8")
    for required in (
        "fine-grained PAT",
        "Contents: Read and write",
        "Pull requests: Read and write",
        "Allow auto-merge",
        "GITHUB_TOKEN",
        "DART_API_KEY",
        "22:00 UTC",
    ):
        assert required in text, f"README missing: {required}"


def test_helpers_no_llm_imports():
    """COLL-07 spirit: routine helpers must not import anthropic/openai either."""
    import glob

    for path in glob.glob(str(SKILL_ROOT / "helpers" / "*.py")):
        src = Path(path).read_text(encoding="utf-8")
        assert "import anthropic" not in src
        assert "import openai" not in src
        assert "from anthropic" not in src
        assert "from openai" not in src


def test_src_guard_still_clean():
    """Re-assert COLL-07 — Plan 05-08 must not leak anthropic/openai into src/."""
    import subprocess

    r = subprocess.run(
        [
            "grep",
            "-rl",
            "-E",
            "import anthropic|from anthropic|import openai|from openai",
            "src/collectors",
            "src/ingest",
            "src/shared",
        ],
        capture_output=True,
        text=True,
    )
    # grep exit 1 = no matches (what we want); exit 0 = matches found (bad)
    assert r.returncode == 1, f"COLL-07 violation: {r.stdout}"
