# Phase 3: MCP Tool Surface (Read-Side) + scope-expanded data collection - Pattern Map

**Mapped:** 2026-06-01
**Files analyzed:** 32 (CREATE) + 5 (MODIFY)
**Analogs found:** 35 / 37 (2 genuinely-new files have no in-tree analog — see No Analog Found)

This phase has THREE clusters. Analogs come from three families:
- **Phase 2 in-tree code** (`src/cards/`, `src/shared/`, `src/db/`) — the current SQL/Pydantic/migration discipline. **Prefer these for style.**
- **Existing collectors** (`src/collectors/krx/`, `src/collectors/dart/`) — DB-direct INSERT pattern for the new fundamentals collector + notes-ingest.
- **v1.0 archive** (`git show archive/llm-wiki-2026-04:src/stock_mcp/<file>` and `:src/ingest/<file>`) — structure + RRF/injection/path/embedding/tokenizer logic to PORT (not import; the archive tree is deleted).

> **Archive retrieval:** `git -C C:\Users\minsu\workspace\stock show archive/llm-wiki-2026-04:src/stock_mcp/server.py` etc. The archive is read-only history; copy the logic into `src/mcp_v2/`, swap the error model to D-01, retarget chunks→whole-body tables.

> **Hard Vetoes honored throughout:** #6 (no embedding of numeric tables — ohlcv/macro/decision_cards excluded from hybrid_search; fundamentals stored as typed columns, never embedded), #7 (no run_sql — every SQL is a module-level `text()` constant + bind params; CI guard test added), #8 (no pre-chunking — get_filing returns whole body_md; hybrid candidate = one whole row), #13 (get_decision_card payload default via serialize-time `exclude`).

---

## File Classification

### Cluster 1 — MCP server + tools (`src/mcp_v2/`)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/mcp_v2/__init__.py` | config (package) | n/a | archive `src/stock_mcp/server.py` (re-export shape) | role-match |
| `src/mcp_v2/__main__.py` | entry point | request-response | archive `src/stock_mcp/__main__.py` | exact (swap error model) |
| `src/mcp_v2/server.py` | server | request-response | archive `src/stock_mcp/server.py` | exact (drop graph/overview tools) |
| `src/mcp_v2/errors.py` | utility (exceptions) | n/a | archive `src/stock_mcp/errors.py` + RESEARCH §Pattern 2 | role-match (REPLACE dict-return → ToolError subclass) |
| `src/mcp_v2/models.py` | model (Pydantic returns) | transform | `src/cards/models.py` | exact |
| `src/mcp_v2/injection.py` | utility (leaf) | transform | archive `src/ingest/injection_defense.py` | exact (gate→WRAP+FLAG) |
| `src/mcp_v2/retrieval.py` | service (RRF core) | request-response | archive `src/stock_mcp/search_core.py` | role-match (chunks→whole-body) |
| `src/mcp_v2/embedding.py` | utility (leaf) | transform | archive `src/ingest/embedder.py` | exact |
| `src/mcp_v2/tokenizer.py` | utility (leaf) | transform | archive `src/ingest/tokenizer.py` | exact |
| `src/mcp_v2/paths.py` | utility (leaf) | file-I/O | archive `src/stock_mcp/paths.py` `safe_join` | exact (write→read-only variant) |
| `src/mcp_v2/tools/__init__.py` | config (package) | n/a | archive `src/stock_mcp/server.py` side-effect import block | role-match |
| `src/mcp_v2/tools/filing.py` | controller (tool) | CRUD (read) | `src/cards/store.py` `get_active` + `src/db/entity.py` | role-match |
| `src/mcp_v2/tools/market.py` | controller (tool) | request-response (numeric) | `src/collectors/krx/db_writer.py` (ohlcv SQL) + `src/db/entity.py` | role-match |
| `src/mcp_v2/tools/search.py` | controller (tool) | request-response | archive `src/stock_mcp/tools/search.py` | exact (registers shared `mcp`) |
| `src/mcp_v2/tools/note.py` | controller (tool) | file-I/O | `src/shared/portfolio.py` `load` + archive `paths.py` | role-match |
| `src/mcp_v2/tools/card.py` | controller (tool) | CRUD (read) | `src/cards/store.py` `get_active` + RESEARCH §get_decision_card | exact |
| `src/mcp_v2/tools/portfolio.py` | controller (tool) | file-I/O | `src/shared/portfolio.py` `Portfolio.load` | exact (thin wrap) |
| `src/mcp_v2/tools/briefing.py` | controller (tool) | request-response | RESEARCH §get_briefing partial + `src/cards/models.py` empty model | role-match |

