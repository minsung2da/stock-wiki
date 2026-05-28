# Phase 1: Load-Bearing Foundation - Research

**Researched:** 2026-04-17
**Domain:** Project scaffolding — Docker/Postgres, vault structure, Python env isolation, Pydantic frontmatter schema, secret hygiene, CI guards
**Confidence:** HIGH

## Summary

Phase 1 locks in every decision that becomes irrevocable once data is written: database engine, vault directory layout, frontmatter zone structure, Python environment isolation (with anthropic-ban enforcement), and secret management. The phase produces no data — only the scaffolding that subsequent phases build on.

The key technical challenges are: (1) getting the `tensorchord/vchord-suite:pg17-latest` Docker image running with pgvector + VectorChord-BM25 + pg_trgm extensions, (2) structuring `uv` projects so the ingest venv provably excludes `anthropic`/`openai`, (3) defining Pydantic v2 models for the 3-zone frontmatter that round-trip through YAML cleanly, (4) setting up pre-commit hooks for secret detection and CI import guards, and (5) providing a WSL migration script.

**Primary recommendation:** Use `tensorchord/vchord-suite:pg17-latest` as the Docker image (it bundles pgvector + VectorChord-BM25 + pg_tokenizer), use a single `pyproject.toml` with dependency groups (not uv workspaces) for simpler management while still achieving anthropic isolation through a dedicated ingest group, use `python-frontmatter` + `pyyaml` + `pydantic` v2 for frontmatter handling, and use `gitleaks` via pre-commit framework for secret detection.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Code in `src/` subdirectories (`src/collectors/`, `src/ingest/`, `src/stock_mcp/`, `src/db/`, `src/orchestration/`). Vault data directories (`raw/`, `notes/`, `ingested/`, `dashboards/`, `graph/`) at repo root.
- **D-02:** Obsidian vault root = repo root. `.obsidian/`, `환영합니다!.md` preserved. `src/` excluded from Obsidian search.
- **D-03:** Private portfolio data at `notes/private/` path, gitignored (local-only).
- **D-04:** Template at `templates/portfolio.md` for initial setup.
- **D-05:** `stock-mcp`'s `get_portfolio_state()` reads `notes/private/portfolio.md`.
- **D-06:** Hard migrate vault from `/mnt/c/Users/minsu/workspace/stock/` to `~/stock/` at Phase 1 start.
- **D-07:** Obsidian reconnects via `\\wsl$\Ubuntu\home\yamin\stock` (or distro path).
- **D-08:** Migration script at `scripts/migrate-to-wsl.sh`.
- **D-09:** Frontmatter 3 zones as nested YAML dicts: `provenance:`, `ingest_state:`, `_derived:`.
- **D-10:** Pydantic models map 1:1: `FrontMatter(provenance: ProvenanceBlock, ingest_state: IngestStateBlock, derived: DerivedBlock)`.
- **D-11:** Dataview queries use `WHERE provenance.source = "dart"` style.

