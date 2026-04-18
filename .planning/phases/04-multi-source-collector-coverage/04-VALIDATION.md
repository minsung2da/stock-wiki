---
phase: 4
slug: multi-source-collector-coverage
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-18
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (Phase 3 established) |
| **Config file** | `pyproject.toml` / `pytest.ini` |
| **Quick run command** | `uv run pytest tests/collectors/ -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~30-60s |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest {scoped to touched module}`
- **After every plan wave:** Run `uv run pytest tests/collectors/`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

*To be populated by the planner as tasks are authored. Each task must have either
an `<automated>` verify command or a Wave-0 fixture dependency.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | — | — | COLL-02 | — | KRX writer refuses path traversal | unit | `pytest tests/collectors/krx/` | ❌ W0 | ⬜ pending |
| TBD | — | — | COLL-03 | — | news drops article w/ no ticker match | unit | `pytest tests/collectors/news/` | ❌ W0 | ⬜ pending |
| TBD | — | — | COLL-04 | — | macro append dedups (date,value) | unit | `pytest tests/collectors/macro/` | ❌ W0 | ⬜ pending |
| TBD | — | — | COLL-05 | — | `collect all` isolates failures | integration | `pytest tests/cli/test_collect_all.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/collectors/krx/` — pykrx OHLCV/flow/short response fixtures (pickle or CSV)
- [ ] `tests/fixtures/rss/hankyung.xml`, `edaily.xml` — RSS feed snapshots
- [ ] `tests/fixtures/news/*.html` — 한경/이데일리 article HTML snapshots for trafilatura
- [ ] `tests/fixtures/kind/*.html` — KIND 불성실공시 listing page snapshots (≥2)
- [ ] `tests/fixtures/ecos/*.json` — PublicDataReader response captures
- [ ] `tests/collectors/conftest.py` — shared fixtures (vault_root tmp dir, fake engine w/ entities)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| KIND robots.txt compliance at runtime | COLL-05 | robots.txt may change upstream; CI snapshot can drift | `curl https://kind.krx.co.kr/robots.txt` before first prod run; confirm target paths still permitted |
| Real ECOS series IDs resolve to expected Korean labels | COLL-04 | Requires live ECOS API key + network | Run `stock collect macro` once manually after `.planning/macro_series.yaml` is filled with verified IDs; inspect `vault/raw/macro/ecos/*.md` frontmatter |
| `collect all` JSON stderr report shape | COLL-05 | Schema is for downstream dashboards (Phase 8) | Run `stock collect all 2>report.json` and eyeball against D-20 schema |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
