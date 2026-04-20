---
phase: 04-multi-source-collector-coverage
plan: 04
subsystem: collectors
tags: [news, rss, trafilatura, feedparser, alias-matching, copyright-summary]

requires:
  - phase: 04-multi-source-collector-coverage
    provides: [ProvenanceBlock.tickers/outlet/license_flag/trust_level, TickerRef, seed_name_aliases CLI, resolve_entity_by_alias]
provides:
  - collect_news() end-to-end collector for 한경 + 이데일리 (COLL-03)
  - Alias-based matcher (load_scoped_aliases + match_tickers_in_text) reusable for future outlets
  - RSS vs article-HTML fetch separation with shared http(s) scheme guard
  - D-13 copyright policy enforced (2-paragraph hard cap) at writer level
affects: [ingest pipeline (delimiter wrap for semi_trusted news), Phase 5 embeddings, stock-mcp news search]

tech-stack:
  added: [feedparser>=6.0]
  patterns:
    - "R-01 preload-then-scan matcher: one DB round-trip at collector start, substring scan per article"
    - "R-08 fetch separation: requests for RSS bytes, trafilatura for article HTML; shared scheme guard only"
    - "D-13 writer-level cap: _assert_two_paragraph_cap raises on >2 paragraphs — defense in depth"
    - "Cross-URL dedup by content_hash (no URL canonicalization) — accepted tradeoff, deferred"

key-files:
  created:
    - src/collectors/news/__init__.py (collect_news orchestration, 122 lines)
    - src/collectors/news/client.py (fetch_rss_feed + fetch_article_html, scheme guard)
    - src/collectors/news/fetcher.py (feedparser parse_rss + extract_first_two_paragraphs)
    - src/collectors/news/matcher.py (load_scoped_aliases, match_tickers_in_text, assert_aliases_seeded)
    - src/collectors/news/writer.py (vault_path_for_news, write_news_doc, _assert_two_paragraph_cap)
    - src/collectors/news/feeds.py (verified RSS URL constants + detect_outlet helper)
    - tests/collectors/news/test_matcher.py (10 tests)
    - tests/collectors/news/test_collect_news.py (21 tests)
    - tests/fixtures/rss/{hankyung_economy,hankyung_finance,edaily_news}.xml
    - tests/fixtures/news/{hankyung,edaily}_sample.html
    - .gitleaksignore (whitelists a public JS cookie token in fixture HTML)
  modified:
    - pyproject.toml (added feedparser>=6.0 to collectors group)

key-decisions:
  - "edaily RSS stays plain HTTP — HTTPS fails with connection reset; probe verified this is an upstream constraint (Microsoft-IIS/7.5 without TLS SNI on 125.209.202.172)"
  - "Browser-like User-Agent required (edaily rejects minimal UA strings); constant USER_AGENT in client.py"
  - "Matcher uses substring scan over regex token extraction — better recall on Korean particles/punctuation/nicknames"
  - "Aliases <2 chars filtered out of alias_map to avoid pathological matches"
  - "trafilatura called with deduplicate=False — the LRU cache across calls breaks cross-URL dedup tests (and makes legitimate duplicate-body articles vanish)"
  - "content_hash is title+\\n\\n+body normalized — URL-independent, so R-11 cross-URL dedup works as documented"

patterns-established:
  - "R-08 fetch separation: RSS via requests (feedparser decodes bytes), articles via trafilatura.fetch_url — independent retry scopes"
  - "R-09 startup guard: collectors refuse to run when seed data missing; raises before any HTTP call"
  - "Writer-level defense-in-depth: both fetcher (D-13 trim) AND writer (_assert_two_paragraph_cap) enforce the 2-paragraph cap"

requirements-completed: [COLL-03]

duration: ~30min
completed: 2026-04-20
---

# Phase 04 Plan 04: News Collector Summary

**한경 + 이데일리 RSS collector with alias-based ticker matching, trafilatura summary extraction, and D-13 copyright-safe 2-paragraph cap.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-04-20T13:12:00Z
- **Completed:** 2026-04-20T13:42:27Z
- **Tasks:** 2 (Wave-0 probe + full implementation)
- **Files modified:** 12 (9 created, 2 modified, 5 fixtures + 1 gitleaks ignore)

## Accomplishments

- `collect_news()` runs end-to-end against fixture RSS + article HTML; writes matched articles only, drops rest
- R-01 pre-load matcher: single SQL call per run returns `{alias: entry}` scoped to holdings ∪ watchlist; in-memory substring scan with longest-alias-wins dedup
- R-08 separation: `client.fetch_rss_feed` (requests, browser UA) vs `client.fetch_article_html` (trafilatura); both share http(s) scheme guard (SSRF T-04-10)
- R-09 startup guard: `collect_news` raises `NoAliasesSeededError` BEFORE any HTTP call when `entity_aliases` has no name rows (test proves zero fetches happen)
- R-11 cross-URL dedup documented: distinct URLs with identical bodies produce two files (different `url_hash8`) but identical `content_hash` in frontmatter — test verifies
- D-13 copyright cap: body limited to first 2 `\n\n`-separated paragraphs; `_assert_two_paragraph_cap` raises on violation (defense in depth against upstream changes)
- D-24 `trust_level='semi_trusted'` + `license_flag='summary_only'` set on every news frontmatter

## Task Commits

