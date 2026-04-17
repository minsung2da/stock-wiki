# Phase 2: Canonical Entity Identity - Research

**Researched:** 2026-04-17
**Domain:** Postgres schema design, Alembic migrations, content-addressed storage, temporal entity modeling for Korean market
**Confidence:** HIGH on stack & patterns; MEDIUM on Korean ticker-recycling fixture sourcing (hard data not in public search)

## Summary

Phase 2 locks the Postgres schema before any document is written: 6 tables, content-hash document IDs, and a normalized entity-alias history that survives KOSPI/KOSDAQ rename / split / 기재정정 / ticker recycling without re-ingest. The technical surface is small and well-trodden — Alembic 1.18 + SQLAlchemy 2.0 Core + psycopg3 are the consensus 2026 stack and all already pinned (or trivially added) in `pyproject.toml`. The only research-heavy decisions are (a) test-DB strategy (testcontainers vs reusing the running docker-compose) and (b) which historical Korean cases to encode as fixtures.

**Primary recommendation:** Add `alembic>=1.18` to a new `db` dependency group, use SQLAlchemy 2.0 Core (not ORM) for migration `op.create_table` and the thin `resolve_entity` query helper, drive integration tests via `testcontainers[postgres]` with `tensorchord/vchord-suite:pg17-latest` (same image already in `docker-compose.yml`) so test schemas are isolated from dev data. Ship one Alembic migration covering all 6 tables — the schema is small enough that splitting buys nothing and a single migration matches the "Phase 2 = lock the foundation" intent.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Entity Alias History Model**
- **D-01:** 엔티티 이력은 별도 `entity_aliases` 테이블로 정규화. JSONB/단일테이블 거부.
- **D-02:** `entity_aliases` 컬럼: `id BIGSERIAL`, `corp_code CHAR(8) REFERENCES entities(corp_code)`, `kind TEXT CHECK(kind IN ('name','ticker','eng_name'))`, `value TEXT NOT NULL`, `valid_from DATE NOT NULL`, `valid_to DATE NULL` (NULL = current), `created_at TIMESTAMPTZ DEFAULT now()`.
- **D-03:** 인덱스: `(kind, value, valid_from, valid_to)` — ticker 재활용·개명 lookup 모두 처리.
- **D-04:** `entities` 테이블은 현재 상태만 저장: `corp_code (PK)`, `canonical_name`, `current_ticker`, `sector`, `market` (KOSPI/KOSDAQ), `listed_at`, `delisted_at NULL`.

**Supersedes Edge Storage**
- **D-05:** 기재정정 체인은 `edges` 테이블에만 기록. `documents`에 self-reference 컬럼을 두지 않는다.
- **D-06:** `edges` 스키마: `id BIGSERIAL`, `src_type TEXT`, `src_id TEXT`, `dst_type TEXT`, `dst_id TEXT`, `edge_type TEXT NOT NULL`, `tag TEXT NULL` (EXTRACTED/INFERRED/AMBIGUOUS for Phase 7), `created_at TIMESTAMPTZ DEFAULT now()`. 복합 유니크: `(src_type, src_id, dst_type, dst_id, edge_type)`.
- **D-07:** 최신 문서 조회는 재귀 CTE로 supersedes 체인을 역추적. Phase 6 `get_filing(id)` 툴에서 명시적으로 "이 문서의 최종 정정본" 의미를 처리.
- **D-08:** Phase 2에서 등록할 엣지 타입: `supersedes`. 나머지(ticker→filing 등)는 Phase 7에서 추가.

**`resolve_entity` Temporal Semantics**
- **D-09:** 단일 축(valid-time only). `as_of` 파라미터는 "실세계 그 시점의 엔티티 상태"를 의미.
- **D-10:** Query form:
  ```sql
  SELECT corp_code FROM entity_aliases
  WHERE kind = :kind AND value = :value
    AND valid_from <= :as_of
    AND (valid_to IS NULL OR valid_to > :as_of)
  LIMIT 1
  ```
- **D-11:** `resolve_entity(ticker_or_corp_code: str, as_of: date | None = None) -> Entity | None`. `as_of=None`일 때 현재(`valid_to IS NULL`)만 조회.
- **D-12:** 8자리면 corp_code, 6자리면 ticker로 자동 분기. 둘 다 미스매치면 None 반환.

**Content-Hash Dedup**
- **D-13:** `documents.id = sha256(normalized_body)`. `body` 정의: 수집된 원문에서 YAML frontmatter(`---` 블록) 제거 후 본문만.
- **D-14:** 정규화: `\r\n` → `\n`, trailing whitespace 제거, 파일 끝 개행 1개로 통일. 추가 정규화 (예: HTML 공백 축약)는 하지 않음 — DART·뉴스 원문이 안정적.
- **D-15:** 충돌 시 동작: Upsert.
  ```sql
  INSERT INTO documents (id, body, source, vault_path, source_url, last_seen_at, source_urls)
  VALUES (...)
  ON CONFLICT (id) DO UPDATE SET
    last_seen_at = EXCLUDED.last_seen_at,
    source_urls = array_append(documents.source_urls, EXCLUDED.source_url)
    WHERE NOT (EXCLUDED.source_url = ANY(documents.source_urls))
  ```
- **D-16:** `documents` 컬럼: `id CHAR(64) PRIMARY KEY` (hex sha256), `body TEXT NOT NULL`, `source TEXT NOT NULL`, `vault_path TEXT NOT NULL`, `source_url TEXT NULL`, `source_urls TEXT[] NULL`, `first_seen_at TIMESTAMPTZ DEFAULT now()`, `last_seen_at TIMESTAMPTZ DEFAULT now()`.

