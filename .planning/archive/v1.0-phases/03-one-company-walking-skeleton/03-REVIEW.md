---
phase: 03-one-company-walking-skeleton
reviewed: 2026-04-17T15:16:20Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - src/collectors/dart/client.py
  - src/collectors/dart/fetcher.py
  - src/collectors/dart/writer.py
  - src/ingest/injection_defense.py
  - src/ingest/embedder.py
  - src/ingest/tokenizer.py
  - src/ingest/chunking.py
  - src/ingest/parsers/dart.py
  - src/ingest/worker.py
  - src/ingest/rebuild.py
  - src/ingest/heartbeat.py
  - src/stock_mcp/search_core.py
  - src/stock_mcp/server.py
  - src/stock_mcp/tools/search.py
  - src/stock_mcp/errors.py
  - src/stock_mcp/models.py
  - src/cli/commands.py
  - src/db/migrations/versions/0002_phase03_chunking_columns.py
  - src/shared/frontmatter.py
  - tests/conftest.py
findings:
  critical: 0
  warning: 4
  info: 4
  total: 8
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-04-17T15:16:20Z
**Depth:** standard
**Files Reviewed:** 20
**Status:** issues_found

## Summary

The Phase 3 walking skeleton is architecturally sound. The primary security requirements are well met: SQL is 100% parameterized across the ingest worker and search core, no f-string interpolation reaches the database, `wrap_untrusted` is wired into search results, `detect_injection_patterns` is invoked in the ingest worker, and the RET-02 `documents.corp_code` filter uses a direct column predicate rather than a LEFT JOIN. The DART API key never touches a log or exception message.

Four warnings require attention before Phase 4 cut-over: (1) `DateRange.start`/`end` strings are passed into SQL date casts without ISO format validation — malformed inputs reach Postgres and produce opaque errors instead of a clean `StructuredError`; (2) the sliding-window chunker silently drops the final partial window when `step` divides evenly into token length, causing tail content loss; (3) `wrap_untrusted` hard-codes `trust_level="trusted"` for every search excerpt regardless of the document's actual provenance trust level, bypassing the D-19 gate; (4) the `pg_clean` conftest truncates tables with an f-string SQL interpolation of table names — while currently safe due to the allow-list guard, the pattern is explicitly flagged in the comment as an injection path if the table list ever becomes dynamic.

Four informational items are noted below.

## Warnings

### WR-01: DateRange strings reach Postgres without ISO-format validation

**File:** `src/stock_mcp/search_core.py:217-218` and `src/stock_mcp/models.py:10-15`

**Issue:** `DateRange.start` and `DateRange.end` are plain `str | None` fields with no format constraint. They flow directly into the SQL bind parameter `CAST(:date_from AS date)` and `CAST(:date_to AS date)`. Postgres will raise a generic `invalid input syntax for type date` error when the client passes a non-ISO string. That error is caught by the outer `except Exception` handler in `tools/search.py`, but it surfaces as `ErrorCode.INTERNAL` with a raw Postgres message rather than a user-actionable `INVALID_TICKER`-style response. It is also a minor DoS vector: a caller can repeatedly trigger expensive connection acquisition before the error is returned.

**Fix:** Add a Pydantic validator to `DateRange` that rejects strings that do not parse as ISO `YYYY-MM-DD`:

```python
from pydantic import field_validator

class DateRange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str | None = None
    end: str | None = None

    @field_validator("start", "end", mode="before")
    @classmethod
    def _validate_iso_date(cls, v: object) -> object:
        if v is None:
            return v
        try:
            date.fromisoformat(str(v))
        except ValueError:
            raise ValueError("date must be ISO YYYY-MM-DD")
        return v
```

---

### WR-02: Sliding-window chunker drops tail tokens when step divides evenly

**File:** `src/ingest/chunking.py:67-69`

