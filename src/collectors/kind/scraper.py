"""KIND AJAX scraper — undisclosure (불성실공시) parser (Option D auxiliary).

The captured warning_risky_list.html was a search-form shell, not the data
fragment, so 투자경고/위험 scraping is deferred (see sources.py docstring +
04-05-SUMMARY.md §Deferred). Only the undisclosure AJAX path is implemented
here; it supplements DART `pblntf_ty="I"` 불성실공시법인지정 events with
KIND's own 지정 record (indexed differently — by company rather than by
rcept_no).

The KIND undisclosure AJAX fragment has no ticker column — rows are keyed by
company name. Scope filtering therefore requires a name→ticker lookup via
`db.entity.resolve_entity_by_alias`.
"""

from __future__ import annotations

import logging
from typing import Any

from collectors.kind import client as kind_client
from collectors.kind import selectors
from collectors.kind.selectors import ParseError
from collectors.kind.sources import KIND_UNDISCLOSURE_URL, KindEventType

_log = logging.getLogger(__name__)


def parse_undisclosure_fragment(html: str) -> list[dict[str, Any]]:
    """Parse a KIND undisclosure AJAX HTML fragment (EUC-KR decoded) into rows.

    Returns a list of dicts: {company_name, subtype, event_date, reason}.
    `event_date` is normalized to YYYYMMDD (raw value is YYYY-MM-DD).

    Raises ParseError if the `<table class="list">` element or any data row
    is missing expected structure (D-17 silent-pass forbidden).
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one(selectors.UNDISCLOSURE_TABLE)
    if table is None:
        raise ParseError(f"selector miss: {selectors.UNDISCLOSURE_TABLE}")

    rows = table.select("tbody > tr")
    out: list[dict[str, Any]] = []
    for row in rows:
        cells = row.find_all("td")
        if not cells:
            # Header/empty placeholder rows — skip silently.
            continue
        if (
            len(cells)
            < max(
                selectors.UNDISCLOSURE_CELL_COMPANY,
                selectors.UNDISCLOSURE_CELL_SUBTYPE,
                selectors.UNDISCLOSURE_CELL_DATE,
                selectors.UNDISCLOSURE_CELL_REASON,
            )
            + 1
        ):
            raise ParseError(
                f"row has {len(cells)} cells; expected at least "
                f"{selectors.UNDISCLOSURE_CELL_REASON + 1}"
            )
        company = cells[selectors.UNDISCLOSURE_CELL_COMPANY].get_text(strip=True)
        subtype = cells[selectors.UNDISCLOSURE_CELL_SUBTYPE].get_text(strip=True)
        date_raw = cells[selectors.UNDISCLOSURE_CELL_DATE].get_text(strip=True)
        reason = cells[selectors.UNDISCLOSURE_CELL_REASON].get_text(strip=True)
        event_date = date_raw.replace("-", "").replace(".", "").strip()
        if not company or not event_date:
            # Row missing key fields — treat as drift.
            raise ParseError(f"row missing company/date: {company!r} {date_raw!r}")
        out.append(
            {
                "company_name": company,
                "subtype": subtype or None,
                "event_date": event_date,
                "reason": reason or "불성실공시법인지정",
            }
        )
    return out


def fetch_undisclosure_events(max_pages: int = 3) -> list[dict[str, Any]]:
    """Fetch + parse KIND undisclosure AJAX pages. Returns event-dict list.

    Each event carries `event_type=unfaithful_disclosure`. The caller is
    responsible for resolving `company_name` → ticker via entity_aliases.
    `source_id` is a synthesized `kind_undiscl_{company}_{event_date}` key
    (KIND offers no stable id for these rows).
    """
    events: list[dict[str, Any]] = []
    for page_index in range(1, max_pages + 1):
        resp = kind_client.throttled_post(
            KIND_UNDISCLOSURE_URL,
            data={
                "method": "searchUnfaithfulDisclosureCorpSub",
                "currentPageSize": 15,
                "pageIndex": page_index,
                "forward": "undisclosure_sub",
            },
        )
        resp.raise_for_status()
        html = kind_client.decode_euckr(resp)
        rows = parse_undisclosure_fragment(html)
        if not rows:
            break
        for r in rows:
            events.append(
                {
                    "event_type": KindEventType.UNFAITHFUL_DISCLOSURE.value,
                    "ticker": None,  # caller resolves by company_name
                    "corp_code": None,
                    "company_name": r["company_name"],
                    "event_date": r["event_date"],
                    "reason": r["reason"],
                    "source_id": f"kind_undiscl_{r['company_name']}_{r['event_date']}",
                    "source_url": KIND_UNDISCLOSURE_URL,
                    "subtype": r.get("subtype"),
                }
            )
        # If this page had fewer than 15 rows, we're done.
        if len(rows) < 15:
            break
    return events
