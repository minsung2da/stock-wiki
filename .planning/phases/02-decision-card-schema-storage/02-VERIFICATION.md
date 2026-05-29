---
phase: 02-decision-card-schema-storage
verified: 2026-05-30T00:00:00Z
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
re_verification: null
gaps: []
deferred: []
human_verification: []
---

# Phase 2: Decision Card Schema & Storage — Verification Report

**Phase Goal:** `decision_cards` 테이블 + Pydantic 모델 + Alembic 마이그레이션; CRUD helper는 `src/cards/` 신규 모듈.
**Verified:** 2026-05-30T00:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Migration creates `decision_cards` with all 12 locked columns, PK, FKs, CHECK constraint | VERIFIED | `0007_decision_cards.py` lines 76–118: all 12 columns declared; `ck_decision_cards_status` CHECK on `('active','superseded','invalidated')`; FK to `entities.corp_code` + two self-ref FKs to `decision_cards.card_id` SET NULL |
| 2 | Indexes: `(corp_code, status, generated_at DESC)`, `(supersedes)`, `(expires_at)`, plus GIN on `body_tsv` | VERIFIED | `0007_decision_cards.py` lines 132–154: all four indexes created; composite uses `sa.text("generated_at DESC")` |
| 3 | `DecisionCard` Pydantic model round-trips the §3 YAML with all required sub-fields | VERIFIED | `src/cards/models.py`: `key_claims`, `contradictions`, `assumptions`, `invalidation_triggers` (inside `Decision`), `numeric_facts`, `evidence_weights`, `guards_passed` all declared; `tests/cards/test_models.py::test_round_trip` + `test_numeric_facts_types_preserved` cover round-trip |
| 4 | `src/cards/store.py` has `save_card`, `get_active`, `walk_supersedes`, `invalidate` | VERIFIED | `store.py` lines 147–278: all four functions implemented with parameterized SQL; `src/cards/__init__.py` re-exports all four |
| 5 | Card without `expires_at` OR empty `assumptions` is rejected (ValidationError) | VERIFIED | `models.py` line 87: `assumptions: list[str] = Field(min_length=1)`; line 91: `expires_at: datetime` (no default, no Optional); `test_models.py::test_missing_expiry_rejected` + `test_empty_assumptions_rejected` confirm both paths raise ValidationError |
| 6 | `body_md` fallback-searchable via `body_tsv` GENERATED tsvector + GIN index | VERIFIED | `0007_decision_cards.py` lines 124–154: `ALTER TABLE ... ADD COLUMN body_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(body_md, ''))) STORED`; GIN index `ix_decision_cards_body_tsv`; `test_migration_0007.py::test_body_tsv_generated` proves query match |