### Claude's Discretion
- pyproject.toml structure (single + dependency groups vs uv workspaces)
- Docker image selection (tensorchord/vchord vs custom Dockerfile)
- Pre-commit hook framework selection (gitleaks vs detect-secrets)
- CI platform selection (GitHub Actions vs pre-commit only)
- Test framework and fixture setup

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FOUND-01 | Postgres 17 container with pgvector + VectorChord-BM25 + pg_trgm | Docker image research: `tensorchord/vchord-suite:pg17-latest` bundles all three; `docker-compose.yml` pattern documented |
| FOUND-02 | Vault directories `raw/`, `notes/`, `ingested/`, `dashboards/`, `graph/` preserving `.obsidian/` and `환영합니다!.md` | Vault layout pattern from ARCHITECTURE.md; `.keep` files for empty dirs |
| FOUND-03 | `.gitignore` excludes workspace churn, caches, portfolio overlays | Comprehensive gitignore pattern from STACK.md + PITFALLS.md (Pitfall 25, 26) |
| FOUND-04 | WSL migration option documented as script | Migration script pattern researched; distro auto-detection via `wsl.exe -l -q` |
| FOUND-05 | `uv`-managed Python 3.12 venvs with anthropic exclusion in ingest | Dependency group strategy researched; single pyproject.toml with groups + CI grep guard |
| FOUND-06 | Pydantic frontmatter schema with unit tests | Pydantic v2 2.13.1 + python-frontmatter 1.1.0 + pyyaml 6.0.3 verified; round-trip pattern documented |
| COLL-07 | CI fails if `ingest/` or `collectors/` imports `anthropic`/`openai` | grep-based CI test + ruff custom rule pattern documented |
| OPS-06 | Secrets loaded from `.env` only; pre-commit blocks committed secrets | gitleaks pre-commit hook pattern; `.env.example` template |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.13.1 | Frontmatter schema validation | Industry standard; Rust core = fast; v2 model_dump/model_validate for YAML round-trip [VERIFIED: pip index] |
| python-frontmatter | 1.1.0 | Parse/write YAML frontmatter in Markdown files | De-facto standard for Python frontmatter handling [VERIFIED: pip index] |
| pyyaml | 6.0.3 | YAML serialization/deserialization | Required by python-frontmatter; explicit version pin avoids C-extension issues [VERIFIED: pip index] |
| pytest | 9.0.3 | Test framework | Standard Python testing [VERIFIED: pip index] |
| ruff | 0.15.11 | Linter + formatter | Replaces flake8+black+isort; fast (Rust) [VERIFIED: pip index] |
| uv | 0.11.7 | Python env manager | Already installed; fast, modern [VERIFIED: command -v] |
| Docker | 29.3.0 | Container runtime for Postgres | Already installed [VERIFIED: docker --version] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dotenv | latest | Load `.env` files | Secret loading pattern for all src/ modules |
| gitleaks | latest | Pre-commit secret scanner | Blocks committed API keys, passwords [VERIFIED: GitHub search] |
| pre-commit | latest | Git hook framework | Manages gitleaks + ruff hooks declaratively |

### Docker Image

| Image | Tag | Contents | Why |
|-------|-----|----------|-----|
| `tensorchord/vchord-suite` | `pg17-latest` | Postgres 17 + pgvector + VectorChord + VectorChord-BM25 + pg_tokenizer.rs | All-in-one; no custom Dockerfile needed [VERIFIED: Docker Hub + VectorChord docs] |

**Installation:**
```bash
# Python deps (Phase 1 only — dev/test/schema)
uv pip install pydantic pyyaml python-frontmatter python-dotenv pytest ruff

# Pre-commit
uv pip install pre-commit
pre-commit install

# Docker
docker compose up -d
```

## Architecture Patterns

### Recommended Project Structure (Phase 1 output)

```
~/stock/                          # repo root = Obsidian vault root
├── .obsidian/                    # preserved
├── 환영합니다!.md                 # preserved
├── raw/                          # collector output (future phases)
├── notes/                        # human + Claude notes
│   └── private/                  # gitignored — personal portfolio
├── ingested/                     # post-enrichment views (future)
├── dashboards/                   # auto-generated (future)
├── graph/                        # graphify output (future)
├── templates/                    # frontmatter templates
│   └── portfolio.md              # portfolio template
├── src/
│   ├── collectors/               # data collection scripts
│   │   └── __init__.py
│   ├── ingest/                   # ingestion pipeline
│   │   └── __init__.py
│   ├── stock_mcp/                # MCP server
│   │   └── __init__.py
│   ├── db/                       # database layer
│   │   └── __init__.py
│   ├── orchestration/            # scheduling/coordination
│   │   └── __init__.py
│   └── shared/                   # shared models (frontmatter schema)
│       ├── __init__.py
│       └── frontmatter.py        # Pydantic models
├── tests/
│   ├── conftest.py
│   ├── test_frontmatter.py       # YAML round-trip tests
│   └── test_import_guard.py      # anthropic/openai import ban
├── scripts/
│   └── migrate-to-wsl.sh         # WSL migration script
├── docker-compose.yml
├── pyproject.toml                # single file, dependency groups
├── .pre-commit-config.yaml
├── .env.example                  # template for secrets
├── .env                          # gitignored — actual secrets
├── .gitignore
└── .obsidianignore               # excludes src/, data/pg/ from Obsidian
```

