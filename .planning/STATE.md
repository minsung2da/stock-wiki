---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: DB-direct redesign
status: ready_to_plan
stopped_at: Phase 05 complete (5/5) — ready to discuss Phase 6
last_updated: 2026-09-23T10:47:36Z
progress:
  total_phases: 9
  completed_phases: 5
  total_plans: 29
  completed_plans: 29
  percent: 56
---

# Project State

## Project Reference

See:

- `.planning/PROJECT.md` (v1.0 framing — to be refreshed in Phase 1)
- `.planning/ROADMAP.md` (v2.0 9-phase roadmap)
- `.planning/research/redesign-2026-05.md` (authoritative architecture criteria + research synthesis)
- `CLAUDE.md` (Hard Vetoes + tech stack + directory layout)

**v2.0 Core Value:** AI는 종목을 찍어주지 않는다. 매일 모은 evidence를 *근거 카드(decision_card)*
로 압축해 사람에게 제시하고, 검증된 paper-trade 실적이 있는 종목만 KIS 자동매매로 보조한다.

**Current focus:** Phase 6 — paper trade action layer

Last activity: 2026-09-23 - Completed quick task 260923-r1s: local read-only database explorer with 10 datasets, search, pagination and full record details. 12 isolated DB tests and live desktop/mobile browser checks passed. Running at http://127.0.0.1:8766.

## Current Position

Phase: 6
Plan: Not started

