"""Vault writer for macro (ECOS/FRED) docs — COLL-04, D-07, D-24.

One file per series at `raw/macro/{source}/{series_id}.md`. Observations
are emitted in BOTH:
  1. frontmatter.provenance.observations (structured, D-07)
  2. body markdown table (human-readable)

Append-style idempotency: re-running reads existing frontmatter
observations, merges by (date,value), recomputes the body hash, and only
rewrites the file if the hash changed. Same-date/different-value triggers
an R-06 revision entry surfaced to the caller for heartbeat logging.

T-04-08: series_id must match ^[A-Z0-9_-]{1,32}$ and source must be in
{'ecos','fred'} before reaching Path.joinpath (path-traversal guard).
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

from shared.content_hash import normalize_body
from shared.frontmatter import (
    FrontMatter,
    ProvenanceBlock,
    read_existing_derived,
    read_frontmatter,
    write_frontmatter,
)

_SERIES_RE = re.compile(r"^[A-Z0-9_\-]{1,32}$")
_ALLOWED_SOURCES = frozenset({"ecos", "fred"})


def vault_path_for_macro(vault_root: Path, source: str, series_id: str) -> Path:
    """Canonical vault path `{vault_root}/raw/macro/{source}/{series_id}.md`."""
    if source not in _ALLOWED_SOURCES:
        raise ValueError(f"bad source {source!r}")
    if not _SERIES_RE.match(series_id):
        raise ValueError(f"bad series_id {series_id!r}")
    return Path(vault_root) / "raw" / "macro" / source / f"{series_id}.md"


def _obs_date_str(o) -> str:
    d = o["date"] if isinstance(o, dict) else o.date
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def _obs_value(o) -> float:
    return float(o["value"] if isinstance(o, dict) else o.value)


def _render_body(label: str, observations: list[dict]) -> str:
    lines = [f"## {label}", "", "| date | value |", "|---|---|"]
    for o in observations:
        lines.append(f"| {_obs_date_str(o)} | {_obs_value(o)} |")
    return "\n".join(lines) + "\n"


def _read_existing_observations(path: Path) -> list[dict]:
    """Return existing frontmatter observations as plain dicts [{date, value}]."""
    if not path.exists():
        return []
    try:
        fm, _ = read_frontmatter(str(path))
        obs = fm.provenance.observations or []
    except Exception:
        return []
    return [{"date": o.date.isoformat(), "value": float(o.value)} for o in obs]


def merge_observations(existing: list[dict], new: list[dict]) -> tuple[list[dict], list[dict]]:
    """R-06: dedup by (date,value); surface same-date value changes.

    Rules:
      - Identical (date,value) in both: skip (dedup).
      - New date not in existing: append.
      - Same date, different value: new value wins, revision recorded.

    Returns (merged_sorted_by_date, revisions).
    """
    by_date: dict[str, dict] = {
        _obs_date_str(o): {"date": _obs_date_str(o), "value": _obs_value(o)} for o in existing
    }
    revisions: list[dict] = []
    for o in new:
        date_s = _obs_date_str(o)
        val = _obs_value(o)
        prev = by_date.get(date_s)
        if prev is not None and prev["value"] != val:
            revisions.append({"date": date_s, "old_value": prev["value"], "new_value": val})
        by_date[date_s] = {"date": date_s, "value": val}
    merged = sorted(by_date.values(), key=lambda x: x["date"])
    return merged, revisions


def _body_hash(body: str) -> str:
    return hashlib.sha256(normalize_body(body).encode("utf-8")).hexdigest()


def write_macro_doc(
    *,
    vault_root: Path,
    source: str,
    series_id: str,
    label: str,
    observations: list[dict],
    source_url: str,
) -> tuple[Path, str, bool, list[dict]]:
    """Write one macro doc. Returns (path, content_hash, rewrote, revisions).

    `rewrote=False` means the merged body hash equals the existing file's
    frontmatter content_hash — no write performed.
    `revisions` (R-06) is the list produced by merge_observations; empty
    when no same-date/different-value change occurred.
    """
    path = vault_path_for_macro(vault_root, source, series_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = _read_existing_observations(path)
    merged, revisions = merge_observations(existing, observations)
    body = _render_body(label, merged)
    content_hash = _body_hash(body)

    existing_hash: str | None = None
    if path.exists():
        try:
            fm_prev, _ = read_frontmatter(str(path))
            existing_hash = fm_prev.provenance.content_hash
        except Exception:
            existing_hash = None

    if existing_hash == content_hash:
        return path, content_hash, False, revisions

    # Quick task 260426-k8h: carry prior _derived block forward verbatim so
    # collector rewrite does not wipe Routine-enriched enrichment.
    prior_derived = read_existing_derived(path)
    fm = FrontMatter(
        provenance=ProvenanceBlock(
            source=source,
            source_id=series_id,
            source_url=source_url,
            date=datetime.now(UTC).date().isoformat(),
            fetched_at=datetime.now(UTC),
            content_hash=content_hash,
            corp_code=None,
            ticker=None,
            company_name=None,
            lang="ko" if source == "ecos" else "en",
            trust_level="trusted",
            observations=merged,  # D-07
        ),
        **({"derived": prior_derived} if prior_derived is not None else {}),
    )
    write_frontmatter(str(path), fm, body)
    return path, content_hash, True, revisions
