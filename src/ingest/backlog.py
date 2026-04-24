"""backlog.md rendering (D-25, INGEST-03/04 observability).

Generates a markdown string for vault/ingested/_status/backlog.md. Today's
dated section is regenerated per run; prior-day sections are preserved
verbatim. Items persisting (path + flag) across runs carry their first_seen
date forward. Items >= CHRONIC_DAYS old surface under a Chronic items section.

Pure function: no I/O except reading prior_path (if provided). Caller writes
the returned string via atomic write.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import date as date_type
from pathlib import Path
from typing import Literal

import yaml

SCHEMA_VERSION = 1
CHRONIC_DAYS = 3

BacklogCategory = Literal[
    "missing_derived",
    "review_flagged",
    "oversize_skipped",
    "disk_warning",
    "schedule_status_warning",
]

_CATEGORY_LABELS: dict[str, str] = {
    "missing_derived": "Missing _derived",
    "review_flagged": "Review flagged",
    "oversize_skipped": "Oversize skipped",
    "disk_warning": "Disk warnings",
    "schedule_status_warning": "Schedule status warnings",
}


@dataclass
class BacklogItem:
    category: BacklogCategory
    path: str
    flag: str = ""
    note: str = ""
    first_seen: date_type | None = None

    def key(self) -> str:
        return f"{self.path}::{self.flag}"


_ROW_RE = re.compile(
    r"^\|\s*(?P<path>[^|]+?)\s*\|\s*(?P<flag>[^|]*?)\s*\|\s*(?P<fs>\d{4}-\d{2}-\d{2})\s*\|"
)


def _parse_prior_first_seen(prior_text: str) -> dict[str, date_type]:
    """Extract {key -> first_seen} map from prior backlog table rows.

    Row shape: `| path | flag_or_blank | YYYY-MM-DD | note |`.
    Tolerant: silently skips malformed rows.
    """
    first_seen_map: dict[str, date_type] = {}
    for line in prior_text.splitlines():
        m = _ROW_RE.match(line.strip())
        if not m:
            continue
        path = m.group("path").strip()
        flag = m.group("flag").strip()
        if path in ("Path", "---", ""):
            continue
        try:
            fs = datetime.strptime(m.group("fs"), "%Y-%m-%d").date()
        except ValueError:
            continue
        first_seen_map[f"{path}::{flag}"] = fs
    return first_seen_map


def _extract_prior_nontoday_sections(prior_text: str, today_header: str) -> str:
    """Return all `## YYYY-MM-DD` sections from prior_text whose date != today.

    Strips the frontmatter block first.
    """
    if prior_text.startswith("---"):
        end = prior_text.find("\n---", 3)
        if end != -1:
            prior_text = prior_text[end + 4 :].lstrip("\n")
    section_re = re.compile(r"^## \d{4}-\d{2}-\d{2}", re.MULTILINE)
    matches = list(section_re.finditer(prior_text))
    preserved: list[str] = []
    for i, m in enumerate(matches):
        newline_idx = prior_text.find("\n", m.start())
        header_end = newline_idx if newline_idx != -1 else len(prior_text)
        header_line = prior_text[m.start() : header_end]
        if today_header in header_line:
            continue
        next_start = matches[i + 1].start() if i + 1 < len(matches) else len(prior_text)
        preserved.append(prior_text[m.start() : next_start].rstrip() + "\n")
    return "\n".join(preserved)


def render_backlog(
    today_items: list[BacklogItem],
    prior_path: str | Path | None = None,
    now: datetime | None = None,
) -> str:
    """Render backlog.md body string.

    Args:
        today_items: items flagged on this run.
        prior_path: path to existing backlog.md for first_seen carryover +
            prior-section preservation. None/missing = fresh start.
        now: deterministic-test override; default = datetime.now(UTC).
    """
    now = now or datetime.now(UTC)
    today = now.date()
    today_header = today.isoformat()

    prior_text = ""
    if prior_path is not None:
        p = Path(prior_path)
        if p.exists():
            prior_text = p.read_text(encoding="utf-8")
    first_seen_map = _parse_prior_first_seen(prior_text)

    for item in today_items:
        item.first_seen = first_seen_map.get(item.key()) or today

    frontmatter_yaml = yaml.safe_dump(
        {"updated": now.isoformat(), "schema_version": SCHEMA_VERSION},
        sort_keys=True,
        allow_unicode=True,
    )
    lines: list[str] = [
        "---",
        frontmatter_yaml.rstrip(),
        "---",
        "",
        "# Schedule Agent Backlog",
        "",
        "*운영자 수동 개입이 필요한 항목. 매 schedule run에 오늘 날짜 섹션을 regenerate.*",
        "",
        "---",
        "",
        f"## {today_header} (run at {now.strftime('%H:%M:%SZ')}, {len(today_items)} items)",
        "",
    ]

    by_cat: dict[str, list[BacklogItem]] = {c: [] for c in _CATEGORY_LABELS}
    for item in today_items:
        by_cat.setdefault(item.category, []).append(item)

    for cat, label in _CATEGORY_LABELS.items():
        items = by_cat.get(cat, [])
        lines.append(f"### {label} ({len(items)})")
        if not items:
            lines.append("")
            lines.append("*(none)*")
            lines.append("")
            continue
        lines.append("")
        lines.append("| Path | Flag | First seen | Note |")
        lines.append("|------|------|------------|------|")
        for it in items:
            fs = (it.first_seen or today).isoformat()
            lines.append(f"| {it.path} | {it.flag} | {fs} | {it.note} |")
        lines.append("")

    chronic = [
        it
        for it in today_items
        if it.first_seen is not None and (today - it.first_seen).days >= CHRONIC_DAYS
    ]
    lines.append(f"### Chronic items ({CHRONIC_DAYS} days+) ({len(chronic)})")
    lines.append("")
    if chronic:
        lines.append("| Path | Flag | First seen | Age (days) |")
        lines.append("|------|------|------------|------------|")
        for it in chronic:
            fs = it.first_seen.isoformat() if it.first_seen else today_header
            age = (today - (it.first_seen or today)).days
            lines.append(f"| {it.path} | {it.flag} | {fs} | {age} |")
    else:
        lines.append("*(none)*")
    lines.append("")
    lines.append("---")
    lines.append("")

    preserved = _extract_prior_nontoday_sections(prior_text, today_header)
    if preserved.strip():
        lines.append(preserved.rstrip())
        lines.append("")

    return "\n".join(lines) + "\n"