**05-01 (Wave 1) DONE:** migration 0009 applied to live DB (report_type/report_date, nullable
corp_code + partial CHECKs/index; alembic current==0009).
**05-02 (Wave 2) DONE:** the typed briefing STORE surface — `BriefingRow` model (SEPARATE from
DecisionCard, Veto #1/#4) + `cards.store.{save_briefing,get_briefing_row,list_cards_for_briefing,
get_daily_briefings_in_range}` + `invalidate()` invalidated_at stamp (OQ1 option a) +
`DecisionCard.invalidated_at`; shared ≥11-ticker `briefing_engine` fixture + `make_card` factory.
**05-03 (Wave 3) DONE:** deterministic LLM-free daily generator — classify_change (D-02/D-03) +
DICT-keyed `_priority_key` + 6-column render + `generate_daily_briefing` orchestrator; self-describing
payload; no-change short row (SC#6).
**05-04 (Wave 3) DONE:** `get_briefing` wired to `cards.store.get_briefing_row` — public type
daily/weekly → stored report_type; ISO-8601 date validation (ASVS V5) before the DB bind; returns
`entries` only (Veto #13, `Briefing` has no body_md field); no inline `text()` (SC#3 AST guard + 10-tool
registry green). Retired the Phase-3 honest-empty guard for DB-backed wired tests (SC#5). 139 mcp_v2
tests green.
**05-05 (Wave 4) DONE:** weekly roll-up — `src/briefing/weekly.py` `aggregate_net` (per-ticker NET
start/end diff over <=7 daily payload['entries'] flat dicts; intra-week flip-flops DROPPED D-07;
same-stance conviction move >= 0.10 retained; best-effort coverage {present,expected:7,missing_dates}
D-08) + `generate_weekly_briefing` (PRE-MATERIALIZES entries+source_reports into a weekly_briefing row;
reuses daily DICT-keyed `_priority_key` over flat dicts, no .card access; <=10, truncated). SC#4 proven
by `test_no_recompute`: delete source dailies AFTER generation → `get_briefing(weekly)` returns
byte-identical stored entries (pure SELECT, never recomputes). 40 briefing tests green.
**Phase 5 COMPLETE — all SC#1-6 delivered (05-01..05-05).** Next: verify-work / Phase 6 (paper-trade
action layer). Full-suite run had 4 pre-existing order/state-pollution + live-API failures unrelated to
this plan (logged in `05-briefing-renderer/deferred-items.md`).

### Phase 8 inputs (from the live run — recorded in 04-06-SUMMARY)

- **D-03 checksum FALSE-DROP bug (not a tolerance issue).** Live card kept 1/22 numeric facts (4.5%).
  Of the 21 drops, 3 are legit (ohlcv/flow/peer count=0, data genuinely absent); the other 18 are real
  filing numbers — 7/7 spot-checked were VERBATIM present in the source (e.g. `37,000,000`,
  `7,174,300,000,000`, `193,900`). Root cause is a matching-coverage gap, NOT the 0.5% tolerance:
  `checksum._verbatim_int_in_body` fallback is gated on `unit==""` (checksum.py:142), so any fact the
  Judge emits WITH a unit (`shares`/`KRW`/`employees`) skips it and drops unless the financial-span
  extractor tagged that exact span. Also `normalize_to_krw('KRW')==None` — the English `KRW` unit isn't
  in the KRW alias family (only `원`/`억`/`조원`/`KRW원`). Proven: `fact_supported(37000000,'shares')==False`
  but `fact_supported(37000000,'')==True` on the same body. **FIXED 2026-07-07 (commit 8afebf2):** the
  verbatim-digit fallback now runs for ANY integer-valued fact (Veto #3's literal rule) and bare `KRW`/`won`
  aliases to `KRW원`; non-integers still require value-equivalence and fabricated/derived numbers still drop.
  Empirical on the real Samsung body: originally-dropped facts now 19/21 kept (was 0/21); the 2 still dropped
  are non-integer derived dilution ratios (correct). +12 regression tests (real kept / fabricated dropped),
  54 checksum / 146 analysis tests green.

- Per-role wall-clock: Judge ~264s vs the 600s ceiling — tune to the observed distribution.
- **Collectors not yet run for price/flow/news/fundamentals** — only DART (217 runs) + macro (1) populated
  the DB, so ohlcv/news/fundamentals = 0 rows. That is why the live card reported "price/flow data absent"
  (correct behavior, not a bug). `stock collect krx` uses the pykrx whole-market snapshot API
  (`get_market_ohlcv_by_ticker`) which is currently broken (returns empty for all dates); the single-ticker
  history API (`get_market_ohlcv`) works and serves real data through 2026-07-08. Collector needs a
  portfolio.md (gitignored, absent here) for scope.

- **Demo (2026-07-07, orchestrator): seeded 61 REAL Samsung OHLCV rows** (2026-04-07..07-06, close
  ₩196,500→₩318,000) via the working single-ticker API into the `ohlcv` table, invalidated the prior
  card, and re-ran `analyze_ticker`. Result proves price data changes the card: price_ref (none→₩318,000)
  and conviction (0.095→0.23) both moved, stance stayed HOLD. Active Samsung card is now
  `card_005930_2026-07-06_f700c985` (the price-less `..077594ca` is invalidated/preserved). Flow/foreign/
  inst_net still NULL (the pykrx investor-flow endpoint is also broken here). This is a partial demo seed,
  not a full collector run.

### Repo-wide note (non-blocking)

- `mypy --strict` has ~30 pre-existing findings across the analysis package (mostly bare `dict`
  generics; `bundle.py` FilingHit attr = annotation imprecision on `hybrid_search` return type, NOT
  a runtime bug — live path builds the bundle fine). mypy is NOT gated by pre-commit or CI. Deferred
  to a dedicated cleanup pass. Executors 04-04/05/06 reported "mypy clean" but only checked their own
  files; the package-mode strict run surfaces the rest.

Phase 03 — VERIFIED (VERIFICATION.md PHASE GOAL ACHIEVED 2026-06-25).

Progress: [██████████] 100%

**Phase 3 closed (2026-06-07):** all 10 locked read-side MCP tools (get_filing,
search_filings, ohlcv_range, flow_range, peer_view, hybrid_search, get_note,
get_decision_card, list_portfolio, get_briefing) implemented + registered on the
FastMCP stdio server (`python -m mcp_v2`); SC#1 (10-tool registry), SC#2 (Pydantic
returns), SC#3 (no run_sql / AST guard enforced), SC#4 (hybrid_search RRF k=60
narrative-only), SC#5/D-02/D-03/D-04 all green.

## Phase 1 Outcomes (2026-05-29)

- 6 new domain tables: `filings`, `news`, `ohlcv`, `macro_series`, `events`, `collector_runs`
- Legacy `events` → `events_legacy` rename (pre-rename row count = 0, verified)
- Legacy `documents`/`chunks` dormant (Phase 3 may revisit narrative-search layer)
- 5 collectors INSERT directly to Postgres; `writer.py` modules deleted
- `--vault-root` flag eliminated; runtime guard prevents resurrection
- `shared/heartbeat.py` deleted; replaced by dual-sink (`shared/run_log.py` + structured stderr)
- Veto #6 (no numeric embedding) verified at schema layer
- Veto #8 (no DART pre-chunking) verified at 308KB body roundtrip
- Veto #9 (no Markdown vault) enforced via 3 layers: physical deletion + CI rglob fence + runtime guard
- ~150 tests pass across 9 plans; vertical E2E smoke (`collect macro` → 0 .md files) green

Open items (logged in `.planning/phases/01-collector-db-cutover/deferred-items.md`):

- DI-1: `tests/test_migration.py::test_events_jsonb_and_fk` still references pre-rename events shape (out of 01-09 scope)
- DI-2: intermittent flake on `test_collect_dart_writes_collector_runs_row` (couldn't reproduce in final state)

## Milestone Transition (v1.0 → v2.0)

**2026-04-26 ~ 2026-05-29**: LLM-wiki strategy shutdown + DB-direct redesign.

- v1.0 final state: 8/11 phases complete (Phase 1-7 + 07.1 done; Phase 8 in progress at plan 08-07)
- Shutdown commit: `daf3edf` on origin/main
- Archive: `git tag pre-llm-wiki-shutdown` / `git branch archive/llm-wiki-2026-04`
- Research seed: `.planning/research/redesign-2026-05.md`
- v2.0 roadmap published: 2026-05-29

## Performance Metrics

**Velocity:** (v2.0, baseline reset)

- Total plans completed: 8
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 (Collector DB cutover) | 0 | - | - |
| 2 (Decision card schema) | 0 | - | - |
| 3 (MCP tool surface) | 0 | - | - |
| 4 (Analysis runner) | 0 | - | - |
| 5 (Briefing renderer) | 0 | - | - |
| 6 (Paper-trade action) | 0 | - | - |
| 7 (Live trade) | 0 | - | - |
| 8 (Eval harness) | 0 | - | - |
| 9 (Ops hardening) | 0 | - | - |
| 02 | 3 | - | - |
| 05 | 5 | - | - |

**Recent Trend:** —

*v1.0 velocity history archived; see `git show archive/llm-wiki-2026-04:.planning/STATE.md` if needed.*
| Phase 02-decision-card-schema-storage P01 | 12 min | 3 tasks | 5 files |
| Phase 02-decision-card-schema-storage P02 | 11 min | 3 tasks | 5 files |
| Phase 02-decision-card-schema-storage P03 | 8 min | 2 tasks | 4 files |
| Phase 03 P03-01 | 22 min | 3 tasks | 9 files |
| Phase 03 P03-02 | 22 | 3 tasks | 11 files |
| Phase 03 P03-03 | 8 min | 3 tasks | 9 files |
| Phase 03 P03-04 | 14 min | 3 tasks | 10 files |
| Phase 03 P03-05 | 12 | 3 tasks | 12 files |
| Phase 03 P03-06 | 11 min | 3 tasks | 8 files |
| Phase 04 P01 | 12 min | 3 tasks | 8 files |
| Phase 04 P02 | 6 min | 3 tasks | 4 files |
| Phase 04 P03 | 18 min | 2 tasks | 2 files |
| Phase 04 P04 | 7 min | 3 tasks | 2 files |
| Phase 04 P05 | 11 min | 3 tasks | 6 files |
| Phase 04 P06 (partial: Tasks 1-2, Task 3 live checkpoint pending) | ~22 min | 2 tasks | 5 files |
| Phase 05 P01 | 5 min | 3 tasks | 4 files |
| Phase 05-briefing-renderer P02 | 15 min | 3 tasks tasks | 7 files files |
| Phase 05-briefing-renderer P03 | 20min | 3 tasks | 6 files |
| Phase 05-briefing-renderer P04 | 12min | 2 tasks | 3 files |
| Phase 05 P05 | 22min | 2 tasks | 3 files |

## Accumulated Context (v2.0)

### Decisions

v2.0 architecture decisions are locked in `.planning/research/redesign-2026-05.md` (sections 1-7) and
encoded as Hard Vetoes in `CLAUDE.md`. Recent decisions affecting Phase 1+:

- **Postgres is source of truth.** Markdown vault폐기. 사용자 thesis 메모만 `notes/private/`에 잔존.
- **Collectors write directly to typed Postgres tables** (Phase 1). `vault_root` 인자 + `heartbeat`
  stub 제거.

- **MCP 도구는 타입드 코드 API.** `run_sql` escape hatch 금지. (Phase 3)
- **decision_card schema가 분석 출력의 표준.** 만료일·assumptions·contradictions 강제. (Phase 2-4)
- **Auto-trade는 paper-shadow ≥30일 + Gates A-D 통과만.** Default disabled per-ticker. (Phase 6-7)
- **백테스트는 CPCV+embargo만.** Walk-forward 단독 금지. (Phase 8)

v1.0 decisions (~70개 누적, mostly LLM-wiki specific) — historical reference로 archive branch에 보존.
v2.0 redesign 시 lessons learned 중 carry-over는 위 항목 + `CLAUDE.md` 통해 통합됨.

- [Phase 02-decision-card-schema-storage]: decision_cards.body_tsv uses to_tsvector('simple',...) GENERATED STORED; PG17 lacks 'korean' config (Pitfall #1) — SC#6 is an explicit fallback search; Korean morphology stays in the Python mecab-ko/VectorChord-BM25 path
- [Phase 02-decision-card-schema-storage]: DecisionCard declared on the shared entity_models.Base (single Base) — Keeps ORM round-trip parity simple (RESEARCH A3); required widening test_migration_0006 metadata-set assertion to 7 tables
- [Phase 02-decision-card-schema-storage]: DecisionCard SC#5 hard veto enforced by field declarations only (non-Optional expires_at + assumptions min_length=1), no @model_validator — CONTEXT 'leave shape to the type system' + Veto #2; ValidationError fires at the model boundary
- [Phase 02-decision-card-schema-storage]: Added optional invalidation_reason field to DecisionCard (not in §3 YAML) — redesign §4 payload field; Plan 03 invalidate() writes it into payload JSONB so extra='forbid' reconstruct must accept it; adds no DB column (SC#1 untouched)
- [Phase 02-decision-card-schema-storage]: src/cards/store.py: 4 typed SC#4 CRUD helpers (save_card/get_active/walk_supersedes/invalidate), atomic single-txn supersession, jsonb_set invalidation reason in payload (OQ-1, no new column); no run_sql escape hatch (Veto #7) — Phase 3 MCP get_decision_card + Phase 4 analyze_ticker call this storage API; supersession must be atomic, all SQL parameterized, get_active returns full typed DecisionCard so view=payload|both is a serialize-time exclude (Veto #13)
- [Phase 02-decision-card-schema-storage]: Added optional status: str|None=None to DecisionCard (Rule 2) so invalidate/get_active/walk return cards surfacing the DB lifecycle status; merged in at reconstruct, defaults None (SC#3 round-trip unaffected, no new DB column) — Plan 02-03 acceptance criteria require invalidate() to return a card with .status=='invalidated'; status is a DB column not §3 payload, mirrors the existing optional invalidation_reason precedent
- [Phase ?]: [Phase 03-01]: fastmcp pinned 2.x (>=2.11,<3.0, 2.14.7 installed) per SC#1; mcp + ingest dep groups re-added; CI uv sync gap closed
- [Phase ?]: [Phase 03-01]: migration 0008 — notes (Veto #8 whole content_md + halfvec content_emb + bm25_tokens) + fundamentals (Veto #6 pure numeric, no embedding); BM25 (bm25_catalog.bm25_ops) + HNSW (halfvec_cosine_ops) indexes on filings/news/notes; APPLIED to live DB (alembic current==0008)
- [Phase ?]: [Phase 03-01]: Plan 03-01 is SINGLE OWNER of collector_runs.source CHECK widening + run_log._ALLOWED_SOURCES (7 sources incl fundamentals/notes_ingest); Plans 02/05 only call record_collector_run
- [Phase ?]: [Phase 03-02]: bge-m3 embedder + mecab-ko tokenizer ported to src/mcp_v2/ as siblings (importable by the notes-ingest backfill outside the MCP server); torch import lazy inside Embedder.__init__ (version constant imports torch-free)
- [Phase ?]: [Phase 03-02]: notes-ingest (ingest_notes) loads notes/private/**/*.md into the notes table (whole content_md, sha256 dedup, idempotent skip on unchanged; portfolio.md excluded); backfill_narrative fills NULL filings/news body_embedding/bm25_tokens/body_tsv (D-05 -> SC#4 full narrative coverage)
- [Phase ?]: [Phase 03-02]: SC#3 run_sql guard — AST layer ENFORCED (every text() arg is a string constant or module-level name) over src/mcp_v2; registry layer (==10 locked names, no run_sql/execute_sql/raw_sql/query) skip-tolerant until 03-06; get_tools() is a coroutine in fastmcp 2.14.7 (awaited via asyncio.run)
- [Phase 03-03]: Shared FastMCP instance lives in src/mcp_v2/_mcp.py (not server.py) to break the server<->tool-module import cycle; tool plans import 'from mcp_v2._mcp import mcp'
- [Phase 03-03]: D-01 leaf layer: McpToolError(ToolError) hierarchy raised on faults + 12 empty-able Pydantic return models (extra='forbid'); mask_error_details=True VERIFIED on fastmcp 2.14.7 (keeps ToolError messages, masks other bugs)
- [Phase 03-03]: injection.py WRAP+FLAG (D-03/SC#5): PATTERNS ported verbatim (6 ids) + detect() + wrap_untrusted() <untrusted> XML delimiter, never block/strip; archive is_adversarial/trust_level gate dropped; _SAFE_ATTR widened to allow dot/colon provenance ids
- [Phase 03-03]: paths.safe_resolve read-only whitelist = ('notes/private/',) only (vault dropped, Veto #9); Path.resolve()+is_relative_to symlink/.. safe; NotePathForbidden/NoteNotFound (V12)
- [Phase ?]: [Phase 03-04]: 6 read-side tools registered via mcp.tool(...)(fn) CALL form, not @mcp.tool decoration — the decorator yields a non-callable FunctionTool; call form keeps tools plain callables for in-process callers while still registering on the shared mcp
- [Phase ?]: [Phase 03-04]: get_filing whole body_md (Veto #8); get_decision_card view=payload serialize-time exclude (Veto #13); all narrative bodies WRAP+FLAG (D-03); search_filings NULL-cast guards keep one parameterized text() (SC#3); get_briefing honest empty model (no report_type)
- [Phase ?]: 03-05: fundamentals collector (pykrx PER/PBR/EPS/BPS + dart-fss ROE) DB-direct to typed NUMERIC fundamentals table (Veto #6); peer_view computes real same-sector percentile_cont(0.5) median (D-06)
- [Phase 03-06]: hybrid_search RRF k=60 fuses pgvector HNSW (halfvec <=>) + VectorChord-BM25 (search_bm25query — verified the live tensorchord/vchord-suite:pg17-latest exposes search_bm25query/to_bm25query, NOT the <&> operator; A1 resolved) over WHOLE-body filings/news/notes (Veto #8); k=60 is an inline SQL literal AND _RRF_K constant (never a bind, SC#4); SET hnsw.iterative_scan='relaxed_order' per session; NULL-cast filter guards
- [Phase 03-06]: hybrid_search returns references+snippet only (D-02 — SearchHit has no body_md field), default top-10 (D-04); snippet = ±200 match-window (300-char head fallback), wrapped+flagged (D-03/SC#5); forbidden numeric sources (ohlcv/macro_series/decision_cards) rejected at BOTH the tool boundary AND the retrieval layer (SC#4, Veto #6)
- [Phase 03-06]: FastMCP server aggregation = _mcp.py (shared instance) + server.py (side-effect-imports 7 tool modules → 10 locked tools, SC#1; _check_db_connection SELECT 1 → DataBackendError) + __main__.py (python -m mcp_v2 stdio boot, stderr-only diagnostics — Pitfall 7); the SC#3 registry guard flipped from skip to ENFORCED (==10 names, no run_sql). Phase 03 CLOSED.
- [Phase ?]: [Phase 04-01]: DecisionCard.warnings optional payload field (Field(default_factory=list)) — D-03 dropped-fact home; rides payload JSONB (not in _PAYLOAD_EXCLUDE), zero DB migration, §3 round-trip unaffected
- [Phase ?]: [Phase 04-01]: src/analysis/checksum.py D-03 value-equivalence (relative tol 0.5%) reusing shared.units.normalize_to_krw + number_extraction; KRW-family→KRW원 canonical, others raw scalar; unverifiable facts dropped into warnings (Veto #1/#4). Optional SANITY_RULES gate skipped (English fact keys won't match — YAGNI)
- [Phase ?]: [Phase 04-01]: CI import guard GUARDED_DIRS += src/analysis (D-01 Max-only Veto); 'live' pytest marker registered (opt-in real claude CLI, deselect by default)
- [Phase 04-02]: src/analysis/roles.py leaf constants — ROLE_SYSTEM_PROMPTS (bull/bear/judge encode Veto #1 no-price-prediction + <untrusted>=data injection control + Veto #3/#5) + ROLE_SCHEMAS inline JSON-Schema dicts (enum stance/weight, additionalProperties:false); Judge schema OMITS conviction (rubric layer computes it, Veto #4); prompt_for/schema_for KeyError on unknown; acyclic (no subagents/runner import)
- [Phase 04-03]: src/analysis/bundle.py — EvidenceBundle (Pydantic extra='forbid', reuses mcp_v2.models types) + build_bundle(engine, corp_code, as_of, *, portfolio_note_path) pre-fetches ALL evidence ONCE via in-process MCP tools (D-02); search_filings(−180d)→top-5 get_filing whole bodies (Veto #8), ohlcv(−90d)/flow(−30d)/peer_view×3 (Veto #5/#6), hybrid_search(name+catalyst,−30d)→filing/note full-body re-fetch (deduped), get_note only if portfolio_note_path given (only-if-held policy lifted to 04-06 runner). to_stdin: deterministic, <untrusted> delimiters preserved verbatim (D-03), 100K char cap drops lowest-weight WHOLE bodies never mid-body (T-04-08); no run_sql/text() (Veto #7). Window/cap constants [ASSUMED] (Discretion #3), tune Phase 8
- [Phase 04-02]: src/analysis/rubric.py — score_to_conviction = clamp(Σwᵢ·scoreᵢ/(10·Σwᵢ),0,1) with contradiction_penalty NEGATIVE (denom=10·Σall=10; all-10→0.80, max-positive/no-penalty→0.90); Veto #5 HARD CAP in Python (0.79 pin) when raw≥0.8 without ≥2 HIGH/MEDIUM refs across ≥2 CORROBORATING_FAMILIES (DART/KRX/macro/news/user_thesis — sentiment excluded → sentiment-only never 0.8); derive_stance = STANCE_TABLE[(net-bucket, held)] + sign guard (BUY/ADD→HOLD when fundamentals_sign<0 AND catalyst_sign<0); weights/table [ASSUMED], tune Phase 8
- [Phase ?]: [Phase 04-04]: analysis.gate.decide — deterministic no-LLM D-04 stance gate (FULL vs REFRESH + all fired reasons); triggers = first-run/new-filing/>=7% close-to-close or 3x vol/2sigma flow/near-expiry D-7/safety-net N=14d/assumption-break; thresholds [ASSUMED] module constants (Discretion #5, tune Phase 8); imports nothing from analysis.subagents/runner so REFRESH can never reach the LLM (T-04-11)
- [Phase ?]: [Phase 04-04]: lightweight_refresh PRESERVES generated_at (safety-net clock counts from the last FULL debate, not each cheap refresh) and NEVER extends expires_at (T-04-10); rebuilt through DecisionCard.model_validate (Veto #2); Escalate sentinel on material shift (new mid-refresh filing OR HIGH-weight claim lost evidence), non-HIGH unresolved refs -> warnings
- [Phase 04-05]: D-01 DebateBackend seam: ClaudeCliBackend spawns headless 'claude -p' via patchable _spawn_claude (mirrors fetcher._http_get), evidence on stdin (T-04-13), --strict-mcp-config + never --bare, reads structured_output not result; SubAgentError(permanent auth/non-zero/bad-envelope) vs SubAgentRetryableError(overload/rate_limit/timeout) with exactly one retry; system_prompt+schema are PARAMS so subagents.py imports no roles.py (leaf); run_bull_bear = parallel-blind helper — SC#2 mechanics + Max-only Veto: the ONLY path to a model is the CLI subprocess; the mockable seam keeps the default suite quota-free
- [Phase 04-05]: SC#7 cost capture (cost.py): StageCost + capture_cost extracts total_cost_usd/duration_ms/usage token subset/modelUsage model from the claude -p JSON envelope (defensive on missing keys); emit_cost writes ONE structured stderr line and NEVER reuses record_collector_run (its 7-source CHECK excludes analysis) nor raises on a partial envelope; FakeDebateBackend (canned per-role structured_output + .calls recorder, zero subprocess) is the seam the whole default suite uses — SC#7 Phase-9 quota input via structured stderr (RESEARCH #6); deep_work_rules: default suite never spawns the live CLI
- [Phase 04-06]: analysis.runner.analyze_ticker composite orchestrator (Tasks 1-2 done; Task 3 = blocking live-CLI checkpoint PENDING, orchestrator-owned). gate.decide → REFRESH (lightweight_refresh, backend NEVER called, SC#6) | FULL (build_bundle → run_bull_bear parallel-blind → Judge over bundle+bull+bear, SC#2 → checksum_facts drops unverifiable numbers into card.warnings, SC#3 → score_to_conviction, Veto #4/#5 → derive_stance from mean-claim-confidence net + rubric fundamentals/catalyst signs + currently_held, RESEARCH Disc #1). Conviction comes from the rubric (Judge schema OMITS it); stance is DERIVED (not taken from Judge) so both are decomposable. Card construction enforces Veto #2 = SC#4 (assumption-less/untimed Judge → ValidationError, retry judge ONCE then fail loudly, Disc #2). Empty contradictions logs a warning (SC#5). Per-stage cost emitted for bundle+bull+bear+judge (SC#7). Atomic supersession via store.save_card(supersedes=prior.card_id) (SC#1). currently_held/portfolio_note_path=None [ASSUMED] until Phase 6 wires portfolio membership. No anthropic/openai import (D-01, import guard green). 126 quota-free tests pass; live proof deferred to Task 3 checkpoint
- [Phase ?]: [Phase 05-01]: migration 0009 — decision_cards gains report_type TEXT + report_date DATE (nullable); corp_code DROP NOT NULL guarded by partial CHECK ck_decision_cards_corp_or_report (analysis-card FK invariant preserved, briefing rows may have NULL corp); ck_decision_cards_report_type enumerates daily_briefing/weekly_briefing; partial ix_decision_cards_report (report_type,report_date) WHERE report_type IS NOT NULL; downgrade DELETEs briefing rows before restoring NOT NULL; APPLIED to live DB (alembic current==0009)
- [Phase 05-briefing-renderer]: [Phase 05-02]: BriefingRow is a SEPARATE Pydantic model (extra='forbid'), never extends DecisionCard (Veto #1/#4 — no invented stance/conviction); cards.store gains save_briefing (NULL-corp write path, no supersede) + get_briefing_row + list_cards_for_briefing (BriefingCandidates NamedTuple: newly-generated/expiring/invalidated, KST ::date, excludes report_type rows) + get_daily_briefings_in_range; invalidate() nested jsonb_set stamps invalidated_at (OQ1 option a, no column) + DecisionCard.invalidated_at optional field; briefing payload is self-describing so get_briefing_row reconstructs scalars from it
- [Phase ?]: [Phase 05-03]: daily briefing = deterministic LLM-free digest — classify_change diffs stance-flip/contradiction-delta/first-card(>=0.8) vs the D-02 supersession-chain baseline; build_entry emits the LOCKED flat entry-dict and _priority_key is DICT-keyed (held_rank, event_class_rank, -conviction) with NO .card access so 05-05 weekly reuses it unchanged over payload[entries]; 제안 = stance+conviction only (Veto #1), Why not = top contradiction (Veto #3)
- [Phase ?]: [Phase 05-03]: daily payload is SELF-DESCRIBING (card_id/report_type/report_date/generated_at/as_of/expires_at as ISO + entries[]) — the plan's literal {entries, generated_for} would KeyError in store.get_briefing_row; added the scalar keys to honor the 05-02 reconstruction contract (Rule 2). SC#6 no-change day still writes a real row
- [Phase ?]: [Phase 05-04]: get_briefing WIRED — delegates the SELECT to cards.store.get_briefing_row (no inline text() in src/mcp_v2, SC#3 AST guard + 10-tool registry green); public type daily/weekly maps to stored report_type daily_briefing/weekly_briefing; date validated via `from datetime import date as _date` + _date.fromisoformat before the report_date bind (ASVS V5 — literal `date.fromisoformat(date)` would hit str.fromisoformat since the `date` param shadows the class); returns entries ONLY (Briefing has no body_md field, Veto #13 by construction, test_no_body_leak); empty DB -> found=False (D-01). Phase-3 honest-empty guard (found=False daily/weekly + report_type-absence AST test) retired for DB-backed test_briefing_wired.py (EXPECTED swap); bad-type no-DB guard kept (SC#5)
- [Phase ?]: [Phase 05-05]: weekly roll-up — aggregate_net computes per-ticker NET change (start vs end stance+conviction) over <=7 daily payload['entries'] flat dicts; intra-week flip-flops net to no-change and DROPPED (D-07), same-stance conviction move >= _CONVICTION_DELTA(0.10) retained; best-effort coverage {present,expected:7,missing_dates} (D-08). generate_weekly_briefing PRE-MATERIALIZES entries+source_reports into a weekly_briefing row; get_briefing(weekly) is a pure SELECT that never recomputes — test_no_recompute deletes source dailies then asserts byte-identical entries (SC#4). Reuses daily DICT-keyed _priority_key over flat dicts (no .card access). Phase 5 COMPLETE.

### Lessons Carried Over from v1.0

(v1.0 phase 진행 중 학습한 것 중 v2.0에서도 유효한 것)

- **CPython 3.12 + uv** — Python 3.13은 ML deps 안정성 부족
- **Postgres 17 + pgvector 0.8 (`halfvec`) + VectorChord-BM25** — testcontainer parity 위해 마이그
  레이션 안에서 `CREATE EXTENSION` 실행

- **psycopg3 driver** (`postgresql+psycopg://`) — testcontainers URL normalization 픽스처 경계에서
- **`corp_code` (DART 8-digit)가 canonical entity PK** — KRX 6-digit ticker 재활용 위험
- **Alembic `target_metadata=None`** — 손으로 작성한 마이그레이션만, autogenerate X
- **Content-hash dedup** (sha256) — primitive로만, 보안 아님
- **mecab-ko 한국어 tokenizer 전처리** — VectorChord-BM25는 whitespace tokenizer로 동작, 한국어
  복합어는 Python에서 사전 토큰화 필수

