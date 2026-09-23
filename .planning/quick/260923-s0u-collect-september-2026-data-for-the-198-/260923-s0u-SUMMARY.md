---
phase: quick
plan: 260923-s0u
status: complete
coverage: partial-upstream-history
completed: 2026-09-23
---

# September portfolio collection

Executed September 1–23 ingestion for all 198 portfolio companies. All entity mappings now resolve.
All five September tables started empty. Final retained data totals 3,671 rows:

| Dataset | Rows | Coverage |
|---|---:|---|
| OHLCV | 3,366 | 198 companies, 17 dates, September 1–23 |
| Fundamentals | 198 | September 23 current snapshot only |
| Filings | 20 | Four A and sixteen B final reports; all six API list pages scanned |
| News | 25 | September 22: eight; September 23: seventeen; 24 companies |
| Macro | 62 | Four configured series, publication dates preserved |

## Implementation and evidence

- Existing OpenDART entity seeder succeeded for 198 companies; 68 previously missing mappings resolved.
- Three bounded operational scripts reuse existing typed DB writers. No dependencies or trading configuration changed.
- DART API list pagination scans 52 A + 442 B market-wide entries and filters to portfolio corporations.
  All 20 selected receipt IDs are present with bodies. Eighteen have complete XML text; two attachment
  correction notices use official viewer text and links because document.xml returned status 014.
  PDF/image attachment contents remain unextracted.
- Naver-backed pykrx adjusted price history provides 3,366 observations; existing flow values are preserved.
- September 23 Naver fundamentals are never backdated. All 1,188 raw metric fields reconcile with typed
  DB values or NULL. Non-null PER=167, PBR/EPS/BPS=198 each, dividend yield/DPS=152 each, ROE=0.
- Macro values were verified against all 62 dated source observations. Latest observations:
  base rate and US10Y September 21, USD/KRW September 23, WTI September 15.
- Three RSS feeds returned 150 articles. A transient empty article was recovered and correctly excluded
  as unmatched. Validation exposed a pre-existing newline bug bypassing the two-paragraph cap.
  Fixed extraction with splitlines and added LF/CRLF/blank-line regressions. Of 68 initially inserted rows,
  25 were shortened and rematched; 43 rows inserted by this task were removed because the capped text
  and title had no portfolio match. No pre-existing news rows were affected.
- Collector run records retain attempts, recovery, provenance and reconciliation (including 220–226).
- Private JSON evidence and a Korean reader-facing report remain under gitignored notes/private/.

## Verification

- Read-only final audit: 198 mappings; exactly 17 price rows per company; all 198 fundamentals dated
  September 23; 20 nonempty filing bodies; 25 scoped news articles; 62 macro observations.
- All fundamentals fields and macro values checked against source responses; representative OHLCV checked.
- News paragraph, hash, ticker, corporate ID and scope validation passed. Four focused tests passed,
  including DB integration. Ruff and compile checks passed for operational helpers.
- Explorer API HTTP 200 and final September totals verified for all five datasets.

## Remaining source coverage gaps

RSS lacks September 1–21 archive history. Historical fundamentals September 1–22, ROE, trading value,
investor net flows and short metrics remain unavailable from the probed KRX path. Current values were
not substituted for history. No claim of complete monthly coverage is made.

## Deviations

Used explicit period scripts because collect-all's since parameter is one day for prices/news/fundamentals.
Used public dated/current Naver fallback sources after legacy KRX responses were empty. Added the minimal
news paragraph fix and repaired this task's new rows after live data demonstrated the existing cap bug.

Market helper and aggregate report commit: 54b3e21. Remaining scripts, news fix, docs and task metadata
are committed by the parent. Private evidence is excluded from Git.
