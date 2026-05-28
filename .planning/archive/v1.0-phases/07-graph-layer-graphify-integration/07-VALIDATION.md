---
phase: 7
slug: graph-layer-graphify-integration
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-05
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Filled by gsd-planner during planning per RESEARCH §"Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + testcontainers-postgres |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ingest/test_edges.py tests/graph/ -x` |
| **Full suite command** | `uv run pytest tests/ -x` |
| **Estimated runtime** | ~60–120 seconds (testcontainers Postgres warm) |

---

## Sampling Rate

- **After every task commit:** Run quick command (edges + graph subset)
- **After every plan wave:** Run full suite
- **Before `/gsd-verify-work`:** Full suite green + 5 canonical queries return non-empty subgraph on fixture corpus
- **Max feedback latency:** ~120 seconds

---

## Per-Task Verification Map

*Filled by gsd-planner during planning. Each task in PLAN.md must map to a row here.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-T1  | 01 | 0 | GRAPH-01,02,03 | T-7-01 | Pinned dep version, no LLM keys | smoke | uv run --group graph python -c "import graphify"   | ✅          | ✅ green |
| 07-01-T2  | 01 | 0 | GRAPH-01,02,03 | —      | N/A             | scaffold | uv run pytest --collect-only tests/graph/ tests/db/test_migration_0004.py | ✅ | ✅ green |
| 07-02-T1  | 02 | 1 | GRAPH-01      | T-7-02 | SQL bind params; pre-validate abort | unit | uv run pytest tests/db/test_migration_0004.py -x | ✅ stub     | ⬜ pending |
| 07-02-T2  | 02 | 1 | GRAPH-01      | T-7-03 | SQL bind params; corp_code regex     | unit | uv run pytest tests/graph/test_edges_deterministic.py tests/graph/test_edges_derived.py tests/graph/test_edges_idempotency.py -x | ✅ stub | ⬜ pending |
| 07-02-T3  | 02 | 1 | GRAPH-01      | T-7-04 | Soft-fail truncate to 200 chars (no PII) | unit | uv run pytest tests/test_ingest_worker.py tests/graph/test_edges_idempotency.py::test_soft_fail_logs_to_failed_per_type -x | ✅ stub | ⬜ pending |
| 07-03-T1  | 03 | 2 | GRAPH-02      | T-7-05 | Symlink targets bound to repo_root; staging cleaned | integration | uv run pytest tests/graph/test_snapshot_cli.py -x | ✅ stub | ⬜ pending |
| 07-03-T2  | 03 | 2 | GRAPH-02      | T-7-06 | mtime-based filter; staging gitignored | unit | uv run pytest tests/graph/test_window.py -x | ✅ stub | ⬜ pending |
| 07-03-T3  | 03 | 2 | GRAPH-02      | —      | N/A             | smoke | uv run stock graph snapshot --dry-run | ❌ W0 | ⬜ pending |
| 07-04-T1  | 04 | 2 | GRAPH-03      | T-7-07 | SQL bind params; depth-cap | unit | uv run pytest tests/graph/test_canonical_queries.py -x | ✅ stub | ⬜ pending |
| 07-04-T2  | 04 | 2 | GRAPH-03      | —      | N/A             | smoke | uv run pytest tests/graph/test_canonical_queries.py::test_readme_parity_imports_match_snippets -x | ✅ stub | ⬜ pending |
| 07-04-T3  | 04 | 2 | GRAPH-01      | —      | N/A             | regression | uv run pytest tests/graph/test_get_related_regression.py -x | ✅ stub | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/ingest/test_edges.py` — stubs for GRAPH-01 edge derivation (per edge_type)
- [ ] `tests/graph/test_canonical_queries.py` — stubs for GRAPH-03 (5 queries return non-empty)
- [ ] `tests/graph/test_snapshot_cli.py` — stub for GRAPH-02 (`stock graph snapshot` smoke)
- [ ] `tests/graph/conftest.py` — fixture vault with seeded ticker/filing/note/event docs
- [ ] `tests/ingest/conftest.py` augmented if needed for edges fixtures

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| graphify HTML opens in Obsidian + browser and renders | GRAPH-02 | Visual rendering not automatable in CI | After `stock graph snapshot`, open `vault/graph/{date}/index.html` in Obsidian (drag) and a browser; confirm graph nodes/edges visible |
| 5 canonical queries return *legible* (not just non-empty) subgraphs on real corpus | GRAPH-03 | "Legible" is human judgment | Run each snippet from `vault/graph/README.md` against current vault; eyeball that node/edge counts are reasonable for the question (not 1 node, not the whole graph) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
