"""End-to-end tests (Phase 3 Plan 06 — Task 2; JUDGE-04 automated portion).

The ``e2e`` pytest marker is registered in pyproject.toml. Slow / live-API
tests here are gated behind env vars (``DART_API_KEY``) and the ``slow``
marker; fast schema-contract tests run in the default suite.
"""
