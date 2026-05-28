---
phase: 02-canonical-entity-identity
reviewed: 2026-04-17T00:00:00Z
depth: standard
files_reviewed: 18
files_reviewed_list:
  - fixtures/entities/amendment_case.yaml
  - fixtures/entities/rename_case.yaml
  - fixtures/entities/split_case.yaml
  - fixtures/entities/ticker_recycle.yaml
  - pyproject.toml
  - src/db/alembic.ini
  - src/db/engine.py
  - src/db/entity.py
  - src/db/migrations/env.py
  - src/db/migrations/versions/0001_phase02_initial_schema.py
  - src/shared/content_hash.py
  - src/shared/frontmatter.py
  - tests/conftest.py
  - tests/fixtures_loader.py
  - tests/test_content_hash.py
  - tests/test_documents_dedup.py
  - tests/test_entity_resolve.py
  - tests/test_migration.py
  - tests/test_pg_fixture.py
  - tests/test_supersedes_edge.py
findings:
  critical: 0
  warning: 5
  info: 4
  total: 9
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-04-17T00:00:00Z
**Depth:** standard
**Files Reviewed:** 18
**Status:** issues_found

## Summary

Phase 02 establishes canonical entity identity — the `entities`, `entity_aliases`, `documents`, `chunks`, `edges`, `events`, and `ingest_runs` schema — plus the `resolve_entity` lookup function and `content_hash` utility. The overall design is solid: all SQL uses bind parameters, the D-12 digit-length gate prevents most injection vectors before SQL is even reached, and the migration covers the meaningful downgrade case.

Five warnings and four info items were found. No critical issues (no SQL injection, no hardcoded secrets, no authentication bypasses). The most consequential findings are the `test_downgrade_then_upgrade_idempotent` test which silently leaves the session-scoped engine in a post-downgrade state for any test that runs after it, and the unvalidated `value` string in `resolve_entity`'s 8-digit branch which bypasses the digit-only gate.

---

## Warnings

### WR-01: `resolve_entity` — 8-digit branch does not verify digits-only

**File:** `src/db/entity.py:46-53`

