---
phase: 08-vault-dashboards-research-memo-templates
plan: 01
subsystem: vault-templates-frontmatter-schema
tags: [phase-8, frontmatter, pydantic, alembic, templates, ingest-parser]
requires: [src/shared/frontmatter.py:NoteFrontmatter, src/db/migrations/versions/0004]
provides:
  - src/shared/frontmatter.py:ThesisFrontmatter
  - src/shared/frontmatter.py:NOTE_MODEL_BY_TYPE
  - src/ingest/parsers/note.py:parse_note
  - templates/notes/thesis.md
  - templates/notes/journal.md
  - documents.note_type (DB column + index)
affects: [src/shared/frontmatter.py, templates/portfolio.md → templates/notes/portfolio.md]
tech_added: []
tech_patterns:
  - "Pydantic subclass for type-extension (ThesisFrontmatter ← NoteFrontmatter)"
  - "Dispatch table by frontmatter['type'] (NOTE_MODEL_BY_TYPE)"
  - "Fail-soft validation: ValidationError → review_flag, body still indexed (D-15)"
  - "Alembic backfill UPDATE scoped by source column (idempotent)"
key_files_created:
  - src/shared/frontmatter.py (extended — see decisions)
  - src/ingest/parsers/note.py
  - src/db/migrations/versions/0005_phase08_note_type.py
  - templates/notes/thesis.md
  - templates/notes/journal.md
  - tests/shared/test_thesis_frontmatter.py
  - tests/ingest/parsers/__init__.py
  - tests/ingest/parsers/test_note.py
  - tests/templates/__init__.py
  - tests/templates/test_templates_parse.py
  - tests/db/test_migration_0005.py
key_files_modified:
  - src/shared/frontmatter.py (NoteFrontmatter extra='forbid' → 'allow' per D-15)
  - tests/shared/test_note_frontmatter.py (replaced extra-forbid test with extra-allow + journal test)
key_files_renamed:
  - templates/portfolio.md → templates/notes/portfolio.md (git mv, history preserved)
decisions:
  - "NoteFrontmatter relaxed to extra='allow' — D-15 says 'review_flags on validation failure', so user free-form keys (mood, weather) must NOT crash ingest. Schema violations on KNOWN fields still raise ValidationError, caught by parse_note and recorded as review_flag."
  - "documents.note_type Text nullable column over JSONB frontmatter zone — indexable, simpler search filter, no JSONB probe overhead."
  - "Migration 0005 backfill scoped to source='private_note' rows — non-private docs stay NULL (no semantics for them)."
  - "ParsedNote dataclass over Pydantic model for parser output — pure-data carrier, no validation overhead, ingest worker owns persistence."
metrics:
  duration: "≈12 min"
  tasks: 3
  tests_added: 16  # 4 thesis + 2 note_frontmatter (delta) + 4 parse_note + 4 templates + 2 migration
  tests_pass: "39/39 (Phase 8 + add_note regression suite)"
  files_created: 11
  files_modified: 2
  files_renamed: 1
  completed: 2026-05-06
---

# Phase 08 Plan 01: Vault Templates + Frontmatter Schema + Note Parser Summary

JWT-style schema landing for Phase 8 — `ThesisFrontmatter` Pydantic subclass with `kill_criteria`/`conviction`/`target_price` extension fields, dispatch table for `notes/private/**/*.md` parser, 3 user-facing markdown templates, and Alembic 0005 adding `documents.note_type` column for memo-aware search filters.

## Outcome

Plans 08-02 (hub_builder) / 08-03 (dashboards) / 08-04 (E2E) can now consume:
- `parse_note(path) → ParsedNote` with type-dispatched Pydantic validation
- `documents.note_type` column for filterable memo queries
- 3 templates committed (thesis/journal/portfolio) ready for `add_note` LLM authoring or manual copy

NOTE-01, NOTE-02, NOTE-03 requirements satisfied.

## ThesisFrontmatter Added Fields

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `type` | `Literal["thesis"]` | `"thesis"` | Discriminator (overrides parent NoteFrontmatter Literal union) |
| `kill_criteria` | `list[str]` | `[]` | Trigger conditions that retire the thesis |
| `conviction` | `Literal["low", "medium", "high"]` | `"medium"` | User confidence |
| `target_price` | `int \| None` | `None` | Target price in KRW (nullable) |

Inherits from `NoteFrontmatter`: `tickers`, `tags`, `created`, `updated`, `author`, `conviction_score`. Inherits `extra="allow"` policy.

## Dispatch Table (`NOTE_MODEL_BY_TYPE`)

