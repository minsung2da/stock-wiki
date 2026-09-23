---
phase: quick
plan: 260923-rry
type: execute
wave: 1
depends_on: []
files_modified:
  - notes/private/portfolio.md
autonomous: true
requirements: [USER-SECTOR-TOP20]
must_haves:
  truths:
    - The existing Portfolio loader returns the deduplicated sector-leading company collection scope.
    - Every listed company has a verifiable sector, market capitalization, name, and source date.
    - No actual ownership or position quantity is invented.
  artifacts:
    - path: notes/private/portfolio.md
      provides: Strict holdings/watchlist frontmatter and human-readable sector ranking tables
  key_links:
    - from: notes/private/portfolio.md
      to: src/shared/portfolio.py
      via: Portfolio.load and scope_tickers
---

<objective>
Populate the requested private portfolio with the top 20 ordinary-share companies in each WICS broad sector, ranking the KOSPI/KOSDAQ universe by full market capitalization. Use the sector granularity explicitly chosen by the user if an answer arrives before generation; otherwise use the communicated broad-sector default. Retain fewer than 20 entries where the verified eligible universe is smaller, explaining the count without inventing members.
</objective>

<context>
@AGENTS.md
@src/shared/portfolio.py
@.planning/research/redesign-2026-05.md
@.planning/ROADMAP.md

Portfolio accepts only holdings and watchlist in YAML frontmatter. Holdings require ticker, qty, and avg_cost; keep holdings empty because the user supplied no actual positions. Watchlist values must be quoted six-character strings. Company names, sector classifications, capitalization, dates, and citations belong in the Markdown body.
</context>

<tasks>
<task type="auto">
  <name>Task 1: Verify sector universe and capitalization snapshot</name>
  <files>notes/private/portfolio.md</files>
  <action>Fetch the complete ordinary-company WICS sector universe and dated full market capitalization from verifiable public sources using existing dependencies. WiseIndex sector constituent MKT_VAL is float-adjusted index capitalization and must not be used as full market capitalization. Verify capitalization units, market membership, ordinary-share eligibility, source dates, and pagination completeness. Sort by descending full capitalization with ticker as deterministic tie breaker; take min(20, eligible count) per sector. Preserve retrieved evidence for the final document and validation. Do not quietly drop missing quotes: resolve them or report the limitation before claiming the ranking is complete.</action>
  <verify><automated>Run an existing-environment Python validation over the fetched snapshot: sector coverage, unique eligible tickers, nonnegative numeric capitalization, source dates, and selected rows equal each sector's sorted top min(20, count).</automated></verify>
  <done>A complete, provenance-backed selected snapshot exists; undersized sectors and any data limitations are explicit.</done>
</task>
<task type="auto">
  <name>Task 2: Write and validate the private collection portfolio</name>
  <files>notes/private/portfolio.md</files>
  <action>Write UTF-8 portfolio frontmatter with holdings: [] and a deduplicated watchlist of quoted ticker strings. Add Korean Markdown explanations defining top as full capitalization, the market/sector scope, snapshot timestamps and units, source links, excluded security types, and a table per sector showing rank, ticker, company name, and capitalization. Explain sectors with fewer than 20 eligible companies. Verify watchlist matches all table tickers exactly. Do not stage or force-add notes/private or secrets. Do not alter collector logic, mutate the database, or trigger trading. A reproducible helper is optional only if needed; record any such additional file in execution summary.</action>
  <verify><automated>.\.venv\Scripts\python.exe -c "from pathlib import Path; from src.shared.portfolio import Portfolio; p=Portfolio.load(Path('.')); assert not p.holdings; assert p.watchlist; assert len(p.watchlist)==len(set(p.watchlist)); assert p.scope_tickers()==sorted(p.watchlist); print(len(p.watchlist))"</automated></verify>
  <done>Portfolio loads successfully, selected snapshot and document agree exactly, every sector has the justified count, and git check-ignore confirms the private file remains ignored.</done>
</task>
</tasks>

<threat_model>
Only public market data enters a local ignored configuration file. Validate tickers and numeric fields before serialization, use safe YAML-compatible quoted strings, and preserve source provenance. No dependency installation, credential exposure, DB writes, or trade execution is needed.
</threat_model>

<verification>
Validate snapshot ranking and membership, then load the actual portfolio with the production loader and verify counts and deduplication. Run git check-ignore notes/private/portfolio.md and inspect staged changes to ensure private information is absent. Record actual source dates and limitations in the quick summary.
</verification>

<success_criteria>
The requested sector portfolio exists, is readable by the unmodified collector scope loader, and can be inspected by company name with dated ranking evidence. The private file remains outside Git.
</success_criteria>

<output>
Create .planning/quick/260923-rry-populate-portfolio-watchlist-with-verifi/260923-rry-SUMMARY.md after execution and update STATE.md quick-task history without changing ROADMAP scope.
</output>
