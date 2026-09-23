---
phase: quick
plan: 260923-qis
type: execute
wave: 1
depends_on: []
autonomous: true
requirements: [SC-1, SC-2, SC-5]
files_modified:
  - src/cli/__main__.py
  - src/cli/commands.py
  - src/collectors/news/__init__.py
  - src/collectors/news/fetcher.py
  - src/collectors/fundamentals/__init__.py
  - src/collectors/fundamentals/db_writer.py
  - src/db/entity_models.py
  - src/db/migrations/versions/0010_fundamentals_dividends.py
  - tests/test_cli_collect_all.py
  - tests/collectors/test_fundamentals.py
  - tests/collectors/news/test_collect_news.py
  - docs/collection.md
must_haves:
  truths:
    - Default collect all runs DART, KRX, news, macro, and fundamentals each invocation for the existing portfolio scope.
    - News admission uses the requested KST calendar day before article HTTP requests.
    - KIND risk-event collection is unavailable while existing stored history and trading safeguards remain intact.
    - DIV and DPS survive insert, update, and repeated idempotent collection in typed numeric columns.
  artifacts:
    - path: src/db/migrations/versions/0010_fundamentals_dividends.py
      provides: Additive dividend metric schema
    - path: docs/collection.md
      provides: Recurring batch invocation and source/date semantics
  key_links:
    - from: src/cli/commands.py
      to: collectors.fundamentals.collect_fundamentals
      via: default all dispatch
    - from: src/collectors/fundamentals/__init__.py
      to: src/collectors/fundamentals/db_writer.py
      via: dividend_yield and dps keyword arguments
---

<objective>
Make collection complete and repeatable for portfolio holdings/watchlist, remove risk-event collection, and retain all pykrx fundamental fields. User decisions supersede historical KIND/default-source decisions. No trading, analysis-card, historical migration, or stored-history deletion is authorized by this change.
</objective>

<context>
@AGENTS.md
@.planning/STATE.md
@.planning/ROADMAP.md
@.planning/research/redesign-2026-05.md
@src/cli/commands.py
@src/collectors/news/fetcher.py
@src/collectors/fundamentals/db_writer.py

Existing contracts: Portfolio.load(repo_root).scope_tickers() returns holdings/watchlist tickers; db.entity.resolve_entities resolves corporate identities; collect_dart requires corp_code, since, max_docs, engine. Existing collectors expose inserted/updated/skipped/failed statistics; succeeded is not the authoritative processed counter. No new dependencies are required. Periodic-ready means safe repeated batch execution; an actual scheduler cadence was not supplied.
</context>