**Issue:** `_is_digits(value, 8)` is checked before the 6-digit ticker branch, so an 8-character string that contains non-digit characters (e.g., `"abc12345"`, `"KOSPI001"`) falls through to the `else: return None` path correctly. However, a string like `"0012638\n"` (length 8, contains a newline) returns `False` from `isdigit()` — that part is safe. The real gap is that `_is_digits` is only called in the `if`/`elif` branches, yet the docstring comment at line 9 claims "Digit/length pre-filter (D-12) ensures only `^\d{8}$` or `^\d{6}$` strings reach the database." The 8-digit corp_code SQL path does not use a ticker alias join — it goes directly to `SELECT … FROM entities WHERE corp_code = :v`. Because `corp_code` is a `CHAR(8)` primary key, Postgres will happily accept and match any 8-character string including ones with spaces or unusual Unicode that `isdigit()` might consider numeric (e.g., superscript digits `²³` return `True` from Python's `str.isdigit()`). A value like `"²²²²²²²²"` (8 superscript-two characters) passes `_is_digits(value, 8)` and reaches the DB query, even though no valid corp_code will ever contain them. This is a correctness gap, not a security hole (bind parameter prevents injection), but it silently returns `None` only because no match exists rather than rejecting malformed input at the gate as the docstring promises.

**Fix:**
```python
import re

_CORP_CODE_RE = re.compile(r"^\d{8}$")  # ASCII digits only
_TICKER_RE    = re.compile(r"^\d{6}$")

def resolve_entity(engine: Engine, value: str, as_of: date | None = None) -> Entity | None:
    if _CORP_CODE_RE.match(value):
        ...
    elif _TICKER_RE.match(value):
        ...
    else:
        return None
```
Using `re` with `\d` in ASCII (or `[0-9]`) closes the superscript-digit loophole and makes the gate exactly match the documented invariant. `str.isdigit()` accepts non-ASCII digit characters in Python.

---

### WR-02: `test_downgrade_then_upgrade_idempotent` corrupts session-scoped engine state

**File:** `tests/test_migration.py:257-271`

**Issue:** `pg_engine` is `scope="session"` — it is shared across all tests in the process. `test_downgrade_then_upgrade_idempotent` calls `command.downgrade(cfg, "base")` which drops all tables, then calls `command.upgrade(cfg, "head")` to restore them. If any test that uses `pg_engine` or `pg_clean` runs **after** this test (pytest ordering is alphabetical by default and not guaranteed across files), it will operate on the re-upgraded schema, but the `pg_clean` fixture's `TRUNCATE … RESTART IDENTITY CASCADE` will succeed silently because the tables exist again. The ordering danger is real: because `test_migration.py` is alphabetically before `test_supersedes_edge.py` and `test_entity_resolve.py`, and the downgrade/upgrade test runs last within `test_migration.py`, if other test files are collected after it, they will run against a freshly-recreated (empty) schema rather than the state left by prior test setup. More importantly, if a future test is added between this test and the final re-upgrade — or if test collection order changes — it will fail with `UndefinedTable` errors rather than the actual assertion.

**Fix:** Isolate this test in its own pytest session (e.g., separate invocation or `--forked`) or use a function-scoped engine for the downgrade/upgrade round-trip:
```python
def test_downgrade_then_upgrade_idempotent(pg_engine):
    """Run in isolation — creates a second engine to avoid session state bleed."""
    import os
    from testcontainers.postgres import PostgresContainer
    from alembic import command
    from alembic.config import Config

    url = os.environ["DATABASE_URL"]
    cfg = Config("src/db/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.downgrade(cfg, "base")
    assert not REQUIRED_TABLES.issubset(_fetch_tables(pg_engine))
    command.upgrade(cfg, "head")
    assert REQUIRED_TABLES.issubset(_fetch_tables(pg_engine))
    command.upgrade(cfg, "head")  # idempotent check
    assert REQUIRED_TABLES.issubset(_fetch_tables(pg_engine))
```
Alternatively, mark this test with `@pytest.mark.last` (using `pytest-ordering`) so it always runs after all other session-engine tests, or add a `yield`-based teardown that calls `upgrade head` before the fixture ends.

---

### WR-03: `pg_clean` TRUNCATE uses f-string on a constant list — safe today, fragile by design

**File:** `tests/conftest.py:115`

**Issue:** The comment "Trusted constant list — not user input; safe f-string composition" is accurate for the current code. However, `_PHASE2_TABLES` is a module-level tuple that a future developer could extend with a table whose name is derived from a variable or config read. If that ever happens, the f-string `TRUNCATE {', '.join(to_truncate)} RESTART IDENTITY CASCADE` becomes an injection path. The comment acknowledges the assumption but does not enforce it. Because this is test infrastructure, the risk is low — but the pattern sets a precedent that bleeds into production code.

**Fix:** Use parameterized per-table TRUNCATE calls instead:
```python
for tbl in to_truncate:
    conn.execute(sa.text(f"TRUNCATE {tbl} RESTART IDENTITY CASCADE"))
    # tbl is guaranteed to be a member of _PHASE2_TABLES (filtered from
    # information_schema); information_schema.table_name cannot contain SQL metacharacters.
```
Or, accept a small performance tradeoff and use individual DELETE statements with `sa.text("DELETE FROM entities")` per table for truly injection-proof cleanup.

---

### WR-04: `content_hash.compute_content_hash` opens file path without validation — path traversal risk

**File:** `src/shared/content_hash.py:27-33`

**Issue:** `compute_content_hash(path: str)` passes `path` directly to `fm.load(path)` with no validation. If the caller passes an attacker-controlled path (e.g., from a filename embedded in a collected document's frontmatter), this can read arbitrary files on the system. In the current codebase, callers appear to be controlled, but this module is marked as a shared utility intended for use by all collectors and the ingest pipeline. A collector receiving a DART attachment with a crafted filename could trigger traversal.

**Fix:**
```python
from pathlib import Path

def compute_content_hash(path: str) -> str:
    """Per D-13: sha256 of frontmatter-stripped, normalized body."""
    resolved = Path(path).resolve()
    # Callers should pass vault-relative paths; enforce vault root if known.
    post = fm.load(str(resolved))
    return hashlib.sha256(normalize_body(post.content).encode("utf-8")).hexdigest()
```
At minimum, call `Path(path).resolve()` to canonicalize the path, eliminating `../` traversal components. If the vault root is accessible, add a `resolved.is_relative_to(vault_root)` guard.

---

### WR-05: `write_frontmatter` opens file for writing without atomic write — partial write on crash

**File:** `src/shared/frontmatter.py:104-117`

**Issue:** The docstring says "Content is fully computed before the file is opened, so a serialization error will not leave a zero-byte or partial file." This is partially true: `fm.dumps(post)` is called before `open(path, "w")`, so a serialization error won't create a truncated file. However, a crash (SIGKILL, power loss, KeyboardInterrupt) during the `f.write(content)` call **will** leave a partial file because the write is not atomic. For a vault that is the "single source of truth" (per CLAUDE.md), a partial frontmatter write would corrupt the affected note silently — future reads would get a YAML parse error or incomplete data.

**Fix:** Use an atomic write pattern — write to a temporary file in the same directory, then `os.replace()`:
```python
import os
import tempfile
from pathlib import Path

def write_frontmatter(path: str, model: FrontMatter, body: str) -> None:
    post = fm.Post(body)
    post.metadata = model.model_dump(by_alias=True, exclude_none=True)
    content = fm.dumps(post)
    dir_ = Path(path).parent
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=dir_,
                                     delete=False, suffix=".tmp") as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    os.replace(tmp_path, path)  # atomic on POSIX; best-effort on Windows
```

---

## Info

### IN-01: `resolve_entity` — no test for non-digit 8-character input (e.g., `"KOSPI001"`)

**File:** `tests/test_entity_resolve.py:75-81`

**Issue:** `test_mismatch_length_returns_none` tests lengths 0, 4, 7 digits, and the string `"garbage"` (7 chars, non-digit). It does not test an 8-character string with non-digit characters such as `"KOSPI001"` or `"abc12345"`. Given WR-01 above (superscript digit bypass), a regression test would lock down the intended behavior.

**Fix:** Add a test case:
```python
assert resolve_entity(pg_clean, "KOSPI001") is None  # 8 chars, not all digits
assert resolve_entity(pg_clean, "²²²²²²²²") is None  # 8 superscript digits
```

---

### IN-02: `alembic.ini` — `sqlalchemy.url` left empty; no comment explaining the pattern

**File:** `src/db/alembic.ini:5`

**Issue:** `sqlalchemy.url =` is intentionally blank (env.py overrides it from `os.environ["DATABASE_URL"]`). Without a comment, a developer unfamiliar with the project might fill in a real URL, which would then be committed to git. The pattern is correct but undocumented in the file itself.

**Fix:** Add an inline comment:
```ini
# DO NOT set this value here. DATABASE_URL is injected at runtime from the
# environment variable. See src/db/migrations/env.py -> run_migrations_online().
sqlalchemy.url =
```

---

### IN-03: `migrations/env.py` — missing `run_migrations_offline` function

**File:** `src/db/migrations/env.py:30`

**Issue:** The file only implements `run_migrations_online()` and calls it unconditionally at module load time (`run_migrations_online()` on line 30). The standard Alembic template separates `run_migrations_offline` (for generating SQL scripts without a live DB) and `run_migrations_online` (for executing against a live DB), guarded by `if context.is_offline_mode()`. The current code will fail with `KeyError: 'DATABASE_URL'` if `alembic upgrade --sql` (offline mode) is ever used, e.g., to generate SQL for a DBA to review before applying. This is an operational gap, not a runtime bug in the normal path.

**Fix:**
```python
def run_migrations_offline() -> None:
    url = os.environ["DATABASE_URL"]
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

---

### IN-04: `fixture_loader` — entity aliases inserted with raw dict `a` without key validation

**File:** `tests/fixtures_loader.py:44-55`

**Issue:** The `entity_aliases` loop passes `a` (the raw YAML dict) directly as the params argument to `conn.execute(sql, a)`. If a future fixture YAML includes extra keys in an alias row (e.g., a comment field or a typo), SQLAlchemy's `text()` parameter binding will silently ignore unknown keys — but if a required key is missing (e.g., `valid_from` omitted), the error will be a `KeyError` or a database null-constraint violation rather than a clear missing-field error. The `entities` loop (lines 21-43) defensively unpacks each key with `.get()`, which is the correct pattern.

**Fix:** Apply the same explicit unpack to alias rows:
```python
conn.execute(
    sa.text("INSERT INTO entity_aliases ..."),
    {
        "corp_code": a["corp_code"],
        "kind": a["kind"],
        "value": a["value"],
        "valid_from": a["valid_from"],
        "valid_to": a.get("valid_to"),
    },
)
```
This catches missing required fields at the Python dict lookup before hitting the DB, giving a clear `KeyError` with the field name.

---

_Reviewed: 2026-04-17T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
