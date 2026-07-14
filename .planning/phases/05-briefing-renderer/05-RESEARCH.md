# Phase 5: Briefing Renderer - Research

**Researched:** 2026-07-14
**Domain:** Deterministic report aggregation over `decision_cards` (Postgres/SQLAlchemy/Alembic), MCP read-tool wiring
**Confidence:** HIGH (all findings grounded in file:line evidence from the live codebase; no external-library uncertainty — Phase 5 introduces zero new dependencies)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01 (Prioritization):** Fixed deterministic 3-level sort key: **(1) held-first** (portfolio holdings rank above watchlist), then **(2) event class** in order `stance flip` > `new contradiction(s)` > `expired/invalidated` > `new high-conviction`, then **(3) conviction descending** within a class. Truncate to 10.
- **D-02 (Change detection baseline):** Diff baseline = the prior active card in the supersession chain (current active card vs the card it superseded, via `store.walk_supersedes` / the `superseded_by` link). Diff `stance`, `contradictions`, `conviction`. NO separate snapshot store; do NOT diff against yesterday's briefing row.
- **D-03 (First-card rule):** A ticker's first-ever card counts as a change ONLY if high-conviction (conviction ≥ 0.8). A first card below 0.8 is noise, excluded.
- **D-04 (Table columns):** `body_md` is the ROADMAP-locked table `종목 | 변화 | 근거 | 제안 | Why now | Why not`.
- **D-05 ('제안' semantics):** '제안' column = the card's stance label + conviction (BUY/ADD/HOLD/TRIM/SELL/AVOID + numeric conviction). NO freeform action text, NO target price, NO return forecast (Veto #1).
- **D-06 (Why now / Why not):** 'Why now' = card's top-ranked `key_claim` (catalyst); 'Why not' = card's top-ranked `contradiction`. Extracted directly from card structure — deterministic, **NO extra LLM call**. '변화' shows the delta (`HOLD→SELL`, `+2 contradictions`, `expired`); '근거' shows the leading supporting evidence.
- **D-07 (Weekly NET):** Weekly aggregates per-ticker NET change: start-of-week state vs end-of-week state (stance + conviction movement) plus a count of intra-week events. Intra-week flip-flops net to "no change" and are dropped; daily rows preserve detail.
- **D-08 (Best-effort coverage):** If some of 7 daily briefings are missing (holiday/failure), roll up whatever exists and record coverage (e.g. `coverage: 5/7`). Do NOT block on a full 7; missing ≠ no-change.

