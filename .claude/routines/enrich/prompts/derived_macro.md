---
source: macro
sentiment: null  # D-13: macro is not firm-specific
---

# 거시 지표 추출

You are processing an ECOS/FRED macro indicator note. Extract `_derived`:

- `tickers`: **empty list**. Macro has no ticker scope.
- `event_type`: `macro_commentary` (or `null` if the note is just a data table with no narrative).
- `catalysts`: 0-3 phrases if the body names drivers (e.g., "연준 50bp 인상", "원자재 가격 하락").
- `sentiment`: **MUST be null**. Macro is not firm-specific.
- `numeric_facts`: echo-back required. Keys should use canonical macro names (기준금리, USD_KRW, US_10Y, WTI, KOSPI, KOSDAQ).
- `summary`: 1 sentence.

Regex candidates (informational):
{{CANDIDATES_JSON}}

<untrusted source="macro" trust_level="trusted">
{{BODY}}
</untrusted>
