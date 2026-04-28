---
phase: 06-full-mcp-tool-surface
plan: 07
type: execute
wave: 2
depends_on: [02, 03]
files_modified:
  - src/stock_mcp/tools/health.py
  - src/ingest/heartbeat.py
  - tests/stock_mcp/test_health.py
autonomous: true
requirements: [MCP-09]
must_haves:
  truths:
    - "health() returns HealthResponse with overall status, per-source dict, db status, and timestamp"
    - "Primary data source is ingest_runs SQL aggregate; fallback to heartbeat.md parse when DB down or rows empty"
    - "STALENESS_THRESHOLDS_HOURS code constant: dart=26, krx=26, news=12, macro=26, kind=26"
    - "Per-source status: ok if age_hours<threshold, stale if age_hours>=threshold and <168h (7d), down if last run errored or no record"
    - "overall: any down → down, any stale → stale, else ok"
    - "DB unreachable: db.status='down'; sources still respond via heartbeat fallback"
    - "Docstring 4 sections per D-24"
  artifacts:
    - path: "src/stock_mcp/tools/health.py"
      provides: "health tool"
      contains: "def health"
    - path: "src/ingest/heartbeat.py"
      provides: "Public _read_sources renamed/exposed for reuse by health"
      contains: "def read_sources"
  key_links:
    - from: "src/stock_mcp/tools/health.py"
      to: "ingest_runs SQL aggregate"
      via: "SELECT source, MAX(finished_at) ..."
      pattern: "ingest_runs"
    - from: "src/stock_mcp/tools/health.py"
      to: "src/ingest/heartbeat.py read_sources"
      via: "import + call"
      pattern: "read_sources"
---

<objective>
Implement `health()` (MCP-09, D-14..D-17) — read-only telemetry surface reporting per-source staleness, DB connectivity, and overall status. Backs JUDGE-05 ("근거 없음/스테일" path) downstream.

Purpose: When data is stale or DB is down, Claude must refuse to speculate. health() is the signal that drives that behavior in Phase 9.

Output: 1 tool module + 1 small refactor of heartbeat.py (rename _read_sources → read_sources for public reuse) + 1 test module.
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
@src/stock_mcp/server.py
@src/ingest/heartbeat.py
@src/stock_mcp/models.py

<interfaces>
ingest_runs schema (Phase 2 migration 0001): `source` (text), `started_at` (timestamptz), `finished_at` (timestamptz), `error` (text nullable), and other status columns. `ingest_runs` is **empty in production today** (Pitfall 3) — Phase 9 OPS-03 populates. Phase 6 fixture conftest pre-seeds rows (per Plan 06-03 task 3).

heartbeat.md parser (src/ingest/heartbeat.py:34-53): `_read_sources(path: Path) -> dict` — reads YAML frontmatter `sources` dict, returns {source_name: {last_success, last_error, ...}}. Currently leading-underscore (private). Refactor: rename to `read_sources` and re-export.

Server `_check_db_connection` (src/stock_mcp/server.py:21-31): raises StructuredError(DB_UNAVAILABLE, ...) on failure.

