---
quick_task: 260924-bgs
date: 2026-09-24
status: complete
requirements: [QUICK-LATEST-FUNDAMENTALS]
---

# Latest portfolio fundamentals refresh

The default fundamentals collection now stores current published market metrics with independent market and financial reporting dates. Latest official DART ROE selection checks closed current/previous-year reporting periods newest first, falling back only for unavailable values; provider errors propagate. Existing annual ROE access remains compatible.

Additive migration **0013** was applied, adding `market_asof`, `metric_periods` and `roe_report_code`. The explorer displays all seven financial fields, observation date, market date and report type, plus per-metric period information and a latest-snapshot filter. Collection documentation was updated.

## Actual collection

The default CLI `collect fundamentals` completed in **55,375 ms**: **198 inserted, 0 failed**. Observation date is **2026-09-24**, while the market date is **2026-09-23**. All 198 ROE observations use **2026 H1**, settlement date **2026-06-30**, report code **11012**.

| Metric | Populated records |
|---|---:|
| PER | 167 |
| PBR | 198 |
| EPS | 198 |
| BPS | 198 |
| ROE | 198 |
| Dividend yield | 152 |
| DPS | 152 |

Unavailable provider values remain null. PER/EPS/BPS/PBR reporting descriptions identify June 2026 for 197 companies and December 2025 for one. Dividend periods vary, including 2025.12 and 2026.02/03/04; original provider `valueDesc` information is preserved rather than replaced by a single shared quarter.

Samsung Electronics ROE is **23.404%** for the selected H1 period. Samsung Epis Holdings (`0126Z0`), previously missing the annual value, now has H1 ROE **3.088%**. ROE is the provider's value; the application performs no local trailing-twelve-month or annual recalculation. This makes no assertion about the provider's own annualization methodology.

The hash of the **198 pre-existing snapshot rows** matched before and after collection; the new current observation did not rewrite those historical rows. Before-state evidence remains in the parent's private evidence file. Current provider data is not represented as historical point-in-time reconstruction.

## Verification

**97 unique relevant tests passed** across the non-overlapping focused runs: DART ROE 25, collector 16, and market/explorer/CLI/import coverage 56. Relevant source and explorer mypy checks passed; full-project mypy cleanliness is not claimed. Final all-changed-files Ruff verification remains with the parent workflow and is not claimed complete here.

Aside native CLI/REPL verification confirmed:

- Latest-snapshot filter enabled: **198 rows**; disabled: **396 rows**.
- All seven financial columns plus observation date, market date and report type are present.
- Samsung list and detail views show **23.404%**, **2026-06-30**, and the half-year report label.
- Per-metric tooltips distinguish **2026.06** financial metrics from **2025.12** dividends in the checked example.

Browser verification used Aside directly. No Orca or standalone browser controller was used. Review of the market client and writer found no blocking date, unit or preservation defect.

Commit and state bookkeeping are handled by the parent workflow.
