---
quick_id: 260506-ix3
plan: 01
type: execute
status: complete
requirements: [REFACTOR-IX3]
completed: 2026-05-06
commit: 29fffa6
---

# Quick 260506-ix3: heartbeat.py refactor — extract _write_meta + _build_source_block

## One-liner

Refactored `src/ingest/heartbeat.py` to deduplicate YAML serialization, separate IO from logic in `record_source_run`, make `compute_enrich_alert_level` order-independent, and drop dead Python <3.11 ISO-Z compat — all 23 existing tests pass without modification.

## Lines-of-code delta

| Metric | Before | After | Δ |
|--------|--------|-------|---|
| Total lines | 205 (HEAD before) / 225 (working tree before) | 238 | +33 (vs working tree) / +13 net behavior |
| `yaml.safe_dump` call sites | 2 | 1 | −1 |
| `_atomic_write` call sites | 2 | 1 | −1 |
| `.replace("Z", "+00:00")` | 2 | 0 | −2 |
| `try/except` around `fromisoformat` | 1 | 0 | −1 |

Note: net additions come from new `_write_meta` + `_build_source_block` helpers and the `__all__` block + `_read_sources = read_sources` alias re-introduction. Logic in `record_source_run` and `write_disk_section` shrank to thin orchestrators.

## Changes applied

1. **`_write_meta(path, meta)`** added as single source of truth for `yaml.safe_dump(sort_keys=True, allow_unicode=True)` + `_atomic_write` boilerplate.
2. **`_build_source_block(source, stats, prev, extra, now)`** extracted as a pure function — no IO, no mutation of `prev` or `stats`. Block construction logic plus the `if source == "enrich"` alert_level branch live here.
3. **`record_source_run`** body slimmed to read → build → assign → `_write_meta`.
4. **`write_disk_section`** now uses `_write_meta`.
5. **`compute_enrich_alert_level`** rewritten as order-independent priority resolver: append candidate levels into `levels: list[str]`, then return `"warn" if "warn" in levels else "info" if "info" in levels else None`.
6. **Dropped Z-suffix compat:** removed both `.replace("Z", "+00:00")` calls and the `try/except (ValueError, TypeError)` around `datetime.fromisoformat`. Python 3.12 `fromisoformat` natively accepts `Z`; stored `last_run` is always written by `_now_iso()` which produces a valid ISO 8601 string.
7. **Public API restoration:** added `__all__` listing the 6 public symbols and re-introduced the `_read_sources = read_sources` backwards-compat alias.

## Public API + alias preservation (verified)

```text
$ grep -n '_read_sources = read_sources' src/ingest/heartbeat.py
66:_read_sources = read_sources

$ uv run python -c "from src.ingest.heartbeat import \
    HEARTBEAT_PATH_DEFAULT, HEARTBEAT_BODY, read_sources, record_source_run, \
    compute_enrich_alert_level, write_disk_section, _read_sources; print('ok')"
ok
```

All 6 `__all__` symbols and the `_read_sources` alias resolve.

## Test run output

```text
$ uv run pytest tests/test_heartbeat.py tests/test_heartbeat_enrich.py tests/test_heartbeat_extra.py -x -v
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.3, pluggy-1.6.0
collected 23 items

tests/test_heartbeat.py ............ (9 PASSED)
tests/test_heartbeat_enrich.py ........ (10 PASSED)
tests/test_heartbeat_extra.py .... (4 PASSED)

============================== 23 passed in 2.27s ==============================
```

**23 / 23 tests passed.** No test edits required.

## Done criteria — verified

- [x] `uv run pytest tests/test_heartbeat*.py -x -v` exits 0 — 23 passed.
- [x] `grep 'replace("Z"' src/ingest/heartbeat.py` returns nothing.
- [x] `grep '_write_meta\|_build_source_block' src/ingest/heartbeat.py` shows both helpers defined and referenced.
- [x] `grep -c 'yaml.safe_dump' src/ingest/heartbeat.py` returns `1`.
- [x] `__all__` lists 6 symbols (HEARTBEAT_PATH_DEFAULT, HEARTBEAT_BODY, read_sources, record_source_run, compute_enrich_alert_level, write_disk_section).
- [x] `_read_sources = read_sources` alias present.
- [x] Import smoke test succeeds.

## Deviations from plan

None — plan executed exactly as written. The pre-refactor file had `_read_sources` as the private internal name; per plan interface contract the public `read_sources` was added with `_read_sources` retained as a backwards-compat alias.

## Self-Check: PASSED

- Commit `29fffa6` exists: `git log --oneline | grep 29fffa6` → present.
- File `src/ingest/heartbeat.py` exists and contains both helpers.
- All 23 heartbeat tests green.
