---
phase: "01-collector-db-cutover"
plan: "01-06"
subsystem: ["collectors/news"]
tags: ["refactor", "db-direct", "wave-2", "narrative", "tickers-array"]
requires: ["01-01", "01-02", "01-03", "01-04"]
provides:
  - "collectors.news.client.url_hash64 — full 64-char sha256 of canonical URL (v2.0 dedup key)"
  - "collectors.news.db_writer.upsert_news_article — INSERT ... ON CONFLICT (url_hash) UPSERT into news"
  - "collect_news rewired: writes news rows via db_writer; legacy writer.* / heartbeat / frontmatter calls removed"
  - "tests/collectors/news/test_db_writer.py (10 tests) — hash stability, insert/update/skip, multi-ticker GIN, FK SET NULL, TIMESTAMPTZ tz, no-corp_code path"
  - "tests/collectors/news/test_collect_news.py rewritten to DB assertions (11 collect_news tests + retained writer/client unit tests)"
affects:
  - "Wave 2D (01-08 observability) — news collector emits structured collector_run_complete log with stats {total, inserted, updated, skipped, failed[], elapsed_ms}"
  - "Wave 2E (01-09 writer module deletion) — src/collectors/news/writer.py is now unused by the collector; ready for deletion"
tech-stack:
  added: []
  patterns:
    - "load-then-classify two-pass UPSERT (load existing content_hash → classify outcome → execute UPSERT) — mirrors collectors.macro.db_writer"
    - "CAST(:tickers AS text[]) explicit cast for psycopg3 ARRAY binding (RESEARCH Pitfall #8)"
    - "naive datetime coerced to UTC in db_writer._normalize_published_at to avoid psycopg3 rejecting naive datetimes against TIMESTAMPTZ"
    - "skipped path bumps last_seen_at only — does NOT rewrite first_seen_at via the UPSERT (preserves original first-seen timestamp)"
key-files:
  created:
    - src/collectors/news/db_writer.py
    - tests/collectors/news/test_db_writer.py
  modified:
    - src/collectors/news/client.py
    - src/collectors/news/__init__.py
    - tests/collectors/news/test_collect_news.py
decisions:
  - "url_hash64 strips whitespace before hashing (some RSS pubDate CDATA wrappers leak trailing newlines; strip prevents two near-identical URLs from producing different hashes); url_hash8 left intact for back-compat"
  - "matcher.match_tickers_in_text return shape is list[dict] (not list[str]); collector extracts ticker strings via [m['ticker'] for m in matches] before db_writer call"
  - "primary corp_code = matches[0]['corp_code'] (RESEARCH Q1 §news — first matched ticker drives corp_code); db_writer accepts None when entity not seeded"
  - "skipped path UPDATE bumps last_seen_at ONLY (separate UPDATE statement); the UPSERT path runs only for inserted/updated rows so DEFAULT now() on first_seen_at fires only on first INSERT"
  - "Test layer monkeypatch.chdir(vault_tmp.parent) places notes/private/portfolio.md on Portfolio.load(Path('.')) discovery path — the cwd-based portfolio resolution replaces the deleted vault_root parameter"
  - "Existing writer.py + client unit tests retained in test_collect_news.py (writer module still imported by tests of write_news_doc); 01-09 will delete them along with writer.py"
metrics:
  tasks_completed: 3
  duration_minutes: ~40
  tests_added: 21
  tests_total_in_news_module: 44
  commit_hashes:
    - c6ad8d0  # Task 1 — db_writer + url_hash64 + 10 unit tests
    - 3097cf2  # Task 2 — collect_news rewire
    - 15f2fcf  # Task 3 — collect_news tests → DB assertions
completed_date: "2026-05-29"
---

# Phase 1 Plan 01-06: News Collector DB Cutover Summary

**One-liner:** `collect_news` UPSERTs `news` rows directly via `db_writer` —
url_hash64 (full sha256) is the dedup key, content_hash diff drives the
inserted/updated/skipped split, and the matcher's `list[dict]` output is
projected to a `tickers TEXT[]` column populated through the GIN-indexed
`ix_news_tickers` for Phase 3 "news mentioning <ticker>" queries.

## What Changed

