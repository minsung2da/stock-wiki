"""Scan vault/raw/**/*.md and yield candidates needing enrichment.

D-19 idempotency: skip if _derived already populated AND content_hash unchanged.
D-21 F-4c: skip if skip_reason set (oversize / review_required / merge_conflict)
and content_hash unchanged — no retry until human edits or upstream content
changes.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from shared.content_hash import compute_content_hash
from shared.frontmatter import read_frontmatter


@dataclass(frozen=True)
class Candidate:
    path: str
    source: str
    content_hash: str
    reason: str  # 'missing_derived' | 'hash_changed'


# Module-level list of (path, exception repr) for files whose frontmatter
# could not be parsed during the most recent ``find_candidates`` call. The
# Routines post-loop reads this so it can emit ``malformed_frontmatter``
# BacklogItems instead of silently dropping poisoned files (D-25
# observability intent — review WR-03).
LAST_PARSE_ERRORS: list[tuple[str, str]] = []


def _derived_is_populated(fm) -> bool:
    """Heuristic: _derived is 'populated' if any of its fields is non-default."""
    d = fm.derived
    return bool(
        d.tickers
        or d.event_type
        or d.catalysts
        or d.sentiment is not None
        or d.numeric_facts
        or d.summary
        or d.skip_reason is not None
    )


def find_candidates(vault_root: str | Path) -> list[Candidate]:
    """Scan vault/raw/**/*.md; return paths needing enrichment.

    Files whose frontmatter cannot be parsed are recorded in
    ``LAST_PARSE_ERRORS`` (path, exc-repr) and a warning is written to
    stderr; the caller (Routines post-loop) is expected to surface them as
    ``malformed_frontmatter`` BacklogItems rather than letting them vanish
    from observability. Truly unexpected exceptions (KeyboardInterrupt,
    MemoryError, ...) are not caught.
    """
    root = Path(vault_root) / "raw"
    LAST_PARSE_ERRORS.clear()
    if not root.exists():
        return []
    out: list[Candidate] = []
    for md_path in root.rglob("*.md"):
        try:
            fm, _body = read_frontmatter(str(md_path))
        except (ValueError, OSError, TypeError, KeyError) as exc:
            # Malformed frontmatter / unreadable file — surface for human
            # review instead of dropping silently (WR-03).
            LAST_PARSE_ERRORS.append((str(md_path), repr(exc)))
            print(
                f"[walk.find_candidates] WARN: unparseable frontmatter at {md_path}: {exc!r}",
                file=sys.stderr,
            )
            continue
        stored = fm.provenance.content_hash
        actual = compute_content_hash(str(md_path))
        # D-21 F-4c: skip_reason sticky unless hash changed
        if fm.derived.skip_reason is not None and stored == actual:
            continue
        # D-19: derived populated + hash stable -> skip
        if _derived_is_populated(fm) and stored == actual:
            continue
        reason = "hash_changed" if (stored and stored != actual) else "missing_derived"
        out.append(
            Candidate(
                path=str(md_path),
                source=fm.provenance.source,
                content_hash=actual,
                reason=reason,
            )
        )
    return out
