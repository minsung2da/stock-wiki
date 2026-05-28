---
phase: 06-full-mcp-tool-surface
plan: 03
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - src/db/migrations/versions/0003_relax_edges_check_for_phase6.py
  - tests/stock_mcp/conftest.py
  - tests/fixtures/mcp-vault/README.md
  - tests/fixtures/mcp-vault/notes/private/portfolio.md
  - tests/fixtures/mcp-vault/raw/dart/2026-04-01/sample-001.md
  - tests/fixtures/mcp-vault/raw/news/2026-04-01/sample-001.md
  - tests/fixtures/mcp-vault/raw/kind/2026-04-01/sample-001.md
  - tests/fixtures/mcp-vault/notes/sample-memo.md
  - tests/fixtures/mcp-vault/ingested/_status/heartbeat.md
  - scripts/build_mcp_vault_fixture.py
  - tests/fixtures/test_mcp_vault_seed.py
autonomous: true
requirements: [MCP-10]
must_haves:
  truths:
    - "tiktoken is added to dev dependency group"
    - "Alembic migration 0003 widens the edges.edge_type CHECK so non-supersedes edges insert successfully"
    - "tests/fixtures/mcp-vault/ contains ≥10 tickers and ≥100 documents (DART + news + KIND + notes)"
    - "tests/stock_mcp/conftest.py provides session-scoped fixture (mcp_vault_engine) that brings up testcontainers Postgres, runs alembic upgrade head, ingests the fixture vault, and yields (engine, vault_root, repo_root)"
    - "tests/stock_mcp/conftest.py provides function-scoped fixture (mcp_vault_isolated) that copies the session vault into tmp_path and sets STOCK_REPO_ROOT so write-test mutations stay isolated"
    - "Fixture build script is reproducible: deleting tests/fixtures/mcp-vault/ and re-running the script reproduces the same file set"
  artifacts:
    - path: "pyproject.toml"
      provides: "tiktoken dev dep"
      contains: "tiktoken"
    - path: "src/db/migrations/versions/0003_relax_edges_check_for_phase6.py"
      provides: "Widened ck_edge_type CHECK constraint"
      contains: "edge_type"
    - path: "tests/stock_mcp/conftest.py"
      provides: "mcp_vault_engine session fixture"
      contains: "scope=\"session\""
    - path: "tests/fixtures/mcp-vault/"
      provides: "≥100 doc fixture corpus"
      contains: "raw/dart"
  key_links:
    - from: "tests/stock_mcp/conftest.py"
      to: "tests/fixtures/mcp-vault/"
      via: "fixture path"
      pattern: "mcp-vault"
    - from: "tests/stock_mcp/conftest.py"
      to: "ingest worker"
      via: "alembic upgrade + ingest"
      pattern: "alembic upgrade|ingest_dir"
---

<objective>
Wave-0 test infrastructure for MCP-10 CI gates: fixture vault (≥10 tickers × ~100 docs), session-scoped Postgres + alembic + ingest fixture, dev dep tiktoken, and a small Alembic migration relaxing the edges CHECK constraint so non-supersedes test edges can be inserted.

Purpose: Plans 06-04..06-09 require a fully ingested fixture corpus + DB to run integration tests against. Without this scaffolding, every downstream tool plan would have to invent its own corpus — fragile and duplicative. This plan front-loads it.

Output: dependency added, migration committed, fixture corpus generated and committed, conftest fixture available for downstream test plans.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md
@.planning/phases/06-full-mcp-tool-surface/06-RESEARCH.md
@.planning/phases/06-full-mcp-tool-surface/06-VALIDATION.md
@pyproject.toml
@src/db/migrations/versions/0001_phase02_initial_schema.py
@src/db/migrations/versions/0002_phase03_chunking_columns.py
@tests/conftest.py

<interfaces>
Existing pg_engine session fixture (tests/conftest.py:51-86): testcontainers Postgres with vector + bm25 extensions + alembic upgrade head. **Reuse this** — do NOT duplicate the bring-up.