### Claude's Discretion

- Alembic env.py 설정 (autogenerate vs explicit)
- 마이그레이션 파일 분할 전략 (one big migration vs 여러 개)
- `events`, `ingest_runs`, `chunks` 테이블의 상세 스키마 (Phase 3에서 구체화해도 됨, 여기서는 최소 뼈대만)
- `chunks` 테이블의 HNSW 인덱스 실제 생성 (Phase 3으로 위임해도 무방)
- pytest fixture에서 사용할 rename/split/ticker-recycling 케이스의 실제 기업 선정 (실제 DART 공시 케이스 권장)

### Deferred Ideas (OUT OF SCOPE)

- Bitemporal 모델 (system-time + valid-time)
- `events` 이벤트 타입 확장 — Phase 4
- `chunks.embedding` HNSW 인덱스 실제 생성 — Phase 3 (INGEST-10 / STORE-03)
- graphify 엣지 타입 전체 등록 — Phase 7 GRAPH-01
- `documents.source_urls` 별도 `document_sources` 테이블로 정규화
- `entity_aliases` GIN 인덱스로 full-text alias fuzzy matching
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ENT-01 | `corp_code` (DART 8자리) is canonical entity ID; KRX ticker is convenience field | D-04 entities schema; D-12 6/8-digit auto-branch in `resolve_entity` |
| ENT-02 | `entities` + 시간 범위 이력으로 종목명 변경·합병·분할·상장폐지·티커 재활용 추적 | D-01~03 normalized `entity_aliases` with `valid_from`/`valid_to`; index on `(kind, value, valid_from, valid_to)` handles all four corporate-action types |
| ENT-03 | DART 기재정정 (`supersedes`) 체인이 엣지로 저장되어 최신 공시만 소비 가능 | D-05~08 `edges` table with `edge_type='supersedes'`; D-07 recursive CTE traversal documented for Phase 6 |
| STORE-01 | Alembic 마이그레이션으로 6개 테이블과 인덱스 생성 | Alembic 1.18 + SQLAlchemy 2.0 — see Standard Stack |
| STORE-02 | `documents.id = sha256(body)` 콘텐츠 주소화 | D-13~16; reuse `src/shared/frontmatter.py` to strip frontmatter before hashing |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tech stack ban:** ingest venv must not gain `anthropic`/`openai` (CI guard COLL-07 enforces). Phase 2 adds only `alembic` to a new `db` group — no LLM dependency.
- **Storage rule:** "DB는 인덱스·캐시이며 언제든 vault에서 재생성 가능" — schema must support full rebuild from `vault/raw/` (`STORE-05` Phase 3). Means: no DB-only fields in Phase 2 that can't be derived from a `.md` file.
- **Immutability:** project rules say "create new objects, not mutate." `entity_aliases` is append-only by design (D-04 + specifics §3) — `valid_to` is the only field ever updated, never the value/from.
- **Surgical changes:** only the files needed for this phase. Don't touch `src/shared/frontmatter.py` beyond importing its `read_frontmatter` body extractor for content-hash. No Pydantic schema changes.
- **TDD:** Phase 1 established RED→GREEN cadence (10 frontmatter tests). Phase 2 must continue: write Alembic + resolve_entity tests first, fail them, implement, pass.
- **Secrets:** DB password via `${POSTGRES_PASSWORD}` env var (already in `docker-compose.yml`). Alembic `env.py` reads from same env, never hardcodes.
- **CLAUDE.md Tech Stack §3.1:** Native Postgres 17 over PGLite — confirmed; phase ships against running container.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `alembic` | `>=1.18,<2` | DB schema migrations | [VERIFIED: PyPI `pip index versions alembic` returns 1.18.4 as latest, 2026-02-10] [CITED: alembic.sqlalchemy.org/en/latest/tutorial.html] — de-facto Python migration tool, paired with SQLAlchemy 2.0 |
| `sqlalchemy` | `>=2.0,<3` | Schema DSL for migrations + thin Core query layer for `resolve_entity` | Already pinned in `ingest` and `mcp` groups [VERIFIED: pyproject.toml lines 31, 38]. Alembic 1.18+ uses SQLAlchemy 2.0 bulk inspector for autogenerate [CITED: alembic 1.18 release notes] |
| `psycopg[binary]` | `>=3.2` | Postgres driver | Already pinned in `ingest` and `mcp` groups [VERIFIED: pyproject.toml]. Modern psycopg3 (not psycopg2) — supports SQLAlchemy 2.0 native, no compilation |
| `pgvector` | `>=0.4` (Python lib) | Type adapter for `vector(1024)` column on `chunks` | Already pinned [VERIFIED: pyproject.toml]. Not strictly needed in Phase 2 if we declare `chunks.embedding` via raw SQL, but cleaner to use the type registration once for the bare-bones column. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `testcontainers[postgres]` | `>=4.8` | Spin Postgres container for integration tests | Add to `dev` group — provides hermetic DB per test session, isolated from dev `docker-compose` data [CITED: testcontainers.com/guides/getting-started-with-testcontainers-for-python/] |
| `python-frontmatter` | `>=1.1` (already pinned) | Already used by `src/shared/frontmatter.py`; reuse `fm.load()` to strip frontmatter for content-hash | [VERIFIED: pyproject.toml line 9] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Alembic | `yoyo-migrations`, raw `.sql` files | Alembic is the consensus tool; raw SQL forfeits autogenerate diff and downgrade. No reason to deviate. |
| `testcontainers[postgres]` | `pytest-postgresql` | `pytest-postgresql` spawns a local `postgres` binary — requires Postgres installed on host. WSL2 dev box already has Docker [VERIFIED: `docker --version` = 29.3.0]. Testcontainers reuses the same `tensorchord/vchord-suite:pg17-latest` image already in `docker-compose.yml`, guaranteeing the test DB has identical extensions to dev. **Pick testcontainers.** |
| `testcontainers[postgres]` | Reuse running dev `docker-compose` Postgres with a `_test` schema | Faster (no startup), but tests pollute dev volume and can't run in CI without Docker Compose orchestration. Use only as a developer-loop fast path; CI still uses testcontainers. |
| SQLAlchemy ORM | SQLAlchemy Core | Project never declared ORM models; Phase 2 defines schema in Alembic `op.create_table(...)` only. `resolve_entity` is a single SELECT — Core's `text()` or `select()` is enough. ORM adds session/identity-map machinery this codebase doesn't need yet. **Pick Core.** |
| One big migration | Multiple per-table migrations | Schema is small (~6 tables), all required for Phase 2 success criteria, all coupled (entity_aliases FK → entities). Splitting requires correct ordering and inflates review surface. **One migration.** Future schema changes get their own migrations. |
| `autogenerate` | Hand-written `op.create_table` calls | Autogenerate requires SQLAlchemy MetaData + model classes. We have no models. Hand-writing is faster and the project never claims to want ORM models. Keep autogenerate as an option for Phase 3+ if model classes appear. **Hand-write Phase 2.** |