<tasks>
<task type="auto" tdd="true">
  <name>Task 1: Persist every pykrx fundamental metric</name>
  <files>src/collectors/fundamentals/__init__.py, src/collectors/fundamentals/db_writer.py, src/db/entity_models.py, src/db/migrations/versions/0010_fundamentals_dividends.py, tests/collectors/test_fundamentals.py</files>
  <behavior>DIV and DPS survive collection and database round trips; repeated identical rows are skipped; changed dividend fields update; zero remains zero and missing/NaN is null; existing ROE preservation remains valid.</behavior>
  <action>Implement user decisions 1 and 4: map pykrx DIV to dividend_yield (percent, no fraction conversion) and DPS to dps (KRW/share), alongside PER/PBR/EPS/BPS and existing DART-derived ROE. Add nullable NUMERIC ORM columns and a handwritten additive Alembic revision after 0009. Extend parameterized UPSERT and equality comparison to both metrics, preserving compatible optional writer arguments. Test isolated PostgreSQL schema upgrade and real insert/update/idempotence; never edit old migrations or drop stored rows.</action>
  <verify><automated>.\.venv\Scripts\python.exe -m pytest tests/collectors/test_fundamentals.py tests/cli/test_collect_fundamentals.py -q</automated></verify>
  <done>All six pykrx fields plus ROE persist with correct units; schema migration and regression tests pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Enforce same-day news collection on every invocation</name>
  <files>src/collectors/news/__init__.py, src/collectors/news/fetcher.py, tests/collectors/news/test_collect_news.py</files>
  <behavior>UTC RSS timestamps admit precisely the selected Asia/Seoul calendar date, including both midnight boundaries; old, future, and unknown-date items do not fetch article bodies; repeated runs can discover later same-day articles and do not duplicate persisted rows.</behavior>
  <action>Implement user decision 2: parse feedparser UTC tuples as timezone-aware UTC, derive one KST target date from since or today, and filter by the half-open local-day interval before article fetching and before applying max_per_feed to eligible entries. Preserve current alias scope, source feeds, two-paragraph extraction, and UPSERT behavior. Reject invalid dates explicitly and account for skipped items honestly. Update fixtures to fixed explicit dates so tests do not depend on wall-clock time.</action>
  <verify><automated>.\.venv\Scripts\python.exe -m pytest tests/collectors/news -q</automated></verify>
  <done>Each run reads feeds again, retrieves eligible same-day articles, and excludes nonmatching days without unnecessary article requests.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Wire complete repeated batch and retire KIND collection</name>
  <files>src/cli/__main__.py, src/cli/commands.py, src/collectors/kind/__init__.py, src/collectors/kind/client.py, src/collectors/kind/dart_events.py, src/collectors/kind/db_writer.py, src/collectors/kind/scraper.py, src/collectors/kind/selectors.py, src/collectors/kind/sources.py, tests/collectors/kind/__init__.py, tests/collectors/kind/test_client.py, tests/collectors/kind/test_collect_kind.py, tests/collectors/kind/test_db_writer.py, tests/collectors/kind/test_scraper.py, tests/collectors/kind/test_sources.py, tests/shared/test_event_type_enum_drift.py, tests/test_cli_collect_all.py, tests/test_phase01_smoke.py, tests/test_no_writer.py, docs/collection.md</files>
  <behavior>Default batch invokes all five active sources including fundamentals; DART receives resolved portfolio corporate codes and a concrete date; one corporation/source failure does not suppress others; KIND is rejected; repeated batches report real processed counts and do not duplicate rows.</behavior>
  <action>Implement user decisions 1 and 3: default sources become dart,krx,news,macro,fundamentals; register fundamentals in dispatch and pass the same resolved KST batch date to date-based collectors. Keep an explicit sources override for targeted reruns. Resolve and deduplicate portfolio corporate codes for DART, aggregate per-corporation counters, and report unresolved identities as failures. Preserve standalone DART arguments, macro series behavior, per-source isolation and nonzero exit on partial failure. Derive docs_processed from real counters instead of nonexistent succeeded. Delete the listed KIND runtime package and its exclusive tests; remove CLI/import and smoke-test assumptions that require KIND. Update any active legacy enum-drift test to retain meaningful surviving schema checks, or delete it if solely KIND-specific. Preserve events history/schema, filing classification, decision-card contradictions, and trading safety gates. Document source inventory, portfolio scope, same-day/backfill semantics, idempotence, missing prerequisites, an absolute-path recurring invocation, and that cadence activation remains unspecified. Remove obsolete active KIND references only where directly affected; leave historical planning documents intact.</action>
  <verify><automated>.\.venv\Scripts\python.exe -m pytest tests/test_cli_collect_all.py tests/test_phase01_smoke.py tests/test_no_writer.py tests/cli/test_collect_fundamentals.py -q</automated></verify>
  <done>Complete default collection is repeatable and failure-visible, fundamentals always participates in default batches, and no runtime KIND import/command remains.</done>
</task>
</tasks>

<threat_model>
| Boundary | Threat | Disposition | Mitigation |
|---|---|---|---|
| RSS to collector | Untrusted/missing timestamps permit unrelated articles | mitigate | UTC-aware parse and KST interval checks before article requests |
| CLI to DB | Invalid date or unresolved corporate identity | mitigate | Parse dates before dispatch, bind SQL parameters, report identity failures |
| Repeated batch to database | Duplicate data or silently skipped failures | mitigate | Existing conflict keys, dividend-aware equality, per-source and per-corporation failure tests |
| Schema upgrade | Loss of stored event or financial history | mitigate | Additive nullable columns only; retain historical event schema |
</threat_model>

<verification>
Run the listed focused suites against isolated testcontainers PostgreSQL, inspect the final diff, and run import guards plus CLI help. Verify no runtime collectors.kind import remains by a source search. Record unavailable Docker/live-provider validation explicitly; do not claim live collection success from mocks. Stage only task-owned changes on feat/collection-completeness.
</verification>

<source_audit>
GOAL: current complete DB-direct collection -> Tasks 1-3.
REQ: ROADMAP SC-1 DART -> Task 3; SC-2 typed DB-direct UPSERT -> Tasks 1-3; SC-5 collector tests -> Tasks 1-3. Historical KIND participation is explicitly superseded by the current user.
RESEARCH: Postgres canonical, typed numbers, whole DART body, content dedup -> preserved across Tasks 1-3; no analysis/trading changes.
CONTEXT: user 1 fundamentals/default periodic-ready all -> Tasks 1/3; user 2 same-day news each run -> Task 2; user 3 remove risk collection -> Task 3; user 4 missing financial metrics -> Task 1. All current requested items covered.
</source_audit>

<success_criteria>Focused regression tests pass; all active sources are in the default batch; news is KST-day scoped; dividends persist; KIND runtime is retired without deleting historical data or safety gates.</success_criteria>
<output>Create 260923-qis-SUMMARY.md in this quick-task directory and update STATE.md Quick Tasks Completed after implementation; do not rewrite ROADMAP for this ad-hoc task.</output>
