---
phase: "01-collector-db-cutover"
plan: "01-07"
subsystem: "collectors/dart"
tags: [collector, dart, filings, postgres, upsert, veto-8, body-md, bug-c, phase-1, wave-2]
requires:
  - migration 0006 (filings + entities) — Plan 01-01
  - CLI vault_root strip + collect_dart signature update — Plan 01-02
  - db.entity.upsert_entity helper (Phase 4 carry-over, Bug C)
provides:
  - src/collectors/dart/db_writer.py::upsert_dart_filing
  - collect_dart body rewired to db_writer (no writer.*, no vault writes,
    no heartbeat, no frontmatter)
  - tests/collectors/dart/ test directory (NEW — DART previously had only
    repo-root tests)
  - 22 new tests (11 db_writer unit + 11 collect_dart integration);
    23rd test added as legacy-coverage carry-over for list_ab_filings routing
affects:
  - Wave 3 / 01-08 (observability) — will INSERT into collector_runs from the
    structured run-complete log call site already added here
  - Wave 3 / 01-09 (writer deletion + fence) — will delete
    src/collectors/dart/writer.py; this plan does NOT delete it (out of scope)
tech-stack:
  added: []
  patterns:
    - "Load-then-classify UPSERT pattern (same as macro 01-03 / krx 01-04):
       SELECT existing content_hash → classify inserted/updated/skipped → UPSERT
       with ON CONFLICT (rcept_no) DO UPDATE. Skip path only bumps last_seen_at."
    - "Body byte-exact roundtrip: filings.body_md stores the WHOLE filing as a
       single TEXT blob. No chunking, no truncation, no embedding population.
       Veto #8 enforced at I/O layer."
    - "Bug C entity upsert gate updated from succeeded > 0 → (inserted +
       updated) > 0 to match Phase 1 v2.0 stats shape."
    - "filed_at TIMESTAMPTZ composed at KST close (15:30 Asia/Seoul) from
       filing.rcept_dt YYYYMMDD — psycopg returns it as UTC-normalized
       tz-aware datetime."
key-files:
  created:
    - src/collectors/dart/db_writer.py
    - tests/collectors/dart/__init__.py
    - tests/collectors/dart/test_db_writer.py
    - tests/collectors/dart/test_collect_dart.py
    - .planning/phases/01-collector-db-cutover/01-07-SUMMARY.md
  modified:
    - src/collectors/dart/__init__.py (writer.* removed; db_writer.* added;
      heartbeat/_LEGACY_VAULT_ROOT/_read_existing_hash dropped; engine REQUIRED;
      stats shape inserted/updated/skipped/failed/elapsed_ms; structured
      collector_run_complete log line added)
  deleted:
    - tests/test_collect_dart.py (R-2 BLOCKER fix; coverage delta documented
      below — no substantive scenario lost beyond heartbeat which v1.0 SC-3
      eliminates)
decisions:
  - "Body byte-length test set to >200KB (test_collect_dart_whole_body_no_chunking)
     vs the plan's 200KB baseline. Largest body successfully roundtripped =
     308,000 bytes (212K Korean+English chars). 1MB and beyond is a Phase 3
     concern (RESEARCH F-3 / R-7) — the chunks-count==0 assertion holds at all
     sizes since the writer never touches the chunks table."
  - "event_type = NULL is hard-coded for the DART A/B branch. KIND (01-05)
     uses a separate db_writer.upsert_kind_filing that DOES set event_type;
     UPSERT on (rcept_no) is whichever wave touches the row last. The collision
     is empty in practice — list_ab_filings filters pblntf_ty=['A','B'] only
     (fetcher.py line 65), and KIND filings carry pblntf_ty='I' which never
     enters this code path."
  - "pblntf_ty validation tightened to {'A','B'} in db_writer. An 'I' value
     fed through this writer raises ValueError — this protects against a
     future KIND/DART cross-write bug where one writer is called by the wrong
     collector."
  - "Bug C path verified with pg_clean + a placeholder pre-seeded entity row.
     A genuine no-pre-seeded scenario can't be exercised because filings.corp_code
     has a NOT NULL FK to entities — the FK has to exist before the filing
     INSERT, so the entity upsert that runs *after* the filings loop is the
     refresh-not-insert path. This matches v1.0 reality (collect_dart is run
     against a pre-seeded entity DB)."
  - "Added test_collect_dart_routes_through_list_ab_filings to carry over the
     legacy test_only_ab_filing_types scenario. The pblntf_ty=['A','B'] filter
     itself lives inside fetcher.list_ab_filings (line 65); the new test
     verifies collect_dart routes through that function rather than a custom
     call path."
