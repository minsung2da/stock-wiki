# Redesign Seed — Post-LLM-Wiki-Shutdown Direction

**Date:** 2026-05-28
**Status:** Research synthesis, not yet a phase. To be promoted via `/gsd:new-milestone`.
**Predecessor:** `pre-llm-wiki-shutdown` tag / `archive/llm-wiki-2026-04` branch.

This memo synthesizes three parallel research investigations (data shape, analysis methodology, report format) into one architecture seed for the redesigned scope per the user's architecture sketch (collector → DB → refinement → analysis → result DB → action / report).

The single most important finding (Q2): **"AI picks stocks" is empirically broken.** The defensible product is **"AI compresses a 100-ticker watchlist into evidence-linked, time-bounded decision cards so the human decides faster with discipline."** Every section below serves this framing.

---

## 1. Architecture (revised)

```
주식 API/뉴스/리포트
        │
        ▼
┌──────────────┐    1. 수집 (schedule)
│  collector   │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────┐    2. 저장
│  Postgres 17 (primary truth)                 │
│  ├─ entities, ohlcv, filings, news,          │
│  │  events, flows, macro_series              │
│  └─ pgvector + VectorChord-BM25              │
│     (narrative columns only)                 │
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐    3. 정제 (refinement)
│  Typed MCP tools (code-execution pattern)    │
│  - get_filing, search_filings,               │
│  - ohlcv_range, flow_range, peer_view        │
│  - hybrid_search (narrative-only)            │
│  - get_note (user thesis from disk)          │
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐    4. 분석 (analysis)
│  Claude Sonnet 4.x (3-role rubric debate)    │
│  → emits `decision_card`                     │
│  - rubric scoring (Bull/Bear/Judge)          │
│  - evidence weights + contradiction block    │
│  - assumption ledger + expiry                │
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐    5. 결과 저장
│  reports table (Postgres)                    │
│  - frontmatter JSONB (machine view)          │
│  - body_md (human view)                      │
│  - supersedes / superseded_by                │
└──────┬───────────────────────────────────────┘
       │
       ├──────► 6. Action layer
       │       - deterministic gates A–D
       │       - paper-trade shadow ≥30d
       │       - human kill-switch
       │       └─► 7-1. KIS Open API
       │
       └──────► 7-2. Daily/Weekly briefing
               (top-N changes only)
                  │
                  └─► review/evaluate loop
                      (re-checks assumptions
                       against fresh data)
```

Key shift vs prior LLM-wiki: **Postgres is now the source of truth; Markdown is not.** Vault is gone. Vector search is reserved for narrative (DART body, news, thesis notes), not for numeric or relational queries.

---

## 2. Q1 — Data Refinement Shape

### Recommendation: structured-first hybrid

| Shape | Verdict |
|---|---|
| Pure vector | ❌ — ~80% of decision questions are numeric/relational; vector degrades them |
| Markdown wiki (Karpathy) | ❌ — known ceiling ~100K tokens, single-user manual curation; fits thesis notes only |
| Pure structured SQL | ⚠ — perfect for numbers, blind to narrative |
| Knowledge graph | ⚠ — useful for peer/supply hops but too heavy as primary |
| **Hybrid: structured DB + vector for narrative only** | ✅ |

### Why hybrid wins (specific to this project)

1. **~80% of Korean stock decision questions are numeric/relational** ("외국인 순매수 상위", "최근 8분기 영업이익률", "유상증자 공시 + 시총 1천억 미만") — collapse to SQL.
2. **Anthropic's Nov 2025 "Code Execution with MCP" guidance** (98.7% token reduction) explicitly says: expose MCP servers as code APIs returning *references*, not blobs.
3. **Long-context Claude (200K)** collapses the wiki/RAG tradeoff for narrative — once the right 3–5 DART filings are retrieved by ID, dump full text.
4. **FinAI Data Assistant (arXiv 2510.14162)**: function-calling against structured DB beat text-to-SQL at 100% completion.

### Schema sketch

