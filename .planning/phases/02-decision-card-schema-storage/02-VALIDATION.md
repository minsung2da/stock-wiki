---
phase: 02
slug: decision-card-schema-storage
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-29
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from 02-RESEARCH.md § Validation Architecture (ROADMAP SC#1–6 as requirement anchors;
> no REQUIREMENTS.md IDs exist for v2.0 yet — that file is stale v1.0).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + testcontainers[postgres] 4.14.2 (real Postgres 17 + vchord) |
| **Config file** | `pyproject.toml` (markers `slow`/`e2e`); session fixtures `pg_engine`/`pg_clean`/`seeded_engine` in `tests/conftest.py` + `tests/db/conftest.py` |
| **Quick run command** | `uv run pytest tests/cards -x -q` |
| **Full suite command** | `uv run pytest -m "not slow and not e2e"` |
| **Estimated runtime** | ~60 seconds (testcontainers Postgres spin-up dominates; per-test < 1s once warm) |

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/cards tests/db/test_migration_0007.py -x -q`
- **After every plan wave:** `uv run pytest -m "not slow and not e2e"`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

> Requirement column uses ROADMAP Phase 2 Success Criteria (SC#1–6) as anchors. Task IDs are
> filled in by the planner; rows below are the SC→test contract the plans must satisfy.

| Requirement | Wave | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|------|-----------------|-----------|-------------------|-------------|--------|
| SC#1 — 12 locked columns + PK/FK | 1 | Pydantic validates card input before INSERT (V5) | schema | `uv run pytest tests/db/test_migration_0007.py::test_decision_cards_shape -x` | ❌ W0 | ⬜ pending |
| SC#2 — 3 mandatory indexes (names + DESC) | 1 | N/A | schema | `uv run pytest tests/db/test_migration_0007.py::test_decision_cards_indexes -x` | ❌ W0 | ⬜ pending |
| SC#3 — §3 YAML round-trips via DecisionCard | 1 | `extra="forbid"` rejects unknown keys (V5) | unit | `uv run pytest tests/cards/test_models.py::test_round_trip -x` | ❌ W0 | ⬜ pending |
| SC#4 — save/get_active/walk_supersedes/invalidate; supersession atomic | 1 | bind-param SQL only; no f-string interpolation (Tampering) | integration (DB) | `uv run pytest tests/cards/test_store.py -x` | ❌ W0 | ⬜ pending |
| SC#5 — missing expiry OR empty assumptions → ValidationError | 1 | hard-veto #2 enforced at type layer | unit | `uv run pytest tests/cards/test_models.py::test_missing_expiry_rejected -x` | ❌ W0 | ⬜ pending |
| SC#6 — body_tsv GENERATED + GIN index; `simple` config; query returns rows | 1 | N/A | schema+integration | `uv run pytest tests/db/test_migration_0007.py::test_body_tsv_generated -x` | ❌ W0 | ⬜ pending |
| drift — ORM ↔ DB column-set parity for DecisionCard | 1 | N/A | schema | `uv run pytest tests/db/test_migration_0007.py::test_orm_round_trip -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/cards/conftest.py` — `decision_card_yaml` fixture transcribed verbatim from redesign §3 (`card_005930_2026-05-28`). This IS the SC#3 round-trip oracle.
- [ ] `tests/cards/test_models.py` — round-trip (SC#3) + 2 hard-veto rejection tests (SC#5: missing `expires_at`, empty `assumptions`).
- [ ] `tests/cards/test_store.py` — CRUD + supersession atomicity (uses `seeded_engine`, which pre-inserts 삼성전자/005930/00126380 so the `corp_code` FK is satisfiable).
- [ ] `tests/db/test_migration_0007.py` — schema-shape + index + body_tsv + ORM round-trip (clone `tests/db/test_migration_0006.py` structure exactly).
- [ ] Add `decision_cards` to `_LIVE_TABLES` in `tests/conftest.py` for TRUNCATE hygiene (self-ref handled by `CASCADE`; place before `entities`).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | — |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
