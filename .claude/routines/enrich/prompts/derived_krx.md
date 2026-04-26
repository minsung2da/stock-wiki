---
source: krx
sentiment: optional  # KRX day-snapshot has direction (등락률), so sentiment may be set
---

# KRX 일별 시세 추출

You are processing a KRX daily snapshot (OHLCV + investor flow + short interest)
for a single ticker. The frontmatter `provenance.ticker` is the authoritative
6-digit code — do NOT re-extract it from the body or filename. The deterministic
post-LLM normalizer will seed `_derived.tickers` from `provenance.ticker` if you
leave it empty, but your output may set it explicitly.

- `tickers`: leave as `[]` OR set to `[provenance.ticker]`. The Python
  normalizer enforces the seed regardless.
- `event_type`: `price_micro` (always — KRX docs are by-construction
  price/flow snapshots, not company-specific events).
- `catalysts`: 0-2 phrases ONLY if the body explicitly names a driver
  (e.g., "외국인 대량 순매도"); otherwise leave `[]`. Do NOT invent.
- `sentiment`: derive from 등락률 (the trading-day return, %) when present:
  - `>= +2%` → `bullish` (bullish_score 0.7)
  - `+0.5% .. +2%` → `bullish` (0.6) or `neutral` (0.55), pick the closer
  - `-0.5% .. +0.5%` → `neutral` (0.5)
  - `-2% .. -0.5%` → `bearish` (0.4) or `neutral` (0.45)
  - `<= -2%` → `bearish` (0.3)
  - If 등락률 absent → `null`.
  These are heuristics; one trading day's return is not a thesis. Do NOT
  set `strongly_*` from a single day.
- `numeric_facts`: echo-back required. Use canonical metric keys: 시가, 고가,
  저가, 종가, 거래량, 거래대금, 외국인_순매수, 기관_순매수, 공매도_잔고.
  Period = ISO date string from `provenance.date`.
- `summary`: 1 sentence summarising the day's price and flow action.

Regex candidates (informational):
{{CANDIDATES_JSON}}

<untrusted source="krx" trust_level="trusted">
{{BODY}}
</untrusted>
