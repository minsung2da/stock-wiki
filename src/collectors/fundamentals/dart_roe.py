"""Official DART annual ROE observations; stored as a ratio, displayed as percent.

The endpoint returns current published values, not historical point-in-time
reconstructions. Keep the settlement date and acquisition timestamp separately.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

import requests  # type: ignore[import-untyped]

ENDPOINT = "https://opendart.fss.or.kr/api/fnlttSinglIndx.json"


@dataclass(frozen=True)
class RoeObservation:
    value: Decimal
    period_end: date
    source: str
    fetched_at: datetime


def fetch_annual_roe(corp_code: str, year: int) -> RoeObservation | None:
    """Fetch annual M211550 (ROE); absent official data stays None.

    Authentication and transport errors expose only sanitized codes, never
    request URLs containing the API credential. No fallback to another year.
    """
    if not re.fullmatch(r"\d{8}", corp_code) or not 2023 <= year <= 9998:
        raise ValueError("invalid_roe_scope")
    key = os.environ.get("DART_API_KEY")
    if not key:
        raise RuntimeError("dart_key_missing")
    params = {
        "crtfc_key": key,
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": "11011",
        "idx_cl_code": "M210000",
    }
    try:
        response = requests.get(ENDPOINT, params=params, timeout=(5, 20))
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        raise RuntimeError("dart_roe_request_failed") from None
    if not isinstance(payload, dict):
        raise ValueError("dart_roe_invalid_response")
    if payload.get("status") == "013":
        return None
    if payload.get("status") != "000":
        code = str(payload.get("status", "unknown"))
        raise RuntimeError(
            "dart_roe_status_" + (code if re.fullmatch(r"\d{3}", code) else "unknown")
        )
    rows = payload.get("list")
    if not isinstance(rows, list):
        raise ValueError("dart_roe_invalid_response")
    matches = [row for row in rows if isinstance(row, dict) and row.get("idx_code") == "M211550"]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("dart_roe_ambiguous_response")
    row = matches[0]
    if (
        row.get("corp_code") != corp_code
        or row.get("bsns_year") != str(year)
        or row.get("reprt_code") != "11011"
        or row.get("idx_cl_code") != "M210000"
        or row.get("idx_nm") != "ROE"
    ):
        raise ValueError("dart_roe_scope_mismatch")
    raw = row.get("idx_val")
    if raw is None or str(raw).strip() in {"", "-"}:
        return None
    try:
        value = Decimal(str(raw).replace(",", "")) / 100
        period_end = date.fromisoformat(row["stlm_dt"])
    except (InvalidOperation, ValueError, KeyError, TypeError):
        raise ValueError("dart_roe_invalid_value") from None
    if not value.is_finite() or period_end.year != year:
        raise ValueError("dart_roe_invalid_value")
    source = (
        f"{ENDPOINT}?corp_code={corp_code}&bsns_year={year}"
        "&reprt_code=11011&idx_cl_code=M210000&idx_code=M211550"
    )
    return RoeObservation(value, period_end, source, datetime.now(UTC))
