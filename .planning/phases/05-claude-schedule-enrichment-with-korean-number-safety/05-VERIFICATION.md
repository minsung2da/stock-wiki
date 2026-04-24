---
phase: 05-claude-schedule-enrichment-with-korean-number-safety
verified: 2026-04-24T23:57:10Z
status: human_needed
score: 5/5 must-haves verified (artifact + structural)
overrides_applied: 0
human_verification:
  - test: "Run Claude Schedule routine end-to-end against real vault/raw/ documents"
    expected: "Routine creates claude/enrich-YYYY-MM-DD branch, commits _derived blocks, opens PR with auto-merge label, PR auto-merges after CI passes"
    why_human: "Requires Anthropic Routines cloud container, Max subscription quota, GitHub PAT, and live GitHub auto-merge — cannot be exercised programmatically from local repo"
  - test: "DART golden-set parity (Success Criterion #3): 10 filings → compare _derived.numeric_facts to dart-fss values"
    expected: "All 10 filings show byte-equal numeric values between _derived (set by financials.py) and dart-fss accessors"
    why_human: "Requires live OpenDART API key, network access, and human curation of the 10-filing set; CI runs against cassette only"
  - test: "Korean number 4-stage pipeline on real Korean news article (Success Criterion #4)"
    expected: "regex extracts candidates → LLM picks → Pydantic validates → digit-checksum confirms; mismatches surface in review_flags rather than silent acceptance"
    why_human: "End-to-end requires real Sonnet call; unit tests cover stages independently but integrated behavior needs an actual run"
  - test: "Idempotency on repeat run (Success Criterion #5): re-run schedule on unchanged document, byte-compare _derived"
    expected: "Identical _derived block; provenance and ingest_state zones unchanged; zone_hash matches"
    why_human: "Requires running the routine twice with state stable across runs (Routines container is fresh per run); needs operator to trigger and diff"
  - test: "Schedule agent zone integrity (Success Criterion #2): attempt to write outside _derived"
    expected: "compute_zone_hash mismatch triggers review_flags=['agent_zone_violation'] and skip; provenance/ingest_state remain untouched"
    why_human: "Helper unit tests pass but the actual enforcement happens inside SKILL.md prompt-driven control flow at runtime"
---

# Phase 5: Claude-Schedule Enrichment with Korean Number Safety — Verification Report

**Phase Goal:** Ingest worker extracts `_derived` attributes via a Claude Schedule agent that runs outside the ingest venv and commits enriched frontmatter back through git. Korean financial numbers stay out of free-form LLM extraction (DART via dart-fss structured accessors; narrative numbers via regex→LLM→Pydantic→digit-checksum). Embeddings remain bge-m3 1024-d via sentence-transformers. The ingest venv `anthropic`/`openai` ban (COLL-07) is preserved.

**Verified:** 2026-04-24T23:57:10Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Schedule agent (outside ingest venv) polls vault/raw, extracts attributes, commits via git; ingest venv has no anthropic/openai imports; CI guard COLL-07 still passes | ✓ VERIFIED (structural) | `.claude/routines/enrich/SKILL.md` (93 lines) defines daily loop. `grep -rE "^(import\|from) (anthropic\|openai)" src/collectors src/ingest` returns 0 matches. `tests/test_import_guard.py` enforces COLL-07. End-to-end execution requires human run. |
| 2 | Schedule agent writes only `_derived` zone (provenance/ingest_state write-protected) | ✓ VERIFIED (structural) | `.claude/routines/enrich/helpers/zone_integrity.py::compute_zone_hash` exists. SKILL.md step 2 stashes `zone_before = compute_zone_hash(fm)` and asserts unchanged post-write. Runtime enforcement needs human run. |
| 3 | DART numeric_facts match dart-fss structured accessors on 10-filing golden set (no LLM) | ✓ VERIFIED (structural) | `src/collectors/dart/financials.py::get_structured_financials` constructs `NumericFact(unit="KRW원", value_krw=value, source_span=None)` directly from dart-fss. `LINE_ITEM_SYNONYMS` maps canonical Korean keys. `tests/fixtures/dart_financial_responses/samsung_2025q4.json` cassette provides offline coverage. 10-filing live golden set requires human run. |
| 4 | Narrative numbers pass 4-stage pipeline (regex → LLM → Pydantic → checksum); disagreements flag for review | ✓ VERIFIED (structural) | Stage 1: `src/shared/number_extraction.py::extract_numeric_candidates` (regex). Stage 2: SKILL.md prompts (LLM). Stage 3: `DerivedBlock`/`NumericFact` Pydantic Literals. Stage 4: `src/shared/number_sanity.py::check_echo_back` + `check_sanity` + 20+ SANITY_RULES. Mismatches map to `ReviewFlag` (`numeric_echo_mismatch`, `numeric_sanity_violation`). Live integration requires human run. |
| 5 | Re-running on unchanged document produces byte-identical `_derived`; three zones non-overlapping | ✓ VERIFIED (structural) | `.claude/routines/enrich/helpers/walk.py::find_candidates` skips when `_derived` populated and content_hash unchanged (D-19 idempotency). `tests/test_enrich_walk.py::test_populated_derived_stable_hash_skipped` and `test_skip_reason_sticks_until_hash_changes` cover the logic. End-to-end byte-equal verification needs human run. |