**Installation:**
```bash
# Add to pyproject.toml [dependency-groups]
# db = ["alembic>=1.18,<2", "sqlalchemy>=2.0,<3", "psycopg[binary]>=3.2", "pgvector>=0.4"]
# dev gets: "testcontainers[postgres]>=4.8"
uv sync --group db --group dev
```

**Version verification:**
- `alembic` 1.18.4 — [VERIFIED: `pip index versions alembic` 2026-04-17, latest `1.18.4`]
- `testcontainers-python` 2.0.0 docs published — [CITED: testcontainers-python.readthedocs.io/]
- Docker 29.3.0 + uv 0.11.7 + Python 3.12.3 — [VERIFIED: `docker --version`, `uv --version`, `python3 --version`]

## Architecture Patterns

### Recommended Layout (extends Phase 1 `src/db/`)
```
src/
├── db/
│   ├── __init__.py
│   ├── alembic.ini             # alembic config (script_location=src/db/migrations)
│   ├── migrations/
│   │   ├── env.py              # reads DATABASE_URL from env, no models
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 0001_phase02_initial_schema.py   # all 6 tables in one revision
│   ├── engine.py               # SQLAlchemy 2.0 Engine factory; reads DATABASE_URL
│   └── entity.py               # resolve_entity(ticker_or_corp_code, as_of) helper
├── shared/
│   └── content_hash.py         # NEW: sha256(normalized_body) per D-13/D-14, reuses fm.load()
└── ...
tests/
├── conftest.py                 # add `pg_container` session fixture (testcontainers)
├── test_migration.py           # alembic upgrade head + downgrade base + idempotent re-up
├── test_documents_dedup.py     # content-hash upsert behavior (D-15)
├── test_entity_resolve.py      # rename/split/ticker-recycling fixtures
└── test_supersedes_edge.py     # 기재정정 chain → recursive CTE
fixtures/
└── entities/
    ├── rename_case.yaml        # corp_code stays, canonical_name + alias change
    ├── split_case.yaml         # corp_code stays, ticker stays, listed_at marker
    └── ticker_recycle.yaml     # ticker reused across two corp_codes with non-overlapping valid ranges
```

### Pattern 1: Alembic env.py for hand-written migrations (no ORM)
**What:** `env.py` runs migrations using a Connection, no `target_metadata` (autogenerate disabled).
**When to use:** Project has no SQLAlchemy declarative models — all schema lives in Alembic `op.*` calls.
**Example:**
```python
# src/db/migrations/env.py
# Source: alembic.sqlalchemy.org/en/latest/tutorial.html (offline / online runner pattern)
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

# No autogenerate — schema is hand-written.
target_metadata = None

DATABASE_URL = os.environ["DATABASE_URL"]  # e.g. postgresql+psycopg://stockwiki:...@127.0.0.1:5432/stockwiki

def run_migrations_online() -> None:
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

run_migrations_online()
```

