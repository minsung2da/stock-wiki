"""DART 거래소공시 (pblntf_ty="I") event fetcher for KIND collector (Option D).

Calls `dart_fss.filings.search(pblntf_ty="I", bgn_de=..., end_de=...)` and
classifies each filing's `report_nm` via `classify_dart_exchange_event`.
Returns a list of dicts shaped for the writer (ticker, event_date, event_type,
company_name, reason, source_url, source_id).

Reuses `collectors.dart.client.get_client()` so the API key is initialized
exactly once per process.

Retries transient network failures via tenacity — same exception set as
`collectors.dart.fetcher`.
"""

from __future__ import annotations

import logging
from typing import Any

from requests.exceptions import ChunkedEncodingError
from requests.exceptions import ConnectionError as ReqConnectionError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from urllib3.exceptions import ProtocolError

from collectors.dart import client as dart_client
from collectors.kind.sources import classify_dart_exchange_event

_log = logging.getLogger(__name__)

_RETRYABLE_EXC: tuple[type[BaseException], ...] = (
    ReqConnectionError,
    ChunkedEncodingError,
    ProtocolError,
)

DART_FILING_URL_TMPL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1.0, min=1.0, max=30.0),
    retry=retry_if_exception_type(_RETRYABLE_EXC),
    before_sleep=before_sleep_log(_log, logging.WARNING),
    reraise=True,
)
def _search_exchange_filings(bgn_de: str, end_de: str, page_count: int = 100) -> list[Any]:
    """Search DART filings with pblntf_ty="I" (거래소공시) in a date window.

    bgn_de/end_de: "YYYYMMDD" strings. Returns a list of dart-fss Report-like
    objects (with `.rcept_no`, `.rcept_dt`, `.corp_code`, `.corp_name`,
    `.stock_code`, `.report_nm`). Iterates pages until exhausted.
    """
    dart_client.get_client()
    import dart_fss

    collected: list[Any] = []
    page_no = 1
    while True:
        results = dart_fss.filings.search(
            bgn_de=bgn_de,
            end_de=end_de,
            pblntf_ty="I",
            page_no=page_no,
            page_count=page_count,
        )
        report_list = getattr(results, "report_list", results)
        reports = list(report_list)
        collected.extend(reports)
        # Stop if fewer results than page_count (last page).
        if len(reports) < page_count:
            break
        page_no += 1
    return collected


def fetch_exchange_events(
    *,
    bgn_de: str,
    end_de: str,
) -> list[dict[str, Any]]:
    """Fetch DART pblntf_ty="I" filings and classify them into event dicts.

    Filings whose `report_nm` doesn't match any primary event pattern are
    dropped (not an error — most 거래소공시 filings are outside our scope).

    Returns a list of dicts with keys:
      event_type, ticker, company_name, corp_code, event_date (YYYYMMDD),
      reason (report_nm), source_url, source_id (rcept_no).
    """
    reports = _search_exchange_filings(bgn_de, end_de)
    events: list[dict[str, Any]] = []
    for r in reports:
        report_nm = getattr(r, "report_nm", None) or ""
        event_type = classify_dart_exchange_event(report_nm)
        if event_type is None:
            continue
        rcept_no = str(getattr(r, "rcept_no", "") or "")
        rcept_dt = str(getattr(r, "rcept_dt", "") or "")
        events.append(
            {
                "event_type": event_type,
                "ticker": getattr(r, "stock_code", None) or None,
                "corp_code": getattr(r, "corp_code", None) or None,
                "company_name": getattr(r, "corp_name", None) or None,
                "event_date": rcept_dt,  # YYYYMMDD
                "reason": report_nm,
                "source_id": rcept_no,
                "source_url": DART_FILING_URL_TMPL.format(rcept_no=rcept_no),
            }
        )
    return events
