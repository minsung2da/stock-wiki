# Phase 4: Analysis Runner (3-role Debate) - Pattern Map

**Mapped:** 2026-06-28
**Files analyzed:** 17 (9 new `src/analysis/`, 6 new `tests/analysis/`, 2 modified)
**Analogs found:** 15 / 17 (2 orchestrators are composites with no single analog)

This codebase is highly self-consistent: read-side tools (`src/mcp_v2/tools/*`), the
card store (`src/cards/store.py`), and the shared numeric pipeline (`src/shared/number_*`,
`units`) all share one house style — module-level docstring citing the lock/Veto, typed
Pydantic returns with `ConfigDict(extra="forbid")`, parameterized `text()` SQL (Veto #7),
pure functions for transforms, and a patchable test seam (`_http_get`-style) for every
external call. New `src/analysis/` files should copy that style verbatim.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/analysis/__init__.py` | package barrel | n/a | `src/cards/__init__.py` | exact |
| `src/analysis/runner.py` | orchestrator/service | request-response + batch | *(composite — store + tools + subagents + checksum)* | no single analog |
| `src/analysis/bundle.py` | model + service | CRUD read-aggregation | `src/mcp_v2/models.py` + `src/mcp_v2/tools/filing.py` | role-match |
| `src/analysis/subagents.py` | service/adapter | request-response (subprocess) | `src/collectors/dart/fetcher.py` | role-match (subprocess vs HTTP) |
| `src/analysis/roles.py` | config/constants | n/a | `src/mcp_v2/injection.py` (`PATTERNS`) + `src/shared/number_sanity.py` (`SANITY_RULES`) | role-match |
| `src/analysis/checksum.py` | utility | transform | `src/shared/number_sanity.py` + `number_extraction.py` + `units.py` | exact |
| `src/analysis/gate.py` | service/utility | request-response (decision) | `src/cards/store.py::get_active` consumer + pure logic | partial |
| `src/analysis/rubric.py` | utility | transform | `src/shared/units.py` + `number_sanity.py` (table-driven map) | role-match |
| `src/analysis/cost.py` | utility/observability | transform/event | `src/shared/run_log.py` | role-match |
| `tests/analysis/conftest.py` | test fixtures | n/a | `tests/cards/conftest.py` + `tests/mcp_v2/conftest.py` + `tests/collectors/dart/test_fetcher.py` | exact |
| `tests/analysis/test_runner.py` | test (integration) | n/a | `tests/cards/test_store.py` | exact |
| `tests/analysis/test_checksum.py` | test (unit) | n/a | `tests/test_number_extraction.py` / `test_number_sanity.py` / `test_units.py` | exact |
| `tests/analysis/test_gate.py` | test (unit) | n/a | `tests/test_dart_fetcher_retry.py` (seam-mock + call-count asserts) | role-match |
| `tests/analysis/test_rubric.py` | test (unit) | n/a | `tests/test_units.py` (pure-fn) | exact |
| `tests/analysis/test_live.py` | test (opt-in integration) | n/a | `tests/test_api_probes.py` (`@pytest.mark.slow`) | role-match |
| `src/cards/models.py` (MOD) | model | n/a | itself — `invalidation_reason`/`status` optional fields | exact (in-file precedent) |
| `tests/test_import_guard.py` (MOD) | test/guard | n/a | itself — `GUARDED_DIRS` list | exact (in-file precedent) |
| `pyproject.toml` (MOD) | config | n/a | itself — `[tool.pytest.ini_options] markers` | exact (register `live` marker) |

---

## Pattern Assignments

### `src/analysis/checksum.py` (utility, transform) — STRONGEST ANALOG

**Analogs:** `src/shared/units.py`, `src/shared/number_extraction.py`, `src/shared/number_sanity.py` (all pure, no-I/O, reuse directly — do NOT re-implement, per RESEARCH "Don't Hand-Roll").

**KRW normalization primitive** (`src/shared/units.py:13-41`) — call this; do not reinvent 억/조:
```python
KRW_MULTIPLIERS: Mapping[str, float] = MappingProxyType(
    {"KRW원": 1.0, "KRW백만": 1e6, "KRW억": 1e8, "KRW조": 1e12}
)

def normalize_to_krw(value: float, unit: str) -> float | None:
    """Convert (value, unit) to KRW원. Returns None for non-KRW units."""
    mult = KRW_MULTIPLIERS.get(unit)
    if mult is None:
        return None
    return float(value) * mult
```

**Source-scan primitive** (`src/shared/number_extraction.py:117-127`) — yields `guessed_unit` per span, codepoint-safe offsets, 13 unit families ordered longest-first (`number_extraction.py:55-79`):
```python
def extract_numeric_candidates(body: str, section_hint: str | None = None) -> list[NumericCandidate]:
    """Returns up to MAX_CANDIDATES_PER_DOC candidates, non-overlapping, by offset.
    body[offset:offset+length] == raw_text holds (echo-back precondition)."""
```
`NumericCandidate` (`number_extraction.py:34-46`) fields: `raw_text`, `offset`, `length`, `guessed_unit`, `sentence_text`, `pre_context`, `post_context`, `section_hint`.

**Magnitude guard** (`src/shared/number_sanity.py:30-63, 86-109`) — `SANITY_RULES` table (24 keys) + `check_sanity()` as the second gate.

**Checksum core shape** (RESEARCH §Code Examples, build on the primitives above):
```python
from shared.units import normalize_to_krw
from shared.number_extraction import extract_numeric_candidates

def fact_supported(value: float, unit: str, body_md: str, tol: float = 0.005) -> bool:
    target = normalize_to_krw(value, unit) if unit.startswith("KRW") else value
    for cand in extract_numeric_candidates(body_md):
        raw = float(cand.raw_text.replace(",", "").rstrip("조억백만원%배주포인트"))
        cv = normalize_to_krw(raw, cand.guessed_unit) if cand.guessed_unit.startswith("KRW") else raw
        if cv is None or target is None:
            continue
        if abs(cv - target) / max(abs(cv), abs(target), 1e-9) <= tol:
            return True
    return False
```
**Divergence from v1.0:** D-03 deliberately uses *value-equivalence* (tolerance compare),
NOT v1.0's exact `check_echo_back` at-offset (`number_sanity.py:66-83`) — exact-only
mass-drops legitimately re-formatted KR values (`42.5조원` vs `42,500,000,000,000`).
Reuse the primitives, not the echo-back gate.

**Module docstring style** to copy (every shared module opens this way): cite the lock,
state "Pure Python. No LLM, no I/O." (see `number_extraction.py:1-8`).

---

### `src/analysis/subagents.py` (service/adapter, subprocess) — `claude -p` wrapper

**Analog:** `src/collectors/dart/fetcher.py` (the only retry+error-classification+test-seam
module in the repo; it uses `requests` HTTP, the new file uses `asyncio` subprocess, but the
*structure* maps 1:1).

**Patchable single-call seam** (`fetcher.py:141-154`) — isolate the raw call so tests patch ONE function. Mirror this with the subprocess spawn:
```python
def _http_get(rcept_no: str, api_key: str) -> requests.Response:
    """Single GET against the OpenDART document API (patchable test seam)."""
    resp = requests.get(_DOCUMENT_API_URL, params={...}, timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp
```
→ new file: a `_spawn_claude(...)` (or `call_role`) seam tests patch via `monkeypatch.setattr`.

**Typed retryable/permanent exception split** (`fetcher.py:71-104`) — copy this hierarchy idea for auth/overload vs rate-limit:
```python
class DartDocumentError(RuntimeError): ...        # permanent
class DartThrottleError(DartDocumentError): ...   # retryable subclass
_RETRYABLE_EXC: tuple[type[BaseException], ...] = (ReqConnectionError, ..., DartThrottleError)
```
→ new file: `SubAgentError` (auth_failed/non-zero exit = permanent) vs a retryable
overload/rate_limit subclass, gated by `is_error` + error category in the JSON envelope
(RESEARCH §Verified CLI Mechanics 4).

**tenacity decorator** (`fetcher.py:157-163`) — exact retry-policy template (RESEARCH says one retry; this shows the canonical decorator if more are wanted):
```python
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1.0, min=1.0, max=30.0),
    retry=retry_if_exception_type(_RETRYABLE_EXC),
    before_sleep=before_sleep_log(_log, logging.WARNING),
    reraise=True,
)
```

**Error-envelope classification** (`fetcher.py:204-226`) — copy the "inspect status → return-empty / raise-retryable / raise-permanent" branch for the CLI's `is_error` envelope.

**RESEARCH-locked subprocess shape** (NOT in repo — from RESEARCH §Pattern 1, live-verified):
```python
proc = await asyncio.create_subprocess_exec(
    "claude", "-p", instruction,
    "--output-format", "json", "--model", "sonnet",
    "--json-schema", json.dumps(schema),
    "--strict-mcp-config",                       # Pitfall 3: no .mcp.json auto-spawn
    "--append-system-prompt", ROLE_SYSTEM_PROMPTS[role],
    stdin=asyncio.subprocess.PIPE, stdout=..., stderr=...,
)
out, err = await asyncio.wait_for(proc.communicate(evidence_stdin.encode("utf-8")), timeout=timeout_s)
env = json.loads(out)                            # tee raw bytes to log BEFORE parse
if env.get("is_error"): raise SubAgentError(role, env)
payload = env["structured_output"]               # parsed object, NOT result string
```
Veto/anti-patterns (RESEARCH §Anti-Patterns): no `--bare` (forces API key → breaks Max-only
Veto); no `shell=True` / argv interpolation of evidence (Windows 32K + injection) → evidence
on **stdin**; read `structured_output` not `result`.

---

### `src/analysis/bundle.py` (model + service, read-aggregation)

**Model analog:** `src/mcp_v2/models.py:55-70` — every return model is `ConfigDict(extra="forbid")`, empty-able, identifier fields carry no default:
```python
class FilingDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rcept_no: str
    corp_code: str = Field(pattern=_CORP_CODE_PATTERN)
    body_md: str  # wrapped via injection.wrap_untrusted (D-03)
