"""Vault writer for KIND events (D-08 layout, D-19 trust_level).

Path: `raw/kind/{YYYY}-{MM}/{event_type}_{ticker}_{event_date}.md` (D-08).
Event type must be one of KindEventType values (path traversal guard T-04-17).
ticker regex `^[0-9]{6}$`; event_date regex `^\\d{8}$`.

trust_level = "trusted" for all KIND events (D-24 — KRX/DART/KIND are official).
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

from collectors.kind.sources import KindEventType
from shared.content_hash import normalize_body
from shared.frontmatter import (
    FrontMatter,
    ProvenanceBlock,
    read_existing_derived,
    write_frontmatter,
)

_TICKER_RE = re.compile(r"^[0-9]{6}$")
_EVENT_DATE_RE = re.compile(r"^\d{8}$")
_ALLOWED_EVENTS = {e.value for e in KindEventType}


def vault_path_for_kind(
    vault_root: Path,
    event_type: str,
    ticker: str,
    event_date: str,
) -> Path:
    """Return the canonical vault path for a KIND event file (T-04-17 guarded)."""
    if event_type not in _ALLOWED_EVENTS:
        raise ValueError(f"bad event_type {event_type!r}")
    if not _TICKER_RE.match(ticker):
        raise ValueError(f"bad ticker {ticker!r}")
    if not _EVENT_DATE_RE.match(event_date):
        raise ValueError(f"bad event_date {event_date!r}")
    yyyy = event_date[:4]
    mm = event_date[4:6]
    return (
        Path(vault_root)
        / "raw"
        / "kind"
        / f"{yyyy}-{mm}"
        / f"{event_type}_{ticker}_{event_date}.md"
    )


def compute_body_hash(body: str) -> str:
    """sha256 hex of `normalize_body(body)` — idempotency key for COLL-08."""
    return hashlib.sha256(normalize_body(body).encode("utf-8")).hexdigest()


def _render_body(
    *,
    event_type: str,
    company_name: str | None,
    ticker: str,
    event_date: str,
    reason: str,
    subtype: str | None,
    source: str,
) -> str:
    title = f"{event_type.replace('_', ' ').title()} — {company_name or ticker}"
    return (
        f"# {title}\n\n"
        f"- ticker: {ticker}\n"
        f"- event_type: {event_type}\n"
        f"- event_date: {event_date}\n"
        f"- subtype: {subtype or '-'}\n"
        f"- reason: {reason}\n"
        f"- source: {source}\n"
    )


def _read_existing_hash(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"content_hash:\s*([0-9a-f]+)", text)
    return m.group(1) if m else None


def write_kind_event(
    *,
    vault_root: Path,
    event_type: str,
    ticker: str,
    event_date: str,
    corp_code: str | None,
    company_name: str | None,
    reason: str,
    source: str,
    source_id: str | None,
    source_url: str,
    subtype: str | None = None,
) -> tuple[Path, str, bool]:
    """Write a single KIND event to the vault. Returns (path, content_hash, rewrote).

    `rewrote` is True when the file was newly written or content changed;
    False when an identical content_hash was already on disk (idempotent skip).
    """
    path = vault_path_for_kind(vault_root, event_type, ticker, event_date)
    path.parent.mkdir(parents=True, exist_ok=True)

    body = _render_body(
        event_type=event_type,
        company_name=company_name,
        ticker=ticker,
        event_date=event_date,
        reason=reason,
        subtype=subtype,
        source=source,
    )
    new_hash = compute_body_hash(body)
    if path.exists() and _read_existing_hash(path) == new_hash:
        return path, new_hash, False

    date_iso = f"{event_date[0:4]}-{event_date[4:6]}-{event_date[6:8]}"
    # Quick task 260426-k8h: carry prior _derived block forward verbatim.
    prior_derived = read_existing_derived(path)
    fm = FrontMatter(
        provenance=ProvenanceBlock(
            source="kind",
            source_id=source_id,
            source_url=source_url,
            date=date_iso,
            fetched_at=datetime.now(UTC),
            content_hash=new_hash,
            corp_code=corp_code,
            ticker=ticker,
            company_name=company_name,
            lang="ko",
            trust_level="trusted",
        ),
        **({"derived": prior_derived} if prior_derived is not None else {}),
    )
    write_frontmatter(str(path), fm, body)
    return path, new_hash, True
