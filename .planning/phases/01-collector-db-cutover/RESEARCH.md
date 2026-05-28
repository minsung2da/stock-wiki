# Phase 1 Research — Collector DB-Direct Cutover

**Researched:** 2026-05-29
**Domain:** Postgres-direct collector rewrite (DART/KRX/news/macro/KIND → typed domain tables)
**Confidence:** HIGH on schema + ordering; MEDIUM on observability replacement (Phase 9 still TBD)

## Summary

Phase 1 retires the Markdown-vault intermediate layer and writes collector output
directly to Postgres. The schema sketch in `redesign-2026-05.md` §2 is sound but
needs concretization on column types, dedup keys, and FK directions. Five domain
tables (`filings`, `news`, `ohlcv`, `macro_series`, `events`) replace the single
generic `documents` table. Hard Veto #6 (no numeric embeddings) splits the tables
cleanly: only `filings` and `news` carry `body_md`/`body_tsv`/`body_embedding`;
`ohlcv`/`macro_series`/`events` are pure typed columns. Hard Veto #8 (no DART
pre-chunking) means `filings.body_md` is whole-filing TEXT — no `chunks` writes
in Phase 1. Hard Veto #9 (no vault revival) forces removal of `writer.py` files,
not just `vault_root` arguments.

**Primary recommendation:** One migration `0006` creates all five domain tables
plus a `collector_runs` observability table; legacy `documents`/`chunks` are
**left dormant** (option B, see Q3); five collectors refactored in order
**macro → krx → kind → news → dart** (simplest narrative-free first).

## User Constraints (from CONTEXT.md)

### Locked Decisions

- 5 collectors target their own tables: `dart→filings`, `krx→ohlcv`,
  `news→news`, `macro→macro_series`, `kind→events`.
- content-hash dedup pattern preserved (UPSERT ON CONFLICT).
- `src/shared/heartbeat.py` no-op stub deleted; runtime stats land in
  structured stderr logs.
- `--vault-root` removed from every CLI subcommand.
- `tests/collectors/` migrated from path-based to DB-based assertions.
- `stock-enrich-daily` Routine already disabled — no action required.

### Claude's Discretion

- Exact column types, indexes, constraints (Q1).
- Dedup-key shape per table (Q2).
- Legacy `documents`/`chunks` disposition (Q3 — recommend Option B).
- Migration granularity (Q4 — recommend single 0006).
- Observability replacement (Q5 — recommend structured log + `collector_runs` row).
- CLI report shape (Q6).
- Test infra: testcontainer parity vs sqlite (Q7).
- Refactor order (Q8 — recommend macro→krx→kind→news→dart).
- vault/raw/ regeneration guard (Q9 — recommend physical deletion + import-error).

### Deferred Ideas (OUT OF SCOPE)

- `decision_cards` table (Phase 2).
- `chunks`/HNSW/BM25 rebuild (Phase 3).
- bge-m3 embedding population for `filings.body_md` / `news.body_md`
  (Phase 3 — leave columns NULLable in 0006, populated by Phase 3 pipeline).
- MCP server, briefing renderer, action layer, eval harness.

## Project Constraints (from CLAUDE.md)

- **Hard Vetoes 6, 8, 9** are load-bearing for Phase 1 schema.
- `src/collectors/` must remain free of `anthropic`/`openai` imports
  (CI guard `tests/test_import_guard.py`). Phase 1 adds no LLM calls.
- All heavy deps (`sentence-transformers`, `mecab-ko`) MUST be lazy-imported;
  Phase 1 does not import them at all.
- Korean comments OK; PR titles use English prefix (`feat:`, `refactor:`).
- Logs are structured `logging.info(extra={...})` to stderr; CLI stdout
  remains JSON.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SC-1 | DART collector INSERT into `filings`, no `vault/raw/` | Q1 schema, Q8 order |
| SC-2 | KRX/news/macro/kind INSERT with UPSERT dedup | Q1 (5 tables), Q2 (dedup keys) |
| SC-3 | `heartbeat.py` deleted, structured logging only | Q5 |
| SC-4 | `--vault-root` removed from CLI | Q6 |
| SC-5 | `tests/collectors/` validates DB paths | Q7 |
| SC-6 | `stock-enrich-daily` Routine — no action | n/a |

## Standard Stack (carry-over from v1.0)

| Library | Version | Purpose | Phase 1 use |
|---|---|---|---|
| SQLAlchemy | 2.0 | ORM + Core | unchanged engine.py |
| Alembic | 1.18 | migrations | adds 0006 |
| psycopg | 3.2 | DB driver | unchanged |
| pgvector | 0.8 | `halfvec(1024)` columns | declared in `filings`/`news`, populated Phase 3 |
| dart-fss | 0.4.x | DART API | filing fetch unchanged |
| pykrx | 1.0.50+ | KRX OHLCV/flow/short | unchanged |
| trafilatura | 1.12+ | news body extraction | unchanged |
| PublicDataReader | latest | ECOS | unchanged |
| fredapi | 0.5+ | FRED | unchanged |
| tenacity | 9.0 | transient retry | unchanged |
| testcontainers | 4.8 | Postgres test container | unchanged |

