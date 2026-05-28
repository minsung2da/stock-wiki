# Phase 1 Plan Verification

**Verdict:** PASS-WITH-WARNINGS
**Confidence:** HIGH on schema + dependency structure, MEDIUM on test-file inventory completeness.

The 9-plan set covers all 6 ROADMAP success criteria and the three load-bearing Hard Vetoes (#6/#8/#9) with multiple defenses. The dependency graph is acyclic, the wave structure is consistent with depends_on, and the must_haves are user-observable. However, two real artifacts that exist in the codebase today are not addressed by any plan (one of them, tests/test_collect_dart.py, will silently fail after Wave 0 lands), and several smaller verification gaps mean the executor needs to be told to fix them inline rather than relying on the plans as written.

Nothing in the warnings prevents /gsd:execute-phase 1 from being run, but the executor should be briefed on Required Changes before Wave 0 starts.

---

## Coverage Matrix (A)

| SC # | ROADMAP requirement | Covered by plan(s) | Actually covered? | Notes |
|------|---------------------|--------------------|---|---|
| SC-1 | collect dart INSERTs into filings; vault/raw/ does not recreate | 01-01 (schema), 01-02 (CLI), 01-07 (collector), 01-09 (fence + smoke) | YES | Defended at four layers. 01-09 test_phase01_smoke.py asserts not (Path.cwd() / "vault" / "raw").exists(); 01-07 has a similar dart-specific assertion. |
| SC-2 | krx/news/macro/kind UPSERT dedup on each domain table | 01-01, 01-03 (macro), 01-04 (krx), 01-05 (kind), 01-06 (news), 01-07 (dart) | YES | Each collector plan exercises content-hash / PK-conflict UPSERT with positive (insert) and negative (skip) assertions. |
| SC-3 | shared/heartbeat.py deleted; structured logs only | 01-08 | YES | Task 3 deletes the file, adds three-assertion CI guard (tests/test_no_heartbeat.py), inserts both stderr log + collector_runs row. |
| SC-4 | --vault-root removed from CLI | 01-02 | PARTIAL | Plan removes the argparse flag and updates tests/test_cli_collect_all.py, but does NOT address tests/test_cli_default_flags.py, which asserts "default: vault" in help_text and will fail immediately after task 1 of 01-02 lands. See R-1. |
| SC-5 | tests/collectors/ validates INSERT paths | 01-03, 01-04, 01-05, 01-06, 01-07, 01-09 | PARTIAL | Five collector plans each add DB-state assertions; 01-09 adds smoke test. BUT tests/test_collect_dart.py (at repo root, NOT under tests/collectors/dart/) exists today with vault_root=tmp_path calls and file-system assertions; no plan deletes or rewrites it. 01-07 incorrectly claims tests/collectors/dart/ does not exist (true) but ignores that root-level dart tests do exist (false claim). See R-2. |
| SC-6 | stock-enrich-daily Routine already disabled | n/a | YES | ROADMAP says no action; PLAN-INDEX correctly maps this. |

PLAN-INDEX.md coverage table matches reality except for the two PARTIAL items above; the index is documentary, not load-bearing.

---

## Hard Veto Defense (B)

| Veto # | Phase 1-relevant rule | Defended by | Confidence |
|---|---|---|---|
| 1 | No AI price prediction | n/a Phase 1 | n/a |
| 2 | No thesis without expires_at + assumptions | n/a (Phase 2) | n/a |
| 3 | Contradictions first-class | n/a Phase 1 | n/a |
| 4 | No black-box scores | n/a Phase 1 | n/a |
| 5 | No sentiment-only signals | n/a Phase 1 | n/a |
| **6** | **No numeric embeddings** | 01-01 schema declares ohlcv/macro_series/events without body_md or body_embedding; 01-01 Task 3 test_ohlcv_table_shape + test_macro_series_table_shape explicitly assert NO body_md and NO body_embedding column; 01-03/01-04 db_writer modules never bind a body or embedding parameter | HIGH |
| 7 | No run_sql MCP escape hatch | n/a (Phase 3) | n/a |
| **8** | **No DART pre-chunking** | 01-01 schema (filings.body_md TEXT NOT NULL); 01-07 test_collect_dart_whole_body_no_chunking asserts byte-length equality on a 200KB body AND SELECT count(*) FROM chunks == 0 after dart run; 01-05 leaves KIND body_md="" and documents Phase 3 backfill | HIGH |
| **9** | **No Markdown vault revival** | 01-09 task 1 deletes all 5 writer.py modules; task 2 adds tests/test_no_writer.py (3 assertions: file absence, importability, __init__.py AST scan); task 2 adds cli/__main__.py::main() runtime guard; every Wave 1/2 plan adds per-collector test_*_no_markdown_written test | HIGH |
| 10-13 | Action / report layer | n/a Phase 1 | n/a |

All three Phase 1-load-bearing Vetoes (#6, #8, #9) are enforced at schema layer, test layer, and (for #9) runtime layer. No plan violates an unrelated Veto.


---

## Dependency Graph (C)

```
Wave 0:   01-01 (schema)     01-02 (CLI strip)
              |                   |
              +---------+---------+
                        |
Wave 1:        01-03 (macro)   01-04 (krx)
                        |
                 +------+------+
                 |             |
Wave 2:   01-05 (kind)  01-06 (news)  01-07 (dart)
                        |
                 +------+------+
                 |             |
Wave 3:   01-08 (observability)  01-09 (writer deletion + fence)
```

- All declared depends_on lists point at existing plans; no forward references.
- No cycles; Wave 0 -> 1 -> 2 -> 3 ordering is consistent with depends_on.
- Wave numbers in frontmatter match topological position.

**Within-wave file disjointness check:**

| Wave | Plans | Shared files? |
|---|---|---|
| 0 | 01-01, 01-02 | 01-01 touches src/db/migrations/..., src/db/entity_models.py, tests/conftest.py. 01-02 touches src/cli/..., 5 collectors/*/__init__.py, tests/collectors/conftest.py, tests/test_cli_collect_all.py. NO shared file (01-02 touches tests/collectors/conftest.py, not tests/conftest.py). OK. |
| 1 | 01-03, 01-04 | macro touches collectors/macro/* + tests/collectors/macro/*. krx touches collectors/krx/* + tests/collectors/krx/*. DISJOINT. |
| 2 | 01-05, 01-06, 01-07 | Each touches its own collectors/<src>/* + tests/collectors/<src>/*. DISJOINT at directory level. |
| 3 | 01-08, 01-09 | 01-08 modifies all 5 collectors/*/__init__.py and deletes src/shared/heartbeat.py. 01-09 deletes all 5 collectors/*/writer.py and edits cli/__main__.py. DISJOINT at file level. OK. |

**Cumulative anomaly:** Plan 01-09 declares tests/collectors/conftest.py in files_modified (to remove vault_tmp), while Plan 01-04 task 3 says "OR keep using vault_tmp fixture". If executor follows 01-04 literally, krx tests in Wave 1 continue consuming vault_tmp; then Wave 3's 01-09 task 1 says "If matches exist, FIX the consuming tests" - contradicting 01-04. Cross-wave fixture-policy inconsistency. See Warning W-1.

**Verdict:** Dependency graph is correct. One cross-wave fixture-policy contradiction is a warning, not a blocker.

---

## Verification Quality (D)

Rubric: A = specific pytest command + DB-state assertion + negative assertion; B = pytest + at least one specific assertion; C = vague "tests pass."

| Plan | Grade | Notes |
|---|---|---|
| 01-01 | **A** | pytest tests/db/test_migration_0006.py -x -v + alembic upgrade head + ORM importability one-liner. Task 3 enumerates explicit pg_attribute/pg_indexes/information_schema queries for halfvec, partial index, GIN, CHECK constraint. Negative assertions (no body_md on ohlcv/macro/events, dormant tables untouched) are present. |
| 01-02 | **B+** | Verify uses introspection one-liner + pytest tests/test_cli_collect_all.py. Missing: no verification that tests/test_cli_default_flags.py still passes (it cannot - see R-1). The grep -c "vault-root" from stock --help is good but the test_cli_default_flags.py blind spot weakens grade. |
| 01-03 | **A** | DB-state SELECTs with explicit values, revision-detection via caplog, test_collect_macro_no_markdown_written negative fence. Schema invariant check is exactly the right Veto #6 enforcement. |
| 01-04 | **A** | OHLCV roundtrip including T+2 COALESCE (positive + negative), FK SET NULL on entity delete, holiday and missing_entity branches, Veto #6 schema check, no-markdown fence. |
| 01-05 | **A** | FK JOIN between events.filing_rcept_no and filings.rcept_no asserted; KIND-only event creates events but NOT filings; idempotent skip; CHECK constraint; no-markdown fence. |
| 01-06 | **A** | url_hash64 stability, content_hash diff drives inserted/updated/skipped, GIN array roundtrip + EXPLAIN index-scan check, R-09 startup guard, no-markdown fence. |
| 01-07 | **A-** | 200KB body roundtrip + count(*) FROM chunks == 0 is gold-standard Veto #8 check. Bug C entity upsert path reproducible. Minor weakness: no test ensures legacy tests/test_collect_dart.py is deleted - see R-2. |
| 01-08 | **A** | best-effort failure path (mock failing engine) tested; JSONB roundtrip query precise; CI guard has 3 assertions (file, importable, AST scan). |
| 01-09 | **B+** | Smoke test asserts macro_series count + collector_runs count + vault/raw/ absence. Runtime guard verification uses grep -vc FATAL (a count assertion, fragile). Bash `rm` on Windows needs portability note - pathlib.Path.unlink() is preferable. Interface table has a name typo (vault_path_for_kind_event vs actual vault_path_for_kind), harmless. |

**Overall:** verification quality is high. The pattern of pairing positive DB-state SELECT with negative vault/raw/ filesystem check is consistent across 01-03 through 01-07.


---

## Open Question Resolution (E)

From RESEARCH.md "Open questions remaining for the planner":

| # | Question | Disposition | Status |
|---|---|---|---|
| 1 | Live DB inventory (events empty?) | 01-01 task 1 docstring documents A1 assumption: rename safe even on populated DB | **DEFERRED with reasoning.** PLAN-INDEX explicitly says "Plans assume A1 (empty). Not blocking." STATE.md confirms baseline reset, testcontainer-only runtime. OK. |
| 2 | events_legacy vs kind_events naming | PLAN-INDEX picks Option B (rename old -> events_legacy, then create new events) | **RESOLVED** in 01-01 task 1. |
| 3 | collector_runs retention policy | PLAN-INDEX defers to Phase 9 | **DEFERRED appropriately.** 01-08 should note this in a code comment - currently does not. See Warning W-2. |
| 4 | macro_revisions audit-trail table | PLAN-INDEX "Out of scope; revisions surface via log + extra JSONB" | **RESOLVED as out-of-scope.** 01-03 task 3 captures revisions via caplog, consistent. |
| 5 | News fixtures rewrite budget | PLAN-INDEX "Absorbed into 01-06 task 3" | **RESOLVED.** 01-06 task 3 enumerates new test cases. tests/fixtures/news/ HTML samples still referenced indirectly via monkeypatching - not blocking. |
| 6 | # noqa: ARG001 on macro engine param | PLAN-INDEX "Done in 01-03 task 2" | **RESOLVED.** Plan 01-03 task 2 step 2 explicitly removes noqa. |
| 7 | _PHASE2_TABLES -> _LIVE_TABLES rename | PLAN-INDEX "Done in 01-01 task 3" | **RESOLVED.** |

All 7 carried-forward open questions have explicit disposition. None silently dropped.

---

## Risks (F)

### F-1 (MEDIUM) - Migration 0006 halfvec column declaration ambiguity
Plan 01-01 task 1 lets you pick (a) UserDefinedType or (b) raw op.execute("ALTER TABLE ... ADD COLUMN body_embedding halfvec(1024)"). Plan picks (b). But ORM model in Task 2 still needs _HalfVec UserDefinedType. The two definitions could drift. Mitigation: strengthen test_orm_round_trip to verify ORM model column type produces same format_type string as live DB.

### F-2 (LOW) - Legacy index ix_events_corp_code_time
Migration 0001 creates this index on the OLD events table. After RENAME TO events_legacy, the index follows the table and keeps its name. The NEW events table declares distinct index names (ix_events_ticker_date, ix_events_type_date) - no collision. Safe in practice. Plan task 1 step 1 is overcautious; no real problem.

### F-3 (LOW) - DART body_md size - psycopg3 TEXT roundtrip at MB scale
RESEARCH.md says "whole 사업보고서, up to ~MB scale text." Plan 01-07 task 1 tests with 100KB; task 3 tests with 200KB. Neither approaches 1MB. psycopg3 handles multi-MB TEXT, but a 1-2MB fixture would catch unexpected timeouts. Not blocking. See R-7.

### F-4 (LOW) - 01-08 record_collector_run best-effort failure semantics
Helper catches all exceptions and logs WARNING. Risk of leaking half-open transaction - but the current pattern is `with engine.begin() as conn` INSIDE record_collector_run, so transaction scope is local. Verified safe.

### F-5 (LOW) - 01-09 runtime guard placement at main() top
Guard hard-codes 5 relative paths. Risk: running stock from non-repo-root will trip incorrectly OR miss a resurrected writer.py. Mitigation: use absolute path via Path(__file__).resolve().parents[2] like the CI guard. See R-5.

### F-6 (HIGH) - tests/test_cli_default_flags.py blocks CI after Wave 0
File asserts `assert "default: vault" in help_text`. After 01-02 task 1 deletes the --vault-root argument, help_text no longer contains "default: vault". The test fails. Plan 01-02 does not modify or delete tests/test_cli_default_flags.py. Wave 0 cannot land green. See R-1.

### F-7 (HIGH) - tests/test_collect_dart.py blocks CI after Wave 0 + Wave 2
Existing root-level test file calls collect_dart(corp_code="00126380", since="2026-01-01", vault_root=tmp_path). After 01-02 strips vault_root, every test in this file will raise TypeError. Plan 01-07 creates new directory tests/collectors/dart/ but does NOT delete the legacy file. Plan 01-09 also does not delete it. See R-2.

### F-8 (MEDIUM) - Portfolio.load(Path(".")) brittleness after vault_root removal
Plans 01-04 and 01-06 use repo_root = Path("."). Works only when process CWD is repo root. CI runs pytest from repo root, so tests pass. But `uv run stock collect krx` from any other dir will fail at Portfolio.load. Behavior regression vs v1.0. Mitigation: resolve repo_root via Path(__file__).resolve().parents[N] or env var. Latent operational issue, not strictly Phase 1 SC-blocking.

### F-9 (LOW) - Plan 01-08 task 2 import-statement contradiction
Plan claims "record_collector_run import has no heavy deps" but shared.run_log imports `from sqlalchemy import text` and `from sqlalchemy.engine import Engine` at module top. Rationale is inaccurate but functionally OK - SQLAlchemy is already transitive.

---

## Warnings (non-blocking)

### W-1 - Cross-wave vault_tmp fixture policy contradiction
01-04 task 3 says "OR keep using vault_tmp"; 01-09 task 1 says "If matches exist, FIX the consuming tests (chdir-based) rather than re-introducing the fixture." Pick one policy. See R-4.

### W-2 - collector_runs retention not noted in 01-08
The Phase 9 deferral is in PLAN-INDEX but not in plan or summary. Future maintainers will have to back-trace. See R-8.


---

## Required Changes

In priority order. R-1 and R-2 are BLOCKERS for Wave 0 / Wave 2; R-3 onward are quality fixes.

### R-1 (BLOCKER, Wave 0) - Update or delete tests/test_cli_default_flags.py

Add tests/test_cli_default_flags.py to Plan **01-02** files_modified. Either delete the file (the Gap-04-03 scenario disappears with the --vault-root flag) or rewrite both tests to verify the flag is GONE. Example replacement:

```python
def test_no_vault_root_flag_in_help():
    from cli.__main__ import build_parser
    help_text = build_parser().format_help()
    assert "vault-root" not in help_text
    assert "vault_root" not in help_text
```

Without R-1, Wave 0 leaves CI red and Wave 1 cannot start.

### R-2 (BLOCKER, Wave 2) - Address tests/test_collect_dart.py

Add tests/test_collect_dart.py to Plan **01-07** files_modified and to task 3 behavior. Options:

1. **Delete the file** - every assertion is path-based, every call passes vault_root=tmp_path. The new tests/collectors/dart/test_collect_dart.py covers the same surface plus SC-1 DB assertions.
2. Move + rewrite under tests/collectors/dart/. More work, no benefit.

Pick option 1. Without R-2, Wave 0 + Wave 2 leave CI red.

### R-3 (QUALITY, Wave 0) - Tighten tests/test_cli_collect_all.py rewrite scope in 01-02

Every test in tests/test_cli_collect_all.py (CA1-CA10) currently passes --vault-root str(tmp_path) as a CLI arg. All ten tests must lose that arg or fail with "argparse: unrecognized arguments". Add inline CA1..CA10 checklist to plan 01-02 task 3.

Also, test CA9 uses positional signature fake_collect_dart(*, corp_code, since, max_docs, vault_root, engine) - needs updating to drop vault_root parameter.

### R-4 (QUALITY, Wave 3) - Resolve vault_tmp fixture policy

Pick one of:
- **A (preferred):** krx test (01-04 task 3) MUST drop vault_tmp and use monkeypatch.chdir(tmp_path) with explicit portfolio file write. Then 01-09 cleanly removes vault_tmp from tests/collectors/conftest.py.
- **B:** Keep vault_tmp in conftest indefinitely; remove the deletion clause from 01-09 task 1 step 3.

Pick A. Update 01-04, 01-05, 01-06 task 3 wording to forbid vault_tmp instead of "OR keep using." Tests can still consume builtin tmp_path + monkeypatch.chdir.

### R-5 (QUALITY, Wave 3) - Make cli/__main__.py runtime guard CWD-independent

In 01-09 task 2:
```python
_REPO_ROOT = Path(__file__).resolve().parents[2]
_legacy_writers = [
    _REPO_ROOT / "src" / "collectors" / src / "writer.py"
    for src in ("dart", "krx", "news", "macro", "kind")
]
for _path in _legacy_writers:
    if _path.exists():
        raise SystemExit(f"FATAL: vault writer module resurrected ({_path}).")
```
Same pattern as tests/test_no_writer.py.

### R-6 (QUALITY, Wave 0) - Strengthen test_migration_0006.py ORM/migration parity

In 01-01 task 3 test_orm_round_trip, also verify the body_embedding column's format_type in live DB equals what ORM _HalfVec(1024) would compile to. Otherwise migration and ORM can silently diverge.

### R-7 (QUALITY, Wave 2) - Add ~2MB DART body roundtrip test

In 01-07 task 1, add test_upsert_filing_megabyte_scale_body round-tripping ~2MB body. Veto #8 implies multi-MB scale; 200KB test is good but doesn't probe ceiling.

### R-8 (DOC) - Reflect open question deferrals in plan summaries

01-08 SUMMARY should note "collector_runs retention deferred to Phase 9." 01-09 SUMMARY should note that vault/raw/ directory existence (vs. recreation under each source) is what the guard catches - empty dir from prior history is OK.

---

## Recommendation

**PASS-WITH-WARNINGS - proceed to /gsd:execute-phase 1 after applying R-1 and R-2.**

R-1 and R-2 are hard blockers: without them, Wave 0 + Wave 2 leave CI red and the executor's fast-failure loop will trip on existing tests that no plan addresses. They are trivial fixes (one file deletion each, one test rewrite) and can be folded into 01-02 and 01-07 with a small planner revision.

R-3 through R-8 are quality improvements; the executor can either apply them inline during execution or defer to a post-Phase 1 cleanup. They do not threaten the phase's success criteria.

The 9-plan structure is otherwise sound:
- Schema (01-01) is comprehensive and Veto-compliant.
- The four-wave dependency graph is correct and parallel-safe within each wave.
- Each Wave 1/2 plan follows the same walking-skeleton pattern (db_writer.py + unit tests + collector rewire + DB-assertion tests), which makes them easy to execute in parallel.
- Veto enforcement is layered (schema + DB tests + Python guards + runtime fences), matching the "defense in depth" prescription of RESEARCH.md Q9.
- The Success Criteria Coverage table in 01-09 closes the loop.

After R-1 and R-2 land in 01-02 and 01-07 respectively, this plan set is ready for execution.