**Issue:** The `range(0, len(ids), step)` loop emits a window starting at `start` but stops when `start >= len(ids)`. For a section of exactly `N * step` tokens, the final start offset is `(N-1)*step`, which yields tokens `(N-1)*step` through `(N-1)*step + win`. If `len(ids) == win` exactly (section that just barely exceeds `max_tokens`), `step = win - overlap = 448` for defaults, so `range(0, 512, 448)` = `[0, 448]`. The window at index `448` covers `ids[448:960]`, but `ids` only has 512 entries — `ids[512:960]` is empty and `tok.decode([])` returns an empty string. The empty chunk is inserted into the database silently.

More generally, whenever `len(ids) > win` and `(len(ids) - overlap) % step == 0`, the very last window starts exactly at `len(ids) - overlap`, producing only `overlap` tokens of real content padded to `win` with empty decode. The immediate consequence is junk empty-string chunks in the embedding index and wasted BM25 token rows.

**Fix:** Guard against empty decoded text before appending:

```python
for i, start in enumerate(range(0, len(ids), step)):
    piece = tok.decode(ids[start : start + win])
    if not piece.strip():
        continue
    chunks.append(Chunk(piece, len(chunks), sec.path, i))
```

---

### WR-03: `wrap_untrusted` hard-codes `trust_level="trusted"` for all search excerpts

**File:** `src/stock_mcp/search_core.py:299-304`

**Issue:** All retrieved chunks are wrapped with `trust_level="trusted"` regardless of the originating document's `provenance.trust_level`. Documents ingested from `semi_trusted` or `adversarial` sources will have their excerpts incorrectly marked as trusted in the `<untrusted>` XML delimiter sent to the downstream LLM. This defeats the D-19 three-layer injection defense: an adversarial forum post that survived ingest (adversarial docs are only skipped from LLM extraction in INGEST-09, not from retrieval) would be returned to the MCP client with `trust="trusted"`.

The `documents` table does not currently store `trust_level`, so the fix requires either (a) adding a `trust_level` column to `documents` populated from `fm.provenance.trust_level` during ingest, or (b) querying from the frontmatter at retrieval time. Option (a) is the correct path.

**Fix (interim):** As a minimum guard, pass `trust_level` from `row.source` using a per-source mapping while the column is added:

```python
_SOURCE_TRUST = {"dart": "trusted", "news": "semi_trusted", "note": "semi_trusted"}

trust = _SOURCE_TRUST.get(row.source or "", "semi_trusted")
excerpt = wrap_untrusted(
    raw_excerpt,
    source=(row.source or "unknown"),
    trust_level=trust,
    doc_id=doc_id_hex,
)
```

A Phase 4 follow-up should add `documents.trust_level CHAR(12)` and populate it in `worker.py`'s `_INSERT_DOC_SQL`.

---

### WR-04: conftest `pg_clean` uses f-string SQL interpolation for table names

**File:** `tests/conftest.py:119`

**Issue:** `conn.execute(sa.text(f"TRUNCATE {tbl} RESTART IDENTITY CASCADE"))` interpolates `tbl` directly into the SQL string. The comment on lines 114-117 acknowledges this pattern and correctly notes it is currently safe because `tbl` is filtered from `_PHASE2_TABLES`. However, the comment itself states "would become an injection path if _PHASE2_TABLES ever grew dynamic entries." The allow-list guard in the comprehension on line 112 (`[t for t in _PHASE2_TABLES if t in existing]`) filters by membership in `_PHASE2_TABLES`, not by safe character class — a future developer adding a table name with a SQL metacharacter to `_PHASE2_TABLES` would not receive a warning. The project-wide rule (worker.py line 21: "zero f-string SQL") applies to test infrastructure as well.

**Fix:** Use `sa.text` with an identifier-safe pattern. SQLAlchemy does not support bind parameters for identifiers, but `psycopg`'s `sql.Identifier` does:

