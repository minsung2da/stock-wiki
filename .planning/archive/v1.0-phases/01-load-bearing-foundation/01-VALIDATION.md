---
phase: 1
slug: load-bearing-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-17
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | FOUND-01 | — | N/A | integration | `docker compose up -d && docker compose exec db psql -U stock -c "SELECT * FROM pg_extension"` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | FOUND-02 | — | N/A | unit | `test -d raw && test -d notes && test -d ingested && test -d dashboards && test -d graph` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01 | 1 | FOUND-03 | — | N/A | unit | `grep -q "workspace" .gitignore` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | FOUND-05 | — | ingest venv has no anthropic | unit | `uv run pytest tests/test_venv_isolation.py` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 1 | FOUND-06 | — | N/A | unit | `uv run pytest tests/test_frontmatter.py` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 2 | COLL-07 | — | CI blocks anthropic imports | unit | `uv run pytest tests/test_import_guard.py` | ❌ W0 | ⬜ pending |
| 01-03-02 | 03 | 2 | OPS-06 | T-1-01 | secrets never committed | integration | `pre-commit run gitleaks --all-files` | ❌ W0 | ⬜ pending |
| 01-04-01 | 04 | 2 | FOUND-04 | — | N/A | manual | `scripts/migrate-to-wsl.sh` exists and is documented | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_frontmatter.py` — Pydantic round-trip stubs for FOUND-06
- [ ] `tests/test_import_guard.py` — AST-based import scan for COLL-07
- [ ] `tests/test_venv_isolation.py` — verify ingest venv excludes anthropic for FOUND-05
- [ ] `tests/conftest.py` — shared fixtures (tmp vault paths, sample YAML)
- [ ] pytest install via `uv add --dev pytest`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Obsidian opens vault at `\\wsl$\...` path | FOUND-04 | Requires GUI interaction | Open Obsidian, navigate to `\\wsl$\Ubuntu\home\yamin\stock`, verify vault loads |
| Docker compose extensions reachable | FOUND-01 | Requires Docker daemon running | `docker compose up -d`, then `docker compose exec db psql -U stock -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS vchord_bm25; CREATE EXTENSION IF NOT EXISTS pg_trgm;"` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