### Cluster 2 — Data collection (D-06 fundamentals + D-05 notes ingest)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/collectors/fundamentals/__init__.py` | service (collector orchestrator) | batch | `src/collectors/krx/__init__.py` `collect_krx` | exact |
| `src/collectors/fundamentals/client.py` | utility (vendor wrapper) | request-response | `src/collectors/krx/client.py` (pykrx) | exact |
| `src/collectors/fundamentals/fetcher.py` | utility (retry wrapper) | request-response | `src/collectors/krx/fetcher.py` (tenacity) | exact |
| `src/collectors/fundamentals/db_writer.py` | service (DB-direct upsert) | CRUD (upsert) | `src/collectors/krx/db_writer.py` `upsert_ohlcv` | exact |
| `src/collectors/fundamentals/roe.py` (ROE from dart-fss) | utility (transform) | transform | `src/collectors/dart/financials.py` `get_structured_financials` | exact |
| `src/mcp_v2/backfill.py` (or `src/collectors/notes_ingest/__init__.py`) — notes-ingest job | service (backfill) | batch / file-I/O | `src/collectors/krx/__init__.py` orchestration + `src/shared/portfolio.py` disk read + `src/collectors/dart/db_writer.py` narrative upsert | role-match |
| (embedding/tsv/bm25 backfill of existing filings/news) | service (backfill) | batch / transform | archive `src/ingest/` pipeline + `src/cards/store.py` parameterized UPDATE | role-match |

> **Placement note for the planner:** the notes-ingest + embedding backfill is a Wave-0 job that the MCP tools depend on. It imports `embedding.py`/`tokenizer.py` (kept as `src/mcp_v2/` siblings per RESEARCH §Recommended Structure) OUTSIDE the MCP context. Whether it lives in `src/mcp_v2/backfill.py` or `src/collectors/notes_ingest/` is planner discretion — both are valid; the collector-dir placement matches `record_collector_run`'s source set better (see Cluster-3 MODIFY note on the `collector_runs` CHECK).

### Cluster 3 — DB schema (migration 0008 + fundamentals/notes tables)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/db/migrations/versions/0008_phase03_*.py` | migration | n/a | `0007_decision_cards.py` (structure) + `0002_phase03_chunking_columns.py` (BM25/HNSW SQL) | exact |
| `src/db/entity_models.py` (ADD Fundamentals + Note ORM classes) | model (ORM) | n/a | `src/db/entity_models.py` `Filing`/`OHLCV` classes + `_HalfVec` | exact (in-file) |

### Cross-cluster MODIFY targets

| Modified File | What Changes | Analog for the change |
|---------------|--------------|-----------------------|
| `pyproject.toml` | re-add `mcp` + `ingest` dependency groups; add `src/mcp_v2` (+ fundamentals/notes_ingest) to `[tool.hatch.build.targets.wheel].packages` | RESEARCH §Standard Stack Installation block |
| `.mcp.json` (CREATE at repo root) | register stdio server: `command`/`args` spawn `.venv` python `-m mcp_v2`, `env` passes `DATABASE_URL` | RESEARCH A5 + Runtime State Inventory |
| `src/shared/run_log.py` | extend `_ALLOWED_SOURCES` + `collector_runs` CHECK if fundamentals/notes_ingest record runs | `src/shared/run_log.py` `_ALLOWED_SOURCES` frozenset |
| `src/cli/commands.py` (optional) | add `cmd_collect_fundamentals` if exposed via CLI | `src/cli/commands.py` `cmd_collect_krx` |
| `tests/mcp_v2/*` + `tests/collectors/*` + `tests/db/test_migration_0008.py` | new test files (Wave-0 gaps) | `tests/db/test_migration_0002.py` (exists) + RESEARCH §Validation Architecture |

---

## Pattern Assignments

### `src/mcp_v2/errors.py` (utility, exceptions)

**Analog:** archive `src/stock_mcp/errors.py` (structure to REPLACE, not copy) + RESEARCH §Pattern 2.

The archive used a `StructuredError` + `to_error_response()` dict — **do NOT port that.** D-01 mandates typed exceptions that subclass FastMCP's `ToolError`. Replace with:

```python
# src/mcp_v2/errors.py — D-01 typed exception hierarchy (RESEARCH §Pattern 2)
from fastmcp.exceptions import ToolError

class McpToolError(ToolError):
    """Base for all stock-mcp-v2 tool faults (bad arg, missing entity, DB error)."""

class InvalidArgument(McpToolError): ...   # ticker not ^[0-9]{6}$, bad view/type
class EntityNotFound(McpToolError): ...     # ticker/corp_code resolves to nothing
class FilingNotFound(McpToolError): ...     # get_filing(rcept_no) — no such row
class NotePathForbidden(McpToolError): ...  # get_note path outside whitelist
class NoteNotFound(McpToolError): ...
class DataBackendError(McpToolError): ...   # DB unreachable / query failure
```