### Pattern 2: Hand-written `op.create_table` migration (Phase 2 schema)
**What:** Single revision creating all 6 tables, indexes, and a CHECK on `entity_aliases.kind`.
**When to use:** Locked schema known before any data exists.
**Example:**
```python
# src/db/migrations/versions/0001_phase02_initial_schema.py
# Source: alembic.sqlalchemy.org/en/latest/ops.html
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("corp_code", sa.CHAR(8), primary_key=True),
        sa.Column("canonical_name", sa.Text, nullable=False),
        sa.Column("current_ticker", sa.CHAR(6), nullable=True),
        sa.Column("sector", sa.Text, nullable=True),
        sa.Column("market", sa.Text, nullable=True),
        sa.Column("listed_at", sa.Date, nullable=True),
        sa.Column("delisted_at", sa.Date, nullable=True),
        sa.CheckConstraint("market IN ('KOSPI','KOSDAQ','KONEX') OR market IS NULL", name="ck_entities_market"),
    )

    op.create_table(
        "entity_aliases",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("corp_code", sa.CHAR(8),
                  sa.ForeignKey("entities.corp_code", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("valid_from", sa.Date, nullable=False),
        sa.Column("valid_to", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('name','ticker','eng_name')", name="ck_alias_kind"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_alias_validity_order"),
    )
    op.create_index(
        "ix_alias_lookup",
        "entity_aliases",
        ["kind", "value", "valid_from", "valid_to"],
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.CHAR(64), primary_key=True),  # sha256 hex
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("vault_path", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("source_urls", sa.ARRAY(sa.Text), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_documents_source", "documents", ["source"])
    op.create_index("ix_documents_vault_path", "documents", ["vault_path"], unique=True)

    # Skeleton chunks table — Phase 3 adds HNSW index + bm25_tokens column population.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")  # idempotent; init-extensions.sql ran on container init
    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.CHAR(64),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ord", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding_model", sa.Text, nullable=True),  # populated by Phase 3
    )
    # Embedding column added via raw SQL to use pgvector type (declared, not indexed in Phase 2)
    op.execute("ALTER TABLE chunks ADD COLUMN embedding vector(1024)")
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])

    op.create_table(
        "edges",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("src_type", sa.Text, nullable=False),
        sa.Column("src_id", sa.Text, nullable=False),
        sa.Column("dst_type", sa.Text, nullable=False),
        sa.Column("dst_id", sa.Text, nullable=False),
        sa.Column("edge_type", sa.Text, nullable=False),
        sa.Column("tag", sa.Text, nullable=True),  # EXTRACTED|INFERRED|AMBIGUOUS — Phase 7
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("src_type", "src_id", "dst_type", "dst_id", "edge_type",
                            name="uq_edge_endpoints"),
        sa.CheckConstraint(
            "edge_type IN ('supersedes')",  # Phase 2 only registers supersedes; relax in Phase 7
            name="ck_edge_type_phase2"
        ),
    )
    op.create_index("ix_edges_src", "edges", ["src_type", "src_id"])
    op.create_index("ix_edges_dst", "edges", ["dst_type", "dst_id"])
    op.create_index("ix_edges_type", "edges", ["edge_type"])

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("corp_code", sa.CHAR(8),
                  sa.ForeignKey("entities.corp_code", ondelete="SET NULL"), nullable=True),
        sa.Column("document_id", sa.CHAR(64),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payload", sa.dialects.postgresql.JSONB, nullable=False),
    )
    op.create_index("ix_events_corp_code_time", "events", ["corp_code", "occurred_at"])

    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=True),
        sa.Column("stats", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
    )

def downgrade() -> None:
    for tbl in ("ingest_runs","events","edges","chunks","documents","entity_aliases","entities"):
        op.drop_table(tbl)
```

### Pattern 3: Content-hash computation reusing existing frontmatter strip
**What:** `src/shared/content_hash.py` — single function `compute_content_hash(file_path) -> str` honoring D-13/D-14.
```python
# src/shared/content_hash.py
import hashlib
import frontmatter as fm  # already in deps

def normalize_body(body: str) -> str:
    """D-14: \\r\\n -> \\n, strip trailing whitespace per line, single trailing newline."""
    lines = body.replace("\r\n", "\n").split("\n")
    stripped = [ln.rstrip() for ln in lines]
    text = "\n".join(stripped).rstrip("\n") + "\n"
    return text

def compute_content_hash(path: str) -> str:
    """D-13: sha256 of frontmatter-stripped, normalized body. Returns 64-char hex."""
    post = fm.load(path)
    return hashlib.sha256(normalize_body(post.content).encode("utf-8")).hexdigest()
```

### Pattern 4: `resolve_entity` — single-axis valid-time SELECT (D-09~12)
```python
# src/db/entity.py
from dataclasses import dataclass
from datetime import date
from typing import Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine

@dataclass(frozen=True)
class Entity:
    corp_code: str
    canonical_name: str
    current_ticker: Optional[str]

def resolve_entity(engine: Engine, value: str, as_of: Optional[date] = None) -> Optional[Entity]:
    """D-12 auto-branch: 8 digits = corp_code direct lookup; 6 digits = ticker via aliases."""
    if len(value) == 8 and value.isdigit():
        kind = "corp_code"
        sql = text("""
            SELECT corp_code, canonical_name, current_ticker
            FROM entities WHERE corp_code = :v
        """)
        params = {"v": value}
    elif len(value) == 6 and value.isdigit():
        # D-10/D-11 valid-time query through aliases
        if as_of is None:
            sql = text("""
                SELECT e.corp_code, e.canonical_name, e.current_ticker
                FROM entity_aliases a JOIN entities e USING (corp_code)
                WHERE a.kind = 'ticker' AND a.value = :v AND a.valid_to IS NULL
                LIMIT 1
            """)
            params = {"v": value}
        else:
            sql = text("""
                SELECT e.corp_code, e.canonical_name, e.current_ticker
                FROM entity_aliases a JOIN entities e USING (corp_code)
                WHERE a.kind = 'ticker' AND a.value = :v
                  AND a.valid_from <= :asof
                  AND (a.valid_to IS NULL OR a.valid_to > :asof)
                LIMIT 1
            """)
            params = {"v": value, "asof": as_of}
    else:
        return None  # D-12 mismatch

    with engine.connect() as conn:
        row = conn.execute(sql, params).first()
    return Entity(*row) if row else None
```

