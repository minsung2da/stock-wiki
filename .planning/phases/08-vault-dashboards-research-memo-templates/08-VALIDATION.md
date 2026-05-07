---
phase: 8
slug: vault-dashboards-research-memo-templates
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-06
updated: 2026-05-06
---

# Phase 8 — Validation Strategy

> Per-phase validation contract. Plans 08-01..08-04 cover NOTE-01/02/03,
> DASH-01/02/03/04, and NOTE-03 E2E. All `<automated>` verifications wired,
> Wave 0 (templates + parsers + Alembic 0005) shipped in Plan 01.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | `pyproject.toml` ([tool.pytest.ini_options]) |
| **Quick run command** | `uv run pytest tests/ingest/ tests/shared/test_thesis_frontmatter.py tests/shared/test_note_frontmatter.py tests/dashboards/ tests/templates/ -x` |
| **Full suite command** | `uv run pytest -x` |
| **Estimated runtime** | ~30 s (Phase 8 only); ~6 min full suite incl. testcontainers Postgres boot |

---

## Sampling Rate

- **After every task commit:** Run quick command above
- **After every plan wave:** Run full suite
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 8 s for unit tests; 30 s when Postgres fixture warm

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 8-01-01 | 01 | 1 | NOTE-01 | T-08-01-01 | Pydantic validation rejects unknown literals (`conviction: 'extreme'`) but tolerates extra keys (D-15) | unit | `uv run pytest tests/shared/test_thesis_frontmatter.py tests/shared/test_note_frontmatter.py` | ✅ | ✅ green |
| 8-01-02 | 01 | 1 | NOTE-01 | — | Templates parse cleanly with python-frontmatter | unit | `uv run pytest tests/templates/test_templates_parse.py` | ✅ | ✅ green |
| 8-01-03 | 01 | 1 | NOTE-02 | — | Alembic 0005 adds `documents.note_type` (Text NULL, indexed); backfill scoped to `source='private_note'` | unit | `uv run pytest tests/db/test_migration_0005.py` | ✅ | ✅ green |
| 8-01-04 | 01 | 1 | NOTE-01 | T-08-01-01 | parse_note dispatches by frontmatter `type`; ValidationError → `review_flag`, body still indexed | unit | `uv run pytest tests/ingest/parsers/test_note.py` | ✅ | ✅ green |
| 8-02-01 | 02 | 2 | DASH-04 | T-08-02-01 | Markdown table cell escapes `\|` and newline (DART titles can contain pipes) | unit | `uv run pytest tests/ingest/test_hub_builder.py` | ✅ | ✅ green |
| 8-02-02 | 02 | 2 | DASH-01 | T-08-02-04 | `dashboards/_data/prices.md` is gitignored derived cache; render is idempotent (no `datetime.now()` in payload) | unit | `uv run pytest tests/ingest/test_price_snapshot.py` | ✅ | ✅ green |
| 8-02-03 | 02 | 2 | DASH-04 | — | Worker post-cycle hook runs price_snapshot then hub_builder; failures logged but isolated (D-01) | unit | `uv run pytest tests/ingest/test_worker_hub_hook.py` | ✅ | ✅ green |
| 8-03-01 | 03 | 2 | DASH-01/02/03 | T-08-03-01 | DataviewJS structurally absent (settings + content); `enableDataviewJs: false` in plugin data.json | unit | `uv run pytest tests/dashboards/test_dataview_bootstrap.py` | ✅ | ✅ green |
| 8-03-02 | 03 | 2 | DASH-01/02/03 | T-08-03-01 | All 3 dashboards use bracket-form `row["_derived"].field` (DQL parser bug avoidance, regression-guarded) | unit | `uv run pytest tests/dashboards/` | ✅ | ✅ green |
| 8-03-03 | 03 | 2 | DASH-01/02/03 | — | Visual UAT — Obsidian renders Dataview tables without parser errors | manual | (UAT round 2 PASS, 2026-05-06) | ✅ | ✅ approved |
| 8-04-01 | 04 | 3 | DASH-03 + NOTE-03 (worker dispatch) | T-08-04-02 | events_this_week SQL uses parameterized binds (`:start_ts`, `:end_ts`); KST week boundary correct; priority sort 공시>거래정지>실적>뉴스 | unit | `uv run pytest tests/ingest/test_events_query.py tests/ingest/test_worker_note_dispatch.py` | ✅ | ✅ green |
| 8-04-02 | 04 | 3 | NOTE-03 | T-08-04-04 | thesis 1 ingest cycle → search hit (vault_path + chunks); invalid thesis still indexed with `note_schema_violation` review_flag | integration | `uv run pytest tests/ingest/test_note_e2e.py` | ✅ | ✅ green |
| 8-04-03 | 04 | 3 | (whole phase) | — | nyquist_compliant=true; full pytest green; COLL-07 CI guard (no anthropic/openai imports in src/ingest/) | integration | `uv run pytest -x && ! grep -rE "^(import\|from) (anthropic\|openai)" src/ingest/ src/collectors/` | ✅ | ✅ green |
| 8-04-04 | 04 | 3 | (phase gate) | — | Visual UAT — thesis flow + 3 dashboards + hub auto-gen + failure-mode + git hygiene | manual | Task 5 checkpoint | (n/a) | ⬜ pending UAT |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

All Wave 0 stubs were absorbed into Plan 01 — no separate scaffolding plan
was required. Test framework (pytest), conftest fixtures (`pg_engine`,
`pg_clean`, `tmp_vault`, `make_hub_inputs`), and Alembic migration chain
already in place from Phase 2/3/6/7. Plan 01 added:

- ✅ `tests/shared/test_thesis_frontmatter.py` — Pydantic schema stubs for NOTE-01
- ✅ `tests/ingest/parsers/__init__.py` + `test_note.py` — parse_note dispatch
- ✅ `tests/templates/__init__.py` + `test_templates_parse.py` — template parse safety
- ✅ `tests/db/test_migration_0005.py` — `documents.note_type` migration

Plan 02 added `tests/ingest/conftest.py` with the `make_hub_inputs` factory
(used by hub_builder + price_snapshot tests).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Obsidian renders Dataview tables without DQL parser errors | DASH-01/02/03 | Requires running Obsidian client; DQL parsing bug surfaces only at render time | Open vault in Obsidian → open `dashboards/portfolio.md`, `dashboards/watchlist.md`, `dashboards/events-this-week.md` → confirm tables render (round 2 PASS 2026-05-06) |
| Phase 8 page gate UAT | (Phase) | End-to-end thesis flow + dashboard visual + hub auto-gen + failure-mode + git hygiene; requires human-driven Obsidian + CLI walk | Plan 04 Task 5 — see PLAN.md `<how-to-verify>` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (absorbed into Plan 01)
- [x] No watch-mode flags
- [x] Feedback latency < 8s for unit tests, < 30s for integration
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-06 (automated gate; UAT pending — Plan 04 Task 5)
