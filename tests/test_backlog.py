"""Tests for ingest.backlog render_backlog (D-25)."""

from __future__ import annotations

from datetime import UTC, datetime

from ingest.backlog import BacklogItem, render_backlog

TODAY = datetime(2026, 4, 24, 22, 5, 13, tzinfo=UTC)


def test_fresh_run_no_prior(tmp_path):
    out = render_backlog([], prior_path=None, now=TODAY)
    assert "schema_version: 1" in out
    assert "## 2026-04-24" in out
    assert "### Missing _derived (0)" in out
    assert "### Chronic items (3 days+) (0)" in out


def test_first_seen_preserved(tmp_path):
    prior = tmp_path / "backlog.md"
    prior.write_text(
        "---\nupdated: 2026-04-20T22:00:00+00:00\nschema_version: 1\n---\n\n"
        "## 2026-04-20 (run at 22:00:00Z, 1 items)\n\n"
        "### Review flagged (1)\n\n"
        "| Path | Flag | First seen | Note |\n"
        "|------|------|------------|------|\n"
        "| vault/raw/dart/abc.md | dart_structured_disagreement | 2026-04-20 | note |\n",
        encoding="utf-8",
    )
    items = [
        BacklogItem(
            category="review_flagged",
            path="vault/raw/dart/abc.md",
            flag="dart_structured_disagreement",
            note="still broken",
        )
    ]
    out = render_backlog(items, prior_path=str(prior), now=TODAY)
    assert (
        "| vault/raw/dart/abc.md | dart_structured_disagreement | 2026-04-20 | still broken |"
        in out
    )


def test_new_item_gets_today_first_seen(tmp_path):
    items = [
        BacklogItem(
            category="review_flagged",
            path="vault/raw/news/new.md",
            flag="numeric_echo_mismatch",
            note="new today",
        )
    ]
    out = render_backlog(items, prior_path=None, now=TODAY)
    assert "| vault/raw/news/new.md | numeric_echo_mismatch | 2026-04-24 | new today |" in out


def test_chronic_detected(tmp_path):
    prior = tmp_path / "backlog.md"
    prior.write_text(
        "---\nupdated: 2026-04-20T22:00:00+00:00\nschema_version: 1\n---\n\n"
        "## 2026-04-20 (run at 22:00:00Z, 1 items)\n\n"
        "### Review flagged (1)\n\n"
        "| Path | Flag | First seen | Note |\n"
        "|------|------|------------|------|\n"
        "| vault/raw/dart/chronic.md | dart_structured_disagreement | 2026-04-20 | |\n",
        encoding="utf-8",
    )
    items = [
        BacklogItem(
            category="review_flagged",
            path="vault/raw/dart/chronic.md",
            flag="dart_structured_disagreement",
        )
    ]
    out = render_backlog(items, prior_path=str(prior), now=TODAY)
    assert "### Chronic items (3 days+) (1)" in out
    assert "| vault/raw/dart/chronic.md | dart_structured_disagreement | 2026-04-20 | 4 |" in out


def test_chronic_not_detected_when_young(tmp_path):
    prior = tmp_path / "backlog.md"
    prior.write_text(
        "---\nupdated: 2026-04-23T22:00:00+00:00\nschema_version: 1\n---\n\n"
        "## 2026-04-23 (run at 22:00:00Z, 1 items)\n\n"
        "### Review flagged (1)\n\n"
        "| Path | Flag | First seen | Note |\n"
        "|------|------|------------|------|\n"
        "| vault/raw/dart/young.md | self_inconsistent | 2026-04-23 | |\n",
        encoding="utf-8",
    )
    items = [
        BacklogItem(
            category="review_flagged",
            path="vault/raw/dart/young.md",
            flag="self_inconsistent",
        )
    ]
    out = render_backlog(items, prior_path=str(prior), now=TODAY)
    assert "### Chronic items (3 days+) (0)" in out


def test_prior_nontoday_sections_preserved(tmp_path):
    prior = tmp_path / "backlog.md"
    prior.write_text(
        "---\nupdated: 2026-04-23T22:00:00+00:00\nschema_version: 1\n---\n\n"
        "## 2026-04-23 (run at 22:00:00Z, 2 items)\n\nHISTORICAL_MARKER_23\n",
        encoding="utf-8",
    )
    out = render_backlog([], prior_path=str(prior), now=TODAY)
    assert "## 2026-04-24" in out
    assert "HISTORICAL_MARKER_23" in out


def test_today_section_regenerated_fresh(tmp_path):
    prior = tmp_path / "backlog.md"
    prior.write_text(
        "---\nupdated: 2026-04-24T10:00:00+00:00\nschema_version: 1\n---\n\n"
        "## 2026-04-24 (run at 10:00:00Z, 99 items)\n\nSTALE_MARKER_24\n",
        encoding="utf-8",
    )
    out = render_backlog([], prior_path=str(prior), now=TODAY)
    assert "STALE_MARKER_24" not in out
    assert "## 2026-04-24 (run at 22:05:13Z, 0 items)" in out


def test_schema_version_in_frontmatter(tmp_path):
    out = render_backlog([], prior_path=None, now=TODAY)
    assert "schema_version: 1" in out[:300]


def test_all_five_categories_rendered(tmp_path):
    out = render_backlog([], prior_path=None, now=TODAY)
    for label in (
        "Missing _derived",
        "Review flagged",
        "Oversize skipped",
        "Disk warnings",
        "Schedule status warnings",
    ):
        assert f"### {label}" in out


def test_dataclass_fields():
    it = BacklogItem(category="oversize_skipped", path="p", flag="", note="n")
    assert it.first_seen is None
    assert it.key() == "p::"