### Claude's Discretion
- **No-change threshold + empty-row policy (SC#6):** exact "significant change" threshold and whether an empty day writes a short `report_type` row — left to planning. **Recommended direction (from CONTEXT):** DO write a short row on a no-change day so `get_briefing` returns a real card, never an empty page.
- `report_type` migration shape (new column after 0007, nullable, indexed for date+type lookup), payload schema, and priority-tiebreak edge cases are planner/researcher territory.

### Deferred Ideas (OUT OF SCOPE)
- Briefing scheduling / cron trigger (which day the weekly covers, how the daily is kicked off) — **Phase 9 ops** (systemd.timer / Claude Schedule).
- Any action/order off a briefing — **Phase 6** (paper-trade action layer).
- No scope creep raised during discussion.
</user_constraints>

<phase_requirements>
## Phase Requirements

No REQ-IDs exist in this project (`.planning/REQUIREMENTS.md` absent — confirmed). The requirements ARE the ROADMAP Success Criteria SC#1–6.

| ID | Description | Research Support |
|----|-------------|------------------|
| SC#1 | `src/briefing/daily.py::generate_daily_briefing(date)` collects stance-changed, new-contradiction, expired/invalidated, new high-conviction(≥0.8) cards; ≤10 entries; priority-sorted | §"Change Detection & Enumeration", §"Prioritization"; requires a NEW store enumeration helper (gap) + diff via `get_active`+`walk_supersedes` |
| SC#2 | Result stored as `decision_cards` row `report_type='daily_briefing'` (payload JSONB + body_md TEXT) | §"THE LANDMINE" — needs migration 0009 + a separate `save_briefing` write path (cannot reuse `save_card`/`DecisionCard`) |
| SC#3 | `body_md` = table `종목 \| 변화 \| 근거 \| 제안 \| Why now \| Why not` | §"Render", D-04/D-05/D-06 fields all exist on `DecisionCard` |
| SC#4 | Weekly = `weekly_briefing` row + `source_reports:[daily×7]`, pre-materialized, NO recompute on read | §"Weekly Roll-Up" |
| SC#5 | Readable via MCP `get_briefing(date, type)` | §"get_briefing Wiring" — delegate SQL to a store helper (SC#3 AST guard forbids `text()` in the tool) |
| SC#6 | No change → short "no significant changes today" card only; never empty page / never skip render | §"No-Change Day" |
</phase_requirements>

## Summary

Phase 5 is a **deterministic aggregation feature over an already-locked table**. The technical domain is not a library ecosystem — it is the internal contract of `decision_cards` (migration 0007), the `src/cards/store.py` CRUD surface, and the honest-empty `get_briefing` MCP scaffold. There are **zero new external dependencies**; everything is SQLAlchemy `text()` constants, Pydantic v2 models, Alembic hand-written migrations, and pytest+testcontainers — all already in the repo.

The single highest-risk finding is a **hard schema/model landmine**: a briefing row must live in `decision_cards` (SC#2) but is NOT a `DecisionCard`. The table's `corp_code` is `CHAR(8) NOT NULL` with a FK to `entities` (`0007_decision_cards.py:79-84`), and the `DecisionCard` Pydantic model requires `corp_code`, `ticker`, a `Decision` (stance+conviction), and `assumptions min_length=1` (`cards/models.py:79-91`). A digest has none of these meaningfully — inventing a fake stance/conviction would violate Veto #1/#4. Therefore Phase 5 **must not reuse `save_card`/`DecisionCard`** for briefing rows; it needs (a) migration 0009 that drops `corp_code NOT NULL` guarded by a partial CHECK, and (b) a separate typed write path (`save_briefing` + a `BriefingRow` model). A second gap: `src/cards/store.py` has **no enumeration helper** (only single-corp `get_active`), so the daily collect-set needs a new store query; and `invalidate()` records **no timestamp** (`store.py:117-125`), so "invalidated today" is not directly queryable — this needs a design choice.

**Primary recommendation:** Add migration **0009** (`report_type TEXT NULL`, `report_date DATE NULL`, `ALTER corp_code DROP NOT NULL` + partial CHECK `report_type IS NOT NULL OR corp_code IS NOT NULL`, partial index `(report_type, report_date) WHERE report_type IS NOT NULL`). Build `src/briefing/{daily,weekly}.py` that reads cards through a new `cards.store` enumeration helper + `get_active`/`walk_supersedes` diff, renders the locked 6-column table deterministically (no LLM), and writes the row via a new `cards.store.save_briefing()`. Wire `get_briefing` to delegate the SELECT to a store helper (never inline `text()` in the tool — the SC#3 AST guard forbids it). Write a short no-change row so `get_briefing` is always positive.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Change detection (stance/contradiction/conviction diff) | `src/briefing/` (new module) | `src/cards/store.py` (data access) | Pure deterministic logic over stored cards; the store owns the SQL (Veto #7 — no `run_sql`) |
| Card enumeration for date D | `src/cards/store.py` (NEW helper) | — | All `decision_cards` SQL lives in the store (mirrors `get_active`); the tool/module layers never emit `text()` |
| Briefing-row persistence | `src/cards/store.py` (NEW `save_briefing`) | migration 0009 (schema) | The write path is a typed store function; the NULL-corp allowance is a schema concern |
| Table render (`body_md`) | `src/briefing/` | — | Deterministic string assembly from card fields (D-04/05/06); NO embedding, NO LLM |
| Read-back | `src/mcp_v2/tools/briefing.py` (wire existing scaffold) | `src/cards/store.py` (SELECT) | The MCP tool is a thin delegate (mirrors `get_decision_card`→`store.get_active`); SC#3 AST guard requires SQL in the store |
| Prioritization / truncation | `src/briefing/` | `src/mcp_v2/tools/portfolio.py` (held membership) | Sort key is app logic; held-first reads portfolio membership |

## Standard Stack

No new packages. Phase 5 uses only libraries already pinned in `pyproject.toml`:

### Core (already installed — verified in `pyproject.toml`)
| Library | Version (pinned) | Purpose | Why Standard |
|---------|------------------|---------|--------------|
| SQLAlchemy | `>=2.0,<3` (`pyproject.toml:45`) | `text()` parameterized queries + engine | Established store pattern (`cards/store.py`); Veto #7 (no run_sql) |
| Alembic | `>=1.18,<2` (`pyproject.toml:44`) | Migration 0009 (`report_type`) | Hand-written, `target_metadata=None` (`env.py:20`) |
| Pydantic v2 | (transitive, used across `cards/models.py`, `mcp_v2/models.py`) | `BriefingRow` model + existing `Briefing`/`DecisionCard` | `extra='forbid'` discipline project-wide |
| pytest | `>=9.0` (`pyproject.toml:63`) | Test suite | `testpaths=["tests"]`, `pythonpath=["src"]` (`pyproject.toml:72-73`) |
| testcontainers[postgres] | `>=4.8` (`pyproject.toml:67`) | `pg_engine` session fixture (real PG17 + vchord) | `conftest.py:51-86` |

### Supporting
| Library | Purpose | When to Use |
|---------|---------|-------------|
| `zoneinfo.ZoneInfo("Asia/Seoul")` | KST date-boundary math for `generated_at::date` / `report_date` | Already used in `runner.py:72`, `gate.py:73` — reuse the `_KST` idiom |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Briefing rows in `decision_cards` (SC#2 locked) | A separate `briefings` table | **Rejected** — SC#2 explicitly mandates a `decision_cards` row with `report_type`. A separate table violates the SC. |
| Dedicated `report_date DATE` column | Reuse `as_of::date` or `generated_at::date` (KST expression index) | Timezone footgun: `generated_at` is `timestamptz` stored `+09:00`; `::date` in UTC is wrong for late-KST-evening rows. A DATE column + equality is robust. See §"get_briefing Wiring". |

**Installation:** none — `uv sync` already provides everything.

## Package Legitimacy Audit

**No external packages are installed in this phase.** All code uses libraries already present and verified by prior phases (SQLAlchemy, Alembic, Pydantic, pytest, testcontainers). Package Legitimacy Gate is **N/A** — nothing to slopcheck.

## THE LANDMINE: a briefing row is NOT a `DecisionCard`

> This is the single highest-risk unknown (research focus #2). Surfaced explicitly with quoted constraints.

### `decision_cards` table constraints (migration `0007_decision_cards.py`)

| Column | Constraint | Briefing-row impact |
|--------|-----------|---------------------|
| `corp_code` | `sa.CHAR(8)`, `ForeignKey("entities.corp_code", ondelete="CASCADE")`, **`nullable=False`** (`0007:79-84`) | **BLOCKS insert.** A digest has no single corp; a fake corp_code would need to exist in `entities` (FK) and is semantically wrong. |
| `expires_at` | `sa.DateTime(timezone=True)`, **`nullable=False`**, no server_default (`0007:108`) | Not a blocker — briefing must SUPPLY a value (e.g. daily → next KST close; weekly → week_end+7d). |
| `payload` | `JSONB`, `nullable=False` (`0007:88`) | Briefing supplies `{entries:[...], ...}`. OK. |
| `body_md` | `Text`, `nullable=False` (`0007:89`) | Briefing supplies the 6-column table. OK. |
| `generated_at`, `as_of` | `nullable=False` (`0007:86-87`) | Briefing supplies both. OK. |
| `status` | `nullable=False` default `'active'`, CHECK `status IN ('active','superseded','invalidated')` (`0007:90-95,115-118`) | Briefing uses `'active'`. OK. |
| `ticker` | `sa.CHAR(6)`, **`nullable=True`** (`0007:85`) | Briefing leaves NULL at the DB level. OK. |
| `body_tsv` | GENERATED from `body_md` (`0007:124-127`) | Auto-computed. OK — briefing `body_md` becomes FTS-searchable for free. |

### `DecisionCard` Pydantic constraints (`cards/models.py`) — a briefing CANNOT be a `DecisionCard`

```
corp_code: str = Field(pattern=r"^[0-9]{8}$")          # models.py:79  — REQUIRED
ticker:    str = Field(pattern=r"^[0-9A-Z]{6}$")       # models.py:80  — REQUIRED (non-Optional)
decision:  Decision                                     # models.py:84  — stance enum + conviction + horizon_days>0
assumptions: list[str] = Field(min_length=1)            # models.py:87  — empty → ValidationError
expires_at: datetime                                    # models.py:91  — REQUIRED
body_md:   str                                          # models.py:92  — REQUIRED
```

A digest has no `corp_code`, no single `ticker`, no `stance`/`conviction` (inventing them violates Veto #1 "no price prediction" and Veto #4 "no black-box scores"), and no per-ticker `assumptions`. **Forcing a `DecisionCard` is impossible and wrong.**

### `save_card` cannot be reused

`store.save_card` (`store.py:147-201`) takes a `DecisionCard` and its `_INSERT_CARD_SQL` (`store.py:69-85`) hard-codes the 12 columns — it (a) binds `card.corp_code` (NOT NULL), (b) does **not** include `report_type`. So it can neither carry a briefing nor set `report_type`.

### RESOLUTION (recommended)

1. **Migration 0009 makes `corp_code` nullable** BUT preserves the analysis-card invariant via a partial CHECK:
   `CHECK (report_type IS NOT NULL OR corp_code IS NOT NULL)` — analysis cards (`report_type IS NULL`) still require `corp_code`; briefing rows (`report_type` set) may have NULL `corp_code`.
2. **A separate typed write path** `cards.store.save_briefing(engine, row)` with its own INSERT SQL that sets `report_type`, `report_date`, `corp_code=NULL`, `ticker=NULL`. Mirror `save_card`'s parameterized-`text()` discipline (Veto #7).
3. **A separate `BriefingRow` Pydantic model** (`src/briefing/models.py`, `extra='forbid'`) — do NOT extend `DecisionCard`. Fields: `card_id`, `report_type`, `report_date`, `generated_at`, `as_of`, `expires_at`, `payload: dict` (or a typed `BriefingPayload`), `body_md`.

**Why not a sentinel `entities` row (corp_code='00000000')?** Rejected — pollutes `entities`, needs a seed, and is semantically dishonest. The partial-CHECK + nullable approach is cleaner and keeps the analysis-card FK invariant intact.

**Downgrade footgun:** re-adding `corp_code NOT NULL` fails if any NULL-corp briefing rows exist. The 0009 `downgrade()` MUST `DELETE FROM decision_cards WHERE report_type IS NOT NULL` before `ALTER COLUMN corp_code SET NOT NULL`.

## Migration 0009 (research focus #1)

**Revision chain:** `revision = "0009"`, `down_revision = "0008"` (head is 0008 — `0008_phase03_mcp_surface.py:52-53`). Hand-written; `target_metadata=None` so NO autogenerate (`env.py:20`).

**Collision check:** `report_type`/`report_date` do NOT collide with any existing column. `status` is the lifecycle column (`active/superseded/invalidated`) — orthogonal to `report_type` (the card KIND). Confirmed by `grep report_type src/` (only docstrings + this phase). No existing `report_date`/`invalidated_at`.

**Recommended `upgrade()` body:**
```python
def upgrade() -> None:
    op.add_column("decision_cards", sa.Column("report_type", sa.Text, nullable=True))
    op.add_column("decision_cards", sa.Column("report_date", sa.Date, nullable=True))
    # Allow NULL corp_code for briefing rows (they have no single corp).
    op.alter_column("decision_cards", "corp_code", nullable=True)
    # Constrain report_type to the two known kinds (NULL = an analysis card).
    op.create_check_constraint(
        "ck_decision_cards_report_type", "decision_cards",
        "report_type IS NULL OR report_type IN ('daily_briefing','weekly_briefing')",
    )
    # PRESERVE the analysis-card invariant: a non-briefing row still requires corp_code.
    op.create_check_constraint(
        "ck_decision_cards_corp_or_report", "decision_cards",
        "report_type IS NOT NULL OR corp_code IS NOT NULL",
    )
    # Serve get_briefing's WHERE report_type=? AND report_date=? — partial index over
    # ONLY briefing rows (mirrors 0008's partial ix_notes_corp / ix_fundamentals_corp).
    op.create_index(
        "ix_decision_cards_report", "decision_cards",
        ["report_type", "report_date"],
        postgresql_where=sa.text("report_type IS NOT NULL"),
    )
```

**Recommended `downgrade()` body:**
```python
def downgrade() -> None:
    op.drop_index("ix_decision_cards_report", table_name="decision_cards")
    # NULL-corp briefing rows must go before restoring corp_code NOT NULL.
    op.execute("DELETE FROM decision_cards WHERE report_type IS NOT NULL")
    op.drop_constraint("ck_decision_cards_corp_or_report", "decision_cards", type_="check")
    op.drop_constraint("ck_decision_cards_report_type", "decision_cards", type_="check")
    op.alter_column("decision_cards", "corp_code", nullable=False)
    op.drop_column("decision_cards", "report_date")
    op.drop_column("decision_cards", "report_type")
```

**Index choice rationale (D-73 "indexed for date+type"):** `get_briefing`'s lookup is `WHERE report_type=:type AND report_date=:date` — equality on both columns → a composite `(report_type, report_date)` btree gives an exact index seek. The partial `WHERE report_type IS NOT NULL` keeps it small (only briefing rows) and follows the established 0008 partial-index style (`0008:94-99, 127-132`).

**`report_date` vs reusing an existing column (planner decision):** CONTEXT D-73 says "column" (singular). A single-column path would reuse `generated_at`/`as_of`, but both are `timestamptz` — exact-date matching needs a KST expression index `((generated_at AT TIME ZONE 'Asia/Seoul')::date)`, which is fragile and easy to get wrong. **Recommendation: add the dedicated `report_date DATE` column** (equality-matchable, timezone-safe). If the planner insists on one new column only, drop `report_date` and index `(report_type, generated_at)` with the KST expression — but flag the timezone risk.

## Change Detection & Enumeration (research focus #5)

### Diff baseline via the supersession chain (D-02) — CONFIRMED

`DecisionCard` has **no** `supersedes` field (`models.py:78-112` — not present), so `get_active` does NOT expose the prior pointer. But `walk_supersedes` follows the DB column `row.supersedes` directly (`store.py:242,246` select+follow), independent of the Pydantic model. The exact idiom:

```python
active = get_active(engine, corp_code)              # store.py:204 → current active DecisionCard | None
chain  = walk_supersedes(engine, active.card_id)    # store.py:219 → [active, prior, ..., oldest]
prior  = chain[1] if len(chain) >= 2 else None       # the immediately-prior card
```

Diff (all fields confirmed present):
- **stance flip:** `active.decision.stance` vs `prior.decision.stance` (`models.py:38`) → `'HOLD→SELL'`.
- **new contradiction:** `active.contradictions` vs `prior.contradictions` (`models.py:86`) — set delta. `Contradiction` fields are `bull/bear_evidence/bear_claim/resolution` (`models.py:57-65`); key each on `(bull, bear_claim)` (or the full tuple) for a deterministic delta → `'+2 contradictions'`.
- **conviction move:** `active.decision.conviction` vs `prior.decision.conviction` (`models.py:39`).
- **first-card (D-03):** `len(chain) == 1` AND `active.decision.conviction >= 0.8` → "new high-conviction"; `len(chain)==1` and `<0.8` → excluded (noise).

### GAP: no enumeration helper exists (NEW store code required)

`src/cards/store.py` exposes only `save_card`, `get_active(corp_code)`, `walk_supersedes(card_id)`, `invalidate` (`store.py:147/204/219/250`). There is **no "list all active cards" / "list cards changed on date D"**. Phase 5 MUST add a store enumeration helper. Recommended:

```python
def list_cards_for_briefing(engine, on_date: date) -> BriefingCandidates: ...
```
returning the collect-set for date D:
- **newly-generated/changed:** `WHERE (generated_at AT TIME ZONE 'Asia/Seoul')::date = :d` — a FULL debate writes a NEW row with `generated_at = datetime.now(_KST)` (`runner.py:190`). A REFRESH **preserves** `generated_at` (`gate.py:338-339` invariant) so it will NOT appear — correct, since a refresh is not a change.
- **expiring:** `WHERE (expires_at AT TIME ZONE 'Asia/Seoul')::date = :d AND status='active'`. Index `ix_decision_cards_expires` exists (`0007:142-146`).

### GAP: "invalidated today" has no timestamp

`invalidate()` sets `status='invalidated'` and writes `invalidation_reason` into payload via `jsonb_set` — but records **NO timestamp** (`store.py:117-125`, `_INVALIDATE_SQL`). So "invalidated on date D" is not directly queryable. Confirmed: `grep invalidated_at src/` → none.

**Options (planner decision — recommend one):**
- **(a) Minimal (recommended):** stamp `invalidated_at` into payload inside `invalidate()` via an additional `jsonb_set` (no new column). The daily enumeration scans `WHERE payload->>'invalidated_at' = :d` (or `::date` match). Card volume is low (one row per ticker per event), so a scan is fine. Keeps migration 0009 to `report_type`+`report_date` only.
- **(b) Clean:** add `invalidated_at TIMESTAMPTZ NULL` as a real column in 0009 (indexable). Costs a 3rd column but makes SC#1's "invalidated" collect-set a clean indexed query.
- **(c) Approximate:** treat "invalidated" as covered by the supersession diff only (a superseding card's `generated_at::date = D`). Misses explicit `invalidate()` calls (assumption-break invalidations) → **not recommended**, since redesign §5:454 explicitly says "invalidated cards surface in next briefing".

## Prioritization (research focus #6, D-01)

Sort key = `(held_rank, event_class_rank, -conviction)`, all deterministic:
- **held_rank (tier 1):** `0` if `card.ticker ∈ holdings_tickers` else `1`. Holdings only (D-01: "holdings always rank above watchlist"); watchlist is NOT held.
- **event_class_rank (tier 2):** `stance_flip=0 < new_contradiction=1 < expired_invalidated=2 < new_high_conviction=3`.
- **conviction (tier 3):** `card.decision.conviction` descending (`models.py:39`).

### Held-first graceful degradation (portfolio absent until Phase 6)

Portfolio membership comes from `list_portfolio()` → `PortfolioView.holdings` (`mcp_v2/tools/portfolio.py:32-58`), which loads `notes/private/portfolio.md` (`shared/portfolio.py:66-83`). **STATE.md:64 + runner.py:175-176** confirm `portfolio.md` is gitignored/absent; `currently_held` is `[ASSUMED]`-false until Phase 6.

**Degradation rule:** wrap the load in `try/except PortfolioLoadError` (raised when the file is missing — `shared/portfolio.py:74-75`; the MCP tool maps it to `DataBackendError` — `portfolio.py:46-47`). On failure OR empty holdings, treat `holdings_tickers = set()` → **every** card gets `held_rank = 1`, so tier-1 collapses to a no-op and sorting proceeds deterministically on tiers 2+3. **Never crash on missing portfolio.** All tiebreak fields (`stance`, `conviction`, `contradictions`, `status`, `expires_at`) exist on `DecisionCard` regardless.

**Recommendation:** `generate_daily_briefing` should call the store/`shared.portfolio` loader directly (or accept an injected `held_tickers: set[str]`) so tests can seed holdings without a real `portfolio.md`.

## Render — `body_md` table (SC#3, D-04/05/06)

Deterministic string assembly, **NO LLM** (D-06). Columns `종목 | 변화 | 근거 | 제안 | Why now | Why not`, one row per entry:
- **종목:** `card.ticker` (+ optional entity name).
- **변화:** the computed delta string (`HOLD→SELL`, `+2 contradictions`, `expired`, `new (conv 0.83)`).
- **근거:** leading supporting evidence — the top-weighted `key_claim.text` (or its evidence_ref). `KeyClaim` has `text`, `weight ∈ {HIGH,MEDIUM,LOW,CONTEXT}`, `confidence` (`models.py:45-54`).
- **제안 (D-05):** `f"{card.decision.stance} ({card.decision.conviction:.2f})"` — stance label + numeric conviction. NO freeform text (Veto #1).
- **Why now (D-06):** top-ranked `key_claim` (sort key_claims by weight HIGH>…>CONTEXT then confidence-desc; take `[0].text`).
- **Why not (D-06):** top-ranked `contradiction` (`card.contradictions[0].bear_claim` or `.bear_evidence`). If `contradictions == []`, render `—` (and note: an empty-contradiction card is already log-warned upstream, `runner.py:370-376`).

`payload` (JSONB) carries the structured `entries` (machine-readable, what `get_briefing` returns); `body_md` carries the human table. Both in the single row (SC#2), exactly like an analysis card's payload+body_md split.

## get_briefing Wiring (research focus #3)

Current scaffold: `get_briefing(date, type='daily')` validates `type ∈ {daily,weekly}` and returns `Briefing(found=False, entries=[])` (`briefing.py:26-46`). The `Briefing` model is `{date, type, found, entries: list[dict]}`, `extra='forbid'`, and has **NO `body_md` field** (`models.py:223-233`).

**Wiring:**
1. Map public `type` → stored `report_type`: `daily → 'daily_briefing'`, `weekly → 'weekly_briefing'`.
2. **SELECT must live in `cards.store`, NOT in the tool.** The SC#3 run-sql AST guard scans `src/mcp_v2` requiring every `text()` arg be a string constant, and `get_decision_card` already delegates all DB access to `store.get_active` with NO inline SQL (`card.py` docstring: "performs NO direct SQL"). Add `cards.store.get_briefing_row(engine, report_type, report_date) -> BriefingRow | None`:
   `SELECT payload, body_md FROM decision_cards WHERE report_type=:rt AND report_date=:d AND status='active' ORDER BY generated_at DESC LIMIT 1`.
3. Map into the return: `entries = row.payload["entries"]`; `found = row is not None`. Returns `Briefing(date, type, found=True, entries=[...])`.
4. **Date-match semantics:** match `report_date` (the dedicated DATE column) against the `date` param (parse/validate as ISO-8601 — currently echoed unparsed, `briefing.py:33`). This is the timezone-safe equality path (§Migration).
5. **The current SC#3 test WILL change:** `tests/mcp_v2/test_portfolio_briefing.py:96-132` asserts `briefing.py` does NOT reference `report_type` in code (the Phase-3 honest-empty guard). Phase 5 replaces this test with one asserting the delegated store query — flag it as an EXPECTED test change, not a regression.

### Veto #13 mirror — already satisfied by construction

`Briefing` has no `body_md` field (`models.py:223-233`), so `get_briefing` returns **entries only** (payload) — the full human table (`body_md`) stays in the DB row and is never shipped to context. This is "filter before context" for free; do NOT add a `body_md` field to `Briefing`. (A future `view="both"` opt-in could expose it, but SC#5 only requires readability — entries suffice.)

## Weekly Roll-Up (research focus #4, SC#4/D-07/D-08)

`src/briefing/weekly.py::generate_weekly_briefing(week_anchor)` writes a `report_type='weekly_briefing'` row, **pre-materialized** (computed once at generation; `get_briefing(type='weekly')` only SELECTs the stored row and returns `payload['entries']` — NEVER re-reads the 7 dailies — SC#4).

**`source_reports` pointer shape (payload field):**
```json
"source_reports": [
  {"date": "2026-07-07", "card_id": "brief_daily_2026-07-07"},
  ... up to 7 ...
]
```
`card_id` is the stable ref (decision_cards PK); `date` is human-readable. Found via `WHERE report_type='daily_briefing' AND report_date BETWEEN :week_start AND :week_end` (the new `ix_decision_cards_report` index).

**D-07 NET algorithm (deterministic read of the ≤7 daily payloads):**
1. Load each daily row's `payload["entries"]` for the week.
2. Group entries by ticker.
3. For each ticker: `start_state` = stance+conviction from the EARLIEST daily entry that week; `end_state` = the LATEST daily entry's stance+conviction (each daily entry already carries stance+conviction per D-05).
4. NET change = `start_stance != end_stance`, OR conviction moved beyond a threshold. `intra_week_events` = count of that ticker's daily entries.
5. **Drop** tickers where `start_state == end_state` (same stance AND conviction within threshold) — flip-flops (BUY→HOLD→BUY) net to no-change (D-07). The daily rows preserve the detail.
6. Surviving per-ticker NET entries are the weekly entries — still ≤10, priority-sorted (same D-01 key).

**D-08 coverage (payload field):** `"coverage": {"present": N, "expected": 7, "missing_dates": [...]}`. Roll up whatever exists; missing ≠ no-change; do NOT block on <7.

**Weekly row's own constraints:** same landmine — NULL `corp_code`, `report_type='weekly_briefing'`, needs `expires_at` (recommend `week_end + 7d`) and `report_date` (recommend `week_end`, the anchor the user queries with — small planner decision).

## No-Change Day (SC#6)

**Recommended (CONTEXT direction):** on an empty collect-set, STILL write a short `daily_briefing` row: `payload["entries"] = []` (or a single sentinel `{"note": "no significant changes today"}`), `body_md` = one line (`오늘 유의미한 변화 없음`). `get_briefing` then returns `found=True` with a real card — never `found=False`, never an empty page.

**"Significant change" threshold (recommended):** significance = membership in the 4 event classes (stance flip ∪ new contradiction ∪ expired/invalidated ∪ new high-conviction≥0.8). If the collect-set is empty, it's a no-change day. Conviction drift below a stance flip does NOT count (avoids noise). This is a clean, decomposable, deterministic threshold (Veto #4 spirit).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Prior-card lookup | A new snapshot table / yesterday-diff | `get_active` + `walk_supersedes` (`store.py:204,219`) | D-02 locks the supersession chain as the prior-state source; the pointer already exists |
| Briefing-row SQL in the tool | Inline `text()` in `briefing.py` | A `cards.store` helper | SC#3 AST guard forbids non-constant `text()` in `src/mcp_v2`; `get_decision_card` already delegates |
| Card serialization | A bespoke briefing serializer | Pydantic `model_dump(mode="json")` + JSONB TEXT-cast bind (`store.py:180,187`) | Datetimes serialize to ISO-8601 cleanly; the store pattern is proven |
| KST date boundaries | Naive `date.today()` | `datetime.now(ZoneInfo("Asia/Seoul"))` (`runner.py:72`, `gate.py:73`) | `generated_at`/`expires_at` are `timestamptz +09:00`; UTC `::date` is off for late-KST rows |

**Key insight:** Phase 5 is almost entirely *reuse* — the only genuinely new primitives are (1) migration 0009, (2) a `save_briefing`/`get_briefing_row`/`list_cards_for_briefing` store trio, and (3) the `src/briefing/` render logic. Everything else (diff, portfolio, KST math, JSONB round-trip) already exists.

## Common Pitfalls

### Pitfall 1: Reusing `DecisionCard`/`save_card` for a briefing row
**What goes wrong:** `IntegrityError` (corp_code NOT NULL / FK) or `ValidationError` (ticker/stance/assumptions required).
**Why:** the table + model were locked in Phase 2 for single-ticker analysis cards.
**How to avoid:** migration 0009 (nullable corp_code + partial CHECK) + a separate `BriefingRow` model + `save_briefing`.
**Warning sign:** any Phase-5 code importing `cards.models.DecisionCard` to build a briefing.

### Pitfall 2: `to_tsvector('korean', ...)` — does NOT exist in PG17
**What goes wrong:** migration hard-fails.
**Why:** PG17 ships no `korean` config (`0007:36-41`, `0008:35-38`). The GENERATED `body_tsv` already uses `'simple'`.
**How to avoid:** Phase 5 does NOT add tsvector columns; the briefing `body_md` reuses the existing `'simple'` GENERATED column automatically. Do not touch it.

### Pitfall 3: `generated_at::date` timezone drift
**What goes wrong:** a briefing generated at 08:00 KST July-15 (= 23:00 UTC July-14) matches the WRONG date under a UTC `::date`.
**How to avoid:** use the dedicated `report_date DATE` column for the lookup, and compute enumeration dates with `AT TIME ZONE 'Asia/Seoul'`.

### Pitfall 4: Weekly recompute-on-read
**What goes wrong:** `get_briefing(weekly)` re-reads the 7 dailies each call — violates SC#4, non-deterministic if dailies change.
**How to avoid:** materialize `entries` INTO the weekly row's payload at generation; the read is a pure SELECT.

### Pitfall 5: "Invalidated today" silently missing from the collect-set
**What goes wrong:** `invalidate()` has no timestamp, so explicit invalidations never surface in the daily.
**How to avoid:** pick one of the §"invalidated today" options (recommend stamping `invalidated_at` into payload).

## Runtime State Inventory

> Phase 5 is a greenfield feature (new `src/briefing/`) plus an **additive** migration. It is NOT a rename/refactor. No stored strings are renamed. The inventory below confirms nothing carries stale runtime state.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None renamed. Migration 0009 ADDS columns (`report_type`/`report_date`) — all existing rows get NULL (analysis cards). Verified: `0007` has no such columns. | none (additive) |
| Live service config | None — no external service holds a "briefing" string. Scheduling is Phase 9 (deferred). | none |
| OS-registered state | None — no Task Scheduler / systemd unit in this phase (deferred to Phase 9). | none |
| Secrets/env vars | None — briefing reads no secrets. `DATABASE_URL` unchanged. | none |
| Build artifacts | None — no package rename. | none |

## Code Examples

### Diff a card against its prior (D-02)
```python
# Source: cards/store.py:204,219 (get_active, walk_supersedes)
active = get_active(engine, corp_code)                 # DecisionCard | None
if active is not None:
    chain = walk_supersedes(engine, active.card_id)    # [active, prior, ...]
    prior = chain[1] if len(chain) >= 2 else None
    stance_flip = prior is not None and active.decision.stance != prior.decision.stance
    new_contradictions = _contradiction_delta(active.contradictions,
                                              prior.contradictions if prior else [])
    is_new_high_conv = prior is None and active.decision.conviction >= 0.8  # D-03
```

### Migration up/down roundtrip test (established pattern)
```python
# Source: tests/conftest.py:58-81 + tests/test_migration.py (command.upgrade)
from alembic import command
from alembic.config import Config
cfg = Config("src/db/alembic.ini"); cfg.set_main_option("sqlalchemy.url", url)
command.upgrade(cfg, "0009")     # report_type/report_date present, corp_code nullable
command.downgrade(cfg, "0008")   # columns gone, corp_code NOT NULL restored
```

## State of the Art

| Old Approach | Current Approach | When | Impact |
|--------------|------------------|------|--------|
| Per-ticker dump report | Change-only top-N (≤10) digest | v2.0 redesign §5 (AlphaSense Workflow Agent + Bloomberg AI Summary) | SC forbids a 7-day union; weekly is NET change per ticker |
| Markdown vault as source of truth | Postgres `decision_cards` rows | 2026-04 shutdown | Briefing is a DB row, not a `.md` file (Veto #9) |

**Deprecated/outdated:** the Phase-3 honest-empty `get_briefing` (`briefing.py`) and its `report_type`-absence guard test (`test_portfolio_briefing.py:96-132`) are superseded by Phase 5 wiring — an EXPECTED change, not a regression.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `report_date DATE` (2nd column) is the right date-match design vs a single-column KST-expression index | Migration 0009 | If planner mandates one column only, use `(report_type, generated_at)` + KST expression index (timezone care needed) |
| A2 | Stamping `invalidated_at` into payload (no column) is sufficient for "invalidated today" enumeration | Change Detection | If card volume grows large, the payload scan is slow → prefer a real indexed column (option b) |
| A3 | Weekly `report_date` = `week_end` (Friday/anchor) is what `get_briefing(date,'weekly')` is called with | Weekly Roll-Up | If callers pass `week_start`, the lookup misses — confirm the query convention |
| A4 | No-change significance = membership in the 4 event classes (conviction-only drift excluded) | No-Change Day | If a conviction jump should count, the threshold widens — a Discretion item |
| A5 | Contradiction identity key = `(bull, bear_claim)` for the set-delta | Change Detection | A poor key double-counts or misses "+N contradictions"; confirm with real cards |
| A6 | Weekly per-ticker start/end state is read from daily `entries` (which carry stance+conviction) | Weekly Roll-Up | If dailies don't persist per-entry stance+conviction in payload, weekly can't compute NET — the daily payload schema MUST include them |

## Open Questions

1. **Invalidated-today detection** — `invalidate()` records no timestamp (`store.py:117-125`).
   - Known: `status='invalidated'` + `invalidation_reason` in payload.
   - Unclear: when it happened.
   - Recommendation: stamp `invalidated_at` into payload (minimal) or add a column (clean). Planner picks.
2. **One new column vs two** — D-73 says "column" (singular); this research recommends `report_type` + `report_date`.
   - Recommendation: two columns (timezone-safe). If constrained to one, use the KST-expression index and accept the footgun risk.
3. **Daily payload entry schema** — the weekly NET algorithm (D-07) requires each daily `entry` to carry `ticker`, `stance`, `conviction`, `event_class`, and the delta string. The planner must lock the `entries[]` payload schema in the daily so the weekly can read it. (A6.)

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker + PG17 image `tensorchord/vchord-suite:pg17-latest` | testcontainers `pg_engine` fixture (migration + store tests) | Assumed ✓ (used by all prior phases — `conftest.py:62-63`) | pg17-latest | none — tests need it (same as Phases 1-4) |
| Alembic | migration 0009 | ✓ (`pyproject.toml:44`) | >=1.18,<2 | — |
| Local Postgres (`docker compose up -d postgres`) | live `generate_daily_briefing` runs | dev-machine dependent | — | tests use testcontainers, not the compose DB |

**No NEW external dependencies.** All required tooling is already exercised by Phases 1-4.

## Validation Architecture

> `workflow.nyquist_validation = true` in `.planning/config.json` — this section is REQUIRED.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest `>=9.0` (`pyproject.toml:63`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths=["tests"]`, `pythonpath=["src"]` (`:71-73`); markers `slow/e2e/db/live` (`:74-79`) |
| DB fixtures | `pg_engine` (session, runs `alembic upgrade head` once — `conftest.py:51-86`), `pg_clean` (function, TRUNCATE incl. `decision_cards` — `conftest.py:97-145`), `seeded_engine` (삼성전자/005930 — `tests/cards/conftest.py:101-124`) |
| Quick run command | `uv run pytest tests/briefing -x` |
| Full suite command | `uv run pytest` |
| Migration roundtrip | `alembic.command.upgrade/downgrade` against testcontainers (pattern: `conftest.py:58-81`, `tests/test_migration.py`) |

### Phase Requirements → Test Map
| Req | Behavior (deterministic property to assert) | Test Type | Automated Command | File Exists? |
|-----|---------------------------------------------|-----------|-------------------|-------------|
| SC#1 | >10 candidate events → exactly 10 entries (truncation) | unit | `uv run pytest tests/briefing/test_daily.py::test_truncates_to_ten -x` | ❌ Wave 0 |
| SC#1/D-01 | Fixed input → fixed priority order (held→event-class→conviction-desc) | unit | `pytest tests/briefing/test_priority.py -x` | ❌ Wave 0 |
| SC#1/D-01 | Missing `portfolio.md` → no crash, held-tier collapses, order still deterministic | unit | `pytest tests/briefing/test_priority.py::test_no_portfolio -x` | ❌ Wave 0 |
| SC#1/D-02 | HOLD→SELL across a superseded chain detected as stance-flip via `get_active`+`walk_supersedes` | integration(db) | `pytest tests/briefing/test_diff.py -x` | ❌ Wave 0 |
| SC#1/D-03 | First card conv≥0.8 included; first card <0.8 excluded | unit | `pytest tests/briefing/test_diff.py::test_first_card_rule -x` | ❌ Wave 0 |
| SC#2 | NULL-corp briefing row INSERTs OK; analysis card with NULL corp REJECTED by partial CHECK | integration(db) | `pytest tests/briefing/test_store_briefing.py -x` | ❌ Wave 0 |
| SC#2 | migration 0009 up→down roundtrip (columns/CHECKs/index add+drop; corp_code NOT NULL restored) | integration(db) | `pytest tests/db/test_migration_0009.py -x` | ❌ Wave 0 |
| SC#3 | `body_md` has header `종목 \| 변화 \| 근거 \| 제안 \| Why now \| Why not`; 제안 = stance+conviction, no forecast text | unit | `pytest tests/briefing/test_render.py -x` | ❌ Wave 0 |
| SC#4 | `get_briefing(weekly)` returns the stored row unchanged after the 7 dailies are mutated/deleted (proves no recompute) | integration(db) | `pytest tests/briefing/test_weekly.py::test_no_recompute -x` | ❌ Wave 0 |
| SC#4/D-07 | Flip-flop BUY→HOLD→BUY nets to no-change (dropped); genuine start≠end retained | unit | `pytest tests/briefing/test_weekly.py::test_net_change -x` | ❌ Wave 0 |
| SC#4/D-08 | 5 present / 2 missing dailies → `coverage: 5/7`, missing ≠ no-change | unit | `pytest tests/briefing/test_weekly.py::test_coverage -x` | ❌ Wave 0 |
| SC#5 | `get_briefing('daily')` reads `daily_briefing` row → found=True, entries populated; invalid type → InvalidArgument | integration(db) | `pytest tests/mcp_v2/test_briefing_wired.py -x` | ❌ Wave 0 |
| SC#5/Veto#13 | `get_briefing` returns entries only (Briefing model has no body_md field) | unit | `pytest tests/mcp_v2/test_briefing_wired.py::test_no_body_leak -x` | ❌ Wave 0 |
| SC#6 | Empty collect-set → short row written; `get_briefing` returns found=True (NOT found=False, NOT empty page) | integration(db) | `pytest tests/briefing/test_daily.py::test_no_change_writes_short_row -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/briefing -x` (+ the touched `tests/mcp_v2`/`tests/db` file).
- **Per wave merge:** `uv run pytest` (full suite, testcontainers Postgres).
- **Phase gate:** full suite green before `/gsd:verify-work`.

### Wave 0 Gaps
- [ ] `tests/briefing/__init__.py` + `tests/briefing/conftest.py` — seed **multiple** entities + cards (the existing `seeded_engine` seeds only 삼성전자/005930; truncation + multi-ticker priority need ≥11 tickers with active cards + superseded chains).
- [ ] `tests/db/test_migration_0009.py` — up/down roundtrip + partial-CHECK behavior.
- [ ] `tests/briefing/test_{daily,weekly,diff,priority,render,store_briefing}.py` — per the map above.
- [ ] `tests/mcp_v2/test_briefing_wired.py` — replaces the Phase-3 `test_portfolio_briefing.py:96-132` honest-empty guard (EXPECTED change).
- [ ] No framework install needed — pytest + testcontainers already present.

## Security Domain

> `security_enforcement` key absent in `.planning/config.json` → treated as enabled. This phase has a narrow surface (DB reads/writes + two string params to `get_briefing`); most ASVS categories are N/A.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | no auth surface (internal MCP tool) |
| V3 Session Management | no | — |
| V4 Access Control | no | `get_note` whitelist already covers file reads; briefing reads only `decision_cards` |
| V5 Input Validation | yes | `get_briefing` validates `type ∈ {daily,weekly}` (`briefing.py:43-44`); ADD ISO-8601 validation of `date` before it reaches the `report_date` bind |
| V6 Cryptography | no | no crypto |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via `date`/`type` params | Tampering | Parameterized `text()` constants only (Veto #7); the SC#3 AST guard enforces string-constant `text()` args in `src/mcp_v2`; all briefing SQL lives in `cards.store` bound by params |
| Prompt injection through briefing `body_md`/entries | Tampering/Info-disclosure | Briefing content is DERIVED from already-wrapped card fields; `get_briefing` returns structured `entries` (no raw narrative body) — Veto #13 filter-before-context by construction |
| Malformed payload reaching storage | Tampering | `BriefingRow` Pydantic `extra='forbid'`; JSONB TEXT-cast bind (`store.py:187`) prevents datetime corruption |

## Sources

### Primary (HIGH confidence — codebase file:line)
- `src/db/migrations/versions/0007_decision_cards.py:76-164` — the 12 locked columns, `corp_code NOT NULL` FK, status CHECK, indexes, `body_tsv` GENERATED (`'simple'`).
- `src/db/migrations/versions/0008_phase03_mcp_surface.py:52-53,94-99,127-132` — head revision + partial-index style precedent.
- `src/db/migrations/env.py:20` — `target_metadata=None` (hand-written only).
- `src/cards/store.py:69-278` — `save_card`/`get_active`/`walk_supersedes`/`invalidate`; INSERT SQL; no enumeration helper; no invalidated timestamp.
- `src/cards/models.py:33-112` — `DecisionCard` required fields (corp_code/ticker/decision/assumptions/expires_at).
- `src/mcp_v2/tools/briefing.py:26-51` + `src/mcp_v2/models.py:223-233` — honest-empty scaffold + `Briefing` model (no body_md field).
- `src/mcp_v2/tools/card.py` (docstring) — the "delegate SQL to store, no inline `text()`" pattern (SC#3 AST guard).
- `src/analysis/runner.py:155-226,190` + `src/analysis/gate.py:323-396` (esp. 338-339) — FULL writes new `generated_at`; REFRESH preserves it.
- `src/shared/portfolio.py:66-83` + `src/mcp_v2/tools/portfolio.py:32-58` — portfolio load + `PortfolioLoadError`→`DataBackendError`.
- `tests/conftest.py:51-145` + `tests/cards/conftest.py:101-124` + `tests/test_migration.py` — fixtures + migration test pattern.
- `pyproject.toml:44-79` — deps + pytest config + markers.
- `.planning/research/redesign-2026-05.md:430-439,454` — §5 briefing rationale (change-only, ≤10, weekly aggregation, invalidated cards surface).
- `.planning/ROADMAP.md:183-208` — Phase 5 SC#1-6.
- `.planning/STATE.md:64,214` — portfolio.md absent; `currently_held` [ASSUMED] until Phase 6.

### Secondary
- `grep report_type/invalidated_at src/` — confirmed no existing collision, no invalidation timestamp.

### Tertiary
- none — no WebSearch needed (internal-contract phase).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new deps; all from `pyproject.toml`.
- Architecture / landmine: HIGH — constraints quoted from migration + model source.
- Migration shape: HIGH — mirrors 0007/0008 established patterns; roundtrip testable.
- Pitfalls: HIGH — each grounded in a specific file:line.
- Invalidated-today / column-count: MEDIUM — genuine open design choices flagged (A1/A2, OQ1/OQ2).

**Research date:** 2026-07-14
**Valid until:** 2026-08-13 (stable internal contract; re-check only if migration 0009 or `cards.store` changes before planning).
