---
source: news
sentiment: tone_or_outcome  # D-13: news ok; choose scope
---

# 뉴스 추출

You are processing a Korean finance news article (한경 / 이데일리 / 서울경제). Semi-trusted source. Extract `_derived`:

- `tickers`: 6-digit KRX tickers mentioned (resolved by entity_aliases upstream; you only echo ones present in the body).
- `event_type`: one of {analyst_upgrade, analyst_downgrade, earnings_release, macro_commentary, market_gossip, other}. `market_gossip` for 테마주/급등주 low-signal articles.
- `catalysts`: 0-5 phrases.
- `sentiment`: choose `scope` = "tone" if reflecting reporter/analyst viewpoint, "outcome" if about the event's impact on the company. If both differ substantively, pick the more load-bearing and record `unclear`.
- `numeric_facts`: **character-level echo-back required**. Every fact.source_span MUST be a verbatim substring at fact.offset in the normalized body. If unsure, emit fewer facts.
- `summary`: 1-2 sentence 한글 summary.

Regex candidates (informational):
{{CANDIDATES_JSON}}

<untrusted source="news" trust_level="semi_trusted">
{{BODY}}
</untrusted>