**Change vs archive:** delete `ErrorCode` enum + `to_error_response`. FastMCP converts a raised `ToolError` to the MCP error response; set `FastMCP(..., mask_error_details=True)` so non-`ToolError` bugs show a generic message while `McpToolError` messages stay specific (verify A6 at planning).

---

### `src/mcp_v2/server.py` + `__main__.py` (server + entry point)

**Analog:** archive `src/stock_mcp/server.py` and `:src/stock_mcp/__main__.py` (exact structure; trim tool set, swap error model).

Archive server.py side-effect-import pattern to KEEP:
```python
# archive src/stock_mcp/server.py — KEEP this shape, drop graph_query/overview/related/health-add_note
from .tools.search import mcp  # re-export; import registers @mcp.tool
from .tools import (  # noqa: F401, E402 — side-effect registration
    events, filing, graph_query, health, notes, overview, portfolio, related,
)
```
**Change:** v2.0 imports only `filing, market, search, note, card, portfolio, briefing` (the 10 locked tools live across these 7 modules). Keep `_check_db_connection()` (archive `SELECT 1` fail-fast) but raise `DataBackendError`, not `StructuredError`.

Archive `__main__.py` to KEEP (swap error type + stderr-only logging per Pitfall 7):
```python
def main() -> None:
    load_dotenv(find_dotenv(usecwd=True))
    from .server import _check_db_connection, mcp
    try:
        _check_db_connection()
    except McpToolError as e:           # was StructuredError
        print(str(e), file=sys.stderr)  # stderr ONLY — stdout is JSON-RPC (Pitfall 7)
        sys.exit(1)
    mcp.run(transport="stdio")
```

---

### `src/mcp_v2/models.py` (Pydantic return models)

**Analog:** `src/cards/models.py` (exact — same Pydantic v2 discipline).

Copy the `ConfigDict(extra="forbid")` + `Field(...)` declaration style. Each return model MUST represent an empty state (D-01):
```python
# src/cards/models.py lines 36-54 — the pattern to replicate
class KeyClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str
    evidence_refs: list[str] = Field(default_factory=list)
    weight: Literal["HIGH", "MEDIUM", "LOW", "CONTEXT"]
    confidence: float = Field(ge=0, le=1)
```
**New models needed:** `FilingDetail` (incl. `injection_suspected: bool`, `injection_flags: list[str]`), `FilingHit`/`SearchResult(hits: list[SearchHit])` with `SearchHit(source_type, id_or_path, rrf_score, snippet, ...)`, `OhlcvRange(bars: list[OhlcvBar])`, `FlowRange(rows=[])`, `PeerView(metric, median: float|None, n: int)`, `NoteContent`, `CardView(found: bool, card: dict|None)`, `Briefing(found: bool, entries=[])`, and a `Portfolio` passthrough. Empty-state lives in `default_factory=list` / `found=False` / `median=None`. Re-use the `r"^[0-9]{6}$"` / `r"^[0-9]{8}$"` patterns from `DecisionCard` (models.py lines 79-80).

---

### `src/mcp_v2/injection.py` (leaf util, WRAP+FLAG)

**Analog:** archive `src/ingest/injection_defense.py` (exact — port the EN+KO `PATTERNS` table verbatim).

