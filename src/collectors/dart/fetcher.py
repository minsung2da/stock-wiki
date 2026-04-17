"""DART filing list + body accessors (D-01, D-04).

D-01: Only 공시유형 A(정기보고서) + B(주요사항보고서) are collected. C/D are
scaffolded in the source_type enum but not fetched in Phase 3.

D-04: Attachments (PDF/HWP) are NOT parsed. Body text only.

`fetch_body` retries transient failures (network flakes, DART rate limit
spikes) via tenacity — dart-fss itself also retries, but tenacity adds a
second layer of safety for the `.pages` iteration.
"""

from __future__ import annotations

from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from collectors.dart import client


def list_ab_filings(corp_code: str, since: str, max_docs: int) -> list[Any]:
    """List A+B filings for a corp since a date, capped at max_docs (D-03).

    Parameters
    ----------
    corp_code : str
        8-digit DART corp code.
    since : str
        ISO date "YYYY-MM-DD" — converted to dart-fss "YYYYMMDD" internally.
    max_docs : int
        Phase-3 cap (D-03).

    Returns
    -------
    list
        dart-fss Report instances (up to max_docs).
    """
    corp = client.find_corp(corp_code)
    bgn_de = since.replace("-", "")
    results = corp.search_filings(
        bgn_de=bgn_de,
        pblntf_ty=["A", "B"],  # D-01: only 정기 + 주요사항
        last_reprt_at="Y",
    )
    # SearchResults.report_list holds Report instances; fallback to iter(results)
    # for mock stubs that return a plain list.
    report_list = getattr(results, "report_list", results)
    return list(report_list)[:max_docs]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.3, max=2.0),
    reraise=True,
)
def fetch_body(filing: Any) -> str:
    """Return the body text of a DART filing.

    Strategy:
    1. Prefer `.pages` iteration + HTML→text extraction (canonical for
       정기보고서, keeps section ordering for D-07 downstream parsing).
    2. Fallback to `filing.to_dict()` textual fields for short 주요사항보고서.
    3. Return empty string rather than raising on a genuinely empty body.
    """
    pages = getattr(filing, "pages", None)
    if pages:
        texts: list[str] = []
        for page in pages:
            html = getattr(page, "html", "") or ""
            if not html:
                continue
            texts.append(_strip_html(html))
        body = "\n\n".join(t for t in texts if t)
        if body:
            return body

    # Fallback: to_dict() may contain a textual summary for 주요사항보고서.
    to_dict = getattr(filing, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
        if isinstance(data, dict):
            text = data.get("text") or data.get("body") or ""
            if text:
                return str(text)
    return ""


def _strip_html(html: str) -> str:
    """Best-effort HTML→text extraction for DART page bodies.

    Uses BeautifulSoup when available (in collectors dep group); falls back
    to naive tag-stripping if not. Not a security primitive — output is
    still considered untrusted and must be wrapped per D-16/D-17 downstream.
    """
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-untyped]

        return BeautifulSoup(html, "lxml").get_text(separator="\n", strip=True)
    except ImportError:
        import re

        no_tags = re.sub(r"<[^>]+>", "", html)
        return re.sub(r"\n\s*\n+", "\n\n", no_tags).strip()
