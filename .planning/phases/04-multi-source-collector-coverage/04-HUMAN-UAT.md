---
status: partial
phase: 04-multi-source-collector-coverage
source: [04-VERIFICATION.md, 04-VALIDATION.md §Manual-Only, live `stock collect all` run 2026-04-22]
started: 2026-04-21T00:00:00+09:00
updated: 2026-04-22T00:00:00+09:00
---

## Current Test

[gap closure required — 3 integration bugs found during live smoke run]

## Tests

### 1. Live `stock collect all` smoke run (end-to-end isolation contract)
expected:
  - All 4 source keys present in stderr JSON report
  - One forced failure leaves the other 3 at `status: "ok"`
  - `ingested/_status/heartbeat.md` reflects per-source independent timestamps
  - Files appear under `vault/raw/{krx,news,macro,kind}/` for the portfolio tickers
result: FAILED (2026-04-22)
evidence: |
  $ uv run stock collect all 2>/tmp/report.json
  exit: 1
  {"run_at":"2026-04-21T15:48:27+00:00","sources":{
    "krx":   {"status":"error","error":"portfolio.md not found at notes/portfolio.md","elapsed_ms":2},
    "news":  {"status":"error","error":"No name aliases seeded — run `uv run python -m src.db.seed_name_aliases` first","elapsed_ms":239},
    "macro": {"status":"partial","docs_processed":2,"elapsed_ms":4931,"failed_count":2},
    "kind":  {"status":"error","error":"portfolio.md not found at notes/portfolio.md","elapsed_ms":1}
  }}

  Isolation contract IS honored (4 sources ran independently, macro partial-succeeded),
  but 3/4 sources failed due to default-value and data-flow bugs that unit tests missed.

## Summary

total: 1
passed: 0
issues: 3
pending: 0
skipped: 0
blocked: 0

## Gaps

### Gap-04-03 [BUG, HIGH]: CLI `--vault-root` default excludes `vault/` subdirectory
source: live `stock collect all` 2026-04-22 (krx + kind errors)
symptom: |
  `collect_krx` and `collect_kind` raise `PortfolioFileNotFoundError: portfolio.md not found at notes/portfolio.md` when run with default flags.
root_cause: |
  `src/cli/__main__.py:43` sets `--vault-root default="."`, but the repo's portfolio file lives at `vault/notes/portfolio.md` (Phase 4 Plan 01 seed location). `Portfolio.load(vault_root)` constructs `<vault_root>/notes/portfolio.md`, which resolves to `./notes/portfolio.md` under the default — wrong path.
  CLAUDE.md and ROADMAP Phase 4 SC #1 both use `vault/raw/...` paths, confirming `vault` is the intended vault root.
fix:
  - `src/cli/__main__.py`: change `--vault-root` default from `"."` to `"vault"`.
  - Update help text: "Vault root directory (default: vault)".
  - Add integration test that runs the CLI with NO `--vault-root` flag and asserts all 4 collectors resolve the portfolio.
verification_gap: |
  `tests/test_cli_collect_all.py` passes because all test scenarios explicitly pass a test-fixture `vault_root` path via argparse. The default-value branch was never exercised.

### Gap-04-04 [BUG, HIGH]: `collect_macro` ECOS item_code server-side filter produces empty response
source: live `stock collect macro` 2026-04-22 (base_rate_kr + usd_krw both failed)
symptom: |
  `{"failed":[{"doc":"base_rate_kr","error":"ECOS empty after filter: 722Y001"},{"doc":"usd_krw","error":"ECOS empty after filter: 731Y001"}]}`
root_cause: |
  `src/collectors/macro/fetcher.py:45` passes `통계항목코드1=item_code` as a kwarg to PublicDataReader's ECOS client. PublicDataReader does not translate that Korean kwarg into the ECOS URL's 7th path segment (item-code filter). The raw response comes back, but the library's pagination/parsing path drops rows that the server returns with unrelated ITEM_CODE1 values, leaving the defensive client-side filter (line 53) with 0 matches.
  Direct live verification (curl `https://ecos.bok.or.kr/api/StatisticSearch/...`) for 722Y001 returns 15 rows over a 7-day window including 5 rows with ITEM_CODE1=0101000 (한국은행 기준금리). So the data is there — the library-call shape is wrong.
