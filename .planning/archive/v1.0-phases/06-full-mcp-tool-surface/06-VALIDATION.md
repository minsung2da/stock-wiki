---
phase: 6
slug: full-mcp-tool-surface
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-28
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (existing) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/stock_mcp -x -q` |
| **Full suite command** | `uv run pytest -x` |
| **Estimated runtime** | ~180 seconds (full, includes testcontainers Postgres + perf gates) |

---

## Sampling Rate

- **After every task commit:** Run quick command (target subset)
- **After every plan wave:** Run full suite
- **Before `/gsd-verify-work`:** Full suite must be green, including `tests/perf/test_mcp_perf_gates.py`
- **Max feedback latency:** ~30s for unit subsets, ~180s for full

---

## Per-Task Verification Map

> Plan IDs are tentative — planner refines. Threat refs filled by security gate in PLAN.md.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 6-01-01 | 01 portfolio-cutover | 1 | MCP-05 | — | path moved atomically; gitignore includes `notes/private/` | unit+grep | `uv run pytest tests/shared/test_portfolio_path.py -x` | ❌ W0 | ⬜ pending |
| 6-02-01 | 02 models | 1 | MCP-03,04,05,06,07,08,09 | — | Pydantic models forbid extras; OverviewResponse has nullable Phase 10 fields | unit | `uv run pytest tests/stock_mcp/test_models.py -x` | ❌ W0 | ⬜ pending |
| 6-02-02 | 02 errors | 1 | MCP-08 | T-6-01 (path traversal) | new ErrorCode constants exist; deny-list paths rejected | unit | `uv run pytest tests/stock_mcp/test_errors.py -x` | ❌ W0 | ⬜ pending |
| 6-03-01 | 03 snippets | 2 | MCP-04,06,07 | — | `<vault_excerpt>` wrapper applied; ≤200 chars; injection markers neutralized | unit | `uv run pytest tests/stock_mcp/test_snippets.py -x` | ❌ W0 | ⬜ pending |
| 6-04-01 | 04 get_filing | 2 | MCP-07 | T-6-02 (id forgery) | unknown id → `PATH_NOT_FOUND`; truncate flag set on >200K | integration | `uv run pytest tests/stock_mcp/test_get_filing.py -x` | ❌ W0 | ⬜ pending |
| 6-05-01 | 05 get_recent_events | 2 | MCP-04 | — | events list contains ID + snippet only (no body); bounded by `since` | integration | `uv run pytest tests/stock_mcp/test_get_recent_events.py -x` | ❌ W0 | ⬜ pending |
| 6-06-01 | 06 get_related | 2 | MCP-06 | — | BFS depth=1 default, max 2; cycles do not loop | integration | `uv run pytest tests/stock_mcp/test_get_related.py -x` | ❌ W0 | ⬜ pending |
| 6-07-01 | 07 get_portfolio_state | 2 | MCP-05 | T-6-03 (private leak) | reads `notes/private/portfolio.md`; never includes raw body | integration | `uv run pytest tests/stock_mcp/test_get_portfolio_state.py -x` | ❌ W0 | ⬜ pending |
| 6-08-01 | 08 get_ticker_overview | 3 | MCP-03 | — | events + portfolio + related_notes axes present; valuation/supply_demand/private_thesis = None; truncation_applied meta | integration | `uv run pytest tests/stock_mcp/test_get_ticker_overview.py -x` | ❌ W0 | ⬜ pending |
| 6-09-01 | 09 add_note path-validation | 2 | MCP-08 | T-6-01 (path traversal), T-6-04 (symlink escape) | only `vault/notes/` ∪ `notes/private/` allowed; `..` and symlink resolved before check | unit | `uv run pytest tests/stock_mcp/test_add_note_paths.py -x` | ❌ W0 | ⬜ pending |
| 6-09-02 | 09 add_note frontmatter | 2 | MCP-08 | T-6-05 (frontmatter injection) | `NoteFrontmatter` Pydantic; missing `type` → `INVALID_FRONTMATTER`; tickers normalized | unit | `uv run pytest tests/stock_mcp/test_add_note_frontmatter.py -x` | ❌ W0 | ⬜ pending |
| 6-09-03 | 09 add_note append+idempotent | 2 | MCP-08 | — | repeated identical body within ISO header → `idempotent=true`; `updated` field bumped | integration | `uv run pytest tests/stock_mcp/test_add_note_append.py -x` | ❌ W0 | ⬜ pending |
| 6-10-01 | 10 health | 2 | MCP-09 | — | `ingest_runs` SQL primary path; heartbeat fallback when DB down; staleness thresholds applied | integration | `uv run pytest tests/stock_mcp/test_health.py -x` | ❌ W0 | ⬜ pending |
| 6-11-01 | 11 docstring contract | 3 | MCP-03..MCP-09 | — | each tool docstring contains Behavior contract / Response shape / Errors / Performance budget | unit | `uv run pytest tests/stock_mcp/test_docstrings.py -x` | ❌ W0 | ⬜ pending |
| 6-12-01 | 12 ci-perf-gates | 3 | MCP-10 | — | per-tool N=20 sample → p95 latency <5s, p95 tokens <8k via `tiktoken` cl100k_base | perf | `uv run pytest tests/perf/test_mcp_perf_gates.py -x` | ❌ W0 | ⬜ pending |
| 6-12-02 | 12 fixture-vault | 1 | MCP-10 | — | `tests/fixtures/mcp-vault/` ≥10 tickers, ≥100 docs; testcontainers Postgres seeded | unit | `uv run pytest tests/fixtures/test_mcp_vault_seed.py -x` | ❌ W0 | ⬜ pending |
| 6-13-01 | 13 server-import | 3 | MCP-03..MCP-09 | — | new `tools/*.py` registered side-effect; `mcp.list_tools()` returns 8 tools | unit | `uv run pytest tests/stock_mcp/test_server_registration.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/stock_mcp/conftest.py` — shared testcontainers Postgres + alembic-upgrade fixture (extend existing if any)
- [ ] `tests/fixtures/mcp-vault/` — fixture vault directory with seed markdown
- [ ] `tests/perf/__init__.py` and `tests/perf/test_mcp_perf_gates.py` — perf harness scaffolding
- [ ] Add `tiktoken` to `[dependency-groups] dev` in `pyproject.toml` (Phase 6 RESEARCH §tiktoken)

*Existing infra: testcontainers + alembic upgrade pattern from Phase 2/3 reused — no framework install.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Docstrings render coherently in MCP inspector | MCP-03..MCP-09 | Inspector UI rendering not scriptable | Run `npx @modelcontextprotocol/inspector uv run stock-mcp serve`, click each tool, verify Behavior contract / Response shape / Errors / Performance budget visible |
| Claude Code end-to-end: judgment workflow returns vault-cited answer | MCP-03 | Requires real Claude Code session | In Claude Code: ask "005930 매수 판단" with stock-mcp connected, verify response cites vault paths under 8k tokens |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 180s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
