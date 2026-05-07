---
phase: 08-vault-dashboards-research-memo-templates
reviewed: 2026-05-07T15:17:44Z
depth: standard
files_reviewed: 30
files_reviewed_list:
  - .gitignore
  - .obsidian/community-plugins.json
  - .obsidian/plugins/dataview/data.json
  - dashboards/events-this-week.md
  - dashboards/portfolio.md
  - dashboards/watchlist.md
  - src/db/migrations/versions/0005_phase08_note_type.py
  - src/ingest/events_query.py
  - src/ingest/hub_builder.py
  - src/ingest/parsers/note.py
  - src/ingest/price_snapshot.py
  - src/ingest/worker.py
  - src/shared/frontmatter.py
  - templates/notes/journal.md
  - templates/notes/thesis.md
  - tests/dashboards/test_dataview_bootstrap.py
  - tests/dashboards/test_events_dashboard_skeleton.py
  - tests/dashboards/test_portfolio_dashboard_skeleton.py
  - tests/dashboards/test_watchlist_dashboard_skeleton.py
  - tests/db/test_migration_0005.py
  - tests/ingest/conftest.py
  - tests/ingest/parsers/test_note.py
  - tests/ingest/test_events_query.py
  - tests/ingest/test_hub_builder.py
  - tests/ingest/test_note_e2e.py
  - tests/ingest/test_price_snapshot.py
  - tests/ingest/test_worker_hub_hook.py
  - tests/ingest/test_worker_note_dispatch.py
  - tests/shared/test_note_frontmatter.py
  - tests/shared/test_thesis_frontmatter.py
  - tests/templates/test_templates_parse.py
findings:
  critical: 0
  warning: 5
  info: 6
  total: 11
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-05-07T15:17:44Z
**Depth:** standard
**Files Reviewed:** 30
**Status:** issues_found

## Summary

Phase 8 implements vault dashboards (Dataview-backed portfolio/watchlist/events views), ticker hub generator, price snapshot derived cache, private-note (thesis/journal) parser/dispatch, and the supporting Alembic migration `0005`. The code is generally well-structured: pure functions are cleanly separated from I/O, content-hash idempotency is correctly implemented in `hub_builder` (excludes `generated_at` from the hash payload), per-doc transaction isolation is preserved in `worker.process_private_note`, and Phase 8 hooks into the ingest worker are wrapped in best-effort try/except per D-01. Test coverage is comprehensive — every D-token from the plan has a corresponding test.

Key concerns are concentrated in two areas:

1. **`events_query.events_this_week` cross-talk between vault test fixtures and DB rows.** The function reads `_derived` from the file system rather than DB columns, so any stale or shared-`tmp_path`-via-DB row will leak across tests. More importantly, candidate-row scanning runs N filesystem reads per ingest cycle (no LIMIT before the FS pass), which can scale poorly.
2. **`process_private_note` security/parity gaps with `process_document`.** Injection-pattern detection is computed but never persisted (`injection_flags` is `# noqa: F841`); private notes also bypass the trust-level pipeline used by other sources.

These are recoverable in a follow-up — none block Phase 8 sign-off.

## Warnings

### WR-01: `process_private_note` computes `injection_flags` but discards them

