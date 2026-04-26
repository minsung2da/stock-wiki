"""Vault writer for DART filings (COLL-06, D-19).

Composes a ProvenanceBlock (trust_level='trusted' per D-19), builds the
FrontMatter model, and writes atomically via shared.frontmatter.write_frontmatter.
Computes content_hash on the normalized body BEFORE writing so the hash
ends up inside the frontmatter (idempotency key for COLL-08).

Path traversal defense (T-3-12): rcept_no and corp_code are digit-only strings
from dart-fss; no user-supplied component reaches Path construction.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shared.content_hash import normalize_body
from shared.frontmatter import (
    FrontMatter,
    IngestStateBlock,
    ProvenanceBlock,
    read_existing_derived,
    read_existing_injection_flags,
    write_frontmatter,
)

DART_FILING_URL_TMPL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


def vault_path_for(filing: Any, corp_code: str, vault_root: Path) -> Path:
    """Return the canonical vault path for a filing.

    Layout: `{vault_root}/raw/dart/{YYYY}/{rcept_no}_{corp_code}.md`
    where YYYY is taken from `filing.rcept_dt[:4]` ("YYYYMMDD" string).
    """
    rcept_dt = str(filing.rcept_dt)
    year = rcept_dt[:4]
    rcept_no = str(filing.rcept_no)
    return vault_root / "raw" / "dart" / year / f"{rcept_no}_{corp_code}.md"


def compute_body_hash(body: str) -> str:
    """sha256 hex digest of `normalize_body(body)` — matches
    shared.content_hash.compute_content_hash() output for equivalent text.

    Kept as a separate helper so the collector can hash in-memory bodies
    without writing to disk first.
    """
    return hashlib.sha256(normalize_body(body).encode("utf-8")).hexdigest()


def write_filing(
    filing: Any,
    body: str,
    corp_code: str,
    ticker: str | None,
    vault_root: Path,
    company_name: str | None = None,
) -> tuple[Path, str]:
    """Write one filing to the vault. Returns (path, content_hash).

    - trust_level='trusted' (D-19) because DART is the canonical 공시 source.
    - content_hash is computed on the normalized body and stored in frontmatter.
    - fetched_at is UTC now; date is parsed from filing.rcept_dt.
    """
    path = vault_path_for(filing, corp_code, vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    rcept_no = str(filing.rcept_no)
    rcept_dt = str(filing.rcept_dt)
    date_iso = f"{rcept_dt[0:4]}-{rcept_dt[4:6]}-{rcept_dt[6:8]}"
    content_hash = compute_body_hash(body)

    # Quick task 260426-k8h: carry prior _derived block forward verbatim.
    # Quick task 260426-mic: also carry ingest_state.injection_flags (D-18).
    prior_derived = read_existing_derived(path)
    prior_injection_flags = read_existing_injection_flags(path)
    fm = FrontMatter(
        provenance=ProvenanceBlock(
            source="dart",
            source_id=rcept_no,
            source_url=DART_FILING_URL_TMPL.format(rcept_no=rcept_no),
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
