---
phase: 06-full-mcp-tool-surface
plan: 06
type: execute
wave: 2
depends_on: [02, 03]
files_modified:
  - src/stock_mcp/tools/notes.py
  - tests/stock_mcp/test_add_note_paths.py
  - tests/stock_mcp/test_add_note_frontmatter.py
  - tests/stock_mcp/test_add_note_append.py
autonomous: true
requirements: [MCP-08]
must_haves:
  truths:
    - "add_note rejects all paths outside vault/notes/ ∪ notes/private/ with WRITE_FORBIDDEN"
    - "Path normalization resolves `..` and symlinks before whitelist check (no symlink escape)"
    - "Path aliases journal/today and {ticker6}/thesis resolve per D-12; auto-mkdir within whitelist; auto-.md extension"
    - "NoteFrontmatter validated; missing type → INVALID_FRONTMATTER; tickers union-merged; updated always now-KST"
    - "Append-only conflict policy: existing file gets `\\n\\n---\\n## {ISO ts KST}\\n\\n` separator + body; idempotent re-append returns idempotent=true"
    - "Atomic write via tempfile.mkstemp + os.replace (no torn writes)"
    - "4-section docstring per D-24"
  artifacts:
    - path: "src/stock_mcp/tools/notes.py"
      provides: "add_note tool"
      contains: "def add_note"
  key_links:
    - from: "src/stock_mcp/tools/notes.py"
      to: "src/stock_mcp/paths.safe_join + resolve_path_alias"
      via: "import"
      pattern: "safe_join|resolve_path_alias"
    - from: "src/stock_mcp/tools/notes.py"
      to: "src/shared/frontmatter.NoteFrontmatter"
      via: "import"
      pattern: "NoteFrontmatter"
---

<objective>
Implement `add_note(path, body, frontmatter?)` (MCP-08, D-09..D-13) — the only write surface in Phase 6 MCP. Enforces path whitelist, validates frontmatter, supports path aliases, append-only conflict policy with idempotency, atomic write.

Purpose: Lets Claude record memos, theses, journal entries during a judgment session — picked up by next ingest cycle. Write-scope rules are non-negotiable: SoT directories (raw/, ingested/, dashboards/, vault/raw/) MUST stay write-protected.

Output: 1 tool module + 3 test modules (paths, frontmatter validation, append+idempotency).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md
@.planning/phases/06-full-mcp-tool-surface/06-UI-SPEC.md
@.planning/phases/06-full-mcp-tool-surface/06-RESEARCH.md
@src/stock_mcp/tools/search.py
@src/stock_mcp/paths.py
@src/shared/frontmatter.py
@src/stock_mcp/models.py
@src/stock_mcp/errors.py

<interfaces>
Helpers from Plan 06-02:
- `src/stock_mcp/paths.py::safe_join(repo_root, user_path) -> Path` (raises WRITE_FORBIDDEN)
- `src/stock_mcp/paths.py::resolve_path_alias(user_path) -> str`
- `src/shared/frontmatter.py::NoteFrontmatter` (Pydantic, type Literal[thesis|journal|conviction|note])
- `src/stock_mcp/models.py::AddNoteResponse` (vault_path, action, idempotent)