### `src/collectors/news/client.py`

Added `url_hash64(url: str) -> str` — full 64-char sha256 hex of the
whitespace-stripped URL. The whitespace strip handles RSS feeds that surface
URLs inside CDATA wrappers (trailing newlines / spaces). The v1.0 `url_hash8`
helper is preserved for back-compat (no current call sites in this plan
delete it).

### `src/collectors/news/db_writer.py` (NEW)

`upsert_news_article(engine, *, url, outlet, published_at, title, body_md,
tickers, corp_code, license_flag="summary_only") -> "inserted" | "updated" |
"skipped"`. Contract:

| Outcome     | When                                                            | DB effect                            |
| ----------- | --------------------------------------------------------------- | ------------------------------------ |
| `inserted`  | no row exists for `url_hash`                                    | INSERT (first_seen_at = now)         |
| `updated`   | row exists, `content_hash` differs                              | UPDATE body_md/title/tickers/cc; last_seen_at bumped |
| `skipped`   | row exists, `content_hash` matches                              | UPDATE last_seen_at only             |

Implementation pattern matches `collectors.macro.db_writer` (load existing →
classify → UPSERT). The UPSERT SQL uses `CAST(:tickers AS text[])` to force
psycopg3 to bind the Python list as a Postgres TEXT[] (Pitfall #8 in
`RESEARCH.md`).

`_normalize_published_at` converts naive datetimes to UTC because psycopg3
rejects naive `datetime` against `TIMESTAMPTZ`; RSS feeds occasionally surface
naive `pubDate` values.

Pre-flight validation: `tickers` non-empty + each element matches
`^[0-9]{6}$`; `corp_code` either None or matches `^[0-9]{8}$`.

### `src/collectors/news/__init__.py`

Rewired to use `db_writer.upsert_news_article` exclusively:

- Removed `from collectors.news import writer`, `from shared.heartbeat import
  record_source_run`, `from shared.frontmatter import read_frontmatter`.
- Removed `_read_existing_hash` helper.
- Removed `_LEGACY_VAULT_ROOT = Path("vault")` placeholder constant.
- Replaced the writer-based block with a single `db_writer` call that
  receives:
  - `tickers = [m["ticker"] for m in matches]` (matcher returns `list[dict]`;
    we project to TEXT[]).
  - `corp_code = matches[0].get("corp_code")` (first match drives the FK per
    RESEARCH.md Q1 §news).
  - `published_at = item.published or datetime.fromtimestamp(0, tz=UTC)`
    (RSS spec requires pubDate but some feeds omit it).
- Replaced `record_source_run("news", ...)` with `_log.info(
  "collector_run_complete", extra={"source": "news", "stats": ...,
  "elapsed_ms": ...})` — matches the macro/krx pattern.
- `stats` shape now: `{total, inserted, updated, skipped, failed[],
  elapsed_ms}` (the legacy `succeeded` counter is split per RESEARCH Q6).
- `repo_root` resolves to `Path(".")` (the v2.0 CLI is cwd-rooted; the
  `--vault-root` flag was removed in 01-02). `Portfolio.load(repo_root)`
  picks up `notes/private/portfolio.md` from the current directory.

R-09 startup guard (`matcher.assert_aliases_seeded(engine)`) is preserved at
the very top of the function — before any HTTP call. R-08 retry semantics are
preserved (tenacity decorators on `client.fetch_rss_feed` /
`client.fetch_article_html`).

### `tests/collectors/news/test_db_writer.py` (NEW — 10 tests)

| Test                                                         | Verifies                                               |
| ------------------------------------------------------------ | ------------------------------------------------------ |
| `test_url_hash64_stable`                                     | Same URL → same hash; whitespace tolerated             |
| `test_url_hash64_different_urls_different_hash`              | Distinct URLs → distinct hashes                        |
| `test_upsert_news_inserts_fresh`                             | First call → "inserted"; row matches inputs            |
| `test_upsert_news_idempotent`                                | 2nd identical call → "skipped"; first_seen_at preserved, last_seen_at bumped |
| `test_upsert_news_body_edited`                               | 2nd call with edited body → "updated"; content_hash differs |
| `test_upsert_news_multiple_tickers`                          | tickers TEXT[] = ['005930','000660']; GIN @> filters precisely |
| `test_upsert_news_corp_code_set_null_on_entity_delete`       | FK ON DELETE SET NULL: delete entity → news.corp_code NULL |
| `test_upsert_news_gin_index_query_works`                     | 3 rows / 3 tickers; GIN @> returns expected counts incl. multi-element match |
| `test_upsert_news_published_at_timezone_safe`                | Naive datetime → UTC; aware datetime preserved as TIMESTAMPTZ |
| `test_upsert_news_corp_code_none_ok`                         | corp_code=None accepted (matched ticker has no seeded entity) |