| frontmatter `type` value | Pydantic class | Notes |
|--------------------------|----------------|-------|
| `"thesis"` | `ThesisFrontmatter` | Phase 8 D-13 extension fields |
| `"journal"` | `NoteFrontmatter` | D-13 common fields only |
| `"conviction"` | `NoteFrontmatter` | Reuses existing `conviction_score` field |
| `"note"` | `NoteFrontmatter` | Generic memo fallback |
| (unknown / missing) | `NoteFrontmatter` | `parse_note` defaults `note_type="note"` and validates against base model; ValidationError → review_flag, no exception |

## Migration Revision Chain

`0001_phase02_initial_schema → 0002_phase03_chunking_columns → 0003_relax_edges_check_for_phase6 → 0004_phase07_edge_check → 0005_phase08_note_type`

Live DB at `0005 (head)` after `uv run alembic upgrade head`. Downgrade-upgrade round-trip verified clean.

## Pitfall 4 Resolution: extra="forbid" → extra="allow"

**Problem (Phase 8 RESEARCH §Pitfall 4):** `NoteFrontmatter` Phase 6 D-11 introduced `extra="forbid"`. D-15 says ingest must tolerate user free-form keys and only record schema violations as `review_flags` (continue body indexing). Strict `forbid` would crash ingest on any unexpected field.

**Decision (per Plan Step 1 decision tree):** Verified add_note callers (`src/stock_mcp/tools/notes.py:174`, all add_note tests) pass only known keys. Safe to relax to `extra="allow"`. Trade-off: Phase 6 test `test_extra_field_forbidden` was inverted to `test_unknown_field_does_not_crash_parse`.

**Why this is correct:** The validation contract for unknown fields was always meant to be "tolerant" per D-15 — the original `forbid` was an over-tightening. Known-field violations (e.g., `conviction: "extreme"`) still raise via Literal/range constraints, and `parse_note` catches those and records `note_schema_violation`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 4 deferred → resolved as Rule 2 (correctness)] entity.py update skipped — no ORM model exists**
- **Found during:** Task 3 read_first
- **Plan said:** "src/db/entity.py 의 Document ORM/dataclass에 `note_type: str | None = None` 필드 추가"
- **Reality:** `src/db/entity.py` is a query helper (`resolve_entity` function with `Entity` dataclass for entity_aliases), not a documents-table ORM. There is no Document ORM/dataclass to update. Phase 2 STATE confirms `Alembic target_metadata=None — hand-written migrations only` — there is no SQLAlchemy ORM layer for `documents`.
- **Action:** Skipped that step. Migration + DB column suffice. Search/filter callers will use raw SQL via existing engine session pattern.
- **Impact:** Zero — there's nothing to update. Future code wanting typed access can add an ad-hoc dataclass alongside the query.

### Other Deviations

None. Plan executed as written for Task 1 (with the documented Pitfall 4 resolution) and Task 2 (atomic `git mv` + 2 new templates). Task 3's entity.py step was a phantom requirement — see deviation 1.

## Authentication Gates

None encountered.

## Verification Evidence

```
$ uv run pytest tests/shared/test_thesis_frontmatter.py \
                tests/shared/test_note_frontmatter.py \
                tests/ingest/parsers/test_note.py \
                tests/templates/test_templates_parse.py \
                tests/db/test_migration_0005.py \
                tests/stock_mcp/test_add_note_paths.py \
                tests/stock_mcp/test_add_note_append.py \
                tests/stock_mcp/test_add_note_frontmatter.py
==================== 39 passed, 1 warning in 33.10s ====================
```

```
$ uv run alembic current
0005 (head)
```

CI guard COLL-07: no `anthropic`/`openai` imports in `src/ingest/parsers/note.py` or `src/shared/frontmatter.py` (grep exit=1 = no match).

## Self-Check: PASSED

**Files:**
- FOUND: src/shared/frontmatter.py (modified — ThesisFrontmatter + NOTE_MODEL_BY_TYPE)
- FOUND: src/ingest/parsers/note.py
- FOUND: src/db/migrations/versions/0005_phase08_note_type.py
- FOUND: templates/notes/thesis.md
- FOUND: templates/notes/journal.md
- FOUND: templates/notes/portfolio.md (renamed from templates/portfolio.md)
- FOUND: tests/shared/test_thesis_frontmatter.py
- FOUND: tests/ingest/parsers/__init__.py
- FOUND: tests/ingest/parsers/test_note.py
- FOUND: tests/templates/__init__.py
- FOUND: tests/templates/test_templates_parse.py
- FOUND: tests/db/test_migration_0005.py

**Commits:**
- FOUND: 6b841ee (Task 1: ThesisFrontmatter + parse_note)
- FOUND: f5aac71 (Task 2: templates + git mv)
- FOUND: 4c31b01 (Task 3: Alembic 0005)

**Live state:**
- alembic current = `0005 (head)` ✓
- 39/39 tests passing ✓
- No add_note regressions ✓
