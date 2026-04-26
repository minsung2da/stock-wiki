"""Vault writer for KRX docs (COLL-02, D-05, D-24).

Composes one merged ProvenanceBlock per (ticker, date_iso) — OHLCV + investor
flow + short balance — and writes atomically under `raw/krx/YYYY-MM-DD/{ticker}.md`.

trust_level='trusted' (D-24) — KRX is the canonical price/flow authority.

Path traversal defense (T-04-04): ticker must match `^[0-9]{6}$` and date_iso
must match `^\\d{4}-\\d{2}-\\d{2}$` before reaching `Path.joinpath`.

Body rendering uses `pandas.DataFrame.to_markdown(index=True)` which requires
`tabulate` (added to collectors dep group in Plan 02).
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from shared.content_hash import normalize_body
from shared.frontmatter import (
    FrontMatter,
    IngestStateBlock,
    ProvenanceBlock,
    read_existing_derived,
    read_existing_injection_flags,
    write_frontmatter,
)

_TICKER_RE = re.compile(r"^[0-9]{6}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

KRX_SOURCE_URL_DEFAULT = "https://data.krx.co.kr/"


def compute_body_hash(body: str) -> str:
    """sha256 hex digest of the normalized body — idempotency key (COLL-08)."""
    return hashlib.sha256(normalize_body(body).encode("utf-8")).hexdigest()


def vault_path_for_krx(vault_root: Path, date_iso: str, ticker: str) -> Path:
    """Canonical vault path `{vault_root}/raw/krx/{date_iso}/{ticker}.md`.

    Raises ValueError if ticker or date_iso fail regex guards (T-04-04).
    """
    if not _TICKER_RE.match(ticker):
        raise ValueError(f"bad ticker (need 6 ASCII digits): {ticker!r}")
    if not _DATE_RE.match(date_iso):
        raise ValueError(f"bad date_iso (need YYYY-MM-DD): {date_iso!r}")
    return Path(vault_root) / "raw" / "krx" / date_iso / f"{ticker}.md"


def _render_body(ohlcv: pd.DataFrame, flow: pd.DataFrame, short: pd.DataFrame) -> str:
    """Render the three KRX data sections as a single markdown body."""
    parts = [
        "## OHLCV\n\n",
        ohlcv.to_markdown(index=True),
        "\n\n## Investor Flow (KRW 순매수)\n\n",
        flow.to_markdown(index=True),
        "\n\n## Short Balance\n\n",
        short.to_markdown(index=True),
        "\n",
    ]
    return "".join(parts)


def write_krx_doc(
    *,
    vault_root: Path,
    ticker: str,
    date_iso: str,
    corp_code: str | None,
    company_name: str | None,
    ohlcv: pd.DataFrame,
    flow: pd.DataFrame,
    short: pd.DataFrame,
    source_url: str = KRX_SOURCE_URL_DEFAULT,
) -> tuple[Path, str]:
    """Write one KRX merged doc. Returns (path, content_hash)."""
    path = vault_path_for_krx(vault_root, date_iso, ticker)
    path.parent.mkdir(parents=True, exist_ok=True)

    body = _render_body(ohlcv, flow, short)
    content_hash = compute_body_hash(body)

    # Quick task 260426-k8h: carry prior _derived block forward verbatim.
    # Quick task 260426-mic: also carry ingest_state.injection_flags (D-18).
    prior_derived = read_existing_derived(path)
    prior_injection_flags = read_existing_injection_flags(path)
    fm = FrontMatter(
        provenance=ProvenanceBlock(
            source="krx",
            source_id=f"{ticker}_{date_iso}",
            source_url=source_url,
            date=date_iso,
            fetched_at=datetime.now(UTC),
            content_hash=content_hash,
            corp_code=corp_code,
            ticker=ticker,
            company_name=company_name,
            lang="ko",
            trust_level="trusted",
        ),
        **(
            {"ingest_state": IngestStateBlock(injection_flags=prior_injection_flags)}
            if prior_injection_flags is not None
            else {}
        ),
        **({"derived": prior_derived} if prior_derived is not None else {}),
    )
    write_frontmatter(str(path), fm, body)
    return path, content_hash