### Anti-Patterns to Avoid
- **Letting Alembic autogenerate run without `target_metadata`:** silently produces empty migrations. Either commit to declarative models or set `target_metadata = None` and write `op.*` by hand.
- **Storing `corp_code` as `TEXT` instead of `CHAR(8)`:** loses fixed-width assumption; `CHECK (length(corp_code) = 8 AND corp_code ~ '^[0-9]+$')` later requires a backfill. **Use `CHAR(8)` from day one.**
- **Updating `entity_aliases` rows in place when ticker changes:** breaks audit trail. Insert a new row, set old row's `valid_to`. Append-only by design.
- **Putting `supersedes` as a column on `documents`:** explicitly rejected in D-05. Edges-only, recursive CTE for traversal.
- **Computing `documents.id` from raw file (with frontmatter) bytes:** then `_derived` enrichment in Phase 5 changes the hash and dedup breaks. Strip frontmatter first per D-13.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Schema migrations | Custom version-tracking SQL files | Alembic 1.18 | Battle-tested up/down/branch model; `alembic_version` table is the consensus pattern |
| Postgres test fixtures | `subprocess.run(["docker","run",...])` shells in conftest | `testcontainers[postgres]` | Handles port allocation, healthchecks, cleanup; image reuse with running compose stack [CITED: testcontainers.com guides] |
| Frontmatter stripping for content-hash | Regex `^---\n.*?\n---\n` | `python-frontmatter` `fm.load(path).content` | Already a dep; handles edge cases (no frontmatter, `---` in body, BOM) |
| YAML round-trip for fixtures | Manual yaml.dump | Reuse `tests/conftest.py::sample_yaml` from Phase 1 | Pattern established |
| Recursive supersedes traversal in Python | Loop + repeated SELECT | Postgres recursive CTE (`WITH RECURSIVE`) | Single round-trip; documented in [PostgreSQL docs WITH RECURSIVE]. Phase 6 implements; Phase 2 documents. |

## Common Pitfalls

### Pitfall 1: Ticker recycling fixture missing → Phase 2 success criteria fail silently
**What goes wrong:** Test fixtures cover rename + split but skip ticker recycling because finding a real KRX example is hard. Bug ships: `resolve_entity("005490", as_of=date(2003,1,1))` returns the wrong entity for any historical query.
**Why it happens:** Public web search for "KRX 6-digit ticker reuse" returns nothing concrete (search performed 2026-04-17 — no useful hits). [VERIFIED: WebSearch returns only delisting reform articles, no recycling cases]
**How to avoid:** Construct a **synthetic but plausible** fixture for v1 (e.g., `corp_code='99999991'` listed 1990–2000 with ticker 099999, `corp_code='99999992'` listed 2010–present with same ticker 099999). Document it as synthetic in fixture comments. Real-case backfill is a v2 task. Phase 2 success criteria #3 only requires "a fixture covering ticker-recycling case resolves correctly" — synthetic data satisfies this.
**Warning signs:** All fixtures use real `corp_code` values from DART crawl that we don't have yet (Phase 3).

### Pitfall 2: Inheritance from PITFALLS.md Pitfall 3 — losing identity at corporate actions
**What goes wrong:** [VERIFIED: PITFALLS.md lines 65-91] Frontmatter uses `ticker` as the join key; rename / split / recycling silently misroute documents.
**How to avoid:** Phase 2 schema makes `corp_code` mandatory in `entities` and FK target for `entity_aliases`/`events`. Documents don't FK to entities directly — they store `corp_code` in frontmatter (Phase 1 `ProvenanceBlock.corp_code`) and Phase 3 collectors look it up via `resolve_entity` before INSERT.
**Warning signs:** Any Phase 2 PR that adds a `ticker`-typed FK to a non-alias table. Reject.

### Pitfall 3: Alembic + extensions ordering on first run
**What goes wrong:** `op.execute("ALTER TABLE chunks ADD COLUMN embedding vector(1024)")` fails with `type "vector" does not exist` if the migration runs against a vanilla Postgres image instead of `tensorchord/vchord-suite`.
**Why it happens:** Phase 1 `scripts/init-extensions.sql` runs only via `/docker-entrypoint-initdb.d` on **first container init**. A test container created without that mount has no extensions.
**How to avoid:** Migration includes `CREATE EXTENSION IF NOT EXISTS vector` (idempotent). Test fixture must use the same image (`tensorchord/vchord-suite:pg17-latest`) so `vchord_bm25` is available for Phase 3 — but Phase 2 only needs `vector` and `pg_trgm`.
**Warning signs:** Tests pass locally (against running compose) but fail in testcontainers.

### Pitfall 4: `documents.id` computed inconsistently between collectors and ingest
**What goes wrong:** Phase 3 collector hashes raw file bytes; Phase 5 ingest hashes `fm.load().content`. Same file → two IDs → dedup broken, duplicate rows.
**How to avoid:** Phase 2 ships `src/shared/content_hash.py::compute_content_hash(path)` as the **single canonical implementation**. Both Phase 3 and Phase 5 import from there. Add a regression test: `assert compute_content_hash(p) == compute_content_hash(p)` after adding/removing an unrelated frontmatter key.
**Warning signs:** Any Phase 3+ task that re-implements sha256 of a file body inline. Reject.