No new deps required for Phase 1. `tabulate` (used only by `krx/writer.py` for
`pandas.to_markdown`) can be dropped from `[dependency-groups.collectors]` once
the writer is removed.

## Architecture Patterns

### Data flow (Phase 1 end state)

```
External APIs ──> collectors.{dart,krx,news,macro,kind}.*
                            │
                            │  (no Markdown intermediate)
                            ▼
                  SQLAlchemy Core insert/upsert
                            │
                            ▼
                  Postgres (entities ← FK from filings/news/ohlcv/events;
                            macro_series independent)
                            │
                            ▼
                  collector_runs (one row per `stock collect <src>` invocation)
                            │
                            ▼
                  structured stderr logs (logging.info extra=…)
```

### Component responsibilities

| File | Phase 0 role | Phase 1 role |
|---|---|---|
| `collectors/<src>/__init__.py` | orchestrate fetch → writer → heartbeat | orchestrate fetch → `db_writer.upsert_<src>` |
| `collectors/<src>/writer.py` | render Markdown + write file | **DELETED** |
| `collectors/<src>/db_writer.py` | (new) | typed INSERT/UPSERT helpers per table |
| `collectors/<src>/fetcher.py`, `client.py` | upstream API wrappers | unchanged |
| `shared/heartbeat.py` | no-op stub | **DELETED** |
| `shared/frontmatter.py` | Pydantic frontmatter models | left dormant for Phase 3 (notes still uses) |
| `shared/content_hash.py` | sha256 normalize | retained — used for `news.body_md` dedup |
| `cli/__main__.py`, `cli/commands.py` | argparse + `_dispatch` | `--vault-root` removed; stats JSON shape changes |

## Q1 — Domain Table Schemas

### `filings` (DART; narrative — Veto #6/#8 apply)

```sql
CREATE TABLE filings (
  rcept_no       CHAR(14)      PRIMARY KEY,           -- DART receipt no (14 digits)
  corp_code      CHAR(8)       NOT NULL
                               REFERENCES entities(corp_code) ON DELETE CASCADE,
  ticker         CHAR(6)       NULL,                  -- snapshot at fetch
  filed_at       TIMESTAMPTZ   NOT NULL,              -- from rcept_dt + KST close
  report_nm      TEXT          NOT NULL,
  pblntf_ty      CHAR(1)       NOT NULL,              -- A|B|I (Phase 1: A,B; KIND uses I)
  event_type     TEXT          NULL,                  -- KIND classifier; NULL for plain A/B
  source_url     TEXT          NOT NULL,
  content_hash   CHAR(64)      NOT NULL,              -- sha256(normalize_body(body_md))
  body_md        TEXT          NOT NULL,              -- WHOLE filing (Veto #8)
  body_tsv       tsvector      NULL,                  -- populated Phase 3
  body_embedding halfvec(1024) NULL,                  -- populated Phase 3 (bge-m3)
  fetched_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
  first_seen_at  TIMESTAMPTZ   NOT NULL DEFAULT now(),
  last_seen_at   TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX ix_filings_corp_filed ON filings (corp_code, filed_at DESC);
CREATE INDEX ix_filings_pblntf_ty  ON filings (pblntf_ty);
CREATE INDEX ix_filings_event_type ON filings (event_type) WHERE event_type IS NOT NULL;
```

KIND `pblntf_ty="I"` filings go into `filings` (not `events`) because they're
DART filings with a `rcept_no`. `events` (below) carries the KIND classification
join row that points back via `source_id = rcept_no`. This avoids data
duplication — every KIND event row references a real filing.

### `news` (narrative; Veto #6/#9)

```sql
CREATE TABLE news (
  id             BIGSERIAL    PRIMARY KEY,
  url_hash       CHAR(64)     NOT NULL UNIQUE,        -- sha256(url) — stable dedup key
  url            TEXT         NOT NULL,
  outlet         TEXT         NOT NULL,               -- hankyung | edaily | …
  corp_code      CHAR(8)      NULL                    -- primary ticker (first match)
                              REFERENCES entities(corp_code) ON DELETE SET NULL,
  tickers        TEXT[]       NOT NULL DEFAULT '{}',  -- all matched tickers (Pitfall: array)
  published_at   TIMESTAMPTZ  NOT NULL,
  title          TEXT         NOT NULL,
  content_hash   CHAR(64)     NOT NULL,               -- sha256(normalize_body(title||body))
  body_md        TEXT         NOT NULL,               -- 2-paragraph cap retained (D-13)
  body_tsv       tsvector     NULL,                   -- Phase 3
  body_embedding halfvec(1024) NULL,                  -- Phase 3
  license_flag   TEXT         NOT NULL DEFAULT 'summary_only',
  fetched_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
  first_seen_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
  last_seen_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ix_news_corp_pub  ON news (corp_code, published_at DESC);
CREATE INDEX ix_news_outlet    ON news (outlet, published_at DESC);
CREATE INDEX ix_news_tickers   ON news USING GIN (tickers);
```