Existing edges schema (migration 0001 line ~153):
```sql
CHECK (edge_type IN ('supersedes')) ck_edge_type_phase2
```

Phase 6 fixture must insert edge_type values for `mentions`, `references`, `precedes`, `same_sector` — none currently allowed. Migration 0003 either DROP CHECK + replace with widened set, or DROP CHECK entirely (Phase 7 GRAPH-01 will redefine; lean toward "drop, leave open" since CHECK constraint is operational guard not security).
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add tiktoken dev dep + Alembic migration 0003 (relax edges CHECK)</name>
  <read_first>
    - pyproject.toml [dependency-groups] dev block
    - src/db/migrations/versions/0001_phase02_initial_schema.py (locate the CHECK constraint named `ck_edge_type_phase2` or equivalent on edges.edge_type)
    - src/db/migrations/versions/0002_phase03_chunking_columns.py (template for migration file shape)
  </read_first>
  <action>
    1. **pyproject.toml** — In `[dependency-groups]` `dev` array, add `"tiktoken>=0.8,<1"`. Preserve existing entries. After edit, run `uv lock` to refresh `uv.lock`.

    2. **Create src/db/migrations/versions/0003_relax_edges_check_for_phase6.py**:
       ```python
       """Phase 6: relax edges.edge_type CHECK so test fixtures can insert non-supersedes edges.

       Phase 7 (GRAPH-01) will redefine the edge taxonomy; until then we drop the
       CHECK so Phase 6 fixture corpus + tests for `get_related` can use realistic
       edge_type values (mentions, references, precedes, same_sector, supersedes).

       Revision: 0003
       Down: 0002
       """
       from alembic import op

       revision = "0003"
       down_revision = "0002"
       branch_labels = None
       depends_on = None

       def upgrade() -> None:
           op.execute('ALTER TABLE edges DROP CONSTRAINT IF EXISTS ck_edge_type_phase2')

       def downgrade() -> None:
           op.execute(
               "ALTER TABLE edges ADD CONSTRAINT ck_edge_type_phase2 "
               "CHECK (edge_type IN ('supersedes'))"
           )
       ```
       Verify the actual constraint name by reading 0001 migration file; if different (e.g., `ck_edges_edge_type`), use that name. Use `IF EXISTS` to make the upgrade idempotent.

    3. Run `uv run alembic upgrade head` against a local Postgres (or testcontainers) to verify migration applies without error.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv sync --group dev &amp;&amp; uv run python -c "import tiktoken; enc=tiktoken.get_encoding('cl100k_base'); assert len(enc.encode('test')) &gt; 0"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "tiktoken" pyproject.toml` returns ≥1 hit under `[dependency-groups]` dev (or equivalent dev group key).
    - `test -f src/db/migrations/versions/0003_relax_edges_check_for_phase6.py` succeeds.
    - `grep -nE "down_revision = \"0002\"|revision = \"0003\"" src/db/migrations/versions/0003_relax_edges_check_for_phase6.py` returns 2 hits.
    - `grep -n "DROP CONSTRAINT" src/db/migrations/versions/0003_relax_edges_check_for_phase6.py` returns 1 hit.
    - tiktoken import test (verify command) exits 0.
  </acceptance_criteria>
  <done>tiktoken installed in dev group; migration 0003 added; importable.</done>
</task>

<task type="auto">
  <name>Task 2: Build mcp-vault fixture corpus + scripts/build_mcp_vault_fixture.py</name>
  <read_first>
    - .planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md D-18 (fixture spec)
    - tests/fixtures/ (existing fixtures directory if any, for layout convention)
    - src/shared/frontmatter.py (FrontMatter, ProvenanceBlock structure for valid markdown frontmatter)
    - vault/raw/dart/ (ANY existing collected file — copy frontmatter shape)
    - templates/portfolio.md (portfolio.md frontmatter shape)
  </read_first>
  <action>
    Create a Python script `scripts/build_mcp_vault_fixture.py` that, given a target directory `tests/fixtures/mcp-vault/`, reproducibly writes the following file structure. The script accepts `--out tests/fixtures/mcp-vault` and `--clean` (rm -rf the target before writing) flags.

    **Required structure (≥10 tickers, ≥100 docs total):**

    1. `notes/private/portfolio.md` — fixture portfolio with:
       ```yaml
       ---
       holdings:
         - ticker: "005930"
           qty: 100
           avg_cost: 70000
         - ticker: "000660"
           qty: 50
           avg_cost: 130000
         - ticker: "035720"
           qty: 30
           avg_cost: 40000
       watchlist:
         - "035420"
         - "051910"
         - "207940"
         - "068270"
         - "323410"
         - "373220"
         - "247540"
       ---
       Test portfolio for MCP-10 CI gates.
       ```
       (3 holdings + 7 watchlist = 10 distinct tickers. Total tickers ≥10.)

    2. `raw/dart/{date}/{ticker}-{report_id}.md` — DART filings. For EACH of the 10 tickers, generate ≥3 DART filings (one per pblntf_ty A/B/D) → ≥30 DART docs. Frontmatter MUST include the FULL FrontMatter Pydantic schema fields used by Phase 3 ingest:
       ```yaml
       ---
       provenance:
         source: dart
         source_id: "20260101000001"
         corp_code: "00126380"
         ticker: "005930"
         url: "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260101000001"
         fetched_at: "2026-01-01T09:00:00+09:00"
         content_hash: "<sha256 of body>"
         trust_level: "official"
       ingest_state:
         injection_flags: []
       _derived:
         summary: "삼성전자 분기보고서 — 매출 70조, 영업이익 6조"
         tickers: ["005930"]
         event_type: "quarterly_report"
         catalysts: []
         numeric_facts: []
       ---
       <body — 200-2000 chars of plausible Korean DART text>
       ```
       Compute `content_hash` as `sha256(body_bytes)` for each generated body so `documents.id` (Phase 2 D-01) matches.

    3. `raw/news/{date}/{slug}.md` — ≥40 news articles spread across tickers (avg 4 per ticker). source: 'news', similar frontmatter.

    4. `raw/kind/{date}/{slug}.md` — ≥20 KIND events (trading_halt, mgmt_issue, disclosure_violation) for half the tickers.

    5. `notes/{slug}.md` — ≥10 user memo notes with NoteFrontmatter (type=note/thesis/journal). Spread across ≥5 tickers via `tickers:` field.

    6. `ingested/_status/heartbeat.md` — minimal heartbeat YAML compatible with `_read_sources` parser (src/ingest/heartbeat.py:34). Include all 5 sources (dart, krx, news, macro, kind) with realistic timestamps:
       ```yaml
       ---
       updated_at: "2026-04-26T18:00:00+09:00"
       sources:
         dart: { last_success: "2026-04-26T17:30:00+09:00", last_error: null }
         krx: { last_success: "2026-04-26T17:35:00+09:00", last_error: null }
         news: { last_success: "2026-04-26T17:50:00+09:00", last_error: null }
         macro: { last_success: "2026-04-26T17:00:00+09:00", last_error: null }
         kind: { last_success: "2026-04-26T17:45:00+09:00", last_error: null }
       ---
       ```

    7. `README.md` (in mcp-vault root) — explain that this fixture is auto-generated by `scripts/build_mcp_vault_fixture.py`; manual edits will be lost.

    Use `random.Random(seed=42)` for any randomized content so the script is byte-deterministic. Total document count target: 30 DART + 40 news + 20 KIND + 10 notes = 100 docs. Adjust counts upward if a tighter test needs it (≥100 minimum).

    **Run the script** and commit the generated tree.

    **Write tests/fixtures/test_mcp_vault_seed.py** with two tests:
    - `test_fixture_count`: walks `tests/fixtures/mcp-vault/` and asserts ≥10 distinct tickers (parsed from `provenance.ticker`) and ≥100 markdown files.
    - `test_fixture_frontmatter_valid`: each .md in raw/ parses through `read_frontmatter` and the resulting FrontMatter validates without error.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run python scripts/build_mcp_vault_fixture.py --out tests/fixtures/mcp-vault --clean &amp;&amp; uv run pytest tests/fixtures/test_mcp_vault_seed.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `find tests/fixtures/mcp-vault/raw -name '*.md' | wc -l` returns ≥90 (DART + news + KIND).
    - `find tests/fixtures/mcp-vault -name '*.md' | wc -l` returns ≥100.
    - `grep -lE "^ticker: \"[0-9]{6}\"|^  ticker: \"[0-9]{6}\"" tests/fixtures/mcp-vault/raw/dart/*/*.md | xargs -I{} sh -c 'grep -oE "ticker: \"[0-9]{6}\"" {}' | sort -u | wc -l` returns ≥10 distinct tickers.
    - `test -f tests/fixtures/mcp-vault/notes/private/portfolio.md` succeeds.
    - `test -f tests/fixtures/mcp-vault/ingested/_status/heartbeat.md` succeeds.
    - `test -f scripts/build_mcp_vault_fixture.py` succeeds and the script is reproducible (re-running with --clean produces identical files; verify with `git status` clean after second run).
    - Test command exits 0; both tests pass.
  </acceptance_criteria>
  <done>Fixture vault built, deterministic, committed; seed test green.</done>
</task>

<task type="auto">
  <name>Task 3: tests/stock_mcp/conftest.py — session fixture (Postgres + ingest of mcp-vault)</name>
  <read_first>
    - tests/conftest.py lines 51-86 (existing pg_engine session fixture)
    - src/ingest/worker.py (entry point for ingest — find function name, e.g., `ingest_directory` or `run_ingest`)
    - src/ingest/rebuild.py (rebuild from vault helper)
    - src/db/seed_name_aliases.py (alias seeding entry point)
    - src/db/seed_entities.py (entity seeding entry point)
  </read_first>
  <action>
    Create `tests/stock_mcp/conftest.py` with a session-scoped fixture that:
    1. Reuses `pg_engine` from `tests/conftest.py` (import via fixture composition: `def mcp_vault_engine(pg_engine, tmp_path_factory)`).
    2. Builds an isolated copy of `tests/fixtures/mcp-vault/` under `tmp_path_factory.mktemp("mcp-vault-session")` so tests that mutate (add_note) don't dirty the committed fixture.
    3. Seeds entity aliases (`uv run python -m src.db.seed_name_aliases` equivalent — call the function directly).
    4. Seeds entities from the fixture's `notes/private/portfolio.md` (call `seed_entities` function with `repo_root=<tmp copy root>`).
    5. Runs ingest over the fixture vault (programmatic call to ingest worker — locate the entry point in `src/ingest/worker.py` or `src/ingest/rebuild.py`; if a function `rebuild(engine, vault_root)` exists, call that).
    6. Inserts a few synthetic edges into the `edges` table for `get_related` testing — at least one `mentions` and one `supersedes` edge between fixture document ids. Pick the document_ids by querying `documents` after ingest. Document this in a helper function `_seed_test_edges(engine, ...)`.
    7. Inserts a few `ingest_runs` rows with realistic `started_at`/`finished_at` for testing health() — one row per source (dart, krx, news, macro, kind), with at least one stale (>26h ago) row to exercise stale path. (Pitfall 3: `ingest_runs` is otherwise empty in production; tests must seed.)
    8. Yields `(engine, vault_root, repo_root)` so downstream tool tests can construct paths cleanly.

    The fixture is `scope="session"` to amortize ingest cost (Pitfall 6).

    9. **REQUIRED — Add `mcp_vault_isolated` function-scoped fixture** for tests that mutate the vault (Plan 06-06 add_note tests). Implementation:
       ```python
       @pytest.fixture(scope="function")
       def mcp_vault_isolated(mcp_vault_engine, tmp_path):
           """Per-test writable copy of the mcp-vault fixture.

           Returns a tuple (engine, vault_root, repo_root) where vault_root and
           repo_root point to a freshly-copied tree under tmp_path. The DB engine
           is shared with the session fixture (read tests don't conflict with
           writes in this isolated tree).
           """
           import shutil
           # Source: the session-scoped tmp copy yielded by mcp_vault_engine
           session_engine, session_vault_root, session_repo_root = mcp_vault_engine
           dst_repo = tmp_path / "repo"
           shutil.copytree(session_repo_root, dst_repo)
           # Set STOCK_REPO_ROOT for the duration of the test so tools that call
           # repo_root() (Plan 06-02) see the isolated copy.
           import os
           prev = os.environ.get("STOCK_REPO_ROOT")
           os.environ["STOCK_REPO_ROOT"] = str(dst_repo)
           try:
               yield (session_engine, dst_repo / "vault", dst_repo)
           finally:
               if prev is None:
                   os.environ.pop("STOCK_REPO_ROOT", None)
               else:
                   os.environ["STOCK_REPO_ROOT"] = prev
       ```
       The fixture explicitly sets `STOCK_REPO_ROOT` so tool code (which calls `repo_root()` from `stock_mcp.repo_root`) resolves to the isolated copy automatically.

    Add a smoke test `tests/stock_mcp/test_conftest_smoke.py::test_session_fixture_yields_engine_with_documents` that asserts:
    - `SELECT COUNT(*) FROM documents` ≥ 90.
    - `SELECT COUNT(DISTINCT corp_code) FROM documents WHERE corp_code IS NOT NULL` ≥ 5 (since not every doc carries corp_code).
    - `SELECT COUNT(*) FROM edges` ≥ 2.
    - `SELECT COUNT(*) FROM ingest_runs` ≥ 5.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run pytest tests/stock_mcp/test_conftest_smoke.py -x -q -m "not slow"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "scope=\"session\"" tests/stock_mcp/conftest.py` returns ≥1 hit.
    - `grep -n "mcp_vault_engine" tests/stock_mcp/conftest.py` returns ≥1 hit (fixture name).
    - `grep -nE "ingest_runs|seed_test_edges" tests/stock_mcp/conftest.py` returns ≥2 hits.
    - `grep -E "^def mcp_vault_isolated" tests/stock_mcp/conftest.py` returns 1 hit (function-scoped fixture defined).
    - `grep -n "scope=\"function\"" tests/stock_mcp/conftest.py` returns ≥1 hit (mcp_vault_isolated marker).
    - `grep -n "STOCK_REPO_ROOT" tests/stock_mcp/conftest.py` returns ≥1 hit (env override for isolated tests).
    - Smoke test exits 0; all four assertions in the smoke test pass.
  </acceptance_criteria>
  <done>Session + function-scoped fixtures defined; per-test isolated tree honors STOCK_REPO_ROOT; smoke test green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Fixture corpus → ingest worker | Fixture is repo-controlled (no external input); test-only |
| Migration 0003 → production DB | Migration relaxes a CHECK constraint; only run in Phase 6 |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-6-03-01 | Tampering | Migration 0003 dropping CHECK | accept | CHECK was operational guard, not security; Phase 7 GRAPH-01 will redefine the taxonomy. Downgrade restores the original CHECK. |
| T-6-03-02 | Information Disclosure | Fixture portfolio committed to git | mitigate | Fixture portfolio uses public ticker symbols + synthetic qty/avg_cost; no real positions. Document this in fixture README.md. |
</threat_model>

<verification>
- Migration 0003 upgrades and downgrades cleanly on testcontainers Postgres.
- Fixture corpus is byte-deterministic across runs (Random(seed=42)).
- Session fixture + ingest completes in <60s (Pitfall 6: amortize cost).
</verification>

<success_criteria>
- Verify commands in all 3 tasks exit 0.
- Downstream Plan 06-04..06-09 can import `mcp_vault_engine` fixture.
</success_criteria>

<output>
Create `.planning/phases/06-full-mcp-tool-surface/06-03-SUMMARY.md` documenting:
- Fixture corpus stats (doc counts, ticker count)
- conftest fixture API (parameter contract for downstream)
- Migration 0003 rationale + Phase 7 follow-up
</output>
