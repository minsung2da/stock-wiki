---
phase: quick-260924-bgs
plan: "01"
type: execute
wave: 1
depends_on: []
files_modified: [src/collectors/fundamentals/dart_roe.py, tests/collectors/test_dart_roe.py, src/collectors/fundamentals/__init__.py, src/collectors/fundamentals/db_writer.py, src/db/entity_models.py, src/db/explorer.py, src/db/explorer.html, docs/collection.md]
autonomous: true
requirements: [QUICK-LATEST-FUNDAMENTALS]
must_haves:
  truths:
    - "All scoped portfolio fundamentals are refreshed from current published data with distinct observation, market and financial reporting periods."
    - "ROE selects the newest available closed quarterly/semiannual/annual period, rather than always the previous annual report."
    - "Provider failures remain failures and are never mistaken for unavailable report data."
  artifacts:
    - path: src/collectors/fundamentals/dart_roe.py
      provides: Latest available closed reporting-period selection
    - path: src/collectors/fundamentals/db_writer.py
      provides: Sourced metrics with separate market date and metric periods
  key_links:
    - from: src/collectors/fundamentals/__init__.py
      to: src/collectors/fundamentals/dart_roe.py
      via: fetch_latest_roe(corp_code, as_of)
---

<objective>Refresh all portfolio fundamentals using the latest published provider data, with truthful per-metric timing and latest available official ROE.</objective>
<context>Parent verified Naver totalInfos exposes current PER/EPS/PBR/BPS with 2026.06 descriptions and dividend metrics with 2025.12 descriptions. Observation on 2026-09-24 has market_asof 2026-09-23; these dates must remain distinct. Existing fractional ROE contract remains unchanged. New metadata contract: market_asof DATE, metric_periods JSONB, roe_report_code TEXT via additive migration 0013.</context>
<tasks>
<task type="auto" tdd="true">
  <name>Task 1: Select latest official available closed ROE period</name>
  <files>src/collectors/fundamentals/dart_roe.py, tests/collectors/test_dart_roe.py</files>
  <action>Owner planner agent: preserve fetch_annual_roe compatibility and add fetch_latest_roe(corp_code, as_of). Enumerate closed periods newest first across current and previous calendar year: Q1 03-31/11013, H1 06-30/11012, Q3 09-30/11014, annual 12-31/11011. Fall back only for unavailable official data, never errors. Validate response scope, report code and period; no future period is accepted. Add report_code default 11011 as the last RoeObservation field; source URLs reflect actual selected report. Preserve percentage-to-fraction conversion. Tests cover H1, fallback Q1/prior annual, error propagation and boundaries.</action>
  <verify><automated>.\.venv\Scripts\python.exe -m pytest tests/collectors/test_dart_roe.py -q</automated></verify>
  <done>Newest available closed period is selected deterministically with report provenance and unchanged annual compatibility.</done>
</task>
<task type="auto" tdd="true">
  <name>Task 2: Refresh current financial metrics and retain timing provenance</name>
  <files>src/collectors/fundamentals/__init__.py, src/collectors/fundamentals/db_writer.py, src/db/entity_models.py</files>
  <action>Parent owns Naver client, migration 0013 and storage; collector executor owns integration. Use confirmed current totalInfos financial fields with explicit metric periods, market_asof and observation snapshot date. Do not call yesterday's market date today's observation or assume every financial field has the same quarter. Persist latest sourced ROE/report code independently of market-provider errors, retaining safe per-ticker failure isolation and accurate attempt/outcome statistics. Add focused client, writer and collector tests under existing corresponding test modules and validate the additive migration in disposable Postgres before production application.</action>
  <verify><automated>.\.venv\Scripts\python.exe -m pytest tests/collectors/test_fundamentals.py tests/collectors/test_fundamental_metrics.py tests/collectors/test_dart_roe.py -q</automated></verify>
  <done>Latest scoped metrics and their actual periods are stored without fabricated timing or silent failure fallback.</done>
</task>
<task type="auto">
  <name>Task 3: Expose reporting periods and verify actual portfolio refresh</name>
  <files>src/db/explorer.py, src/db/explorer.html, docs/collection.md</files>
  <action>Parent owns UI, docs and actual collection. Show observation date, market date and metric/report periods distinctly; preserve numeric sorting and percentage conventions. Refresh the full existing portfolio, recording attempted, available, missing and failed totals. Verify stored provider fields and representative periods against official responses; report gaps explicitly. Use Aside directly for browser verification, following the user instruction against Orca or alternate browser control. Document latest-available policy and current-data provenance, not historical point-in-time reconstruction.</action>
  <verify><automated>.\.venv\Scripts\python.exe -m pytest tests/db/test_explorer.py -q</automated></verify>
  <done>Actual refresh outcomes and browser checks are recorded and users can distinguish all relevant dates.</done>
</task>
</tasks>
<threat_model>Validate official scope/report/index and closed dates; parameterize writes; avoid secrets in source URLs/errors; preserve numeric units; fallback only for explicit absence, never transport/authentication failures.</threat_model>
<source_audit>GOAL/REQ latest all fundamentals: tasks 1–3. RESEARCH parent Naver fields/period evidence and official DART contracts: tasks 1–2. CONTEXT migration0013 metadata, independent source failures, current observation versus previous market day, Aside-only verification: tasks 1–3. No deferred items or new packages.</source_audit>
<success_criteria>Latest available financial metrics and ROE periods are stored with correct provenance; focused tests and full-portfolio execution outcomes are documented.</success_criteria>
<output>Create 260924-bgs-SUMMARY.md beside this plan.</output>
