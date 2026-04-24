---
phase: 5
slug: claude-schedule-enrichment-with-korean-number-safety
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-24
updated: 2026-04-24
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (existing project stack; `[tool.pytest.ini_options]` in pyproject.toml) |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run --extra dev pytest tests/test_units.py tests/test_number_extraction.py tests/test_number_sanity.py tests/test_backlog.py tests/test_heartbeat_enrich.py tests/test_disk_metrics.py tests/test_frontmatter_v2.py tests/test_facts_equal.py tests/test_enrich_walk.py tests/test_zone_integrity.py tests/test_skill_structure.py -x -q` |
| **Full suite command** | `uv run --extra dev pytest -x --tb=short -m "not integration"` |
| **Integration (DART cassette)** | `uv run --extra dev pytest tests/test_dart_financials.py -x -q` |
| **Estimated runtime** | ~8 seconds (unit-only); <20 seconds full |

---

## Sampling Rate

- **After every task commit:** Run the plan-specific test file (e.g., editing `number_sanity.py` → run `tests/test_number_sanity.py`). ≤5 s per loop.
- **After every plan wave:** Run quick-run command above. ≤10 s.
- **Before `/gsd-verify-work`:** Full suite must be green + DART cassette integration green.
- **Max feedback latency:** 10 seconds (unit-only)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 5-01-01 | 01 | 1 | INGEST-05 | T-05-01-01 / T-05-01-02 | Pydantic `extra="forbid"` + Literal enums reject hallucinated keys/values | unit | `pytest tests/test_frontmatter_v2.py -x -q` | ❌ W0 | ⬜ pending |
| 5-01-02 | 01 | 1 | INGEST-05 | T-05-01-03 | Legacy Phase 3/4 YAML loads without error (additive migration) | unit | `pytest tests/test_frontmatter_v2.py::test_legacy_phase3_shape_still_validates -x -q` | ❌ W0 | ⬜ pending |
| 5-02-01 | 02 | 2 | INGEST-07 | T-05-02-01 | Unknown unit returns None (no KeyError exposure) | unit | `pytest tests/test_units.py -x -q` | ❌ W0 | ⬜ pending |
| 5-02-02 | 02 | 2 | INGEST-07 | T-05-02-02 | Non-KRW units return None (no silent FX) | unit | `pytest tests/test_units.py::test_non_krw_returns_none -x -q` | ❌ W0 | ⬜ pending |
| 5-03-01 | 03 | 2 | INGEST-07 | T-05-03-02 | Character offsets codepoint-safe on Hangul | unit | `pytest tests/test_number_extraction.py::test_hankyung_offsets_roundtrip -x -q` | ❌ W0 | ⬜ pending |
| 5-03-02 | 03 | 2 | INGEST-07 | T-05-03-03 | MAX_CANDIDATES_PER_DOC caps overflow | unit | `pytest tests/test_number_extraction.py::test_candidate_overflow_trimmed -x -q` | ❌ W0 | ⬜ pending |
| 5-04-01 | 04 | 2 | INGEST-07 | T-05-04-01 | Echo-back flags hallucinated source_span | unit | `pytest tests/test_number_sanity.py::test_hallucinated_fact_flagged -x -q` | ❌ W0 | ⬜ pending |
| 5-04-02 | 04 | 2 | INGEST-07 | T-05-04-02 | Sanity range flags out-of-range magnitudes | unit | `pytest tests/test_number_sanity.py::test_sanity_out_of_range -x -q` | ❌ W0 | ⬜ pending |
| 5-04-03 | 04 | 2 | INGEST-07 | T-05-04-03 | Unit mismatch flagged | unit | `pytest tests/test_number_sanity.py::test_unit_mismatch_flagged -x -q` | ❌ W0 | ⬜ pending |
| 5-05-01 | 05 | 3 | INGEST-06 | T-05-05-02 | COLL-07 preserved — no anthropic/openai imports in financials.py | unit | `pytest tests/test_dart_financials.py::test_no_llm_imports -x -q` | ❌ W0 | ⬜ pending |
| 5-05-02 | 05 | 3 | INGEST-06 | T-05-05-03 | Synonym map resolves "수익(매출액)" → canonical "매출액" | integration | `pytest tests/test_dart_financials.py::test_service_firm_synonym_resolved -x -q` | ❌ W0 | ⬜ pending |
| 5-05-03 | 05 | 3 | INGEST-06 | — | Returned NumericFacts have source_span=None (D-14 structured path) | unit | `pytest tests/test_dart_financials.py::test_all_facts_are_valid_pydantic -x -q` | ❌ W0 | ⬜ pending |
| 5-06-01 | 06 | 3 | INGEST-03, INGEST-04 | T-05-06-02 | first_seen persistence across runs | unit | `pytest tests/test_backlog.py::test_first_seen_preserved -x -q` | ❌ W0 | ⬜ pending |
| 5-06-02 | 06 | 3 | INGEST-03 | — | Chronic items (3+ days) surfaced | unit | `pytest tests/test_backlog.py::test_chronic_detected -x -q` | ❌ W0 | ⬜ pending |
| 5-06-03 | 06 | 3 | INGEST-03 | — | Prior-day sections preserved verbatim | unit | `pytest tests/test_backlog.py::test_prior_nontoday_sections_preserved -x -q` | ❌ W0 | ⬜ pending |
| 5-07-01 | 07 | 3 | INGEST-03 | — | 5 D-24 SLA thresholds compute alert_level correctly | unit | `pytest tests/test_heartbeat_enrich.py -x -q -k alert_level` | ❌ W0 | ⬜ pending |
| 5-07-02 | 07 | 3 | INGEST-04 | T-05-07-04 | Non-enrich sources unchanged (COLL-08 isolation) | unit | `pytest tests/test_heartbeat_enrich.py::test_other_sources_unchanged -x -q` | ❌ W0 | ⬜ pending |
| 5-07-03 | 07 | 3 | INGEST-03 | — | .git excluded from vault_mb walk | unit | `pytest tests/test_disk_metrics.py::test_git_excluded_from_vault_mb -x -q` | ❌ W0 | ⬜ pending |
| 5-08-01 | 08 | 4 | INGEST-02 | T-05-08-07 | COLL-07 guard preserved (no anthropic/openai in src/collectors/ingest/shared) | unit | `pytest tests/test_skill_structure.py::test_src_guard_still_clean -x -q` | ❌ W0 | ⬜ pending |
| 5-08-02 | 08 | 4 | INGEST-03 | — | Idempotent walk: unchanged content_hash + populated _derived → skip | unit | `pytest tests/test_enrich_walk.py::test_populated_derived_stable_hash_skipped -x -q` | ❌ W0 | ⬜ pending |
| 5-08-03 | 08 | 4 | INGEST-03 | — | F-4c stick: skip_reason set + stable hash → skip | unit | `pytest tests/test_enrich_walk.py::test_skip_reason_sticks_until_hash_changes -x -q` | ❌ W0 | ⬜ pending |
| 5-08-04 | 08 | 4 | INGEST-04 | T-05-08-03 | Zone-integrity SHA256 detects provenance/ingest_state drift | unit | `pytest tests/test_zone_integrity.py::test_provenance_change_detected -x -q` | ❌ W0 | ⬜ pending |
| 5-08-05 | 08 | 4 | INGEST-05 | T-05-08-08 | facts_equal tuple-set equality (Pitfall 3 resolution) | unit | `pytest tests/test_facts_equal.py -x -q` | ❌ W0 | ⬜ pending |
| 5-08-06 | 08 | 4 | INGEST-02 | — | SKILL.md structure: frontmatter + 5 required sections + 4 prompts | unit | `pytest tests/test_skill_structure.py -x -q` | ❌ W0 | ⬜ pending |
| 5-08-07 | 08 | 4 | INGEST-05 | — | D-13 sentiment routing: KIND/macro prompts force sentiment=null | unit | `pytest tests/test_skill_structure.py::test_kind_and_macro_prompts_force_sentiment_null -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