**Score:** 5/5 truths verified at structural level; 5/5 require human runtime confirmation.

### Required Artifacts

All 29 artifacts across 8 plans verified via `gsd-tools verify artifacts`: `all_passed=true`.

| Plan | Artifact | Status |
|------|----------|--------|
| 05-01 | `src/shared/frontmatter.py` (ReviewFlag, EventType, extended NumericFact/SentimentBlock/DerivedBlock) | ✓ VERIFIED |
| 05-01 | `tests/test_frontmatter_v2.py` | ✓ VERIFIED |
| 05-02 | `src/shared/units.py` (`normalize_to_krw`, `KRW_MULTIPLIERS`) | ✓ VERIFIED |
| 05-02 | `tests/test_units.py` | ✓ VERIFIED |
| 05-03 | `src/shared/number_extraction.py` (`extract_numeric_candidates`, `NumericCandidate`) | ✓ VERIFIED |
| 05-03 | `tests/test_number_extraction.py` + 2 fixtures | ✓ VERIFIED |
| 05-04 | `src/shared/number_sanity.py` (`SANITY_RULES` ≥20, `check_echo_back`, `check_sanity`) | ✓ VERIFIED |
| 05-04 | `tests/test_number_sanity.py` | ✓ VERIFIED |
| 05-05 | `src/collectors/dart/financials.py` (`get_structured_financials`, `LINE_ITEM_SYNONYMS`) | ✓ VERIFIED |
| 05-05 | `tests/fixtures/dart_financial_responses/samsung_2025q4.json` + test | ✓ VERIFIED |
| 05-06 | `src/ingest/backlog.py` (`render_backlog`, `BacklogItem`) | ✓ VERIFIED |
| 05-06 | `tests/test_backlog.py` | ✓ VERIFIED |
| 05-07 | `src/ingest/heartbeat.py` (`compute_enrich_alert_level`) | ✓ VERIFIED |
| 05-07 | `src/ingest/disk_metrics.py` (`compute_disk_metrics`, `compute_disk_alert_level`) | ✓ VERIFIED |
| 05-07 | `tests/test_heartbeat_enrich.py` + `tests/test_disk_metrics.py` | ✓ VERIFIED |
| 05-08 | `.claude/routines/enrich/SKILL.md` (93 lines, defines daily loop) | ✓ VERIFIED |
| 05-08 | `.claude/routines/enrich/README.md` (operator runbook) | ✓ VERIFIED |
| 05-08 | 4 prompts (`derived_dart_b.md`, `derived_news.md`, `derived_kind.md`, `derived_macro.md`) | ✓ VERIFIED |
| 05-08 | 3 helpers (`facts_equal.py`, `walk.py`, `zone_integrity.py`) + 4 tests | ✓ VERIFIED |

### Key Link Verification

| From | To | Via | Status |
|------|----|----|--------|
| `DerivedBlock` | `ReviewFlag` / `NumericFact` / `SentimentBlock` | typed Pydantic fields, additive | ✓ WIRED |
| `units.normalize_to_krw` | `frontmatter.NumericFact.unit` Literal | unit enum values match Literal | ✓ WIRED |
| `number_sanity.check_echo_back` | `number_extraction.NumericCandidate` offsets | codepoint-safe `body[offset:offset+...]` | ✓ WIRED |
| `number_sanity.check_sanity` | `units.normalize_to_krw` | `value_krw` compared against min/max | ✓ WIRED |
| `dart/financials.py` | `frontmatter.NumericFact` | direct construction with `unit="KRW원"` | ✓ WIRED |
| `dart/financials.py` | `dart/client.py::get_client` | `from .client import` | ✓ WIRED |
| `heartbeat.py` | `disk_metrics.py` | `record_source_run` accepts disk dict | ✓ WIRED |
| Routines SKILL.md | helpers (walk/zone_integrity/facts_equal) | imports + step references | ✓ WIRED (structurally) |