- **Half-open temporal interval `[valid_from, valid_to)` + depth<20 recursive CTE 가드** — entity
  history walk

- **dart-fss의 attachment parsing** — Open DART API가 노출 안 하는 항목 (linked-note financials)
  커버

- **CI guard: collectors/는 `anthropic`/`openai` import 금지** — Sonnet은 Claude Code 세션을 통해서만
  접근. (이 가드는 Phase 1 재작성 시 다시 추가 필요 — `tests/test_import_guard.py` 이미 잔존)

### Pending Todos

- `/gsd:plan-phase 1` 실행 → Phase 1 plan 산출
- Phase 1 plan 완성 후 PROJECT.md를 v2.0 framing으로 업데이트
- (선택) `.planning/phases/01-08, 07.1, 10` 디렉토리를 `.planning/archive/v1.0/`로 이동 — 현재 그대로 두고
  ROADMAP의 v1.0 섹션에서 명시적으로 historical reference라 표시

### Blockers/Concerns

- **Phase 1 우선 결정 필요**: Phase 4 (analysis runner)에서 Sonnet sub-agent를 어떻게 spawn할지 —
  Claude Code session 내 Task tool? 별도 Claude Schedule routine? quota 영향 측정 필요. Phase 4 plan 단계에서 확정.

- **KIS API 모의 환경 접근권**: Phase 6 시작 전 모의투자 계정 발급 및 API 키 확보 필요. KIS 키는
  Phase 4 기준 `.env`에 없음(DART/ECOS/FRED/GitHub/DB만) + KIS 코드 0건 — greenfield. **결정 노트:**
  Phase 6에서 KIS를 자동매매뿐 아니라 *숫자형 시장데이터(시세/수급/재무비율)의 주 소스*로 쓸지 검토
  (pykrx 스크래핑 취약성 — Phase 4에서 KRX 수급/fundamental 엔드포인트 빈값 목격 → SK하이닉스 카드
  수급/peer 부재의 원인). DART 공시원문/뉴스/매크로는 KIS 대체 불가 → 유지. 데이터 수집을 매매계좌와
  디커플링(Veto #10) + pykrx/FDR 폴백. 상세는 ROADMAP Phase 6 "Design consideration" 참조.

- **`notes/private/portfolio.md` schema 미정**: Phase 1에서 entity seed + Phase 6에서 auto_trade_enabled
  토글까지 사용. 한 번에 결정 vs 점진 진화 — Phase 1 plan에서 결정.

### Quick Tasks Completed

v1.0의 7개 quick task는 archive branch에 보존. v2.0 quick task는 새로 누적.

| # | Description | Date | Commit | Status | Directory |
|---|-------------|------|--------|--------|-----------|
| fast-260923-company-names | Show canonical company names beside ticker/corporation codes in explorer lists and details | 2026-09-23 | 5bd2949 | Browser verified: Samsung list/detail, multi-ticker mapping, unknown fallback, price list | src/db/explorer.html |
| 260923-r1s | Local read-only DB explorer: inventory, keyword/ticker/date filters, pagination, full details | 2026-09-23 | 7b691ee | 12 tests pass; live DB, desktop/mobile browser, ruff and mypy verified | [260923-r1s](./quick/260923-r1s-build-local-read-only-database-explorer-/) |
| 260923-qis | Complete default collection, KST-day news, DIV/DPS persistence, retire KIND | 2026-09-23 | 65b1e1b | 125 non-DB tests passed; follow-up 77 tests passed including DB; migration 0010 applied | [260923-qis](./quick/260923-qis-complete-recurring-collection-fundamenta/) |
| 260628-mh9 | Fix two DART collector bugs (alphanumeric KRX tickers `^[0-9A-Z]{6}$`; fetch_body retries OpenDART throttle status 020/800) | 2026-06-28 | d4d249e, 2bbe71b | Done (190 tests pass) | [260628-mh9-...](./quick/260628-mh9-fix-two-dart-collector-bugs-alphanumeric/) |
| 260628-n8d | Widen ticker regex `^[0-9A-Z]{6}$` across read/analysis/shared layers (cards/mcp_v2/portfolio/frontmatter) — end-to-end alphanumeric ticker consistency | 2026-06-28 | c59d276, 48c183f | Done (211 pass/2 skip) | [260628-n8d-...](./quick/260628-n8d-widen-ticker-regex-to-alphanumeric-acros/) |

## Session Continuity

Last session: 2026-07-16T14:07:37.749Z
Stopped at: Completed 05-05-PLAN.md (Phase 5 briefing-renderer COMPLETE)
Resume file: None
