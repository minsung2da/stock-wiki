---
phase: 03-mcp-tool-surface-read-side
plan: 02
subsystem: testing
tags: [bge-m3, sentence-transformers, mecab-ko, bm25, halfvec, hybrid-search, notes-ingest, backfill, ast-guard, fastmcp, pgvector, vchord-bm25]

# Dependency graph
requires:
  - phase: 03-01
    provides: "notes + fundamentals tables, bm25_tokens INT[] on filings/news/notes, BM25/HNSW indexes (migration 0008 applied), run_log._ALLOWED_SOURCES + collector_runs.source CHECK widened to 7 sources (notes_ingest allowed), mcp+ingest dep groups (fastmcp 2.14.7, sentence-transformers 5.5.1, python-mecab-ko 1.3.7), src/mcp_v2 registered as wheel package"
  - phase: 01-collector-db-cutover
    provides: "filings/news halfvec(1024) body_embedding columns (left NULL), body_tsv 'simple' columns, resolve_entity, collector orchestration pattern (krx/__init__.py), dart narrative content_hash upsert pattern"
provides:
  - "src/mcp_v2/embedding.py — lazy bge-m3 in-process singleton (Embedder, get_default_embedder, LRU encode_query, EMBEDDING_MODEL_VERSION); torch import is lazy"
  - "src/mcp_v2/tokenizer.py — tokenize_ko(text) -> list[int] mecab-ko content-POS BLAKE2s hashing (index/query parity)"
  - "src/collectors/notes_ingest/ — ingest_notes (disk notes/private/**/*.md -> notes table) + upsert_note (ON CONFLICT path, content_hash dedup, Veto #8 whole content_md) + backfill_narrative (fills NULL filings/news body_embedding/bm25_tokens/body_tsv)"
  - "tests/mcp_v2/conftest.py — seeded_engine + seeded_narrative_engine (filings/news/notes with non-NULL tsv/embedding/bm25_tokens) for Wave-2 hybrid_search tests"
  - "tests/mcp_v2/test_no_run_sql_guard.py — SC#3 AST guard (enforced) + registry guard (staged for 03-06)"
affects: [03-03-tools, 03-04-tools, 03-06-hybrid_search, 03-05-fundamentals-peer_view, 04-analysis-runner]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "bge-m3 in-process embedder ported as an mcp_v2 sibling leaf (importable by the backfill OUTSIDE the MCP server context); torch import deferred into Embedder.__init__"
    - "mecab-ko content-POS (NNG/NNP/SL/SN) -> BLAKE2s-4byte positive-int32 token ids; SAME fn at index + query time"
    - "notes-ingest mirrors the krx collector orchestration (per-file try/except isolation, {total,inserted,updated,skipped,failed} stats, record_collector_run); narrative upsert mirrors dart db_writer (sha256 content_hash, ON CONFLICT DO UPDATE, whole body)"
    - "halfvec write via format_halfvec_literal('[x,..]') string + CAST(:vec AS halfvec) bind (ported archive _format_vec); body_tsv = to_tsvector('simple',...) (never 'korean')"
    - "SC#3 two-layer run_sql guard: enforced AST (every text() arg is a string Constant or module-level Name; matches text() and X.text()) + skip-tolerant registry (asyncio.run(mcp.get_tools()) — coroutine in fastmcp 2.14.7)"

key-files:
  created:
    - "src/mcp_v2/__init__.py"
    - "src/mcp_v2/embedding.py"
    - "src/mcp_v2/tokenizer.py"
    - "src/collectors/notes_ingest/__init__.py"
    - "src/collectors/notes_ingest/db_writer.py"
    - "src/collectors/notes_ingest/backfill.py"
    - "tests/mcp_v2/__init__.py"
    - "tests/mcp_v2/conftest.py"
    - "tests/mcp_v2/test_no_run_sql_guard.py"
    - "tests/mcp_v2/test_tokenizer.py"
    - "tests/collectors/test_notes_ingest.py"
  modified: []

key-decisions:
  - "embedding.py/tokenizer.py ported verbatim from archive ingest/* as mcp_v2 siblings (RESEARCH §Recommended Structure) — kept out of tools/ so the notes-ingest backfill imports them without spinning the MCP server"
  - "encode_query lazy import of sentence_transformers stays inside Embedder.__init__ so importing the module + EMBEDDING_MODEL_VERSION never pulls torch (asserted in test)"
  - "notes-ingest excludes notes/private/portfolio.md (config parsed by Portfolio.load, not a searchable thesis memo)"
  - "upsert_note is idempotent: unchanged content_hash → 'skipped' (only updated_at bumps, no re-embed) — re-embedding burns bge-m3 cycles for no gain"
  - "Embedder is injectable into ingest_notes/backfill_narrative so DB tests use a deterministic 1024-d stub vector and never download bge-m3 (~2GB)"
  - "SC#3 registry test awaits get_tools() via asyncio.run (it is a coroutine in fastmcp 2.14.7, NOT the .keys() sync accessor the RESEARCH skeleton assumed); skip-if-ImportError until 03-06 wires mcp_v2.server"

