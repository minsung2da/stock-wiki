# Phase 2: Decision Card Schema & Storage - Pattern Map

**Mapped:** 2026-05-29
**Files analyzed:** 12 (10 new, 2 modified)
**Analogs found:** 12 / 12 (all have a direct in-repo analog)

> Note on paths: the source tree lives at the main worktree
> `C:\Users\minsu\workspace\stock\src` / `…\tests`. The current GSD worktree CWD
> (`…\.claude\worktrees\exciting-mendeleev-476256`) has no `src/`. All line
> references below are against the main-tree files (the ones the planner edits).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/db/migrations/versions/0007_decision_cards.py` | migration | CRUD (DDL) | `src/db/migrations/versions/0006_phase01_domain_tables.py` (`filings` block) | exact |
| `src/cards/models.py` | model (Pydantic) | transform/validate | `src/shared/portfolio.py` + `src/shared/frontmatter.py` | role-match (exact convention) |
| `src/cards/store.py` | service (CRUD) | CRUD / request-response | `src/collectors/krx/db_writer.py` | role-match (atomic-write exact) |
| `src/cards/validators.py` (only if split) | utility | validate | `src/shared/portfolio.py::_validate_ticker` | role-match |
| `src/cards/__init__.py` | config (barrel) | — | `src/db/entity_models.py::__all__` | role-match |
| `src/db/entity_models.py` (MODIFY) | model (ORM) | CRUD | existing `Filing` class in same file | exact (in-file sibling) |
| `tests/cards/conftest.py` | test (fixtures) | — | `tests/db/conftest.py::seeded_engine` + `tests/conftest.py::SAMPLE_YAML` | exact |
| `tests/cards/test_models.py` | test (unit) | transform | RESEARCH §Code Examples round-trip block + `portfolio.py` validators | role-match |
| `tests/cards/test_store.py` | test (integration DB) | CRUD | `tests/db/conftest.py::seeded_engine` consumer pattern | role-match |
| `tests/db/test_migration_0007.py` | test (schema) | CRUD | `tests/db/test_migration_0006.py` (whole file) | exact |
| `tests/conftest.py` (MODIFY) | test (fixtures) | — | existing `_LIVE_TABLES` tuple in same file | exact (in-file edit) |

**Verified facts (read-only checks performed):**
- `src/cards/` and `tests/cards/` do **not** exist → all `src/cards/*` and `tests/cards/*` are NEW. `[VERIFIED: ls]`
- Migration versions present: `0001..0006`. `0007` is the next free number; `down_revision = "0006"`. `[VERIFIED: ls versions/]`
- `grep to_tsvector src/` → **zero matches**. Phase 2 is the FIRST GENERATED tsvector in the repo; there is no expression to copy (RESEARCH Pitfall #2 confirmed). `[VERIFIED: Grep]`
- `scripts/init-extensions.sql` has **no** `korean` / `CREATE TEXT SEARCH CONFIGURATION` → must use `'simple'` (RESEARCH Pitfall #1 confirmed). `[VERIFIED: grep]`

---

## Pattern Assignments

### `src/db/migrations/versions/0007_decision_cards.py` (migration, DDL)

**Analog:** `src/db/migrations/versions/0006_phase01_domain_tables.py` — the `filings` block is the closest shape (narrative `body_md TEXT` + `body_tsv` + corp_code FK to entities).

**Revision header** (mirror 0006:45-55):
```python
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None
```

**`create_table` + corp_code FK pattern** (mirror 0006:73-89 `filings`):
```python
op.create_table(
    "filings",
    sa.Column("rcept_no", sa.CHAR(14), primary_key=True),
    sa.Column(
        "corp_code",
        sa.CHAR(8),
        sa.ForeignKey("entities.corp_code", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("ticker", sa.CHAR(6), nullable=True),
    sa.Column("filed_at", sa.DateTime(timezone=True), nullable=False),
    ...
    sa.Column("body_md", sa.Text, nullable=False),
    sa.Column("body_tsv", postgresql.TSVECTOR, nullable=True),   # ← 0006 leaves NULL; Phase 2 makes it GENERATED instead
```
Copy this directly: `corp_code CHAR(8)` + `ForeignKey("entities.corp_code", ondelete="CASCADE")`, `ticker CHAR(6) nullable`, `payload postgresql.JSONB nullable=False` (see `collector_runs.stats` at 0006:346), `body_md sa.Text nullable=False`.

**CheckConstraint enum-like pattern** (mirror 0006:311-321 `ck_events_event_type` / 0006:266-269 `ck_macro_series_source`) — Discretion #1 resolved to TEXT+CheckConstraint:
```python
sa.CheckConstraint(
    "source IN ('ecos','fred')",
    name="ck_macro_series_source",
),
```
→ Phase 2 writes `sa.CheckConstraint("status IN ('active','superseded','invalidated')", name="ck_decision_cards_status")` and `sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'active'"))` (server_default idiom from 0006:251 `cycle` / 0006:155 `license_flag`).

**Self-referential FK pattern** (no in-repo analog; closest is the soft FK 0006:291-296 `events.filing_rcept_no` with `ondelete="SET NULL"`):
```python
sa.Column(
    "filing_rcept_no",
    sa.CHAR(14),
    sa.ForeignKey("filings.rcept_no", ondelete="SET NULL"),
    nullable=True,
),
```
→ Phase 2 declares both `supersedes` and `superseded_by` as
`sa.ForeignKey("decision_cards.card_id", ondelete="SET NULL")`, `nullable=True`. Single-column self-ref FK works inline in one `create_table` (RESEARCH Pitfall #5 — no `use_alter`).

**halfvec ALTER-TABLE-after-create pattern** (mirror 0006:113 / 0006:176) — reuse the *technique* for the GENERATED tsvector column (NOT halfvec; decision_cards has no embedding per CONTEXT):
```python
op.execute("ALTER TABLE filings ADD COLUMN body_embedding halfvec(1024)")
```
→ Phase 2:
```python
op.execute(
    "ALTER TABLE decision_cards ADD COLUMN body_tsv tsvector "
    "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(body_md, ''))) STORED"
)
```
(`'simple'`, NOT `'korean'` — RESEARCH Pitfall #1.) Alternatively `sa.Column("body_tsv", postgresql.TSVECTOR, sa.Computed("to_tsvector('simple', coalesce(body_md, ''))", persisted=True))` inside `create_table` (RESEARCH §Alternative). Either is acceptable; `op.execute` matches 0006's raw-SQL-for-special-columns habit.

**Index DDL with DESC ordering + partial WHERE + GIN** (mirror 0006:114-125):
```python
op.create_index(
    "ix_filings_corp_filed",
    "filings",
    ["corp_code", sa.text("filed_at DESC")],
)
op.create_index("ix_filings_pblntf_ty", "filings", ["pblntf_ty"])
op.create_index(
    "ix_filings_event_type",
    "filings",
    ["event_type"],
    postgresql_where=sa.text("event_type IS NOT NULL"),
)
```
GIN form (mirror 0006:187-192 `ix_news_tickers`):
```python
op.create_index("ix_news_tickers", "news", ["tickers"], postgresql_using="gin")
```
→ Phase 2 SC#2 indexes:
- `op.create_index("ix_decision_cards_corp_status_gen", "decision_cards", ["corp_code", "status", sa.text("generated_at DESC")])`
- `op.create_index("ix_decision_cards_supersedes", "decision_cards", ["supersedes"])`
- `op.create_index("ix_decision_cards_expires", "decision_cards", ["expires_at"])`
- SC#6: `op.create_index("ix_decision_cards_body_tsv", "decision_cards", ["body_tsv"], postgresql_using="gin")`

**downgrade() — drop indexes then table, reverse order** (mirror 0006:360-385):
```python
def downgrade() -> None:
    op.drop_index("ix_filings_event_type", table_name="filings")
    ...
    op.drop_table("filings")
```
→ drop the 4 indexes (body_tsv → expires → supersedes → corp_status_gen) then `op.drop_table("decision_cards")`.

> **server_default note** (RESEARCH OQ-2): `generated_at` / `as_of` / `expires_at` get NO server_default (data-meaningful, set by author). Contrast 0006 which uses `server_default=sa.func.now()` only for bookkeeping `fetched_at`/`*_seen_at` (0006:95-111).

---

### `src/db/entity_models.py` (MODIFY — add `DecisionCard` ORM class)

**Analog:** the existing `Filing` class in the same file (entity_models.py:72-123) — Recommended option A from RESEARCH Discretion #3 (extend the existing single `Base`, do not create a second declarative base).

**ORM class shape** (mirror `Filing` 72-123):
```python
class Filing(Base):
    __tablename__ = "filings"

    rcept_no = sa.Column(sa.CHAR(14), primary_key=True)
    corp_code = sa.Column(
        sa.CHAR(8),
        sa.ForeignKey("entities.corp_code", ondelete="CASCADE"),
        nullable=False,
    )
    ...
    __table_args__ = (
        sa.Index("ix_filings_corp_filed", "corp_code", sa.text("filed_at DESC")),
        ...
    )
```

**CheckConstraint in `__table_args__`** (mirror `Event` 305-327 / `MacroSeries` 261-264):
```python
__table_args__ = (
    sa.CheckConstraint("source IN ('dart','kind')", name="ck_events_source"),
    sa.Index("ix_events_ticker_date", "ticker", sa.text("event_date DESC")),
)
```

**`__all__` barrel** (mirror entity_models.py:35-43) — add `"DecisionCard"`:
```python
__all__ = ["Base", "Filing", "News", "OHLCV", "MacroSeries", "Event", "CollectorRun"]
```

**Critical for `test_orm_round_trip`:** the ORM column set must EXACTLY match the migration (including the `body_tsv` GENERATED column — declare it `sa.Column("body_tsv", postgresql.TSVECTOR, sa.Computed(...))` or just `postgresql.TSVECTOR, nullable=True` so `sa.inspect` column-set parity holds). The round-trip test asserts `orm_cols == db_cols` per table (see test_migration_0006.py:393-404) AND `set(Base.metadata.tables) == {...}` (0006 test:407-414) — so adding `DecisionCard` requires updating that table-set assertion in the NEW `test_migration_0007.py` (do NOT widen the 0006 assertion; the new test re-asserts the full set including `decision_cards`).

> Do NOT use `_HalfVec` here — decision_cards has no embedding column (CONTEXT lock). `_HalfVec` (entity_models.py:46-65) is irrelevant to this table.

---

### `src/cards/models.py` (model, Pydantic v2)

**Analogs:** `src/shared/portfolio.py` (28-63) and `src/shared/frontmatter.py` (27-67) — house Pydantic v2 conventions.

**`ConfigDict(extra="forbid")` + `Field(pattern=...)` + `field_validator`** (mirror portfolio.py:28-42):
```python
from pydantic import BaseModel, ConfigDict, Field, field_validator

class Holding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    qty: float = Field(ge=0)
    avg_cost: float = Field(ge=0)

    @field_validator("ticker")
    @classmethod
    def _validate_ticker(cls, v: str) -> str:
        if not _TICKER_RE.match(v):
            raise ValueError(f"ticker must be 6 ASCII digits, got {v!r}")
        return v
```

**`Literal[...]` enum + `Field(pattern=...)` + ISO-coerced datetime** (mirror frontmatter.py:30-59):
```python
class TickerRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str = Field(pattern=r"^[0-9]{6}$")
    corp_code: str | None = Field(default=None, pattern=r"^[0-9]{8}$")
    ...

class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date_type  # pydantic auto-coerces ISO-8601
    value: float

class ProvenanceBlock(BaseModel):
    trust_level: Literal["trusted", "semi_trusted", "adversarial"] = "trusted"
```

**SC#5 hard-veto via field declarations only** (RESEARCH §Code Examples + Veto #2 — no `@model_validator` needed):
```python
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
    contradictions: list[Contradiction] = Field(default_factory=list)  # Veto #3
    assumptions: list[str] = Field(min_length=1)         # SC#5 HARD VETO (empty → ValidationError)
    numeric_facts: dict[str, float | int] = Field(default_factory=dict)
    evidence_weights: dict[str, str] = Field(default_factory=dict)
    guards_passed: list[str] = Field(default_factory=list)
    expires_at: datetime                                  # SC#5 HARD VETO (no default, no Optional → omission = ValidationError)
    body_md: str
```

**Nested models match §3 YAML field names EXACTLY** (the round-trip oracle, redesign §3 lines 236-294):
- `Decision`: `stance: Literal["BUY","ADD","HOLD","TRIM","SELL","AVOID"]`, `conviction: float = Field(ge=0, le=1)`, `horizon_days: int = Field(gt=0)`, `price_ref: float | None = None`, `invalidation_triggers: list[str]`.
- `KeyClaim`: `id`, `text`, `evidence_refs: list[str]`, `weight: Literal["HIGH","MEDIUM","LOW","CONTEXT"]`, `confidence: float = Field(ge=0, le=1)`.
- `Contradiction`: `bull`, `bear_evidence`, `bear_claim`, `resolution`.
- `numeric_facts` mixes int (`market_cap_krw: 425000000000000`) and float (`pe_ttm: 17.2`) → typed `dict[str, float | int]` (RESEARCH A2 + Pitfall #4).
- tz offsets `+09:00` must survive — use `datetime` fields, compare via `model_dump(mode="json")`.

---

### `src/cards/store.py` (service, CRUD — SC#4 helpers)

**Analog:** `src/collectors/krx/db_writer.py` — the repo's only write helper; `with engine.begin()` atomic read-then-write + bind-param SQL (Discretion #2 resolved here).

**Module-level `text()` SQL constant + `__all__`** (mirror db_writer.py:30-65):
```python
from sqlalchemy import text

__all__ = ["upsert_ohlcv"]

_UPSERT_SQL = text(
    """
    INSERT INTO ohlcv (ticker, trade_date, ... ) VALUES (:ticker, :trade_date, ...)
    ON CONFLICT (ticker, trade_date) DO UPDATE SET ...
    """
)
_SELECT_EXISTING_SQL = text("SELECT ... FROM ohlcv WHERE ticker = :t AND trade_date = :d")
```

**`with engine.begin()` atomic block + bind params** (mirror db_writer.py:196-207 — the load-bearing pattern for supersession atomicity):
```python
with engine.begin() as conn:
    existing = conn.execute(
        _SELECT_EXISTING_SQL, {"t": ticker, "d": trade_date}
    ).first()
    if existing is None:
        outcome = "inserted"
    elif _values_match_existing(existing, params):
        return "skipped"
    else:
        outcome = "updated"
    conn.execute(_UPSERT_SQL, params)
return outcome
```
→ `save_card(engine, card)` does INSERT-new-then-conditional-UPDATE-old in ONE `with engine.begin()` block (RESEARCH Discretion #2):
```python
with engine.begin() as conn:
    conn.execute(_INSERT_CARD_SQL, {... "payload": json.dumps(card.model_dump(mode="json")) ...})
    if card.supersedes is not None:
        conn.execute(
            sa.text(
                "UPDATE decision_cards SET status='superseded', superseded_by=:new "
                "WHERE card_id=:old AND status='active'"
            ),
            {"new": card.card_id, "old": card.supersedes},
        )
```

**Signature / docstring / regex-guard style** (mirror db_writer.py:30, 137-174):
```python
_TICKER_RE = re.compile(r"^[0-9]{6}$")

def upsert_ohlcv(engine: Engine, *, ticker: str, trade_date: date, ...) -> Literal["inserted","updated","skipped"]:
    if not _TICKER_RE.match(ticker):
        raise ValueError(f"bad ticker (need 6 ASCII digits): {ticker!r}")
```
→ Keyword-only args, `Engine` imported under `TYPE_CHECKING` (db_writer.py:27-28), all SQL via bind params (NEVER f-string — Veto #7 / RULES Safety).

**SC#4 locked signatures + return types** (RESEARCH Discretion #4 — return the Pydantic instance, `body_md` is a field):
- `save_card(engine, card: DecisionCard) -> str` (returns card_id)
- `get_active(engine, corp_code: str) -> DecisionCard | None` — `SELECT ... WHERE corp_code=:cc AND status='active' AND superseded_by IS NULL ORDER BY generated_at DESC LIMIT 1`; reconstruct `DecisionCard` from row (`payload` JSONB + `body_md`).
- `walk_supersedes(engine, card_id: str) -> list[DecisionCard]` (ordered chain).
- `invalidate(engine, card_id: str, reason: str) -> DecisionCard | None` — RESEARCH OQ-1: write `reason` into payload JSONB via `jsonb_set(payload, '{invalidation_reason}', to_jsonb(:reason))` (keeps SC#1 column set intact; do NOT add a column).

> JSONB binding (RESEARCH Pitfall #3): `payload = card.model_dump(mode="json")` (datetimes → ISO strings) then bind `json.dumps(payload)` or the dict directly (psycopg3 auto-adapts dict→JSONB). Confirm `payload->'decision'->>'stance'` round-trips in test_store.py.

---

### `src/cards/validators.py` (utility — only if planner adopts 3-file split)

**Analog:** `portfolio.py::_validate_ticker` (37-42). RESEARCH Discretion #3: if the only rules are the two SC#5 field-level constraints, FOLD into `models.py` (no separate file). Create this file only if a validator is reused across models. Same `@field_validator` + `@classmethod` + `raise ValueError` shape as portfolio.py.

---

### `src/cards/__init__.py` (config — public barrel)

**Analog:** `entity_models.py::__all__` (35-43). Re-export the public surface:
```python
from .models import DecisionCard
from .store import save_card, get_active, walk_supersedes, invalidate

__all__ = ["DecisionCard", "save_card", "get_active", "walk_supersedes", "invalidate"]
```

---

### `tests/db/test_migration_0007.py` (test, schema — clone 0006 test exactly)

**Analog:** `tests/db/test_migration_0006.py` (whole file) — the structure to clone.

**Column / PK / FK introspection via `sa.inspect`** (mirror test_migration_0006.py:32-53):
```python
def test_filings_table_shape(pg_engine) -> None:
    insp = inspect(pg_engine)
    cols = {c["name"]: c for c in insp.get_columns("filings")}
    pk = insp.get_pk_constraint("filings")
    assert pk["constrained_columns"] == ["rcept_no"], pk
    fks = insp.get_foreign_keys("filings")
    fk_corp = [fk for fk in fks if fk["constrained_columns"] == ["corp_code"]]
    assert fk_corp[0]["referred_table"] == "entities"
```

**Index presence + partial-WHERE assertion via `pg_indexes`** (mirror 0006 test:68-82):
```python
idx_names = {i["name"] for i in insp.get_indexes("filings")}
assert "ix_filings_corp_filed" in idx_names
...
idxdef = conn.execute(sa.text(
    "SELECT indexdef FROM pg_indexes WHERE tablename='filings' AND indexname='ix_filings_event_type'"
)).scalar()
assert "event_type IS NOT NULL" in idxdef, idxdef
```
→ For SC#2: assert the 3 index names + `generated_at DESC` in the corp_status_gen `indexdef`. For SC#6: assert `ix_decision_cards_body_tsv` exists and `indexdef` contains `USING gin`, and the body_tsv column type/generation.

**CheckConstraint assertion via `pg_get_constraintdef`** (mirror 0006 test:213-224 / 261-279):
```python
ck = conn.execute(sa.text(
    "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
    "WHERE c.conrelid='macro_series'::regclass AND c.contype='c' "
    "AND c.conname='ck_macro_series_source'"
)).scalar()
assert "ecos" in ck and "fred" in ck, ck
```
→ assert `ck_decision_cards_status` contains `active`, `superseded`, `invalidated`.

**Column type check via `format_type(atttypid, atttypmod)`** (mirror 0006 test:56-66) — for the `body_tsv tsvector` GENERATED column + `payload jsonb` (0006 test:297-309):
```python
typ = conn.execute(sa.text(
    "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
    "WHERE attrelid='filings'::regclass AND attname='body_embedding' AND NOT attisdropped"
)).scalar()
assert typ == "halfvec(1024)", f"... got {typ!r}"
```
→ assert `body_tsv` is `tsvector` and add a `test_body_tsv_generated` that confirms generation (e.g. query `pg_attribute.attgenerated = 's'` or insert a row and assert `body_tsv @@ to_tsquery('simple', ...)` returns the row).

**ORM round-trip test — the load-bearing parity check** (mirror 0006 test:376-414):
```python
def test_orm_round_trip(pg_engine) -> None:
    from db.entity_models import (Base, CollectorRun, Event, Filing, MacroSeries, News, OHLCV)
    insp = inspect(pg_engine)
    for model in (Filing, News, OHLCV, MacroSeries, Event, CollectorRun):
        db_cols = {c["name"] for c in insp.get_columns(model.__tablename__)}
        orm_cols = {c.name for c in model.__table__.columns}
        assert not (orm_cols - db_cols)
        assert not (db_cols - orm_cols)
    assert set(Base.metadata.tables) == {"filings","news","ohlcv","macro_series","events","collector_runs"}
```
→ Phase 2: import `DecisionCard`, add it to the per-model loop, and assert the table set includes `"decision_cards"` (the full set is now 7 tables — see note in the `entity_models.py` section above). Import style is `from db.entity_models import ...` (not `src.db...`).

---

### `tests/cards/conftest.py` (test, fixtures)

**Analog A — `seeded_engine`** (`tests/db/conftest.py:44-62`): pre-inserts 삼성전자/005930/00126380 so the `corp_code` FK is satisfiable. Reuse verbatim for `test_store.py` (the §3 YAML uses corp_code `00126380`, ticker `005930` — already what `seeded_engine` seeds):
```python
@pytest.fixture
def seeded_engine(pg_clean):
    with pg_clean.begin() as conn:
        conn.execute(text(
            "INSERT INTO entities (corp_code, canonical_name, current_ticker, market) "
            "VALUES ('00126380', '삼성전자', '005930', 'KOSPI')"
        ))
        ...
    return pg_clean
```
> `seeded_engine` is defined in `tests/db/conftest.py`. To use it under `tests/cards/`, either re-declare it in `tests/cards/conftest.py` or rely on it being visible (conftest scoping is per-directory — re-declare it locally, copying the block).

**Analog B — inline YAML/dict fixture** (`tests/conftest.py:19-41` `SAMPLE_YAML` + `sample_yaml` fixture). The `decision_card_yaml` fixture transcribes redesign §3 (lines 236-294) verbatim — this IS the SC#3 round-trip oracle:
```python
@pytest.fixture
def decision_card_yaml() -> dict:
    return {
        "card_id": "card_005930_2026-05-28",
        "corp_code": "00126380",
        "ticker": "005930",
        "generated_at": "2026-05-28T17:42+09:00",
        "as_of": "2026-05-28T16:00+09:00",
        "schema_version": 1,
        "decision": {"stance": "HOLD", "conviction": 0.55, "horizon_days": 30,
                     "price_ref": 71200, "invalidation_triggers": [...]},
        "key_claims": [{"id": "c1", "text": "...", "evidence_refs": [...],
                        "weight": "HIGH", "confidence": 0.7}, ...],
        "contradictions": [{"bull": "c1", "bear_evidence": "...",
                            "bear_claim": "...", "resolution": "..."}],
        "assumptions": ["...", "..."],
        "numeric_facts": {"market_cap_krw": 425000000000000, "pe_ttm": 17.2,
                          "foreign_ownership_pct": 53.1},
        "evidence_weights": {"dart": "HIGH", ...},
        "guards_passed": ["position_size_ok", ...],
        "expires_at": "2026-06-15T00:00+09:00",
        "body_md": "...",  # any human-render string (NOT in §3 YAML; add minimal)
    }
```

---

### `tests/cards/test_models.py` (test, unit)

**Analog:** RESEARCH §Code Examples round-trip block + `portfolio.py` validator semantics. Round-trip + 2 hard-veto rejections:
```python
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
Round-trip semantics = `model_validate(card.model_dump(mode="json")) == card` (RESEARCH OQ-3 / Pitfall #4), NOT byte-identical YAML.

---

### `tests/cards/test_store.py` (test, integration DB)

**Analog:** `seeded_engine` consumer pattern (any test that takes `seeded_engine` then `with engine.begin()`). Exercises SC#4: `save_card` → `get_active` returns it → `save_card(supersedes=prev)` flips prior to `superseded='superseded' + superseded_by` in ONE txn → `walk_supersedes` returns the chain → `invalidate` sets status + payload reason. Assert atomicity (RESEARCH Discretion #2) and that `payload->'decision'->>'stance'` survives the JSONB round-trip (Pitfall #3).

---

### `tests/conftest.py` (MODIFY — add `decision_cards` to `_LIVE_TABLES`)

**Analog:** the existing `_LIVE_TABLES` tuple in the same file (tests/conftest.py:97-119). It is ordered TRUNCATE-safe: child tables (FKs into others) FIRST, `entities` LAST.
```python
_LIVE_TABLES = (
    "collector_runs",
    "events",        # FKs into filings → precede filings
    "news",
    "filings",
    "ohlcv",
    "macro_series",
    "events_legacy",
    "ingest_runs", "edges", "chunks", "documents",
    "entity_aliases",
    "entities",      # FK target of nearly everything → last
)
```
→ Add `"decision_cards"` among the body-bearing tables, BEFORE `entities` (it has a corp_code FK → entities). Its self-ref FK is handled by `TRUNCATE ... CASCADE` (already used at conftest.py:140). Place it next to `filings`/`news` (e.g. right after `events`, before `news`). The `_SAFE_TABLE_RE = ^[a-z_]+$` guard (conftest.py:10) already passes for `decision_cards`.

---

## Shared Patterns

### Atomic write boundary
**Source:** `src/collectors/krx/db_writer.py:196-207`
**Apply to:** `src/cards/store.py` (all 4 CRUD helpers; mandatory for `save_card` supersession atomicity).
```python
with engine.begin() as conn:
    existing = conn.execute(_SELECT_EXISTING_SQL, {...}).first()
    ...
    conn.execute(_UPSERT_SQL, params)
```
One `engine.begin()` block per logical operation; bind params only; no f-string SQL (Veto #7).

### Pydantic v2 strict model
**Source:** `src/shared/portfolio.py:28-42`, `src/shared/frontmatter.py:30-59`
**Apply to:** `src/cards/models.py` (every model class).
```python
class X(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(pattern=r"^[0-9]{6}$")
    @field_validator("field")
    @classmethod
    def _v(cls, v): ...
```
`extra="forbid"` rejects unknown payload keys (ASVS V5). Hard vetoes (Veto #2/SC#5) expressed as field declarations (`expires_at: datetime` non-Optional, `assumptions = Field(min_length=1)`) — NOT `@model_validator`.

### TEXT + CheckConstraint enum
**Source:** `0006_phase01_domain_tables.py:311-321, 266-269, 348-351`; ORM form `entity_models.py:261-264, 314-324`
**Apply to:** migration 0007 + `DecisionCard` ORM `__table_args__` (`status` column).
```python
sa.CheckConstraint("source IN ('dart','kind')", name="ck_events_source")
```
Project uses TEXT+Check for EVERY enum-like column; zero `CREATE TYPE` (Discretion #1).

### Schema-shape regression test
**Source:** `tests/db/test_migration_0006.py` (whole file; round-trip 376-414)
**Apply to:** `tests/db/test_migration_0007.py`.
`sa.inspect()` for columns/PK/FK/indexes; raw `pg_attribute.format_type` for special types; `pg_get_constraintdef` for CHECKs; `pg_indexes.indexdef` for partial/GIN; ORM↔DB column-set parity loop + `Base.metadata.tables` assertion.

### TRUNCATE hygiene membership
**Source:** `tests/conftest.py:97-119` (`_LIVE_TABLES`)
**Apply to:** add `"decision_cards"` (before `entities`, after `events`/near `filings`).

---

## No Analog Found

| File / pattern | Role | Data Flow | Reason |
|----------------|------|-----------|--------|
| `body_tsv ... GENERATED ALWAYS AS (to_tsvector('simple', ...)) STORED` | migration DDL | transform | **First GENERATED tsvector in the repo** — `grep to_tsvector src/` returns zero matches (RESEARCH Pitfall #2). 0006's `body_tsv` is a plain nullable column left NULL, not generated. Planner authors the `'simple'` expression FRESH; only the column *name* + `TSVECTOR` *type* + GIN-index *style* are mirrored from 0006. |
| self-referential FK (`supersedes`/`superseded_by` → `decision_cards.card_id`) | migration DDL | CRUD | No self-ref FK exists in the repo. Closest analog is the soft cross-table FK `events.filing_rcept_no` (0006:291-296) with `ondelete="SET NULL"`. RESEARCH Pitfall #5 confirms single-column self-ref works inline (no `use_alter`). |

Everything else has a direct in-repo analog.

## Metadata

**Analog search scope:** `src/db/migrations/versions/`, `src/db/`, `src/shared/`, `src/collectors/krx/`, `tests/db/`, `tests/`, `scripts/`, `.planning/research/redesign-2026-05.md` §3.
**Files scanned (read in full or targeted):** `0006_phase01_domain_tables.py`, `entity_models.py`, `krx/db_writer.py`, `portfolio.py`, `frontmatter.py` (1-90), `test_migration_0006.py`, `tests/conftest.py`, `tests/db/conftest.py`, `init-extensions.sql`, `redesign-2026-05.md` (160-300).
**Read-only verifications:** `ls` (cards dirs absent, migration list), `grep to_tsvector src/` (zero), `grep korean init-extensions.sql` (zero).
**Pattern extraction date:** 2026-05-29
