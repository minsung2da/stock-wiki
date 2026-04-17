---
phase: 01-load-bearing-foundation
reviewed: 2026-04-17T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - .env.example
  - .gitignore
  - .obsidianignore
  - .pre-commit-config.yaml
  - docker-compose.yml
  - pyproject.toml
  - scripts/init-extensions.sql
  - scripts/migrate-to-wsl.sh
  - src/shared/frontmatter.py
  - templates/portfolio.md
  - tests/conftest.py
  - tests/test_frontmatter.py
  - tests/test_import_guard.py
  - tests/test_secrets.py
findings:
  critical: 1
  warning: 4
  info: 4
  total: 9
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-04-17T00:00:00Z
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

This phase establishes the load-bearing foundation: schema models, infrastructure config, dev tooling, and CI guards. The overall structure is sound — Pydantic v2 models are well-designed, the 3-zone frontmatter pattern is clean, and the test suite covers the key behavioral contracts. One critical issue exists: a real credential value (`stockwiki_dev`) is committed in `.env.example`, which means it is already tracked in git history. Four warnings cover missing error handling in `frontmatter.py`, a shell script with variable quoting risks, a hardcoded personal path in a shared script, and a `docker-compose.yml` without restart policy. Info items flag minor quality gaps.

---

## Critical Issues

### CR-01: Real password committed in `.env.example`

**File:** `.env.example:8-9`
**Issue:** `POSTGRES_PASSWORD` and `DATABASE_URL` in `.env.example` both contain the actual development password `stockwiki_dev` in plain text. Unlike placeholder strings (e.g., `your_password_here`), this is a real credential. Because `.env.example` is committed, this password is now permanently in git history. If anyone clones the repo and uses this file as-is (the documented workflow), they will have a predictable, known password. More importantly, the pattern trains contributors to treat real values in example files as acceptable.

**Fix:**
```bash
# .env.example lines 8-9 — replace real values with descriptive placeholders
POSTGRES_PASSWORD=your_postgres_password_here
DATABASE_URL=postgresql://stockwiki:your_postgres_password_here@127.0.0.1:5432/stockwiki
```
Also update `docker-compose.yml` line 8 default fallback accordingly:
```yaml
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-change_me_in_dotenv}
```

---

## Warnings

### WR-01: `read_frontmatter` has no error handling for missing or malformed files

**File:** `src/shared/frontmatter.py:68-76`
**Issue:** `fm.load(path)` will raise `FileNotFoundError` if the path does not exist and `yaml.YAMLError` / `fm.YAMLException` if the YAML is malformed. Neither is caught. `FrontMatter.model_validate(dict(post.metadata))` will raise `pydantic.ValidationError` if `provenance.source` is missing. All three exceptions propagate uncaught to every caller across the ingest and MCP server layers. Because this function is the vault's primary read entry point, an error in any single note would crash the calling pipeline without a diagnostic message.

**Fix:**
```python
from pydantic import ValidationError

def read_frontmatter(path: str) -> tuple[FrontMatter, str]:
    """Read a markdown file and parse its frontmatter into a Pydantic model.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If frontmatter YAML is malformed or fails schema validation.
    """
    try:
        post = fm.load(path)
    except Exception as exc:
        raise ValueError(f"Failed to load frontmatter from {path!r}: {exc}") from exc
    try:
        model = FrontMatter.model_validate(dict(post.metadata))
    except ValidationError as exc:
        raise ValueError(f"Frontmatter schema validation failed for {path!r}: {exc}") from exc
    return model, post.content
```

### WR-02: `write_frontmatter` opens file without error handling; silent overwrite risk

**File:** `src/shared/frontmatter.py:79-88`
**Issue:** `open(path, "w", encoding="utf-8")` will silently overwrite an existing file with no guard. For vault notes that serve as the single source of truth, a partial write (e.g., due to `fm.dumps` raising an exception mid-flight) would corrupt the file. The file is opened before `fm.dumps(post)` is called, so any exception in `dumps` leaves a zero-byte or partial file at `path`.

**Fix:** Compute the content string before opening the file, so the open/write is atomic from the caller's perspective:
```python
def write_frontmatter(path: str, model: FrontMatter, body: str) -> None:
    post = fm.Post(body)
    post.metadata = model.model_dump(by_alias=True, exclude_none=True)
    content = fm.dumps(post)          # Compute before opening file
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
```
For stronger atomicity, write to a `.tmp` file and `os.replace()` into place.

### WR-03: Hardcoded personal path in shared migration script

**File:** `scripts/migrate-to-wsl.sh:16`
**Issue:** `SRC="/mnt/c/Users/minsu/workspace/stock"` is a hardcoded absolute path tied to a specific Windows username (`minsu`). Anyone else using this script (the project targets "2-5 people") will silently hit the `Source directory does not exist` guard at line 33 and abort — the script appears to work correctly but is not actually portable. The variable name `SRC` implies it should be configurable.