`url_hash` (full sha256 over canonical URL) replaces the v1.0 8-char `url_hash8`
in path layout. Use a full hash; collisions at 8 chars are not zero. The
`tickers TEXT[]` column captures all alias-matched tickers (v1.0 stored
`ProvenanceBlock.tickers` as a list — same idea, but GIN-indexed for
"news mentioning 005930" queries.

### `ohlcv` (numeric; Veto #6)

```sql
CREATE TABLE ohlcv (
  ticker         CHAR(6)      NOT NULL,
  trade_date     DATE         NOT NULL,
  open           NUMERIC(18,4) NOT NULL,
  high           NUMERIC(18,4) NOT NULL,
  low            NUMERIC(18,4) NOT NULL,
  close          NUMERIC(18,4) NOT NULL,
  volume         BIGINT        NOT NULL,
  trading_value  BIGINT        NULL,
  foreign_net    BIGINT        NULL,                  -- 외국인 순매수 (KRW)
  inst_net       BIGINT        NULL,                  -- 기관합계 순매수
  retail_net     BIGINT        NULL,                  -- 개인 순매수
  short_volume   BIGINT        NULL,                  -- T+2 lag — often NULL on fetch
  short_balance  BIGINT        NULL,
  corp_code      CHAR(8)       NULL                   -- denormalized for FK join speed
                               REFERENCES entities(corp_code) ON DELETE SET NULL,
  fetched_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
  PRIMARY KEY (ticker, trade_date)
);
CREATE INDEX ix_ohlcv_date ON ohlcv (trade_date DESC);
CREATE INDEX ix_ohlcv_corp ON ohlcv (corp_code, trade_date DESC) WHERE corp_code IS NOT NULL;
```

No `body_md`, no embedding. `NUMERIC(18,4)` accommodates Korean prices
(KRX max close ~3,000,000원, no decimals; using 4 decimals leaves room for
ETF NAV with sub-won precision). `BIGINT` is mandatory for `trading_value`
and net-flow columns — they exceed INT4 routinely (`외국인 순매수` of a
mega-cap can be 1조원 = 10^12).

### `macro_series` (numeric; Veto #6)

```sql
CREATE TABLE macro_series (
  source         TEXT          NOT NULL,              -- 'ecos' | 'fred'
  series_id      TEXT          NOT NULL,              -- ECOS 통계표코드 / FRED series id
  item_code      TEXT          NULL,                  -- ECOS ITEM_CODE1; NULL for FRED
  obs_date       DATE          NOT NULL,
  value          NUMERIC(20,6) NOT NULL,
  unit           TEXT          NULL,
  label          TEXT          NOT NULL,              -- catalog label (denorm for ops)
  cycle          CHAR(1)       NOT NULL DEFAULT 'D',  -- D|M|Q|Y
  fetched_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
  PRIMARY KEY (source, series_id, item_code, obs_date),
  CHECK (source IN ('ecos','fred'))
);
CREATE INDEX ix_macro_obs ON macro_series (obs_date DESC);
```

`item_code` is NOT NULL-able in the PK because ECOS series can have multiple
`ITEM_CODE1` values under one `series_id` (v1.0 fetcher.py filters by this).
Use empty string `''` for FRED (PK requires non-NULL). Add a CHECK if you
want stricter — but a default of `''` for FRED is simplest.

### `events` (KIND classifier — Veto #6)

```sql
CREATE TABLE events (
  id             BIGSERIAL    PRIMARY KEY,
  event_type     TEXT         NOT NULL,               -- KindEventType enum
  ticker         CHAR(6)      NOT NULL,
  event_date     DATE         NOT NULL,
  corp_code      CHAR(8)      NULL
                              REFERENCES entities(corp_code) ON DELETE SET NULL,
  subtype        TEXT         NULL,
  reason         TEXT         NOT NULL DEFAULT '',
  source         TEXT         NOT NULL,               -- 'dart' (pblntf_ty=I) | 'kind'
  source_id      TEXT         NULL,                   -- DART rcept_no when source='dart'
  source_url     TEXT         NOT NULL,
  filing_rcept_no CHAR(14)    NULL
                              REFERENCES filings(rcept_no) ON DELETE SET NULL,
  fetched_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
  UNIQUE (event_type, ticker, event_date, source, source_id)
);
CREATE INDEX ix_events_ticker_date ON events (ticker, event_date DESC);
CREATE INDEX ix_events_type_date   ON events (event_type, event_date DESC);
CHECK (event_type IN ('suspension','watchlist_designation','investment_caution',
                      'investment_risk','unfaithful_disclosure'));
```

Note the FK to `filings.rcept_no` — when `source='dart'`, the classifier row
also points at the underlying filing. This is the v2.0 win: KIND
`pblntf_ty="I"` filings appear *both* in `filings` (raw body) and in `events`
(structured classification), joined by `rcept_no`.

### `collector_runs` (observability — replaces heartbeat)

```sql
CREATE TABLE collector_runs (
  id             BIGSERIAL    PRIMARY KEY,
  source         TEXT         NOT NULL,               -- dart|krx|news|macro|kind
  run_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
  elapsed_ms     INTEGER      NOT NULL,
  stats          JSONB        NOT NULL,               -- {total,succeeded,skipped,failed[]}
  extra          JSONB        NULL                    -- per-source: revisions[], parse_error, etc.
);
CREATE INDEX ix_collector_runs_source_time ON collector_runs (source, run_at DESC);
```

This is the **dual-write** answer to Q5: collector ends emit a row here AND
a structured stderr log line. Phase 9's ops dashboard queries `collector_runs`;
real-time observers tail stderr.

## Q2 — Dedup Strategy

| Table | Dedup key | UPSERT shape |
|---|---|---|
| `filings` | `rcept_no` (PK, naturally unique per DART) | `ON CONFLICT (rcept_no) DO UPDATE SET body_md=…, content_hash=…, last_seen_at=now() WHERE filings.content_hash <> EXCLUDED.content_hash` |
| `news` | `url_hash` (UNIQUE) | `ON CONFLICT (url_hash) DO UPDATE SET last_seen_at=now() WHERE news.content_hash = EXCLUDED.content_hash; …else update body` |
| `ohlcv` | `(ticker, trade_date)` (PK) | `ON CONFLICT (ticker, trade_date) DO UPDATE SET short_volume=COALESCE(EXCLUDED.short_volume, ohlcv.short_volume), …` (T+2 fill-in pattern) |
| `macro_series` | `(source, series_id, item_code, obs_date)` (PK) | `ON CONFLICT … DO UPDATE SET value=EXCLUDED.value, fetched_at=now() WHERE macro_series.value <> EXCLUDED.value` (R-06 revision semantics) |
| `events` | `(event_type, ticker, event_date, source, source_id)` (UNIQUE) | `ON CONFLICT … DO NOTHING` — events are immutable classifications |

The v1.0 `documents.source_urls` array (`ARRAY(sa.Text)`) was a hack to dedupe
duplicate-body articles from multiple URLs. We **do not carry it forward**.
News dedupes on `url_hash` (one row per URL). If two URLs share a body that's
a fact about the source ecosystem, not something we should hide. The Phase 3
narrative-search layer will surface near-duplicates via embedding similarity,
which is the right place.

content-hash is retained as a **change detector** on `filings`/`news`: same
`rcept_no`/`url_hash` with the same `content_hash` = idempotent no-op (only
`last_seen_at` bumps); different `content_hash` = body changed, UPDATE.
Pyt's content-hash defined as `sha256(normalize_body(body_md))` using
existing `shared.content_hash.normalize_body` — no new code needed.

## Q3 — Legacy `documents` / `chunks` Disposition

**Recommendation: Option B (leave dormant).** Don't DROP, don't rename.

Rationale:

1. `entities` and `entity_aliases` are still active (used by `news.matcher`,
   `krx.collect`, `kind.collect`). They live in the same schema. A `DROP TABLE
   documents CASCADE` would have to walk all FKs — `events.document_id FK
   documents.id` is the only one currently pointing in. Cleaner to leave the
   old tables empty.
2. Phase 3 (MCP read-side) will rebuild a narrative-search layer. Whether it
   reuses `chunks` (re-purposing as `filings_chunks` / `news_chunks`) or
   creates new sibling tables (`filings.body_md` + materialized HNSW on
   `body_embedding` halfvec — preferred per `redesign-2026-05.md` §2) is a
   Phase 3 decision. Leaving the table shape intact buys flexibility.
3. Rename (Option C) would invalidate the existing `ix_chunks_embedding_hnsw`
   HNSW index recreation cost on next Phase 3 deploy — pointless. Empty
   tables cost nothing.

Migration 0006 explicitly does NOT touch `documents`, `chunks`, `edges`, or
`events_legacy`. (Note: the existing `events` table from 0001 conflicts in
name with our new `events` — see Q4.)

## Q4 — Migration Order

**Recommendation: single migration 0006 with one careful name collision.**

The blocker: migration 0001 already created an `events` table with shape
`(id, event_type, occurred_at, corp_code, document_id, payload JSONB)`. Our
new `events` table for KIND classifier rows has a different shape. Two
options:

A. **Rename the new table** to `kind_events` — clean but loses the §2
   schema sketch's naming.
B. **Rename the old table** to `events_legacy` in 0006, then create the
   new `events`. Old table is empty (no collector writes it post-shutdown)
   so rename is zero-risk.

**Pick B.** The §2 sketch and ROADMAP both say `events`; matching named
intent is worth a 1-line `ALTER TABLE events RENAME TO events_legacy`.
v1.0 had no live data in `events` post-shutdown (verified by inspecting
collectors — none populate it; only `src/ingest/` did, which is deleted).

Migration 0006 outline:

1. `ALTER TABLE events RENAME TO events_legacy` (preserve FK paths just in case).
2. `CREATE TABLE filings (…)` — full DDL above.
3. `CREATE TABLE news (…)`.
4. `CREATE TABLE ohlcv (…)`.
5. `CREATE TABLE macro_series (…)`.
6. `CREATE TABLE events (…)` — fresh, the KIND classifier shape.
7. `CREATE TABLE collector_runs (…)`.

Testcontainer parity: `tests/conftest.py::pg_engine` uses
`tensorchord/vchord-suite:pg17-latest` and runs `alembic upgrade head`.
Migration 0006 just works there. Update `_PHASE2_TABLES` in `pg_clean`
fixture to include the new tables (plus `events_legacy`) for TRUNCATE
between tests.

## Q5 — Heartbeat Replacement

**Recommendation: both** — structured stderr log + `collector_runs` row.

```python
# collectors/<src>/__init__.py end of run:
import logging
_log = logging.getLogger(__name__)

_log.info(
    "collector_run_complete",
    extra={"source": "dart", "stats": stats, "elapsed_ms": elapsed},
)
with engine.begin() as conn:
    conn.execute(text("""
        INSERT INTO collector_runs (source, elapsed_ms, stats, extra)
        VALUES (:source, :ms, CAST(:stats AS jsonb), CAST(:extra AS jsonb))
    """), {"source": "dart", "ms": elapsed,
           "stats": json.dumps(stats), "extra": json.dumps(extra or {})})
```

Why both:

- **stderr log**: real-time visibility during `stock collect`; what
  `cmd_collect_all` aggregates into its JSON report. No DB dependency.
- **`collector_runs` row**: persistent history for Phase 9 dashboards
  (success rate per source over time, mean elapsed_ms drift, failure
  spikes). One row per `collect_<src>()` call is trivially cheap.

Failure of the DB write must **not** fail the collect run — wrap in
try/except and degrade to stderr-only (this is the "ops dashboard goes
blind" failure mode, not a data-loss failure mode). v1.0's heartbeat had
the same isolation property.

## Q6 — CLI Changes

### `--vault-root` removal

Drop from `cli/__main__.py` (lines 40-44) and every subparser. No
replacement — Postgres is reached via `DATABASE_URL` env var, already
the existing pattern. **No config file needed.**

### stdout JSON shape

Current (per-collector): `{"total":N, "succeeded":N, "skipped":N, "failed":[…]}`.

Proposed (v2.0):

```json
{
  "source": "dart",
  "total": 12,
  "inserted": 4,         // new rows
  "updated": 1,          // existing row, content_hash changed
  "skipped": 7,          // idempotent no-op
  "failed": [{"id":"…", "error":"…"}],
  "elapsed_ms": 8423
}
```

`inserted` + `updated` together = "rows touched"; `succeeded` is replaced
with this finer split because UPSERT semantics make a single counter
misleading.

`collect all` report (stderr) replaces `docs_processed` (file count) with
`rows_touched` (= `inserted` + `updated`). Same overall shape:
`{run_at, sources: {dart: {status, rows_touched, elapsed_ms, failed_count}, …}}`.

## Q7 — Test Strategy

**Use testcontainer; do not try SQLite.**

- pgvector, JSONB, ARRAY, vchord_bm25 — none work in SQLite. The existing
  `pg_engine` fixture is the model. Migration 0006 needs no new test
  infrastructure beyond updating `_PHASE2_TABLES` (rename to
  `_LIVE_TABLES`) in `tests/conftest.py` to TRUNCATE the new tables.

- `_dispatch()` monkeypatch pattern (`tests/test_cli_collect_all.py`
  pattern): **retain**. Tests inject fake collector functions, which is
  orthogonal to the storage layer. The collector signature changes from
  `(vault_root=…, engine=…)` to `(engine=…)` — `kwargs` filter at the
  dispatch site simplifies.

- Per-collector tests (`tests/collectors/<src>/`):

  - Replace `path.exists() / parse_frontmatter(path)` assertions with
    `engine.execute(SELECT … FROM filings WHERE rcept_no=…)` row reads.
  - `vault_tmp` fixture becomes vestigial — most tests no longer need it
    (only `seed_portfolio` survives, since `notes/private/portfolio.md`
    is still on disk per `notes_root` convention).
  - Use `seeded_engine` (existing fixture) for entity FK satisfaction.

- New test file: `tests/db/test_migration_0006.py` — verify each table
  exists, columns match, indexes match. Mirror the existing
  `test_migration_0002.py` shape.

## Q8 — Refactor Order (Walking Skeleton)

**Recommendation: macro → krx → kind → news → dart.**

Rationale (simplest first; each step references the previous):

1. **macro** — pure numeric series, no FK to `entities`, no body text. The
   smallest valid UPSERT exercise. Establishes the `db_writer.py` pattern.
   Also exercises the `(PK, ON CONFLICT, value-changed)` revision logic
   that `news`/`filings` need.
2. **krx** — adds FK to `entities` (already battle-tested via
   `resolve_entity`). One row per (ticker, trade_date). Still no body text.
   Builds on macro pattern + adds the FK resolution dance.
3. **kind** — first table with **two** writes per filing: the underlying
   DART `pblntf_ty="I"` filing lands in `filings` (with empty body OK in
   Phase 1; full body needs the `body_md` plumbing tested by dart later),
   the classifier row in `events`. Tests the FK from `events.filing_rcept_no
   → filings.rcept_no`.
4. **news** — first table with `body_md TEXT NOT NULL` + `tickers TEXT[]`.
   Reuses alias matcher (R-09 guard still applies).
5. **dart** — last because it carries the largest body (whole 사업보고서,
   up to ~MB scale text), highest risk of TEXT-column blowup in tests,
   and any plumbing issue surfaces only after the simpler tables work.

This ordering also gives the team a working `stock collect macro` flow
after Wave 1 — a real value milestone, not just refactor churn.

## Q9 — `vault/raw/` Regeneration Guard

**Recommendation: physical deletion + ImportError.**

Three layers, defense in depth:

1. **Delete `src/collectors/*/writer.py`** entirely. Anyone re-importing
   the old function gets a hard `ModuleNotFoundError`. Stronger than a
   runtime assertion because it fires at import time in CI.
2. **Delete `src/shared/frontmatter.py`'s usage from collectors** but keep
   the module — it's used by `tests/test_frontmatter*.py` and the
   future MCP `add_note` path. Just remove `collectors.<src>` imports of
   `FrontMatter`, `ProvenanceBlock`, `write_frontmatter`.
3. **Add a runtime assertion in `cli/__main__.py`**:

```python
def main(argv=None) -> int:
    from pathlib import Path
    legacy_writer = Path("src/collectors/dart/writer.py")
    if legacy_writer.exists():
        raise SystemExit("FATAL: vault writer modules must be deleted — see Phase 1 Q9")
    …
```

This is belt-and-suspenders — the CI test_import_guard pattern is the
real enforcement, but the runtime check protects against an editor
restoring a deleted file.

A **test_import_guard companion test** is the cleanest fence:
`tests/test_no_writer.py` asserts none of
`src/collectors/{dart,krx,news,macro,kind}/writer.py` exist on disk and
that no `collectors.<src>.writer` module is importable.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| UPSERT with conditional update | hand-coded SELECT-then-INSERT | `INSERT … ON CONFLICT … DO UPDATE WHERE …` | atomicity + Postgres optimizer |
| sha256(body) hash | new hashlib calls | `shared.content_hash.normalize_body` + `hashlib.sha256` (existing pattern in all 5 collectors today) | proven normalization, CRLF/whitespace stable |
| structured logging extra | custom formatter | stdlib `logging.info(extra=…)` + JSON formatter | Phase 9 ops dashboard can ingest |
| pgvector halfvec | inserting now | NULL columns now, populate Phase 3 | embedding model lazy-load lives in Phase 3 module |
| Korean tokenization for `body_tsv` | mecab-ko in Phase 1 | leave `body_tsv` NULL, Phase 3 fills | keeps Phase 1 dependency-free |

## Pitfalls to Avoid

1. **`halfvec` requires pgvector 0.7+.** `docker-compose.yml` uses
   `tensorchord/vchord-suite:pg17-latest` which ships 0.8.x. Verified
   via existing migration 0002 which already CREATEs `vector` extension.
   No new ext needed for 0006.
2. **DART rate limit is real.** `dart-fss` defaults to 1 req/sec
   throttling but parallelizing across corp_codes will hit
   `OpenDartError: 일일거래량초과`. Phase 1 doesn't add parallelism —
   keep `collect dart` serial.
3. **trafilatura is not thread-safe.** Existing `news/collect` is serial;
   keep it serial. Don't tempt async.
4. **`ohlcv.short_volume` arrives T+2 days late.** A run on day D fills
   `open/high/low/close/volume` but leaves `short_volume` NULL. A run
   2 days later for the same date must update only the short columns
   without clobbering the rest — that's the
   `COALESCE(EXCLUDED.x, ohlcv.x)` pattern in the UPSERT.
5. **Korean `body_md` over `NUMERIC(18,4)`.** `to_dict()` from dart-fss
   for 주요사항보고서 returns text fields, not numbers. Don't apply numeric
   parsing in Phase 1 — that's Phase 3 (`_derived` extraction). Just
   store `body_md` as TEXT.
6. **`entity_aliases` deliberately has no UNIQUE on (corp_code, kind, value).**
   See `db/migrations/0001` line 77 (Pitfall 5 in v1.0 — KRX recycles
   tickers). Any FK from collectors to entities must go through
   `resolve_entity()` which handles the half-open `[valid_from, valid_to)`
   interval correctly. Don't bypass.
7. **`pblntf_ty="I"` filings have NO ticker.** DART exchange filings
   come through with `stock_code=None` sometimes (the issuer's `entities`
   row has the ticker). Resolve via `corp_code → entities.current_ticker`
   in the kind collector, not from the filing object directly.
8. **`tickers TEXT[]` in `news` needs `CAST(:val AS text[])`.** psycopg3
   binds Python list as JSON by default. Use SQLAlchemy `postgresql.ARRAY`
   column type with `psycopg`'s adapter, or wrap as `cast(:val, ARRAY(TEXT))`
   in the INSERT.
9. **`testcontainers` pulls a ~2GB image first run.** Set
   `TESTCONTAINERS_RYUK_DISABLED=true` on Windows where Docker Desktop
   sometimes leaks containers. Existing CI already handles this.
10. **`logging.info(extra=…)` keys collide with stdlib LogRecord attributes.**
    Don't use `message`, `name`, `pathname`, `lineno`, `args` as keys —
    use `{"source": …, "stats": …, "elapsed_ms": …}` shape only.

## Suggested Wave Organization

Per `gsd-executor` parallelism, three waves, each a self-contained slice:

### Wave 0 — Schema + CLI cleanup (sequential, gates everything)

- Migration `0006` with all 5 domain tables + `collector_runs` + rename of
  legacy `events → events_legacy`.
- `_LIVE_TABLES` update in `tests/conftest.py`.
- `tests/db/test_migration_0006.py` — schema-shape assertions.
- Remove `--vault-root` from `cli/__main__.py` and `cli/commands.py`.
- Remove `vault_root` parameter from collector signatures (signature-only
  change; bodies still write to disk this wave).
- Delete `src/shared/heartbeat.py` import sites; replace with a TODO
  comment (next wave wires real logging).

This wave must land first because the schema is the contract every
subsequent collector refactor depends on. CLI/heartbeat removal is bundled
here because tests in subsequent waves assume the new signatures.

### Wave 1 — Simple-table collectors (parallel)

Two tasks, parallelizable:

- **Wave-1A — `macro` collector**:
  - New `collectors/macro/db_writer.py` with
    `upsert_macro_series(engine, source, series_id, item_code, observations)`.
  - `collectors/macro/__init__.py` calls db_writer instead of writer.
  - Delete `collectors/macro/writer.py`.
  - Update `tests/collectors/macro/test_collect_macro.py`.

- **Wave-1B — `krx` collector**:
  - New `collectors/krx/db_writer.py` with `upsert_ohlcv(engine, ticker, date, ohlcv, flow, short)`.
  - Same shape as macro.
  - Tests updated.

### Wave 2 — Body-bearing collectors + observability (parallel within wave)

Three tasks, parallelizable (kind depends on filings shape only, which
is locked by Wave 0):

- **Wave-2A — `kind` collector**: writes to `filings` (raw `pblntf_ty="I"`
  filings, body_md may be empty for now — Phase 3 backfills) AND `events`
  (classifier row).
- **Wave-2B — `news` collector**: full `body_md` + `tickers TEXT[]` UPSERT.
  Reuses alias matcher.
- **Wave-2C — `dart` collector**: full A+B filings into `filings.body_md`.
  Highest body sizes; runs last in dev but parallel with others in plan.
- **Wave-2D — Observability**: `collector_runs` INSERT wiring + structured
  logging. Single small task that touches all 5 collectors (post-Wave-1A/B,
  parallel with 2A/B/C since it adds calls, not signature changes).
- **Wave-2E — Guards**: `tests/test_no_writer.py` + cli runtime assertion.
  Trivial, runs last as a fence.

Wave 2 succeeds when `uv run stock collect all` exits 0 with no
`vault/raw/` directory created.

## Validation Architecture

### Test Framework

| Property | Value |
|---|---|
| Framework | pytest 9.x |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest -m "not slow and not e2e" -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test type | Command | File exists? |
|---|---|---|---|---|
| SC-1 | `collect dart` INSERTs into `filings` | integration | `uv run pytest tests/collectors/dart/ -k filings -x` | ❌ Wave 0 |
| SC-2 | UPSERT dedup on all 5 tables | integration | `uv run pytest tests/collectors/ -k upsert` | ❌ Wave 0 |
| SC-3 | `heartbeat.py` deleted; structured logs | unit | `uv run pytest tests/test_no_heartbeat.py` | ❌ Wave 0 |
| SC-4 | `--vault-root` removed | unit | `uv run pytest tests/test_cli_default_flags.py` (update existing) | ✅ |
| SC-5 | DB-based test assertions | integration | `uv run pytest tests/collectors/` | partial — update existing |
| Migration | `0006` head reachable | unit | `uv run pytest tests/db/test_migration_0006.py` | ❌ Wave 0 |

### Sampling rate

- Per task commit: `uv run pytest -m "not slow and not e2e" -x` (~30s).
- Per wave merge: full suite + manual `uv run stock collect macro`.
- Phase gate: `uv run stock collect all` succeeds with empty `vault/raw/`.

### Wave 0 gaps

- [ ] `tests/db/test_migration_0006.py`
- [ ] `tests/test_no_heartbeat.py`
- [ ] `tests/test_no_writer.py`
- [ ] Update `tests/conftest.py` `_PHASE2_TABLES → _LIVE_TABLES` with new tables
- [ ] Update `tests/collectors/conftest.py::vault_tmp` — most tests no longer
      need `vault/raw/` subdir.

## Security Domain

| ASVS Category | Applies | Standard Control |
|---|---|---|
| V2 Authentication | yes (DB) | `DATABASE_URL` env, no hardcoded creds |
| V3 Session Management | no | n/a — local-only DB |
| V4 Access Control | no | single-user runtime |
| V5 Input Validation | yes | regex pre-filters at `entities.py` D-12 carry over; UPSERT bind params |
| V6 Cryptography | no (sha256 is dedup, not auth) | already noted in `content_hash.py` |

### Known threat patterns

| Pattern | STRIDE | Mitigation |
|---|---|---|
| SQL injection via corp_code | Tampering | `^[0-9]{8}$` regex pre-filter in `entity.py` — unchanged in Phase 1 |
| psycopg3 ARRAY binding mistake | Tampering | Use `postgresql.ARRAY(Text)` column type + bind, not `:val::text[]` interpolation |
| Path traversal in writer.py | Tampering | **Eliminated** — writers deleted |
| Prompt injection via news body | Spoofing | **Deferred to Phase 3** — `body_md` stored as-is; LLM-side wrapping happens at MCP gate |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | Legacy `events` table is empty post-shutdown | Q4 | Rename fails — verify with `SELECT count(*)` first |
| A2 | pgvector 0.8 `halfvec` available in `tensorchord/vchord-suite:pg17-latest` | Q1 | Migration error; fallback `vector(1024)` |
| A3 | `psycopg3` adapts `list[str]` to `text[]` when column type declared | Q1 news | Use `postgresql.ARRAY` SQLAlchemy column type explicitly |
| A4 | DART rate limit unaffected by removing Markdown write step | Pitfalls | Negligible — bottleneck was always upstream |
| A5 | No production DB exists today; testcontainer is sole runtime | Q4 | If a real DB exists, 0006 must handle live legacy data |

## Open questions remaining for the planner

1. **Live DB inventory.** Does anyone have a populated stock DB right now, or
   is this all in testcontainer? If live data exists, A1 must be checked
   (the `events_legacy` rename assumes empty). Recommend: planner adds
   pre-migration `SELECT count(*) FROM events` assertion task.

2. **Event of duplicate `events` table name.** Confirm preference Q4-A
   (`kind_events`) vs Q4-B (`events_legacy` + new `events`). Researcher
   recommends B but it's a naming-aesthetics call.

3. **Test container Korean locale.** `tensorchord/vchord-suite:pg17-latest`
   may default to `C` locale, breaking Korean ORDER BY. Not Phase 1 blocking,
   but planner should note this for Phase 3 BM25 work.

4. **`collector_runs` retention.** No retention policy here. If runs are
   logged every minute via Phase 9 routine, table grows ~525k rows/year.
   Planner may want a Phase 9 prune task — not Phase 1 concern.

5. **Idempotency of `collect macro` revision rows.** v1.0's
   `merge_observations` surfaced same-date/different-value as a "revision."
   The UPSERT pattern in Q2 does the same thing structurally (UPDATE on
   value change, fetched_at=now()), but does **not** keep history. If
   audit-trail of ECOS revisions matters, planner should add a
   `macro_revisions` table — not in scope today.

6. **`tests/collectors/news/` fixtures.** Existing news tests rely on
   `tests/fixtures/news/` (HTML samples). Some tests assert frontmatter
   shape. Planner should budget time to rewrite those — they account for
   ~1/3 of Phase 1 test churn.

7. **Whether to commit the rename of `pg_clean` fixture's `_PHASE2_TABLES`
   to `_LIVE_TABLES`.** Cosmetic; planner can choose.

8. **`collectors.macro.collect_macro`'s `engine` parameter is unused** (R-12
   signature parity). After Phase 1, it WILL be used (for INSERT). The
   `# noqa: ARG001` should be removed — bookkeeping item for the planner.

## Sources

### Primary (HIGH confidence — read from this repo)

- `C:/Users/minsu/workspace/stock/CLAUDE.md` — Hard Vetoes (lines 22-58)
- `C:/Users/minsu/workspace/stock/.planning/research/redesign-2026-05.md` §2 (schema sketch, lines 96-180)
- `C:/Users/minsu/workspace/stock/.planning/ROADMAP.md` Phase 1 (lines 34-58)
- `C:/Users/minsu/workspace/stock/src/db/migrations/versions/0001_phase02_initial_schema.py` — existing schema
- `C:/Users/minsu/workspace/stock/src/db/entity.py` — `resolve_entity` contract
- `C:/Users/minsu/workspace/stock/src/collectors/*/writer.py` — current Markdown writers (all 5)
- `C:/Users/minsu/workspace/stock/src/cli/{__main__,commands}.py` — CLI surface
- `C:/Users/minsu/workspace/stock/src/shared/heartbeat.py` — no-op stub to delete
- `C:/Users/minsu/workspace/stock/tests/conftest.py` — `pg_engine` testcontainer fixture
- `C:/Users/minsu/workspace/stock/pyproject.toml` — dep groups

### Secondary (MEDIUM — codebase consistency)

- `C:/Users/minsu/workspace/stock/.planning/macro_series.yaml` — macro catalog shape
- `C:/Users/minsu/workspace/stock/src/collectors/kind/sources.py` — `KindEventType` enum
- `C:/Users/minsu/workspace/stock/src/collectors/news/matcher.py` — alias matching contract

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all libraries already in `pyproject.toml`, no
  new deps required.
- Schema (Q1): HIGH — driven by §2 sketch + Hard Vetoes #6/#8/#9.
- Dedup (Q2): HIGH — natural PKs exist for every source.
- Legacy disposition (Q3): MEDIUM — depends on whether live `documents`
  rows exist (planner must verify).
- Migration order (Q4): HIGH — single 0006 is clearly sufficient.
- Observability (Q5): MEDIUM — Phase 9 ops dashboard is unscoped, so the
  `collector_runs` shape is a forward-looking guess.
- CLI changes (Q6): HIGH — surface is small.
- Test strategy (Q7): HIGH — testcontainer is the established pattern.
- Refactor order (Q8): HIGH — dependency chain is obvious.
- vault/raw/ guard (Q9): HIGH — physical deletion is the cleanest fence.

**Research date:** 2026-05-29
**Valid until:** 2026-06-29 (30 days; codebase is stable post-shutdown)
