# Phase 5: Briefing Renderer - Pattern Map

**Mapped:** 2026-07-14
**Files analyzed:** 8 new/modified source files + 9 test files
**Analogs found:** 17 / 17 (100% — Phase 5 is almost entirely reuse; zero new deps)

> This map pulls the **actual code excerpts** from the analogs RESEARCH.md already
> identified by file:line. An executor copies these patterns directly. Every SQL
> excerpt is a module-level `text()` constant bound with params (Veto #7). No file
> here embeds numbers (Veto #6). The read tool returns entries-only (Veto #13).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/db/migrations/versions/0009_*.py` | migration | transform (DDL) | `0007_decision_cards.py` + `0008_phase03_mcp_surface.py` | exact (same hand-written Alembic + partial-index idiom) |
| `src/briefing/models.py` (`BriefingRow`) | model | transform | `src/cards/models.py` (`DecisionCard`) + `src/mcp_v2/models.py` (`Briefing`) | role-match (Pydantic v2, `extra='forbid'`) — MUST NOT extend `DecisionCard` |
| `src/briefing/daily.py` (`generate_daily_briefing`) | service | batch / CRUD | `src/analysis/runner.py` (`analyze_ticker`) | role-match (module-level orchestrator: engine handling, KST, store read+write) |
| `src/briefing/weekly.py` (`generate_weekly_briefing`) | service | batch / transform | `src/analysis/runner.py` + reads 7 daily payloads | role-match |
| `src/briefing/__init__.py` | config | — | `src/cards/store.py` `__all__` header (existing package init style) | role-match |
| `src/cards/store.py` (ADD `save_briefing` / `get_briefing_row` / `list_cards_for_briefing`) | service (data access) | CRUD | existing `save_card` / `get_active` / `walk_supersedes` in the SAME file | exact |
| `src/mcp_v2/tools/briefing.py` (MODIFY — wire) | controller (MCP tool) | request-response | `src/mcp_v2/tools/card.py` (`get_decision_card` → `store.get_active` delegate) | exact |
| Tests (see §Test Patterns) | test | — | `tests/conftest.py`, `tests/cards/conftest.py`, `tests/test_migration.py`, `tests/mcp_v2/test_portfolio_briefing.py` | exact |

---

## Pattern Assignments

### `src/db/migrations/versions/0009_*.py` (migration, DDL transform)

**Primary analog:** `src/db/migrations/versions/0008_phase03_mcp_surface.py` (revision header + partial-index style + module-level SQL constants + `op.execute` for raw DDL).
**Secondary analog:** `src/db/migrations/versions/0007_decision_cards.py` (the columns/CHECK it alters).

**Revision header pattern** (`0008:45-55`) — copy verbatim, bump ids:
```python
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql  # only if JSONB/TSVECTOR needed (0009 does not)

# revision identifiers, used by Alembic.
revision = "0009"
down_revision = "0008"   # head is 0008 — confirmed 0008:52-53
branch_labels = None
depends_on = None
```

**The `corp_code NOT NULL` this migration relaxes** — the exact column being altered (`0007:79-84`):
```python
sa.Column(
    "corp_code",
    sa.CHAR(8),
    sa.ForeignKey("entities.corp_code", ondelete="CASCADE"),
    nullable=False,
),
```

**Partial-index idiom to copy** (`0008:94-99` `ix_notes_corp`, also `0008:127-132` `ix_fundamentals_corp`) — the `postgresql_where=sa.text(...)` form is the established precedent for the `(report_type, report_date) WHERE report_type IS NOT NULL` index:
```python
op.create_index(
    "ix_notes_corp",
    "notes",
    ["corp_code"],
    postgresql_where=sa.text("corp_code IS NOT NULL"),
)
```

**`downgrade()` order + raw-SQL DELETE idiom** (`0008:180-208` reverses in strict LIFO order; note `op.execute` for statements Alembic has no op-helper for). The 0009 downgrade MUST run the DELETE *before* re-adding NOT NULL (RESEARCH §THE LANDMINE "Downgrade footgun"):
```python
def downgrade() -> None:
    op.drop_index("ix_decision_cards_report", table_name="decision_cards")
    op.execute("DELETE FROM decision_cards WHERE report_type IS NOT NULL")  # before restoring NOT NULL
    op.drop_constraint("ck_decision_cards_corp_or_report", "decision_cards", type_="check")
    op.drop_constraint("ck_decision_cards_report_type", "decision_cards", type_="check")
    op.alter_column("decision_cards", "corp_code", nullable=False)
    op.drop_column("decision_cards", "report_date")
    op.drop_column("decision_cards", "report_type")
```

> RESEARCH.md §"Migration 0009" already gives the full recommended `upgrade()`/`downgrade()`
> bodies (lines 145-182). Use those verbatim; this map confirms every idiom they use has a
> live precedent in 0007/0008.
> **CHECK-constraint helper:** `op.create_check_constraint(name, table, condition)` — NOT used
> in 0007/0008 (which used inline `sa.CheckConstraint` at create-table, `0007:115-118`); the
> `op.create_check_constraint` op-helper is the correct ALTER-time form for 0009.
> **`body_tsv` warning:** do NOT touch tsvector — PG17 has no `'korean'` config; the GENERATED
> `'simple'` `body_tsv` (`0007:124-127`) auto-covers the briefing `body_md` for free (Pitfall #2).

---

### `src/cards/store.py` — ADD `save_briefing` / `get_briefing_row` / `list_cards_for_briefing` (service, CRUD)

**Analog:** the existing `save_card` / `get_active` / `walk_supersedes` in the SAME file. This is the strongest, most load-bearing analog in the phase — the new helpers mirror these three exactly.

**Module-level `text()` constant + bind discipline** (`store.py:69-85`, `_INSERT_CARD_SQL`) — the template for a NEW `_INSERT_BRIEFING_SQL` that binds `report_type`/`report_date` and sets `corp_code=NULL, ticker=NULL`:
```python
_INSERT_CARD_SQL = text(
    """
    INSERT INTO decision_cards (
        card_id, corp_code, ticker,
        generated_at, as_of,
        payload, body_md,
        status, supersedes, superseded_by,
        expires_at, schema_version
    ) VALUES (
        :card_id, :corp_code, :ticker,
        :generated_at, :as_of,
        CAST(:payload AS jsonb), :body_md,
        'active', :supersedes, NULL,
        :expires_at, :schema_version
    )
    """
)
```
Note `CAST(:payload AS jsonb)` — the JSONB TEXT-cast bind (Pitfall #3, datetimes never corrupt). The briefing INSERT reuses this exact cast; it ADDS `report_type, report_date` columns and drops `corp_code`/`ticker` to `NULL`.

**`save_card` body — the write-path template** (`store.py:180-201`), esp. the `model_dump(mode="json")` → `json.dumps` → single-txn `engine.begin()`:
```python
payload = card.model_dump(mode="json", exclude=_PAYLOAD_EXCLUDE)
params: dict[str, Any] = {
    "card_id": card.card_id,
    "corp_code": card.corp_code,
    ...
    "payload": json.dumps(payload),
    "body_md": card.body_md,
    ...
}
with engine.begin() as conn:
    conn.execute(_INSERT_CARD_SQL, params)
    if effective_supersedes is not None:
        conn.execute(_SUPERSEDE_PRIOR_SQL, {"new": card.card_id, "old": effective_supersedes})
return card.card_id
```
`save_briefing(engine, row: BriefingRow)` mirrors this: `json.dumps(row.payload)`, bind params, single `engine.begin()`. No supersede branch (a briefing does not supersede an analysis card).

**`get_active` — the SELECT + reconstruct template** (`store.py:97-107` SQL, `store.py:204-216` fn). `get_briefing_row` copies this shape but selects `payload, body_md` filtered on `report_type`/`report_date`:
```python
_SELECT_ACTIVE_SQL = text(
    """
    SELECT payload, body_md, status, supersedes, superseded_by
      FROM decision_cards
     WHERE corp_code = :cc
       AND status = 'active'
       AND superseded_by IS NULL
     ORDER BY generated_at DESC, card_id DESC
     LIMIT 1
    """
)

def get_active(engine: Engine, corp_code: str) -> DecisionCard | None:
    with engine.begin() as conn:
        row = conn.execute(_SELECT_ACTIVE_SQL, {"cc": corp_code}).first()
    if row is None:
        return None
    return _row_to_card(row.payload, row.body_md, row.status)
```
New `_SELECT_BRIEFING_ROW_SQL` (per RESEARCH §get_briefing Wiring step 2):
`SELECT payload, body_md FROM decision_cards WHERE report_type=:rt AND report_date=:d AND status='active' ORDER BY generated_at DESC LIMIT 1`.

**`walk_supersedes` — the diff-baseline read** (`store.py:219-247`) — daily.py calls `get_active` then this to get `chain[1]` (the prior card, D-02). No new store code needed for the diff read; it is pure reuse:
```python
active = get_active(engine, corp_code)              # DecisionCard | None
chain  = walk_supersedes(engine, active.card_id)    # [active, prior, ..., oldest]
prior  = chain[1] if len(chain) >= 2 else None
```

**`__all__` export list to extend** (`store.py:49`):
```python
__all__ = ["save_card", "get_active", "walk_supersedes", "invalidate"]
# → append "save_briefing", "get_briefing_row", "list_cards_for_briefing"
```

**GAP note (from RESEARCH):** there is NO enumeration helper today — `list_cards_for_briefing(engine, on_date)` is genuinely new store code. Model its SQL on the `get_active` template above; the enumeration WHERE clause uses `(generated_at AT TIME ZONE 'Asia/Seoul')::date = :d` and `(expires_at AT TIME ZONE 'Asia/Seoul')::date = :d AND status='active'` (RESEARCH §Change Detection). The `invalidate()` "no timestamp" gap (`store.py:117-125` `_INVALIDATE_SQL` writes reason but no `invalidated_at`) is an OPEN planner decision (RESEARCH §"invalidated today" options a/b/c).

---

### `src/briefing/models.py` — `BriefingRow` (model, transform)

**Analog:** `src/cards/models.py` `DecisionCard` (`extra='forbid'` discipline, field-declaration-as-validation) + `src/mcp_v2/models.py` `Briefing` (the result model already in use).

**`extra='forbid'` + field-only validation** (`cards/models.py:76-92`) — copy the `ConfigDict` and the timed-thesis fields (`expires_at` non-Optional; a briefing MUST supply one — RESEARCH §THE LANDMINE row `expires_at`):
```python
class DecisionCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card_id: str
    corp_code: str = Field(pattern=r"^[0-9]{8}$")   # ← BriefingRow OMITS this (no single corp)
    ticker: str = Field(pattern=r"^[0-9A-Z]{6}$")   # ← BriefingRow OMITS this
    generated_at: datetime
    as_of: datetime
    decision: Decision                               # ← BriefingRow OMITS (no stance/conviction — Veto #1/#4)
    assumptions: list[str] = Field(min_length=1)     # ← BriefingRow OMITS (no per-ticker assumptions)
    expires_at: datetime                             # ← BriefingRow KEEPS (daily→next KST close; weekly→week_end+7d)
    body_md: str                                     # ← BriefingRow KEEPS
```

**Why NOT reuse `DecisionCard`** (Pitfall #1): its 5 required fields (`corp_code`, `ticker`, `decision`, `assumptions min_length=1`, `expires_at`) have no honest briefing value — inventing a stance/conviction violates Veto #1/#4. `BriefingRow` is a SEPARATE model. Recommended fields (RESEARCH §THE LANDMINE RESOLUTION 3): `card_id`, `report_type`, `report_date`, `generated_at`, `as_of`, `expires_at`, `payload: dict` (or a typed `BriefingPayload`), `body_md`.

**Result-model contract that must stay unchanged** — `Briefing` (`mcp_v2/models.py:223-233`). Do NOT add a `body_md` field (Veto #13 filter-before-context is satisfied by its ABSENCE):
```python
class Briefing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: str
    type: str  # "daily" | "weekly"
    found: bool = False
    entries: list[dict] = Field(default_factory=list)   # ← Phase 5 populates from payload["entries"]
```

---

### `src/briefing/daily.py` — `generate_daily_briefing(date)` (service, batch orchestrator)

**Analog:** `src/analysis/runner.py` `analyze_ticker` — the module-level orchestrator entrypoint style (engine defaulting, KST handling, read→build→store).

**Module header constants** (`runner.py:71-72`) — the `_KST` idiom to reuse for all date-boundary math (do NOT use naive `date.today()` — Pitfall #3):
```python
_log = logging.getLogger(__name__)
_KST = ZoneInfo("Asia/Seoul")
```

**Engine-defaulting entrypoint signature** (`runner.py:103-140`) — the injectable-engine pattern lets tests pass a testcontainers engine:
```python
def analyze_ticker(
    corp_code: str,
    as_of: datetime | None = None,
    *,
    engine: Engine | None = None,
    backend: DebateBackend | None = None,
    timeout_s: float = 600.0,
) -> DecisionCard:
    engine = engine if engine is not None else get_engine()
    ...
```
`generate_daily_briefing(on_date, *, engine=None, held_tickers: set[str] | None = None)` copies this — inject `engine` AND `held_tickers` so tests seed holdings without a real `portfolio.md` (RESEARCH §Prioritization "Recommendation").

**Read → build → store shape** (`runner.py:155-165` + `225`) — the daily's collect→render→persist:
```python
prior = get_active(engine, corp_code)               # store read
decision = gate.decide(engine, prior, as_of_dt)     # deterministic logic (no LLM)
...
save_card(engine, card, supersedes=prior.card_id if prior else None)   # store write
return card
```
Daily analog: `list_cards_for_briefing(engine, on_date)` → diff each via `get_active`+`walk_supersedes` → build entries → `save_briefing(engine, row)`. **NO backend/LLM** (D-06 render is deterministic string assembly — unlike runner, daily.py imports no `subagents`).

**Structured logging idiom** (`runner.py:167-170, 372-376`) — `logging` with `extra={...}`:
```python
_log.warning(
    "card has no contradictions — suspect",
    extra={"corp_code": card.corp_code, "card_id": card.card_id},
)
```

**KST close derivation** (`runner.py:382-395` `_default_as_of`) — reusable pattern for the daily's `report_date`/`expires_at` (next KST close):
```python
now = datetime.now(_KST)
close = now.replace(hour=16, minute=0, second=0, microsecond=0)
if now < close:
    close -= timedelta(days=1)
while close.weekday() >= 5:  # Saturday=5, Sunday=6
    close -= timedelta(days=1)
```

**Held-first degradation** (portfolio may be absent — RESEARCH §Prioritization). `list_portfolio` (`mcp_v2/tools/portfolio.py:44-47`) maps a missing file to `DataBackendError`; the underlying `Portfolio.load` raises `PortfolioLoadError` (`shared/portfolio.py:74-75`). daily.py must wrap the load and fall back to `held_tickers = set()` on failure — never crash:
```python
try:
    portfolio = Portfolio.load(_REPO_ROOT)
except PortfolioLoadError as exc:
    raise DataBackendError(...) from exc   # tool layer; in briefing prefer: held = set()
```

---

### `src/briefing/weekly.py` — `generate_weekly_briefing(week_anchor)` (service, transform)

**Analog:** same `runner.py` orchestrator shape + reads the 7 daily payloads back through `store.list_cards_for_briefing` / a date-range SELECT. **Pre-materialized** (SC#4): compute `entries` ONCE at generation and store them — `get_briefing(type='weekly')` NEVER recomputes (Pitfall #4).

**Reuses the exact same primitives as daily:** `_KST`, `save_briefing`, the D-01 sort key. The weekly-specific logic (per-ticker NET, flip-flop drop, `coverage:N/7`) is deterministic dict aggregation over `payload["entries"]` — RESEARCH §"Weekly Roll-Up" gives the 6-step algorithm and the `source_reports` / `coverage` payload shapes. No new analog beyond runner.py + the store helpers.

---

### `src/mcp_v2/tools/briefing.py` — MODIFY to wire `get_briefing` (controller, request-response)

**Analog:** `src/mcp_v2/tools/card.py` `get_decision_card` — the canonical "delegate ALL SQL to `cards.store`, inline NO `text()`" pattern (the SC#3 AST guard REQUIRES this — see §Shared Patterns).

**Delegate-to-store pattern** (`card.py:20-22` docstring contract + `card.py:72-90` body):
```python
# This module performs NO direct SQL — all DB access is delegated to
# ``cards.store.get_active`` (so the SC#3 AST guard finds no ``text()`` here).
...
card = store.get_active(get_engine(), corp_code)
if card is None:
    return CardView(corp_code=corp_code, found=False, card=None)   # D-01 empty result, NOT error
...
return CardView(corp_code=corp_code, found=True, card=data)
```

**Current honest-empty body to REPLACE** (`briefing.py:26-46`) — keep the `_VALID_TYPES` guard, replace the `found=False` return with a `store.get_briefing_row(...)` delegate:
```python
def get_briefing(date: str, type: str = "daily") -> Briefing:
    if type not in _VALID_TYPES:
        raise InvalidArgument("type must be 'daily' or 'weekly'")
    # Phase 5 wires the data; Phase 3 is an honest empty model (no report_type query).
    return Briefing(date=date, type=type, found=False, entries=[])
```
Wired form (RESEARCH §get_briefing Wiring steps 1-4): map `daily→'daily_briefing'` / `weekly→'weekly_briefing'`, validate `date` as ISO-8601 (ASVS V5 — add before the `report_date` bind), call `row = store.get_briefing_row(get_engine(), report_type, report_date)`, return `Briefing(date=date, type=type, found=row is not None, entries=(row.payload["entries"] if row else []))`. **Import `from cards import store` + `from db.engine import get_engine`** exactly like `card.py:30-31`.

**Registration line stays** (`briefing.py:51` / identical to `card.py:95`):
```python
mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(get_briefing)
```

---

## Shared Patterns

### Parameterized `text()` — the ONLY DB access (Veto #7)
**Source:** `src/cards/store.py:67-125` (all SQL is a module-level `text()` constant, bound with a params dict).
**Apply to:** every new store helper (`save_briefing`, `get_briefing_row`, `list_cards_for_briefing`). NEVER f-string / `%` / `+` / `.format` into `text()`.
```python
_INVALIDATE_SQL = text(
    """
    UPDATE decision_cards
       SET status = 'invalidated',
           payload = jsonb_set(payload, '{invalidation_reason}', to_jsonb(CAST(:reason AS text)))
     WHERE card_id = :cid
       AND status <> 'invalidated'
    """
)
```

### SC#3 AST run-sql guard — forbids `text()` in `src/mcp_v2` (why the tool delegates)
**Source:** `tests/mcp_v2/test_no_run_sql_guard.py:102-126` (`test_no_fstring_sql_in_mcp_v2`) — AST-walks every `src/mcp_v2/**.py` and requires each `text(...)` first arg be a **string constant or module-level Name**. It also asserts the tool registry is EXACTLY the 10 locked names (`:27-40`), `get_briefing` already among them.
**Apply to:** `src/mcp_v2/tools/briefing.py` — it MUST contain NO `text()` at all; all SQL lives in `cards.store`. (Adding an inline query here fails this test.)
```python
LOCKED_TOOL_NAMES = frozenset({
    "get_filing", "search_filings", "ohlcv_range", "flow_range", "peer_view",
    "hybrid_search", "get_note", "get_decision_card", "list_portfolio", "get_briefing",
})  # get_briefing count/name must NOT change
```

### JSONB round-trip (Pitfall #3)
**Source:** `src/cards/store.py:180,187` — `model_dump(mode="json")` → `json.dumps(...)` → bound as TEXT with `CAST(:payload AS jsonb)`. Datetimes serialize to ISO-8601 and never corrupt.
**Apply to:** `save_briefing` (bind `json.dumps(row.payload)`), and to `get_briefing_row` reconstruction (`row.payload` comes back as a dict).

### KST date boundaries (Pitfall #3)
**Source:** `src/analysis/runner.py:72` and `src/analysis/gate.py:73` — `_KST = ZoneInfo("Asia/Seoul")`; enumerate dates with `(col AT TIME ZONE 'Asia/Seoul')::date`.
**Apply to:** `daily.py`, `weekly.py`, and the `list_cards_for_briefing` WHERE clauses. The dedicated `report_date DATE` column is queried by equality (timezone-safe); `generated_at`/`expires_at` are `timestamptz +09:00` so their `::date` needs the AT TIME ZONE cast.

### Empty result is `found=False`, NOT an error (D-01)
**Source:** `src/mcp_v2/tools/card.py:73-75` — `get_active` returning `None` yields `CardView(found=False, card=None)`, never a raise.
**Apply to:** `get_briefing` — BUT note SC#6/CONTEXT recommends the daily ALWAYS writes a short row (empty `entries=[]`) so `get_briefing` returns `found=True` even on a no-change day. A genuine miss (no row at all) still returns `found=False`.

---

## Test Patterns

### `tests/briefing/conftest.py` — multi-entity seed
**Analog:** `tests/cards/conftest.py:101-124` (`seeded_engine`) — but it seeds ONLY 삼성전자/005930. Phase 5 truncation (SC#1, >10 entries) + multi-ticker priority need ≥11 tickers with active cards + superseded chains (RESEARCH §Wave 0 Gaps). Copy the INSERT idiom, loop it:
```python
with pg_clean.begin() as conn:
    conn.execute(text(
        "INSERT INTO entities (corp_code, canonical_name, current_ticker, market) "
        "VALUES ('00126380', '삼성전자', '005930', 'KOSPI')"
    ))
    conn.execute(text(
        "INSERT INTO entity_aliases (corp_code, kind, value, valid_from, valid_to) "
        "VALUES ('00126380', 'ticker', '005930', :vf, NULL), "
        "       ('00126380', 'name',   '삼성전자', :vf, NULL)"
    ), {"vf": date(2020, 1, 1)})
```
The `decision_card_yaml` fixture (`tests/cards/conftest.py:24-98`) is the ready-made valid-card dict — reuse it (varying `corp_code`/`ticker`/`decision.stance`/`conviction`) to build the ≥11 cards and superseded chains.

### DB fixtures (session/function scope)
**Analog:** `tests/conftest.py:51-86` (`pg_engine` — session-scoped, `alembic upgrade head` once) and `:126-145` (`pg_clean` — function-scoped TRUNCATE incl. `decision_cards`, `:105`). Consume `pg_clean`/`seeded_engine` directly; no new fixture infra needed. `decision_cards` is already in `_LIVE_TABLES` (`:97-123`) so briefing rows get truncated between tests for free.

### `tests/db/test_migration_0009.py` — up/down roundtrip
**Analog:** `tests/test_migration.py:275-298` (`test_downgrade_then_upgrade_idempotent`) — the `command.downgrade`/`command.upgrade` pattern with a `try/finally` that ALWAYS restores head. And `:44-87` (`test_entities_schema`) for the `information_schema.columns` / `pg_get_constraintdef` assertion style:
```python
url = os.environ["DATABASE_URL"]
cfg = Config("src/db/alembic.ini")
cfg.set_main_option("sqlalchemy.url", url)
try:
    command.downgrade(cfg, "0008")   # 0009 columns gone, corp_code NOT NULL restored
    command.upgrade(cfg, "0009")     # report_type/report_date present, corp_code nullable
finally:
    command.upgrade(cfg, "head")     # always leave session engine fully migrated
```
Assert the CHECK constraints via `pg_get_constraintdef` (like `:78-87`) and the partial index via `pg_indexes.indexdef` (like `:136-142`).

### `tests/mcp_v2/test_briefing_wired.py` — REPLACES `test_portfolio_briefing.py:96-132`
**Analog:** `tests/mcp_v2/test_portfolio_briefing.py` — the Phase-3 honest-empty tests. `test_get_briefing_does_not_reference_report_type` (`:96-132`) is now INVERTED: Phase 5 DOES delegate a `report_type` query. **This is an EXPECTED test change, not a regression** (RESEARCH §State of the Art). Keep `test_get_briefing_bad_type_raises_invalid_argument` (`:135-139`). Add: seed a `daily_briefing` row → `get_briefing('...','daily')` returns `found=True` + populated `entries`; assert `Briefing` has no `body_md` attr (Veto #13 `test_no_body_leak`).

---

## No Analog Found

None. Every Phase-5 file has a strong in-repo analog. The only genuinely NEW logic (no line-for-line copy) is:
| Behavior | Note |
|----------|------|
| `list_cards_for_briefing` enumeration SQL | New query, but SQL SHAPE copies `get_active` (`store.py:97-107`); the WHERE clause is new (KST `::date` enumeration) |
| Weekly NET aggregation | New deterministic dict logic; orchestration shell copies `runner.py`. Algorithm fully specified in RESEARCH §Weekly Roll-Up |
| D-01 3-level sort key | New pure function; all tiebreak fields (`ticker`, `decision.conviction`, `contradictions`, `status`) exist on `DecisionCard` |
| `invalidated_at` timestamp | OPEN planner decision (RESEARCH §"invalidated today" options a/b/c); `invalidate()` currently records none (`store.py:117-125`) |

## Metadata

**Analog search scope:** `src/db/migrations/versions/`, `src/cards/`, `src/mcp_v2/`, `src/analysis/`, `src/shared/`, `tests/`, `tests/cards/`, `tests/mcp_v2/`, `tests/db/`
**Files read (analogs):** `0007_decision_cards.py`, `0008_phase03_mcp_surface.py`, `src/cards/store.py`, `src/cards/models.py`, `src/mcp_v2/tools/briefing.py`, `src/mcp_v2/tools/card.py`, `src/mcp_v2/models.py`, `src/mcp_v2/tools/portfolio.py`, `src/shared/portfolio.py`, `src/analysis/runner.py`, `src/analysis/gate.py`, `tests/conftest.py`, `tests/cards/conftest.py`, `tests/test_migration.py`, `tests/mcp_v2/test_portfolio_briefing.py`, `tests/mcp_v2/test_no_run_sql_guard.py`
**Verified NOT-yet-existing:** `src/briefing/` (absent), `tests/briefing/` (absent), migration `0009` (head is `0008`)
**Pattern extraction date:** 2026-07-14
