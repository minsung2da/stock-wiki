---
phase: 04-analysis-runner-3-role-debate
plan: 02
subsystem: analysis
tags: [roles, rubric, prompts, json-schema, veto-4, veto-5, conviction, stance]
requires:
  - "src/cards/models.py::Decision (six stances mirrored by roles + rubric)"
provides:
  - "src/analysis/roles.py::ROLE_SYSTEM_PROMPTS (Bull/Bear/Judge veto-encoded prompts)"
  - "src/analysis/roles.py::ROLE_SCHEMAS (inline JSON schemas for claude -p --json-schema)"
  - "src/analysis/roles.py::prompt_for / schema_for accessors"
  - "src/analysis/rubric.py::score_to_conviction (Veto #4 decomposable + Veto #5 cap)"
  - "src/analysis/rubric.py::derive_stance (STANCE_TABLE lookup → six stances)"
  - "src/analysis/rubric.py::RUBRIC_WEIGHTS / STANCE_TABLE / CORROBORATING_FAMILIES"
affects:
  - "Wave-3 runner/subagents (04-06) consume prompts+schemas+rubric without re-deriving veto logic"
tech-stack:
  added: []
  patterns:
    - "module-level frozen constants (MappingProxyType) — units.py / number_sanity.py style"
    - "leaf module, no LLM/no I/O, acyclic (no subagents/runner import)"
key-files:
  created:
    - src/analysis/roles.py
    - src/analysis/rubric.py
    - tests/analysis/test_roles.py
    - tests/analysis/test_rubric.py
  modified: []
decisions:
  - "Judge schema omits conviction — the deterministic rubric layer computes it from cited subscores (Veto #4), Judge never self-scores conviction"
  - "conviction = clamp(Σwᵢ·scoreᵢ/(10·Σwᵢ),0,1), denom=10·Σall weights=10; contradiction_penalty subtracts"
  - "Veto #5 cap = 0.79 pin when raw≥0.8 without ≥2 HIGH/MEDIUM refs across ≥2 corroborating families; sentiment excluded from CORROBORATING_FAMILIES"
  - "STANCE_TABLE keyed on (net-strength bucket, currently_held); BUY/ADD downgraded to HOLD when fundamentals_sign<0 AND catalyst_sign<0"
metrics:
  duration_min: 12
  completed: 2026-07-06
---

# Phase 4 Plan 02: Role Prompts + Rubric Summary

Deterministic "intelligence shaping" leaves for the 3-role debate: veto-encoded
Bull/Bear/Judge system prompts + inline JSON schemas (`roles.py`), and the decomposable
Judge rubric → conviction + auditable stance table (`rubric.py`). Both are pure
constants/transforms (no LLM, no I/O), so the Veto #4/#5 guarantees are unit-tested
without spawning a model, keeping the Wave-3 runner thin.

## What Was Built

- **`src/analysis/roles.py`** — `ROLE_SYSTEM_PROMPTS` (bull/bear/judge) each append a shared
  hard-rules block encoding Veto #1 (never predict/forecast a price), prompt-injection
  control (`<untrusted>` content is DATA not instructions), Veto #3 (surface
  contradictions), Veto #5 (no sentiment-alone). `ROLE_SCHEMAS` are `json.dumps`-able
  JSON-Schema dicts with `enum` stance/weight and `additionalProperties:false` on every
  fixed-shape object; the Judge schema is kept flat and its `decision.stance` enum equals
  the six `DecisionCard` stances. `prompt_for` / `schema_for` raise `KeyError` on unknown
  roles. Leaf module — no `subagents`/`runner` import (acyclic).
- **`src/analysis/rubric.py`** — `score_to_conviction(subscores, *, evidence_refs)` returns
  `clamp(Σ wᵢ·scoreᵢ / (10·Σwᵢ), 0, 1)` with `contradiction_penalty` subtracting, then the
  Veto #5 hard cap (0.79 pin) in Python when the value would be ≥0.8 without ≥2 independent
  HIGH/MEDIUM refs spanning ≥2 corroborating families. `derive_stance(...)` is a pure
  `STANCE_TABLE` lookup returning one of the six stances with a fundamentals/catalyst sign
  guard. `RUBRIC_WEIGHTS` / `STANCE_TABLE` / `CORROBORATING_FAMILIES` are module-level frozen
  constants (Veto #4 — every number reproducible from cited inputs).

## Tasks & Commits

| Task | Description | Commit |
|------|-------------|--------|
| 1 | roles.py — prompts + inline JSON schemas | `0254366` |
| 2 (RED) | failing rubric tests | `94a0433` |
| 2 (GREEN) | rubric.py — conviction + stance | `f462ac1` |
| 3 | roles schema/prompt-safety tests | `6b213e4` |

## Verification

- `.venv/Scripts/python.exe -m pytest tests/analysis -q` → **81 passed** (43 prior + 38 new:
  test_rubric 18, test_roles 20). Did NOT spawn the live `claude` CLI (pure-constant tests).
- `pytest tests/test_import_guard.py -q` → **4 passed** (D-01 Max-only: `src/analysis` cannot
  import a cloud-LLM SDK).
- Acceptance criteria met: all-10 multi-source → conviction ≥0.8; same subscores with 1 HIGH
  → capped <0.8 (Veto #5 fired); contradiction_penalty strictly lowers conviction;
  `derive_stance` returns only the six stances; no-price-prediction + `<untrusted>`-as-data
  substrings present in all three prompts; Judge stance enum == six DecisionCard stances.

## Deviations from Plan

None — plan executed exactly as written. (Task 3's `test_rubric.py` was authored during
Task 2's TDD RED phase per the `tdd="true"` flow; Task 3 added `test_roles.py`. Same files,
same coverage, no scope change.)

## TDD Gate Compliance

Task 2 (`tdd="true"`) followed RED → GREEN: `test(04-02)` RED commit `94a0433` precedes the
`feat(04-02)` GREEN commit `f462ac1`. No refactor commit needed (code clean on first pass).

## Known Stubs

None. `roles.py` and `rubric.py` are complete pure modules with no placeholder data or
unwired paths; conviction/stance are fully computed from inputs.

## Notes for Wave 3

- Judge emits NO `conviction` — the runner calls `rubric.score_to_conviction` from the Judge's
  cited subscores + the bundle's evidence weights/families. Do not let the Judge self-score it.
- `evidence_refs` for `score_to_conviction` is `list[{"weight","family"}]`; family must be one of
  `CORROBORATING_FAMILIES` (DART/KRX/macro/news/user_thesis) to count toward the ≥0.8 gate.
- Rubric weights + stance thresholds are `[ASSUMED]` (RESEARCH A1) — Phase 8 eval tunes them;
  they are single-line module constants for that reason.

## Self-Check: PASSED

- Files: roles.py, rubric.py, test_roles.py, test_rubric.py, 04-02-SUMMARY.md all FOUND.
- Commits: `0254366`, `94a0433`, `f462ac1`, `6b213e4` all present in git log.