metrics:
  tasks_completed: 4
  duration_minutes: ~25
  tests_added: 23  # 11 db_writer + 12 collect_dart (including the carry-over)
  tests_total_in_dart_module: 23
  largest_body_md_bytes_roundtripped: 308000
  chunks_count_after_dart_run: 0
  commit_hashes:
    - 5a1af45  # Task 1 — db_writer + unit tests
    - 8c3dce3  # Task 2 — collect_dart rewire
    - 532614d  # Task 3 — collect_dart integration tests
    - d76a8d6  # Task 4 — legacy file deletion
---

# Phase 1 Plan 01-07: DART Collector DB-Direct Cutover — Summary

One-liner: DART regular A+B filings now INSERT directly into `filings` via
`upsert_dart_filing`, with the WHOLE filing body stored verbatim in
`filings.body_md TEXT` and the `chunks` table left untouched — Veto #8
enforced at the I/O layer (308KB Korean+English roundtrip byte-exact, zero
chunks writes); Bug C entity upsert preserved with the new
`(inserted+updated) > 0` gate.

## What Changed

### Files created

| File | Purpose |
|---|---|
| `src/collectors/dart/db_writer.py` | Single function `upsert_dart_filing` — load-then-classify UPSERT, content-hash idempotency, body stored verbatim |
| `tests/collectors/dart/__init__.py` | Empty (new directory marker — pytest package discovery) |
| `tests/collectors/dart/test_db_writer.py` | 11 db_writer unit tests |
| `tests/collectors/dart/test_collect_dart.py` | 12 collect_dart integration tests (including the carry-over) |

### Files modified

| File | Change |
|---|---|
| `src/collectors/dart/__init__.py` | `writer.*` imports + calls removed; `db_writer.upsert_dart_filing` wired in; `_LEGACY_VAULT_ROOT` placeholder + `_read_existing_hash` helper deleted; `shared.heartbeat.record_source_run` replaced with structured `_log.info("collector_run_complete", extra=...)`; engine becomes REQUIRED (RuntimeError on None); stats shape switched from `succeeded` to `inserted+updated`; `elapsed_ms` added |

### Files deleted

| File | Why |
|---|---|
| `tests/test_collect_dart.py` | R-2 BLOCKER from PLAN-VERIFICATION.md. Repo-root v1.0 tests called `collect_dart(vault_root=tmp_path)` (post-01-02 TypeError) and asserted Markdown vault paths. Coverage moved to `tests/collectors/dart/` with DB-state assertions. |

### Files NOT touched (out of scope; owned by other plans)

- `src/collectors/dart/writer.py` — Plan 01-09 deletes
- `src/collectors/dart/client.py`, `fetcher.py` — upstream API wrappers, unchanged
- `src/shared/heartbeat.py` — Plan 01-08 deletes
- `src/db/migrations/*` — schema already locked by 01-01

## upsert_dart_filing Contract

```python
def upsert_dart_filing(
    engine: Engine,
    *,
    rcept_no: str,           # 14 ASCII digits — PK
    corp_code: str,          # 8 ASCII digits — FK to entities
    ticker: str | None,      # 6 ASCII digits or None
    filed_at: datetime,      # TIMESTAMPTZ
    report_nm: str,
    pblntf_ty: str,          # 'A' or 'B'
    body_md: str,            # WHOLE filing — stored verbatim (Veto #8)
    source_url: str,
) -> Literal["inserted", "updated", "skipped"]:
```

Implementation pattern (load-then-classify, mirrors 01-03 macro + 01-04 krx):

1. Regex-validate all shaped arguments (ValueError before any SQL).
2. Compute `content_hash = sha256(normalize_body(body_md))` —
   shared.content_hash.normalize_body normalizes CRLF, trailing whitespace,
   and trailing newline so the hash survives benign text-formatting changes.
3. `SELECT content_hash FROM filings WHERE rcept_no = :r` in the transaction.
4. Classify:
   - None → `"inserted"`, run the UPSERT INSERT branch.
   - mismatch → `"updated"`, run the UPSERT UPDATE branch.
   - match → `"skipped"`, run only `UPDATE filings SET last_seen_at = now()` and return early.
