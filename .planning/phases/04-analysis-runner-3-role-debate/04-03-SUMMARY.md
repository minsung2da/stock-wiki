---
phase: 04-analysis-runner-3-role-debate
plan: 03
subsystem: analysis
tags: [evidence-bundle, D-02, prefetch, injection-wrap, reproducibility]
requires:
  - "src/mcp_v2/tools/{filing,market,search,note} (in-process callables)"
  - "src/mcp_v2/injection.wrap_untrusted (D-03 delimiter, applied upstream by tools)"
  - "db.entity.resolve_entity (corp_code → current_ticker)"
provides:
  - "analysis.bundle.EvidenceBundle — fixed pre-fetched evidence snapshot (D-02)"
  - "analysis.bundle.build_bundle(engine, corp_code, as_of, *, portfolio_note_path)"
  - "EvidenceBundle.to_stdin() — deterministic, bounded, <untrusted>-preserving serialization"
affects:
  - "04-06 analyze_ticker orchestrator (SC#2 step a → hands the same bundle to Bull/Bear/Judge)"
tech-stack:
  added: []
  patterns:
    - "Pydantic v2 ConfigDict(extra='forbid') reusing mcp_v2.models types as bundle fields"
    - "greedy priority-ordered narrative packing under a char cap (drop whole bodies)"
key-files:
  created:
    - src/analysis/bundle.py
    - tests/analysis/test_bundle.py
  modified: []
decisions:
  - "build_bundle takes portfolio_note_path (only-if-held policy stays in the runner, 04-06); keeps bundle focused + hermetically testable"
  - "hybrid note/filing bodies re-fetched via get_note/get_filing; news hits keep only the wrapped snippet (no whole-body news tool)"
  - "to_stdin char cap = 100K [ASSUMED]; drop lowest-weight WHOLE body first, never mid-body (T-04-08)"
metrics:
  duration: ~18 min
  completed: 2026-07-06
  tasks: 2
  files: 2
---

# Phase 4 Plan 3: EvidenceBundle (D-02 fixed pre-fetch) Summary

D-02 `EvidenceBundle` + `build_bundle` assemble ALL evidence for one ticker ONCE via the
Phase-3 in-process MCP tools and expose a deterministic, bounded, `<untrusted>`-preserving
`to_stdin()` — the fixed snapshot SC#2 step (a) hands identically to Bull/Bear/Judge (sub-agents
call no tools), and the reproducibility anchor for Phase-8 CPCV.

## What Was Built

- **`src/analysis/bundle.py`**
  - `EvidenceBundle` (Pydantic, `extra="forbid"`) holds typed tool outputs directly: `filings`
    (whole wrapped bodies, Veto #8), `ohlcv`/`flow` ranges + `peers` (3 `PeerView`s, Veto #5/#6),
    `hybrid_hits` + re-fetched `hybrid_bodies`, and an optional `portfolio_note`.
  - `build_bundle(engine, corp_code, as_of, *, portfolio_note_path=None)` — resolves the ticker via
    `resolve_entity` (raises `ValueError` on unknown entity / missing ticker), then pre-fetches:
    `search_filings(since=as_of−180d)` → top-5 `get_filing` whole bodies; `ohlcv_range(−90d)`,
    `flow_range(−30d)`, `peer_view` × {per,pbr,roe}; `hybrid_search(name+catalyst, date_range=−30d)`
    → filing/note full-body re-fetch (deduped against `filings`); `get_note` only if a path is given.
    Window/limit constants are module-level `[ASSUMED]` (Discretion #3).
  - `to_stdin()` — deterministic serialization; emits each narrative body INSIDE its existing
    `<untrusted source=... ref=...>` delimiter verbatim (never re-wrapped/stripped) + compact numeric
    text; enforces a 100K char cap by greedily including narrative blocks in priority order (user
    thesis → newest filings → hybrid bodies), dropping oversized WHOLE bodies rather than truncating.
  - No `run_sql`, no raw `text(` SQL — only the typed tools (Veto #7).

- **`tests/analysis/test_bundle.py`** (8 tests) — wrapped filings, numeric ranges + 3 PeerViews,
  bounded `to_stdin` preserving `<untrusted source=`, reproducibility (equal bundle + equal stdin),
  portfolio note only-when-held, cap drops whole bodies (oversized dropped, small sibling intact),
  unknown corp_code raises, and a source scan (no `run_sql(`/`text(`/cloud-LLM import). `encode_query`
  is stubbed so `hybrid_search` runs without the bge-m3 download.

## Verification

- `.venv/Scripts/python.exe -m pytest tests/analysis/test_bundle.py -q` → **8 passed**.
- `.venv/Scripts/python.exe -m pytest tests/analysis -q` → **89 passed** (no regressions).
- `.venv/Scripts/python.exe -m pytest tests/test_import_guard.py -q` → **4 passed** (src/analysis stays cloud-LLM-free).
- No live `claude` CLI invoked.

## Deviations from Plan

None of Rules 1–4 triggered. One planned-discretion resolution worth noting: `build_bundle` accepts
`portfolio_note_path` rather than computing held-ness itself — the only-if-held decision belongs to
the 04-06 runner (which already loads the portfolio for the D-04 gate), and it keeps the bundle
hermetically testable. This is within the plan's `<action>` ("get_note … only if held") — the trigger
is lifted one level up, not changed.

## Known Stubs

None. `ohlcv`/`flow`/`peers` are legitimately empty against the seeded corpus (no OHLCV/fundamentals
rows seeded) — the tools return valid empty models (D-01), not stubbed data. Against the live DB
(200 entities / 578 filings) these populate from real rows.

## Self-Check: PASSED

- `src/analysis/bundle.py` — FOUND
- `tests/analysis/test_bundle.py` — FOUND
- commit `3ea3401` (feat bundle) — FOUND
- commit `fa23eb9` (test bundle) — FOUND