fix_options:
  A. Drop the `통계항목코드1=item_code` kwarg to PublicDataReader; rely purely on the client-side `ITEM_CODE1` filter at line 53 against the full response. Simplest; known-correct (matches direct curl behavior).
  B. Replace PublicDataReader with direct `requests` calls to `https://ecos.bok.or.kr/api/StatisticSearch/{API_KEY}/json/kr/{start}/{end}/{stat_code}/{cycle}/{from}/{to}` — full control, no black-box dependency.
  preference: A (minimal change, preserves library abstraction).
verification_gap: |
  `tests/collectors/macro/` uses recorded JSON fixtures that already match the item_code, so the client-side filter never ran against unfiltered real data. Fixture should include rows for multiple ITEM_CODE1 values to exercise the filter.

### Gap-04-05 [DOCS + UX, MEDIUM]: First-run seed step not documented; CLI gives no hint
source: live `stock collect news` 2026-04-22
symptom: |
  `{"status":"error","error":"No name aliases seeded — run \`uv run python -m src.db.seed_name_aliases\` first"}`
root_cause: |
  Plan 01's R-09 startup check (`matcher.assert_aliases_seeded`) is working as designed — raises `NoAliasesSeededError` with a corrective message. But:
  1. There is no "first-run setup" documentation in README or CLAUDE.md that lists the seed step alongside `uv sync` / `.env` setup.
  2. The CLI's `--help` output does not mention that `collect news` requires a pre-seeded `entity_aliases` table.
  3. `stock collect all` does not run the seed as a prerequisite OR opportunistically.
fix:
  - Add a "First-time setup" section to README (or CLAUDE.md ops section) listing:
    1. `uv sync`
    2. Configure `.env` (DART/ECOS/FRED keys, DATABASE_URL)
    3. Alembic migrate: `uv run alembic upgrade head`
    4. Seed aliases: `uv run python -m src.db.seed_name_aliases`
    5. Run collector.
  - `stock collect news --help` footer should hint: "Requires: run `python -m src.db.seed_name_aliases` once before first use."
  - Consider a `stock setup` meta-command that runs steps 3+4 idempotently (nice-to-have, not required).
verification_gap: |
  Tests mock the engine with pre-seeded aliases in the `seeded_engine` fixture, so the `NoAliasesSeededError` path exists as a unit test but its operational friction was not surfaced until real-run.

### Gap-04-06 [TEST COVERAGE, MEDIUM]: `test_cli_collect_all.py` misses default-flag integration contract
source: inference from Gap-04-03 + Gap-04-04
symptom: |
  Three integration bugs (vault_root default, ECOS filter, seed precondition) slipped past 120 passing tests because no test exercises the CLI with default flags against a realistic non-fixture environment.
root_cause: |
  All existing CLI tests pass `--vault-root` explicitly and mock the collectors' fetch paths, avoiding the live library-call shape. This violates the spirit of Phase 4 SC #5 ("orchestrated run ... the other three complete successfully").
fix:
  - Add `tests/test_cli_default_flags.py` with a test that:
    1. Creates a tmp-path vault containing `notes/portfolio.md` with a single watchlist ticker.
    2. Runs the CLI subprocess with NO flags beyond `--vault-root <tmp>` (to exercise argparse defaults where safe).
    3. Asserts the stderr JSON schema and exit code contract under at least one real-library code path (e.g., a Real ECOS response replayed via `responses` or `pytest-httpx`).
  - This is a safety net, not a replacement for the existing mocked unit tests.

### Gap-04-01 [deferred, out-of-scope]: investment_caution / investment_risk event types
status: deferred
description: (unchanged — tracked as V2-KIND-01 backlog)

### Gap-04-02 [RESOLVED]: CONTEXT D-14 text still reflects pre-execution hybrid
status: resolved
resolved_at: 2026-04-24
resolved_via: quick-260424-asr-context-d14-amendment
description: |
  CONTEXT.md D-14 본문을 Option D 전략으로 갱신 (DART `pblntf_ty="I"` 3종 + KIND
  스크레이핑 1종 + KRX 교차확증). pykrx 경로 폐기 근거(함수 부재, live 검증),
  개념 축(기업평가 vs 시장가격) 재정리, 정규식 상수 위치(`sources.py`), 보조
  교차확증 메커니즘을 모두 문서화. 04-05-SUMMARY의 Strategy Amendment 섹션과 상호 참조.
