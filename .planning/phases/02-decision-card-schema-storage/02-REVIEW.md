---
phase: 02-decision-card-schema-storage
reviewed: 2026-05-30T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - src/cards/__init__.py
  - src/cards/models.py
  - src/cards/store.py
  - src/db/entity_models.py
  - src/db/migrations/versions/0007_decision_cards.py
  - tests/cards/__init__.py
  - tests/cards/conftest.py
  - tests/cards/test_models.py
  - tests/cards/test_store.py
  - tests/conftest.py
  - tests/db/test_migration_0006.py
  - tests/db/test_migration_0007.py
findings:
  critical: 1
  warning: 6
  info: 4
  total: 11
resolved:
  fixed: 7        # CR-01, WR-01, WR-02, WR-03, WR-04, IN-01, IN-02 (commit 41e63a7)
  deferred: 3     # WR-05, WR-06, IN-04 (rationale below)
  no_action: 1    # IN-03 (empty package marker — correct as-is)
resolution_commit: 41e63a7
status: resolved
---

> **Resolution (2026-05-30, commit `41e63a7`):** The BLOCKER and all actionable
> warnings/info were fixed and verified (mypy clean, full cards suite green, 2 new
> regression tests added). See the **## Resolution** section at the bottom for the
> per-finding disposition. CR-01 was fixed with `AND status <> 'invalidated'` (not the
> reviewer's `AND status = 'active'`), because the existing, intentional
> `test_walk_includes_invalidated` test relies on the `superseded → invalidated`
> transition — the genuine defect was silent re-invalidation reason-clobbering, which
> the chosen guard fixes without breaking tested behavior.

# Phase 2: Code Review Report

**Reviewed:** 2026-05-30T00:00:00Z
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

The decision_card schema (Pydantic model + Alembic migration + CRUD store) is well structured
and the SQL surface is genuinely safe: every statement in `store.py` is a module-level `text()`
constant bound with parameters, with NO f-string interpolation (Veto #7 satisfied). The `pg_clean`
truncation in `tests/conftest.py` guards table names with a `_SAFE_TABLE_RE` allowlist before
interpolation. Hard Vetoes #2 (timed thesis), #3 (first-class contradictions), #6 (no embedding
column on `decision_cards`), and #8 (whole-card `body_md`) are correctly enforced at both the
model and DDL layers.

However, the review surfaced one BLOCKER and several WARNINGs centered on the store layer's
lifecycle-state handling:

- `invalidate()` unconditionally clobbers `status`, destroying `superseded` / chain-pointer
  state — the only lifecycle mutation in the file that lacks the defensive status guard
  `save_card()` carefully applies (BLOCKER).
- `body_md` is persisted twice — in its own column AND inside the `payload` JSONB — creating a
  silent consistency hazard that contradicts the file's own "body_md lives in its own column"
  contract.
- `get_active()` has a non-deterministic tie-break on equal `generated_at`.
- The `status` field is serialized into the stored `payload` JSONB (always `null`), so the
  on-disk payload no longer matches the §3 schema oracle.

No critical SQL-injection or secret-leak issues were found.

## Critical Issues

### CR-01: `invalidate()` clobbers `superseded`/`active` lifecycle state with no guard

**File:** `src/cards/store.py:102-109, 241-244`
**Issue:**
The `_INVALIDATE_SQL` statement is unconditional on the current status:

```sql
UPDATE decision_cards
   SET status = 'invalidated',
       payload = jsonb_set(payload, '{invalidation_reason}', to_jsonb(CAST(:reason AS text)))
 WHERE card_id = :cid
```

`save_card()` is careful to guard its supersession UPDATE with `AND status = 'active'` (line 78)
specifically so it "prevents clobbering an already-invalidated prior card" (docstring line 146-147).
`invalidate()` has no symmetric guard. Consequences:

1. **Chain corruption.** A card that was already `superseded` (so it carries a real
   `superseded_by` pointer and is part of a chain) can be flipped to `invalidated`. The DB now
   reports a card that is both the target of a `superseded_by` pointer AND `status='invalidated'`,
   an inconsistent lifecycle state the `status` CHECK constraint cannot catch (it only enumerates
   the three values, not their transition rules). `walk_supersedes` will then return a chain whose
   middle link claims `status='invalidated'` while a newer card still points at it via
   `superseded_by`.
2. **Re-invalidation overwrites history.** Calling `invalidate(card, "reason B")` on an
   already-invalidated card silently overwrites the prior `invalidation_reason` ("reason A") with
   no detection — the function still returns a card and reports success (rowcount=1).
3. **No active-only intent.** The lifecycle is documented as `active → superseded`
   (via `save_card`) and `active → invalidated` (via `invalidate`). Allowing
   `superseded → invalidated` is an undocumented, unintended transition that the tests never cover
   (every `test_invalidate*` only invalidates an `active` or chain-tail card; none invalidates a
   card that is currently `superseded` and still pointed at).

This is the data-integrity twin of the bug `save_card` explicitly defends against, left unguarded.

**Fix:**
Add a status guard mirroring `save_card`, and treat a no-op UPDATE as "not invalidatable" so the
caller can distinguish "missing" from "wrong-state":

```python
_INVALIDATE_SQL = text(
    """
    UPDATE decision_cards
       SET status = 'invalidated',
           payload = jsonb_set(payload, '{invalidation_reason}', to_jsonb(CAST(:reason AS text)))
     WHERE card_id = :cid
       AND status = 'active'
    """
)
```

With this guard, `result.rowcount == 0` already short-circuits to `None` (line 243), so an
attempt to invalidate a superseded/already-invalidated card returns `None` instead of silently
corrupting the chain. If the intended product behavior is "any non-invalidated card may be
invalidated," make that explicit (`AND status <> 'invalidated'`) and add a test for the
`superseded → invalidated` path — but `AND status = 'active'` is the conservative, chain-safe
default and matches `save_card`'s own guard rationale.

## Warnings

### WR-01: `body_md` is persisted twice (column + payload JSONB) — silent divergence hazard

**File:** `src/cards/store.py:124, 161, 168-169`; `src/cards/models.py:92`
**Issue:**
`body_md` is a declared field on `DecisionCard` (models.py:92), so `card.model_dump(mode="json")`
(store.py:161) emits it INTO the `payload` dict. `save_card` then `json.dumps`-serializes that
whole payload (including `body_md`) into the `payload` JSONB column, AND separately binds
`card.body_md` into the dedicated `body_md` column (store.py:169). The full markdown body is thus
stored twice in every row.

On read, `_row_to_card` rebuilds the dict as `{**payload, "body_md": body_md, ...}` (line 124),
where the column value overrides the payload copy — so reads are self-consistent today. But:

- The two copies can drift if any external SQL writer (the migration docstring explicitly
  contemplates "any external SQL writer") updates one and not the other.
- It contradicts this file's own contract: `_row_to_card`'s docstring says "``body_md`` lives in
  its own column (Veto #8 — whole-card TEXT, never chunked)" — implying it is NOT also in the
  payload.
- For large filing-derived bodies this doubles row size for no functional gain (out-of-scope as a
  perf issue, but it is a correctness/consistency smell).

**Fix:**
Exclude `body_md` (and see WR-02 re `status`) from the payload serialization so the column is the
single source of truth:

```python
payload = card.model_dump(mode="json", exclude={"body_md", "status"})
```

and reconstruct with `{**payload, "body_md": body_md, "status": status}` as today. Verify
`test_jsonb_payload_roundtrip` and `test_save_and_get_active` still pass (they assert on
`payload->'decision'` and on the reconstructed object, neither of which needs `body_md` inside
the JSONB).

### WR-02: `status` is serialized into the stored `payload` JSONB (always `null`), breaking §3-schema parity

**File:** `src/cards/store.py:161, 168`; `src/cards/models.py:104`
**Issue:**
`status` is a declared model field (models.py:104), so `model_dump(mode="json")` includes
`"status": null` in the dict that gets stored in the `payload` JSONB. The lifecycle status is
supposed to live ONLY in the `decision_cards.status` column — the model docstring states it
"lives in the decision_cards.status DB COLUMN ..., NOT in the §3 YAML payload" (models.py:98-99),
and the migration docstring locks `payload` to the §3 schema. Storing a `status` key inside the
payload means the persisted JSONB no longer matches the §3 oracle, and a future consumer reading
`payload->>'status'` would see a stale `null` rather than the real lifecycle value in the column.
The same applies to `invalidation_reason` (stored as `null` on initial insert, then later
overwritten by `jsonb_set` in `invalidate`).

**Fix:** Exclude both store-layer-only fields from the payload (combined with WR-01):

```python
payload = card.model_dump(mode="json", exclude={"body_md", "status"})
```

Keep `invalidation_reason` out of the initial payload too (it is `None` at insert time and is
written by `invalidate`'s `jsonb_set` only when actually invalidated), so a fresh card's payload
contains exactly the §3 fields.

### WR-03: `get_active()` ordering is non-deterministic on equal `generated_at`

**File:** `src/cards/store.py:82-92, 185-197`
**Issue:**
`_SELECT_ACTIVE_SQL` is `ORDER BY generated_at DESC LIMIT 1` with no tie-breaker. Two active cards
for the same `corp_code` with the same `generated_at` (e.g. two same-minute analyses, or any case
where supersession was not used) make the "latest active card" arbitrary across runs and across
Postgres plan changes. The model permits multiple active cards per corp (nothing enforces a single
active card per corp), so this is reachable, not theoretical. `_make_card` in the tests even
reuses the fixture's identical `generated_at` for several cards (test_store.py:50-54) — the only
reason existing tests are stable is that they never assert `get_active` across two same-timestamp
active cards.

**Fix:** Add a deterministic secondary sort key (PK):

```sql
 ORDER BY generated_at DESC, card_id DESC
 LIMIT 1
```

Consider whether the domain actually wants at most one active card per corp; if so, that is a
stronger invariant (partial unique index `WHERE status='active'`) but is a Phase-3+ schema change,
out of scope here.

### WR-04: `getattr(card, "supersedes", None)` is dead/misleading defensive code

**File:** `src/cards/store.py:157-159`
**Issue:**
```python
effective_supersedes = supersedes or getattr(card, "supersedes", None)
```
`DecisionCard` has `model_config = ConfigDict(extra="forbid")` and declares no `supersedes`
field, so `getattr(card, "supersedes", None)` can only ever return `None`. The fallback is dead
code. Worse, it is subtly misleading: it implies a card might carry a `supersedes` attribute,
which the schema forbids. It also means a caller passing `supersedes=""` (empty string) would fall
through the `or` to the dead getattr and produce `None` — an empty-string card_id is already
invalid, but the `or` masks it rather than failing.

**Fix:** Drop the getattr fallback; bind the keyword directly:

```python
effective_supersedes = supersedes
```

If a future card model ever gains a `supersedes` field, reintroduce the merge deliberately with a
test.

### WR-05: `invalidate()` re-SELECT can race; reason write not re-checked

**File:** `src/cards/store.py:241-248`
**Issue:**
`invalidate` performs the UPDATE and the re-SELECT inside one `engine.begin()` transaction (good),
but the returned object is built from a fresh `_SELECT_BY_ID_SQL` rather than a `RETURNING` clause.
Within the same transaction this is correct, but it issues a second round-trip and re-parses the
whole payload purely to surface `.status`/`.invalidation_reason`. More importantly, because the
UPDATE has no status guard (see CR-01), the re-SELECT will faithfully return a card it should never
have mutated, giving false confidence that the operation "succeeded."

**Fix:** Primary fix is CR-01 (add the status guard). Optionally collapse the two statements using
`RETURNING payload, body_md, status` on the UPDATE to avoid the second query:

```python
_INVALIDATE_SQL = text(
    """
    UPDATE decision_cards
       SET status = 'invalidated',
           payload = jsonb_set(payload, '{invalidation_reason}', to_jsonb(CAST(:reason AS text)))
     WHERE card_id = :cid
       AND status = 'active'
    RETURNING payload, body_md, status
    """
)
# row = conn.execute(_INVALIDATE_SQL, {...}).first(); return None if row is None
```

### WR-06: No DB-level enforcement that an active card carries `expires_at`/non-empty assumptions (Veto #2 only half-covered at storage)

**File:** `src/db/migrations/versions/0007_decision_cards.py:108`; `tests/db/test_migration_0007.py:155-217`
**Issue:**
Veto #2 ("no untimed thesis") is enforced two ways: `expires_at NOT NULL` at the DB (good) and
`assumptions: min_length=1` at the Pydantic layer. But the store layer is NOT the only writer —
`test_body_tsv_generated` (test_migration_0007.py:198-217) inserts a row via raw SQL with a
`payload` of `'{"decision": {"stance": "HOLD"}}'`, i.e. NO `assumptions`, NO `key_claims`. That
row would fail `DecisionCard.model_validate` if ever read back through `get_active`/`walk_supersedes`
(it lacks mandatory fields), raising `ValidationError` deep inside the store rather than at the
write boundary. The migration docstring itself acknowledges "any external SQL writer stays
correct" for `body_tsv`, but there is no constraint ensuring `payload` is a well-formed card. The
empty-assumptions veto is therefore enforceable only when writes go through the Pydantic model —
which the test suite itself demonstrably bypasses.

**Fix:** This is a known layering decision (Pydantic is the gate), so it is a WARNING not a
BLOCKER. Two mitigations, pick one:
- Document explicitly in `store.py`/migration that raw `payload` inserts bypass Veto #2/#5 and
  MUST NOT be used outside tests, and isolate the test insert so it cannot be copied as a pattern.
- Or add a lightweight CHECK on `payload ? 'assumptions'` and
  `jsonb_array_length(payload->'assumptions') >= 1` so even raw SQL writers cannot persist an
  untimed/assumption-less card. (CHECK on JSONB is valid in PG17.)

## Info

### IN-01: `walk_supersedes` magic number `100` for the cycle/depth guard

**File:** `src/cards/store.py:208, 217`
**Issue:** The depth cap `100` is an undocumented magic literal. The `seen` set already guarantees
termination on a true cycle (any repeated `card_id` stops the loop); the `len(chain) < 100` clause
is a secondary cap whose value has no stated rationale and silently truncates a legitimate chain
longer than 100 with no warning/log.
**Fix:** Hoist to a named module constant (`_MAX_SUPERSEDE_DEPTH = 100`) and either log when the
cap is hit or rely solely on the `seen` cycle guard (which is already correct for cycles). At
minimum, a comment on why 100 is the chosen ceiling.

### IN-02: `_row_to_card` mutates via dict-merge order that masks a payload `status` key

**File:** `src/cards/store.py:124`
**Issue:** `{**payload, "body_md": body_md, "status": status}` relies on the explicit keys winning
over any same-named keys already in `payload` (which today exist — see WR-02). This is correct
Python dict semantics, but it is load-bearing behavior that is undocumented at the call site and
only works because of WR-01/WR-02's accidental double-storage. Once WR-01/WR-02 are fixed the
override stops being a silent fallback and becomes the sole source — worth an inline comment.
**Fix:** After fixing WR-01/WR-02, add a brief comment that `status`/`body_md` are intentionally
injected from columns, not payload.

### IN-03: `tests/cards/__init__.py` is empty (0 lines) — package marker only

**File:** `tests/cards/__init__.py:1`
**Issue:** Not a defect; noted for completeness. The file is a bare package marker, consistent with
the other test packages. No action needed.
**Fix:** None.

### IN-04: Migration `down_revision`/`revision` are bare strings, not zero-padded vs. file prefix consistency check

**File:** `src/db/migrations/versions/0007_decision_cards.py:63-64`
**Issue:** `revision = "0007"` / `down_revision = "0006"` match the prior file's `revision = "0006"`,
so the chain is intact. This is fine; flagged only to note there is no automated test asserting the
Alembic revision chain is linear/consistent (the migration tests assert resulting schema shape, not
the revision graph). A broken `down_revision` would surface only at `alembic upgrade head` time.
**Fix:** Optional: add a test that `alembic history` is linear and head == "0007". Low priority.

---

## Resolution (commit `41e63a7`)

| ID | Severity | Disposition | Notes |
|----|----------|-------------|-------|
| CR-01 | BLOCKER | ✅ Fixed | `invalidate()` now guards `AND status <> 'invalidated'` → idempotent, no reason-clobbering. Used `<> 'invalidated'` (not `= 'active'`) because `test_walk_includes_invalidated` relies on the intended `superseded → invalidated` transition. New test `test_invalidate_twice_is_noop_and_preserves_reason` locks it. |
| WR-01 | Warning | ✅ Fixed | `body_md` excluded from payload JSONB (`_PAYLOAD_EXCLUDE`). Direct test assertion `payload ? 'body_md' IS false` added — protects Veto #13. |
| WR-02 | Warning | ✅ Fixed | `status` (+ `invalidation_reason`) excluded from payload; stored payload is now exactly the §3 schema. |
| WR-03 | Warning | ✅ Fixed | `get_active` ORDER BY now `generated_at DESC, card_id DESC` (deterministic). |
| WR-04 | Warning | ✅ Fixed | Dead `getattr(card, 'supersedes', None)` fallback removed. |
| IN-01 | Info | ✅ Fixed | Magic `100` hoisted to `_MAX_SUPERSEDE_DEPTH` with rationale comment. |
| IN-02 | Info | ✅ Fixed | Inline comment added in `_row_to_card` documenting the column-injection of `body_md`/`status`. |
| WR-05 | Warning | ⏸ Deferred | The `RETURNING` collapse is a perf/round-trip optimization only; CR-01's guard fully addresses the correctness concern (no false "success" on a no-op). Optional Phase 3+ cleanup. |
| WR-06 | Warning | ⏸ Deferred | A JSONB CHECK enforcing `assumptions` is a **schema change** (new migration) and a design decision: Pydantic (`save_card`) is the documented single write-gate for app code; the only bypass is the test's raw insert. Tracked as a follow-up (defense-in-depth, not a bug). |
| IN-03 | Info | — No action | Empty `tests/cards/__init__.py` is a correct package marker. |
| IN-04 | Info | ⏸ Deferred | Optional `alembic history` linearity test — low priority; revision chain (`0007`→`0006`) is intact. |

**Verification after fix:** `mypy --strict` clean on `store.py`/`models.py`; `tests/cards` + `tests/db/test_migration_0007.py` → **19 passed**; full non-slow suite re-run pending in completion gate.

---

_Reviewed: 2026-05-30T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
_Resolved: 2026-05-30 (commit 41e63a7) — orchestrator_