### Pitfall 5: `entity_aliases` `(kind, value)` not unique enough — ticker recycling collides on insert
**What goes wrong:** Naive `UNIQUE(kind, value)` constraint blocks the recycle case where two different `corp_code` rows both have `kind='ticker', value='099999'`.
**How to avoid:** **No uniqueness constraint on `(kind, value)`** — only the index `(kind, value, valid_from, valid_to)` for lookup speed. Application-level invariant (enforced by inserts in Phase 3): for any `(kind, value)` pair, all rows have non-overlapping `[valid_from, valid_to)` ranges. Postgres exclusion constraints (with `daterange` + `gist`) could enforce this at DB level — defer to v2.
**Warning signs:** Adding `UniqueConstraint("kind","value")` to the migration. Reject.

### Pitfall 6: `documents.source_urls` upsert race condition
**What goes wrong:** D-15 upsert pattern `array_append(documents.source_urls, EXCLUDED.source_url) WHERE NOT (... = ANY(...))` is not atomic across concurrent INSERTs of the same `id` from different sources.
**How to avoid:** Wrap upsert in a row-level `SELECT ... FOR UPDATE` inside a transaction, OR accept eventual consistency since Phase 1 `init-extensions.sql` doesn't enable advisory locks and concurrent collector writes are rare at this scale (1–10 collectors/day per source). Document as known limitation for v1; revisit if duplicates appear in `source_urls`.

## Code Examples

### Document upsert respecting D-15
```python
# Source: D-15 verbatim, Postgres UPSERT pattern
from sqlalchemy import text

UPSERT_DOC = text("""
INSERT INTO documents (id, body, source, vault_path, source_url, source_urls)
VALUES (:id, :body, :source, :vault_path, :source_url, ARRAY[:source_url])
ON CONFLICT (id) DO UPDATE SET
  last_seen_at = now(),
  source_urls = CASE
    WHEN EXCLUDED.source_url = ANY(documents.source_urls) THEN documents.source_urls
    ELSE array_append(documents.source_urls, EXCLUDED.source_url)
  END
RETURNING id, (xmax = 0) AS inserted;
""")
# `inserted` is True for fresh row, False for upsert hit — useful for stats.
```

### Recursive supersedes traversal (Phase 6 preview, but documented now)
```sql
-- "Find the final amendment of a given DART filing."
WITH RECURSIVE chain(src_id, dst_id, depth) AS (
    SELECT src_id, dst_id, 1
    FROM edges
    WHERE edge_type = 'supersedes' AND src_id = :starting_doc_id
  UNION ALL
    SELECT e.src_id, e.dst_id, c.depth + 1
    FROM edges e JOIN chain c ON e.src_id = c.dst_id
    WHERE e.edge_type = 'supersedes' AND c.depth < 20  -- cycle guard
)
SELECT dst_id FROM chain ORDER BY depth DESC LIMIT 1;
```

### Testcontainers session fixture
```python
# tests/conftest.py addition
# Source: testcontainers-python.readthedocs.io/
import pytest
from testcontainers.postgres import PostgresContainer
from sqlalchemy import create_engine
from alembic.config import Config
from alembic import command

@pytest.fixture(scope="session")
def pg_engine():
    with PostgresContainer(
        "tensorchord/vchord-suite:pg17-latest",
        username="test", password="test", dbname="test"
    ) as pg:
        url = pg.get_connection_url().replace("postgresql://", "postgresql+psycopg://")
        engine = create_engine(url)
        # Run migrations
        cfg = Config("src/db/alembic.ini")
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        yield engine
        engine.dispose()

@pytest.fixture
def pg_clean(pg_engine):
    """Per-test truncation — cheaper than container restart."""
    with pg_engine.begin() as conn:
        conn.execute(sa.text("TRUNCATE entities, entity_aliases, documents, chunks, edges, events, ingest_runs RESTART IDENTITY CASCADE"))
    return pg_engine
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `psycopg2` + SQLAlchemy 1.4 | `psycopg[binary]` (psycopg3) + SQLAlchemy 2.0 | SA 2.0 GA, 2023 | psycopg3 is async-capable, faster server-side prepared statements; pinned in pyproject already |
| pytest-postgresql (spawns local pg binary) | testcontainers[postgres] (Docker) | Docker ubiquity 2022+ | Hermetic, version-pinned to dev image |
| Bitemporal (system-time + valid-time) | Single-axis valid-time | D-09 user decision | Simpler queries, sufficient for personal/small-team scope |
| Self-reference column on `documents` for amendments | `edges` table with `edge_type='supersedes'` | D-05 user decision | Generalizes to other graph relations in Phase 7 |

**Deprecated/outdated:**
- SQLAlchemy 1.x patterns (`sessionmaker(autocommit=False, autoflush=False)`) — use 2.0 `Session`/`begin()` context managers.
- Alembic `revision --autogenerate` without explicit MetaData — pointless; produces empty migrations.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Korean ticker recycling cases exist but are not easily searchable; synthetic fixtures are acceptable for Phase 2 success criteria | Pitfall 1 | If user requires real-case proof, planner must add a Phase 3 task to discover one from `pykrx` historical listings |
| A2 | `psycopg[binary]>=3.2` is the right driver (not `psycopg2-binary`) | Standard Stack | Already pinned in Phase 1 ingest/mcp groups, so this is consistent — but Alembic env.py URL must use `postgresql+psycopg://` scheme not `postgresql+psycopg2://` |
| A3 | `chunks.embedding vector(1024)` is bge-m3's correct dimension | Pattern 2 | [VERIFIED: CLAUDE.md §4 "bge-m3 1024-d vectors"] — correct |
| A4 | `tensorchord/vchord-suite:pg17-latest` image is testcontainers-compatible (responds to `pg_isready`) | Pattern in conftest | If image lacks `pg_isready` or has nonstandard health, testcontainers wait_for fails. Fallback: standard `postgres:17-alpine` + `CREATE EXTENSION vector` only — but loses vchord_bm25 (Phase 3 problem). |
| A5 | A single Alembic migration file is acceptable to user (CONTEXT.md left this to discretion) | Alternatives Considered | Low — discretion explicitly granted in D-decisions |