### Pattern 1: Single pyproject.toml with Dependency Groups

**What:** One `pyproject.toml` at repo root with dependency groups instead of uv workspaces.
**When to use:** When the goal is anthropic-isolation-by-group, not full workspace separation.
**Why not uv workspaces:** uv workspaces share a single lockfile but create separate venvs per member. This adds complexity (multiple pyright configs, multiple test runs) for minimal benefit. The `anthropic` ban can be enforced more simply with a CI grep test + dependency groups where the `ingest` group explicitly excludes cloud SDKs.

```toml
# pyproject.toml
[project]
name = "stock-wiki"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.13,<3",
    "pyyaml>=6.0",
    "python-frontmatter>=1.1",
    "python-dotenv>=1.0",
]

[dependency-groups]
collectors = [
    "dart-fss",
    "pykrx>=1.0.50",
    "finance-datareader>=0.9.94",
    "trafilatura>=1.12",
    "PublicDataReader",
    "fredapi>=0.5",
    "yfinance>=0.2.50",
    "beautifulsoup4>=4.12",
    "requests>=2.32",
    "pandas",
    "lxml",
]
ingest = [
    # NOTE: anthropic and openai are INTENTIONALLY ABSENT
    "ollama",
    "psycopg[binary]",
    "pgvector",
    "sqlalchemy>=2.0",
    "python-mecab-ko",
]
mcp = [
    "fastmcp>=2.11,<3.0",
    "anthropic",  # only here — MCP server may call Haiku as fallback
    "psycopg[binary]",
    "pgvector",
    "sqlalchemy>=2.0",
]
dev = [
    "pytest>=9.0",
    "ruff>=0.15",
    "pre-commit",
    "mypy",
]
```

**Key insight:** The `ingest` group has NO `anthropic` or `openai`. The `mcp` group CAN have `anthropic` because the MCP server runs in a separate process with budget caps. CI grep-test catches any `import anthropic` in `src/ingest/` or `src/collectors/` regardless.

### Pattern 2: Frontmatter 3-Zone Pydantic Models

**What:** Nested Pydantic v2 models mapping 1:1 to the YAML frontmatter zones.
**Source:** User decision D-09/D-10.

```python
# src/shared/frontmatter.py
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class ProvenanceBlock(BaseModel):
    """Zone 1: Written by collectors. Never overwritten by ingest."""
    source: str                          # dart|naver|news|macro|krx|note
    source_id: Optional[str] = None      # rcept_no, url hash, etc.
    source_url: Optional[str] = None
    date: Optional[str] = None           # publication date
    fetched_at: Optional[datetime] = None
    content_hash: Optional[str] = None
    corp_code: Optional[str] = None      # DART 8-digit
    ticker: Optional[str] = None         # KRX 6-digit (convenience)
    lang: str = "ko"

class IngestStateBlock(BaseModel):
    """Zone 2: Written by ingest pipeline. Tracks processing state."""
    processed: bool = False
    processed_at: Optional[datetime] = None
    embedding_model: Optional[str] = None
    ingest_model: Optional[str] = None
    ingest_version: Optional[int] = None

class DerivedBlock(BaseModel):
    """Zone 3: LLM-extracted attributes. Regenerable; do not hand-edit."""
    tickers: list[str] = Field(default_factory=list)
    event_type: Optional[str] = None
    catalysts: list[str] = Field(default_factory=list)
    sentiment: Optional[dict] = None      # {score, label, rationale}
    numeric_facts: list[dict] = Field(default_factory=list)
    summary: Optional[str] = None

class FrontMatter(BaseModel):
    """Top-level frontmatter container. Maps to YAML 1:1."""
    provenance: ProvenanceBlock
    ingest_state: IngestStateBlock = Field(default_factory=IngestStateBlock)
    _derived: DerivedBlock = Field(default_factory=DerivedBlock, alias="derived")

    model_config = {"populate_by_name": True}
```

### Pattern 3: YAML Round-Trip with python-frontmatter

