---
phase: 4
slug: analysis-runner-3-role-debate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-28
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `.venv/Scripts/python.exe -m pytest tests/analysis -q` |
| **Full suite command** | `.venv/Scripts/python.exe -m pytest tests/analysis tests/cards tests/shared -q` |
| **Estimated runtime** | ~30–90 seconds (LLM sub-agent calls mocked; no live `claude` CLI in unit tests) |

---

## Sampling Rate

- **After every task commit:** Run `.venv/Scripts/python.exe -m pytest tests/analysis -q`
- **After every plan wave:** Run the full suite command above
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~90 seconds

---

## Per-Task Verification Map

> Populated by the planner per task. The `claude` CLI debate calls MUST be mocked
> in unit tests (a `DebateBackend`/subprocess seam) — do NOT hit the live CLI or
> spend Max quota during the test suite.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 4-01-01 | 01 | 1 | SC#3 (numeric checksum) | — | Korean-unit normalize + verbatim source check; fail → drop + `_warnings` | unit | `.venv/Scripts/python.exe -m pytest tests/analysis -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/analysis/` — new test package + `conftest.py` with a `FakeDebateBackend` fixture (no live `claude` CLI)
- [ ] Seeded `EvidenceBundle` fixture (reuse the live 578-filing corpus or a small fixture subset)

*Planner refines this list against the final task breakdown.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| End-to-end `analyze_ticker` against the live `claude` CLI emits a valid decision_card | SC#1, SC#2 | Spends Max quota + needs live OAuth; not suitable for CI | Run `analyze_ticker("00126380", as_of=...)` once manually; assert a saved active card with expires_at + assumptions + numeric_facts checksummed |
| Token/cost economics of 3-role × N tickers (Open Q4) | SC#7 | Real cost only observable against live CLI | Capture `total_cost_usd`/`duration_ms` from a real run; feed Phase 9 quota analysis |
