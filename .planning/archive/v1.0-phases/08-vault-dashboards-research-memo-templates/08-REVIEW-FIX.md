---
phase: 08-vault-dashboards-research-memo-templates
fixed_at: 2026-05-06T00:00:00Z
review_path: .planning/phases/08-vault-dashboards-research-memo-templates/08-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 4
skipped: 1
status: partial
---

# Phase 8: Code Review Fix Report

**Fixed at:** 2026-05-06
**Source review:** .planning/phases/08-vault-dashboards-research-memo-templates/08-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope (Critical + Warning): 5
- Fixed: 4
- Skipped: 1

## Fixed Issues

### WR-01: `process_private_note` computes `injection_flags` but discards them

**Files modified:** `src/ingest/worker.py`
**Commit:** c7d70bd
**Applied fix:** Option B — removed the dead `detect_injection_patterns(body)` call inside `process_private_note` along with the misleading `# noqa: F841 — recorded for parity` comment. Replaced with a TODO Phase 9 marker explaining that private_note frontmatter has no `ingest_state` zone yet, so injection_flags persistence is deferred until a JSONB column or audit table lands. This matches the reviewer's preference for honest dead-code removal over silently misleading state.

### WR-02: `events_this_week` reads frontmatter from disk for every candidate row

**Files modified:** `src/ingest/events_query.py`
**Commit:** 1591004
**Applied fix:** Added a SQL-side `LIMIT :hard_cap` clause to the candidate scan, with `hard_cap = max(limit * 10, 500)`. This caps the per-row FS read cost at a bounded multiple of the caller's `limit`, while still leaving headroom for the post-SQL ticker-overlap filter to find enough matches. The relative-vault-path correctness sub-issue is intentionally deferred to WR-03 (skipped — see below).

### WR-04: `hub_builder.write_hub_if_changed` uses substring match for hash compare

**Files modified:** `src/ingest/hub_builder.py`
**Commit:** ababb68
**Applied fix:** Replaced `if f"content_hash: {content_hash}" in existing` with an anchored regex match on a YAML scalar line: `^content_hash:\s*['"]?([a-f0-9]{64})['"]?\s*$` (MULTILINE). Eliminates substring false positives from hash hex appearing elsewhere in the body and tightens the check to the frontmatter line only. Added `import re` at module top.

### WR-05: `hub_builder._sparkline` boundary off-by-one risk on hi==lo

**Files modified:** `src/ingest/hub_builder.py`
**Commit:** ababb68
**Applied fix:** Updated the `_sparkline` docstring from "7-bin Unicode block sparkline" to "8-level Unicode block sparkline (▁ to █)" to match the actual 8-character `bars` constant. No behavior change — code was already correct; this is a doc/code mismatch fix to prevent future maintainer confusion. Bundled into the same commit as WR-04 since both target hub_builder.py.

## Skipped Issues

### WR-03: `worker.py` writes absolute `vault_path` — clone portability bug

**File:** `src/ingest/worker.py:128, 142, 257`
**Reason:** Skipped — scope too large for a surgical, atomic fix in this review pass. The change requires:
1. Threading a `vault_root: Path` argument through `process_document` and `process_private_note` (both signatures + all call sites).
2. Updating the dedup `WHERE vault_path = :vp` query semantics (a clone with new relative paths must match prior absolute-path rows for one cycle, or trigger re-ingest).
3. Migrating any existing `documents.vault_path` rows in user databases (data migration, not just code).
4. Updating multiple test fixtures (`tests/ingest/test_worker_*.py`, `tests/ingest/test_events_query.py`, `tests/ingest/test_hub_builder.py`) that currently assert on absolute paths.
5. Coordinating with `events_query._read_derived` and `hub_builder.collect_inputs_for_corp` consumers.

This is a multi-file refactor that should land as its own planned phase (e.g., Phase 9 portability hardening) with a written migration story, not as a drive-by fix during code-review remediation. Tracked as a follow-up.

**Original issue:** `process_document` and `process_private_note` insert `"vp": str(path)` where `path` is the absolute `Path` from `rglob`. This breaks `events_query._read_derived` and `hub_builder.collect_inputs_for_corp` on any clone where the repo root differs (different developer machines, CI containers, WSL vs native). The dedup `WHERE vault_path = :vp` query also misses across machines because the absolute prefix differs.

---

_Fixed: 2026-05-06_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
