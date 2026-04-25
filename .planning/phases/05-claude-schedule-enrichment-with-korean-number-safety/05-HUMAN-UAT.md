---
status: partial
phase: 05-claude-schedule-enrichment-with-korean-number-safety
source: [05-VERIFICATION.md]
started: 2026-04-24T23:57:10Z
updated: 2026-04-25T02:15:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. End-to-end Routines run
expected: Routine creates `claude/enrich-YYYY-MM-DD` branch, commits `_derived` blocks, opens PR with `auto-merge` label, PR auto-merges after CI passes
result: [pending]
why_human: Requires Anthropic Routines cloud container, Max subscription quota, GitHub PAT, and live GitHub auto-merge — cannot be exercised programmatically from local repo

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
result: [pending]
why_human: End-to-end requires real Sonnet call; unit tests cover stages independently but integrated behavior needs an actual run

### 4. Idempotency on repeat run (Success Criterion #5)
expected: Identical `_derived` block; provenance and ingest_state zones unchanged; `zone_hash` matches
result: [pending]
why_human: Requires running the routine twice with state stable across runs (Routines container is fresh per run); needs operator to trigger and diff

### 5. Schedule agent zone integrity (Success Criterion #2)
expected: `compute_zone_hash` mismatch triggers `review_flags=['agent_zone_violation']` and skip; provenance/ingest_state remain untouched
result: [pending]
why_human: Helper unit tests pass but the actual enforcement happens inside SKILL.md prompt-driven control flow at runtime

## Summary

total: 5
passed: 1
issues: 0
pending: 4
skipped: 0
blocked: 0
partial: 0

## Gaps

- Tests #1, #3, #4, #5 require deploying the Routine (claude.ai/code/routines)
  per README §5.2. They will be exercised together by a single "Run now"
  invocation and a follow-up second run for idempotency byte-diff.
