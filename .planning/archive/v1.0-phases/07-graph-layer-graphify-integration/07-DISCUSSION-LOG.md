# Phase 7: Graph Layer & graphify Integration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-05
**Phase:** 07-graph-layer-graphify-integration
**Areas discussed:** Edge population pipeline, Edge taxonomy & tag policy, graphify invocation/scope/retention, Canonical subgraph queries

---

## Edge Population Pipeline

### Q1 — Where should edges get inserted during ingest?
| Option | Description | Selected |
|--------|-------------|----------|
| Post-pass module | New `src/ingest/edges.py` runs after parsers commit documents/chunks. | ✓ |
| Inline in each parser | Each parser inserts its own edges when it parses the doc. | |
| Hybrid by edge nature | Deterministic edges inline; INFERRED in separate post-pass. | |

### Q2 — Idempotency policy?
| Option | Description | Selected |
|--------|-------------|----------|
| ON CONFLICT DO NOTHING | Rely on Phase 2 composite UNIQUE; safe re-runs. | ✓ |
| Diff-and-sync per document | Compute desired set per `documents.id` and DELETE+INSERT. | |
| Append-only + content-hash skip | Skip if `documents.content_hash` already has edges. | |

### Q3 — How should the edge post-pass be invoked?
| Option | Description | Selected |
|--------|-------------|----------|
| Auto after `stock ingest` worker batch | `worker.py` calls `edges.populate(doc_ids)` at batch end. | ✓ |
| Separate CLI subcommand only | `stock graph build-edges` independent. | |
| Both: auto + scheduler hook | Belt-and-suspenders. | |

### Q4 — Failure handling?
| Option | Description | Selected |
|--------|-------------|----------|
| Soft-fail + ingest_runs.warning | Catch, log, write warning row; doc commit stands. | ✓ |
| Hard-fail the whole batch | Edge error rolls back entire batch. | |
| Fail only the failing doc's edges | Per-doc try/except. | |

### Q5 — Observability?
| Option | Description | Selected |
|--------|-------------|----------|
| ingest_runs row + heartbeat counts | `source='edges'` row with `extra` JSONB counts. | ✓ |
| Logs only | Just structured logging. | |
| Dedicated `edge_runs` table | New table for edge-specific stats. | |

---

## Edge Taxonomy & Tag Policy

### Q1 — Final `edge_type` enum + CHECK?
| Option | Description | Selected |
|--------|-------------|----------|
| Roadmap 6 + supersedes | Strict 6-value CHECK; new types require migration. | ✓ |
| Roadmap 6 + extensible namespace | Pattern CHECK allows new types without migration. | |
| No CHECK, document in code | Drop CHECK; rely on Python Literal. | |

### Q2 — How is EXTRACTED/INFERRED/AMBIGUOUS assigned?
| Option | Description | Selected |
|--------|-------------|----------|
| Per-edge-type policy table | Code constant maps each edge_type to its provenance. | ✓ |
| Per-row computed at insert | Each insert site sets its own tag. | |
| Tag column unused in ingest | Only graphify writes the tag. | |

### Q3 — Source of `note_ticker` edges?
| Option | Description | Selected |
|--------|-------------|----------|
| Frontmatter `tickers:` only | Deterministic, EXTRACTED. | ✓ |
| Frontmatter + body NER | Also scan body for ticker patterns. | |
| Frontmatter only + strict warning | Recommended + warn on body-only matches. | |

### Q4 — Derivation of `event_event` edges?
| Option | Description | Selected |
|--------|-------------|----------|
| Same-ticker temporal precedence | Sort `_derived.events` by date, link consecutive within 90d window. | ✓ |
| Phase 5 LLM `caused_by` links | Extend Phase 5 enrichment to ask Claude. | |
| Defer event_event to Phase 8/9 | Ship 5 edges only. | |

---

## graphify Invocation, Scope & Retention

### Q1 — How is graphify invoked?
| Option | Description | Selected |
|--------|-------------|----------|
| `stock graph snapshot` CLI wrapper | Wraps `graphify` CLI binary. | |
| Document `/graphify` skill usage only | No wrapper, just docs. | |
| Direct graphifyy library import | Import `graphifyy` Python API and orchestrate. | ✓ |

**Notes:** User chose direct library import over CLI wrapper — judgment call. CONTEXT.md D-10 captures the rationale: Python API gives single-transaction control over scope curation, output validation, and prune; Phase 9 scheduler still gets a one-line `uv run stock graph snapshot` entrypoint.

### Q2 — Input scope?
| Option | Description | Selected |
|--------|-------------|----------|
| `vault/notes/` + `notes/private/` + `vault/raw/` curated subset | Notes + recent N days of raw. | ✓ |
| Full vault | Everything under `vault/`. | |
| Notes only | Smallest, fastest. | |

### Q3 — Raw window configuration?
| Option | Description | Selected |
|--------|-------------|----------|
| Last 90 days, code constant | Single global default. | |
| Last 180 days, env-overridable | Default 180d, env override. | |
| Per-source tunable in config.json | DART/news/KIND/macro independently configurable. | ✓ |

### Q4 — Snapshot retention?
| Option | Description | Selected |
|--------|-------------|----------|
| Keep last N=14 dated dirs, gitignored | Auto-prune older; vault/graph/ in .gitignore. | ✓ |
| Keep all snapshots, gitignored | No auto-prune. | |
| Keep only latest, gitignored | Replace each time. | |

---

## Canonical Subgraph Queries

### Q1 — Which queries should Phase 7 ship?
| Option | Description | Selected |
|--------|-------------|----------|
| Positions × last-30-day events | Holdings × 30d events subgraph. | ✓ |
| Catalyst chain for ticker X | Walk `event_event` precedes-edges. | ✓ |
| Sector filing clusters | Sector + N-day filings + community detection. | ✓ |
| Supersedes chain | Walk `supersedes` edges back to origin. | ✓ |

### Q2 — Add a 5th?
| Option | Description | Selected |
|--------|-------------|----------|
| Add: Notes ↔ events around ticker X | User memos × recent events for a ticker. | ✓ |
| Stop at 4 | Four lenses cover the major needs. | |
| Add: Macro indicator ↔ sector cluster | Requires new `macro_sector` edge type — scope creep. | |

### Q3 — Expression form?
| Option | Description | Selected |
|--------|-------------|----------|
| Prose recipe + runnable Python snippet | README has Korean question + copy-pasteable Python. | ✓ |
| SQL views in `src/db/views/` | Each query as Postgres VIEW. | |
| Pure prose recipes only | Documents intent only. | |

---

## Claude's Discretion
None — every gray area presented received an explicit choice.

## Deferred Ideas
- `query_graph(question)` MCP tool — v2.
- graphify `--mcp` composition — out of scope.
- Body-text NER for mentions_ticker — Phase 8/9.
- Phase 5 LLM `caused_by` labelling — Phase 5 contract change deferred.
- New edge types (`macro_sector` etc.) — locked taxonomy.
- Multi-user / chunks.visibility — Phase 10 deferred.
- Incremental graphify (`--update`) — measure first.
- SQL views for canonical queries — snippet sufficient.
- Output format extensions (SVG, GraphML, Neo4j) — optional flag later.
