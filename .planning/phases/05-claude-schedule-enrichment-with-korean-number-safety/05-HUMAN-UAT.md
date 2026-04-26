---
status: partial
phase: 05-claude-schedule-enrichment-with-korean-number-safety
source: [05-VERIFICATION.md]
started: 2026-04-24T23:57:10Z
updated: 2026-04-26T04:30:00Z
---

## Current Test

Test #4 (idempotency on repeat run) — awaiting second Routine "Run now"
trigger from operator.

## Tests

### 1. End-to-end Routines run
expected: Routine creates `claude/enrich-YYYY-MM-DD` branch, commits `_derived` blocks, opens PR with `auto-merge` label, PR auto-merges after CI passes
result: ok
note: |
  2026-04-26 — Routine `stock-enrich-daily` first Run produced PR #1
  (branch `claude/admiring-brown-vxCJZ` — Anthropic Routines container
  picks its own branch slug instead of literal `claude/enrich-YYYY-MM-DD`,
  but the prefix invariant `claude/*` from D-03 is preserved). PR merged
  via auto-merge after CI `test` job passed (commit bc09c08 on main:
  "chore(enrich): _derived for 2026-04-26 (8 docs)").

  Infrastructure prep that landed during UAT setup:
  - Default branch master → main (gh repo edit --default-branch main).
  - Repo public (required for branch protection on GitHub Free; private
    repos need GitHub Pro).
  - Allow-auto-merge enabled (gh repo edit --enable-auto-merge).
  - Branch protection on main: required `test` status check + required
    PR + linear history.
  - .github/workflows/ci.yml: pytest + COLL-07 import_guard with
    Postgres service container (tensorchord/vchord-suite:pg17-latest).
  - `auto-merge` label created (gh label create).
  - .gitignore: vault/raw/ removed (was incorrectly added — conflicts
    with PROJECT.md §9.2 source-of-truth design); 8 markdown docs
    committed under vault/raw/ so the Routine container's fresh clone
    can see candidate documents.

  Auth model note: Routine container uses Anthropic GitHub App token
  for git push (not the GITHUB_TOKEN env var). The App needed Contents:RW
  + Pull requests:RW on the repo before push succeeded — initial run
  hit 403 until App permissions were upgraded.
why_human: Required claude.ai/code/routines web UI for environment + GitHub App permission grant — both completed by operator on 2026-04-26.

### 2. DART golden-set parity (Success Criterion #3)
expected: All 10 filings show byte-equal numeric values between `_derived` (set by `financials.py`) and dart-fss accessors
result: ok
note: |
  2026-04-25 — Re-run via `scripts/uat_dart_parity.py` against curated 10-corp golden set:
  삼성전자, SK하이닉스, NAVER, 기아, 현대자동차, LG에너지솔루션, KB금융, 삼성SDI,
  삼성바이오로직스, POSCO홀딩스 (bgn_de=20240101). Result: 10/10 filings ok,
  184/184 numeric facts byte-equal, 0 mismatches.

  Bug discovered + fixed during this UAT:
  - `_fs_extract` previously assumed dart-fss returned dict (cassette shape). Live
    `FinancialStatement` has MultiIndex columns via `.show(sheet)`. Fix: route through
    `fs.show(sheet_key)` and flatten MultiIndex to last level. Regression tests:
    `test_fs_extract_live_shape_flattens_multiindex` +
    `test_get_structured_financials_live_shape_end_to_end` (both pass).
  - Original golden-set candidates 카카오 (00918444) and 셀트리온 (00421045) raised
    `RuntimeError('Could not find an annual report')` for bgn_de=20240101 — replaced
    with 기아 + 삼성SDI to keep sector diversity (auto + battery).

  Operator artifact: `scripts/uat_dart_parity.py`. Re-runnable on demand.
why_human: Live OpenDART API key + network access — completed by operator on 2026-04-25.