```
→ `EvidenceBundle` = `ConfigDict(extra="forbid")` Pydantic model holding the pre-fetched tool outputs.

**Build-function analog:** the in-process tools are plain callables (registered via `mcp.tool(...)(fn)` call-form, NOT `@mcp.tool`, exactly so in-process callers like this runner work — see `filing.py:187-195`). `build_bundle` calls them directly:
- `search_filings(corp_code, since=...)` → `get_filing(rcept_no)` for top-K (`src/mcp_v2/tools/filing.py:94, 131`)
- `ohlcv_range(ticker, from_date, to_date)`, `flow_range(...)`, `peer_view(corp_code, metric)` (`src/mcp_v2/tools/market.py:151, 193, 233`)
- `hybrid_search(query, source_filter, date_range, limit)` (`src/mcp_v2/tools/search.py:45`)
- `get_note(path)` (`src/mcp_v2/tools/note.py:54`)

**Narrative already injection-wrapped (free, D-02/D-03):** `get_filing`/`get_note`/`hybrid_search`
return bodies already passed through `injection.wrap_untrusted` + flagged (`filing.py:116-128`,
`note.py:71-73`). Bundle serialization keeps the `<untrusted source="..." ref="...">` delimiter:
```python
# src/mcp_v2/injection.py:106-116
def wrap_untrusted(body: str, source: str, ref_id: str) -> str:
    if not _SAFE_ATTR.match(source) or not _SAFE_ATTR.match(ref_id):
        raise ValueError("invalid delimiter attribute")
    return f'<untrusted source="{source}" ref="{ref_id}">\n{body}\n</untrusted>'