Existing atomic write pattern (src/shared/frontmatter.py:243-261, write_frontmatter): tempfile.mkstemp + os.replace.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: add_note tool — path resolve + frontmatter validation + new-file create path</name>
  <read_first>
    - src/stock_mcp/paths.py (safe_join, resolve_path_alias)
    - src/shared/frontmatter.py (NoteFrontmatter, write_frontmatter atomic pattern lines 243-261)
    - src/stock_mcp/tools/search.py (envelope pattern)
    - src/stock_mcp/models.py (AddNoteResponse)
    - .planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md D-09, D-11, D-12
  </read_first>
  <behavior>
    - Test P1: `add_note(path="vault/notes/foo.md", body="hi", frontmatter={"type":"note"})` creates the file; response action="created", idempotent=False.
    - Test P2: `add_note(path="raw/dart/x.md", body="x", frontmatter={"type":"note"})` returns dict with `error.code="WRITE_FORBIDDEN"`.
    - Test P3: `add_note(path="../etc/passwd", body="x", frontmatter={"type":"note"})` returns WRITE_FORBIDDEN.
    - Test P4: `add_note(path="journal/today", body="hi", frontmatter={"type":"journal"})` creates `notes/private/journal/{KST today}.md`; response.vault_path equals that path.
    - Test P5: `add_note(path="005930/thesis", body="x", frontmatter={"type":"thesis"})` creates `notes/private/005930/thesis.md`; auto-mkdir of intermediate dir.
    - Test P6: Symlink under `notes/private/` pointing to `/tmp/escape` — write attempt → WRITE_FORBIDDEN (resolve catches).
    - Test F1: `add_note(path="vault/notes/x.md", body="hi", frontmatter={})` — missing type → INVALID_FRONTMATTER.
    - Test F2: `add_note(path="vault/notes/x.md", body="hi", frontmatter={"type":"note", "tickers":["005930","invalid"]})` — invalid ticker is warning, file still created.
    - Test F3: `add_note(path="vault/notes/x.md", body="hi", frontmatter=None)` — frontmatter omitted; defaults: missing type → INVALID_FRONTMATTER (since type is required).
    - Test F4: Created file has YAML frontmatter at top with `type`, `tickers`, `tags`, `created`, `updated`, `author` keys.
    - Test D1: Docstring 4 sections present.
  </behavior>
  <action>
    Create `src/stock_mcp/tools/notes.py`:

    Function signature:
    ```python
    def add_note(
        path: str,
        body: str,
        frontmatter: dict | None = None,
    ) -> AddNoteResponse | dict:
    ```

    Flow:
    1. Resolve repo_root via the same `_repo_root()` helper as Plan 06-05 (consider extracting to a shared module). Inline-duplicate is acceptable for now; refactor in Phase 7.
    2. `aliased = resolve_path_alias(path)` — converts journal/today, ticker/kind, auto .md.
    3. `target = safe_join(repo_root, aliased)` — raises WRITE_FORBIDDEN if outside whitelist (after symlink resolve).
    4. Build NoteFrontmatter:
       ```python
       fm_dict = dict(frontmatter or {})
       fm_dict.setdefault("type", None)  # forces Pydantic to fail-fast on missing
       try:
           note_fm = NoteFrontmatter(**fm_dict)
       except ValidationError as e:
           raise StructuredError(
               ErrorCode.INVALID_FRONTMATTER,
               "frontmatter validation failed",
               details={"errors": [str(err) for err in e.errors()][:5]},
           )
       # Always update 'updated' to now-KST
       note_fm = note_fm.model_copy(update={"updated": datetime.now(ZoneInfo("Asia/Seoul"))})
       ```
    5. Ticker normalization (warning, not error):
       ```python
       engine = get_engine()
       warnings = []
       normalized_tickers = []
       for t in note_fm.tickers:
           ent = resolve_entity(engine, t)
           if ent is None:
               warnings.append(f"unresolved_ticker:{t}")
           normalized_tickers.append(t)  # keep original
       note_fm = note_fm.model_copy(update={"tickers": normalized_tickers})
       ```
    6. Branch: target.exists() ?
       - **NO** (this task): create new file via atomic write. Body format:
         ```
         ---
         <yaml.safe_dump(note_fm.model_dump(mode="json"), sort_keys=False, allow_unicode=True)>---

         {body}
         ```
         Use `tempfile.mkstemp(dir=target.parent)` + write + `os.replace(temp, target)`. Auto-mkdir parent: `target.parent.mkdir(parents=True, exist_ok=True)`.
         Return `AddNoteResponse(vault_path=str(target.relative_to(repo_root)), action="created", idempotent=False)`.
       - **YES**: defer to Task 2 (append flow). For Task 1, returning a sentinel error like NotImplementedError is acceptable — but since both tasks are in the same plan, structure the code so Task 1 implements the FULL `add_note` with both paths; Task 2 adds the test and verification for the append branch + idempotency.

    Actually — since this is one plan with 2 tasks, Task 1 implements the **complete** `add_note` (both create and append branches) and Task 2 only adds the append-specific tests. This avoids dead code between tasks. Make this the structure.

    Wire mcp.tool()(add_note). Standard error envelope.

    Docstring (LLM-facing, 4 sections per D-24): describe whitelist, alias rules, append-only conflict policy, frontmatter required type field, idempotency flag, error codes WRITE_FORBIDDEN / INVALID_FRONTMATTER / INTERNAL.

    Create `tests/stock_mcp/test_add_note_paths.py` (P1-P6) and `tests/stock_mcp/test_add_note_frontmatter.py` (F1-F4 + D1). Use a function-scoped fixture (writable per-test copy of mcp-vault) to avoid polluting session fixture.

    For Test P6 (symlink), the test must:
    1. Create a directory `notes/private/sneaky/` in the per-test repo
    2. `os.symlink('/tmp/some-escape', notes/private/sneaky/escape)` (or any path outside whitelist)
    3. Call `add_note(path="notes/private/sneaky/escape/foo.md", ...)` — expect WRITE_FORBIDDEN.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run pytest tests/stock_mcp/test_add_note_paths.py tests/stock_mcp/test_add_note_frontmatter.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "def add_note" src/stock_mcp/tools/notes.py` returns 1 hit.
    - `grep -nE "safe_join|resolve_path_alias" src/stock_mcp/tools/notes.py` returns 2+ hits.
    - `grep -n "NoteFrontmatter" src/stock_mcp/tools/notes.py` returns ≥1 hit.
    - `grep -n "tempfile.mkstemp\|os.replace" src/stock_mcp/tools/notes.py` returns ≥2 hits (atomic write).
    - `grep -n "mcp.tool()(add_note)" src/stock_mcp/tools/notes.py` returns 1 hit.
    - `grep -nE "### Behavior contract|### Response shape|### Errors|### Performance budget" src/stock_mcp/tools/notes.py` returns 4 hits.
    - Test command exits 0; all 11 tests pass (P1-P6 + F1-F4 + D1).
  </acceptance_criteria>
  <done>add_note tool registered with whitelist + alias + frontmatter validation + atomic create + symlink defense; tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: add_note append-only flow + idempotency tests</name>
  <read_first>
    - src/stock_mcp/tools/notes.py (full add_note function from Task 1)
    - .planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md D-10, D-13
  </read_first>
  <behavior>
    - Test A1: Two consecutive `add_note(path="vault/notes/multi.md", body="first", frontmatter={"type":"note"})` then `add_note(path="vault/notes/multi.md", body="second", frontmatter={"type":"note","tickers":["005930"]})` — file exists; second response action="appended"; final body contains both "first" and "second" plus a `---\n## ` separator with KST ISO timestamp.
    - Test A2: Frontmatter merge: tickers union (initial=[], after second=["005930"]); `updated` field reflects second call's timestamp; `created` retained from first call.
    - Test A3: Idempotency — call `add_note` with identical (path, body, frontmatter) twice within the same minute (so timestamp header collides). Second call returns response with `idempotent=True`; file body is NOT duplicated.
    - Test A4: Different bodies but identical timestamp header second window: body is appended (not skipped). Idempotency only triggers on identical body+frontmatter delta.
    - Test A5: Existing file with malformed frontmatter (no opening `---`) → graceful append: treat existing content as "no frontmatter" and prepend a fresh frontmatter block? OR raise? **Decision:** Reject with `INVALID_FRONTMATTER` — existing file has malformed frontmatter; user must fix manually. (Documented in docstring under Errors.)
    - Test A6: Concurrent write simulation (two add_note calls back-to-back, same path) — both must succeed without lost write (atomic write guarantees serialization at fs level).
  </behavior>
  <action>
    Extend the `add_note` function from Task 1 to handle the `target.exists()` branch (append flow):

    1. Read existing file via `frontmatter.load(target)` (from python-frontmatter library; verify import path matches existing usage in src/shared/frontmatter.py:22).
    2. Validate the existing frontmatter parses to a dict; if the existing file has no `---` fence, raise `INVALID_FRONTMATTER` with detail "existing file lacks frontmatter; manual fix required".
    3. Merge frontmatter:
       ```python
       existing_fm = post.metadata
       merged_tickers = sorted(set(existing_fm.get("tickers", [])) | set(note_fm.tickers))
       merged_tags = sorted(set(existing_fm.get("tags", [])) | set(note_fm.tags))
       new_meta = {
           **existing_fm,
           "tickers": merged_tickers,
           "tags": merged_tags,
           "updated": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
       }
       # type/created/author preserved from existing if present; else from note_fm.
       ```
    4. Build separator + new section:
       ```python
       ts_header = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%dT%H:%M:%S%z")
       new_section = f"\n\n---\n## {ts_header}\n\n{body}"
       ```
    5. Idempotency check (D-13):
       - Look at the LAST `## ` separator in existing post.content.
       - If the last section's body equals the new body AND its timestamp header matches `ts_header` (truncated to second precision), skip the append.
       - Return `AddNoteResponse(vault_path=..., action="appended", idempotent=True)`.
    6. Otherwise concatenate `final_content = post.content + new_section` and atomic-write `Frontmatter+body` via the same tempfile.mkstemp + os.replace pattern.
    7. Return `AddNoteResponse(action="appended", idempotent=False)`.

    Add `tests/stock_mcp/test_add_note_append.py` covering A1-A6.

    For Test A3 (idempotency), the two calls happen in the same second — the test asserts the file content is the SAME after the second call (no duplicate section).

    For Test A6 (concurrent), use `concurrent.futures.ThreadPoolExecutor(max_workers=2)` to fire two add_note calls; both should succeed; final file content has both sections.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run pytest tests/stock_mcp/test_add_note_append.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "idempotent=True" src/stock_mcp/tools/notes.py` returns ≥1 hit.
    - `grep -nE "post.metadata|frontmatter.load" src/stock_mcp/tools/notes.py` returns ≥1 hit (existing file read).
    - `grep -nE "## \{|## \"|strftime" src/stock_mcp/tools/notes.py` returns ≥1 hit (timestamp header construction).
    - `grep -n "merged_tickers\|set(.*tickers" src/stock_mcp/tools/notes.py` returns ≥1 hit (union merge).
    - Test command exits 0; all 6 tests pass.
  </acceptance_criteria>
  <done>add_note append flow + idempotency working; concurrent writes do not corrupt; frontmatter merge correct.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| MCP caller (LLM) → tool function | path, body, frontmatter all untrusted |
| Tool → filesystem write | High-impact; only writable surface in Phase 6 MCP |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-6-06-01 | Tampering | path traversal (`..`) | mitigate | safe_join Path.resolve() + is_relative_to whitelist (D-09; tested P3). |
| T-6-06-02 | Tampering | symlink escape | mitigate | Path.resolve() follows symlinks BEFORE whitelist check (Pitfall 2; tested P6). |
| T-6-06-03 | Tampering | YAML deserialization in NoteFrontmatter | mitigate | yaml.safe_load only (existing pattern); Pydantic extra='forbid'. |
| T-6-06-04 | Tampering | frontmatter injection via body containing `---` | mitigate | Body appended AFTER existing closing fence; never re-parsed; new section uses markdown `## {ts}` header not YAML (D-10). |
| T-6-06-05 | Denial of Service / lost write | concurrent add_note | mitigate | tempfile.mkstemp + os.replace atomic; verified by Test A6. |
| T-6-06-06 | Information Disclosure | writing under notes/private/ | accept | notes/private/ is gitignored; user authored content goes there intentionally. |
</threat_model>

<verification>
- All 17 tests across the 3 test files pass.
- No path outside whitelist accepts a write.
- Concurrent writes preserve both sections.
</verification>

<success_criteria>
- Verify commands in both tasks exit 0.
- `pytest tests/stock_mcp/test_add_note_*.py -q` reports 17+ passes.
</success_criteria>

<output>
Create `.planning/phases/06-full-mcp-tool-surface/06-06-SUMMARY.md`.
</output>