```sql
-- Hub: one row per listed corp
entities(
  corp_code   TEXT PRIMARY KEY,   -- DART canonical, stable through 종목코드 변경
  ticker      TEXT,               -- 6-digit KRX, may recycle
  name_ko     TEXT,
  market      TEXT,               -- KOSPI | KOSDAQ | KONEX
  sector      TEXT,
  valid_from  DATE,
  valid_to    DATE NULL
);

-- DART filings (events)
filings(
  rcept_no    TEXT PRIMARY KEY,
  corp_code   TEXT REFERENCES entities,
  filed_at    TIMESTAMPTZ,
  report_nm   TEXT,
  event_type  TEXT,               -- 분류 (earnings/m_and_a/regulatory/...)
  derived     JSONB,              -- LLM-extracted facts (post-validated)
  body_md     TEXT,
  body_tsv    tsvector,
  body_emb    halfvec(1024)       -- bge-m3
);

-- News (same shape, dedup on url_hash)
news(
  id          BIGSERIAL PRIMARY KEY,
  url_hash    TEXT UNIQUE,
  corp_code   TEXT NULL REFERENCES entities,
  published_at TIMESTAMPTZ,
  title       TEXT,
  source      TEXT,               -- 한경 / 매경 / 연합 / ...
  body_md     TEXT,
  body_tsv    tsvector,
  body_emb    halfvec(1024)
);

-- KRX daily snapshot — no text, no embedding, just numbers
ohlcv(
  ticker      TEXT,
  trade_date  DATE,
  open        NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC,
  volume      BIGINT, trading_value BIGINT,
  foreign_net BIGINT, inst_net BIGINT, short_volume BIGINT,
  PRIMARY KEY (ticker, trade_date)
);

-- Macro indicators (ECOS/FRED)
macro_series(
  series_id   TEXT,
  obs_date    DATE,
  value       NUMERIC,
  unit        TEXT,
  PRIMARY KEY (series_id, obs_date)
);

-- User thesis notes (only Markdown survivor — on disk, gitignored)
-- Stored at notes/private/thesis-{ticker}.md
-- DB-side row points at path + holds embedding for search
notes(
  path        TEXT PRIMARY KEY,
  corp_code   TEXT NULL REFERENCES entities,
  updated_at  TIMESTAMPTZ,
  content_md  TEXT,
  content_emb halfvec(1024)
);

-- Decision cards (analysis output, see §3)
decision_cards(
  card_id     TEXT PRIMARY KEY,
  corp_code   TEXT REFERENCES entities,
  ticker      TEXT,
  generated_at TIMESTAMPTZ,
  as_of       TIMESTAMPTZ,        -- data cutoff
  payload     JSONB,              -- full structured decision (schema below)
  body_md     TEXT,               -- human render
  status      TEXT,               -- active | superseded | invalidated
  supersedes  TEXT REFERENCES decision_cards,
  superseded_by TEXT REFERENCES decision_cards,
  expires_at  TIMESTAMPTZ
);
```

### MCP tool surface (replacing the old `search_vault`)

| Tool | Purpose |
|---|---|
| `get_filing(rcept_no)` | One DART filing, full body |
| `search_filings(corp_code, event_type, since, until)` | Structured filter, ranked by `filed_at` |
| `ohlcv_range(ticker, from, to)` | Numeric, no narrative |
| `flow_range(ticker, from, to)` | 외국인/기관/공매도 |
| `peer_view(corp_code, metric)` | 동종업종 median PER/PBR/ROE |
| `hybrid_search(query, filters)` | RRF pgvector + BM25, narrative only |
| `get_note(path)` | Read user thesis from `notes/private/` |
| `get_decision_card(corp_code, latest=true)` | Returns frontmatter by default |
| `list_portfolio()` | Reads `notes/private/portfolio.md` |

All tools return *typed rows*, not chunks. Claude composes them via small Python via code execution.

### Anti-patterns (do not do)

1. **Don't embed OHLCV or numeric DART line items.** Loses precision; forces LLM to re-parse what SQL would return exactly.
2. **Don't expose a `run_sql` escape hatch.** ~60% of finance-agent hallucinations come from silent SQL failures (InfoQ Q4 2025).
3. **Don't chunk DART filings before storing.** Store full `body_md` per `rcept_no`; let 200K context handle the 사업보고서.

---

## 3. Q2 — Analysis Methodology (THE critical question)

### Framing — what's actually been shown to work