## Open Questions

1. **Real Korean ticker-recycling case for fixture**
   - What we know: Public web search returns no concrete examples; KRX delisting reform articles dominate.
   - What's unclear: Whether KRX policy actually allows 6-digit reuse, and after how many years.
   - Recommendation: Use synthetic fixture in Phase 2; spawn a v2 spike task to mine `pykrx.get_market_ticker_list(date)` historical snapshots for empirical recycling cases.

2. **`alembic.ini` location: project root vs `src/db/`?**
   - What we know: Alembic looks for `alembic.ini` in CWD by default.
   - What's unclear: Whether running `alembic upgrade head` from project root is expected or `cd src/db && alembic ...`.
   - Recommendation: Place at `src/db/alembic.ini`, document `uv run alembic -c src/db/alembic.ini upgrade head` in plan task. Cleaner src layout; CI calls it via -c flag.

3. **`DATABASE_URL` env var convention**
   - What we know: Phase 1 has `POSTGRES_PASSWORD` env var only; no full URL convention yet.
   - What's unclear: Should `.env.example` (added Phase 1 §3) be extended now with `DATABASE_URL=postgresql+psycopg://stockwiki:${POSTGRES_PASSWORD}@127.0.0.1:5432/stockwiki`?
   - Recommendation: Yes — Phase 2 plan adds the line. Compositional with existing var.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | testcontainers + dev DB | ✓ | 29.3.0 | — |
| `uv` | Dependency install | ✓ | 0.11.7 | — |
| Python 3.12 | Runtime | ✓ | 3.12.3 | — |
| `tensorchord/vchord-suite:pg17-latest` image | Migration target | Pulled (Phase 1) | pg17-latest | `postgres:17-alpine` (loses vchord_bm25 — Phase 3 problem only) |
| `alembic` | Migrations | Not installed | 1.18.4 latest on PyPI | — (must add to `db` dep group) |
| `testcontainers[postgres]` | Integration tests | Not installed | 4.x | — (must add to `dev` dep group) |
| Running Postgres container | Manual smoke test | Reachable on 127.0.0.1:5432 (Phase 1 sets up) | 17 | — |

**Missing dependencies with no fallback:** `alembic`, `testcontainers[postgres]` — must be added to pyproject.toml as part of Phase 2 first task.