### 3. Korean number 4-stage pipeline on real Korean news article (Success Criterion #4)
expected: regex extracts candidates → LLM picks → Pydantic validates → digit-checksum confirms; mismatches surface in `review_flags` rather than silent acceptance
result: ok
note: |
  2026-04-26 — Sample (vault/raw/dart/2026/20260318001062_00126380.md,
  Samsung 자기주식 취득 결정): pipeline produced 13 numeric_facts including
  large KRW values like 7,174,300,000,000 원 (취득예정금액), 234,066,285,488,714 원
  (자기주식 취득금액 한도), share counts (37,000,000 주), percentages (2.0%,
  1.7%), and a date-stamped 종가 (193,900 원, period 2026-03-17). All 13
  facts validated cleanly: review_flags=[] for that document (no
  numeric_echo_mismatch, no numeric_sanity_violation, no
  self_inconsistent).

  Document-level coverage (8 enriched docs from PR #1):
  - dart/20260318001062_00126380.md: 13 facts, sentiment=bullish, 0 flags
  - dart/20260318001203_00126380.md: 10 facts, sentiment=neutral, 0 flags
  - krx/000660.md: 1 fact, sentiment=neutral, 0 flags
  - krx/005930.md: 5 facts, sentiment=bearish, 0 flags
  - macro/ecos/722Y001.md: 3 facts, sentiment=neutral, 0 flags
  - macro/ecos/731Y001.md: 7 facts, sentiment=null, 0 flags
  - macro/fred/DCOILWTICO.md: 6 facts, sentiment=mixed, 0 flags
  - macro/fred/DGS10.md: 4 facts, sentiment=bearish, 0 flags

  All 8 documents passed echo-back + sanity validation cleanly. Numeric
  pipeline working end-to-end.
why_human: End-to-end Sonnet invocation completed by Routine on 2026-04-26.

### 4. Idempotency on repeat run (Success Criterion #5)
expected: Identical `_derived` block; provenance and ingest_state zones unchanged; `zone_hash` matches
result: [pending]
why_human: Requires running the routine twice with state stable across runs (Routines container is fresh per run); needs operator to trigger and diff

### 5. Schedule agent zone integrity (Success Criterion #2)
expected: `compute_zone_hash` mismatch triggers `review_flags=['agent_zone_violation']` and skip; provenance/ingest_state remain untouched
result: ok
note: |
  2026-04-26 — Verified by diffing each enriched doc between the
  pre-enrich commit (0b0135f) and post-enrich commit (bc09c08). For
  each of the 8 documents the `provenance` and `ingest_state` YAML
  blocks compared byte-equal between the two commits — the Routine
  modified only the `_derived` zone.

  Verification command (re-runnable):
    uv run python /tmp/check_zones.py
  Result: "8 docs · zone violations = 0".

  No `agent_zone_violation` flag observed across any document
  (review_flags=[] for all 8), confirming the SKILL.md step 15
  `assert_zones_unchanged` guard never had to fire — the agent
  adhered to the zone contract by design rather than by remediation.
why_human: Runtime enforcement observed in actual Routine container — completed 2026-04-26.

## Summary

total: 5
passed: 4
issues: 0
pending: 1
skipped: 0
blocked: 0
partial: 0

## Gaps

- Test #4 (idempotency) — needs a second Routine run after the first PR
  merged. The second run should observe content_hash unchanged on all 8
  docs, skip enrichment for each, and either produce no PR or a no-op PR.
  Operator action: trigger "Run now" again at claude.ai/code/routines;
  check that the resulting branch / PR contains zero modifications to
  vault/raw/**/*.md (or no branch is created at all).

## Minor observations (not UAT failures — backlog candidates)

- D-13 says macro and kind sources MUST set sentiment=null; observed
  sentiment values on macro docs (722Y001=neutral, DCOILWTICO=mixed,
  DGS10=bearish). Only one macro doc (731Y001) correctly returned null.
  Tighten prompts/derived_macro.md echo-back wording.
- KRX docs (000660.md, 005930.md) have tickers=[] in _derived even though
  the filename and frontmatter expose the ticker. Consider seeding
  `_derived.tickers` from `provenance.ticker` for KRX-source docs (cheap
  deterministic step that bypasses LLM extraction).