5. UPSERT SQL:
   ```sql
   INSERT INTO filings (...) VALUES (...)
   ON CONFLICT (rcept_no) DO UPDATE SET
     body_md = EXCLUDED.body_md,
     content_hash = EXCLUDED.content_hash,
     report_nm = EXCLUDED.report_nm,
     ticker = COALESCE(EXCLUDED.ticker, filings.ticker),
     last_seen_at = now()
   ```

`event_type` is HARD-CODED `NULL` in the INSERT and absent from the
DO UPDATE clause. The DART A/B branch never sets it; KIND's separate
writer (01-05) owns the `pblntf_ty='I'` branch and the `event_type`
population.

## "Whole body, no chunks" — Veto #8 enforcement evidence

Two complementary assertions catch this invariant:

**1. Byte-length equality (DB roundtrip)**

- `test_upsert_filing_whole_body_stored` — db_writer test with a 100KB+
  Korean+English body. `row.body_md == body` AND
  `len(row.body_md.encode('utf-8')) == len(body.encode('utf-8'))`.
- `test_collect_dart_whole_body_no_chunking` — collect_dart integration test
  with a 308,000-byte body (212K Korean+English chars). Same byte-exact
  roundtrip assertion at the collector level (through the full
  client→fetcher→db_writer pipeline).

**2. `chunks` table count == 0 after a dart run**

- `test_collect_dart_whole_body_no_chunking` runs `collect_dart` then
  `SELECT count(*) FROM chunks` — must equal 0. If a future agent were to
  add chunking logic to the writer (e.g. inserting into `chunks` for narrative
  search), this assertion would catch it immediately.

The largest body successfully roundtripped: **308,000 bytes** (212,000 Korean
+ English mixed characters). The plan asked for 100KB and 200KB tests; both
brackets are exercised. 1MB+ bodies (which RESEARCH F-3 / R-7 flagged for a
future stress test) are not yet exercised, but the chunks-count assertion is
size-independent — any size that fits in TEXT works.

## Bug C entity upsert verification

The Phase 4 quick-260418-asr fix is preserved with a gate-condition change:

| Phase | Gate | Stats key |
|---|---|---|
| v1.0 / Phase 4 | `stats["succeeded"] > 0` | succeeded |
| Phase 1 v2.0 (this plan) | `(stats["inserted"] + stats["updated"]) > 0` | inserted + updated |

The change is mechanical — the v2.0 stats shape splits "succeeded" into
inserted/updated, so the gate has to sum them. Functional behavior is
unchanged: at least one filing row landed → entity upsert fires once at the
end of the run with `(corp_code, canonical_name, ticker)`.

`test_collect_dart_bug_c_entity_upsert` verifies the path:

1. Pre-seeds a placeholder entity row (canonical_name="placeholder_name",
   current_ticker=NULL) so the filings.corp_code FK is satisfiable.
2. Runs `collect_dart` with mocked Samsung corp.
3. Asserts the entity row was UPDATEd to canonical_name="삼성전자",
   current_ticker="005930".
4. Asserts entity_aliases now has a `(kind='ticker', value='005930', valid_to IS NULL)`
   row — the alias materialization that lets downstream
   `resolve_entity('005930')` succeed.

The entity row MUST exist before the filings INSERT (FK NOT NULL CASCADE);
the upsert_entity at end-of-run is therefore a refresh path, which is what
the v1.0 Bug C fix actually exercised (collect_dart is always run against
a pre-seeded entity DB in practice).

## Test Results

| File | Tests | Result |
|---|---|---|
| `tests/collectors/dart/test_db_writer.py` | 11 | 11 PASS |
| `tests/collectors/dart/test_collect_dart.py` | 12 | 12 PASS |
| `tests/collectors/dart/` total | **23** | **23 PASS** |

Runtime ≈ 12 seconds against the session pg_engine testcontainer.

## R-2 Coverage Delta

The legacy `tests/test_collect_dart.py` (8 test cases, ~280 lines) was
deleted in Task 4. Below is the scenario-by-scenario mapping to the new
`tests/collectors/dart/test_collect_dart.py`:

