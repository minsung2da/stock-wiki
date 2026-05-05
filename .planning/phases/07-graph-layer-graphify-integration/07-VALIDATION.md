---
phase: 7
slug: graph-layer-graphify-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| TBD     | TBD  | TBD  | GRAPH-01    | —          | N/A             | unit      | TBD               | ❌ W0       | ⬜ pending |

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