```python
from psycopg import sql as psql

for tbl in to_truncate:
    conn.execute(
        sa.text(
            psql.SQL("TRUNCATE {} RESTART IDENTITY CASCADE")
            .format(psql.Identifier(tbl))
            .as_string(conn.connection.driver_connection)
        )
    )
```

Alternatively, build a hard-coded allow-list pattern that verifies `tbl` matches `^[a-z_]+$` before interpolation:

```python
import re
_SAFE_TABLE_RE = re.compile(r"^[a-z_]+$")
for tbl in to_truncate:
    assert _SAFE_TABLE_RE.match(tbl), f"unsafe table name: {tbl!r}"
    conn.execute(sa.text(f"TRUNCATE {tbl} RESTART IDENTITY CASCADE"))
```

## Info

### IN-01: `client._initialized` global is not reset between test runs

**File:** `src/collectors/dart/client.py:25-45`

**Issue:** `_initialized` is a module-level boolean. Once `get_client()` succeeds in one test, it remains `True` for subsequent tests in the same process. If a test sets `DART_API_KEY` and calls `get_client()`, then a later test unsets the env var, `get_client()` will return silently without re-reading the env var even though the key is no longer present. This is not a bug in production (where the key is stable), but it creates subtle test ordering dependencies and can mask missing-key failures when running tests in parallel.

**Fix:** Expose a `_reset()` helper (test-only) or use the lazy singleton only within a `pytest.fixture` that patches the module-level flag. No production code change required.

---

### IN-02: `chunk_document` receives a `sections` list typed as `list` (no element type)

**File:** `src/ingest/chunking.py:51`

**Issue:** `chunk_document(sections: list, ...)` accepts `list` with no type annotation for elements. The function accesses `sec.text` and `sec.path` on each element. If a caller passes a list of strings or dicts (e.g., from a mock that returns raw text instead of `Section` objects), the `AttributeError` will be cryptic. Given that `parse_sections` returns `list[Section]`, this is a narrowing opportunity.

**Fix:** Tighten the signature to `sections: list[Section]` (import `Section` from `ingest.parsers`). The circular-import concern is minimal since `parsers` is a sibling module; use `TYPE_CHECKING` if needed.

---

### IN-03: `rebuild_from_vault` has no transaction boundary around alembic round-trip

**File:** `src/ingest/rebuild.py:143-150`

**Issue:** Steps are: `command.downgrade(cfg, "base")` → `command.upgrade(cfg, "head")` → `ingest_run(...)`. If the process is killed or `upgrade` fails after `downgrade` completes, the database is left in a wiped state with no schema. There is no try/except or rollback path. This is partially acceptable for a Phase 3 tool (`--yes` bypass is explicit), but there is also no note in the docstring warning operators that an interrupted rebuild leaves an empty-schema DB.

**Fix:** Add an explicit warning to the docstring and, at minimum, verify schema health before the `ingest_run` call:

```python
# After upgrade, verify at least one known table exists before ingest.
with engine.connect() as conn:
    result = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'documents'")
    ).first()
if result is None:
    raise RuntimeError("alembic upgrade head did not create expected schema")
```

---

### IN-04: `DateRange` does not validate that `start <= end`

**File:** `src/stock_mcp/models.py:10-15`

**Issue:** `DateRange` allows `start="2026-12-31"` and `end="2025-01-01"`. In the SQL, this produces `first_seen_at >= '2026-12-31' AND first_seen_at < '2025-01-01'`, which is always false — returning zero results with no error. The silent empty result makes this hard to debug. This is lower priority than WR-01 but should be caught at the model layer.

**Fix:** Add a model validator after WR-01's field validators are in place:

```python
from pydantic import model_validator

@model_validator(mode="after")
def _start_before_end(self) -> "DateRange":
    if self.start and self.end and self.start > self.end:
        raise ValueError("start must be <= end")
    return self
```

---

_Reviewed: 2026-04-17T15:16:20Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