All test files listed below are MISSING and MUST be created alongside each plan's implementation task (test files are co-delivered with code, not a separate Wave 0 task):

- [ ] `tests/test_frontmatter_v2.py` — Plan 05-01 Task 2
- [ ] `tests/test_units.py` — Plan 05-02 Task 2
- [ ] `tests/test_number_extraction.py` — Plan 05-03 Task 1 (tests first, impl Task 2)
- [ ] `tests/fixtures/number_extraction/hankyung_sample.md` — Plan 05-03 Task 1
- [ ] `tests/fixtures/number_extraction/dart_narrative_sample.md` — Plan 05-03 Task 1
- [ ] `tests/test_number_sanity.py` — Plan 05-04 Task 2
- [ ] `tests/test_dart_financials.py` — Plan 05-05 Task 1
- [ ] `tests/fixtures/dart_financial_responses/samsung_2025q4.json` — Plan 05-05 Task 1
- [ ] `tests/fixtures/dart_financial_responses/service_firm_synonym.json` — Plan 05-05 Task 1
- [ ] `tests/test_backlog.py` — Plan 05-06 Task 2
- [ ] `tests/test_heartbeat_enrich.py` — Plan 05-07 Task 2
- [ ] `tests/test_disk_metrics.py` — Plan 05-07 Task 1
- [ ] `tests/test_facts_equal.py` — Plan 05-08 Task 1
- [ ] `tests/test_enrich_walk.py` — Plan 05-08 Task 1
- [ ] `tests/test_zone_integrity.py` — Plan 05-08 Task 1
- [ ] `tests/test_skill_structure.py` — Plan 05-08 Task 2

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| End-to-end Routines execution: operator creates routine → Run now → PR lands on `main` with `_derived` populated | INGEST-02, INGEST-03, INGEST-04 | Claude Code Routines is a cloud product; can't be exercised from CI. Anthropic-operated substrate. | Follow `.claude/routines/enrich/README.md` Routine Creation steps + click "Run now" once → verify commit + PR on `main` with non-empty `_derived` on at least one document. |
| GitHub auto-merge actually merges PR after required checks pass | D-03 | Depends on repo admin config (branch protection + auto-merge enablement). Can't be asserted from within routine. | Per README step: repo Settings → Allow auto-merge; add branch protection rule for `main` with required checks; label the PR `auto-merge` — confirm GitHub merges after CI green. |
| Sonnet 4.6 Korean extraction accuracy ≥85% on 10-filing + 10-news golden set | INGEST-05 | LLM evaluation — requires running live API. Baseline measurement during Phase 5 manual smoke + Wave 1 golden set review. | After manual Routines smoke: sample 20 `_derived` blocks from first week of production runs; spot-check against source bodies; record hit rate. Below 85% → add 3-shot prompt examples (deferred to Phase 9 unless triggered). |
| Phase 5 daily routine remains supported (research preview continuity) | INGEST-02 | External Anthropic product state. Monitor monthly. | Check `code.claude.com/docs/en/routines` every 30 days until feature leaves preview. Fallback: local `stock enrich` CLI (deferred per CONTEXT). |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s (unit-only quick run)
- [x] `nyquist_compliant: true` set in frontmatter
- [x] `security_enforcement` applied: every plan carries `<threat_model>` with STRIDE dispositions

**Approval:** approved 2026-04-24