```python
# archive src/ingest/injection_defense.py — PATTERNS table (port verbatim) + detect
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EN_IGNORE_PREV",  re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|prompts|rules)", re.I)),
    ("FAKE_SYSTEM_TAG", re.compile(r"</?(?:system|assistant|user|instructions|prompt)\s*>", re.I)),
    ("DAN_MODE",        re.compile(r"\b(?:DAN\s*mode|jailbreak|developer\s+mode)\b", re.I)),
    ("ROLEPLAY_ADMIN",  re.compile(r"(?:role[-\s]?play\s+as|pretend\s+(?:you\s+are|to\s+be))\s+(?:admin|root|system)", re.I)),
    ("KO_IGNORE_PREV",  re.compile(r"이전\s*(?:지시|프롬프트)\s*무시")),
    ("KO_ADMIN_MODE",   re.compile(r"관리자\s*모드|시스템\s*프롬프트\s*출력")),
]
_SAFE_ATTR_RE = re.compile(r"^[A-Za-z0-9_-]+$")  # delimiter attr safety (info-disclosure guard)
```
**Change vs archive (D-03):** archive `is_adversarial()` GATED (skipped) adversarial content. v2.0 NEVER blocks/strips — `wrap_untrusted()` always wraps; `detect()` returns flags that the tool attaches to its return model metadata (`injection_suspected=True`). Drop `is_adversarial`/`trust_level` gating. Rename `detect_injection_patterns`→`detect` (or keep). Keep the `wrap_untrusted(body, source, ref_id)` attribute-validation guard (raises `ValueError` on bad attr — never echoes the offending value). Snapshot the pattern-ID list in a test (archive did; SC#5/D-03).

---

### `src/mcp_v2/retrieval.py` (RRF core, request-response)

**Analog:** archive `src/stock_mcp/search_core.py` (role-match — same RRF k=60 CTE; **retarget chunks/documents → whole-body filings/news/notes**, Veto #8).

The archive CTE to ADAPT (keep `_RRF_K=60`, the session GUC, the FULL OUTER JOIN fusion, NULL-filter casts):
```python
# archive src/stock_mcp/search_core.py — port these constants + CTE shape
_RRF_K = 60  # SC#4 LOCKED — do not parameterize away
_SESSION_SET_ITERATIVE_SCAN = sa.text("SET hnsw.iterative_scan = 'relaxed_order'")  # Pitfall 2 (D-13)

# NULL filter casts (Pitfall 3 — AmbiguousParameter without these):
_FILTER_WHERE = """
  AND (CAST(:corp_code AS char(8)) IS NULL OR d.corp_code = CAST(:corp_code AS char(8)))
  AND (CAST(:source    AS text)    IS NULL OR d.source    = CAST(:source    AS text))
  AND (CAST(:date_from AS date)    IS NULL OR d.first_seen_at >= CAST(:date_from AS date))
  AND (CAST(:date_to   AS date)    IS NULL OR d.first_seen_at <  CAST(:date_to   AS date))
"""
# fusion tail (port verbatim — sign-independent RRF):
#   SELECT COALESCE(dense.id, sparse.id) AS id,
#          COALESCE(1.0/(60 + dense.rk), 0) + COALESCE(1.0/(60 + sparse.rk), 0) AS rrf_score
#   FROM dense FULL OUTER JOIN sparse USING (id) ORDER BY rrf_score DESC LIMIT :top_k
```

**Changes vs archive:**
1. `chunks c JOIN documents d` → query `filings` / `news` / `notes` directly (each row IS one candidate — no chunk join, Veto #8). `c.embedding <=> CAST(:qvec AS vector)` → `f.body_embedding <=> CAST(:qvec AS halfvec)` (column is `halfvec(1024)`, not `vector`).
2. BM25: `'ix_chunks_bm25'::regclass` → per-table index name (`ix_filings_bm25` etc.). **Verify the vchord API surface (A1):** archive used `bm25_catalog.search_bm25query(...)` / `to_bm25query(...)` / `bm25_ops`; the migration 0002 in-tree (`src/db/migrations/versions/0002_phase03_chunking_columns.py`) confirms `search_bm25query` + `bm25_ops` were tested against the same `tensorchord/vchord-suite:pg17-latest` image — use that, not `<&>`, unless a Wave-0 spike says otherwise.
3. For "all narrative", run filings+news+notes candidate CTEs and UNION into one RRF, each carrying a `source_type` tag. SC#4: never touch ohlcv/macro_series/decision_cards.
4. Use `db.entity.resolve_entity` for ticker→corp_code (archive `build_filter_clause` already does — keep that, swap `StructuredError(INVALID_TICKER)` → `InvalidArgument`/`EntityNotFound`).
5. Snippet: RESEARCH §snippet recommends ±200-char match-window, fallback first-300-char head; wrap snippet via `injection.wrap_untrusted` (D-02 references-not-blobs: NO body_md in the hit).

---

### `src/mcp_v2/embedding.py` + `tokenizer.py` (leaf utils)

**Analogs:** archive `src/ingest/embedder.py` and `:src/ingest/tokenizer.py` (exact — port verbatim).

embedder.py to KEEP: lazy `SentenceTransformer("BAAI/bge-m3")` singleton + `@functools.lru_cache(maxsize=256) encode_query(q) -> tuple[float,...]` (returns tuple for hashability). tokenizer.py to KEEP: `mecab.MeCab()` + `_CONTENT_POS = {"NNG","NNP","SL","SN"}` + BLAKE2s-4byte → positive-int32 `tokenize_ko(text) -> list[int]` (SAME fn at index + query time). No changes needed — these are schema-agnostic leaves. Both depend on the re-added `ingest` dependency group.

---

### `src/mcp_v2/paths.py` (leaf util, file-I/O)

**Analog:** archive `src/stock_mcp/paths.py` `safe_join` (exact — convert to read-only variant).

```python
# archive safe_join — KEEP the resolve()+is_relative_to defense (symlink + .. safe)
def safe_join(repo_root: Path, user_path: str) -> Path:
    rr = repo_root.resolve()
    candidate = (rr / user_path).resolve()   # collapses '..' AND follows symlinks
    roots = _allowed_roots(repo_root)
    if not any(candidate == r or candidate.is_relative_to(r) for r in roots):
        raise StructuredError(ErrorCode.WRITE_FORBIDDEN, ...)
    return candidate
```
**Changes:** whitelist becomes `("notes/private/",)` only (drop `vault/notes/` — vault is deleted); raise `NotePathForbidden` (not `WRITE_FORBIDDEN`); add `candidate.is_file()` → `NoteNotFound` check (RESEARCH §get_note). Drop the write-oriented `resolve_path_alias` unless the planner wants the `journal/today` aliases (read-side may keep a read-only subset). Rename to `safe_resolve` per RESEARCH.

---

### `src/mcp_v2/tools/card.py` — `get_decision_card` (controller, CRUD read)

**Analog:** `src/cards/store.py` `get_active` (exact — wrap it; view is serialize-time exclude, Veto #13).

```python
# src/cards/store.py get_active returns a FULL typed DecisionCard (payload + body_md + status).
# Veto #13 view projection is a serialize-time exclude — NO re-query:
card = get_active(get_engine(), corp_code)
if card is None:
    return CardView(corp_code=corp_code, found=False)        # D-01 empty model, NOT an error
data = card.model_dump(mode="json", exclude={"body_md"})     # view="payload" default (Veto #13)
# view="both": card.model_dump(mode="json") then wrap body_md via injection.wrap_untrusted (D-03)
```
`_PAYLOAD_EXCLUDE = {"body_md","status","invalidation_reason"}` is the store convention (store.py line 64) — for the tool's payload view, exclude `{"body_md"}` at minimum. `get_active` returning `None` → empty model branch; bad corp_code shape → `InvalidArgument` (regex from `DecisionCard` models.py line 79).

---

### `src/mcp_v2/tools/filing.py` — `get_filing`, `search_filings` (controller, CRUD read)

**Analog:** `src/cards/store.py` (parameterized `text()` SQL + module-level constants) + `src/db/entity.py` (regex pre-filter + `resolve_entity`).

Replicate store.py's module-level `text()` constant + bind-param discipline (store.py lines 69-125). `get_filing(rcept_no)`: `SELECT ... body_md FROM filings WHERE rcept_no = :r` → whole `body_md` (Veto #8, no slicing), wrap via `injection.wrap_untrusted(body_md, "dart", rcept_no)`, attach `injection_suspected`. No row → `FilingNotFound`. `search_filings`: `... WHERE corp_code=:cc [AND event_type / filed_at filters] ORDER BY filed_at DESC LIMIT :limit` (D-04 default `limit=50`); metadata-only return (no injection wrap, no body). Validate corp_code regex (`entity.py` line 22) → `InvalidArgument`; resolve missing → `EntityNotFound`.

---

### `src/mcp_v2/tools/market.py` — `ohlcv_range`, `flow_range`, `peer_view` (controller, numeric)

**Analog:** `src/collectors/krx/db_writer.py` (`ohlcv` column set + parameterized SQL) + `src/db/entity.py` (ticker resolve) + RESEARCH §peer_view.

`ohlcv_range`/`flow_range`: `SELECT ... FROM ohlcv WHERE ticker=:t AND trade_date >= :from AND trade_date <= :to ORDER BY trade_date` — column names from db_writer.py `_UPSERT_SQL` (lines 37-48: open/high/low/close/volume/trading_value/foreign_net/inst_net/retail_net/short_volume/short_balance). D-04: `from_date`/`to_date` REQUIRED, no hard cap. Pure numeric → NO injection wrap (Veto #6). Empty → `bars=[]`/`rows=[]`.

`peer_view(corp_code, metric)`: **now full-scope (D-06).** Query the NEW `fundamentals` table:
```sql
-- RESEARCH §peer_view shape — replicate against the real fundamentals table (Cluster 3)
SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY fnd.per) AS median_per, count(*) AS n
FROM fundamentals fnd
JOIN entities e ON e.corp_code = fnd.corp_code
WHERE e.sector = (SELECT sector FROM entities WHERE corp_code = :corp_code)
  AND fnd.per IS NOT NULL
```
`entities.sector` exists (migration 0001 line 40). Return `PeerView(metric, median, n)`; no same-sector peers → `median=None, n=0` (D-01 empty model). Metric ∈ {per, pbr, roe}; bad metric → `InvalidArgument`.

---

### `src/mcp_v2/tools/note.py`, `portfolio.py`, `search.py`, `briefing.py` (controllers)

- **note.py** `get_note`: `paths.safe_resolve` (above) → `Path.read_text` → wrap content via `injection.wrap_untrusted(content, "note", path)` → `NoteContent` with `injection_suspected`. Disk read of `notes/private/` (D-05 keeps `get_note` disk-whitelist read-only even though hybrid_search now uses the `notes` table).
- **portfolio.py** `list_portfolio`: thin wrap of `src/shared/portfolio.py` `Portfolio.load(repo_root)` (portfolio.py lines 65-83). `PortfolioLoadError` → `DataBackendError`. Structured return (no injection wrap). Empty holdings/watchlist is a valid empty model.
- **search.py** `hybrid_search`: register on shared `mcp` instance (archive `tools/search.py` pattern), delegate to `retrieval.hybrid_search`, shape `SearchResult`. D-04 default `limit=10`. `source_filter` rejects ohlcv/macro/decision_cards (SC#4). Archive `_hits_to_models` field-projection helper is the model-build pattern.
- **briefing.py** `get_briefing`: RESEARCH §get_briefing — Phase 3 returns `Briefing(date, type, found=False, entries=[])` (D-01). Do NOT query/add a `report_type` column (Phase 5's migration). Bad `type` → `InvalidArgument`.

---

### `src/collectors/fundamentals/` (D-06 — service + DB-direct upsert)

**Analogs:** `src/collectors/krx/` (whole collector: `__init__.py` orchestration, `client.py` pykrx wrapper, `fetcher.py` tenacity retry, `db_writer.py` upsert) + `src/collectors/dart/financials.py` (ROE source).

**`client.py`** — replicate `src/collectors/krx/client.py` (lazy `from pykrx import stock`):
```python
# NEW — analog: krx/client.py get_ohlcv pattern
def get_market_fundamental(ticker: str, date_str: str) -> pd.DataFrame:
    from pykrx import stock
    return stock.get_market_fundamental_by_date(date_str, date_str, ticker)  # PER/PBR/EPS/BPS/DIV
```

**`fetcher.py`** — replicate `src/collectors/krx/fetcher.py` `@retry(...)` decorator + `_RETRYABLE_EXC` verbatim (lines 30-46).

**`db_writer.py`** — replicate `src/collectors/krx/db_writer.py` `upsert_ohlcv` EXACTLY (lines 30-207): `_TICKER_RE` pre-filter, module-level `_UPSERT_SQL = text(...)` with `ON CONFLICT (ticker, fdate) DO UPDATE`, `Literal["inserted","updated","skipped"]` return, COALESCE-preservation for late ROE fill-in. **Veto #6: fundamentals are typed NUMERIC columns (per/pbr/eps/bps/roe), never embedded.**

**`roe.py`** — replicate `src/collectors/dart/financials.py` `get_structured_financials` (lines 143-190): lazy `import dart_fss`, `_fs_extract` wrapper, `LINE_ITEM_SYNONYMS` for 당기순이익/자본총계, compute `roe = 당기순이익 / 자본총계`. **COLL-07: no LLM SDK imports in collectors/** (financials.py docstring lines 4-7).

**`__init__.py`** — replicate `src/collectors/krx/__init__.py` `collect_krx` (lines 118-233): `Portfolio.load(repo_root).scope_tickers()` for scope, per-ticker try/except isolation, `stats={total,inserted,updated,skipped,failed}`, `resolve_entity` before write (R-03 missing-entity), structured `_log.info("collector_run_complete", ...)` + `record_collector_run(engine, "fundamentals", ...)`.

---

### Notes-ingest job + embedding/tsv/bm25 backfill (D-05 — service, batch)

**Analogs:** `src/collectors/krx/__init__.py` orchestration + `src/shared/portfolio.py` disk read (`notes/private/`) + `src/collectors/dart/db_writer.py` narrative upsert (`body_md` whole-text, content_hash dedup) + archive `src/ingest/` (embed+tokenize backfill of `body_md`).

- **Notes ingest:** walk `notes/private/*.md` from disk (Path glob like `portfolio.py` line 73), upsert into the NEW `notes` table with the DART writer's narrative pattern (`src/collectors/dart/db_writer.py` lines 63-178 — `content_hash = sha256(normalize_body(body))`, `ON CONFLICT (path) DO UPDATE`, whole `content_md` TEXT, Veto #8 no chunking). Local-only: never git-committed (D-05).
- **Embedding/tsv/bm25 backfill:** for existing `filings`/`news` rows (and new `notes`) where `body_embedding`/`bm25_tokens`/`body_tsv` are NULL: `embedding.encode_query`-style batch embed (use `Embedder.encode` archive pattern), `tokenizer.tokenize_ko` → INT[], then a parameterized `UPDATE filings SET body_embedding=CAST(:vec AS halfvec), bm25_tokens=:toks WHERE rcept_no=:r` (store.py parameterized-`text()` discipline; `_format_vec` literal from archive search_core.py for the halfvec literal). `body_tsv` is GENERATED-or-`to_tsvector('simple', ...)` — **never `'korean'`** (Pitfall 1).

---

### `src/db/migrations/versions/0008_phase03_*.py` (migration)

**Analogs:** `0007_decision_cards.py` (overall structure: revision IDs, `op.create_table`, raw-SQL ALTER for special types, GENERATED tsvector, index creation) + `0002_phase03_chunking_columns.py` (the BM25 + HNSW index SQL — **this is the in-tree, image-tested version**).

From `0007` — table + revision skeleton + GENERATED tsvector (use `'simple'`, NOT `'korean'`, Pitfall 1):
```python
revision = "0008"; down_revision = "0007"
op.create_table("notes", sa.Column("path", sa.Text, primary_key=True), ...
    sa.Column("content_md", sa.Text, nullable=False),
    sa.Column("body_tsv", postgresql.TSVECTOR, nullable=True), ...)
op.execute("ALTER TABLE notes ADD COLUMN content_emb halfvec(1024)")  # 0006 raw-ALTER habit
```
From `0002` — the BM25 + HNSW index SQL to replicate on filings/news/notes (verified against `tensorchord/vchord-suite:pg17-latest`):
```python
# src/db/migrations/versions/0002_phase03_chunking_columns.py — port these
op.execute("CREATE EXTENSION IF NOT EXISTS vchord_bm25")
op.execute("ALTER TABLE filings ADD COLUMN bm25_tokens INT[] NULL")  # raw SQL — keeps implicit bm25vector cast
op.execute("CREATE INDEX ix_filings_embedding_hnsw ON filings USING hnsw (body_embedding halfvec_cosine_ops)")  # NOTE: halfvec_cosine_ops, NOT vector_cosine_ops (0002 used vector on chunks)
op.execute("CREATE INDEX ix_filings_bm25 ON filings USING bm25 "
           "(((bm25_tokens)::bm25_catalog.bm25vector) bm25_catalog.bm25_ops)")
```
**Tables to create:** `notes(path PK, corp_code FK, updated_at, content_md, content_hash, body_tsv, content_emb halfvec(1024), bm25_tokens INT[])` and `fundamentals(ticker, fdate, per NUMERIC, pbr NUMERIC, eps, bps, roe, corp_code FK, source, fetched_at, PK(ticker, fdate))`. **Columns to ADD:** `filings.bm25_tokens INT[]`, `news.bm25_tokens INT[]`, + BM25/HNSW indexes on filings/news (and notes). The `_HalfVec` ORM declarations go in `entity_models.py` (see below).

**Change vs 0002:** 0002 used `vector_cosine_ops` on `chunks.embedding vector(1024)`; Phase 1 columns are `halfvec(1024)` → use `halfvec_cosine_ops` and the `<=>` distance operator on halfvec. The dormant `chunks` table from 0002 is NOT searched — build the equivalent indexes on the whole-body tables.

---

### `src/db/entity_models.py` (ADD Fundamentals + Note ORM classes)

**Analog (in-file):** the existing `Filing` (lines 73-124) and `OHLCV` (lines 185-228) classes + `_HalfVec` UserDefinedType (lines 47-67).

Add `Note` modeling the new `notes` table (mirror `Filing`'s `body_md`/`body_tsv`/`body_embedding` shape — use `_HalfVec(1024)` for `content_emb`; whole `content_md` TEXT, Veto #8) and `Fundamentals` (mirror `OHLCV`'s pure-numeric typed columns, Veto #6 — `sa.Numeric` for per/pbr/eps/bps/roe, NO embedding column). Add `bm25_tokens = sa.Column(postgresql.ARRAY(sa.Integer), nullable=True)` to `Filing`/`News`/`Note`. ORM parity is enforced by `tests/db/test_migration_0008.py::test_orm_round_trip` (analog: existing `test_migration_0002.py`). DDL authority stays in the migration (entity_models.py docstring lines 7-19).

---

## Shared Patterns

### Parameterized `text()` SQL (Veto #7 — applies to ALL DB tools, db_writers, backfill, migration helpers)
**Source:** `src/cards/store.py` lines 67-125 (module-level `text()` constants, bind params only, NO f-string).
```python
_SELECT_ACTIVE_SQL = text("""SELECT payload, body_md, status ... WHERE corp_code = :cc ...""")
with engine.begin() as conn:
    row = conn.execute(_SELECT_ACTIVE_SQL, {"cc": corp_code}).first()
```
**Apply to:** every `src/mcp_v2/tools/*.py`, `retrieval.py`, `fundamentals/db_writer.py`, notes-ingest, backfill UPDATE. The SC#3 CI guard AST-checks that every `text()` arg is a constant/module-level name (RESEARCH §CI Guard).

### ASCII regex pre-filter before DB (V5 input validation)
**Source:** `src/db/entity.py` lines 22-23 + `src/cards/models.py` lines 79-80 + `src/shared/portfolio.py` line 21.
```python
_TICKER_RE = re.compile(r"^[0-9]{6}$")     # ASCII-only (str.isdigit accepts superscripts)
_CORP_CODE_RE = re.compile(r"^[0-9]{8}$")
```
**Apply to:** every tool arg + every db_writer that takes ticker/corp_code/rcept_no. Raise `InvalidArgument` (mcp tools) / `ValueError` (collectors) on mismatch — BEFORE touching the DB.

### Entity resolution (ticker→corp_code)
**Source:** `src/db/entity.py` `resolve_entity(engine, value, as_of=None)` (lines 33-96) — the ONLY place reading entity_aliases.
**Apply to:** `ohlcv_range`/`flow_range`/`search_filings`/`peer_view`/`hybrid_search` filter resolution, and every collector's pre-write missing-entity check. Returns `None` → `EntityNotFound` (tools) / `stats["failed"]` (collectors, R-03).

### Injection WRAP+FLAG (D-03, SC#5)
**Source:** `src/mcp_v2/injection.py` (ported from archive `src/ingest/injection_defense.py`).
**Apply to:** every narrative-returning tool — `get_filing` (body_md), `get_note` (content_md), `hybrid_search` (snippet), `get_decision_card` view="both" (body_md). NOT numeric tools (ohlcv/flow/peer) or structured fields.

### Collector orchestration + observability (Cluster 2)
**Source:** `src/collectors/krx/__init__.py` `collect_krx` (lines 118-233) + `src/shared/run_log.py` `record_collector_run` (lines 44-133).
**Apply to:** `fundamentals/__init__.py` and notes-ingest job — `Portfolio.load().scope_tickers()` scope, per-item try/except isolation, `{total,inserted,updated,skipped,failed}` stats, dual-sink (`_log.info("collector_run_complete")` + `record_collector_run`). **MODIFY** `run_log.py` `_ALLOWED_SOURCES` (line 39) + the `collector_runs` source CHECK (migration) if fundamentals/notes_ingest record runs.

### Empty-model vs typed-exception (D-01)
**Source:** RESEARCH §Pattern 2 + `src/cards/store.py` `get_active` returning `None` (no card) vs raising.
**Apply to:** every tool. Zero rows → model with empty collection / `found=False` / `median=None`. Genuine fault → `raise McpToolError` subclass.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `.mcp.json` (repo root) | config (live-service registration) | n/a | Deleted in shutdown; no in-tree example. Use RESEARCH A5 standard Claude Code MCP shape (`command`/`args`/`env` spawning `.venv` python `-m mcp_v2` with `DATABASE_URL`). Verify against current Claude Code MCP docs at planning time. |
| `tests/mcp_v2/test_no_run_sql_guard.py` | test (CI guard) | n/a | SC#3 registry + AST guard is genuinely new — no existing test does AST-walk of tool modules. Skeleton in RESEARCH §CI Guard (`mcp.get_tools().keys()` registry check + `ast`-walk asserting `text()` args are constants). Closest in-tree precedent: `tests/test_import_guard.py` (exists) for the CI fast-step shape, but the AST logic is new. |

> All other Phase-3 files have a strong in-tree or archive analog above. The `peer_view` fundamentals dependency (RESEARCH A4 flagged it as possibly empty) is RESOLVED by D-06 full-scope — the `fundamentals` table + collector are now in scope, so `peer_view` computes real medians.

## Metadata

**Analog search scope:** `src/mcp_v2/` (target, empty), `src/cards/`, `src/collectors/{krx,dart}/`, `src/db/` (engine, entity, entity_models, migrations 0001/0002/0006/0007), `src/shared/` (portfolio, run_log), `src/cli/`, and `git archive/llm-wiki-2026-04:src/{stock_mcp,ingest}/`.
**Files scanned:** ~22 in-tree + 8 archive.
**Pattern extraction date:** 2026-06-01
**Key open items for planner (from RESEARCH):** A1 vchord BM25 API surface (spike at Wave 0 — in-tree 0002 says `search_bm25query`/`bm25_ops`), A2 long-body dense embedding (head-truncate vs sibling chunk-view; BM25 carries Korean recall), A6 FastMCP 2.x `mask_error_details` + `get_tools()` accessor.
