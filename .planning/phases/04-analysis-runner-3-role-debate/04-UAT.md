---
phase: 04
plan: 04-01
status: resolved
tested: 2026-07-06
resolved: 2026-07-06
resolution_commit: 7d11ffc
tests_total: 3
tests_passed: 3
tests_failed: 0
---

> **RESOLVED 2026-07-06 (commit `7d11ffc`).** GAP-1 + GAP-2 fixed in
> `src/analysis/checksum.py`; all 3 UAT cases now KEEP correctly. Re-run evidence:
> `_to_canonical(42.5,'조원')=4.25e13`; TEST A kept `{market_cap, foreign_pct}` no
> warnings; TEST B keeps real market_cap, drops fake; TEST C keeps `310`, drops
> fabricated. +22 regression tests (`tests/analysis/test_checksum.py`: 43 passed),
> including the previously-missing cross-form (unit-claim vs raw-digit-body) matrix.

# Phase 04-01 — UAT (D-03 numeric checksum)

Conversational UAT of the `src/analysis/checksum.py` feature built in plan 04-01,
run against REAL DART data (Samsung 사업보고서, 910,932 chars) + realistic Judge
fact shapes (`{key, value, unit}` with natural Korean units).

## Current Test

(complete — 2 gaps found)

## Test Log

### Test 1 — Korean-unit equivalence (`42.5조원` ≡ `42,500,000,000,000`) — ❌ FAIL
- **Expected (D-03):** a fact `market_cap=42.5조원` is KEPT when the body contains
  `42,500,000,000,000원` (value-equivalence).
- **Actual:** DROPPED → `warnings=['market_cap=42.5조원: not verifiable in source']`.
  Only `foreign_pct=53.1%` (×1 unit) was kept.

### Test 2 — Fabrication drop — ✅ PASS (but market_cap also wrongly dropped)
- Fabricated `fake_revenue=999조원` correctly dropped + warned. (The real
  `market_cap=42.5조원` was ALSO dropped — false negative, see Test 1.)

### Test 3 — Real DART body, bare count `310` — ❌ FAIL
- **Expected:** `subsidiaries=310` KEPT (`'310' in body == True`, "310개 종속기업").
- **Actual:** DROPPED. The extractor only surfaces unit-tagged financial spans, not
  bare counts, so `fact_supported(310, "", body)` = False.

## Root Cause (confirmed by diagnostic)

**GAP-1 (BLOCKER, SC#3 core) — claim-side Korean units not multiplied.**
`_to_canonical(value, unit)` (checksum.py:47) applies the KRW multiplier ONLY when
`unit.startswith("KRW")`. Candidates are tagged `guessed_unit="KRW원"/"KRW조"` by the
extractor (normalized correctly), but Judge facts carry NATURAL Korean units
(`"조원"`, `"억"`, `"백만원"`), which do NOT start with `"KRW"` → fall through to
`float(value)` unmultiplied. Evidence:
- `_to_canonical(42.5, '조원')` → `42.5` (should be `4.25e13`)
- `fact_supported(42.5, '조원', body)` → `False`
- `fact_supported(42_500_000_000_000, '원', body)` → `True`
→ Every 조/억/백만-unit financial fact from the debate is silently dropped. Only
raw-원 or %-unit facts survive. This defeats D-03's stated 3-way equivalence.
Unit tests (21 passed) missed it because they compared unit-form claim vs unit-form
body (both go through the same broken path → 42.5 == 42.5), never unit-form claim
vs raw-digit body (the real DART case).

**GAP-2 (MINOR) — bare counts not verifiable.**
`extract_numeric_candidates` surfaces only unit-tagged financial spans, so bare
counts (e.g. "310개") are never candidates → count-facts always drop. Lower
severity (D-03 targets financial numeric_facts), but should be acknowledged: the
Judge schema may need to restrict numeric_facts to financial values, or the gate
must accept bare-integer verbatim matches.

## Recommended Fix (gap closure)

- **GAP-1:** In `_to_canonical`, translate the Judge's natural Korean unit strings
  → the KRW multiplier family before comparison (map `조원|조 → ×1e12`, `억원|억 →
  ×1e8`, `백만원|백만 → ×1e6`, `원 → ×1`; leave `%|배|주|bps|foreign-ccy` as raw
  scalars). Add a regression test: unit-form CLAIM vs raw-digit BODY must match
  (the case the current suite lacks).
- **GAP-2:** Decide the numeric_facts contract — either (a) constrain the Judge
  schema to financial (unit-bearing) facts, or (b) add a verbatim bare-integer
  match path. Document in the plan.

Route: `/gsd:plan-phase 4 --gaps` (or a targeted quick fix to checksum.py + tests),
then re-run this UAT (unit-form-claim vs raw-digit-body must KEEP).