```

**Engine access:** tools call `get_engine()` internally; for the store-write path the runner passes `engine` explicitly (see store section). Do NOT add a `run_sql` escape hatch (Veto #7).

---

### `src/analysis/runner.py` (orchestrator) — COMPOSITE, no single analog

Assemble from the analogs above. The save/gate wiring has exact reuse targets:

**Prior-card load + atomic supersede** (`src/cards/store.py:204-216, 147-201`):
```python
prior = store.get_active(engine, corp_code)            # D-04 "yesterday's card" or None
# ... build card ...
store.save_card(engine, card, supersedes=prior.card_id if prior else None)
```
`save_card` flips the prior row to `superseded` in the SAME `with engine.begin()` txn
(`store.py:194-201`); reuse it — no new write path (RESEARCH Discretion #7). Analysis calls
`store` directly, NOT via an MCP write tool (out of scope).

**Card construction + Veto #2 enforcement** (`src/cards/models.py:68-104`): build a
`DecisionCard` — `expires_at` (non-Optional) and `assumptions` (`min_length=1`) raise
`ValidationError` if omitted; that IS SC#4. Re-validate the Judge's `structured_output`
through this model (RESEARCH Discretion #2: constrained decode guarantees shape, not semantics).

**SC#5 empty-contradictions warning** (RESEARCH Discretion #8) — structured logging like the rest of the repo:
```python
if not card.contradictions:
    logging.warning("card has no contradictions — suspect", extra={"corp_code": ..., "card_id": ...})
