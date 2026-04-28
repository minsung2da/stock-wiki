---
phase: 06-full-mcp-tool-surface
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/shared/portfolio.py
  - src/db/seed_entities.py
  - src/collectors/dart/__init__.py
  - src/collectors/kind/__init__.py
  - src/collectors/krx/__init__.py
  - src/collectors/news/__init__.py
  - tests/test_cli_default_flags.py
  - tests/test_portfolio.py
  - tests/collectors/conftest.py
  - tests/collectors/krx/test_collect_krx.py
  - tests/db/conftest.py
  - tests/db/test_seed_entities.py
  - vault/notes/portfolio.md
  - notes/private/portfolio.md
  - .gitignore
  - README.md
  - CLAUDE.md
autonomous: true
requirements: [MCP-05]
must_haves:
  truths:
    - "Portfolio.load(repo_root) reads notes/private/portfolio.md (not vault/notes/portfolio.md)"
    - "All 4 collectors (dart/kind/krx/news) call Portfolio.load(repo_root) and resolve scope without missing-file errors"
    - "Test suite green after cutover (pytest tests/test_portfolio.py + tests/collectors/ + tests/db/)"
    - "No source/test reference to vault/notes/portfolio.md remains except git history"
  artifacts:
    - path: "notes/private/portfolio.md"
      provides: "Portfolio source of truth (Phase 10 P-01)"
      contains: "holdings:"
    - path: "src/shared/portfolio.py"
      provides: "Portfolio.load(repo_root) signature"
      contains: "repo_root"
  key_links:
    - from: "src/collectors/{dart,kind,krx,news}/__init__.py"
      to: "Portfolio.load"
      via: "repo_root argument"
      pattern: "Portfolio\\.load\\(repo_root"
---

<objective>
Atomic cutover (Phase 10 P-01): change Portfolio.load signature from `vault_root` to `repo_root` so it loads `notes/private/portfolio.md` instead of `vault/notes/portfolio.md`. Updates 9 source/test sites in a single commit; partial cutover breaks all collector E2E tests.

Purpose: Phase 6 MCP-05 (`get_portfolio_state`) requires SoT to be `notes/private/portfolio.md` (gitignored, per Phase 1 D-03). REQUIREMENTS.md MCP-05 has been amended; this plan delivers the code/test/data move. All downstream Phase 6 plans assume this is complete.

Output: Portfolio.load signature changed, all callers updated, fixture data moved, gitignore confirmed, tests green.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md
@.planning/phases/06-full-mcp-tool-surface/06-RESEARCH.md
@src/shared/portfolio.py
@templates/portfolio.md

<interfaces>
Current signature (src/shared/portfolio.py:66-83):
```python
@classmethod
def load(cls, vault_root: Path) -> Portfolio:
    p = Path(vault_root) / "notes" / "portfolio.md"
```

Target signature:
```python
@classmethod
def load(cls, repo_root: Path) -> Portfolio:
    p = Path(repo_root) / "notes" / "private" / "portfolio.md"
```

All 4 collectors (`src/collectors/{dart,kind,krx,news}/__init__.py`) currently call `Portfolio.load(vault_root)`. After cutover they MUST call `Portfolio.load(repo_root)` where `repo_root = vault_root.parent` in the existing layout.