| What | Verdict | Evidence |
|---|---|---|
| LLM predicts price | ❌ broken | FinGPT 45–53% movement accuracy; FINSABER long-run loss to B&H |
| Pure sentiment | ❌ alpha decays in 12–24 months | arXiv 2507.03350 |
| Crowded factor models | ⚠ Quant Winter 2025 blew them up | Qube, Cubist failures |
| Black-box ML scoring | ❌ <33% quant funds document model changes (De Prado) | GARP whitepaper |
| LLM auto-trade w/o circuit breakers | ❌ Aidya liquidated <1yr | FIA whitepaper |
| **Event-driven on earnings (PEAD)** | ✅ Korean retail trades *against* surprise → 1%/mo drift 12 months | ScienceDirect S0927538X17305930 |
| **Hybrid retrieval w/ strict citation** | ✅ Bloomberg/AlphaSense/Perplexity all converge | product evidence |
| **Numeric post-validation on LLM output** | ✅ mandatory — Toss built it specifically | Toss Tech writeup |
| **Multi-agent debate as reasoning scaffold** | ✅ improves *quality*, not Sharpe | TradingAgents, FinDebate |
| **Behavioral discipline (sizing, stops, journaling)** | ✅ only retail edge that compounds | SMU Cox 2025 |
| **Fama-French factor tilts as backbone** | ✅ long-run robust | Robeco 2024 |
| **CPCV backtest** | ✅ only credible validation method | De Prado |

### Competitor lesson (key takeaways)

- **Bloomberg ASKB / AlphaSense / Perplexity**: never say BUY/SELL — synthesize evidence only. Their product is *cited snippets*.
- **OpenBB Workspace + Copilot**: closest open-source analog. Keep humans in loop, expose tools, don't auto-decide.
- **Composer.trade / QuantConnect**: auto-trade only behind deterministic rules + paper-trade gate.
- **Toss Securities AI (KR)**: KR market validation that "explainers > predictions" + numeric checksum is mandatory.

### Decision card schema (the analysis output)

Every Claude analysis emits a `decision_card`:

```yaml
card_id: card_005930_2026-05-28
corp_code: "00126380"
ticker: "005930"
generated_at: 2026-05-28T17:42+09:00
as_of: 2026-05-28T16:00+09:00          # data cutoff (KST close)
schema_version: 1

decision:
  stance: HOLD                          # BUY | ADD | HOLD | TRIM | SELL | AVOID
  conviction: 0.55                      # 0-1; ≥0.8 only with multi-source corroboration
  horizon_days: 30
  price_ref: 71200
  invalidation_triggers:                # explicit events that flip thesis
    - "HBM3E NVIDIA qualification fails"
    - "1Q26 메모리 ASP guidance < -10% QoQ"

key_claims:                             # atomic, citation-linkable
  - id: c1
    text: "HBM3E 12-stack NVIDIA qualification near-term catalyst"
    evidence_refs: [dart:20260527000412, news:hankyung:8821]
    weight: HIGH
    confidence: 0.7
  - id: c2
    text: "Memory cycle bottom Q1 2026"
    evidence_refs: [macro:dramx:2026-05-27]
    weight: MEDIUM
    confidence: 0.6

contradictions:                         # first-class output, not noise
  - bull: c1
    bear_evidence: news:zdnet:9912
    bear_claim: "AMD MI300 시장 점유율 확대"
    resolution: "downgraded conviction by 0.15"

assumptions:                            # for the daily worker to re-check
  - "DRAM contract ASP holds ≥ $X / Gb"
  - "NVIDIA HBM3E qual decision arrives by 2026-06-15"

numeric_facts:                          # digit-checksummed against source
  market_cap_krw: 425000000000000
  pe_ttm: 17.2
  foreign_ownership_pct: 53.1

evidence_weights:                       # rubric, not scalar
  dart: HIGH
  krx_flow: MEDIUM
  news_primary_kr: MEDIUM
  user_thesis: HIGH
  sentiment: LOW
  price_action: CONTEXT

guards_passed:                          # for any downstream action
  - position_size_ok
  - daily_loss_under_2pct
  - no_earnings_blackout
  - no_unresolved_contradiction

expires_at: 2026-06-15T00:00+09:00     # MANDATORY — no untimed thesis
```

### Multi-agent debate (the reasoning scaffold)

Per card:
1. **Bull builder** — lists best supporting evidence
2. **Bear builder** — lists disconfirming evidence
3. **Judge** — scores 0–10 on rubric (fundamentals, catalyst presence, contradiction count, thesis freshness, position-sizing fit)

