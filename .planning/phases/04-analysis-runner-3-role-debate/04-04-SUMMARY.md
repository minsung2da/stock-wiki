---
phase: 04-analysis-runner-3-role-debate
plan: 04
subsystem: analysis
tags: [stance-gate, D-04, SC#6, no-llm, lightweight-refresh, token-economics]
requires:
  - "src/cards/models.DecisionCard (prior card shape: as_of/generated_at/expires_at/key_claims/decision)"
  - "src/cards/store.get_active (prior active card — runner passes it to the gate)"
  - "src/mcp_v2/tools/filing.{search_filings,get_filing} + tools/market.{ohlcv_range,flow_range} (signals)"
  - "db.entity.resolve_entity (current ticker for price/flow reads)"
provides:
  - "analysis.gate.decide(engine, prior, as_of, *, safety_net_days=14) -> GateDecision (FULL|REFRESH + reasons)"
  - "analysis.gate.lightweight_refresh(engine, prior, as_of) -> DecisionCard | Escalate"
  - "analysis.gate.GateDecision / Escalate result types + FULL/REFRESH constants"
affects:
  - "04-06 analyze_ticker runner (calls decide → FULL runs the 3-role debate; REFRESH runs lightweight_refresh, then saves/supersedes)"
tech-stack:
  added: []
  patterns:
    - "frozen dataclass control-flow results (GateDecision/Escalate) — pydantic reserved for persisted contracts"
    - "deterministic trigger fan-out collecting ALL fired reasons for observability"
    - "refresh rebuilt through DecisionCard.model_validate to re-enforce Veto #2 (model_copy skips validators)"
key-files:
  created:
    - src/analysis/gate.py
    - tests/analysis/test_gate.py
  modified: []
decisions:
  - "lightweight_refresh PRESERVES generated_at (not bumped) so the N-day safety net counts from the last FULL debate — bumping it (loose plan wording) would let daily refreshes keep the safety net from ever firing"
  - "assumption-break trigger = deterministic evidence-resolution proxy (a cited dart: filing no longer resolves via get_filing); free-text invalidation_triggers cannot be evaluated without an LLM (Veto #1)"
  - "gate thresholds are module-level [ASSUMED] constants (7% / 3× vol / 2σ / D-7 / N=14 / 45d trail) — Discretion #5, tune in Phase 8"
metrics:
  duration: ~7 min
  completed: 2026-07-06
  tasks: 3
  files: 2
---

# Phase 4 Plan 4: D-04 Stance-Change Gate (SC#6) Summary

`analysis.gate` is the deterministic, NO-LLM token-economics gate: `decide()` returns FULL
(re-debate) only on a real change — new filing, ≥7% close-to-close move / 3× volume, 2σ flow
spike, near-expiry (D-7), a broken cited-evidence assumption, or the N=14d safety net — else
REFRESH; `lightweight_refresh()` cheaply re-validates the prior card without re-debating,
never extends `expires_at`, and escalates on a material shift. The module can never reach the
LLM (imports nothing from `analysis.subagents`/`runner`, spawns no subprocess).

## What Was Built

- **`src/analysis/gate.py`**
  - `GateDecision(action: FULL|REFRESH, reasons: tuple[str, ...])` frozen dataclass + `is_full`
    property; `reasons` carries EVERY fired trigger (observability), empty ⇒ REFRESH.
  - `decide(engine, prior, as_of, *, safety_net_days=14)` — first-run (`prior is None`) → FULL;
    otherwise evaluates the full D-04 set and collects fired reasons:
    - cheap timestamp triggers (no DB): near-expiry `expires_at − as_of ≤ 7d`; safety-net
      `as_of − generated_at ≥ N`;
    - signal triggers (typed tools): new filing since `prior.as_of` (`search_filings`); price
      spike |close-to-close| ≥ 7% OR volume ≥ 3× trailing-20d avg (`ohlcv_range`); flow spike
      |foreign/inst net| ≥ 2× trailing-20d stdev (`flow_range`); assumption-break (a cited
      `dart:` filing no longer resolves).
    - Any reason ⇒ FULL; none ⇒ REFRESH. All thresholds are `[ASSUMED]` module constants.
  - `Escalate(reasons)` sentinel + `lightweight_refresh(engine, prior, as_of)` — bumps `as_of`
    + assigns a fresh `card_id`, **preserves `expires_at`** (T-04-10 — never extend; near-expiry
    is itself a FULL trigger) and **preserves `generated_at`** (safety-net clock). Re-validates
    each `key_claim.evidence_ref`: a new mid-refresh filing OR a HIGH-weight claim losing its
    evidence ⇒ `Escalate` (runner runs the full debate); a non-HIGH unresolved ref ⇒ appended to
    `warnings` (dropped fact never silently lost). The refreshed card is rebuilt through
    `DecisionCard.model_validate` so Veto #2 (assumptions non-empty, `expires_at` present) is
    re-enforced.
  - No `run_sql`, no raw `text(` SQL in the gate (Veto #7) — signals via the typed tools only;
    `resolve_entity` supplies the current ticker.

- **`tests/analysis/test_gate.py`** (12 tests) — each trigger drives FULL (first-run, new
  filing, ≥7% move, near-expiry, isolated safety-net), no-trigger → REFRESH (`reasons == ()`),
  refresh keeps `expires_at` + `generated_at` and returns a valid card, refresh does not extend
  expiry even with a far-forward as_of, Escalate on broken HIGH-weight assumption / new
  mid-refresh filing, an AST assert that gate.py imports nothing from
  `analysis.subagents`/`runner` (+ no anthropic/openai/subprocess), and a runtime assert that the
  REFRESH path loads no sub-agent module (SC#6 skip-the-debate). Fixtures local to the file;
  `seeded_engine` reused (not edited).

## Verification

- `.venv/Scripts/python.exe -m pytest tests/analysis/test_gate.py -x -q` → **12 passed**.
- `.venv/Scripts/python.exe -m pytest tests/analysis -q` → **105 passed** (no regressions).
- `.venv/Scripts/python.exe -m pytest tests/test_import_guard.py -q` → **4 passed** (src/analysis stays cloud-LLM-free).
- `ruff check` + `mypy --strict src/analysis/gate.py` → clean.
- No live `claude` CLI invoked; gate + refresh contain no LLM call and no `run_sql` (Veto #7).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Correctness] `lightweight_refresh` preserves `generated_at` instead of bumping it**
- **Found during:** Task 2
- **Issue:** The Task 2 `<action>` text says "bump `as_of` and `generated_at`". Bumping
  `generated_at` on every cheap refresh would reset the safety-net clock (`as_of −
  prior.generated_at`), so a daily refresh would keep the N-day safety net from EVER firing —
  defeating the must_have "safety-net … each force a FULL debate" and the token-economics
  guarantee. The DecisionCard schema has no separate `last_full_debate_at` field, so
  `generated_at` must mean "time of last full generation" for the safety net to work.
- **Fix:** Refresh bumps only `as_of` (+ new `card_id`) and preserves `generated_at`. This
  aligns with the authoritative must_have truth ("bumps `as_of` and re-validates … WITHOUT
  extending expires_at", which names only `as_of`) and RESEARCH #5 ("Lightweight refresh
  recomputes: `as_of`, re-confirm each key_claim …") — neither requires bumping `generated_at`.
- **Files modified:** src/analysis/gate.py
- **Commit:** f635976

### Design resolutions (within plan discretion)

- **Assumption-break trigger** is a deterministic evidence-resolution proxy: a `key_claim`'s
  cited `dart:<rcept_no>` no longer resolving via `get_filing` (FilingNotFound) = "an assumption
  no longer supported by current evidence" (RESEARCH #5). Free-text
  `decision.invalidation_triggers` cannot be evaluated in pure Python without an LLM (Veto #1),
  so the gate uses the checkable evidence-existence signal; the deeper semantic re-check is the
  refresh's escalation path.

## Known Stubs

None. `ohlcv`/`flow` reads return valid empty models (D-01) against the seeded corpus (no OHLCV
rows seeded except where a test inserts them); price/flow spikes fire against real rows. The gate
is fully wired — every trigger reads live signals, none returns placeholder data.

## Self-Check: PASSED

- `src/analysis/gate.py` — FOUND
- `tests/analysis/test_gate.py` — FOUND
- commit `a9e9e6f` (feat gate.decide) — FOUND
- commit `f635976` (feat gate.lightweight_refresh) — FOUND
- commit `d99e15b` (test gate) — FOUND
