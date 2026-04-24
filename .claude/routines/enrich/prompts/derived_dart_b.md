---
source: dart
filing_type: B  # 주요사항
sentiment: outcome  # D-13: DART 주요사항 ok for outcome-scope sentiment
---

# DART 주요사항(B) 추출

You are processing a DART 주요사항 공시. Extract `_derived`:

- `tickers`: list of 6-digit KRX tickers mentioned (usually just the filer)
- `event_type`: one of {earnings_release, equity_issue, mergers_acquisitions, major_contract, board_change, ownership_change, buyback_announcement, dividend, other}. Use `other` if none fits. Use `null` only if the filing is purely administrative.
- `catalysts`: 0-5 short 한글 phrases naming the driver (e.g., "4Q 영업이익 서프라이즈", "대규모 자사주 매입").
- `sentiment`: SentimentBlock with `scope="outcome"`. Label the filing's impact on the company (bullish if positive for shareholders). `null` if genuinely neutral; `unclear` if evidence insufficient.
- `numeric_facts`: narrative numbers from the body ONLY. DART structured financials come separately. Every numeric_fact needs `source_span` as a verbatim substring + `offset` (character index into normalized body).
- `summary`: 1-2 sentence 한글 summary of what changed.

Follow the DerivedBlock v2 JSON schema exactly. Regex candidates below are informational hints — select and echo only what's truly in the body.

Regex candidates (informational):
{{CANDIDATES_JSON}}

<untrusted source="dart" trust_level="trusted">
{{BODY}}
</untrusted>
