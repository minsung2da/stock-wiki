---
status: partial
phase: 05-claude-schedule-enrichment-with-korean-number-safety
source: [05-VERIFICATION.md]
started: 2026-04-24T23:57:10Z
updated: 2026-04-24T23:57:10Z
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
result: [pending]
why_human: Requires live OpenDART API key, network access, and human curation of the 10-filing set; CI runs against cassette only

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
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