1. **Task 1: Wave-0 probe + fixtures + feeds.py** — `806e74c` (feat)
   - Fixtures captured live 2026-04-20 (operator-verified); committed as-is per execution prompt
   - `feeds.py`: `HANKYUNG_ECONOMY_FEED`, `HANKYUNG_FINANCE_FEED`, `EDAILY_FEED` (http://, not https), `FEEDS_BY_OUTLET`, `detect_outlet(url)`
2. **Task 2: collect_news implementation + 31 tests** — `c2ff5be` (feat, TDD: RED → GREEN)

## Files Created/Modified

- `src/collectors/news/feeds.py` — URL constants + outlet detection (verified URLs, edaily stays http://)
- `src/collectors/news/client.py` — RSS/article fetch separation, tenacity retry on transient network errors, http(s) scheme guard
- `src/collectors/news/fetcher.py` — feedparser `parse_rss` returning `RSSItem`, trafilatura `extract_first_two_paragraphs`
- `src/collectors/news/matcher.py` — `NoAliasesSeededError`, `assert_aliases_seeded`, `load_scoped_aliases`, `match_tickers_in_text`
- `src/collectors/news/writer.py` — `vault_path_for_news` (regex guards), `compute_news_content_hash`, `write_news_doc`, `_assert_two_paragraph_cap`
- `src/collectors/news/__init__.py` — `collect_news` orchestration, idempotency short-circuit, heartbeat write
- `tests/collectors/news/test_matcher.py` — 10 tests: single-SQL verification, title+body match, nicknames, scope exclusion, dedup, startup guard
- `tests/collectors/news/test_collect_news.py` — 21 tests: writer path validation, scheme guard, R-08 fetch separation, end-to-end writes, drop-unmatched, idempotency, cross-URL dedup, heartbeat, soft-skip on empty trafilatura, body truncation
- `pyproject.toml` — `feedparser>=6.0` added to collectors group
- `.gitleaksignore` — whitelist a public JS cookie token baked into the hankyung fixture HTML (not a project secret)

## Decisions Made

- **trafilatura `deduplicate=False`:** Initially used `deduplicate=True` (recommended default), but its LRU across calls breaks R-11 cross-URL dedup tests (second identical body returns None). For the 2-paragraph-cap use case the dedup benefit is minimal; disabling is the right call.
- **Matcher skips aliases <2 chars:** Single-character names (e.g., bare "S") would match wildly. Documented in `load_scoped_aliases`.
- **Writer recomputes content_hash in collect_news for idempotency check:** Avoids redundant writer call; `compute_news_content_hash` exposed as a public helper.
- **`extra_alias` test helper inserts raw rows:** Tests need nickname aliases (`'삼전'`) without running the full seed CLI; direct INSERT is test-local and scoped.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] trafilatura deduplicate=True caused cross-URL dedup test failures**
- **Found during:** Task 2 (cross-URL dedup test)
- **Issue:** The plan's action block specified `deduplicate=True`. That flag enables an LRU across calls, so the second identical-body article returns None and isn't written — contradicting the plan's own R-11 requirement that both files should exist.
- **Fix:** `deduplicate=False` in `fetcher.extract_first_two_paragraphs`.
- **Files modified:** src/collectors/news/fetcher.py
- **Verification:** R-11 test now verifies two files + identical content_hash.
- **Committed in:** `c2ff5be`

**2. [Rule 2 - Missing Critical] .gitleaksignore needed for fixture**
- **Found during:** Task 1 commit (pre-commit hook failed)
- **Issue:** hankyung article fixture HTML contains a literal JS cookie-relay key string that gitleaks flags as a generic-api-key. It's a public third-party page token, not a project secret, but unignored it blocks commits.
- **Fix:** Added `.gitleaksignore` entry with explanation.
- **Files modified:** .gitleaksignore (new)
- **Verification:** gitleaks passes; commit succeeds.
- **Committed in:** `806e74c`

**3. [Rule 3 - Blocking] db dep group not in uv sync**
- **Found during:** Task 2 test run (alembic ModuleNotFoundError)
- **Issue:** Fresh uv sync only installed `collectors/ingest/dev` groups; `seeded_engine` fixture requires alembic from the `db` group.
- **Fix:** `uv sync --group collectors --group ingest --group dev --group db`. Not a code change — operator-environment fix.
- **Files modified:** uv.lock regenerated
- **Verification:** All 31 news tests run.
- **Committed in:** `c2ff5be`

---

**Total deviations:** 3 auto-fixed (1 bug, 1 missing critical, 1 blocking)
**Impact on plan:** All essential for correctness/security/execution. No scope creep.

## Issues Encountered

- Ruff F841 (unused `paragraphs` local in one test) caught by pre-commit; removed in the same commit flow.

## User Setup Required

None. `src/db/seed_name_aliases.py` is the operator prerequisite (must be run once before `collect_news`), but that module shipped in Plan 01.

## Next Phase Readiness

- Plan 04-05 (forum collector) can now follow the same alias-matching pattern (matcher is outlet-agnostic).
- Plan 04-06 (source-of-truth delimiters in ingest) can rely on `trust_level='semi_trusted'` being set on every news doc.
- Scheme guard + writer regex guards cover SSRF + path-traversal for the news subsystem (T-04-10, T-04-11).

## Verification Evidence

- `uv run pytest tests/collectors/news/ -x -q` — 31 passed in 19.15s
- `uv run pytest tests/test_import_guard.py -x -q` — 4 passed (no anthropic/openai in news package)
- `uv run pytest tests/ -k "frontmatter or heartbeat or dart or portfolio or entity_alias or krx or macro" -x -q` — 97 passed, 1 skipped (regression clean)

## Self-Check: PASSED

- All 12 listed files exist on disk (verified post-commit).
- Commits `806e74c` and `c2ff5be` present in `git log`.
- 31 news tests pass fresh; regression suite green.

---
*Phase: 04-multi-source-collector-coverage*
*Completed: 2026-04-20*
