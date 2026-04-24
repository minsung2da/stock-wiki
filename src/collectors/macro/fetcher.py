"""ECOS + FRED fetch wrappers. Return a list[{date, value}].

ECOS: PublicDataReader.Ecos.get_statistic_search returns a DataFrame that
must be row-filtered by ITEM_CODE1 when the catalog supplies one (live
probe confirmed that StatisticSearch returns multiple items under a
STAT_CODE otherwise). Date normalization: TIME is YYYYMMDD for cycle='D'
and YYYYMM for cycle='M'; we emit ISO dates (Monday of month for monthly
cycle is out of scope — we use the 1st).
"""

from __future__ import annotations

from datetime import date, timedelta

from collectors.macro.client import MacroEmptyResultError


def _normalize_ecos_time(t: str) -> str:
    t = str(t)
    if len(t) == 8:
        return f"{t[:4]}-{t[4:6]}-{t[6:8]}"
    if len(t) == 6:
        return f"{t[:4]}-{t[4:6]}-01"
    return t


def fetch_ecos_series(
    api,
    series_id: str,
    cycle: str,
    item_code: str,
    *,
    days_back: int = 365,
) -> list[dict]:
    """Fetch recent observations for an ECOS series. Raises MacroEmptyResultError
    if the filtered response is empty (R-05 per-series soft-fail)."""
    end = date.today()
    start = end - timedelta(days=days_back)
    fmt = "%Y%m%d" if cycle == "D" else "%Y%m"
    # Gap-04-04 fix: PublicDataReader does not translate the server-side
    # item-code kwarg into the ECOS URL's item-code segment — rows come back
    # unfiltered with mixed ITEM_CODE1 values, OR the library drops them
    # during parsing. Direct live verification (curl
    # ecos.bok.or.kr/api/StatisticSearch/...) confirms the data exists for
    # the configured item_code. We drop the server-side kwarg and rely on
    # the defensive ITEM_CODE1 filter below as the sole filter.
    # Rationale documented in 04-HUMAN-UAT.md Gap-04-04 fix_options.A.
    df = api.get_statistic_search(
        통계표코드=series_id,
        주기=cycle,
        검색시작일자=start.strftime(fmt),
        검색종료일자=end.strftime(fmt),
    )
    if df is None or len(df) == 0:
        raise MacroEmptyResultError(f"ECOS empty: {series_id}")

    # Gap-04-07 fix: PublicDataReader renames ECOS JSON keys to Korean in its
    # DataFrame output (ITEM_CODE1 → 통계항목코드1, TIME → 시점, DATA_VALUE → 값).
    # Accept either naming — tests mock with English keys, production uses Korean.
    def _pick(row: dict, *keys: str) -> str:
        for k in keys:
            v = row.get(k)
            if v is not None and str(v) != "":
                return str(v)
        return ""

    out: list[dict] = []
    for _, row in df.iterrows():
        row_item = _pick(row, "통계항목코드1", "ITEM_CODE1")
        if item_code and row_item != item_code:
            continue
        raw_v = _pick(row, "값", "DATA_VALUE")
        if raw_v == "":
            continue
        try:
            v = float(raw_v)
        except (TypeError, ValueError):
            continue
        raw_t = _pick(row, "시점", "TIME")
        if raw_t == "":
            continue
        out.append({"date": _normalize_ecos_time(raw_t), "value": v})
    if not out:
        raise MacroEmptyResultError(f"ECOS empty after filter: {series_id}")
    return out


def fetch_fred_series(fred, series_id: str, *, days_back: int = 365) -> list[dict]:
    """Fetch recent observations for a FRED series. Empty series → empty list
    (FRED legitimately returns empty for stale/delisted IDs; the caller decides
    whether that's a config bug — collect_macro treats it as soft-fail)."""
    import pandas as pd  # local import: pandas is a collectors-group dep

    series = fred.get_series(
        series_id,
        observation_start=(date.today() - timedelta(days=days_back)).isoformat(),
    )
    out: list[dict] = []
    for idx, v in series.items():
        if pd.isna(v):
            continue
        out.append({"date": idx.date().isoformat(), "value": float(v)})
    if not out:
        raise MacroEmptyResultError(f"FRED empty: {series_id}")
    return out
