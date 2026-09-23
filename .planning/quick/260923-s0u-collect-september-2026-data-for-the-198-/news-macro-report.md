# September news and macro collection

Requested range: 2026-09-01 through 2026-09-23 inclusive, Asia/Seoul.

## Persisted results

| Source | Newly inserted | Updated | Stored date range |
|---|---:|---:|---|
| Portfolio-matched RSS news, after paragraph repair | 25 retained | 25 repaired | September 22–23 KST |
| ECOS Korean base rate (722Y001 / 0101000) | 21 | 0 | September 1–21 |
| ECOS USD/KRW (731Y001 / 0000001) | 17 | 0 | September 1–23 |
| FRED US 10-year yield (DGS10) | 14 | 0 | September 1–21 |
| FRED WTI (DCOILWTICO) | 10 | 0 | September 1–15 |

September baseline was zero rows in both news and macro_series. Macro total is 62 newly inserted observations. Final news touches 24 distinct portfolio tickers under the existing alias-matching rules. Final news counts by KST publication date: September 22 = 8; September 23 = 17. The initial 68 inserted news rows were audited and repaired as described below; 43 no longer matched after enforcing the two-paragraph cap and were removed from this run's newly inserted rows only.

## Requests and limitations

- Fetched the three existing RSS feeds once: Hankyung economy 50 entries, Hankyung finance 50, Edaily 50. All 150 dated entries fell within the requested interval. Initial attempt: 68 matched articles persisted, 81 articles had no scoped alias match, and one Edaily article returned no extractable body. No feed request failed.
- Retried only that Edaily article: direct requests returned HTTP 200 (`text/html; charset=utf-8`, 134140 bytes); existing trafilatura client also succeeded and the then-existing extractor returned 711 characters. Article metadata states September 22 at 21:10:09 KST. The article covers Microsoft and has zero scoped portfolio alias matches, so it was correctly excluded without insertion. Before paragraph repair: 68 inserted, 82 unmatched, zero unresolved request/extraction failures. The initial failure remains in the historical attempt log.
- Feed history only covered September 22–23. September 1–21 news is not recovered, and this is not an archive-complete September news dataset.
- Investigation exposed a pre-existing cap defect: the extractor split only double newlines while live trafilatura output separated paragraphs with single newlines. `extract_first_two_paragraphs` now keeps the first two nonempty `splitlines()` entries. The LF and CRLF regression cases failed before the fix; all three separator cases plus the existing DB integration test pass afterward (4 passed).
- Only this run's 68 newly inserted URL keys were audited. All 68 had excess paragraphs. Recomputed title + shortened-body alias matches retained and updated 25 records; 43 now-unmatched records were deleted using their exact URL hashes and expected existing content hashes. No prior-user/out-of-scope records were modified. Final outcome: 25 retained, 125 unmatched across 150 RSS entries, zero unresolved failures.
- `summary_only` license flags were retained. Existing substring matching can yield ambiguous short-name matches; article counts are not a claim of manually verified company relevance.
- All four macro APIs succeeded. Missing later observations remain missing; publication lags and missing-value observations are not filled. FRED missing-value markers were excluded. Macro observations are current revisions, not historical vintages.
- ECOS and FRED requests explicitly restricted September dates; rows were date-filtered again before upsert. No prior-year macro observations were written.

## Verification and artifacts

- Every one of 62 macro values was compared with the stored typed numeric value against its dated API response.
- All 68 initial news rows were verified for source publication timestamp and scope. After repair, all 25 retained rows were verified for a maximum of two nonempty paragraphs, recomputed content hashes, exact recomputed ticker/corp matches, and `summary_only` flags.
- Existing `record_collector_run` persisted macro run 220, news run 222, single-article retry run 224, and paragraph repair run 225.
- `ruff check scripts/september_news_macro_backfill.py`, compileall, and `git diff --check` passed.
- Helper: `scripts/september_news_macro_backfill.py`.
- Cap fix: `src/collectors/news/fetcher.py`; regression: `tests/collectors/news/test_collect_news.py`.
- Detailed checkpoint, article URLs, ticker matches, source dates, and failure record: `notes/private/september-news-macro-report.json` (gitignored; do not commit).
- No DART calls, trading operations, dependency installation, or STATE edits were performed by this task.