Three Sonnet sub-agents in parallel (via Task tool), then Judge synthesizes. ~30–60s/ticker. Use only for *actionable* cards (changed stance vs prior), not for steady-state HOLD reruns — that's the token-economics gate.

### Action layer gates (KIS auto-trade)

Hard sequence — every gate must pass:

- **Gate A — deterministic guards (not LLM):**
  - Position ≤ 2% portfolio
  - Daily realized loss < 2%
  - No earnings blackout
  - Ticker passes circuit-breaker check
  - KIS rate-limit headroom (20 req/s)
- **Gate B — decision card freshness:**
  - Age ≤ 24h
  - Conviction ≥ 4 (out of 5 scale)
  - No unresolved contradictions
- **Gate C — human kill switch:**
  - `auto_trade_enabled: false` in `notes/private/portfolio.md` halts everything
  - Default: false (per-ticker explicit opt-in)
- **Gate D — paper-trade shadow:**
  - New strategy runs in paper mode ≥30 days before live
  - Composer + QuantConnect both enforce this

### Hard vetoes (NEVER ship)

| ❌ | Why |
|---|---|
| "Predict the price" tool | Empirically broken — coin flip |
| Autonomous LLM trade trigger | Aidya / Eurekahedge AI fund underperformance |
| Factor crowding (value+quality+momentum composite) | Quant Winter 2025 |
| Walk-forward backtest only | Overstates Sharpe 20–40%; use CPCV+embargo |
| Black-box scoring | Must decompose to cited evidence items |
| Untimed thesis | If no expiry + assumption ledger, it's a vibe |
| Sentiment-as-primary | Always corroborate w/ DART/KRX/macro |
| Silent contradiction resolution | First-class output |
| Fine-tuned local LLM | Sonnet is the brain; spend budget on retrieval/eval |

### Open empirical questions (to test in this project)

1. CPCV on Korean small-caps with daily DART catalysts — stable?
2. Korean PEAD magnitude 2024–2026 (literature ends earlier)
3. Sonnet 4.x calibration on Korean financial NLP (no public benchmark)
4. Token economics of 3-role debate × 200 tickers × daily — Schedule quota fit?
5. Auto-trade kill-switch latency — acceptable upper bound?
6. Thesis-decay function shape (linear / exponential / event-triggered)

---

## 4. Q3 — Report Format (dual audience)

### Recommendation: frontmatter + body, single Postgres row

Three columns derived from one canonical write:
- `payload JSONB` — schema-validated, what `get_decision_card()` returns to Claude by default
- `body_md TEXT` — human view (mobile-friendly Markdown)
- `body_md` also BM25-indexed for citation fallback

**Default `get_decision_card()` returns `payload` only (~400 tokens).** With `view="both"`, adds `body_md` (~1.5k). 10-card session ≈ 4k vs 20k+ tokens. Matches Anthropic's "filter before context" guidance.

### Why not the other options

