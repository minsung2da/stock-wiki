---
phase: 3
slug: mcp-tool-surface-read-side
status: active
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-01
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `03-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9.0 (`[tool.pytest.ini_options]`, `pythonpath=["src"]`, markers: `slow`, `e2e`, `db`) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/Scripts/python.exe -m pytest tests/mcp_v2/ -q -m "not db"` |
| **Full suite command** | `.venv/Scripts/python.exe -m pytest tests/ -q` |
| **Estimated runtime** | ~10s quick (no-DB) · ~90s full (testcontainer `tensorchord/vchord-suite:pg17-latest`) |

> Note: `uv` is NOT on the Bash PATH in this environment — invoke pytest via `.venv/Scripts/python.exe -m pytest` (CONTEXT.md code_context).

---

## Sampling Rate

- **After every task commit:** Run `.venv/Scripts/python.exe -m pytest tests/mcp_v2/ -q -m "not db"` (server registration, injection, paths, error-model — fast, no DB)
- **After every plan wave:** Run `.venv/Scripts/python.exe -m pytest tests/mcp_v2/ -q` + `tests/db/` (full, incl. testcontainer hybrid_search)
- **Before `/gsd:verify-work`:** Full suite green AND `tests/mcp_v2/test_no_run_sql_guard.py` green
- **Max feedback latency:** ~10s (quick) / ~90s (full)

---

## Per-Task Verification Map

> Task IDs are assigned by the planner. Rows below bind each Success Criterion / locked Decision to its automated test. The planner MUST attach these test commands to the corresponding task `<acceptance_criteria>` and keep the SC/D coverage complete.

| Requirement | Behavior | Wave | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|------|------------|-----------------|-----------|-------------------|-------------|--------|
| SC#1 | server imports + registers exactly 10 tools; `mcp.run` stdio | 0→1 | — | stdout protocol clean (logs→stderr) | unit | `pytest tests/mcp_v2/test_server.py::test_all_tools_registered -x` | ❌ W0 | ⬜ pending |
| SC#2 | each tool returns its Pydantic model; empty case is a valid model | 1+ | — | typed output schema (no raw dict) | unit+db | `pytest tests/mcp_v2/test_tools_contract.py -x` | ❌ W0 | ⬜ pending |
| SC#3 | CI guard: no `run_sql`/arbitrary-SQL tool exists | 0/1 | T-SQL-escape | registry==10 locked names + AST no f-string SQL | unit (no DB) | `pytest tests/mcp_v2/test_no_run_sql_guard.py -x` | ❌ W0 | ⬜ pending |
| SC#4 | hybrid_search rejects ohlcv/macro/decision_cards sources; narrative-only | 2 | T-veto6 | numeric tables never embedded/searched | unit+db | `pytest tests/mcp_v2/test_hybrid_search.py -x` | ❌ W0 | ⬜ pending |
| SC#5 | narrative tools wrap body in XML delimiter + set injection flag | 1+ | T-prompt-inj | WRAP+FLAG, never block/strip | unit | `pytest tests/mcp_v2/test_injection.py -x` | ❌ W0 | ⬜ pending |
| D-01 | empty rows → empty model; bad ticker/corp_code/DB err → `McpToolError` raised | 1+ | — | loud failure, no silent None | unit+db | `pytest tests/mcp_v2/test_error_model.py -x` | ❌ W0 | ⬜ pending |
| D-02 | hybrid_search hit carries id+rrf_score+snippet, NO body_md | 2 | — | references-not-blobs | unit+db | `pytest tests/mcp_v2/test_hybrid_search.py::test_no_body_md -x` | ❌ W0 | ⬜ pending |
| D-03 | injection match flags (not blocks/strips) — pattern-ID snapshot | 1+ | T-prompt-inj | flag-only, body preserved | unit | `pytest tests/mcp_v2/test_injection.py::test_flag_not_block -x` | ❌ W0 | ⬜ pending |
| D-04 | search_filings default limit=50, `filed_at DESC`; ohlcv/flow require dates | 1 | T-token-DoS | bounded default response | unit+db | `pytest tests/mcp_v2/test_market.py -x` | ❌ W0 | ⬜ pending |
| Veto#13 | get_decision_card payload default excludes body_md; `view="both"` includes | 1 | — | serialize-time exclude | db | `pytest tests/mcp_v2/test_card.py -x` | ❌ W0 | ⬜ pending |
| get_note | path-traversal `..`/symlink rejected; `notes/private/` whitelist enforced | 1 | T-path-traversal | read-only, outside-whitelist rejected | unit | `pytest tests/mcp_v2/test_paths.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/mcp_v2/__init__.py` + `tests/mcp_v2/conftest.py` — re-declare `pg_clean`/`seeded_engine` (per-dir conftest scoping); seed `filings`/`news`(/`notes` if in scope) rows with non-NULL `body_tsv`/`body_embedding`/`bm25_tokens` for hybrid_search tests
- [ ] `tests/mcp_v2/test_no_run_sql_guard.py` — SC#3 (registry + AST), runnable WITHOUT DB
- [ ] `tests/mcp_v2/{test_server.py,test_tools_contract.py,test_hybrid_search.py,test_injection.py,test_error_model.py,test_market.py,test_card.py,test_paths.py}`
- [ ] Migration **0008** — `filings.bm25_tokens`/`news.bm25_tokens` INT[] + VectorChord-BM25 indexes + HNSW indexes on `body_embedding` (+ `notes` table & content embeddings IF note-search is in scope — see scope decision); adapt archive migration 0002 SQL
- [ ] **Backfill job** — tokenize `body_md`→`bm25_tokens`, embed→`body_embedding`, populate `body_tsv` for existing `filings`/`news` rows
- [ ] Re-add `mcp` + `ingest` dependency groups to `pyproject.toml`; `uv sync`
- [ ] `.mcp.json` at repo root (stdio server registration)
- [ ] Add `src/mcp_v2` to `[tool.hatch.build.targets.wheel].packages`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `.mcp.json` actually loads the server in Claude Code | SC#1 | Requires a live Claude Code MCP client handshake (not unit-testable) | Register `.mcp.json`, restart Claude Code, confirm the 10 tools appear and `get_filing` returns a known seeded filing |
| VectorChord-BM25 operator/function surface in pinned `pg17-latest` image | SC#4 | Depends on the live image's extension version (Open Question A1) | Wave-0 spike: `\dx` + `\df bm25_catalog.*` in testcontainer; lock RRF SQL to whatever the image exposes |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (plan-checker confirmed every SC/D maps to a task with an automated verify command)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (deps re-add, migration 0008, backfill, test scaffolding in 03-01/03-02)
- [x] No watch-mode flags
- [x] Feedback latency < 90s (full)
- [x] `nyquist_compliant: true` set in frontmatter

> `wave_0_complete` remains `false` until Wave 0 tasks execute green during /gsd:execute-phase.

**Approval:** approved 2026-06-01