patterns-established:
  - "mcp_v2 leaf utilities (embedding/tokenizer) reused by the collectors layer for the Wave-0 backfill"
  - "AST static guard over a source tree (text() arg discipline) as a no-DB CI gate, paralleling tests/test_import_guard.py"

requirements-completed: [SC#3, SC#4, D-05]

# Metrics
duration: 22 min
completed: 2026-06-07
---

# Phase 3 Plan 02: MCP Read-Side Wave-0 Data + Test Scaffolding Summary

**Ported the bge-m3 embedder + mecab-ko tokenizer leaves into `src/mcp_v2/`, built the notes-ingest job (disk `notes/private/*.md` → `notes` table) plus the embedding/tsv/bm25 backfill for existing filings/news (D-05), and stood up the `tests/mcp_v2/` package with seeded narrative fixtures and the enforced SC#3 run_sql AST guard.**

## Performance

- **Duration:** 22 min
- **Started:** 2026-06-07
- **Completed:** 2026-06-07
- **Tasks:** 3
- **Files modified:** 11 (all created)

## Accomplishments
- `src/mcp_v2/embedding.py` + `src/mcp_v2/tokenizer.py` ported verbatim from the archive (`archive/llm-wiki-2026-04:src/ingest/{embedder,tokenizer}.py`): a lazy bge-m3 `Embedder` singleton with `get_default_embedder()` + LRU `encode_query()` + `EMBEDDING_MODEL_VERSION = "BAAI/bge-m3@v1"` (sentence_transformers import deferred into `__init__` so the version constant imports torch-free), and `tokenize_ko(text) -> list[int]` content-POS BLAKE2s hashing with index/query parity. mecab-ko verified working on Windows (NNP/NNG/SL/SN tags produced; josa JKG + punctuation SY/SF dropped).
- `src/collectors/notes_ingest/` (3 modules): `db_writer.upsert_note` (parameterized `ON CONFLICT (path) DO UPDATE`, sha256 `content_hash` dedup, whole `content_md` TEXT per Veto #8, `content_emb` halfvec + `bm25_tokens` + `body_tsv to_tsvector('simple',...)`), `ingest_notes` orchestrator (rglob `notes/private/**/*.md`, per-file isolation, `{total,inserted,updated,skipped,failed}` stats, `record_collector_run(engine, "notes_ingest", ...)`, excludes `portfolio.md`), and `backfill_narrative` (batch-embed + tokenize `body_md`, parameterized `UPDATE filings/news SET body_embedding=CAST(:vec AS halfvec), bm25_tokens=:toks, body_tsv=to_tsvector('simple', body_md)` for rows where either signal is NULL).
- `tests/mcp_v2/` package: `conftest.py` re-declares `seeded_engine` (per-dir scoping) and adds `seeded_narrative_engine` seeding filings/news/notes rows with non-NULL `body_tsv`/`body_embedding|content_emb`/`bm25_tokens` (the Wave-2 hybrid_search corpus); `test_no_run_sql_guard.py` implements the SC#3 two-layer guard — the AST layer ENFORCED (every `text()` arg is a string constant or module-level name; f-string/`%`/`+`/`.format` rejected), the registry layer (==10 locked names, no `run_sql`/`execute_sql`/`raw_sql`/`query`) skip-tolerant until 03-06.
- `tests/collectors/test_notes_ingest.py` — 6 db-marked tests green against the live testcontainer: ingest writes a notes row with non-NULL `content_emb`+`bm25_tokens`+`body_tsv`, stores whole `content_md` verbatim, excludes `portfolio.md`, records a `notes_ingest` collector_runs row, and is idempotent on unchanged content; backfill fills a NULL filings embedding/tokens/tsv.

## Task Commits

Each task was committed atomically:

1. **Task 1: Port embedding.py + tokenizer.py leaf utils** - `10b942e` (feat)
2. **Task 2: Notes-ingest job + filings/news embedding/tsv/bm25 backfill (D-05)** - `35c58e3` (feat)
3. **Task 3: tests/mcp_v2 package + seeded fixtures + SC#3 run_sql CI guard** - `22f736c` (test)

**Plan metadata:** committed with this SUMMARY (docs).

## Files Created/Modified
- `src/mcp_v2/__init__.py` - Package docstring; explains the Wave-0 leaf utilities + sibling placement rationale.
- `src/mcp_v2/embedding.py` - Lazy bge-m3 `Embedder` singleton, `get_default_embedder`, LRU `encode_query`, `EMBEDDING_MODEL_VERSION`; lazy torch import.
- `src/mcp_v2/tokenizer.py` - `tokenize_ko` mecab-ko content-POS BLAKE2s int32 tokenizer (index/query parity).
- `src/collectors/notes_ingest/db_writer.py` - `upsert_note` parameterized notes upsert (content_hash dedup, halfvec literal CAST, body_tsv 'simple'); `format_halfvec_literal`.
- `src/collectors/notes_ingest/__init__.py` - `ingest_notes` orchestrator (disk → notes table, stats, record_collector_run, portfolio.md excluded).
- `src/collectors/notes_ingest/backfill.py` - `backfill_narrative` (fills NULL body_embedding/bm25_tokens/body_tsv on existing filings + news).
- `tests/mcp_v2/__init__.py` - empty package marker.
- `tests/mcp_v2/conftest.py` - `seeded_engine` + `seeded_narrative_engine` fixtures.
- `tests/mcp_v2/test_no_run_sql_guard.py` - SC#3 AST guard (enforced) + registry guard (staged) + 2 guard self-tests.
- `tests/mcp_v2/test_tokenizer.py` - 5 no-DB tokenizer + torch-free-version-import tests.
- `tests/collectors/test_notes_ingest.py` - 6 db-marked ingest + backfill tests (deterministic stub embedder).

## Decisions Made
- **mcp_v2 leaves as siblings:** `embedding.py`/`tokenizer.py` live directly under `src/mcp_v2/` (not under `tools/`) so the collectors-layer backfill imports them without the FastMCP server — RESEARCH §Recommended Structure.
- **Torch-free version import:** the `from sentence_transformers import SentenceTransformer` stays inside `Embedder.__init__`; `test_embedder_version_constant_imports_without_torch` asserts importing the module + reading `EMBEDDING_MODEL_VERSION` does not eagerly load torch.
- **Injectable embedder:** `ingest_notes` and `backfill_narrative` accept an `embedder=` param so DB tests pass a deterministic `_StubEmbedder` (constant 1024-d vector) and never download bge-m3.
- **Idempotent ingest:** unchanged `content_hash` → `"skipped"` (only `updated_at` bumps), avoiding a wasted re-embed.
- **portfolio.md excluded** from the searchable notes corpus (it is collector scope config, not a thesis memo).
- **get_tools() is a coroutine** in fastmcp 2.14.7 — the registry test awaits via `asyncio.run`, correcting the RESEARCH skeleton's `mcp.get_tools().keys()` assumption (verified empirically).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Incorrect tokenizer behavioral assertion (standalone '의')**
- **Found during:** Task 1 (running `test_tokenize_ko_drops_non_content_pos`).
- **Issue:** The first draft asserted `tokenize_ko("의 의 의") == []` on the assumption that '의' is always a 조사 (dropped). mecab actually tags a STANDALONE '의' as `NNG` (content noun) and only tags the ATTACHED '의' in '삼성전자의' as `JKG` (dropped). The test failed (`[376962670, 376962670] != []`).
- **Fix:** Replaced with a verified-behavior assertion: pure punctuation (`"!!! ??? , ."` → SY/SF) tokenizes to `[]`, AND `tokenize_ko("삼성전자의 영업이익") == tokenize_ko("삼성전자 영업이익")` (the attached JKG '의' is stripped, so the josa-bearing phrase yields the same content-token set). Confirmed mecab POS tagging via a direct probe before rewriting.
- **Files modified:** `tests/mcp_v2/test_tokenizer.py`
- **Verification:** `pytest tests/mcp_v2/test_tokenizer.py` → 5 passed.
- **Committed in:** `10b942e` (Task 1 commit)

**2. [Rule 1 - Bug] seeded_narrative_engine used non-existent `news.ticker` column**
- **Found during:** Task 3 (verifying the `seeded_narrative_engine` fixture against the live DB).
- **Issue:** The news INSERT referenced a `ticker` column; the `news` table (migration 0006) has `tickers` (TEXT[] NOT NULL, default `{}`), no scalar `ticker`. Fixture setup raised `psycopg.errors.UndefinedColumn: column "ticker" of relation "news" does not exist`.
- **Fix:** Changed the news INSERT to `tickers` bound as a Python list `["005930"]`.
- **Files modified:** `tests/mcp_v2/conftest.py`
- **Verification:** A temporary db-marked check confirmed all three seeded tables carry non-NULL tsv/embedding/bm25_tokens; the temp file was then removed (workspace hygiene).
- **Committed in:** `22f736c` (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs — a wrong test assertion and a schema-column mismatch, both in test code). No production-code deviations.
**Impact on plan:** Both fixes were necessary for the tests to be correct and green. No scope creep — the embedding/tokenizer leaves, notes-ingest + backfill jobs, fixtures, and SC#3 guard match the plan exactly.

## Issues Encountered
- **mecab console garbling on Windows:** the cp949 stdout codepage renders Korean surface forms as mojibake in Bash captures, but tokenization is correct (POS tags + token ids verified). No code impact — purely a console display artifact.
- **Long db-test runtime (~352s for Task 2):** dominated by the testcontainer cold start + `alembic upgrade head` (0001→0008), not the tests themselves; the `_StubEmbedder` keeps the actual ingest/backfill work sub-second (no bge-m3 download). The no-DB mcp_v2 suite runs in 0.19s.
- **mypy not re-run:** consistent with Plan 03-01's note — mypy is not a green pre-commit/CI gate here (pre-commit = gitleaks + ruff). ruff check + ruff format are clean on all 11 new files.

## Verification Results
- `tests/mcp_v2/test_tokenizer.py` — 5 passed (no DB, no model load).
- `tests/mcp_v2/test_no_run_sql_guard.py` — 3 passed + 1 skipped (registry staged for 03-06) with `-m "not db"`; full no-DB mcp_v2 suite: 8 passed, 1 skipped in 0.19s.
- `tests/collectors/test_notes_ingest.py` — 6 passed with `-m db` (live Postgres at migration 0008).
- `seeded_narrative_engine` confirmed to seed filings/news/notes with non-NULL `body_tsv`/`body_embedding`/`content_emb`/`bm25_tokens` (Plan 06 hybrid_search precondition).
- `tests/test_import_guard.py` — 4 passed (notes_ingest imports neither anthropic nor openai; COLL-07 intact — embeddings are in-process sentence-transformers).
- ruff check + ruff format-check clean on all created files.

## Known Stubs
None. The embedder/tokenizer are real ports; the notes-ingest + backfill write real rows verified against live Postgres. The `_StubEmbedder` is a TEST double (deterministic vector to skip the bge-m3 download), not a production stub. The SC#3 registry test SKIPS (does not return fake data) until 03-06 wires `mcp_v2.server` — by design, not a stub.

## Threat Flags
None beyond the plan's threat model.
- **T-SQL-escape (mitigate):** `test_no_fstring_sql_in_mcp_v2` enforces the AST discipline now; the registry layer (no `run_sql`-class tool) is staged for 03-06.
- **T-veto6 (mitigate):** only narrative (filings/news/notes `body_md`/`content_md`) is embedded; ohlcv/macro/fundamentals are never touched by the backfill or ingest.
- **T-03-03 (mitigate):** sha256 `content_hash` + `ON CONFLICT (path) DO UPDATE` makes ingest idempotent (primitive dedup, not security).
- **T-03-04 (accept):** notes load to LOCAL Postgres only; `notes/private/` is gitignored, never committed (D-05).

## User Setup Required
None. Postgres is running at migration 0008; `.env` carries `DATABASE_URL`. The first real (non-test) `ingest_notes`/`backfill_narrative` run will download bge-m3 (~2GB) to the HuggingFace cache; tests avoid this via the stub embedder.

## Next Phase Readiness
- The mcp_v2 embedding + tokenizer leaves are importable and used by the backfill; Plan 06 `hybrid_search`/`retrieval.py` will reuse `encode_query` + `tokenize_ko` at query time (index/query parity guaranteed by the same functions).
- `seeded_narrative_engine` gives Wave-2 hybrid_search tests a ready non-NULL corpus across all three narrative tables.
- The SC#3 AST guard is live and will grow over whatever `src/mcp_v2/**.py` Plans 03-03/04/06 add; the registry assertion flips from skip to enforced the moment `mcp_v2.server` exists (03-06).
- notes-ingest + backfill exist so filings/news/notes can carry non-NULL embeddings/bm25_tokens (D-05 → SC#4 full narrative coverage).
- No blockers.

## Self-Check: PASSED

All 11 created files exist on disk (embedding.py, tokenizer.py, mcp_v2/__init__.py, notes_ingest/{__init__,db_writer,backfill}.py, tests/mcp_v2/{__init__,conftest,test_no_run_sql_guard,test_tokenizer}.py, tests/collectors/test_notes_ingest.py — all FOUND). All three task commits (`10b942e`, `35c58e3`, `22f736c`) present in git log. Task 1 tokenizer tests 5/5 green; Task 2 notes-ingest db tests 6/6 green; Task 3 guard 3 passed + 1 skipped (no DB). ruff clean on all changed files.

---
*Phase: 03-mcp-tool-surface-read-side*
*Completed: 2026-06-07*
