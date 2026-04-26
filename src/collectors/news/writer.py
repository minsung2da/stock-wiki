"""Vault writer for news articles (D-06, D-13, D-24).

Path: `{vault_root}/raw/news/YYYY-MM/{outlet}_{url_hash8}.md`.
trust_level='semi_trusted' (D-24) — news outlets are semi-trusted, INGEST-08
will wrap body in XML delimiters downstream.
license_flag='summary_only' (D-13) — hard-capped to 2 paragraphs.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

from shared.content_hash import normalize_body
from shared.frontmatter import (
    FrontMatter,
    IngestStateBlock,
    ProvenanceBlock,
    TickerRef,
    read_existing_derived,
    read_existing_injection_flags,
    write_frontmatter,
)

_OUTLET_RE = re.compile(r"^(hankyung|edaily)$")
_YYYYMM_RE = re.compile(r"^\d{6}$")
_HASH8_RE = re.compile(r"^[0-9a-f]{8}$")


def vault_path_for_news(vault_root: Path, outlet: str, yyyymm: str, url_hash8: str) -> Path:
    if not _OUTLET_RE.match(outlet):
        raise ValueError(f"bad outlet {outlet!r}")
    if not _YYYYMM_RE.match(yyyymm):
        raise ValueError(f"bad yyyymm {yyyymm!r}")
    if not _HASH8_RE.match(url_hash8):
        raise ValueError(f"bad url_hash8 {url_hash8!r}")
    return (
        Path(vault_root)
        / "raw"
        / "news"
        / f"{yyyymm[:4]}-{yyyymm[4:]}"
        / f"{outlet}_{url_hash8}.md"
    )


def _assert_two_paragraph_cap(body: str) -> None:
    """D-13: body must contain ≤2 non-empty \\n\\n-separated paragraphs."""
    paragraphs = [p for p in body.split("\n\n") if p.strip()]
    if len(paragraphs) > 2:
        raise ValueError(f"news body exceeds 2-paragraph cap ({len(paragraphs)} paragraphs)")


def compute_news_content_hash(title: str, body: str) -> str:
    """Stable content hash: sha256(normalize_body(title + \\n\\n + body))."""
    return hashlib.sha256(normalize_body(f"{title}\n\n{body}").encode("utf-8")).hexdigest()


def write_news_doc(
    *,
    vault_root: Path,
    outlet: str,
    url: str,
    url_hash8: str,
    yyyymm: str,
    title: str,
    published_iso: str,
    tickers: list[dict],
    body: str,
) -> tuple[Path, str]:
    """Write one news article to the vault. Returns (path, content_hash)."""
    _assert_two_paragraph_cap(body)
    path = vault_path_for_news(vault_root, outlet, yyyymm, url_hash8)
    path.parent.mkdir(parents=True, exist_ok=True)
    content_hash = compute_news_content_hash(title, body)
    md_body = f"# {title}\n\n{body}\n"
    ticker_refs = [
        TickerRef(
            ticker=t["ticker"],
            corp_code=t.get("corp_code"),
            name=t.get("name"),
        )
        for t in tickers
    ]
    # Quick task 260426-k8h: carry prior _derived block forward verbatim.
    # Quick task 260426-mic: also carry ingest_state.injection_flags (D-18).
    prior_derived = read_existing_derived(path)
    prior_injection_flags = read_existing_injection_flags(path)
    fm = FrontMatter(
        provenance=ProvenanceBlock(
            source="news",
            source_id=url_hash8,
            source_url=url,
            date=published_iso[:10],
            fetched_at=datetime.now(UTC),
            content_hash=content_hash,
            corp_code=tickers[0]["corp_code"] if tickers else None,
            ticker=tickers[0]["ticker"] if tickers else None,
            company_name=tickers[0].get("name") if tickers else None,
            lang="ko",
            trust_level="semi_trusted",
            tickers=ticker_refs,
            outlet=outlet,
            license_flag="summary_only",
        ),
        **(
            {"ingest_state": IngestStateBlock(injection_flags=prior_injection_flags)}
            if prior_injection_flags is not None
            else {}
        ),
        **({"derived": prior_derived} if prior_derived is not None else {}),
    )
    write_frontmatter(str(path), fm, md_body)
    return path, content_hash