```python
import frontmatter
import yaml
from shared.frontmatter import FrontMatter

def read_frontmatter(path: str) -> FrontMatter:
    """Read a markdown file and parse its frontmatter into a Pydantic model."""
    post = frontmatter.load(path)
    return FrontMatter.model_validate(dict(post.metadata))

def write_frontmatter(path: str, fm: FrontMatter, body: str) -> None:
    """Write a markdown file with validated frontmatter."""
    post = frontmatter.Post(body)
    post.metadata = fm.model_dump(by_alias=True, exclude_none=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
```

### Pattern 4: docker-compose.yml for Postgres

```yaml
# docker-compose.yml
services:
  postgres:
    image: tensorchord/vchord-suite:pg17-latest
    environment:
      POSTGRES_DB: stockwiki
      POSTGRES_USER: stockwiki
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-stockwiki_dev}
    volumes:
      - ./data/pg:/var/lib/postgresql/data
      - ./scripts/init-extensions.sql:/docker-entrypoint-initdb.d/init-extensions.sql
    ports:
      - "127.0.0.1:5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U stockwiki"]
      interval: 5s
      timeout: 5s
      retries: 5
```

```sql
-- scripts/init-extensions.sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS vchord_bm25;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

### Pattern 5: CI Import Guard

```python
# tests/test_import_guard.py
"""CI test: ingest/ and collectors/ must not import anthropic or openai."""
import ast
import pathlib

BANNED_MODULES = {"anthropic", "openai"}
GUARDED_DIRS = ["src/ingest", "src/collectors"]

