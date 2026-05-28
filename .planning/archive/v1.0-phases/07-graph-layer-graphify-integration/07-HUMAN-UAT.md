---
status: diagnosed
phase: 07-graph-layer-graphify-integration
source: [07-VERIFICATION.md]
started: 2026-05-05T22:15:00Z
updated: 2026-05-06T07:30:00Z
---

## Current Test

[diagnosed — gaps escalated to phase 7.1 gap-closure]

## Tests

### 1. Live snapshot run produces 3 files
expected: `uv run stock graph snapshot` (no flags) → `vault/graph/<YYYY-MM-DD>/` contains `index.html`, `graph.json`, `GRAPH_REPORT.md`. `index.html` opens cleanly in browser and Obsidian; `graph.json` parses as valid JSON; `GRAPH_REPORT.md` is human-readable.
result: passed (commit 7cba9b8 fixed graphifyy 0.7.5 API call signatures; vault/graph/2026-05-06/ contains all 3 files)

### 2. Visualization quality (no supernova)
expected: Rendered `vault/graph/<date>/index.html` is interactive (zoom/pan/click). Communities visible, god-nodes labelled, edges legible. Not a hairball. If supernova → tighten `raw_windows_days` in `config/graphify.json`. (D-12 trap.)
result: failed — graph is empty (`nodes: []`, `links: []`). graphifyy 0.7.5 AST extraction only handles code files (.py/.js/...); the markdown vault produces no AST nodes. Semantic LLM extraction would require API key + per-token cost, which violates PROJECT.md "수집에 LLM 토큰 0" constraint.

### 3. Canonical queries return non-empty on live corpus
expected: Each of the 5 Python snippets in `vault/graph/README.md` runs in REPL on live (non-fixture) vault. Q1 returns recent events for portfolio holdings; Q2 returns non-empty catalyst chain; Q3 returns filings for populated sector; Q4 returns `[]` (graceful no-op until DART supersedes deferred task); Q5 returns notes+events for a populated ticker.
result: blocked — depends on populated SQL `edges` table on live ingest data; not testable until live ingest run + (separately) Q1-Q5 readers verified against Phase 7.1 SQL→graph pipeline.

## Summary

total: 3
passed: 1
issues: 1
pending: 0
skipped: 0
blocked: 1

## Gaps

### gap-1: SC-2 spirit — empty graph from markdown vault
status: failed
test_id: 2
issue: graphifyy AST extraction can't process markdown; semantic extraction needs paid LLM API key forbidden by PROJECT.md cost constraint
fix: Build graph directly from SQL `edges` table (already populated by Phase 7-02) via networkx, then reuse graphifyy's cluster/visualize layer. Eliminates dependency on graphifyy.detect/extract/collect_files; LLM-free.
escalated_to: phase 7.1 gap-closure (Phase 7.1)

### gap-2: MCP graph traversal acceleration (enhancement)
status: failed
test_id: 3
issue: SQL recursive queries for multi-hop neighborhoods are slow on cold cache; `get_related` becomes I/O-bound at depth>1
fix: Cache the graph.json snapshot in-memory in stock-mcp; expose `graph_query` tool for BFS/community lookups. Reuses Phase 7.1 SQL→graph artifact.
escalated_to: phase 7.1 gap-closure (Phase 7.1)