**Fix:**
```bash
# Replace hardcoded path with a configurable default
SRC="${STOCK_SRC:-/mnt/c/Users/$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r' || whoami)/workspace/stock}"
# Or simpler: require the caller to export STOCK_SRC, and fail clearly if not set
SRC="${STOCK_SRC:?Set STOCK_SRC to your Windows vault path, e.g. /mnt/c/Users/yourname/workspace/stock}"
```

### WR-04: `docker-compose.yml` has no restart policy; container will not recover after crash

**File:** `docker-compose.yml:4-17`
**Issue:** Without `restart: unless-stopped` (or equivalent), the Postgres container will not restart after a host reboot or after Docker daemon restart. Because the ingest pipeline and MCP server both depend on Postgres being available, any system restart would silently break all data collection and queries until the developer manually runs `docker compose up -d`. This is a reliability gap for a daily-batch pipeline.

**Fix:**
```yaml
services:
  postgres:
    image: tensorchord/vchord-suite:pg17-latest
    restart: unless-stopped   # Add this line
    ...
```

---

## Info

### IN-01: `pyproject.toml` pins `ruff>=0.15` but pre-commit config pins `ruff v0.11.7`

**File:** `pyproject.toml:44` and `.pre-commit-config.yaml:8`
**Issue:** The dev dependency specifies `ruff>=0.15` while the pre-commit hook pins `rev: v0.11.7`. These will diverge: `uv sync --group dev` installs ruff 0.15+, but `pre-commit run` uses 0.11.7. Rule sets, default behaviors, and `--fix` outputs may differ between these versions, meaning code that passes pre-commit may fail `ruff check` in CI and vice versa.

**Fix:** Align both to the same version. Pin the pre-commit rev to match the installed version:
```yaml
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.11.7        # bump to match pyproject.toml dev dep, or
```
Or relax `pyproject.toml` to match the pre-commit pin: `"ruff==0.11.7"`.

### IN-02: `test_secrets.py` does not test that `.env` itself is absent from the repo

**File:** `tests/test_secrets.py:14-55`
**Issue:** The test suite validates that `.env.example` exists and `.gitignore` contains `.env`, but it does not assert that no `.env` file is actually committed (i.e., that `PROJECT_ROOT / ".env"` does not exist in the working tree). A developer could accidentally commit `.env` and this test suite would not catch it.

**Fix:**
```python
def test_env_file_not_committed(self) -> None:
    """.env must not exist in the project root (it must remain gitignored)."""
    env_file = PROJECT_ROOT / ".env"
    assert not env_file.exists(), (
        ".env file found at project root — it must NOT be committed. "
        "Add real values to .env but keep it gitignored."
    )
```

### IN-03: `DerivedBlock.sentiment` and `DerivedBlock.numeric_facts` use untyped `dict` and `list[dict]`

**File:** `src/shared/frontmatter.py:48-49`
**Issue:** `sentiment: dict | None` and `numeric_facts: list[dict]` accept arbitrary structure. When Pydantic v2 serializes these, it performs no validation on the content. A typo in a key name (e.g., `bullish_score` vs `bullish`) would pass schema validation silently and cause KeyError failures downstream in the MCP server or ingest pipeline. Given that `mypy` is configured with `strict = true`, mypy will also flag `dict` as `dict[Any, Any]`.

**Fix:** Define typed sub-models:
```python
class SentimentBlock(BaseModel):
    bullish_score: float | None = None    # 0.0–1.0
    label: str | None = None              # bullish | bearish | neutral

class NumericFact(BaseModel):
    key: str
    value: float
    unit: str | None = None

class DerivedBlock(BaseModel):
    tickers: list[str] = Field(default_factory=list)
    event_type: str | None = None
    catalysts: list[str] = Field(default_factory=list)
    sentiment: SentimentBlock | None = None
    numeric_facts: list[NumericFact] = Field(default_factory=list)
    summary: str | None = None
```
If the schema is intentionally open-ended at this stage, add a comment explaining why and suppress the mypy warning explicitly.

### IN-04: `migrate-to-wsl.sh` uses `read -p` which is not POSIX-compatible with `#!/usr/bin/env bash` on some systems

**File:** `scripts/migrate-to-wsl.sh:45`
**Issue:** The shebang is `#!/usr/bin/env bash` so `read -p` is valid for bash. However, the script documentation says "Usage: bash scripts/migrate-to-wsl.sh", which also implies bash. This is fine as-is, but the `wsl.exe` distro detection on line 21 pipes through `head -1 | tr -d '\r\0'` — the `\0` NUL character is not a valid `tr` delete-class on all platforms and will silently produce an empty result on some WSL distributions, causing `DISTRO` to fall back to `hostname` unexpectedly. The variable is used only in the printed Obsidian path (informational), so this does not break functionality, but the path shown to the user will be wrong.

**Fix:**
```bash
# Separate the NUL and carriage-return removal steps for compatibility
DISTRO=$(wsl.exe -l -q 2>/dev/null | head -1 | tr -d '\r' | tr -d '\000' || echo "Ubuntu")
```

---

_Reviewed: 2026-04-17T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