### `tests/collectors/news/test_collect_news.py` (REWRITE — 23 tests total)

Retained 12 writer + client unit tests (writer module survives until 01-09;
client tests test still-active helpers).

Replaced 8 collect_news tests with 11 DB-backed tests:

| Test                                                          | Verifies                                                      |
| ------------------------------------------------------------- | ------------------------------------------------------------- |
| `test_collect_news_no_engine_raises`                          | `engine=None` → RuntimeError                                  |
| `test_collect_news_assert_aliases_seeded_raises`              | R-09: NoAliasesSeededError before any HTTP call               |
| `test_collect_news_inserts_row`                               | End-to-end → inserted=1; row in DB with tickers=['005930'], corp_code='00126380', license_flag='summary_only' |
| `test_collect_news_idempotent`                                | 2nd run same body → skipped=1; row count stays at 1           |
| `test_collect_news_body_edited_updates`                       | 2nd run edited body → updated=1; content_hash differs in DB    |
| `test_collect_news_no_match_skipped`                          | Unmatched body → no row, stats.skipped >= 1                   |
| `test_collect_news_multiple_tickers_array`                    | Seed SK Hynix at test layer; both tickers in TEXT[]; GIN @> hits both |
| `test_collect_news_no_markdown_written`                       | Veto #9: no `vault/raw/news/` subdir created under cwd        |
| `test_collect_news_truncates_body_to_two_paragraphs`          | D-13: 5-paragraph trafilatura output → DB body_md has only 2  |
| `test_collect_news_soft_skips_when_trafilatura_returns_none`  | Empty body → stats.skipped >= 1, stats.failed == []           |
| `test_collect_news_cross_url_dedup_writes_two_rows_same_content_hash` | R-11: two URLs / same body → two rows, identical content_hash |

`monkeypatch.chdir(vault_tmp.parent)` puts cwd at the directory containing
`notes/private/portfolio.md`, which `Portfolio.load(Path("."))` discovers.

## Hard Veto Enforcement (this plan)

| Veto                                                 | How verified                                                                                          |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| **#6 — no numeric embedding**                        | `news` body_md / body_tsv / body_embedding columns carry narrative only (text); typed numeric not used by this writer (none in news table). All test assertions reference TEXT/TEXT[]/CHAR/TIMESTAMPTZ — no NUMERIC. |
| **#8 — no DART pre-chunking**                        | n/a for news (bodies are 2-paragraph capped); db_writer stores whole `body_md` in a single TEXT column with no chunking. |
| **#9 — no vault revival**                            | `_LEGACY_VAULT_ROOT` constant removed from `collect_news`; `test_collect_news_no_markdown_written` asserts no `vault/raw/news/` directory appears under cwd after a successful run; writer.py call sites all removed from `__init__.py`. |

## Key Facts

- **news rows UPSERTed in tests:** 11 (across the 23 collect_news + 10 db_writer test cases)
- **`url_hash` UNIQUE dedup verified:** YES — `test_upsert_news_idempotent` (skipped path), `test_upsert_news_body_edited` (updated path), `test_collect_news_idempotent` (full run-through skipped)
- **`tickers TEXT[]` + GIN populated:** YES — `test_upsert_news_multiple_tickers`, `test_upsert_news_gin_index_query_works`, `test_collect_news_multiple_tickers_array`
- **R-09 startup guard (NoAliasesSeededError):** preserved — `test_collect_news_assert_aliases_seeded_raises` confirms it fires before any HTTP call
- **`license_flag='summary_only'` stored:** YES — `test_upsert_news_inserts_fresh`, `test_collect_news_inserts_row`
- **`writer.*` + `_LEGACY_VAULT_ROOT` removed from `collect_news`:** YES — `grep -n "writer\.\|_LEGACY_VAULT_ROOT" src/collectors/news/__init__.py` shows only `db_writer.upsert_news_article` (the new module)