| # | Legacy test | Substantive scenario | New coverage |
|---|---|---|---|
| 1 | `test_collects_ab_filings_writes_files` | A+B filings land; provenance fields recorded | `test_collect_dart_inserts_filing` (DB-state SELECT) + `test_collect_dart_pblntf_ty_recorded` (B-type preserved) |
| 2 | `test_max_docs_cap_respected` | 200 filings + max_docs=100 → 100 rows | `test_collect_dart_max_docs_cap` (200 filings + DB count==100) |
| 3 | `test_only_ab_filing_types` | search_filings called with pblntf_ty=['A','B'] | `test_collect_dart_routes_through_list_ab_filings` (NEW — the A/B filter itself lives inside fetcher.list_ab_filings line 65; new test verifies collect_dart routes through that function) |
| 4 | `test_idempotent_rerun_skips_unchanged` | Rerun same body → skipped | `test_collect_dart_idempotent` (stats.skipped=1, no duplicate row) |
| 5 | `test_changed_body_is_rewritten` | Body changed → re-written | `test_collect_dart_body_edited` (stats.updated=1, body_md has new content) |
| 6 | `test_collector_records_heartbeat` | Heartbeat md last_success populated | **DROPPED (intentional)** — Phase 1 SC-3 deletes heartbeat.py entirely. Replacement is `_log.info("collector_run_complete", extra=...)` + Plan 01-08 collector_runs row INSERT. |
| 7 | `test_collector_records_heartbeat_on_failure` | Heartbeat last_failure populated + per-filing isolation | Heartbeat half: same as #6, DROPPED. Isolation half: `test_collect_dart_per_filing_isolation` (3 filings, #2 raises during fetch_body; stats.inserted=2, stats.failed=[{doc=…,error=…}], DB count==2). |
| 8 | `test_ci_import_guard_passes` | No anthropic/openai imports in collectors/dart/ | **COVERED GLOBALLY** — `tests/test_import_guard.py` checks every collector module. Not a dart-specific concern; legacy file's docstring even acknowledged it (line 12). |

**Scenarios lost (no substantive coverage):**