**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x (already pinned in `dev` group) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (already configured: `pythonpath=["src"]`, `testpaths=["tests"]`) |
| Quick run command | `uv run --group dev --group db pytest tests/test_content_hash.py tests/test_entity_resolve.py -x` |
| Full suite command | `uv run --group dev --group db pytest -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STORE-01 | `alembic upgrade head` creates 6 tables on fresh DB; `downgrade base` drops them | integration | `pytest tests/test_migration.py::test_upgrade_then_downgrade -x` | ❌ Wave 0 |
| STORE-01 | Re-running migration on already-migrated DB is no-op (idempotent) | integration | `pytest tests/test_migration.py::test_idempotent -x` | ❌ Wave 0 |
| STORE-02 | `compute_content_hash` returns same sha256 regardless of frontmatter changes | unit | `pytest tests/test_content_hash.py -x` | ❌ Wave 0 |
| STORE-02 | UPSERT with same `id` updates `last_seen_at` and accumulates `source_urls` | integration | `pytest tests/test_documents_dedup.py -x` | ❌ Wave 0 |
| ENT-01 | `entities.corp_code` is PRIMARY KEY; `current_ticker` is nullable | integration | `pytest tests/test_migration.py::test_entities_schema -x` | ❌ Wave 0 |
| ENT-02 | `resolve_entity("005930")` returns Samsung; rename fixture round-trips | integration | `pytest tests/test_entity_resolve.py::test_rename -x` | ❌ Wave 0 |
| ENT-02 | `resolve_entity("005930", as_of=split_date - 1day)` returns same corp_code as today (split test) | integration | `pytest tests/test_entity_resolve.py::test_split -x` | ❌ Wave 0 |
| ENT-02 | Ticker recycling: same 6-digit value, two corp_codes, non-overlapping valid ranges → `as_of` selects correct one | integration | `pytest tests/test_entity_resolve.py::test_ticker_recycle -x` | ❌ Wave 0 |
| ENT-02 | `resolve_entity("garbage")` returns None | unit | `pytest tests/test_entity_resolve.py::test_mismatch_returns_none -x` | ❌ Wave 0 |
| ENT-03 | INSERT amendment doc + supersedes edge → recursive CTE returns final doc | integration | `pytest tests/test_supersedes_edge.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** Quick command (content-hash + entity-resolve unit-ish tests, ~3s)
- **Per wave merge:** Full suite (incl. testcontainers, ~15-30s with cached image)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_migration.py` — upgrade/downgrade/idempotent migration tests
- [ ] `tests/test_content_hash.py` — D-13/D-14 hash determinism + frontmatter independence
- [ ] `tests/test_documents_dedup.py` — D-15 upsert behavior
- [ ] `tests/test_entity_resolve.py` — rename / split / ticker-recycle / 6-vs-8 digit branches
- [ ] `tests/test_supersedes_edge.py` — edge insert + recursive CTE traversal
- [ ] `tests/conftest.py` — add `pg_engine` (session-scoped testcontainers) + `pg_clean` (per-test TRUNCATE) fixtures
- [ ] `fixtures/entities/{rename,split,ticker_recycle}.yaml` — minimal entity + alias rows for each case
- [ ] Dependency add: `alembic>=1.18,<2`, `sqlalchemy>=2.0,<3`, `psycopg[binary]>=3.2`, `pgvector` to new `db` group; `testcontainers[postgres]>=4.8` to `dev` group

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — (no user auth in Phase 2) |
| V3 Session Management | no | — |
| V4 Access Control | no | — (DB role separation deferred) |
| V5 Input Validation | yes | All `resolve_entity` inputs validated by digit/length check (D-12); all SQL parameterized via SQLAlchemy `text(...)` bind params — no string concatenation |
| V6 Cryptography | yes | sha256 via stdlib `hashlib` — no hand-rolled crypto. Used only for content addressing, not as a security primitive. |

### Known Threat Patterns for Postgres + Python
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via `resolve_entity(value)` | Tampering | All SQL uses bind parameters (`:v`, `:asof`); no f-string interpolation into SQL |
| DB password leakage in logs | Information disclosure | Read from `${POSTGRES_PASSWORD}` env via `python-dotenv` (Phase 1 pattern); never log connection URL with password |
| Migration applied to wrong DB | Tampering | `env.py` requires `DATABASE_URL` env var explicitly — no default; CI must set it |
| Test container leaving open port | Information disclosure | Testcontainers binds to ephemeral port + container removed at session end. Never bind to 0.0.0.0. |
| `documents.body` containing untrusted content stored as TEXT | (handled in Phase 3+) | Phase 2 stores raw text only; XSS / injection defenses are Phase 5 (INGEST-08) when LLM consumes the body |

## Sources

### Primary (HIGH confidence)
- [Alembic Tutorial — alembic.sqlalchemy.org/en/latest/tutorial.html](https://alembic.sqlalchemy.org/en/latest/tutorial.html) — env.py online runner pattern, version 1.18 docs
- [Alembic on PyPI](https://pypi.org/project/alembic/) — verified 1.18.4 latest
- [Alembic Auto Generating Migrations](https://alembic.sqlalchemy.org/en/latest/autogenerate.html) — when to use vs hand-write
- [Alembic 1.18 release notes — github.com/sqlalchemy/alembic/releases](https://github.com/sqlalchemy/alembic/releases) — SQLAlchemy 2.0 bulk inspector
- `pip index versions alembic` — verified locally 2026-04-17 (returned 1.18.4)
- `docker --version` 29.3.0, `uv --version` 0.11.7, `python3 --version` 3.12.3 — verified locally
- `pyproject.toml` lines 27–39 — psycopg[binary], sqlalchemy>=2.0, pgvector already pinned in `ingest`/`mcp` groups
- `src/shared/frontmatter.py` — verified `fm.load(path).content` strips frontmatter cleanly
- `.planning/research/PITFALLS.md` lines 65–91 — Pitfall 3 ticker identity loss (verified)
- `.planning/research/ARCHITECTURE.md` §3 Postgres Schema — pre-existing schema sketch (Phase 2 supersedes with D-decisions)
- `docker-compose.yml` — verified `tensorchord/vchord-suite:pg17-latest` image and 127.0.0.1:5432 binding

### Secondary (MEDIUM confidence)
- [Testcontainers Python — testcontainers-python.readthedocs.io](https://testcontainers-python.readthedocs.io/) — PostgresContainer fixture pattern
- [Testcontainers getting started — testcontainers.com](https://testcontainers.com/guides/getting-started-with-testcontainers-for-python/)
- [pytest-postgresql on PyPI](https://pypi.org/project/pytest-postgresql/) — alternative considered, rejected
- [TestDriven.io — Handling Database Migrations with Alembic](https://testdriven.io/blog/alembic-database-migrations/) — expand-contract pattern guidance
- [Alembic large-set discussion #1259](https://github.com/sqlalchemy/alembic/discussions/1259) — file organization patterns

### Tertiary (LOW confidence)
- KRX ticker recycling specifics — **not found** via WebSearch (2026-04-17). Synthetic fixture recommended; flagged as Open Question 1.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Alembic 1.18 + SQLAlchemy 2.0 + psycopg3 verified live; testcontainers a 2026 consensus
- Architecture (schema, env.py, helpers): HIGH — locked decisions in CONTEXT.md, patterns map cleanly
- Pitfalls: HIGH — most derive from PITFALLS.md verified content; Pitfall 1 (synthetic fixture) is the one MEDIUM
- Testcontainers + vchord-suite image compatibility: MEDIUM — assumption A4, fallback documented
- Korean ticker recycling fixture: LOW — no public source; mitigation is synthetic fixture
- Security domain: HIGH — narrow surface, no auth/secret handling new to this phase

**Research date:** 2026-04-17
**Valid until:** 2026-05-17 (30 days — stable stack, low expected drift)
