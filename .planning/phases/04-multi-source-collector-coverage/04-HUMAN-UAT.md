---
status: partial
phase: 04-multi-source-collector-coverage
source: [04-VERIFICATION.md, 04-VALIDATION.md §Manual-Only]
started: 2026-04-21T00:00:00+09:00
updated: 2026-04-21T00:00:00+09:00
---

## Current Test

[awaiting human testing]

## Tests

### 1. Live `stock collect all` smoke run (end-to-end isolation contract)
expected:
  - All 4 source keys present in stderr JSON report
  - One forced failure leaves the other 3 at `status: "ok"`
  - `ingested/_status/heartbeat.md` reflects per-source independent timestamps
  - Files appear under `vault/raw/{krx,news,macro,kind}/` for the portfolio tickers
result: [pending]
how-to-run:
  - Ensure `.env` has `DART_API_KEY`, `ECOS_API_KEY`, `FRED_API_KEY`, `DATABASE_URL`
  - Ensure `vault/notes/portfolio.md` has at least one `watchlist` or `holdings` ticker
  - Run: `uv run stock collect all 2>/tmp/report.json`
  - Inspect: `cat /tmp/report.json | jq` — should match the D-20 schema
  - Inspect: `cat ingested/_status/heartbeat.md` — 4 source keys
  - Inspect: `ls vault/raw/krx/ vault/raw/news/ vault/raw/macro/ vault/raw/kind/`
  - Force-fail test: `uv run stock collect all --sources=news,macro,kind,krx` with a network-unreachable env for one source (e.g., temporarily revoke `ECOS_API_KEY` in shell) → exit 1, stderr JSON shows 1 error + 3 ok

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps

### Gap-04-01: investment_caution / investment_risk event types deferred
status: deferred
description: Plan 05 executor captured KIND `/investwarn/investattentwarnrisky.do` fixtures but did not implement the parser. ROADMAP Phase 4 Success Criterion #4 enumerates only 거래정지·관리종목·불성실공시 (all three DELIVERED via DART `pblntf_ty="I"`), so strictly the phase goal is met. CONTEXT D-08 event_type enum is a superset.
recommendation: Add to backlog as `V2-KIND-01 — investment_caution/risk parser using pre-captured KIND fixtures`. Reuse Plan 05's `src/collectors/kind/scraper.py` scaffold.

### Gap-04-02: CONTEXT D-14 text still reflects pre-execution hybrid
status: documentation
description: Plan 05 executed Option D (DART `pblntf_ty="I"` + KIND AJAX, no pykrx), operator-approved during execution 2026-04-20. CONTEXT.md D-14 prose still describes the original pykrx/DART/KIND hybrid. 04-05-SUMMARY.md records the amendment but CONTEXT.md itself hasn't been edited.
recommendation: Single-commit CONTEXT.md D-14 amendment in Phase 5 or as a `/gsd-quick` task, citing 04-05-SUMMARY.md §"Strategy Amendment (Option D)".
