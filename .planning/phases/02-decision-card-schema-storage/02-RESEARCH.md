# Phase 2: Decision Card Schema & Storage - Research

**Researched:** 2026-05-29
**Domain:** Postgres 17 schema design + Pydantic v2 modeling + Alembic hand-written migration (decision_cards canonical storage)
**Confidence:** HIGH (codebase patterns are decisive; the 5 discretion areas all resolve cleanly to "mirror Phase 1")

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Pure JSONB payload** — `decision.stance`, `decision.conviction`, `decision.horizon_days`, `decision.price_ref` are NOT promoted to typed columns. All accessed via `payload->'decision'->>...`. Only `expires_at` is a typed top-level column (matches ROADMAP SC#1). `[CITED: 02-CONTEXT.md §Payload Structure]`
- **JSONB expression indexes (stance/conviction) = OUT.** Phase 2 ships only the SC#2 three indexes. YAGNI; Phase 5 briefing decides JSONB expression indexes after measuring. `[CITED: 02-CONTEXT.md]`
- **Validator scope = ROADMAP SC#5 exactly**: Pydantic rejects only two conditions — `expires_at` missing, OR `assumptions[]` empty. No additional business rules on `invalidation_triggers`/`contradictions`/`key_claims`/`guards_passed`/`numeric_facts` (shape-only via type system). `[CITED: 02-CONTEXT.md §Validator 강제 범위]`
- **numeric_facts digit checksum = Phase 4 responsibility**, NOT Phase 2. Phase 2 Pydantic validates dict shape only. `[CITED: 02-CONTEXT.md]`
- **`body_tsv TSVECTOR` — exactly one fallback search column**, declared `GENERATED ALWAYS AS (to_tsvector(...)) STORED` (DB auto-computes on INSERT/UPDATE; app inserts only `body_md`). Generated column chosen over trigger ("trigger = hidden state, hard to debug"). Satisfies SC#6 "BM25 index" requirement. `[CITED: 02-CONTEXT.md §Body_md fallback]`
- **NO `body_embedding halfvec(1024)` on decision_cards.** Explicitly excluded from Phase 3 `hybrid_search` (narrative tables only). Add via ALTER TABLE in Phase 4+ if ever needed. **NO `pg_trgm` index either** — body_tsv suffices. `[CITED: 02-CONTEXT.md]`
- **Phase 2 = ROADMAP SC#1 columns EXACTLY.** No `report_type`, no `source_reports`, no briefing-specific columns — Phase 5 adds those via its own 3-step ALTER migration. `[CITED: 02-CONTEXT.md §Phase 5 호환성]`
- **`DecisionCard` Pydantic = ticker_card shape only.** Briefing-row Pydantic defined separately in Phase 5 (same table, different schema_version or model class). `[CITED: 02-CONTEXT.md]`
- **Migration number = 0007** (revises 0006). Table name = `decision_cards` (plural snake_case). `status` values = `active`, `superseded`, `invalidated`. `expires_at: datetime` (no default, no Optional). `assumptions: list[str]` min_length=1. CRUD helpers (locked names/signatures): `save_card(card)`, `get_active(corp_code)`, `walk_supersedes(card_id)`, `invalidate(card_id, reason)`. `[CITED: 02-CONTEXT.md §specifics + ROADMAP SC#4]`

### Claude's Discretion (the 5 areas this research resolves)
1. `status` enum representation — Postgres `CREATE TYPE` vs `TEXT + CheckConstraint`
2. Supersession atomicity mechanism (transaction / trigger / deferred constraint)
3. `src/cards/` module structure (single file vs split)
4. CRUD helper return types (Pydantic instance vs tuple vs dict)
5. `schema_version` representation (int vs semver) + translator-stub timing

### Deferred Ideas (OUT OF SCOPE)
- JSONB expression indexes (stance, conviction) — Phase 5 measures first
- `decision_cards.body_embedding halfvec(1024)` — Phase 4+ ALTER if needed
- `schema_version` v1→v2 translator scaffold — built when real v2 schema lands
- CheckConstraint-vs-ENUM ADR standardization — Phase 9 ops hardening
</user_constraints>

<phase_requirements>
## Phase Requirements (ROADMAP SC#1–6 as anchors; no REQUIREMENTS.md IDs for v2.0 yet)

| ID | Description | Research Support |
|----|-------------|------------------|
| SC-1 | Migration creates `decision_cards` with: `card_id PK`, `corp_code FK`, `ticker`, `generated_at`, `as_of`, `payload JSONB`, `body_md TEXT`, `status`(active\|superseded\|invalidated), `supersedes FK`, `superseded_by FK`, `expires_at`, `schema_version` | DDL pattern from 0006 (§Standard Stack, §Code Examples); self-ref FK resolution (§Pitfalls #5) |
| SC-2 | Indexes: `(corp_code, status, generated_at DESC)`, `(supersedes)`, `(expires_at)` | Index DDL mirrors 0006 `op.create_index` w/ `sa.text("... DESC")` (§Code Examples); partial-index discussion (§Discretion area resolved) |
| SC-3 | `DecisionCard` Pydantic round-trips §3 YAML (`key_claims`, `contradictions`, `assumptions`, `invalidation_triggers`, `numeric_facts`, `evidence_weights`, `guards_passed`) | Pydantic v2 nested model + `model_validate`/`model_dump(mode="json")` (§Code Examples, §Pitfalls #4) |
| SC-4 | `src/cards/store.py`: `save_card`, `get_active`, `walk_supersedes`, `invalidate` | Module structure + return-type recommendations (Discretion #3, #4); transaction shape (Discretion #2) |
| SC-5 | Card with no expiry + no assumptions → REJECTED (Pydantic validator, hard veto) | `expires_at: datetime` non-Optional + `Field(min_length=1)` on assumptions (§Code Examples); Veto #2 |
| SC-6 | `body_md` searchable via fallback BM25/tsvector index | `body_tsv` GENERATED column + GIN index; tsearch config resolved to `simple` (§Pitfalls #1 — CRITICAL) |
</phase_requirements>

## Summary

Phase 2 is a **schema + model + CRUD** phase with almost no novel research surface: the dominant
finding is that **every one of the 5 delegated discretion decisions resolves to "do exactly what
Phase 1 migration 0006 / `entity_models.py` already did."** The codebase is internally consistent
and the planner should treat consistency-with-0006 as a hard constraint, not a preference.

Two findings carry real risk and must reach the planner verbatim:

1. **`to_tsvector('korean', ...)` will fail at migration time.** PostgreSQL 17 ships **no** Korean
   text-search configuration, and `scripts/init-extensions.sql` installs only `vector`,
   `vchord_bm25`, `pg_trgm` — no `CREATE TEXT SEARCH CONFIGURATION korean`. The codebase does all
   Korean morphological tokenization in Python (mecab-ko → `INT[]` → VectorChord-BM25
   `bm25vector`), never in Postgres. The only safe built-in config for a GENERATED `body_tsv`
   column is **`simple`** (`to_tsvector('simple', coalesce(body_md, ''))`). This is acceptable
   because SC#6 is an explicit *fallback* search, not the primary retrieval path. `[VERIFIED: scripts/init-extensions.sql + postgresql.org/docs/17/textsearch]`

2. **Phase 1's `body_tsv` is NOT a generated column** — it is a plain nullable `TSVECTOR` left
   NULL (the embedding/tsv pipeline was deferred to Phase 3). So "mirror Phase 1's `body_tsv`
   expression" is impossible — there is no expression to mirror. Phase 2 is the **first** table in
   the project to use a GENERATED tsvector. The planner must author the `to_tsvector('simple', ...)`
   expression fresh (DDL pattern below). `[VERIFIED: src/db/migrations/versions/0006... grep for to_tsvector returned zero matches]`

**Primary recommendation:** Author migration 0007 as a near-clone of 0006's `filings` block —
`TEXT + CheckConstraint` for `status`, single-transaction supersession in `store.py`, a
3-file `src/cards/` module (`models.py` / `store.py` / `validators.py`), `get_active()` returning
the full `DecisionCard` (which already carries `body_md` so payload-only vs both is a serializer
choice, not a re-query), `schema_version: int = 1` with NO translator stub yet, and a
`body_tsv ... GENERATED ALWAYS AS (to_tsvector('simple', coalesce(body_md,''))) STORED` column +
GIN index.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Card persistence (DDL, indexes) | Database / Storage | — | Alembic is sole DDL author (`target_metadata=None`); table lives in Postgres |
| Card validation (expiry, assumptions hard veto) | API / Backend (Pydantic) | — | Veto #2 enforced in Python before INSERT — DB CHECK can't express "assumptions JSON array non-empty" cleanly |
| Supersession atomicity | API / Backend (`store.py` txn) | Database (FK integrity) | Single SQLAlchemy transaction is the correct boundary; FK enforces referential validity |
| Fallback text search | Database / Storage | — | `body_tsv` GENERATED column computed by Postgres; query happens DB-side in Phase 3 MCP |
| Payload-vs-both view selection | API / Backend (Phase 3 MCP) | — | Phase 2 stores both `payload` + `body_md` in one row; view choice is a Phase 3 serialization concern (Veto #13) |

## Standard Stack

### Core
| Library | Version (verified) | Purpose | Why Standard |
|---------|--------------------|---------|--------------|
| SQLAlchemy | 2.0.49 | ORM declarative model (`DecisionCard` table) + Core for CRUD | Already the project ORM; `entity_models.py` is the mirror target `[VERIFIED: uv.lock]` |
| Alembic | 1.18.4 | Hand-written migration 0007 (`target_metadata=None`, no autogenerate) | Sole DDL author per `env.py` line 20 `[VERIFIED: uv.lock + env.py]` |
| Pydantic | 2.13.1 | `DecisionCard` schema + validators (hard veto) | House standard; `portfolio.py`/`frontmatter.py` set the convention `[VERIFIED: uv.lock]` |
| psycopg | 3.3.3 | DB driver (`postgresql+psycopg://`) | Forced in conftest; JSONB adaptation built-in `[VERIFIED: uv.lock + tests/conftest.py:71-74]` |
| testcontainers[postgres] | 4.14.2 | `pg_engine` session fixture (real Postgres 17 + vchord) | Existing `tests/conftest.py:pg_engine` `[VERIFIED: uv.lock]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (Postgres image) `tensorchord/vchord-suite:pg17-latest` | pg17 | DB engine + extensions | testcontainers + docker-compose both use it `[VERIFIED: docker-compose.yml + conftest]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `TEXT + CheckConstraint` for `status` | Postgres `CREATE TYPE ... AS ENUM` | ENUM is harder to evolve (adding a value requires `ALTER TYPE`, and removing is near-impossible); diverges from the project's established `ck_events_*`/`ck_macro_series_source` pattern. **Rejected — see Discretion #1.** |
| `to_tsvector('simple', ...)` | VectorChord-BM25 `bm25vector` (like `chunks`) | bm25vector requires external mecab-ko pre-tokenization → `INT[]` at the app layer; CONTEXT explicitly mandates a *GENERATED* `TSVECTOR` column with no app involvement. bm25vector cannot be a GENERATED column from `body_md` alone. **Rejected — CONTEXT locks GENERATED tsvector.** |
| `to_tsvector('korean', ...)` | — | **Does not exist in PG17. Hard failure at migration time.** See Pitfall #1. |

**Installation:** No new packages. All dependencies already pinned in `pyproject.toml` / `uv.lock`.

## Package Legitimacy Audit

> Not applicable — Phase 2 installs **no new external packages**. Every dependency
> (SQLAlchemy 2.0.49, Alembic 1.18.4, Pydantic 2.13.1, psycopg 3.3.3, testcontainers 4.14.2)
> is already present and pinned in `uv.lock`. No `npm`/`pip`/`cargo install` step exists in this
> phase, so the slopcheck gate has nothing to evaluate. `[VERIFIED: uv.lock + pyproject.toml]`

## Resolved Discretion Areas

### Discretion #1 — `status` enum representation → **TEXT + CheckConstraint**

**RECOMMENDATION:** Use `sa.Text` + a named `CheckConstraint`, exactly like `ck_events_event_type`
and `ck_events_source` in 0006.

```python
sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'active'")),
# ...
sa.CheckConstraint(
    "status IN ('active','superseded','invalidated')",
    name="ck_decision_cards_status",
),
```

**Rationale:** 0006 uses `TEXT + CheckConstraint` for *every* enum-like column
(`ck_events_event_type` 5 values, `ck_events_source`, `ck_macro_series_source`,
`ck_collector_runs_source`) — zero `CREATE TYPE` usage anywhere in the project. Consistency wins;
CONTEXT §Deferred explicitly defers any ENUM-vs-CHECK ADR to Phase 9. `[VERIFIED: 0006 lines 311-321, 266-269, 348-351]`

`server_default='active'` is recommended so `save_card` never has to set status on the insert path
(new cards are always active). Confidence: HIGH.

### Discretion #2 — Supersession atomicity → **single SQLAlchemy transaction**

**RECOMMENDATION:** One `with engine.begin() as conn:` block performing the INSERT of the new card
**and** the UPDATE of the prior row's `superseded_by`. No trigger, no deferred constraint.

```python
def save_card(engine: Engine, card: DecisionCard) -> str:
    payload = card.model_dump(mode="json")          # datetime → ISO strings
    with engine.begin() as conn:                    # mirrors krx/db_writer.py:196
        conn.execute(_INSERT_CARD_SQL, {
            "card_id": card.card_id,
            "corp_code": card.corp_code,
            "ticker": card.ticker,
            "generated_at": card.generated_at,
            "as_of": card.as_of,
            "payload": json.dumps(payload),          # see Pitfall #3
            "body_md": card.body_md,
            "status": "active",
            "supersedes": card.supersedes,
            "superseded_by": None,
            "expires_at": card.expires_at,
            "schema_version": card.schema_version,
        })
        if card.supersedes is not None:
            conn.execute(
                sa.text(
                    "UPDATE decision_cards "
                    "SET status='superseded', superseded_by=:new "
                    "WHERE card_id=:old AND status='active'"
                ),
                {"new": card.card_id, "old": card.supersedes},
            )
    return card.card_id
```

**Rationale:** The project's only write helper (`krx/db_writer.py:196`) uses `with engine.begin()`
for atomic read-then-write; this is the established pattern. A trigger reintroduces exactly the
"hidden state" CONTEXT rejected for `body_tsv`. A deferred constraint solves a different problem
(circular FK at COMMIT) that doesn't arise here because we INSERT the new row first, then UPDATE the
old one — FK order is naturally satisfied. The `AND status='active'` guard makes the UPDATE
idempotent and prevents clobbering an already-invalidated prior card. Confidence: HIGH.

> Order note: INSERT-new-then-UPDATE-old is correct because `superseded_by` on the *old* row points
> at the *new* `card_id`, which must exist first. `supersedes` on the new row points at the old row,
> which already exists. No deferred constraint needed.

### Discretion #3 — `src/cards/` module structure → **3 files: `models.py` + `store.py` + `validators.py`**

**RECOMMENDATION:**
```
src/cards/
├── __init__.py        # re-export DecisionCard, save_card, get_active, walk_supersedes, invalidate
├── models.py          # DecisionCard + nested Pydantic models (KeyClaim, Contradiction, Decision, ...)
├── store.py           # 4 CRUD helpers (SC#4 locked names) — Core SQL, mirrors krx/db_writer.py
└── validators.py      # field_validator helpers IF reused; else fold into models.py
```

Plus the SQLAlchemy ORM table declaration. **Two valid placements** — pick one and state it in the
plan:
- **(A) Add `DecisionCard` ORM class to existing `src/db/entity_models.py`** (alongside Filing,
  News, …). This is what the round-trip test already imports from. **Recommended** — keeps all ORM
  table declarations in one module and lets `test_orm_round_trip` extend trivially.
- (B) New `src/cards/table.py` with its own `Base`. Rejected: would create a second declarative
  `Base`, complicating the round-trip test which asserts `set(Base.metadata.tables) == {...}`.

**Rationale:** `frontmatter.py` and `portfolio.py` show the house style is *Pydantic models grouped
in one module*; `entity_models.py` is the ORM home; `krx/db_writer.py` shows CRUD as a separate
single-purpose module. Splitting `models.py`/`store.py` mirrors that ORM-vs-writer separation. A
single `store.py` would mix three concerns (Pydantic schema, ORM table, CRUD) — heavier to test.
`validators.py` is optional: if the only validators are the two SC#5 rules, fold them into
`models.py` as `@field_validator` methods (like `portfolio.py:_validate_ticker`). Confidence: MEDIUM
(structure is a judgment call; the *consistency anchors* are HIGH).

### Discretion #4 — CRUD helper return types → **return the `DecisionCard` Pydantic instance (body_md included as a field)**

**RECOMMENDATION:** `get_active(corp_code) -> DecisionCard | None`, where `DecisionCard` has a
`body_md: str` field. The full row is read once; payload-only vs both becomes a **serialization
choice downstream**, not a re-query.

```python
class DecisionCard(BaseModel):
    # ... payload fields ...
    body_md: str
    # Phase 3 MCP get_decision_card(view=...) chooses what to serialize:
    #   view="payload"  → card.model_dump(mode="json", exclude={"body_md"})
    #   view="both"     → card.model_dump(mode="json")
```

`walk_supersedes(card_id) -> list[DecisionCard]` (ordered chain). `invalidate(card_id, reason) ->
DecisionCard | None` (returns the updated card; reason stored — see open question OQ-2 on where
`reason` lands).

**Rationale:** Veto #13 ("`get_decision_card` default = payload only") is satisfied by
*not serializing* `body_md` by default, not by *not loading* it. Loading the whole row once and
letting Phase 3 pick the view via `model_dump(exclude=...)` avoids a second query for `view="both"`
and keeps `store.py` ignorant of the MCP view API (clean layering). A `(DecisionCard, body_md)`
tuple is rejected — it splits one logical object, and callers would have to recombine.
Returning a `dict` is rejected — loses the typed contract Veto #7 cares about. Confidence: HIGH
(directly ties to Veto #13 + #7).

### Discretion #5 — `schema_version` → **integer, default 1; NO translator stub in Phase 2**

**RECOMMENDATION:**
- DDL: `sa.Column("schema_version", sa.SmallInteger, nullable=False, server_default=sa.text("1"))`
- Pydantic: `schema_version: int = 1`
- **Do not** scaffold `migrate_v1_to_v2()`.

**Rationale:** redesign §3 YAML shows `schema_version: 1` (a bare integer) and §4 says "bump
`schema_version`; translate on read via `migrate_v{n}_to_v{n+1}()` *if exists*" — the "if exists"
wording plus CONTEXT §Deferred ("translator scaffold built when real v2 lands") means an empty stub
now is speculative (YAGNI / RULES.md Scope Discipline). Integer over semver because the migration is
a discrete on-read translation step, not a dependency-resolution version. `SmallInteger` is
sufficient (versions won't exceed 32k). Confidence: HIGH (explicit in §3 YAML + CONTEXT defer).

## Architecture Patterns

### System Architecture Diagram

```
                 Phase 4 analyze_ticker()            Phase 3 MCP get_decision_card()
                        │ DecisionCard                        │ corp_code, view
                        ▼                                     ▼
        ┌───────────────────────────┐          ┌──────────────────────────────┐
        │  src/cards/store.py        │          │  src/cards/store.py           │
        │  save_card(card)           │          │  get_active(corp_code)        │
        │   1. model_dump(mode=json) │          │   SELECT ... WHERE status=    │
        │   2. validate (Pydantic    │          │     'active' AND              │
        │      already enforced veto)│          │     superseded_by IS NULL     │
        │   3. with engine.begin():  │          │   ORDER BY generated_at DESC  │
        │      INSERT new            │          │   → DecisionCard (body_md incl)│
        │      UPDATE prior.         │          └──────────────┬───────────────┘
        │        superseded_by       │                         │ model_dump(exclude=
        └────────────┬──────────────┘                         │   {"body_md"}) if payload-only
                     │                                         ▼
                     ▼ (single txn)                    [Phase 3 serializes view]
        ┌─────────────────────────────────────────────────────────────┐
        │  Postgres: decision_cards (migration 0007)                   │
        │  ┌─────────────────────────────────────────────────────────┐ │
        │  │ card_id PK | corp_code FK→entities | ticker | generated_at│ │
        │  │ as_of | payload JSONB | body_md TEXT                      │ │
        │  │ body_tsv TSVECTOR GENERATED ALWAYS AS                     │ │
        │  │   (to_tsvector('simple', coalesce(body_md,''))) STORED ◄──┼─┼─ DB auto-computes
        │  │ status TEXT + CHECK | supersedes FK→self | superseded_by  │ │
        │  │   FK→self | expires_at | schema_version SMALLINT          │ │
        │  └─────────────────────────────────────────────────────────┘ │
        │  Indexes: (corp_code,status,generated_at DESC) │ (supersedes) │
        │           │ (expires_at) │ GIN(body_tsv)                      │
        └─────────────────────────────────────────────────────────────┘
                     ▲
                     │ invalidate(card_id, reason): UPDATE status='invalidated'
              Phase 5/9 stale-detection job (expires_at < now())
```

### Recommended Project Structure
```
src/cards/
├── __init__.py        # public surface re-exports
├── models.py          # DecisionCard + Decision/KeyClaim/Contradiction/... nested models
├── store.py           # save_card / get_active / walk_supersedes / invalidate
└── validators.py      # (optional) shared validator helpers

src/db/entity_models.py  # add DecisionCard ORM class (Recommended option A)
src/db/migrations/versions/0007_decision_cards.py  # the migration

tests/cards/
├── conftest.py        # decision_card YAML fixture (from redesign §3)
├── test_models.py     # round-trip + hard-veto rejection (SC#3, SC#5)
└── test_store.py      # save/get_active/walk/invalidate + supersession atomicity (SC#4)
tests/db/test_migration_0007.py  # schema-shape + ORM round-trip (mirror test_migration_0006.py)
```

### Pattern 1: Hand-written Alembic migration mirroring 0006 `filings`
**What:** `create_table` for the typed columns, then `op.execute` raw SQL for the GENERATED tsvector
column (SQLAlchemy `Computed` also works — both shown below), then `create_index`.
**When to use:** Always for this phase. `target_metadata=None`, so no autogenerate.

### Pattern 2: Pydantic v2 hard-veto via non-Optional field + min_length
**What:** `expires_at: datetime` (no `| None`, no default) makes omission a `ValidationError`;
`assumptions: list[str] = Field(min_length=1)` rejects empty lists. No custom validator needed for
SC#5 — the type system enforces it.
**When to use:** SC#5 hard veto. This is *cleaner* than a `@model_validator` and matches CONTEXT's
"leave shape to the type system" directive.

### Anti-Patterns to Avoid
- **`to_tsvector('korean', ...)`** — config doesn't exist; migration fails. Use `'simple'`.
- **Promoting `stance`/`conviction` to typed columns** — Veto'd by CONTEXT (pure JSONB payload).
- **Second declarative `Base` for cards** — breaks `test_orm_round_trip`'s `Base.metadata.tables`
  assertion. Add to the existing `entity_models.Base`.
- **Trigger for supersession** — CONTEXT rejected hidden state; use one transaction.
- **`model_validator` re-checking what the type already enforces** — over-engineering per CONTEXT.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| tsvector population on write | A Python function + UPDATE after INSERT, or a trigger | `GENERATED ALWAYS AS (...) STORED` column | DB computes atomically on every INSERT/UPDATE incl. external SQL; CONTEXT locks this |
| expiry/assumptions enforcement | `if card.expires_at is None: raise` in store.py | Pydantic non-Optional field + `Field(min_length=1)` | Validation belongs at the model boundary; rejects before any DB round-trip (Veto #2) |
| datetime → JSONB serialization | Manual `.isoformat()` walking the dict | `model_dump(mode="json")` | Pydantic emits ISO-8601 for all nested datetimes in one call `[CITED: pydantic serialization docs]` |
| Supersession consistency | Two separate `engine.begin()` calls | One `engine.begin()` block | Atomicity — a crash between two transactions leaves a dangling chain |

**Key insight:** Phase 2 has essentially zero "hard things" left to hand-roll because Phase 1
already solved the migration/ORM/CRUD/test patterns. The work is *transcription with one new wrinkle*
(the GENERATED tsvector column, which is new to this codebase).

## Common Pitfalls

### Pitfall 1: `to_tsvector('korean', ...)` — CRITICAL, will hard-fail the migration
**What goes wrong:** Declaring `body_tsv ... GENERATED ALWAYS AS (to_tsvector('korean', body_md)) STORED`
raises `ERROR: text search configuration "korean" does not exist` at migration time.
**Why it happens:** PostgreSQL 17 ships only Snowball/ISpell configs for European languages plus
`simple`. There is **no** CJK config. `scripts/init-extensions.sql` installs `vector`,
`vchord_bm25`, `pg_trgm` only — no `CREATE TEXT SEARCH CONFIGURATION korean`. The project does
Korean tokenization in Python (mecab-ko), feeding VectorChord-BM25 via pre-tokenized `INT[]`, never
via `to_tsvector`. `[VERIFIED: init-extensions.sql + 0002 chunks bm25_tokens + postgresql.org/docs/17/textsearch]`
**How to avoid:** Use `to_tsvector('simple', coalesce(body_md, ''))`. The `coalesce` guards the
NULL case (a generated expression over a nullable column must be NULL-safe; `body_md` is NOT NULL on
this table but coalesce is defensive and standard). SC#6 is explicitly a *fallback*, so `simple`'s
whitespace/punctuation tokenization (no Korean morphology) is acceptable — primary retrieval is
Phase 3 `hybrid_search` over narrative tables, which decision_cards are excluded from anyway.
**Warning signs:** Migration green on a fresh `simple`-based column; red with "configuration does
not exist" if anyone reaches for `'korean'`.

### Pitfall 2: "Mirror Phase 1's body_tsv expression" — there is no expression to mirror
**What goes wrong:** Planner reads CONTEXT "Phase 1 filings/news 패턴과 일치" and tries to copy a
`to_tsvector(...)` from 0006 — but 0006 declares `body_tsv` as a **plain nullable column left NULL**
(filled by the deferred Phase 3 pipeline), not generated.
**Why it happens:** `grep to_tsvector src/` returns zero matches. Phase 1 never populated body_tsv.
**How to avoid:** Recognize Phase 2 is the *first* GENERATED-tsvector table. "Consistent with Phase
1" means "same column *name* + `TSVECTOR` *type* + GIN-index style", NOT "same expression". Author
the `simple` expression fresh. `[VERIFIED: 0006 lines 90, 150 — body_tsv nullable, no Computed]`

### Pitfall 3: psycopg3 + JSONB — pass a Python dict, or `json.dumps`, but be consistent
**What goes wrong:** Binding a Pydantic model directly, or a dict-with-datetime, to a JSONB param
can raise adaptation errors or store datetimes as Postgres timestamps inside JSON unexpectedly.
**Why it happens:** psycopg3 adapts `dict` → JSONB automatically, but datetime values inside a dict
are not JSON-native. `model_dump(mode="json")` converts datetimes to ISO strings first.
**How to avoid:** `payload = card.model_dump(mode="json")` then bind that dict to the JSONB column.
With psycopg3 you can bind the dict directly (auto-adapted) or wrap with `json.dumps`. Recommend
`model_dump(mode="json")` → bind dict; confirm in `test_store.py` that `payload->'decision'->>'stance'`
returns the expected string. `[CITED: pydantic serialization docs — mode="json" emits ISO-8601]`

### Pitfall 4: Pydantic round-trip equivalence — datetime tz + numeric types
**What goes wrong:** `model_validate(yaml_dict)` → `model_dump()` may not equal the original YAML
because (a) `mode="python"` keeps `datetime` objects while YAML had strings, (b) the §3 YAML uses
`+09:00` offsets that must survive, (c) large ints (`market_cap_krw: 425000000000000`) must stay int
not float.
**Why it happens:** YAML loads `425000000000000` as int (good) but `pe_ttm: 17.2` as float; tz-aware
datetimes need `datetime` fields (Pydantic coerces ISO-8601 incl. offset). SC#3 says "round-trip" —
clarify it means semantic equivalence, typically `DecisionCard.model_validate(d).model_dump(mode="json")`
compared against `DecisionCard.model_validate(d).model_dump(mode="json")` after a serialize→reparse
cycle, OR field-by-field equality after coercion — not byte-identical YAML.
**How to avoid:** Test as: `card = DecisionCard.model_validate(yaml_loaded)`; assert
`DecisionCard.model_validate(card.model_dump(mode="json")) == card`. Use `mode="json"` so datetimes
become comparable ISO strings on the wire and reparse to the same aware datetime. Keep `numeric_facts`
as a permissive `dict[str, float | int]` or typed sub-model — §3 mixes int and float values.
**Warning signs:** Equality fails on `pe_ttm` (float repr) or on naive-vs-aware datetime.

### Pitfall 5: Self-referential FKs (`supersedes`, `superseded_by`)
**What goes wrong:** Two FKs from `decision_cards` back to `decision_cards.card_id` in one
`create_table`.
**Why it happens:** Fear of "table doesn't exist yet" during creation.
**How to avoid:** Single-column self-ref FKs declared inline in `create_table` work fine — Postgres
creates the table then the FK in the same DDL; no `use_alter` needed (that's only for *circular FKs
between two tables* or composite-PK self-refs, per the Alembic issue #1215 which is a different,
composite case). Declare both as `sa.ForeignKey("decision_cards.card_id", ondelete="SET NULL")`.
`ondelete="SET NULL"` mirrors how 0006 handles soft references (e.g. `events.filing_rcept_no`).
`[VERIFIED: github.com/sqlalchemy/alembic#1215 — error is composite-PK-specific; single-col self-ref is fine]`
**Warning signs:** `DuplicateColumnError` only appears with composite-PK self-refs — not our case.

### Pitfall 6: GIN index on a GENERATED tsvector column
**What goes wrong:** Forgetting `postgresql_using="gin"`, or trying to GIN-index before the column
exists (if column added via `op.execute` after `create_table`).
**How to avoid:** Either declare `body_tsv` with SQLAlchemy `Computed(..., persisted=True)` inside
`create_table` (so the column exists when `create_index` runs), OR add it via `op.execute("ALTER
TABLE decision_cards ADD COLUMN body_tsv tsvector GENERATED ALWAYS AS (...) STORED")` *before* the
`op.create_index(..., postgresql_using="gin")` call. Index: `op.create_index("ix_decision_cards_body_tsv",
"decision_cards", ["body_tsv"], postgresql_using="gin")`.

## Code Examples

### DDL — migration 0007 core table (mirrors 0006 `filings`)
```python
# Source: pattern from src/db/migrations/versions/0006_phase01_domain_tables.py
revision = "0007"
down_revision = "0006"

def upgrade() -> None:
    op.create_table(
        "decision_cards",
        sa.Column("card_id", sa.Text, primary_key=True),
        sa.Column(
            "corp_code",
            sa.CHAR(8),
            sa.ForeignKey("entities.corp_code", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ticker", sa.CHAR(6), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("body_md", sa.Text, nullable=False),
        # body_tsv added below — GENERATED column. Two valid ways:
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'active'")),
        sa.Column(
            "supersedes",
            sa.Text,
            sa.ForeignKey("decision_cards.card_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "superseded_by",
            sa.Text,
            sa.ForeignKey("decision_cards.card_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.SmallInteger, nullable=False, server_default=sa.text("1")),
        sa.CheckConstraint(
            "status IN ('active','superseded','invalidated')",
            name="ck_decision_cards_status",
        ),
    )
    # GENERATED tsvector — 'simple' config (NO 'korean' config exists; Pitfall #1)
    op.execute(
        "ALTER TABLE decision_cards ADD COLUMN body_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(body_md, ''))) STORED"
    )
    # SC#2 mandatory indexes
    op.create_index(
        "ix_decision_cards_corp_status_gen",
        "decision_cards",
        ["corp_code", "status", sa.text("generated_at DESC")],
    )
    op.create_index("ix_decision_cards_supersedes", "decision_cards", ["supersedes"])
    op.create_index("ix_decision_cards_expires", "decision_cards", ["expires_at"])
    # SC#6 fallback search index
    op.create_index(
        "ix_decision_cards_body_tsv",
        "decision_cards",
        ["body_tsv"],
        postgresql_using="gin",
    )

def downgrade() -> None:
    op.drop_index("ix_decision_cards_body_tsv", table_name="decision_cards")
    op.drop_index("ix_decision_cards_expires", table_name="decision_cards")
    op.drop_index("ix_decision_cards_supersedes", table_name="decision_cards")
    op.drop_index("ix_decision_cards_corp_status_gen", table_name="decision_cards")
    op.drop_table("decision_cards")
```

> **Optional partial index** for `(corp_code, status, generated_at DESC)`: a `postgresql_where=
> sa.text("status='active'")` partial index makes "latest active by ticker" faster and smaller.
> CONTEXT mandates only the 3 plain indexes (YAGNI), so the planner MAY make it partial but is not
> required to. If chosen, the test must assert the WHERE clause (like `test_filings_table_shape`
> does for `ix_filings_event_type`).

### Alternative — `Computed` inside `create_table` (also valid)
```python
# Source: docs.sqlalchemy.org/en/20/core/defaults.html (Computed)
sa.Column(
    "body_tsv",
    postgresql.TSVECTOR,
    sa.Computed("to_tsvector('simple', coalesce(body_md, ''))", persisted=True),
),
# persisted=True → GENERATED ALWAYS AS (...) STORED
```
Either form is acceptable; `op.execute` matches 0006's raw-SQL-for-special-columns habit (halfvec),
`Computed` is more declarative and lets the GIN index be created in the same `create_table` flow.

### Pydantic — DecisionCard with hard-veto fields (SC#3, SC#5)
```python
# Source: house convention from src/shared/portfolio.py + frontmatter.py
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stance: Literal["BUY", "ADD", "HOLD", "TRIM", "SELL", "AVOID"]
    conviction: float = Field(ge=0, le=1)
    horizon_days: int = Field(gt=0)
    price_ref: float | None = None
    invalidation_triggers: list[str] = Field(default_factory=list)

class KeyClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str
    evidence_refs: list[str] = Field(default_factory=list)
    weight: Literal["HIGH", "MEDIUM", "LOW", "CONTEXT"]
    confidence: float = Field(ge=0, le=1)

class Contradiction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bull: str
    bear_evidence: str
    bear_claim: str
    resolution: str

class DecisionCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card_id: str
    corp_code: str = Field(pattern=r"^[0-9]{8}$")
    ticker: str = Field(pattern=r"^[0-9]{6}$")
    generated_at: datetime
    as_of: datetime
    schema_version: int = 1
    decision: Decision
    key_claims: list[KeyClaim] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)   # Veto #3: 1st-class
    assumptions: list[str] = Field(min_length=1)                        # SC#5 HARD VETO
    numeric_facts: dict[str, float | int] = Field(default_factory=dict)  # shape-only; Phase 4 checksums
    evidence_weights: dict[str, str] = Field(default_factory=dict)
    guards_passed: list[str] = Field(default_factory=list)
    expires_at: datetime                                                # SC#5 HARD VETO: no default, no Optional
    body_md: str
```
The two SC#5 conditions are enforced purely by field declarations: `expires_at: datetime` (omission
→ ValidationError) and `assumptions: list[str] = Field(min_length=1)` (empty → ValidationError). No
custom `@model_validator` required, matching CONTEXT's "leave shape to the type system."

### Round-trip test (SC#3)
```python
# tests/cards/test_models.py
def test_round_trip(decision_card_yaml: dict) -> None:
    card = DecisionCard.model_validate(decision_card_yaml)
    reparsed = DecisionCard.model_validate(card.model_dump(mode="json"))
    assert reparsed == card

def test_missing_expiry_rejected(decision_card_yaml: dict) -> None:
    bad = {**decision_card_yaml}; bad.pop("expires_at")
    with pytest.raises(ValidationError):
        DecisionCard.model_validate(bad)

def test_empty_assumptions_rejected(decision_card_yaml: dict) -> None:
    bad = {**decision_card_yaml, "assumptions": []}
    with pytest.raises(ValidationError):
        DecisionCard.model_validate(bad)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Trigger-maintained tsvector | `GENERATED ALWAYS AS ... STORED` generated column | PG12+ | No trigger; DB maintains it; CONTEXT mandates it |
| Pydantic v1 `.dict()`/validators | v2 `model_dump(mode="json")` + `field_validator` classmethods | Pydantic 2.x | House code already on v2 (portfolio.py) |
| `CREATE TYPE ... AS ENUM` | `TEXT + CheckConstraint` (project choice) | — | Evolvability; project-wide consistency (0006) |

**Deprecated/outdated:** none relevant — all libs are current pins.

## Runtime State Inventory

> Greenfield table creation, not a rename/refactor. **Section included for completeness; nothing to
> migrate** because `decision_cards` does not yet exist.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — `src/cards` and `tests/cards` do not exist; `decision_cards` table is new in 0007 | None (verified: `ls src/cards` → not found; grep for decision_cards in migrations → only the §3 sketch in redesign doc) |
| Live service config | None | None |
| OS-registered state | None | None |
| Secrets/env vars | None new (uses existing `DATABASE_URL`) | None |
| Build artifacts | None | None |

**Nothing found in any category** — verified `src/cards/` and `tests/cards/` are absent and no
prior decision_cards DDL exists outside the redesign §3 sketch.

## Validation Architecture

> `workflow.nyquist_validation` not found disabled in config — section included. The project has a
> mature testcontainers-based DB test harness this phase plugs directly into.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + testcontainers[postgres] 4.14.2 (real Postgres 17 + vchord) |
| Config file | `pyproject.toml` (markers `slow`/`e2e`); session fixture `pg_engine` in `tests/conftest.py` |
| Quick run command | `uv run pytest tests/cards -x -q` |
| Full suite command | `uv run pytest -m "not slow and not e2e"` |

### Phase Requirements → Test Map
| Req | Behavior | Test Type | Automated Command | File Exists? |
|-----|----------|-----------|-------------------|-------------|
| SC-1 | Table has all 12 locked columns + PK/FK | schema | `uv run pytest tests/db/test_migration_0007.py::test_decision_cards_shape -x` | ❌ Wave 0 |
| SC-2 | 3 mandatory indexes present (names + DESC ordering) | schema | `... ::test_decision_cards_indexes -x` | ❌ Wave 0 |
| SC-3 | §3 YAML round-trips via DecisionCard | unit | `uv run pytest tests/cards/test_models.py::test_round_trip -x` | ❌ Wave 0 |
| SC-4 | save/get_active/walk_supersedes/invalidate work; supersession atomic | integration (DB) | `uv run pytest tests/cards/test_store.py -x` | ❌ Wave 0 |
| SC-5 | missing expiry OR empty assumptions → ValidationError | unit | `... test_models.py::test_missing_expiry_rejected -x` | ❌ Wave 0 |
| SC-6 | body_tsv GENERATED + GIN index exists; `simple` config; query returns rows | schema+integration | `... test_migration_0007.py::test_body_tsv_generated -x` | ❌ Wave 0 |
| (drift) | ORM ↔ DB column-set parity for DecisionCard | schema | `... test_migration_0007.py::test_orm_round_trip -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/cards tests/db/test_migration_0007.py -x -q`
- **Per wave merge:** `uv run pytest -m "not slow and not e2e"`
- **Phase gate:** full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/cards/conftest.py` — `decision_card_yaml` fixture transcribed verbatim from
      redesign §3 (card_005930_2026-05-28). This IS the SC#3 round-trip oracle.
- [ ] `tests/cards/test_models.py` — round-trip + 2 hard-veto rejection tests (SC#3, SC#5)
- [ ] `tests/cards/test_store.py` — CRUD + supersession atomicity (uses `seeded_engine` fixture
      which pre-inserts 삼성전자/005930/00126380 so the corp_code FK is satisfiable)
- [ ] `tests/db/test_migration_0007.py` — schema-shape + index + body_tsv + ORM round-trip
      (clone `tests/db/test_migration_0006.py` structure exactly)
- [ ] Add `decision_cards` to `_LIVE_TABLES` in `tests/conftest.py` (TRUNCATE hygiene) — must come
      BEFORE `entities` and BEFORE itself-FK-wise; since it self-refs, place it among body-bearing
      tables, before `entities`. `CASCADE` handles the self-ref.

## Security Domain

> `security_enforcement` not disabled in config — section included. Phase 2 is storage-only; most
> categories N/A. Veto #7 (no `run_sql`) is the live concern.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | DB access via `DATABASE_URL`; no user auth in this phase |
| V3 Session Management | no | — |
| V4 Access Control | no | single-user system |
| V5 Input Validation | yes | Pydantic `DecisionCard` validates all card input before INSERT; `extra="forbid"` rejects unknown keys |
| V6 Cryptography | no | no secrets handled in card storage |

### Known Threat Patterns for Postgres + SQLAlchemy
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via card_id / corp_code | Tampering | All `store.py` SQL uses SQLAlchemy bind params (mirror `krx/db_writer.py`); NEVER f-string interpolate (RULES.md Safety) |
| Arbitrary SQL escape hatch | Elevation | Veto #7: `store.py` exposes only typed helpers — no generic query function. Phase 3 CI guard checks for `run_sql` |
| JSONB injection / malformed payload | Tampering | psycopg3 parameterized JSONB binding; Pydantic shape-validates payload before it reaches DB |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `simple` tsvector config is acceptable for the SC#6 *fallback* search (no Korean morphology) | Pitfall #1, Stack | LOW — SC#6 says "fallback"; primary retrieval is Phase 3 hybrid_search which excludes decision_cards. If morphological search is later needed, the codebase's mecab-ko→bm25vector path is the upgrade (ALTER in a later phase) |
| A2 | `numeric_facts` should be typed `dict[str, float \| int]` (not a fixed sub-model) | Pydantic example | LOW — §3 YAML shows arbitrary keys (market_cap_krw, pe_ttm, foreign_ownership_pct); a permissive dict matches "shape-only" CONTEXT directive. Phase 4 does the verbatim checksum |
| A3 | Adding `DecisionCard` ORM to existing `entity_models.Base` (option A) is preferred over a new Base | Discretion #3 | LOW — keeps `test_orm_round_trip` single-Base; if planner prefers isolation, option B works but must update the round-trip assertion |
| A4 | `card_id` is `TEXT` PK (not UUID) — §3 YAML uses human-readable `card_005930_2026-05-28` | DDL | LOW — redesign §3 + §4 ("card_id immutable") show string IDs; matches filings' TEXT PK habit |
| A5 | `invalidate(card_id, reason)` stores `reason` — but WHERE is undecided (payload key vs new column). CONTEXT locks columns to SC#1 exactly (no `invalidation_reason` column) | OQ-2 | MEDIUM — see Open Questions; planner must decide |

## Open Questions (RESOLVED)

> All three resolved during Phase 2 planning + post-plan-check. Inline RESOLVED markers below.

1. **Where does `invalidate(card_id, reason)` write `reason`?** — RESOLVED: into `payload` JSONB via
   `jsonb_set(payload, '{invalidation_reason}', to_jsonb(:reason))` (SC#1 column set untouched).
   Post-plan-check addendum: `invalidation_reason: str | None = None` is ALSO declared as an optional
   field on `DecisionCard`, so the payload round-trips cleanly under `extra="forbid"` (redesign §4 lists
   `invalidation_reason` as a frontmatter field). See Plans 02-02 / 02-03.
   - What we know: SC#1 column list is locked and does NOT include `invalidation_reason`. redesign
     §4 mentions `invalidation_reason: event_id` as a *frontmatter* (payload) field, not a column.
   - What's unclear: store `reason` inside `payload` JSONB (e.g. `payload->>'invalidation_reason'`)
     vs adding a column (would violate "SC#1 columns exactly").
   - Recommendation: **write `reason` into `payload` JSONB** (`UPDATE ... SET status='invalidated',
     payload = jsonb_set(payload, '{invalidation_reason}', to_jsonb(:reason))`). Keeps the locked
     column set intact and matches §4's frontmatter framing. Planner should confirm.

2. **`generated_at` / `as_of` server_default?** — RESOLVED: NO `server_default` (data-meaningful, set by card author / Phase 4). See Plan 02-01.
   - What we know: §3 shows both as explicit values set by the analysis runner (Phase 4).
   - Recommendation: NO `server_default` — these are *data-meaningful* timestamps the card author
     sets (unlike `fetched_at` which is a write-time marker). `expires_at` likewise no default
     (SC#5). Pydantic supplies them; store.py binds them. (Contrast: 0006 uses `server_default=now()`
     only for `fetched_at`/`*_seen_at` bookkeeping columns.)

3. **Round-trip equality semantics for SC#3** — RESOLVED (semantic equality; see Plan 02-02): confirm "round-trip" means
   `model_validate(dump(card)) == card` (semantic), not byte-identical YAML (Pitfall #4). The plan's
   test should encode the chosen semantics explicitly.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Postgres 17 + vchord image | migration + DB tests | ✓ (testcontainers pulls it) | `tensorchord/vchord-suite:pg17-latest` | — |
| Docker | testcontainers | ✓ assumed (Phase 1 tests ran) | — | — |
| `simple` tsearch config | body_tsv GENERATED column | ✓ (PG built-in) | PG17 | — |
| `korean` tsearch config | (NOT used) | ✗ | — | `simple` (the recommended choice) |
| pgvector/vchord_bm25 | (NOT used by this phase) | ✓ | — | n/a — decision_cards has no embedding/bm25vector |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** `korean` tsearch config absent → use `simple` (already the
recommendation, not a degradation since SC#6 is fallback-only).

## Sources

### Primary (HIGH confidence)
- Codebase: `src/db/migrations/versions/0006_phase01_domain_tables.py` — table/index/CheckConstraint/halfvec patterns to mirror
- Codebase: `src/db/entity_models.py` — ORM declarative + `_HalfVec`; `Base` to extend
- Codebase: `src/db/migrations/versions/0002_phase03_chunking_columns.py` — VectorChord-BM25 `bm25vector` + mecab-ko `INT[]` evidence (why NOT to use bm25vector for body_tsv)
- Codebase: `scripts/init-extensions.sql` — proves no `korean` tsearch config installed
- Codebase: `src/collectors/krx/db_writer.py` — `with engine.begin()` atomic write pattern + bind-param SQL
- Codebase: `tests/db/test_migration_0006.py` + `tests/conftest.py` + `tests/db/conftest.py` — test harness, `pg_engine`/`pg_clean`/`seeded_engine` fixtures, `_LIVE_TABLES`
- Codebase: `src/shared/portfolio.py`, `src/shared/frontmatter.py` — house Pydantic v2 conventions (`ConfigDict(extra="forbid")`, `field_validator`, ISO coercion)
- `.planning/research/redesign-2026-05.md` §3 (decision_card YAML), §4 (frontmatter+body single row, supersession chain, schema_version translate-on-read)
- `uv.lock` — verified versions: SQLAlchemy 2.0.49, Alembic 1.18.4, Pydantic 2.13.1, psycopg 3.3.3, testcontainers 4.14.2
- [docs.sqlalchemy.org/en/20/core/defaults.html](https://docs.sqlalchemy.org/en/20/core/defaults.html) — `Computed(sqltext, persisted=True)` → `GENERATED ALWAYS AS ... STORED`
- [postgresql.org/docs/17/textsearch.html](https://www.postgresql.org/docs/17/textsearch.html) — default config `simple`; no CJK/Korean built-in config

### Secondary (MEDIUM confidence)
- [pydantic.dev serialization docs](https://docs.pydantic.dev/latest/concepts/serialization/) — `model_dump(mode="json")` emits ISO-8601 datetimes; `round_trip` param
- [github.com/sqlalchemy/alembic#1215](https://github.com/sqlalchemy/alembic/issues/1215) — self-ref FK DuplicateColumnError is *composite-PK specific*; single-column self-ref is unaffected

### Tertiary (LOW confidence)
- (none — no unverified-single-source claims)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified in uv.lock; no new packages
- Architecture / discretion resolutions: HIGH — each maps directly to an existing 0006/entity_models/db_writer pattern; only #3 module split is a MEDIUM judgment call
- Pitfalls: HIGH for #1 (verified config absence + extension SQL), #2 (grep proof), #5 (issue scoping); MEDIUM for #4 (round-trip semantics depend on test author's intent)
- tsearch config: HIGH that `korean` is unavailable; A1 (acceptability of `simple` as fallback) is the one judgment to confirm with the user/planner

**Research date:** 2026-05-29
**Valid until:** 2026-06-28 (stable — all pins current; codebase patterns are the primary source and won't drift)