```

**Structured `logging.*(extra={...})`** is the house convention (stdout = JSON output,
stderr = structured logs; see `run_log.py:9-12`, `fetcher.py:212-215`).

---

### `src/analysis/cost.py` (observability) — SC#7

**Analog:** `src/shared/run_log.py` — the dual-sink pattern (structured stderr + best-effort DB row).
RESEARCH §Alternatives explicitly says do NOT overload `record_collector_run`: `_ALLOWED_SOURCES`
(`run_log.py:43-45`) is a hard 7-source CHECK that excludes analysis. Copy the *shape*, new sink.

**Best-effort degrade pattern to copy** (`run_log.py:127-138`) — observability write never aborts the run:
```python
except Exception as exc:  # noqa: BLE001 — best-effort sink, swallow & log
    _log.warning("... INSERT failed (degrade to stderr-only): %s: %s", type(exc).__name__, exc, extra={...})
    return None
```
**SC#7 source data** = the per-call `claude -p` JSON envelope subset (RESEARCH §3, live-verified):
`total_cost_usd`, `duration_ms`, `usage{input_tokens,output_tokens,cache_*}`, `modelUsage{...}`.
Capture per Bull/Bear/Judge call + bundle-build wall time. Structured stderr alone satisfies
SC#7's "Phase 9 input"; an optional new `analysis_runs` table is the planner's call (NOT `collector_runs`).

---

### `src/analysis/gate.py` (decision logic) — D-04

**Analog:** consumes `store.get_active` (`store.py:204-216`) for the prior card; pure-Python
deterministic decision (no LLM — RESEARCH Responsibility Map). Triggers (RESEARCH Discretion #5,
all `[ASSUMED]`): new filing since `prior.as_of`, price spike ≥7% / vol ≥3×20d, flow ≥2σ,
near-expiry `prior.expires_at − as_of ≤ 7d`, invalidation/assumption break, safety-net N=14d.
Reads price/flow via the same `ohlcv_range`/`flow_range` callables `bundle.py` uses. Lightweight
refresh must NOT extend `expires_at` (near-expiry is itself a full-debate trigger).

---

### `src/analysis/roles.py` (constants/config)

**Analog:** module-level ordered constant tables — `src/mcp_v2/injection.py:40-74` (`PATTERNS`)
and `src/shared/number_sanity.py:30-63` (`SANITY_RULES`). Hold Bull/Bear/Judge system prompts +
inline JSON schemas (RESEARCH Discretion #2). Schema shapes are in RESEARCH Discretion #2; pass
each as `json.dumps(schema)` to `--json-schema` (inline string, NOT a file path).

---

### `src/analysis/rubric.py` (transform) — Judge rubric → conviction/stance

**Analog:** `src/shared/units.py` (pure table-driven map) + `number_sanity.py:86-109` (rule
lookup → result). RESEARCH Discretion #1: `conviction = clamp(Σ wᵢ·scoreᵢ / (10·Σwᵢ), 0, 1)`;
keep the weight table + stance table auditable module-level constants (Veto #4 — decomposable to
cited evidence, no black-box). Hard cap (Veto #5): `conviction ≥ 0.8` only with ≥2 independent
HIGH/MEDIUM refs across ≥2 source families — enforce in Python, not the prompt.

---

### `src/analysis/__init__.py` (barrel)

**Analog:** `src/cards/__init__.py` (verbatim style) — short docstring + explicit re-exports + `__all__`:
```python
from .runner import analyze_ticker
__all__ = ["analyze_ticker"]
```

---

## Test Pattern Assignments

### `tests/analysis/conftest.py`

**Fake-claude fixture (the Wave-0 gap):** the subprocess seam must be mockable. Copy the
flaky/canned-seam fakes from `tests/test_dart_fetcher_retry.py:56-99` and the patch pattern from
`tests/collectors/dart/test_fetcher.py:51-58`:
```python
@pytest.fixture(autouse=True)
def _dummy_key(monkeypatch):
    monkeypatch.setattr("collectors.dart.client.get_api_key", lambda: "dummy-key")

def _patch_get(monkeypatch, content: bytes) -> None:
    monkeypatch.setattr(fetcher, "_http_get", lambda rcept_no, api_key: _FakeResp(content))