`.gitignore:9` already contains `notes/private/`. Cutover does NOT change gitignore semantics; the file `notes/private/portfolio.md` becomes local-only. Fresh clones must seed from `templates/portfolio.md`.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Cutover source code (Portfolio.load signature + 4 collectors + seed_entities)</name>
  <read_first>
    - src/shared/portfolio.py (current signature, docstring lines 7, 25, 65-83)
    - src/db/seed_entities.py (call site line 35; docstring line 2)
    - src/collectors/dart/__init__.py (search for Portfolio.load)
    - src/collectors/kind/__init__.py (call site line 85)
    - src/collectors/krx/__init__.py (call site line 65)
    - src/collectors/news/__init__.py (call site line 61)
    - .planning/phases/06-full-mcp-tool-surface/06-RESEARCH.md §"Runtime State Inventory" (full cutover surface table)
    - .planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md P-01
  </read_first>
  <action>
    Atomic edits in src/:

    1. **src/shared/portfolio.py** — Rename parameter `vault_root` → `repo_root` in `Portfolio.load`. Change body line 73 from `Path(vault_root) / "notes" / "portfolio.md"` to `Path(repo_root) / "notes" / "private" / "portfolio.md"`. Update docstring line 7 from `vault file ``vault/notes/portfolio.md``` to `repo-relative file ``notes/private/portfolio.md``` and update line 25 exception docstring identically. Update Python docstring on `load()` line 67 to read `Load and validate portfolio.md from `<repo_root>/notes/private/portfolio.md``.

    2. **src/db/seed_entities.py** — At line 35, change `Portfolio.load(vault_root)` to `Portfolio.load(repo_root)`. The local variable that previously held `vault_root` should be renamed to `repo_root` (= the project root, parent of `vault/`). Identify how the script obtains its root path today and ensure it now resolves to the project root (e.g., `Path(__file__).resolve().parents[2]` if currently parents[1]; verify by reading file). Update docstring line 2 to reference `notes/private/portfolio.md`.

    3. **src/collectors/{dart,kind,krx,news}/__init__.py** — In each file, locate the `Portfolio.load(vault_root)` call. Replace with `Portfolio.load(repo_root)` where `repo_root` is derived from existing `vault_root` via `vault_root.parent` (since current layout has `vault/` directly under repo). Add a comment `# repo_root = vault_root.parent (Phase 6 P-01: portfolio moved to notes/private/)` next to the derivation. Do NOT change any other behavior.

    4. Verify NO file in `src/` still contains the literal string `vault/notes/portfolio.md` (use ripgrep). The only remaining references should be in git history.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run pytest tests/test_portfolio.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -rn "vault_root" src/shared/portfolio.py src/collectors/ src/db/seed_entities.py` returns ONLY references where `vault_root` is used as an intermediate variable to derive `repo_root` (no `Portfolio.load(vault_root)` calls remain).
    - `grep -rn "Portfolio.load(repo_root)" src/` returns ≥5 hits (4 collectors + seed_entities).
    - `grep -n "notes/private/portfolio.md" src/shared/portfolio.py` returns ≥1 hit (in load() body).
    - `grep -rn "vault/notes/portfolio.md" src/` returns 0 hits.
    - `uv run python -c "from src.shared.portfolio import Portfolio; import inspect; sig=inspect.signature(Portfolio.load); assert 'repo_root' in sig.parameters, sig"` exits 0.
  </acceptance_criteria>
  <done>Portfolio.load signature uses repo_root; all 4 collectors + seed_entities updated; no source file references the old path string.</done>
</task>

<task type="auto">
  <name>Task 2: Cutover test fixtures + data file move + docs</name>
  <read_first>
    - tests/test_portfolio.py (lines 19, 24, 31, 40, 45, 55)
    - tests/test_cli_default_flags.py (line 19)
    - tests/collectors/conftest.py (line 39)
    - tests/collectors/krx/test_collect_krx.py (line 170)
    - tests/db/conftest.py (line 35)
    - tests/db/test_seed_entities.py (line 31)
    - vault/notes/portfolio.md (existing data — preserve content)
    - templates/portfolio.md (template lines 12-13 already reference correct path)
    - .gitignore (line 9 already has notes/private/)
    - README.md (lines 32, 98, 156, 266)
    - CLAUDE.md (line 126 first-time setup step)
  </read_first>
  <action>
    1. **Test fixture path moves** — In each of:
       - tests/test_portfolio.py
       - tests/test_cli_default_flags.py
       - tests/collectors/conftest.py
       - tests/collectors/krx/test_collect_krx.py
       - tests/db/conftest.py
       - tests/db/test_seed_entities.py

       Replace fixture creation paths from `tmp_path/"vault"/"notes"/"portfolio.md"` (or `tmp_path/"notes"/"portfolio.md"`) to `tmp_path/"notes"/"private"/"portfolio.md"`. Use `mkdir(parents=True, exist_ok=True)` on the parent directory before write. Update any `Portfolio.load(tmp_path / "vault")` or `Portfolio.load(vault_root)` calls to `Portfolio.load(tmp_path)` (since tmp_path now serves as repo_root with `notes/private/` underneath).

    2. **Data file move** — Use `git mv vault/notes/portfolio.md notes/private/portfolio.md` to relocate the actual portfolio data. (`notes/private/` is gitignored, so the moved file becomes local-only — this is correct per Phase 1 D-03/D-05.) After git mv, the file content stays intact; only path changes. Verify the move with `git status` showing the rename.

       NOTE: Because `notes/private/` is gitignored, the `git mv` will untrack the destination. That is the intended outcome (private portfolio data must not be committed). Document this in the commit message: "P-01: portfolio.md moved to notes/private/ (gitignored — local-only per Phase 1 D-03)."

    3. **gitignore verification** — Confirm `.gitignore` line containing `notes/private/` is present. No edit needed unless missing.

    4. **Docs updates** — In README.md and CLAUDE.md, replace any reference to `vault/notes/portfolio.md` with `notes/private/portfolio.md`. Specific lines per RESEARCH cutover surface table: README.md:32, 98, 156, 266; CLAUDE.md:126. Use grep to ensure no stale references remain in either file.

    5. **Re-run entity seed** (advisory, executable) — After move, run `uv run python -m src.db.seed_entities` to refresh entity rows from the new path. If DB is not available locally, skip; tests will exercise the path independently.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run pytest tests/test_portfolio.py tests/test_cli_default_flags.py tests/collectors/ tests/db/test_seed_entities.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -rn "vault/notes/portfolio.md" tests/ README.md CLAUDE.md` returns 0 hits.
    - `grep -rn "notes/private/portfolio.md" tests/ README.md CLAUDE.md` returns ≥6 hits (≥4 test files + README + CLAUDE).
    - `test -f notes/private/portfolio.md` succeeds (data file present locally).
    - `git ls-files notes/private/portfolio.md` returns empty (file is gitignored, untracked — intended).
    - `git ls-files vault/notes/portfolio.md` returns empty after `git mv` (file removed from tracking).
    - The full test command (verify block) exits 0.
  </acceptance_criteria>
  <done>All test fixtures use notes/private/portfolio.md path; data file moved with git mv; docs updated; full test slice green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| repo FS → collector code | Portfolio loader reads vault file; integrity assumed (no LLM-author surface) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-6-01-01 | Tampering | Portfolio.load | accept | Loader is internal; YAML parsed via yaml.safe_load (existing); Pydantic extra='forbid' enforced (existing) |
| T-6-01-02 | Information Disclosure | private portfolio data leakage | mitigate | `notes/private/` is gitignored (.gitignore:9); cutover preserves this. Acceptance criterion explicitly checks `git ls-files` returns empty for new path. |
</threat_model>

<verification>
- All 4 collectors load portfolio without raising (`uv run pytest tests/collectors/ -x`).
- `Portfolio.load(repo_root)` returns valid Portfolio object with non-empty holdings/watchlist when notes/private/portfolio.md exists.
- No git-tracked file references the old path.
</verification>

<success_criteria>
- Test slice in Task 2 verify block exits 0.
- `grep -rn "vault/notes/portfolio.md"` returns 0 hits across src/ + tests/ + README.md + CLAUDE.md.
- `git status` shows portfolio.md as renamed (or new untracked at notes/private/, with vault/notes/portfolio.md deleted from tracking).
</success_criteria>

<output>
After completion, create `.planning/phases/06-full-mcp-tool-surface/06-01-SUMMARY.md` documenting:
- Files modified (count)
- Test slice green
- Confirmation that downstream Phase 6 plans (02..09) may now assume `notes/private/portfolio.md` is the canonical path.
</output>
