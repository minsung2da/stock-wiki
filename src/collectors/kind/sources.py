"""KIND collector source constants (Plan 05, Option D strategy).

Option D supersedes D-14's original pykrx-based hybrid. Live verification on
2026-04-20 confirmed pykrx exposes no `get_market_status_by_ticker` function
(nor equivalent in master branch) — pykrx covers only market-price data, not
exchange status designations. Exchange-issued status events (거래정지, 관리종목,
투자경고, 불성실공시) are **fundamental-axis** evaluations by the exchange about
the issuer, and must therefore be sourced from DART and KIND — not pykrx.

Primary source = **DART `pblntf_ty="I"` (거래소공시)**:
- Verified 30-day window: 190 거래정지 + 16 관리종목지정우려 + 23 불성실공시
  filings. Classification is by `report_nm` regex because `pblntf_detail_ty`
  is None across all samples.

Auxiliary source = **KIND `undisclosure.do` AJAX** (reference only; EUC-KR):
- Returns structured HTML fragment with <table class="list">. Used for
  cross-check / enrichment, NOT as the primary write path (DART already
  captures these events with higher fidelity via rcept_no).

Investment caution / investment risk (투자경고/위험) scraping is DEFERRED:
the live captured warning_risky_list.html is a search-form shell, not a
data fragment — a separate AJAX endpoint probe is needed. DART 30-day window
produced 0 such filings, so these events remain a known gap documented in
04-05-SUMMARY.md §Deferred.
"""

from __future__ import annotations

import re
from enum import Enum


class KindEventType(str, Enum):
    """D-08 event_type enum — stable identifiers for vault file names.

    Additions since original plan: INVESTMENT_RISK (KIND distinguishes
    투자경고 vs 투자위험), DELISTING and LISTING_ELIGIBILITY_REVIEW remain
    behind a flag (see DART_EXCHANGE_EVENT_PATTERNS_EXTENDED).
    """

    SUSPENSION = "suspension"
    WATCHLIST_DESIGNATION = "watchlist_designation"
    INVESTMENT_CAUTION = "investment_caution"
    INVESTMENT_RISK = "investment_risk"
    UNFAITHFUL_DISCLOSURE = "unfaithful_disclosure"


# --- DART 거래소공시 (pblntf_ty="I") classification ---
# Verified 2026-04-20 via `dart_fss.filings.search(pblntf_ty="I")` over a
# 30-day window. Patterns match `report_nm`; order matters (more specific
# first) but current regexes are mutually disjoint.
DART_EXCHANGE_EVENT_PATTERNS: dict[str, re.Pattern[str]] = {
    KindEventType.SUSPENSION.value: re.compile(r"주권매매거래정지"),
    KindEventType.WATCHLIST_DESIGNATION.value: re.compile(r"관리종목지정우려"),
    KindEventType.UNFAITHFUL_DISCLOSURE.value: re.compile(r"불성실공시법인지정"),
}

# Optional extras — enable only when a collector caller explicitly opts in.
# Left disabled by default so the vault layout keeps the D-08 enum stable.
DART_EXCHANGE_EVENT_PATTERNS_EXTENDED: dict[str, re.Pattern[str]] = {
    "delisting": re.compile(r"상장폐지"),
    "listing_eligibility_review": re.compile(r"상장적격성\s*실질심사"),
}


def classify_dart_exchange_event(report_nm: str) -> str | None:
    """Map a DART pblntf_ty="I" filing's `report_nm` to an event_type enum value.

    Returns None if no primary pattern matches (caller should skip the filing).
    Probe data showed `pblntf_detail_ty` is None across samples, so `report_nm`
    is the authoritative classifier. Strings like '주권매매거래정지기간변경'
    still match the SUSPENSION pattern by design (it is still a suspension
    lifecycle event).
    """
    if not report_nm:
        return None
    for event_type, pattern in DART_EXCHANGE_EVENT_PATTERNS.items():
        if pattern.search(report_nm):
            return event_type
    return None


# --- KIND endpoints (verified HTTP 200 on 2026-04-20) ---
KIND_BASE = "https://kind.krx.co.kr"

# Primary page for 투자경고/위험 landing (shell only — live data is AJAX-loaded;
# captured fixture warning_risky_list.html is the shell, not the data fragment).
KIND_WARNING_RISKY_URL = (
    f"{KIND_BASE}/investwarn/investattentwarnrisky.do?method=investattentwarnriskyMain"
)

# AJAX POST target for 불성실공시 AJAX fragment. Required params:
#   method=searchUnfaithfulDisclosureCorpSub
#   currentPageSize=15
#   pageIndex=1
#   forward=undisclosure_sub
# Response is EUC-KR-encoded HTML with <table class="list"> + 15 rows/page.
KIND_UNDISCLOSURE_URL = f"{KIND_BASE}/investwarn/undisclosure.do"

# --- Browser-like User-Agent (WAF rejects minimal UAs) ---
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