**File:** `src/ingest/worker.py:229-230`
**Issue:** `detect_injection_patterns(body)` is called and `injection_flags` is computed, but the variable is annotated `# noqa: F841 — recorded for parity` and never persisted anywhere. This is a security regression: a malicious memo embedded by a user (or imported from a source they don't fully trust) gets indexed without the injection markers that gate downstream LLM extraction. The comment explicitly says "recorded for parity" but no recording happens.

The frontmatter for private notes does not embed an `ingest_state` zone, so the marker can't write back to the file. It should be persisted on the `documents` row (e.g., a JSONB column) or recorded into a separate audit table — or the detection call should be removed entirely with a comment explaining why private notes are exempt.

**Fix:** Either persist `injection_flags` (preferred) or drop the dead detection call:
```python
# Option A: persist on documents row (requires schema add — file as Phase 9)
# Option B: drop detection until persistence exists
# hits = detect_injection_patterns(body)  # TODO Phase 9: persist + gate LLM
```
At minimum, the `# noqa: F841 — recorded for parity` comment is misleading and must be corrected. This was likely cargo-culted from `process_document` where the value IS recorded (`fm_model.ingest_state.injection_flags = sorted(...)`).

### WR-02: `events_this_week` reads frontmatter from disk for every candidate row

**File:** `src/ingest/events_query.py:184-203`
**Issue:** The SQL pulls all `documents` rows in the KST week window without any ticker filter, then performs a per-row filesystem read of `_derived.tickers` to filter. With ~수만 건/년 of news/dart/kind documents, a typical week has hundreds of rows; in degenerate cases (popular ticker hits or import backfills), this can be thousands. Each row triggers a `frontmatter.load` (YAML parse) plus path-existence checks. There's no upper bound enforcement on the SQL side — `limit` only truncates AFTER all FS reads complete.

This is also a correctness concern: `documents.vault_path` may not be resolvable on every machine (paths are absolute in `worker._INSERT_DOC_SQL`: `"vp": str(path)`). On a teammate's clone, those absolute paths won't exist, all rows return `[], None, None`, and the dashboard silently shows zero events.

**Fix:** Add a SQL-side `LIMIT` cap and/or persist `_derived.tickers` to a column at ingest time:
```python
sql = sa.text(
    "SELECT id, vault_path, source, first_seen_at "
    "  FROM documents "
    " WHERE source IN ('dart', 'news', 'kind') "
    "   AND first_seen_at >= :start_ts AND first_seen_at < :end_ts "
    " ORDER BY first_seen_at DESC "
    " LIMIT :hard_cap"
)
# pass {"hard_cap": max(limit * 10, 500)} — soft pre-filter cap
```
For correctness on clones: store `vault_path` as a *relative* path (resolved against `vault_root` at read time). This is already half-implemented in `_read_derived` (the `vault_root / vault_path_value` candidate), but the worker writes absolute paths.

### WR-03: `worker.py` writes absolute `vault_path` — clone portability bug

**File:** `src/ingest/worker.py:128, 142, 257`
**Issue:** `process_document` and `process_private_note` insert `"vp": str(path)` where `path` is the absolute `Path` from `rglob`. This breaks `events_query._read_derived` and `hub_builder.collect_inputs_for_corp` on any clone where the repo root differs (different developer machines, CI containers, WSL vs native). The dedup `WHERE vault_path = :vp` query also misses across machines because the absolute prefix differs.

**Fix:** Store `vault_path` as relative to `vault_root`:
```python
try:
    rel_vp = str(path.resolve().relative_to(vault_root.resolve()))
except ValueError:
    rel_vp = str(path)  # fallback for tests outside vault_root
# pass rel_vp into INSERT
```
The signature of `process_document` will need `vault_root: Path` threaded through — `ingest_run` already has it. Worth a follow-up phase, but worth tracking now.

### WR-04: `hub_builder.write_hub_if_changed` uses substring match for hash compare

**File:** `src/ingest/hub_builder.py:178`
**Issue:** `if f"content_hash: {content_hash}" in existing:` does a substring check on the entire file. This is O(n) on file size and — more concerning — produces false positives if the hash hex appears elsewhere (e.g., user's `## Private Notes` section embedding a quoted hash, or another document linked via wikilink). Unlikely but possible since the hash is just hex.

**Fix:** Parse the YAML frontmatter properly:
```python
import re
m = re.search(r"^content_hash:\s*([a-f0-9]{64})\s*$", existing, re.MULTILINE)
if m and m.group(1) == content_hash:
    return False
```
Or load with `pyfm.loads(existing)` and read `metadata["content_hash"]` directly.

### WR-05: `hub_builder._sparkline` boundary off-by-one risk on hi==lo

**File:** `src/ingest/hub_builder.py:64-67`
**Issue:** `span = max(hi - lo, 1)` defends against zero-division when all 30 prices are identical, but the bin index `int((p - lo) / span * 7)` then always evaluates to 0 (since `p - lo == 0`), producing a flat `▁▁▁...` line. That's reasonable behavior. However, when prices vary, the `min(7, ...)` guard masks an off-by-one: the maximum value `(hi - lo) / span * 7 = 7.0` indexes `bars[7]` (= `█`), which is correct ONLY because `bars` has 8 chars. The comment says "7-bin Unicode block sparkline" but it's actually 8-bin. Minor doc/code mismatch — not a bug, but the next maintainer will be confused.

**Fix:** Update docstring or rename:
```python
def _sparkline(price_30d: list[tuple[date, int]]) -> str:
    """8-level Unicode block sparkline (▁ to █). Returns em-dash on empty input."""
```

## Info

### IN-01: `events_query._read_derived` swallows all exceptions silently

**File:** `src/ingest/events_query.py:133-135`
**Issue:** `except Exception: logger.exception(...)` is good defensive code, but the bare `Exception` masks `ImportError` if `frontmatter` (PyYAML/python-frontmatter) ever fails to import — that should crash loudly, not return empty. Consider narrowing to `(yaml.YAMLError, OSError, KeyError)` or similar.

**Fix:** Narrow the exception or document why broad catching is required (currently the comment says "best-effort, mirrors edges.py" — acceptable as an explicit policy choice, just confirm the policy is intentional).

### IN-02: Lazy `import frontmatter as pyfm` inside hot loop

**File:** `src/ingest/events_query.py:116`
**Issue:** `import frontmatter as pyfm` is inside the per-file `for cand in candidates` loop. Python caches imports so the cost is just a dict lookup, but moving it to module-level matches the rest of the codebase (e.g., `parsers/note.py` does it correctly).

**Fix:** Move import to top of file alongside other imports.

### IN-03: `hub_builder.collect_inputs_for_corp` reads first 80 chars of body as title

**File:** `src/ingest/hub_builder.py:226-228, 244-246`
**Issue:** `COALESCE(SUBSTRING(body FROM 1 FOR 80), '') AS title` is a placeholder that takes the first 80 bytes of the markdown body. For DART/news this often includes frontmatter tail or markdown heading characters (`# ` prefix, etc.). The hub render then puts this raw substring into a markdown table cell. `_escape_cell` only escapes `|`/newlines — `#`, `[`, `]`, backticks, etc. will render as raw markdown.

**Fix:** Either (a) read `provenance.title` from the file like `events_query._read_derived` does, or (b) extend `_escape_cell` to escape markdown control chars. The former is cleaner.

### IN-04: `hub_builder` Valuation section hardcodes ticker into Dataview query

**File:** `src/ingest/hub_builder.py:110`
**Issue:** `LIST FROM \"\" WHERE valuation AND ticker = \"{inp.ticker}\"` — the ticker is interpolated into the DQL string. No injection risk here (corp_code is validated on line 144, and ticker comes from DB), but it's a Phase 10 placeholder. Worth adding a TODO comment that links to the Phase 10 D-12 hook so future-you doesn't ship this as-is.

**Fix:** Add explicit TODO marker:
```python
# TODO Phase 10 D-12: replace ticker-string interpolation with proper Dataview LINK.
```
Currently the comment says `_(Phase 10 D-12 hook — placeholder)_` in body text, but that's user-visible. A code-side TODO is also helpful.

### IN-05: `price_snapshot.collect_prices` returns rows even when `as_of is None`

**File:** `src/ingest/price_snapshot.py:74-94`
**Issue:** The loop appends to `rows` even when no row is processed yet (`as_of` may stay None if all `d` values are None). The `run()` caller checks `if as_of is None: return False`, so `rows` is discarded — but the function itself returns `(rows, None)` which is a slightly leaky contract. Minor.

**Fix:** Either return `([], None)` when `as_of` ends up None, or document the existing behavior in the docstring.

### IN-06: `templates/notes/thesis.md` has hardcoded ticker `005930`

**File:** `templates/notes/thesis.md:3`
**Issue:** The thesis template hardcodes `tickers: ["005930"]`. Since this is a *template*, users are expected to copy + edit, but a placeholder like `tickers: ["{ticker}"]` (matching the body's `# {ticker} Thesis`) would be more consistent.

**Fix:**
```yaml
tickers: ["{ticker}"]  # replace with actual KRX 6-digit code
```
Note: this would break `tests/templates/test_templates_parse.py::test_thesis_template_parses_with_thesis_model` because `"{ticker}"` doesn't match `^[0-9]{6}$` — but the test currently passes only because `005930` is real. Either update the test to use `tickers: []` (consistent with `journal.md`), or document the placeholder convention.

---

_Reviewed: 2026-05-07T15:17:44Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
