---
phase: 08-vault-dashboards-research-memo-templates
plan: 02
subsystem: ingest-hooks-hub-builder-price-snapshot
tags: [phase-8, hub, dashboards, ingest, idempotent, content-hash]
requires:
  - src/ingest/worker.py:ingest_run
  - src/shared/content_hash.py
provides:
  - src/ingest/hub_builder.py:render_hub
  - src/ingest/hub_builder.py:write_hub_if_changed
  - src/ingest/hub_builder.py:run
  - src/ingest/price_snapshot.py:render_prices_md
  - src/ingest/price_snapshot.py:run
  - dashboards/_data/prices.md (derived, gitignored)
  - vault/ingested/by-ticker/{corp_code}.md (derived, idempotent)
affects:
  - src/ingest/worker.py (post-cycle hook block added)
  - .gitignore (dashboards/_data/ exclusion)
tech_added: []
tech_patterns:
  - "Idempotent rebuild via content_hash substring pre-check (D-04)"
  - "Pure-function render + side-effecting write split (testability)"
  - "generated_at excluded from hash payload (Pitfall 1)"
  - "Best-effort post-cycle hooks with try/except logger.exception (D-01)"
  - "Markdown table cell escape for user-sourced strings (T-08-02-01)"
key_files_created:
  - src/ingest/hub_builder.py
  - src/ingest/price_snapshot.py
  - tests/ingest/conftest.py
  - tests/ingest/test_hub_builder.py
  - tests/ingest/test_price_snapshot.py
  - tests/ingest/test_worker_hub_hook.py
key_files_modified:
  - src/ingest/worker.py
  - .gitignore
decisions:
  - "render_hub is a pure function returning (body, content_hash). The hash payload uses yaml.safe_dump(sort_keys=True) over a fixed-key dict + the canonical body, so two renders at different wall-clock times produce hash-identical output (Pitfall 1)."
  - "write_hub_if_changed pre-checks via substring match `content_hash: <hex>` in the existing frontmatter — no full-text re-parse. mtime is preserved on no-op."
  - "Worker hook order: price_snapshot first, then hub_builder. Hub may consume prices.md in future iterations; reverse order would race."
  - "Best-effort hook failures are logged with logger.exception but never propagate. ingest_run guarantees its core contract (per-doc commits + heartbeat) regardless of hub/price status."
  - "vault_root passed as both vault_root + repo_root in the worker hook because in this project the repo root IS the vault root (raw/ is a subdirectory). Plan documented this as a TODO; matches existing worker call conventions."
  - "Markdown table cells escape `|` and newline (T-08-02-01) — DART titles can contain pipe characters."
metrics:
  duration: "≈18 min"
  tasks: 3
  tests_added: 15  # 8 hub_builder + 4 price_snapshot + 3 worker hook
  tests_pass: "19/19 (Phase 8 ingest suite)"
  files_created: 6
  files_modified: 2
  completed: 2026-05-07
---

# Phase 08 Plan 02: hub_builder + price_snapshot + worker post-cycle hook Summary

DASH-04 ticker hub auto-generation + DASH-01 평가액 데이터 소스 (D-08) landed. Three leaf utilities — `hub_builder.run`, `price_snapshot.run`, and a best-effort post-cycle hook block in `ingest_run` — together close the loop from ingest to Obsidian dashboards without any net-new CLI surface.

## Outcome

After `stock ingest run` completes:
1. `dashboards/_data/prices.md` is regenerated (gitignored derived cache).
2. Every `entities.corp_code` row triggers a hub rebuild; only changed hubs hit disk.
3. ingest_run's stats payload is unchanged; failures in (1) or (2) are logged but never poison the run.

DASH-04 wiring is now fully in place; the `## Valuation` section of each hub carries a Phase 10 D-12 hook (a `dataview` placeholder code block).

## render_hub Canonical Payload

`hashlib.sha256` over `yaml.safe_dump(sort_keys=True, allow_unicode=True)` of:

| Key | Source | Notes |
|-----|--------|-------|
| `type` | constant `"ticker_hub"` | discriminator |
| `ticker` | `HubInputs.ticker` | KRX 6-digit |
| `corp_code` | `HubInputs.corp_code` | DART 8-digit, path key |
| `corp_name` | `HubInputs.corp_name` | from entities.canonical_name |
| `sector` | `HubInputs.sector` | nullable |
| `latest_price` | `HubInputs.latest_price` | from prices.md |
| `market_cap` | `HubInputs.market_cap` | nullable |
| `as_of` | `HubInputs.as_of.isoformat()` | last trading day |

Concatenated with the canonical body (sections in fixed order). **`generated_at` and `content_hash` themselves are EXCLUDED** — they are written into the final frontmatter only, after the hash is computed.

## Hub Body Sections (D-03)

Fixed wording, fixed order:
1. `# {corp_name} ({ticker})` heading
2. Auto-generated banner with link to `notes/private/{ticker}/notes.md`
3. `## 최근 공시 (10건)` — 3-column table (날짜 | 제목 | 링크) or `_없음_`
4. `## 최근 뉴스 (10건)` — 4-column table (날짜 | 제목 | 소스 | 링크) or `_없음_`
5. `## 가격 트렌드 (30일)` — Unicode 7-bin sparkline `▁▂▃▄▅▆▇█`
6. `## Valuation` — Phase 10 D-12 placeholder (`dataview` code block)
7. `## Private Notes` — wiki-links to thesis/conviction/notes.md per ticker