## Deviations from Plan

**None of substance.** All three tasks executed as written. Minor mechanical choices:

1. **Writer / client unit tests retained in `test_collect_news.py`.** The plan
   said "rewrite `tests/collectors/news/test_collect_news.py`" — but the existing
   file contains writer / client tests that exercise `write_news_doc`,
   `vault_path_for_news`, `_assert_two_paragraph_cap`, `fetch_rss_feed`,
   `fetch_article_html`, and `url_hash8`. The writer module is not deleted
   by this plan (01-09 owns that). Removing these tests now would lose coverage
   on still-active code. They are retained as-is; only the `collect_news`
   subsection of the file was rewritten.

2. **Skipped-path SQL split.** The plan's example UPSERT SQL had a
   `WHERE news.content_hash IS DISTINCT FROM EXCLUDED.content_hash` clause
   intended to make the UPDATE conditional. Implementation uses an explicit
   pre-query (`_SELECT_EXISTING_SQL`) → classify in Python → run either the
   UPSERT or the `_BUMP_LAST_SEEN_SQL`. This matches the established pattern
   in `collectors.macro.db_writer.upsert_macro_observations` and gives a
   deterministic outcome value without RETURNING-clause classification
   acrobatics. Net effect on DB state is identical.

3. **`primary_ticker` lookup.** The plan suggested calling
   `resolve_entity(engine, primary_ticker)` to obtain `corp_code` for the FK,
   but `matcher.match_tickers_in_text` already returns dicts containing
   `corp_code`. The collector uses the dict directly — one less DB round-trip
   per article and same data.

## Auth Gates Encountered

None.

## Known Stubs

None introduced by this plan.

## Threat Flags

None — no new network surface (RSS / article fetch helpers unchanged), no new
auth path, no new file-system write boundary (db_writer never writes to disk;
the only persistence is Postgres bind-param INSERT/UPDATE).

## Test Results

| Test file                                          | Tests | Result    |
| -------------------------------------------------- | ----- | --------- |
| `tests/collectors/news/test_db_writer.py`          | 10    | 10 PASS   |
| `tests/collectors/news/test_collect_news.py`       | 23    | 23 PASS   |
| `tests/collectors/news/test_matcher.py` (untouched)| 11    | 11 PASS   |
| **Total (`tests/collectors/news/`)**               | **44**| **44 PASS** |

Runtime: 12-16s for the full news subdir on the session testcontainer.

## Commits

| Task | Hash      | Subject                                                                          |
| ---- | --------- | -------------------------------------------------------------------------------- |
| 1    | `c6ad8d0` | `feat(01-06): add news UPSERT db_writer + url_hash64 + 10 unit tests`           |
| 2    | `3097cf2` | `refactor(01-06): rewire collect_news to db_writer; drop writer/heartbeat/frontmatter` |
| 3    | `15f2fcf` | `test(01-06): port collect_news tests to DB-state assertions`                   |

## Self-Check: PASSED

- `src/collectors/news/db_writer.py` — FOUND
- `src/collectors/news/client.py` modified (url_hash64 added) — FOUND
- `src/collectors/news/__init__.py` modified (writer/heartbeat/frontmatter removed) — FOUND
- `tests/collectors/news/test_db_writer.py` — FOUND
- `tests/collectors/news/test_collect_news.py` modified — FOUND
- commit `c6ad8d0` (Task 1) — FOUND in git log
- commit `3097cf2` (Task 2) — FOUND in git log
- commit `15f2fcf` (Task 3) — FOUND in git log
- 44/44 tests in `tests/collectors/news/` PASS
- `_LEGACY_VAULT_ROOT` absent from `src/collectors/news/__init__.py` (verified by grep)
- `read_frontmatter` / `record_source_run` absent from `src/collectors/news/__init__.py` (verified by inspect)
- `collect_news` signature is `(*, engine, since=None, max_per_feed=100)` (no vault_root)