```
→ patch `analysis.subagents._spawn_claude` (or `call_role`) to return canned `structured_output`
envelopes. Class-based stateful fakes with a `.calls` counter (`_FlakyGet`,
`test_dart_fetcher_retry.py:56-69`) are the template for "assert sub-agent NOT called" (SC#6) and
"called twice in parallel, blind" (SC#2).

**EvidenceBundle / card fixtures:** copy `tests/cards/conftest.py:24-98` (`decision_card_yaml` =
the §3 round-trip oracle dict) and `tests/mcp_v2/conftest.py:31-122` (`seeded_engine` /
`seeded_narrative_engine` — seed entities + filings/news/notes; conftest scoping is per-directory,
so re-declare what's needed). Real-filing fixture target: corp `00126380` / ticker `005930`.

### `tests/analysis/test_runner.py` (integration)
**Analog:** `tests/cards/test_store.py:1-60` — `seeded_engine` + a `_make_card` helper that
overrides `card_id` from the §3 oracle; assert round-trip + supersession. Add mocked sub-agents.

### `tests/analysis/test_checksum.py` (unit)
**Analog:** `tests/test_number_extraction.py`, `tests/test_number_sanity.py`, `tests/test_units.py`
(pure-function, table of in/out cases, no DB). Edge cases: `42.5조원` ≡ `42,500,000,000,000` ≡ `425000억`.

### `tests/analysis/test_gate.py` (unit)
**Analog:** `tests/test_dart_fetcher_retry.py` — seam-mock + `assert get.calls == N` is exactly
the SC#6 "lightweight refresh did NOT spawn the LLM" assertion shape.

### `tests/analysis/test_live.py` (opt-in)
**Analog:** `tests/test_api_probes.py:37` (`@pytest.mark.slow`). Register a `live` marker
(see pyproject mod) and gate the real-`claude` smoke behind it so the default run skips quota cost.

---

## Shared Patterns (apply to all new files)

### Module docstring header
**Source:** every module (`store.py:1-35`, `number_extraction.py:1-8`, `injection.py:1-28`,
`market.py:1-25`). Open with a one-line summary citing the lock (D-0x / SC#x / Veto #x), then a
short contract. Korean inline comments are allowed (CLAUDE.md Conventions).

### Typed Pydantic returns, `extra="forbid"`
**Source:** `src/cards/models.py:36`, `src/mcp_v2/models.py:63`.
**Apply to:** `bundle.py` (EvidenceBundle), `subagents.py` (RoleResult), and re-validating every
sub-agent `structured_output` through `DecisionCard`.
```python
model_config = ConfigDict(extra="forbid")
```

### Optional payload field = no DB migration (the `warnings` field)
**Source:** `src/cards/models.py:93-104` — the in-file precedent for `invalidation_reason` /
`status` added as optional payload fields with NO DB column change.
**Apply to:** `src/cards/models.py` MOD — add `warnings: list[str] = Field(default_factory=list)`
for D-03 dropped facts (RESEARCH Open Q1). It rides in payload JSONB; `store.save_card`'s
`model_dump(mode="json")` + `_PAYLOAD_EXCLUDE` (`store.py:64`) need NO change (warnings is not
excluded → persists in payload; reconstruct round-trips because the field exists). Confirm with planner.

### Parameterized `text()` SQL only (Veto #7)
**Source:** `src/cards/store.py:67-125`, `src/mcp_v2/tools/market.py:55-127` — module-level
`text()` constants, bind params only, NEVER f-string. Any DB read the gate/cost layers add must follow this.

### Cloud-LLM import guard (Max-only Veto)
**Source:** `tests/test_import_guard.py:19-20` — `BANNED_MODULES = {"anthropic", "openai"}`,
`GUARDED_DIRS = ["src/collectors"]`.
**Apply to:** MOD `GUARDED_DIRS` → add `"src/analysis"` (RESEARCH §Security). This is the CI
enforcement of D-01 "no API direct calls" — the runner must reach the model only via the `claude` CLI.

### Patchable single-call test seam
**Source:** `fetcher.py:141-154` (`_http_get`). Every external call gets one thin function tests
patch with `monkeypatch.setattr`. Mandatory for `subagents.py` (no real `claude` in default tests).

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/analysis/runner.py` | orchestrator | request-response + batch | First multi-stage orchestrator in the repo (`src/orchestration/` is an empty stub). Composite of store + tools + subagents + checksum + cost analogs — no single file to copy; wiring shown in §runner above. |
| `src/analysis/subagents.py` (subprocess core) | adapter | subprocess | No existing `asyncio.create_subprocess_exec` usage anywhere in the repo. The *retry/error/seam structure* copies `fetcher.py`; the subprocess body itself comes from RESEARCH §Pattern 1 (live-verified, not from repo). |

---

## Metadata

**Analog search scope:** `src/cards/`, `src/mcp_v2/` (tools, injection, models, errors),
`src/shared/` (units, number_extraction, number_sanity, run_log, retry), `src/collectors/dart/`,
`tests/` (cards, mcp_v2, collectors/dart, import_guard, dart_fetcher_retry, api_probes), `pyproject.toml`.
**Files scanned:** ~20 read in full + 2 globs (74 src + 88 test files enumerated).
**Confirmed greenfield:** `src/analysis/` and `tests/analysis/` do NOT exist yet.
**Pattern extraction date:** 2026-06-28