| Option | Why not |
|---|---|
| One MD with two sections | Claude wastes tokens re-parsing prose; section drift |
| JSON canonical + MD render | Loses Markdown-native git review (we're DB-first anyway, partially mitigated) |
| Two physical files | Atomicity / drift risk; doubles DB rows |

### Human body order (mobile-first)

1. **Decision badge** — `HOLD · 확신도 0.55 · 30일`
2. **Three bullets** — why now / what could flip it / what to watch
3. **Price + key numbers table**
4. **Evidence section** — links to source docs
5. **Diff vs prior** — `어제 대비 무엇이 바뀌었나`

### Example (005930)

```markdown
---
report_id: rpt_005930_2026-05-28_daily
decision: {stance: HOLD, conviction: 0.55, horizon_days: 30}
supersedes: rpt_005930_2026-05-27_daily
deltas_vs_prior: {stance_change: null, price_change_pct: +1.2}
...
---
# 삼성전자 · HOLD · 확신도 0.55 (30일)

**왜 지금 HOLD인가**: HBM3E 엔비디아 퀄 통과 임박(+) vs 1Q 메모리 가이던스 불확실(-) 균형.
**무엇이 바뀌면 BUY**: HBM3E 12-stack 퀄 공식 발표 (예상 6월 첫째 주).
**오늘 핵심 변화**: 외국인 +1,240억 순매수 4일 연속.

| 지표 | 값 | vs 전일 |
|---|---|---|
| 종가 | 71,200 | +1.2% |
| 외국인 비중 | 53.1% | +0.08pp |

### 근거
- [DART 20260527000412 — 자기주식취득 신탁계약 체결](...)
- [한경 — HBM3E 양산 인증 임박](...)

### 어제 대비
- 신규 catalyst: HBM3E 퀄 (c1)
- 폐기: "DDR5 가격 반등 thesis" (반등 못 함)
```

### Versioning (chain pointer pattern)

| Concern | Resolution |
|---|---|
| Latest active card | `get_decision_card(ticker)` returns row where `status='active' AND superseded_by IS NULL` |
| Supersession chain | Each daily write sets `supersedes = previous.card_id`; updates prior's `superseded_by` |
| Mid-day invalidation | New event card writes `status='invalidated'` on the morning's card + `invalidation_reason: event_id` |
| Weekly aggregate | Own row with `report_type=weekly` + `source_reports: [card_...×7]`; pre-materialize, don't recompute on read |
| Schema migration | Bump `schema_version`; `get_decision_card()` translates on read via `migrate_v{n}_to_v{n+1}()` if exists; never mutate historical rows |
| `as_of` vs `generated_at` | Separate — Claude must reason about `as_of` when comparing to today |

### Anti-patterns

1. **Don't make Claude re-parse Markdown body** — promote `decision.stance` into payload. Prose is fallback, not API.
2. **Don't bury verdict in narrative** — BLUF or it's useless on phone and in 10-card context windows.
3. **Don't store free-text claims without IDs** — atomic `key_claims[].id` lets next day say `supersedes_claim: c1` instead of regenerating diffs.
4. **Don't write evidence as inline links only** — duplicate as `evidence_refs: [doc:source:id]` for MCP dereference.
5. **Don't return both views by default** — opt into prose.
6. **Don't version by file rename** — `supersedes` pointers; `card_id` immutable.

---

## 5. Daily/weekly briefing (7-2 in the diagram)

Top-of-watchlist *changes only* — no per-ticker dumps. Each entry:

| 종목 | 변화 (1줄) | 근거 링크 | 제안 액션 | Why now | Why not |
|---|---|---|---|---|---|

Cap at 10 entries. Pattern is AlphaSense Workflow Agent + Bloomberg AI Summary distilled.

Weekly briefing is a card with `report_type=weekly` aggregating week's stance changes per ticker, P&L if `auto_trade_enabled` was on, and open contradictions.

---

## 6. Mapping back to architecture diagram

| Step in user's diagram | Concrete artifact in this design |
|---|---|
| 1. API call / schedule collect | `src/collectors/*` (kept post-shutdown) → schedule via systemd.timer or Routine |
| 2. 수집 데이터 DB 저장 | Collector writes directly to Postgres (no Markdown intermediate). New: `INSERT` paths in each collector. |
| 3. 데이터 정제 | Typed MCP tools — `get_filing`, `ohlcv_range`, etc. — over Postgres + selective pgvector/BM25 for narrative |
| 4. 분석 | Sonnet 4.x via 3-role debate, emitting `decision_card` |
| 5. 결과 DB 저장 | `decision_cards` table — JSONB payload + body_md |
| 6. Action | Deterministic gates A–D → KIS API call |
| 7-1. 자동매매 | KIS Open API; rate-limited; paper-shadow ≥30d before live |
| 7-2. Daily/Weekly 리포트 | `decision_cards` aggregation; review loop re-checks `assumptions[]` against fresh data; invalidated cards surface in next briefing |

---

## 7. Recommended phasing (seed for `/gsd:new-milestone`)

| # | Phase | Goal | Depends on |
|---|---|---|---|
| 1 | DB-direct collector cutover | Rewrite 5 collectors to INSERT into Postgres instead of writing Markdown to `vault/raw/`. Drop heartbeat stub. | — |
| 2 | Decision-card schema + storage | `decision_cards` table, Pydantic schema, migration | 1 |
| 3 | MCP tool surface (read-side) | `get_filing`, `ohlcv_range`, `hybrid_search`, etc. | 1, 2 |
| 4 | Analysis runner (3-role debate) | Sonnet sub-agent orchestration → emits cards | 3 |
| 5 | Briefing renderer | Daily/weekly top-N change summary | 4 |
| 6 | Action layer (paper-trade) | Gates A–D + KIS paper API + 30-day shadow | 4 |
| 7 | Action layer (live) | Live KIS w/ kill switch | 6 + ≥30d paper data |
| 8 | Evaluation harness | CPCV+embargo backtest; Sonnet KR-finance calibration eval | 4 |
| 9 | Ops hardening | Schedule routines, contradiction-rate dashboards, alert on stale assumptions | 4–7 |

---

## 8. Sources (consolidated)

### Architecture / data shape
- [Anthropic — Code Execution with MCP (Nov 2025)](https://www.anthropic.com/engineering/code-execution-with-mcp)
- [FinAI Data Assistant — arXiv 2510.14162](https://arxiv.org/pdf/2510.14162)
- [Rethinking Retrieval — arXiv 2511.18177](https://arxiv.org/pdf/2511.18177)
- [InfoQ — Hierarchical Agentic RAG (Q4 2025)](https://www.infoq.com/articles/building-hierarchical-agentic-rag-systems/)
- [Tiger Data — Elasticsearch hybrid search now in Postgres](https://www.tigerdata.com/blog/elasticsearchs-hybrid-search-now-in-postgres-bm25-vector-rrf)
- [VectorChord hybrid search](https://docs.vectorchord.ai/vectorchord/use-case/hybrid-search.html)
- [LLM Wiki — Karpathy pattern, 100K-token ceiling](https://decodethefuture.org/en/llm-wiki-karpathy-pattern/)

### Analysis methodology
- [TradingAgents — arXiv 2412.20138](https://arxiv.org/abs/2412.20138)
- [StockBench — arXiv 2510.02209](https://arxiv.org/abs/2510.02209)
- [FINSABER long-run LLM eval — arXiv 2505.07078](https://arxiv.org/abs/2505.07078)
- [FinDebate — arXiv 2509.17395](https://arxiv.org/pdf/2509.17395)
- [Korean PEAD individual investors](https://www.sciencedirect.com/science/article/abs/pii/S0927538X17305930)
- [Quant Winter 2025 — Ainvest](https://www.ainvest.com/news/quant-winter-2025-market-structure-shifts-ai-limitations-expose-hidden-vulnerabilities-2507/)
- [Eurekahedge AI fund underperformance — AlphaArchitect](https://alphaarchitect.com/ai-funds/)
- [SMU Cox 2025 — patience in retail trading](https://www.smu.edu/cox/coxtoday-magazine/2025-11-03-patience-in-trading-retail-investors)
- [FIA Best Practices for Automated Trading Risk Controls](https://www.fia.org/sites/default/files/2024-07/FIA_WP_AUTOMATED%20TRADING%20RISK%20CONTROLS_FINAL_0.pdf)
- [De Prado — 10 Reasons ML Funds Fail (GARP)](https://www.garp.org/hubfs/Whitepapers/a1Z1W0000054x6lUAA.pdf)
- [CPCV — Quantinsti](https://blog.quantinsti.com/cross-validation-embargo-purging-combinatorial/)
- [KIS Open Trading API](https://github.com/koreainvestment/open-trading-api)
- [Toss Tech earnings call](https://toss.tech/article/toss-securities-earnings-call)
- [AlphaSense Financial Data launch](https://www.alpha-sense.com/press/alphasense-launches-financial-data/)
- [Bloomberg ASKB / Terminal AI](https://www.itbrew.com/stories/2025/11/19/bloomberg-new-ai-tool-for-terminal)
- [OpenBB Workspace](https://openbb.co/blog/introducing-the-new-openbb-terminal/)

### Report format
- [Anthropic Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Frontmatter-First Is Not Optional (Hannecke, 2026)](https://medium.com/@michael.hannecke/frontmatter-first-is-not-optional-context-window-survival-for-local-llms-in-opencode-15809b207977)
- [BLUF writing format](https://en.wikipedia.org/wiki/BLUF_(communication))
- [Trading-R1 — arXiv 2509.11420](https://arxiv.org/pdf/2509.11420)
- [AlphaSense Smart Summaries](https://www.alpha-sense.com/blog/product/smart-summaries-earnings-analysis/)

---

**Status:** This is research, not yet a phase. Promote via `/gsd:new-milestone` ("v2.0 — DB-direct redesign") with phases per §7.
