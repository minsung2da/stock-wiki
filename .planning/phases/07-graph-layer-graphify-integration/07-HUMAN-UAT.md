---
status: partial
phase: 07-graph-layer-graphify-integration
source: [07-VERIFICATION.md]
started: 2026-05-05T22:15:00Z
updated: 2026-05-05T22:15:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Live snapshot run produces 3 files
expected: `uv run stock graph snapshot` (no flags) → `vault/graph/<YYYY-MM-DD>/` contains `index.html`, `graph.json`, `GRAPH_REPORT.md`. `index.html` opens cleanly in browser and Obsidian; `graph.json` parses as valid JSON; `GRAPH_REPORT.md` is human-readable.
result: [pending]

### 2. Visualization quality (no supernova)
expected: Rendered `vault/graph/<date>/index.html` is interactive (zoom/pan/click). Communities visible, god-nodes labelled, edges legible. Not a hairball. If supernova → tighten `raw_windows_days` in `config/graphify.json`. (D-12 trap.)
result: [pending]

### 3. Canonical queries return non-empty on live corpus
expected: Each of the 5 Python snippets in `vault/graph/README.md` runs in REPL on live (non-fixture) vault. Q1 returns recent events for portfolio holdings; Q2 returns non-empty catalyst chain; Q3 returns filings for populated sector; Q4 returns `[]` (graceful no-op until DART supersedes deferred task); Q5 returns notes+events for a populated ticker.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