def test_no_cloud_llm_imports():
    violations = []
    for dir_path in GUARDED_DIRS:
        for py_file in pathlib.Path(dir_path).rglob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in BANNED_MODULES:
                            violations.append(f"{py_file}:{node.lineno} imports {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.split(".")[0] in BANNED_MODULES:
                        violations.append(f"{py_file}:{node.lineno} imports from {node.module}")
    assert not violations, f"Cloud LLM imports found:\n" + "\n".join(violations)
```

### Anti-Patterns to Avoid

- **Flat frontmatter:** Mixing provenance, ingest state, and derived fields at the top level. This makes it impossible to know which fields are safe to regenerate on reingest. Use the 3-zone nested structure.
- **uv workspaces for isolation:** Over-engineers the anthropic ban. A CI grep test is simpler and more reliable than separate lockfiles.
- **Custom Dockerfile for Postgres:** The `tensorchord/vchord-suite` image already bundles everything needed. Building a custom image adds maintenance burden.
- **Hardcoded DB credentials:** Use `.env` + `python-dotenv` from day one. Never embed passwords in `docker-compose.yml` (use variable substitution).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML frontmatter parsing | Custom regex/string splitting | `python-frontmatter` 1.1.0 | Handles edge cases (multi-line values, escaping, encoding) |
| Schema validation | Manual dict checks | Pydantic v2 BaseModel | Type coercion, error messages, serialization built-in |
| Secret detection | Custom grep scripts | `gitleaks` via pre-commit | 800+ built-in patterns, low false-positive rate, Go speed |
| Python linting + formatting | flake8 + black + isort | `ruff` | Single tool, 10-100x faster, drop-in replacement |
| Docker Postgres + extensions | Custom Dockerfile with apt-get | `tensorchord/vchord-suite:pg17-latest` | Pre-built, tested, maintained by extension authors |

**Key insight:** Phase 1 is scaffolding. Every component should be a standard, well-maintained tool. No custom code for infrastructure problems.

## Common Pitfalls

### Pitfall 1: Frontmatter Zone Cross-Contamination
**What goes wrong:** Collector writes a field that belongs to the `_derived` zone, or ingest overwrites a `provenance` field.
**Why it happens:** Without zone enforcement, any code can write any frontmatter field.
**How to avoid:** Each zone maps to a Pydantic model. Collectors instantiate only `ProvenanceBlock`; ingest writes only `IngestStateBlock`; LLM extraction writes only `DerivedBlock`. The `write_frontmatter()` function takes a zone parameter and merges only that zone, preserving others. Unit test: write all three zones independently, verify no cross-contamination.
**Warning signs:** A `_derived` field appearing in a file that hasn't been through ingest yet.

### Pitfall 2: python-frontmatter Drops or Reorders YAML Keys
**What goes wrong:** YAML round-trip through `python-frontmatter` reorders keys alphabetically or drops keys with `None` values, causing noisy git diffs.
**Why it happens:** `python-frontmatter` uses `pyyaml` default dumper which sorts keys and drops None.
**How to avoid:** Use `pydantic`'s `model_dump(exclude_none=True)` before writing (intentional None-dropping). For key ordering, accept alphabetical sort — it is deterministic and avoids noisy diffs from insertion-order variation. Test this in the round-trip fixture.
**Warning signs:** Every ingest run generates git diffs on files that didn't actually change.

### Pitfall 3: WSL /mnt/c Performance Degradation
**What goes wrong:** Running the project from `/mnt/c/...` causes 5-10x slower file I/O due to Windows filesystem translation layer (9p/DrvFs). Docker volume mounts from `/mnt/c/` are even worse.
**Why it happens:** WSL2 uses a Plan 9 filesystem bridge to access Windows files; native ext4 is dramatically faster.
**How to avoid:** D-06 addresses this: hard-migrate to `~/stock/`. The migration script must handle: (a) copying all files preserving permissions, (b) re-initializing git remote, (c) printing Obsidian reconnection instructions for `\\wsl$\` path.
**Warning signs:** `docker compose up` takes >30s; file-heavy operations (git status, pytest discovery) noticeably slower than expected.

### Pitfall 4: Docker Volume Permissions on WSL
**What goes wrong:** Postgres data directory (`./data/pg/`) created with wrong ownership when Docker runs as root but the WSL user is non-root. Postgres refuses to start: "data directory has wrong ownership."
**Why it happens:** Docker Desktop for Windows + WSL2 has known permission mapping issues between the Linux and Windows filesystems.
**How to avoid:** (a) Use a named Docker volume instead of a bind mount for the Postgres data directory (simpler, avoids permission issues). (b) If bind mount is required (for backup visibility), set `user: "1000:1000"` in docker-compose.yml matching the WSL user UID.
**Warning signs:** `docker compose up` exits with permission errors on the data directory.

### Pitfall 5: `.env` Accidentally Committed
**What goes wrong:** Developer creates `.env` with real API keys, runs `git add .`, keys are in history forever.
**Why it happens:** `.gitignore` added after the first commit; or a rename (`.env.local` not in gitignore).
**How to avoid:** (a) `.gitignore` must exist BEFORE the first `.env` file. (b) Pre-commit hook via `gitleaks` catches key patterns. (c) Provide `.env.example` with placeholder values so developers know what to set. (d) Document in README: "copy .env.example to .env, fill in your keys."
**Warning signs:** `gitleaks` pre-commit hook fires; `git log -p -- .env` shows any content.

## Code Examples

### YAML Round-Trip Test Fixture

```python
# tests/test_frontmatter.py
import tempfile
from pathlib import Path
from shared.frontmatter import FrontMatter, ProvenanceBlock, IngestStateBlock, DerivedBlock

FIXTURE_YAML = """\
---
provenance:
  source: dart
  source_id: "20260416000523"
  content_hash: "sha256:abc123"
  corp_code: "00126380"
  ticker: "005930"
  lang: ko
ingest_state:
  processed: false
_derived:
  tickers: []
  catalysts: []
---
Test document body.
"""

def test_frontmatter_round_trip():
    """FrontMatter model round-trips through YAML without data loss."""
    import frontmatter as fm

    # Parse
    post = fm.loads(FIXTURE_YAML)
    model = FrontMatter.model_validate(dict(post.metadata))

    # Verify fields
    assert model.provenance.source == "dart"
    assert model.provenance.corp_code == "00126380"
    assert model.ingest_state.processed is False

    # Round-trip: dump back to YAML, re-parse
    dumped = model.model_dump(by_alias=True, exclude_none=True)
    post2 = fm.Post("Test document body.")
    post2.metadata = dumped

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(fm.dumps(post2))
        tmp_path = f.name

    post3 = fm.load(tmp_path)
    model2 = FrontMatter.model_validate(dict(post3.metadata))

    assert model2.provenance.source == model.provenance.source
    assert model2.provenance.corp_code == model.provenance.corp_code
    assert model2.ingest_state.processed == model.ingest_state.processed
    Path(tmp_path).unlink()


def test_zone_isolation():
    """Each zone can be updated independently without affecting others."""
    import frontmatter as fm

    post = fm.loads(FIXTURE_YAML)
    model = FrontMatter.model_validate(dict(post.metadata))

    # Update only ingest_state
    updated = model.model_copy(update={
        "ingest_state": IngestStateBlock(processed=True, embedding_model="bge-m3")
    })

    # Provenance unchanged
    assert updated.provenance.source == "dart"
    assert updated.provenance.corp_code == "00126380"

    # Ingest state updated
    assert updated.ingest_state.processed is True
    assert updated.ingest_state.embedding_model == "bge-m3"
```

### Pre-commit Configuration

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.24.0  # check for latest
    hooks:
      - id: gitleaks

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.11
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

### WSL Migration Script Skeleton

```bash
#!/usr/bin/env bash
# scripts/migrate-to-wsl.sh
# Migrates vault from /mnt/c/.../stock to ~/stock (WSL-native filesystem)

set -euo pipefail

SRC="/mnt/c/Users/minsu/workspace/stock"
DST="$HOME/stock"
DISTRO=$(wsl.exe -l -q 2>/dev/null | head -1 | tr -d '\r\0' || hostname)

if [ -d "$DST" ]; then
  echo "ERROR: $DST already exists. Aborting."
  exit 1
fi

echo "Copying $SRC -> $DST ..."
cp -a "$SRC" "$DST"

echo "Done. Next steps:"
echo "1. cd $DST && git remote -v  (verify remotes)"
echo "2. In Obsidian (Windows): Open vault at:"
echo "   \\\\wsl\$\\${DISTRO}\\home\\$(whoami)\\stock"
echo "3. Verify .obsidian/ settings are intact"
echo "4. Remove old location when confirmed: rm -rf $SRC"
```

### .env.example Template

```bash
# .env.example — copy to .env and fill in real values
# NEVER commit .env to git

# DART API (from opendart.fss.or.kr)
OPEN_DART_API_KEY=your_40_hex_char_key_here

# Database
POSTGRES_PASSWORD=stockwiki_dev
DATABASE_URL=postgresql://stockwiki:stockwiki_dev@127.0.0.1:5432/stockwiki

# FRED API (from fred.stlouisfed.org)
FRED_API_KEY=your_fred_api_key_here

# ECOS API (from ecos.bok.or.kr)
ECOS_API_KEY=your_ecos_api_key_here

# Cloud LLM fallback (only for MCP server, NEVER for ingest)
# ANTHROPIC_API_KEY=sk-ant-...  # uncomment only if using Haiku fallback
# ALLOW_CLOUD_LLM=0
# MAX_CLOUD_USD=0.50
```

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v --tb=short` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FOUND-01 | Postgres 17 with extensions loads | integration | `docker compose up -d && docker exec stock-postgres psql -U stockwiki -c "SELECT extname FROM pg_extension;"` | Wave 0 |
| FOUND-02 | Vault dirs exist, .obsidian preserved | smoke | `uv run pytest tests/test_vault_layout.py -x` | Wave 0 |
| FOUND-03 | .gitignore excludes correct patterns | unit | `uv run pytest tests/test_gitignore.py -x` | Wave 0 |
| FOUND-04 | WSL migration script exists and is executable | smoke | `bash -n scripts/migrate-to-wsl.sh` | Wave 0 |
| FOUND-05 | ingest venv has no anthropic | unit | `uv run pytest tests/test_import_guard.py -x` | Wave 0 |
| FOUND-06 | Pydantic models round-trip YAML | unit | `uv run pytest tests/test_frontmatter.py -x` | Wave 0 |
| COLL-07 | CI import guard catches anthropic/openai | unit | `uv run pytest tests/test_import_guard.py -x` | Wave 0 |
| OPS-06 | .env loading works; secrets not in git | unit + hook | `uv run pytest tests/test_secrets.py -x && pre-commit run gitleaks --all-files` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v --tb=short`
- **Phase gate:** Full suite green + `docker compose up -d` succeeds + `pre-commit run --all-files` clean

### Wave 0 Gaps
- [ ] `tests/test_frontmatter.py` -- covers FOUND-06 (Pydantic round-trip)
- [ ] `tests/test_import_guard.py` -- covers FOUND-05, COLL-07 (anthropic ban)
- [ ] `tests/test_vault_layout.py` -- covers FOUND-02 (directory structure)
- [ ] `tests/test_secrets.py` -- covers OPS-06 (.env loading)
- [ ] `tests/conftest.py` -- shared fixtures (tmp vault dir, sample frontmatter)
- [ ] `pyproject.toml` -- pytest configuration section
- [ ] Framework install: `uv pip install pytest` -- not yet installed

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | n/a (local tool, no auth) |
| V3 Session Management | no | n/a |
| V4 Access Control | yes (partial) | Frontmatter zone write-permissions enforced by Pydantic models |
| V5 Input Validation | yes | Pydantic v2 for all frontmatter; `.env` key validation on startup |
| V6 Cryptography | no | n/a (no encryption in Phase 1) |

### Known Threat Patterns for This Phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API keys committed to git | Information Disclosure | gitleaks pre-commit + `.gitignore` + `.env.example` pattern |
| Cloud LLM cost blow-up via ingest | Elevation of Privilege (cost) | CI grep guard + dependency group exclusion |
| Portfolio data exposure via git | Information Disclosure | `notes/private/` gitignored + pre-commit scan for account patterns |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | FOUND-01 (Postgres container) | YES | 29.3.0 | -- |
| Docker Compose | FOUND-01 | YES | v5.1.0 | -- |
| uv | FOUND-05 (Python env) | YES | 0.11.7 | -- |
| Python 3.12 | FOUND-05 | YES | 3.12.3 | -- |
| git | Version control | YES | 2.43.0 | -- |
| Ollama | NOT Phase 1 | NO | -- | Not needed in Phase 1 |
| psql | DB inspection (optional) | NO | -- | Use `docker exec` to run psql inside container |

**Missing dependencies with no fallback:** None -- all Phase 1 dependencies are available.

**Missing dependencies with fallback:**
- `psql` CLI not installed locally -- use `docker exec stock-postgres psql -U stockwiki` instead.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Separate Dockerfile for pgvector+BM25 | `tensorchord/vchord-suite:pg17-latest` all-in-one | 2025-2026 | No custom image maintenance; pgvector + VectorChord-BM25 + pg_tokenizer bundled |
| Pydantic v1 `parse_obj()` | Pydantic v2 `model_validate()` + `model_dump()` | 2023 | 5-50x faster; Rust core; `model_config` replaces `Config` class |
| flake8 + black + isort | ruff (single tool) | 2023-2024 | 10-100x faster; single config |
| detect-secrets (Yelp) | gitleaks | 2024-2026 | Go binary = faster; 800+ built-in patterns; lower false-positive rate |
| Manual `pip install` | `uv` with dependency groups | 2024-2026 | 10-100x faster; deterministic lockfile |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `tensorchord/vchord-suite:pg17-latest` includes `pg_trgm` extension | Docker Image | If pg_trgm is missing, add `CREATE EXTENSION pg_trgm` to init script or switch to `pgvector/pgvector:pg17` base + manual VectorChord install |
| A2 | `python-frontmatter` 1.1.0 handles nested YAML dicts (not just flat key-value) correctly | Pattern 3 | If nested dicts flatten or fail, need custom YAML handler; test in Wave 0 |
| A3 | Pydantic v2 `model_dump(by_alias=True)` correctly emits `_derived` key with underscore prefix | Pattern 2 | If alias handling breaks, the `_derived` zone won't serialize correctly; test in Wave 0 |
| A4 | Named Docker volumes avoid WSL2 permission issues for Postgres data | Pitfall 4 | If permissions still break, need explicit UID mapping in docker-compose |
| A5 | gitleaks `v8.24.0` is the current stable release tag for pre-commit | Pre-commit Config | If tag doesn't exist, check `gitleaks` releases page for latest |

## Open Questions

1. **pg_trgm in vchord-suite image**
   - What we know: vchord-suite bundles pgvector + VectorChord + VectorChord-BM25 + pg_tokenizer.rs
   - What's unclear: Whether `pg_trgm` (a contrib extension) is included in the image
   - Recommendation: Test at docker-compose-up time. If missing, `pg_trgm` is in standard Postgres contrib and should be available; just `CREATE EXTENSION` it. Worst case, it's a non-blocker for Phase 1 (pg_trgm is used for fuzzy matching, not critical until search layer).

2. **Pydantic `_derived` alias behavior**
   - What we know: Pydantic v2 supports `Field(alias="derived")` with `populate_by_name=True`
   - What's unclear: Whether the underscore-prefixed `_derived` key survives YAML round-trip correctly (YAML doesn't treat `_` specially, but python-frontmatter might)
   - Recommendation: Validate in Wave 0 test fixture. If problematic, rename to `derived` (drop underscore) -- the naming convention is informational, not technical.

3. **Bind mount vs named volume for Postgres data**
   - What we know: Bind mounts (`./data/pg:/var/lib/...`) have permission issues on WSL2
   - What's unclear: Whether the post-migration path (`~/stock/data/pg`) avoids the issue
   - Recommendation: Default to named volume (`pgdata:/var/lib/postgresql/data`) in docker-compose. Add optional bind-mount config in comments for users who want backup visibility.

## Sources

### Primary (HIGH confidence)
- [tensorchord/vchord-suite Docker Hub](https://hub.docker.com/r/tensorchord/vchord-suite) -- all-in-one image with pg17 support [VERIFIED: WebSearch]
- [VectorChord Suite docs](https://docs.vectorchord.ai/vectorchord/getting-started/vectorchord-suite.html) -- extension list [VERIFIED: WebSearch]
- [pydantic 2.13.1 on PyPI](https://pypi.org/project/pydantic/) -- latest version [VERIFIED: pip index]
- [python-frontmatter 1.1.0 on PyPI](https://pypi.org/project/python-frontmatter/) -- latest version [VERIFIED: pip index]
- [pyyaml 6.0.3 on PyPI](https://pypi.org/project/pyyaml/) -- latest version [VERIFIED: pip index]
- [pytest 9.0.3 on PyPI](https://pypi.org/project/pytest/) -- latest version [VERIFIED: pip index]
- [ruff 0.15.11 on PyPI](https://pypi.org/project/ruff/) -- latest version [VERIFIED: pip index]
- [gitleaks on GitHub](https://github.com/gitleaks/gitleaks) -- secret scanning [VERIFIED: WebSearch]
- [uv workspaces docs](https://docs.astral.sh/uv/concepts/projects/workspaces/) -- workspace vs dependency groups [VERIFIED: WebSearch]

### Secondary (MEDIUM confidence)
- [frontmatter-format on PyPI](https://pypi.org/project/frontmatter-format/) -- Pydantic+frontmatter integration reference
- [Pydantic YAML config pattern](https://trhallam.github.io/trhallam/blog/pydantic-yaml-config/) -- YAML round-trip approach
- [Docker Compose WSL2 volume permissions](https://docs.docker.com/desktop/troubleshoot-and-support/topics/) -- known issues [ASSUMED]

### Tertiary (LOW confidence)
- gitleaks pre-commit rev tag `v8.24.0` -- needs verification against actual releases [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all versions verified against PyPI/registries
- Architecture: HIGH -- follows locked user decisions (D-01 through D-11)
- Pitfalls: HIGH -- sourced from project PITFALLS.md (Pitfall 1, 2, 7, 25, 26) + WSL-specific research
- Docker image: HIGH -- tensorchord/vchord-suite confirmed available with pg17 tag
- Pydantic round-trip: MEDIUM -- pattern is standard but nested YAML + underscore alias needs empirical validation

**Research date:** 2026-04-17
**Valid until:** 2026-05-17 (stable domain; Docker image tags may update)
