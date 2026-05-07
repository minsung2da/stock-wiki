"""Phase 8 Plan 03 — Task 2: dashboards/events-this-week.md skeleton (D-09).

UAT (2026-05-06) revealed: Dataview DQL parser rejects identifiers starting with
`_` in dotted form (`_derived.event_type`). The fix is bracket-form access:
`row["_derived"].event_type`. Test below enforces the bracket form and forbids
the dotted form so a regression cannot ship silently.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = REPO_ROOT / "dashboards" / "events-this-week.md"

# Match bare `_derived.` outside any bracketed context.
# Allowed: `row["_derived"].field`, `dashboards/_data` (slash-separated, not DQL ref)
# Forbidden in DQL bodies: `_derived.field`, `(_derived.field`, ` _derived.field`
_BARE_DERIVED_DOTTED = re.compile(r'(?<!["\w/])_derived\.')


def _read() -> str:
    assert DASHBOARD_PATH.exists(), f"Missing {DASHBOARD_PATH}"
    return DASHBOARD_PATH.read_text(encoding="utf-8")


def test_file_exists_with_dataview() -> None:
    """D-09: vault/raw FROM clause + ```dataview block."""
    content = _read()
    block_count = sum(
        1 for line in content.splitlines() if line.strip() == "```dataview"
    )
    assert block_count >= 1, (
        f"events-this-week.md must have >=1 ```dataview block; found {block_count}"
    )
    assert "vault/raw" in content, (
        "events-this-week.md must reference vault/raw (D-09 FROM clause)"
    )


def test_event_type_priority_visible() -> None:
    """D-09: event_type sort priority traces in DQL or prose."""
    content = _read()
    assert "event_type" in content, (
        "events-this-week.md must surface event_type ordering (D-09 priority)"
    )


def test_derived_uses_bracket_form() -> None:
    """UAT 2026-05-06: Dataview DQL rejects `_derived.x`; require `row["_derived"].x`."""
    content = _read()
    assert 'row["_derived"]' in content, (
        "events-this-week.md must use bracket-form `row[\"_derived\"]` access "
        "(Dataview DQL parser rejects leading-underscore dotted refs)"
    )
    bare = _BARE_DERIVED_DOTTED.findall(content)
    assert not bare, (
        f"events-this-week.md must NOT contain bare `_derived.` dotted refs "
        f"(parser fails); found {len(bare)} occurrence(s). Use `row[\"_derived\"].field`."
    )


def test_seven_day_window() -> None:
    """D-09: 7-day window expression."""
    content = _read()
    assert "dur(7 days)" in content, (
        "events-this-week.md must use dur(7 days) day window (D-09)"
    )


def test_no_dataviewjs() -> None:
    """D-18 guard."""
    content = _read()
    assert "```dataviewjs" not in content, (
        "T-08-03-01: dataviewjs must NOT appear in events-this-week.md"
    )