## price_snapshot Frontmatter

```yaml
as_of: 2026-05-05            # last trading day, ISO
type: derived_prices         # Dataview discriminator
prices:                      # inline dict (Dataview-indexable, Pitfall 3)
  '005930': 72000
  '000660': 180000
```

Body has an `AUTO-GENERATED — DO NOT EDIT` HTML-comment banner + a human-readable Latest Close table. Idempotent: same `(rows, as_of)` produces the same string (no `datetime.now()` in render).

## Worker Hook Order

```python
record_source_run("ingest", stats, ...)   # existing heartbeat

# Phase 8 D-01 hooks (added):
try:
    price_snapshot.run(engine, repo_root=vault_root)
except Exception:
    logger.exception(...)

try:
    hub_builder.run(engine, vault_root=vault_root, repo_root=vault_root)
except Exception:
    logger.exception(...)

return stats
```

`price_snapshot` first because future hub_builder iterations will read `dashboards/_data/prices.md` to fill `latest_price` and `market_cap` per ticker without an extra DB roundtrip.

## Test Counts

| File | Tests | Coverage |
|------|------:|----------|
| `tests/ingest/test_hub_builder.py` | 8 | render_hub purity, hash idempotency (Pitfall 1), write_hub_if_changed (skip / overwrite / create), `run` review_flag for missing inputs (Pitfall 5), corp_code-based path (T-08-02-04), Valuation D-12 placeholder |
| `tests/ingest/test_price_snapshot.py` | 4 | render frontmatter + table, idempotency, run() writes to `dashboards/_data/prices.md`, .gitignore exclusion (Pitfall 6) |
| `tests/ingest/test_worker_hub_hook.py` | 3 | both hooks invoked once, hub failure isolated, price-snap failure does not block hub |
| **Total** | **15** | |

`tests/ingest/parsers/test_note.py` (4 tests) regresses cleanly → **19/19** in `tests/ingest/`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] worker.py monkeypatch target**
- **Found during:** Task 3 RED execution
- **Issue:** `worker.py` does `from ingest.edges import populate as edges_populate` and `from ingest.heartbeat import record_source_run` at module level. Patching the source modules (`ingest.edges`, `ingest.heartbeat`) had no effect — worker held its own bound references.
- **Fix:** Tests patch `worker_mod.edges_populate` and `worker_mod.record_source_run` directly. No production-code change.
- **Files modified:** `tests/ingest/test_worker_hub_hook.py` (during RED iteration, no extra commit).

**2. [Rule 3 - Blocking] price_snapshot.run engine=None handling**
- **Found during:** Task 2 GREEN
- **Issue:** Initial implementation short-circuited `if engine is None: return False` BEFORE calling `collect_prices`, defeating the test's `patch("ingest.price_snapshot.collect_prices", ...)`.
- **Fix:** `run()` now always calls `collect_prices`, and `collect_prices` itself returns `([], None)` when engine is None. Test patches now take effect.

### Other Deviations

None. Plan executed as written for all 3 tasks. Hash payload, body sections, hook order, and test counts match the plan exactly.

## Authentication Gates

None encountered — pure code work, no external services touched.

## Verification Evidence

```
$ uv run pytest tests/ingest/test_hub_builder.py \
                tests/ingest/test_price_snapshot.py \
                tests/ingest/test_worker_hub_hook.py \
                tests/ingest/
==================== 19 passed in 2.68s ====================
```

```
$ grep -q "dashboards/_data/" .gitignore && echo OK
OK
$ ! grep -E "^(import|from) (anthropic|openai)" \
        src/ingest/hub_builder.py \
        src/ingest/price_snapshot.py \
        src/ingest/worker.py && echo "no LLM imports"
no LLM imports
```

CI guard COLL-07 maintained: zero `anthropic`/`openai` imports in any of the 3 ingest modules.

## Self-Check: PASSED

**Files:**
- FOUND: src/ingest/hub_builder.py
- FOUND: src/ingest/price_snapshot.py
- FOUND: tests/ingest/conftest.py
- FOUND: tests/ingest/test_hub_builder.py
- FOUND: tests/ingest/test_price_snapshot.py
- FOUND: tests/ingest/test_worker_hub_hook.py
- FOUND: src/ingest/worker.py (modified)
- FOUND: .gitignore (modified — `dashboards/_data/` line present)

**Commits:**
- FOUND: 11beee0 (Task 1 RED)
- FOUND: 62001c4 (Task 1 GREEN)
- FOUND: b6ce3fc (Task 2 RED)
- FOUND: 644fa29 (Task 2 GREEN)
- FOUND: d62e1fe (Task 3 RED)
- FOUND: 8b71347 (Task 3 GREEN)

**Live state:**
- 19/19 ingest tests passing
- `.gitignore` contains `dashboards/_data/`
- worker.py post-cycle hook block present with `try/except logger.exception`
