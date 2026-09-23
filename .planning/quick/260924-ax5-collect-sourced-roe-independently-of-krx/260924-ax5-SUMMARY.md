---
quick_task: 260924-ax5
date: 2026-09-24
status: complete
requirements: [QUICK-SOURCED-ROE]
---

# Official annual ROE collection and explorer display

The fundamentals collector now retrieves official DART annual ROE independently of KRX availability. KRX errors or empty frames no longer prevent ROE enrichment; DART failures do not discard valid market metrics. The active path uses `dart_roe.fetch_annual_roe`, not the retained legacy `compute_roe` helper.

Official ROE index M211550 is requested through `fnlttSinglIndx.json`, annual report 11011, index group M210000, using the preceding calendar year. Provider percentage values are converted to the existing fractional NUMERIC storage contract. Additive migration 0012 adds `roe_period_end`, `roe_source` and `roe_fetched_at` and has been applied to the production database.

`db_writer.upsert_roe` enriches ROE and its provenance separately from the daily market metrics. The explorer shows ROE as a percentage, exposes the annual period and source, and supports server-side ascending/descending sorting. Missing official values remain missing rather than becoming synthetic zeroes.

## Actual portfolio enrichment

The 2026-09-23 snapshot was enriched using values observed on 2026-09-24. This is current-published-data enrichment, not a reconstruction of information available on the historical snapshot date.

| Result | Count |
|---|---:|
| Scoped snapshot records attempted | 198 |
| Official ROE available and enriched | 197 |
| Official ROE unavailable | 1 |
| Failed | 0 |

The unavailable company was Samsung Epis Holdings, ticker `0126Z0`. Samsung Electronics returned annual 2025 ROE of **10.783%**, stored as fractional ROE with settlement date **2025-12-31**, source reference and observation timestamp.

The before/after hash of the existing six non-ROE financial metrics, source and market `fetched_at` matched. Thus PER, PBR, EPS, BPS, dividend yield and DPS were preserved during the actual enrichment.

## Verification

The parent ran the combined focused suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/collectors/test_dart_roe.py tests/collectors/test_fundamentals.py tests/collectors/test_fundamental_metrics.py tests/cli/test_collect_fundamentals.py tests/db/test_explorer.py tests/test_import_guard.py -q
```

Result: **69 passed, 1 existing warning, 24.66 seconds**. Coverage includes official source parsing and units, independent provider failures, preservation of existing metrics, collector statistics, CLI behavior, explorer sorting and collector import restrictions.

Ruff passed for the changed files. Targeted mypy checks passed for `dart_roe` and the explorer. Full-project mypy cleanliness is not claimed: a pre-existing untyped warning remains in `db_writer`.

Aside's native CLI/REPL verified list and detail percentage rendering, annual period, source and sorting. Ascending order began at **-110.435%**; descending order began at **75.301%**. Verification used Aside directly, without Orca or a standalone browser controller.

The known Docker Desktop socket startup failure was repaired using the existing control-project repair script. Docker **29.5.2** returned healthy before the successful database verification.

## Review follow-through

The backfill script now returns exit code 1 when individual failures remain, so automation can identify a partial failure. Its report distinguishes `retrieved_at` from a retained database observation timestamp when an unchanged value causes the writer to skip storage.

No new dependency was required. Database/API absence remains visible in collection statistics and the explorer. Commit and final state bookkeeping are handled by the parent workflow.
