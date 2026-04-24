"""LLM-free DART financial-statement accessor (D-14, INGEST-06).

Calls dart-fss `fs.extract()` and maps canonical Korean line items into
NumericFact records. NO LLM involvement. COLL-07 preserved: this module
is in src/collectors/ and must never depend on LLM SDKs (see COLL-07 guard
test).

Pitfall 5: IFRS label_ko naming varies ("매출액" vs "수익(매출액)" vs "영업수익").
LINE_ITEM_SYNONYMS below maps canonical key → observed variants. Expand as
disagreements surface via backlog.md `dart_structured_disagreement` counts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

from shared.frontmatter import NumericFact

_PERIOD_COL_RE = re.compile(r"^\d{8}$")


@dataclass(frozen=True)
class StructuredFact:
    """Internal intermediate shape — used only within this module."""

    key: str
    value: float


# Canonical Korean line-item → set of observed label_ko variants.
# Canonical MUST appear in its own set (test_synonyms_preserve_canonical_in_own_set).
LINE_ITEM_SYNONYMS: dict[str, frozenset[str]] = {
    # Income statement
    "매출액": frozenset({"매출액", "수익(매출액)", "매출", "영업수익"}),
    "영업이익": frozenset({"영업이익", "영업이익(손실)"}),
    "영업손익": frozenset({"영업손익"}),
    "당기순이익": frozenset({"당기순이익", "당기순이익(손실)", "당기순손익"}),
    "매출원가": frozenset({"매출원가"}),
    "매출총이익": frozenset({"매출총이익", "매출총이익(손실)"}),
    "판매비와관리비": frozenset({"판매비와관리비"}),
    "금융수익": frozenset({"금융수익"}),
    "금융비용": frozenset({"금융비용"}),
    "법인세비용": frozenset({"법인세비용", "법인세비용(수익)"}),
    # Balance sheet
    "자산총계": frozenset({"자산총계"}),
    "부채총계": frozenset({"부채총계"}),
    "자본총계": frozenset({"자본총계"}),
    "유동자산": frozenset({"유동자산"}),
    "비유동자산": frozenset({"비유동자산"}),
    "유동부채": frozenset({"유동부채"}),
    "비유동부채": frozenset({"비유동부채"}),
    "이익잉여금": frozenset({"이익잉여금", "이익잉여금(결손금)"}),
    "자본금": frozenset({"자본금"}),
    # Cash flow
    "영업활동현금흐름": frozenset({"영업활동현금흐름", "영업활동으로 인한 현금흐름"}),
    "투자활동현금흐름": frozenset({"투자활동현금흐름", "투자활동으로 인한 현금흐름"}),
    "재무활동현금흐름": frozenset({"재무활동현금흐름", "재무활동으로 인한 현금흐름"}),
}


def _fs_extract(corp_code: str, bgn_de: str) -> dict[str, pd.DataFrame]:
    """Thin wrapper around dart_fss.fs.extract — monkeypatchable in tests.

    Returns dict mapping sheet_key ("bs"|"is"|"cis"|"cf") to DataFrame. Each
    frame must have a 'label_ko' column and a 'value' (or last numeric) column.
    """
    import dart_fss as dart  # lazy import; COLL-07 safe (not anthropic/openai)

    fs = dart.fs.extract(corp_code=corp_code, bgn_de=bgn_de)
    if isinstance(fs, dict):
        return fs
    if hasattr(fs, "to_dict"):
        return {k: pd.DataFrame(v) for k, v in fs.to_dict().items()}
    raise TypeError(f"Unexpected dart-fss extract return type: {type(fs)!r}")


def _pick_value(row: Any) -> float | None:
    """Extract a numeric 'value' from a DataFrame row.

    Cassette rows have a 'value' column. Live dart-fss rows have multiple
    YYYYMMDD period columns (e.g. ``20250930``, ``20240930``, ...). dart-fss
    does not contractually guarantee column order, so we sort
    YYYYMMDD-shaped column names descending and pick the most-recent period
    with a non-null numeric value. Non-period columns (other than
    ``label_ko``) are used as a fallback in original order.
    """
    if "value" in row.index:
        v = row["value"]
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    period_cols = [c for c in row.index if _PERIOD_COL_RE.fullmatch(str(c))]
    for col in sorted(period_cols, reverse=True):
        try:
            f = float(row[col])
            if f == f:  # not NaN
                return f
        except (TypeError, ValueError):
            continue
    # Fallback: any other non-label numeric column (preserves prior behaviour
    # for cassettes / shapes that don't expose YYYYMMDD period columns).
    for col, v in row.items():
        if col == "label_ko" or _PERIOD_COL_RE.fullmatch(str(col)):
            continue
        try:
            f = float(v)
            if f == f:  # not NaN
                return f
        except (TypeError, ValueError):
            continue
    return None


def get_structured_financials(corp_code: str, bgn_de: str) -> list[NumericFact]:
    """Return NumericFact list extracted from DART structured financials.

    LLM-FREE (D-14). unit='KRW원' (DART reports raw 원). value_krw=value.
    source_span=None (structured path — no body text to echo back).

    Args:
        corp_code: 8-digit DART corp_code.
        bgn_de: earliest reporting date, YYYYMMDD.

    Returns:
        List of NumericFact, one per canonical line item found. Order = sheet
        iteration order (bs, is, cis, cf). Duplicates (same canonical key
        appearing in multiple sheets) keep the first occurrence.
    """
    fs = _fs_extract(corp_code, bgn_de)
    seen: set[str] = set()
    facts: list[NumericFact] = []
    for sheet_key in ("bs", "is", "cis", "cf"):
        df = fs.get(sheet_key)
        if df is None or df.empty:
            continue
        if "label_ko" not in df.columns:
            continue
        for _, row in df.iterrows():
            label = row["label_ko"]
            canonical = None
            for cand_key, synonyms in LINE_ITEM_SYNONYMS.items():
                if label in synonyms:
                    canonical = cand_key
                    break
            if canonical is None or canonical in seen:
                continue
            value = _pick_value(row)
            if value is None:
                continue
            facts.append(
                NumericFact(
                    key=canonical,
                    value=value,
                    unit="KRW원",
                    value_krw=value,
                    source_span=None,
                    offset=None,
                )
            )
            seen.add(canonical)
    return facts