Models from Plan 06-02: SourceHealth, HealthResponse.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Refactor heartbeat._read_sources → read_sources (public)</name>
  <read_first>
    - src/ingest/heartbeat.py (full file)
    - All call sites of `_read_sources` (run grep)
  </read_first>
  <action>
    1. In `src/ingest/heartbeat.py`, rename the function `_read_sources` to `read_sources`. Add `__all__ = [...]` (or extend existing) to include `read_sources`. Keep a short docstring documenting the return shape:
       ```python
       def read_sources(path: Path) -> dict:
           """Parse heartbeat.md and return {source_name: {last_success: datetime, last_error: str | None, ...}}.

           Returns empty dict if file missing or sources block absent.
           Used by stock_mcp.tools.health as fallback when ingest_runs is unreachable
           or empty.
           """
       ```
    2. Add a backwards-compatibility alias: `_read_sources = read_sources` so any internal callers in ingest/ keep working without further edits.
    3. Run grep across the codebase for `_read_sources(` and verify all call sites work via the alias.

    No behavior change.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run pytest tests/ingest/ -x -q 2>&amp;1 | tail -20</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "def read_sources" src/ingest/heartbeat.py` returns 1 hit.
    - `grep -n "_read_sources = read_sources" src/ingest/heartbeat.py` returns 1 hit (alias).
    - Existing ingest tests still pass (verify command exits 0; if no tests/ingest/ exists, run `pytest tests/test_ingest*.py` or skip the test step and rely on grep).
  </acceptance_criteria>
  <done>read_sources is public and importable; aliased _read_sources still works for legacy callers.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: health tool (MCP-09, D-14..D-17)</name>
  <read_first>
    - src/stock_mcp/tools/search.py (envelope pattern)
    - src/stock_mcp/server.py (_check_db_connection)
    - src/ingest/heartbeat.py (read_sources from Task 1)
    - src/stock_mcp/models.py (SourceHealth, HealthResponse)
    - .planning/phases/06-full-mcp-tool-surface/06-CONTEXT.md D-14, D-15, D-16, D-17
    - .planning/phases/06-full-mcp-tool-surface/06-UI-SPEC.md "Health Response Shape"
    - tests/stock_mcp/conftest.py (fixture seeds ingest_runs rows)
  </read_first>
  <behavior>
    - Test 1: Fresh DB with ingest_runs rows for all 5 sources, all recent (<26h) and successful → response.overall="ok", every source.status="ok".
    - Test 2: One source's last_success is 30h old → that source.status="stale"; overall="stale".
    - Test 3: One source's most recent ingest_runs row has non-null error → that source.status="down"; overall="down".
    - Test 4: DB unreachable (mock get_engine to raise) → response.db.status="down"; sources populated from heartbeat.md fallback; overall reflects fallback statuses.
    - Test 5: Both DB and heartbeat.md missing → all sources status="down" with last_error="no telemetry available"; db.status="down"; overall="down".
    - Test 6: STALENESS_THRESHOLDS_HOURS is monkeypatchable (test sets news threshold to 1h; verifies stale boundary).
    - Test 7: Response timestamp is recent (within 5s of test start) and KST-aware.
    - Test 8: Docstring 4 sections present.
  </behavior>
  <action>
    Create `src/stock_mcp/tools/health.py`:

    ```python
    """health tool — DB and per-source staleness telemetry (MCP-09, D-14..D-17)."""
    from __future__ import annotations
    import time
    from datetime import datetime, timedelta
    from pathlib import Path
    from zoneinfo import ZoneInfo

    import sqlalchemy as sa
    from db.engine import get_engine

    from ..errors import ErrorCode, StructuredError, to_error_response
    from ..logging import log_tool_call
    from ..models import SourceHealth, HealthResponse
    from .search import mcp

    # D-14 — code constant, monkeypatchable
    STALENESS_THRESHOLDS_HOURS: dict[str, float] = {
        "dart": 26,
        "krx": 26,
        "news": 12,
        "macro": 26,
        "kind": 26,
    }
    DOWN_AFTER_HOURS = 168  # 7d — stale beyond this is "down"
    HEARTBEAT_PATH_DEFAULT = Path("vault/ingested/_status/heartbeat.md")

    def _classify(age_hours: float | None, last_error: str | None, threshold: float) -> str:
        if last_error:
            return "down"
        if age_hours is None:
            return "down"
        if age_hours >= DOWN_AFTER_HOURS:
            return "down"
        if age_hours >= threshold:
            return "stale"
        return "ok"

    def _from_ingest_runs(engine) -> dict[str, SourceHealth]:
        """Aggregate ingest_runs per source. Returns {} if 0 rows."""
        sql = sa.text("""
            WITH ranked AS (
                SELECT source, started_at, finished_at, error,
                       ROW_NUMBER() OVER (PARTITION BY source ORDER BY started_at DESC) AS rn
                FROM ingest_runs
                WHERE source IS NOT NULL
            )
            SELECT
              source,
              MAX(finished_at) FILTER (WHERE error IS NULL) AS last_success,
              MAX(CASE WHEN rn = 1 THEN error END) AS last_error
            FROM ranked
            GROUP BY source
        """)
        with engine.connect() as conn:
            rows = conn.execute(sql).mappings().all()
        out: dict[str, SourceHealth] = {}
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        for r in rows:
            source = r["source"]
            ls = r["last_success"]
            age = ((now - ls).total_seconds() / 3600.0) if ls else None
            threshold = STALENESS_THRESHOLDS_HOURS.get(source, 26)
            status = _classify(age, r["last_error"], threshold)
            out[source] = SourceHealth(
                status=status,
                last_success=ls,
                age_hours=age,
                last_error=(r["last_error"] or None),
            )
        return out

    def _from_heartbeat(repo_root: Path) -> dict[str, SourceHealth]:
        """Fallback: parse heartbeat.md."""
        from src.ingest.heartbeat import read_sources
        path = repo_root / HEARTBEAT_PATH_DEFAULT
        try:
            sources = read_sources(path)
        except Exception:
            sources = {}
        out: dict[str, SourceHealth] = {}
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        for src_name, info in sources.items():
            ls = info.get("last_success")
            if isinstance(ls, str):
                ls = datetime.fromisoformat(ls)
            age = ((now - ls).total_seconds() / 3600.0) if ls else None
            threshold = STALENESS_THRESHOLDS_HOURS.get(src_name, 26)
            le = info.get("last_error")
            out[src_name] = SourceHealth(
                status=_classify(age, le, threshold),
                last_success=ls,
                age_hours=age,
                last_error=(le[:200] if le else None),
            )
        return out

    def _empty_sources_response() -> dict[str, SourceHealth]:
        return {
            s: SourceHealth(status="down", last_success=None, age_hours=None,
                            last_error="no telemetry available")
            for s in STALENESS_THRESHOLDS_HOURS
        }

    def _overall(sources: dict[str, SourceHealth], db: SourceHealth) -> str:
        if db.status == "down":
            return "down"
        statuses = [s.status for s in sources.values()]
        if "down" in statuses:
            return "down"
        if "stale" in statuses:
            return "stale"
        return "ok"

    def health() -> HealthResponse | dict:
        """4-section docstring: behavior contract / response shape / errors / perf budget."""
        t0 = time.perf_counter()
        # locate repo root via public helper from Plan 06-02
        from stock_mcp.repo_root import repo_root as _resolve_repo_root
        repo_root_path = _resolve_repo_root()
        try:
            db_status = SourceHealth(
                status="ok", last_success=None, age_hours=None, last_error=None
            )
            sources: dict[str, SourceHealth] = {}
            try:
                engine = get_engine()
                with engine.connect() as conn:
                    conn.execute(sa.text("SELECT 1"))
                # DB up
                ingest_runs_data = _from_ingest_runs(engine)
                if ingest_runs_data:
                    sources = ingest_runs_data
                else:
                    # ingest_runs empty (Pitfall 3) — fall back to heartbeat
                    sources = _from_heartbeat(repo_root_path) or _empty_sources_response()
            except Exception as e:  # noqa: BLE001
                db_status = SourceHealth(
                    status="down", last_success=None, age_hours=None,
                    last_error=str(e)[:200],
                )
                sources = _from_heartbeat(repo_root_path) or _empty_sources_response()
            # Ensure all 5 expected sources are present (fill missing with 'down')
            for expected in STALENESS_THRESHOLDS_HOURS:
                if expected not in sources:
                    sources[expected] = SourceHealth(
                        status="down", last_success=None, age_hours=None,
                        last_error="no telemetry available",
                    )
            result = HealthResponse(
                overall=_overall(sources, db_status),
                sources=sources,
                db=db_status,
                timestamp=datetime.now(ZoneInfo("Asia/Seoul")),
            )
            latency = int((time.perf_counter() - t0) * 1000)
            log_tool_call("health", {}, latency, len(result.model_dump_json()) // 4)
            return result
        except Exception as e:  # noqa: BLE001
            wrapped = StructuredError(ErrorCode.INTERNAL, str(e)[:200])
            latency = int((time.perf_counter() - t0) * 1000)
            err = to_error_response(wrapped)
            log_tool_call("health", {}, latency, 0, error=err["error"])
            return err

    mcp.tool()(health)
    ```

    Docstring (4 sections per D-24):
    - **Behavior contract:** No parameters; never raises (returns dict on internal failure but the normal "DB down" case is a successful HealthResponse with db.status='down').
    - **Response shape:** HealthResponse with overall (ok/stale/down), sources dict (keys: dart, krx, news, macro, kind), db (SourceHealth), timestamp (KST ISO).
    - **Errors:** Only INTERNAL on truly unexpected failure. DB unreachable is NOT an error — it's reported via db.status='down'.
    - **Performance budget:** p95 < 2s, p95 < 2k tokens.

    Create `tests/stock_mcp/test_health.py` covering Tests 1-8. For Test 4 (DB down), monkeypatch `get_engine` to raise. For Test 6 (threshold monkeypatch), use `monkeypatch.setitem(health_module.STALENESS_THRESHOLDS_HOURS, "news", 1)`.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/minsu/workspace/stock &amp;&amp; uv run pytest tests/stock_mcp/test_health.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "def health" src/stock_mcp/tools/health.py` returns 1 hit.
    - `grep -n "STALENESS_THRESHOLDS_HOURS" src/stock_mcp/tools/health.py` returns ≥1 hit (with values dart=26, krx=26, news=12, macro=26, kind=26).
    - `grep -n "from src.ingest.heartbeat import read_sources" src/stock_mcp/tools/health.py` returns 1 hit.
    - `grep -n "from stock_mcp.repo_root import repo_root" src/stock_mcp/tools/health.py` returns 1 hit.
    - `grep -nE "^def _repo_root|^    def _repo_root" src/stock_mcp/tools/health.py` returns 0 hits (no local helper).
    - `grep -n "_from_ingest_runs\|_from_heartbeat" src/stock_mcp/tools/health.py` returns ≥2 hits.
    - `grep -n "mcp.tool()(health)" src/stock_mcp/tools/health.py` returns 1 hit.
    - `grep -nE "### Behavior contract|### Response shape|### Errors|### Performance budget" src/stock_mcp/tools/health.py` returns 4 hits.
    - Test command exits 0; all 8 tests pass.
  </acceptance_criteria>
  <done>health tool registered; primary path (ingest_runs SQL) + fallback (heartbeat.md) + double-fallback (empty sources) all working; all 5 sources always present in response.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| ingest_runs / heartbeat.md → tool response | Internal telemetry — trusted but length-bounded |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-6-07-01 | Information Disclosure | last_error string from internal exception | mitigate | Truncate to 200 chars before inclusion in SourceHealth.last_error. |
| T-6-07-02 | Denial of Service | health() blocking on DB connection | mitigate | _check_db_connection has a fast SELECT 1; if engine.connect() hangs, the tool falls into the except branch and reports DB down. |
</threat_model>

<verification>
- All 5 expected sources always present in response (ingest_runs data + missing-source fill).
- DB-down case returns SUCCESSFUL HealthResponse with db.status='down', not error envelope.
</verification>

<success_criteria>
- Verify commands in both tasks exit 0.
</success_criteria>

<output>
Create `.planning/phases/06-full-mcp-tool-surface/06-07-SUMMARY.md`.
</output>
