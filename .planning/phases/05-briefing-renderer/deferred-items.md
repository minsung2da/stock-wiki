# Phase 05 — Deferred / Out-of-Scope Items

Discoveries logged during execution that are NOT caused by the current plan's changes.
Per the executor SCOPE BOUNDARY rule: logged, not fixed.

## 05-05 — pre-existing full-suite test-ordering failures (NOT caused by weekly roll-up)

Running the full `pytest` suite (859 passed, 4 failed, 2 skipped, 17m10s) surfaced 4
failures. **All 4 are pre-existing and unrelated to the additive `src/briefing/weekly.py`
work** — each passes in isolation and passes when run alongside the new
`tests/briefing/test_weekly.py`; they only fail in the full ~860-test run (state/order
pollution), or depend on a live external API.

| Test | Class | Evidence it is out-of-scope |
|------|-------|------------------------------|
| `tests/mcp_v2/test_tokenizer.py::test_embedder_version_constant_imports_without_torch` | test-order pollution (torch already imported by an earlier test in the full run) | passes in isolation; does not import `briefing.*` |
| `tests/test_migration.py::test_downgrade_then_upgrade_idempotent` | alembic session-engine state after ~800 prior DB tests | passes in isolation and alongside `test_weekly.py` |
| `tests/test_migration_0002.py::test_downgrade_reverses_migration` | same alembic session-engine state pollution | passes in isolation and alongside `test_weekly.py` |
| `tests/test_api_probes.py::test_dart_fss_report_body_shape` | live external DART API probe (network-dependent AssertionError on remote body shape) | not a code test; external service |

Verification commands run:
- `pytest tests/test_migration.py::test_downgrade_then_upgrade_idempotent tests/test_migration_0002.py::test_downgrade_reverses_migration tests/mcp_v2/test_tokenizer.py::test_embedder_version_constant_imports_without_torch` → **3 passed** (isolation).
- `pytest tests/briefing/test_weekly.py <the 3 above>` → **11 passed** (new tests do not trigger the failures).

Recommendation: address full-suite test isolation (torch import fixture teardown +
per-test alembic engine, or `pytest-forked`/order-independence for the migration
downgrade tests) as a dedicated infra cleanup pass. Not a Phase-5 correctness issue.