### Anti-Pattern Scan

- COLL-07 (`anthropic`/`openai` imports in `src/collectors` or `src/ingest`): 0 violations
- Schedule agent code lives at `.claude/routines/enrich/` (outside collectors/ingest as required by D-29)
- `tests/test_import_guard.py` enforces the rule in CI

No blocker anti-patterns found. The 1 critical + 4 warnings reported during code review have been auto-fixed (commits 332e4ea, 4296729, 85ac868, ad2c724, 7b6709e).

### Requirements Coverage

| Requirement | Description | Source Plan(s) | Status | Evidence |
|-------------|-------------|----------------|--------|----------|
| INGEST-02 | `_derived` extraction by separate Schedule agent (git round-trip); ingest venv has no anthropic/openai | 05-08 | ✓ SATISFIED | SKILL.md + COLL-07 guard test |
| INGEST-03 | Agent detects docs missing `_derived`; idempotent on stable hash | 05-06, 05-07, 05-08 | ✓ SATISFIED | `walk.find_candidates` + idempotency tests; backlog + heartbeat observability |
| INGEST-04 | Agent writes only `_derived`; doctor reports zone drift | 05-06, 05-07, 05-08 | ✓ SATISFIED (structural) | `zone_integrity.compute_zone_hash`; doctor scan is Phase 6 (deferred per ROADMAP) |
| INGEST-05 | LLM extracts tickers/event_type/catalysts/sentiment/numeric_facts/summary into `_derived` | 05-01, 05-08 | ✓ SATISFIED | DerivedBlock v2 schema + 4 source-specific prompts |
| INGEST-06 | DART financials via dart-fss structured accessor (no LLM) | 05-05 | ✓ SATISFIED | `get_structured_financials` + cassette tests |
| INGEST-07 | Narrative numbers via regex → LLM → Pydantic → digit-checksum | 05-02, 05-03, 05-04, 05-08 | ✓ SATISFIED | units + number_extraction + number_sanity + SKILL.md pipeline |

All 6 phase requirements accounted for. No orphans.

### Test Evidence

User-reported: full test suite ran 427 passed, 2 skipped. All 12 phase-5 test files exist:
- `tests/test_frontmatter_v2.py`, `tests/test_units.py`, `tests/test_number_extraction.py`, `tests/test_number_sanity.py`
- `tests/test_dart_financials.py`, `tests/test_backlog.py`, `tests/test_heartbeat_enrich.py`, `tests/test_disk_metrics.py`
- `tests/test_facts_equal.py`, `tests/test_enrich_walk.py`, `tests/test_zone_integrity.py`, `tests/test_skill_structure.py`

### Human Verification Required

5 items (see frontmatter `human_verification:` for full detail):

1. **End-to-end Routines run** — Anthropic Routines cloud container, Max subscription quota, GitHub PAT, live GitHub auto-merge cannot be exercised programmatically.
2. **DART 10-filing golden set parity** (Success Criterion #3) — needs live OpenDART API key + human curation.
3. **4-stage Korean number pipeline integrated** (Success Criterion #4) — needs real Sonnet call.
4. **Idempotency byte-compare** (Success Criterion #5) — needs operator to trigger 2 runs and diff.
5. **Zone-integrity enforcement at runtime** (Success Criterion #2) — helper tests pass; runtime path needs live confirmation.

### Gaps Summary

No structural gaps detected. All 29 artifacts exist at substantive sizes; all key links wired; all 6 requirements covered across 8 plans; COLL-07 guard preserved; SKILL.md and helpers present at the prescribed `.claude/routines/enrich/` path (D-29).

The 5 human-verification items above represent inherent runtime/integration concerns that no automated programmatic check can satisfy from a local repo snapshot — they are not gaps in the code but require operator action to close the goal-achievement loop.

---

_Verified: 2026-04-24T23:57:10Z_
_Verifier: Claude (gsd-verifier)_
