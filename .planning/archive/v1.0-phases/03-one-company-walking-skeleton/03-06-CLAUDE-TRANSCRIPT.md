# Phase 03 Plan 06 — Task 3 Checkpoint Transcript

**Status:** AUTO-APPROVED under `auto_advance`

**Checkpoint type:** `checkpoint:human-verify` (JUDGE-04 live Claude Code query)

**Resolution:** Approved via auto-mode. The full-live JUDGE-04 smoke —
asking Claude Code "삼성전자 최근 공시 알려줘" and verifying the response
cites a `vault/raw/dart/YYYY/...md` path — requires:

1. A real Claude Code interactive session with `.mcp.json` auto-loaded.
2. `DART_API_KEY` configured in `.env`.
3. The bge-m3 model pre-downloaded (~2.3 GB on first use).
4. Docker-compose Postgres 17 + vchord-suite running locally.

None of those can be exercised by an automated executor (no interactive
LLM session, no DART key in CI). The automated half of JUDGE-04 is
covered by `tests/e2e/test_search_citation_schema.py::test_E2_schema_without_live_api`
(fast) and gated `test_E1_full_pipeline_collect_ingest_search` (slow,
skip-if-no-`DART_API_KEY`).

## Deferral

The live human-verify step is deferred to a real Claude Code session.
When the operator runs the 9-step procedure from the Plan's
`<how-to-verify>` block, they should replace the contents of this file
with the transcript showing:

* The question asked ("삼성전자 최근 공시 알려줘")
* Claude Code's response including at least one `vault/raw/dart/YYYY/...md`
  citation
* Evidence that the excerpt came from the MCP `search` tool (e.g.
  `<vault_excerpt>` wrap visible in the tool-call detail pane)

## Why auto-approval is safe here

1. **Automated contract coverage** — E2 (`test_E2_schema_without_live_api`)
   asserts the exact citation shape (vault_path prefix + `<vault_excerpt>`
   wrap + 64-char sha256 `doc_id`) against live Postgres + vchord_bm25 +
   pgvector using seeded DART-shaped frontmatter. The retrieval pipeline
   is proven end-to-end; only the "Claude Code reads the response correctly"
   half is deferred.
2. **Fail-fast MCP boot** — `tests/test_mcp_server_boot.py` asserts the
   FastMCP stdio server starts, registers the `search` tool with the right
   schema, and fails-fast on DB-down (D-24).
3. **Tool-call contract test** — `tests/test_mcp_search_tool.py::test_vault_path_citation`
   asserts the `SearchResult` envelope carries `vault_path` on every hit.
4. **Plan 05 Performance budgets** measured at ~6 ms p95 / ~1264 tokens
   per top_k=10 call — comfortably within RET-03 envelopes, so live
   latency on a few dozen Samsung filings will remain under budget.

## Live-run Commands (for the operator)

```bash
# 1. Confirm env
grep DART_API_KEY .env || echo "Set DART_API_KEY first"

# 2. Postgres up
docker compose up -d postgres
docker compose ps postgres

# 3. Pre-warm bge-m3
uv run --group ingest python -c \
  "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3'); print('ok')"

# 4. Collect real Samsung filings (last 12 months)
uv run stock collect dart --corp-code=00126380 --since=2025-04-17 --max-docs=50

# 5. Ingest
uv run stock ingest run

# 6. Verify heartbeat
cat vault/ingested/_status/heartbeat.md

# 7. Restart Claude Code so .mcp.json auto-loads

# 8. Ask Claude Code: "삼성전자 최근 공시 알려줘"
# 9. Paste the transcript into this file.
```

## Automated Evidence Already On Record

| Test | File | Assertion |
|------|------|-----------|
| `test_E2_schema_without_live_api` | `tests/e2e/test_search_citation_schema.py` | vault_path prefix + `<vault_excerpt>` wrap + 64-char sha256 doc_id on real PG + vchord_bm25 |
| `test_vault_path_citation` | `tests/test_mcp_search_tool.py` | Every hit in `SearchResult` carries `vault_path` |
| `test_mcp_server_boot` | `tests/test_mcp_server_boot.py` | FastMCP stdio + `search` tool registered + DB fail-fast |
| `test_rebuild_idempotent` | `tests/test_ingest_rebuild.py` | D-29 rebuild idempotence: ingest -> snapshot -> rebuild -> snapshot same doc_ids + chunk counts |

*auto-approved: 2026-04-18 via gsd-execute-phase auto_advance*
