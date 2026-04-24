---
source: kind
sentiment: null  # D-13: KIND event_type already encodes direction
---

# KIND 이벤트 추출

You are processing a KIND (Korea Investor's Network for Disclosure) event (거래정지, 관리종목지정, 불성실공시, investment_caution, investment_risk).

- `tickers`: single 6-digit ticker for the affected entity.
- `event_type`: one of {suspension, watchlist_designation, unfaithful_disclosure, delisting, investment_caution, investment_risk, other}. Required — these filings are event-defined.
- `catalysts`: 1-3 phrases explaining the trigger if the body says (e.g., "공시불이행 3회 누적").
- `sentiment`: **MUST be null**. The event_type already encodes direction.
- `numeric_facts`: rare for KIND; usually none. If present, echo-back required.
- `summary`: 1 sentence.

Regex candidates (informational):
{{CANDIDATES_JSON}}

<untrusted source="kind" trust_level="trusted">
{{BODY}}
</untrusted>