- None. The two heartbeat-specific scenarios (#6, #7-heartbeat half) are
  intentionally dropped per Phase 1 SC-3. The per-filing-isolation half of
  #7 is preserved.

**Scenarios added (above and beyond legacy):**

- `test_collect_dart_whole_body_no_chunking` — 308KB body + chunks count=0
  (Veto #8 gold standard).
- `test_collect_dart_bug_c_entity_upsert` — Bug C path with the new
  inserted+updated gate (Phase 1 v2.0 stats shape).
- `test_collect_dart_no_engine_raises` — RuntimeError on engine=None (R-12).
- `test_collect_dart_no_markdown_written` — SC-1 fence: no vault/raw/dart/
  directory created post-run.
- `test_collect_dart_filed_at_kst_close` — TIMESTAMPTZ semantics
  (15:30 Asia/Seoul ⇔ 06:30 UTC).
- `test_collect_dart_invalid_corp_code_raises` (db_writer), 5 other shape-
  validation tests.

Net: **+10 tests** beyond the legacy file's coverage. Zero substantive
scenarios lost.

## Phase 1 Veto Compliance

| Veto | Phase 1 rule | Defense in this plan |
|---|---|---|
| **#6** | No numeric embedding | `filings.body_embedding halfvec(1024)` declared NULL in migration 0006; db_writer never SETs it. The dart-specific `body_embedding` is left for Phase 3 to populate via bge-m3. |
| **#8** | No DART pre-chunking | `filings.body_md TEXT NOT NULL`; db_writer stores the body verbatim; tests verify byte-length match + `count(*) FROM chunks == 0` after a dart run. The chunks table from migration 0002 is dormant per Q3 Option B. |
| **#9** | No Markdown vault revival | `vault_root` parameter gone (post-01-02); `_LEGACY_VAULT_ROOT` placeholder removed (this plan); `writer.*` call sites zero; `test_collect_dart_no_markdown_written` runs collect_dart in tmp_path and asserts no `vault/raw/dart/` directory created. (Plan 01-09 deletes the `writer.py` module file itself.) |

## DART Rate Limit Preservation

The serial per-filing loop is unchanged. No parallelism, no async, no
ThreadPool/ProcessPool. RESEARCH.md Pitfall 2 says DART rate-limits at ~1
req/sec and parallelism risks `OpenDartError: 일일거래량초과`. The collector
body iterates filings one at a time:

```python
for filing in filings:
    try:
        body = fetcher.fetch_body(filing)
        ...
        outcome = db_writer.upsert_dart_filing(engine, ...)
```

Adding an `asyncio.gather` or `concurrent.futures` wrapper here would be a
direct Veto on Pitfall 2. The per-filing isolation (failure → stats["failed"])
is the only concurrency-related surface this collector touches.

## Deviations from Plan

**None of substance.** All four tasks executed as specified.

Minor mechanical notes:

1. **Test count slightly higher than plan.** Plan called for "Nine
   `test_collect_dart.py` tests"; the file ships with 11 (added
   `test_collect_dart_max_docs_cap` for D-03 cap coverage which was implied
   but not explicitly listed in the plan's task-3 enumeration, and
   `test_collect_dart_filed_at_kst_close` for TIMESTAMPTZ semantics).
   `test_collect_dart_routes_through_list_ab_filings` was added in Task 4 to
   carry forward the legacy `test_only_ab_filing_types` scenario (R-2
   coverage check) — 12 total in the file.

2. **Body byte length test set to 308KB rather than the plan's 100KB / 200KB
   baseline.** Both 100KB (`test_upsert_filing_whole_body_stored`) and 308KB
   (`test_collect_dart_whole_body_no_chunking`) bodies are exercised. The
   chunks-count==0 assertion is size-independent and would catch a violation
   at any body size.

3. **The plan's grep assertion `grep "writer\\." src/collectors/dart/__init__.py # 0`
   was substantively (but not literally) satisfied.** The literal grep matches
   the `db_writer.upsert_dart_filing` call site (since `writer.` is a substring
   of `db_writer.`). I verified the *intent* with a refined token list:
   `writer.write_filing`, `writer.vault_path_for`, `writer.compute_body_hash`,
   `vault_root`, `_LEGACY_VAULT_ROOT`, `heartbeat`, `record_source_run`,
   `_read_existing_hash`, `frontmatter` — all return zero matches.

## Pitfalls Encountered + Resolution

| # | Pitfall | Resolution |
|---|---|---|
| 1 | First version of `test_collect_dart_max_docs_cap` used `f"202605200006{i:04d}"` (16 chars) for rcept_no. db_writer correctly rejected it. | Shortened to `f"2026052000{i:04d}"` (14 chars). The rejection was a correctness signal, not a bug — the validation worked. |
| 2 | Sibling agents (01-05 kind, 01-06 news) were committing concurrently. | Disjoint file sets; `git status` showed only my staged files. No locks observed. |
| 3 | Console `cp949` codec rejecting em-dash during inspect-source diagnostic. | Switched to `sys.stdout.reconfigure(encoding='utf-8')` for the one-off check. Tests themselves are unaffected (they run in pytest's UTF-8 environment). |
| 4 | uv CLI on PATH not preferred on this box (per 01-01 summary note); used `python -m uv run` for all pytest/alembic invocations. | Pre-existing pattern; no new mitigation required. |

## Threat Surface

No new network endpoints, auth paths, or file access patterns introduced.
The collector still talks to dart-fss (existing external dep) and now talks
to Postgres via the existing `Engine` (FK CASCADE on `filings.corp_code →
entities.corp_code` mirrors the v1.0 trust boundary). All UPSERT params flow
through SQLAlchemy bind params; no f-string SQL. Shape validation
(rcept_no/corp_code/ticker/pblntf_ty) fires before any SQL — closes
T-3-12 (path traversal class) carry-over from `writer.py`.

No threat flags.

## Self-Check: PASSED

Files created (existence check):

- `src/collectors/dart/db_writer.py` — FOUND
- `tests/collectors/dart/__init__.py` — FOUND
- `tests/collectors/dart/test_db_writer.py` — FOUND
- `tests/collectors/dart/test_collect_dart.py` — FOUND

Files modified (existence check):

- `src/collectors/dart/__init__.py` — FOUND (modified; `db_writer` import +
  `engine` REQUIRED guard present; `writer.*`/`heartbeat`/`_LEGACY_VAULT_ROOT`
  absent)

Files deleted (absence check):

- `tests/test_collect_dart.py` — GONE (verified via `test ! -f`)

Commits in git log:

- `5a1af45` (Task 1) — FOUND
- `8c3dce3` (Task 2) — FOUND
- `532614d` (Task 3) — FOUND
- `d76a8d6` (Task 4) — FOUND

Test results:

- `tests/collectors/dart/` — 23/23 PASS (1 expected DeprecationWarning from
  alembic config, not from this plan's code).

`pytest --collect-only tests/` succeeds repo-wide: 361 tests collected, no
ImportError or collection failure.