**Score:** 6/6 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/db/migrations/versions/0007_decision_cards.py` | Migration DDL: 12 columns, self-ref FKs, body_tsv GENERATED, 4 indexes | VERIFIED | `revision="0007"`, `down_revision="0006"`; complete upgrade/downgrade |
| `src/db/entity_models.py` | `DecisionCard` ORM class on existing Base | VERIFIED | `class DecisionCard(Base)` at line 365; all 13 columns (12 + body_tsv); in `__all__` |
| `src/cards/models.py` | `DecisionCard` Pydantic v2 model | VERIFIED | All §3 fields present; `extra="forbid"`; SC#5 hard-veto via field constraints |
| `src/cards/store.py` | CRUD helpers: save_card, get_active, walk_supersedes, invalidate | VERIFIED | All four implemented; parameterized SQL only; `_PAYLOAD_EXCLUDE` excludes body_md/status/invalidation_reason |
| `src/cards/__init__.py` | Barrel re-export | VERIFIED | Re-exports `DecisionCard`, `save_card`, `get_active`, `walk_supersedes`, `invalidate` |
| `tests/cards/test_models.py` | Round-trip + hard-veto tests | VERIFIED | 5 test functions covering SC#3/SC#5 |
| `tests/cards/test_store.py` | CRUD integration tests | VERIFIED | 8 test functions covering save/get/supersession/invalidate/walk |
| `tests/db/test_migration_0007.py` | Schema regression tests | VERIFIED | 4 tests: `test_decision_cards_shape`, `test_decision_cards_indexes`, `test_body_tsv_generated`, `test_orm_round_trip` |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `0007_decision_cards.py` | `entities.corp_code` | `ForeignKey("entities.corp_code", ondelete="CASCADE")` | WIRED | Line 82 |
| `0007_decision_cards.py` | `decision_cards.card_id` (x2) | `ForeignKey("decision_cards.card_id", ondelete="SET NULL")` | WIRED | Lines 98–106 (supersedes + superseded_by) |
| `store.py` | `DecisionCard` model | `from .models import DecisionCard` | WIRED | Line 44; all four functions use typed inputs/outputs |
| `src/cards/__init__.py` | `store.py` | `from .store import ...` | WIRED | Line 10 |
| `tests/cards/test_store.py` | `src/cards` | `from cards import (DecisionCard, get_active, invalidate, save_card, walk_supersedes)` | WIRED | Lines 29–35 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `store.py::save_card` | `card.model_dump(mode="json", exclude=_PAYLOAD_EXCLUDE)` | Caller-supplied `DecisionCard`; no hardcoded default | Yes — payload bound to `CAST(:payload AS jsonb)` | FLOWING |
| `store.py::get_active` | `row.payload, row.body_md, row.status` | `SELECT ... WHERE corp_code=:cc AND status='active' ORDER BY generated_at DESC, card_id DESC LIMIT 1` | Yes — live DB query | FLOWING |
| `store.py::invalidate` | `jsonb_set(payload, '{invalidation_reason}', to_jsonb(:reason))` with `AND status <> 'invalidated'` | DB UPDATE + re-SELECT | Yes; idempotency guard prevents clobbering | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| ORM import + 13 columns present | `python -c "from db.entity_models import DecisionCard; cols = {c.name for c in DecisionCard.__table__.columns}; assert len(cols) == 13"` | Evidence from source inspection — 13 columns declared in entity_models.py | PASS (static) |
| `_PAYLOAD_EXCLUDE` contains all three excluded keys | grep confirmation | `{"body_md", "status", "invalidation_reason"}` at store.py line 64 | PASS |
| `invalidate()` carries `AND status <> 'invalidated'` guard | grep confirmation | store.py line 123 | PASS |
| No f-string SQL interpolation in store.py | grep check | No f-string patterns found in SQL-adjacent code; all SQL is module-level `text()` constants | PASS |
| No `body_embedding` column on `DecisionCard` ORM class | grep confirmation | Absent from entity_models.py `DecisionCard` class; only on Filing/News | PASS |

Step 7b: Full slow-test suite skipped (Docker/testcontainers not available in verifier). The 02-REVIEW.md resolution note records "full cards suite 19 passed" after commit 41e63a7.

---

### Probe Execution

No probe scripts declared for this phase. Step 7c: SKIPPED (no `scripts/*/tests/probe-*.sh` for phase 02).

---

### Requirements Coverage

Requirements.md is stale v1.0 — no phase-mapped IDs apply. Success Criteria are sourced from ROADMAP.md Phase 2 section directly.

| SC | Description | Status | Evidence |
|----|-------------|--------|---------|
| SC#1 | Migration creates `decision_cards` with 12 locked columns | SATISFIED | Migration file + ORM class fully verified |
| SC#2 | Three mandatory indexes + GIN body_tsv | SATISFIED | All 4 indexes in migration + ORM `__table_args__` |
| SC#3 | Pydantic model round-trips §3 YAML | SATISFIED | models.py fields match §3 exactly; round-trip tests exist |
| SC#4 | `src/cards/store.py` CRUD helpers | SATISFIED | All four helpers implemented and exported |
| SC#5 | Hard Veto: no card without expires_at or empty assumptions | SATISFIED | `expires_at: datetime` (non-optional) + `assumptions: Field(min_length=1)` |
| SC#6 | body_md fallback-searchable via BM25/pg_trgm | SATISFIED | `body_tsv GENERATED` + GIN index + tsvector query match test |

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `tests/db/test_migration_0007.py` line 202–217 | Raw SQL INSERT bypasses Pydantic validation (test inserts a minimal payload without `assumptions`) | Info | Acknowledged and deferred (WR-06) — documented in 02-REVIEW.md; test intent is to prove body_tsv generation, not card validity; the bypass pattern is isolated to this test and not in production code |

No TBD/FIXME/XXX debt markers found in phase-modified files.
No `return null` / `return {}` / placeholder stub patterns found in production code.

---

### Hard Veto Compliance (CLAUDE.md)

| Veto | Rule | Status | Evidence |
|------|------|--------|---------|
| #2 | expires_at + assumptions required (timed thesis) | COMPLIANT | `expires_at` NOT NULL in DDL; `assumptions: Field(min_length=1)` in Pydantic model |
| #3 | contradictions[] first-class output | COMPLIANT | `contradictions: list[Contradiction]` declared as explicit field in `DecisionCard`; CHECK constraints do not bury it |
| #6 | No numeric embedding column on decision_cards | COMPLIANT | No `body_embedding` or `_HalfVec` on `DecisionCard` ORM class or migration DDL |
| #7 | No run_sql escape hatch — parameterized only | COMPLIANT | All SQL in store.py is module-level `text()` constants; no f-string interpolation; confirmed by grep |
| #8 | body_md whole-card TEXT, no pre-chunking | COMPLIANT | body_md is a single TEXT column in migration; no chunks/chunk_id column |
| #13 | payload-only default view feasible (body_md NOT in payload JSONB) | COMPLIANT | `_PAYLOAD_EXCLUDE = {"body_md", "status", "invalidation_reason"}` at store.py line 64; `test_jsonb_payload_roundtrip` directly asserts `payload ? 'body_md' IS false` |

---

### Code Review Resolution Confirmation

The 02-REVIEW.md BLOCKER (CR-01) fix was confirmed in the actual codebase:

- **CR-01 fix confirmed:** `_INVALIDATE_SQL` at store.py lines 117–125 carries `AND status <> 'invalidated'` (not unconditional), making invalidate() idempotent and reason-clobbering-safe.
- **WR-01 fix confirmed:** `_PAYLOAD_EXCLUDE` at line 64 contains `"body_md"` — body_md is not stored in payload JSONB.
- **WR-02 fix confirmed:** `_PAYLOAD_EXCLUDE` contains `"status"` and `"invalidation_reason"` — neither pollutes the stored payload.
- **WR-03 fix confirmed:** `_SELECT_ACTIVE_SQL` at lines 97–107 orders by `generated_at DESC, card_id DESC` (deterministic tie-break).
- **WR-04 fix confirmed:** `save_card` at line 178 sets `effective_supersedes = supersedes` directly; no dead `getattr` fallback.
- **IN-01 fix confirmed:** `_MAX_SUPERSEDE_DEPTH = 100` named constant at line 55 with rationale comment.
- **WR-05/WR-06/IN-04 deferred:** Intentional — documented in 02-REVIEW.md; WR-06 not treated as a gap per phase context instructions.

---

### Human Verification Required

None. All success criteria are verifiable through static code inspection and test structure analysis.

---

### Gaps Summary

No gaps. All 6 Success Criteria are fully satisfied in the codebase with complete, substantive, wired implementations. The phase delivers:

- A complete Alembic migration (0007) creating the locked `decision_cards` schema with 12 columns, self-ref FKs, body_tsv GENERATED tsvector, and all 4 required indexes.
- A `DecisionCard` ORM class matching the live schema (13 columns including body_tsv).
- A Pydantic v2 `DecisionCard` model with all §3 fields and hard-veto enforcement via field constraints (not validators).
- Four CRUD helpers in `src/cards/store.py` with parameterized SQL only, `_PAYLOAD_EXCLUDE` correctly set, and the CR-01 idempotency guard in place.
- Comprehensive test coverage across schema regression, model round-trip, and CRUD integration suites.

---

_Verified: 2026-05-30T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
