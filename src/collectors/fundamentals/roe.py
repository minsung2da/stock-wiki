"""ROE derivation from dart-fss structured financials (D-06).

ROE = 당기순이익 / 자본총계 (net income / total equity). Reuses
``collectors.dart.financials.get_structured_financials`` — the LLM-free
structured accessor (COLL-07: no LLM SDK imports anywhere under ``collectors/``;
this module imports only the in-tree DART helper, which itself lazy-imports
dart-fss, never an LLM).

Veto #6: ROE is a pure number written to a typed NUMERIC column — never embedded.

Divide-by-zero / missing-line-item guard: if 자본총계 is absent, zero, or
당기순이익 is absent, ``compute_roe`` returns ``None`` (the collector then writes
roe=NULL, and the db_writer COALESCE preserves any prior value).
"""

from __future__ import annotations

import logging

from collectors.dart.financials import get_structured_financials

_log = logging.getLogger(__name__)

__all__ = ["compute_roe"]

_NET_INCOME_KEY = "당기순이익"
_TOTAL_EQUITY_KEY = "자본총계"


def compute_roe(corp_code: str, bgn_de: str) -> float | None:
    """Compute ROE = 당기순이익 / 자본총계 from DART structured financials.

    Args:
        corp_code: 8-digit DART corp_code.
        bgn_de: earliest reporting date, ``YYYYMMDD``.

    Returns:
        ROE as a float (e.g. 0.1234 = 12.34%), or ``None`` when either line item
        is missing or 자본총계 is zero (divide-by-zero guard).
    """
    facts = get_structured_financials(corp_code, bgn_de)
    by_key = {f.key: f.value for f in facts}

    net_income = by_key.get(_NET_INCOME_KEY)
    total_equity = by_key.get(_TOTAL_EQUITY_KEY)

    if net_income is None or total_equity is None:
        return None
    if total_equity == 0:
        _log.warning(
            "fundamentals.roe: 자본총계 is zero for corp_code %s — ROE undefined", corp_code
        )
        return None

    return net_income / total_equity
