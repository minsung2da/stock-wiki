# September market collection results

Completed 2026-09-23 KST. Portfolio scope: 198 companies. Canonical storage: existing Postgres typed tables; no schema changes or trading actions.

## Persisted coverage

- OHLCV: 3,366 newly inserted rows, 198 companies, 17 source trading dates each, September 1–23 inclusive. September baseline was zero. No ticker failures. Collector run ID 223.
- Fundamentals: 198 newly inserted current snapshots, all dated September 23 only. Collector run ID 226. Historical September 1–22 valuations were not reconstructed from current values.
- Non-null fundamental counts: PER 167; PBR 198; EPS 198; BPS 198; dividend yield 152; DPS 152; ROE 0. Missing source values remain NULL, not zero.

## Sources and limitations

- OHLCV uses installed pykrx 1.0.51 `get_market_ohlcv_by_date(..., adjusted=True)`, which uses Naver adjusted daily chart data. Existing flow fields are preserved on upsert. Current Naver integration session volume differs from chart volume; the two are not mixed.
- Fundamentals use `https://m.stock.naver.com/api/stock/{ticker}/integration`, with `/basic` validating ticker and actual local trade date. Database source includes the endpoint URL, observation date, and `current_snapshot` label. Raw metric fiscal periods (`valueDesc`) are retained in the ignored private evidence file.
- KRX investor trading-value, short-balance, and historical fundamental probes for Samsung returned empty frames. No trading-value, investor-flow, or short fields were fabricated. All 3,366 new OHLCV records have these unavailable optional fields NULL.
- Installed environment has neither `KRX_ID` nor `KRX_PW`. Current upstream pykrx documentation requires those credentials for authenticated KRX APIs: https://github.com/sharebook-kr/pykrx . Empty legacy responses are not proof of a particular HTTP error.
- Naver investor trend fields are share quantities, so they were not substituted into KRW investor-flow columns. ROE was not estimated from mismatched reporting periods.
- All HTTP requests have a 25-second timeout and a minimum one-second interval. Current snapshot mode refuses to run on another date rather than backdating a later valuation.

## Validation and evidence

- All 1,188 raw fundamental fields (198 × 6, including explicit unavailable values) were compared against persisted Decimal/NULL fields with no mismatches.
- Samsung September 1 OHLCV matched all five source values: open 256500, high 262500, low 254000, close 261000 KRW; volume 15319615 shares.
- Portfolio/date coverage was queried from the actual DB. No failed tickers in either completed batch.
- Ruff and Python compilation passed for `scripts/september_market_backfill.py`; `git diff --check` passed.
- Private evidence: `notes/private/september-2026-market.json` and `notes/private/september-2026-fundamentals.json`. Both confirmed gitignored and not staged.

## Self-Check: PASSED

The operational helper, private evidence files, and canonical DB rows exist. Only the helper and this aggregate report are assigned to the market subtask commit; parent owns overall SUMMARY and STATE updates.
