# Stack Research — Korean-Market Stock Wiki (stock-mcp + gbrain + graphify + Obsidian)

**Domain:** Personal/small-team Korean equity research knowledge base (Obsidian vault as source of truth, Postgres+pgvector retrieval, MCP server exposed to Claude Code)
**Researched:** 2026-04-16
**Overall confidence:** HIGH on Python data libs, MEDIUM on embeddings/LLM sizing (hardware-dependent), MEDIUM on storage layer (actively evolving in 2026)

---

## TL;DR — The Prescribed Stack

| Layer | Pick | Version | Confidence |
|---|---|---|---|
| DART (공시) | **dart-fss** | latest (0.4.x series, healthy) | HIGH |
| KRX 가격/재무 | **pykrx** + **FinanceDataReader** (both) | pykrx >= 1.0.50, FDR >= 0.9.94 | HIGH |
| 네이버 증권 | **requests + pandas.read_html** (no library; bespoke scrapers) | n/a | HIGH |
| 뉴스 본문 추출 | **trafilatura** | >= 1.12 | HIGH |
| 한은 ECOS | **PublicDataReader** | latest | MEDIUM |
| FRED/글로벌 거시 | **fredapi** + **yfinance** | fredapi >= 0.5, yfinance >= 0.2.50 | HIGH |
| Scheduler | **systemd.timer** on Linux / Task Scheduler on Windows; APScheduler only if in-process is needed | n/a | HIGH |
| DB (dev/single-user) | **PGLite** (gbrain default) | @electric-sql/pglite ^0.4.4 | HIGH |
| DB (multi-user, recommended for this project) | **Native Postgres 17** via Docker | postgres:17-alpine | HIGH |
| Vector | **pgvector** | 0.8.0 | HIGH |
| BM25 | **VectorChord-BM25** | latest (2026) | MEDIUM |
| Embeddings | **bge-m3** (via Ollama) | bge-m3:latest | HIGH |
| Local LLM (ingest) | **Qwen2.5-14B-Instruct** Q4_K_M (primary) + **EXAONE-3.5-7.8B** (Korean-heavy docs) | Ollama tags | HIGH |
| Ingest fallback | **Claude Haiku 4.5** | via Anthropic SDK | HIGH |
| MCP server | **FastMCP** (Python) | 2.x stable (currently 2.11+); avoid 3.x until ecosystem catches up | MEDIUM |
| Obsidian plugin | **domleca/llm-wiki** (optional, for UX) + **Dataview** (required, for dashboard notes) | dataview >= 0.5 | HIGH |
| Graph | **graphify** (`safishamsi/graphify`, `graphifyy` on PyPI) | latest (v4) | HIGH |
| Python runtime | **CPython 3.12** (not 3.13 until ML deps catch up) | 3.12.x | HIGH |
| Env manager | **uv** (fast, modern) | >= 0.4 | HIGH |

---

## 1. Data Collection Libraries (Python)

### 1.1 DART (전자공시) — Pick: `dart-fss`

**Recommendation:** `dart-fss` (josw123/dart-fss).
**Version pin:** Latest on PyPI (healthy maintenance in past 3 months as of 2026-04).
**Install:** `pip install dart-fss`

**Rationale:**
- **Actively maintained**: Snyk's advisor confirms `dart-fss` has "Healthy" maintenance status with a release in the past 3 months; OpenDartReader had no PyPI release in past 12 months and is effectively dormant.
- dart-fss wraps both the Open DART API (공시·재무제표) and adds HTML parsing for items the API doesn't expose (attachment parsing, linked-note financials). This reduces how much custom code you need.
- Returns structured `DataFrame`-friendly objects — plays well with the downstream ingest pipeline.

**What NOT to use:**
- `OpenDartReader` (FinanceData/OpenDartReader) — dormant. Useful historical reference but don't adopt.
- `open-darts` — **completely unrelated** (differentiable adaptive reservoir simulator). Easy name confusion; skip.

**Caveat:** Both libraries call the same government Open DART REST API. You need an API key from `opendart.fss.or.kr`. Rate limit is 20,000 calls/day — trivially sufficient for daily batch.

**Confidence:** HIGH.

---

### 1.2 KRX 가격 & 재무 — Pick: `pykrx` + `FinanceDataReader` (use both)

**Recommendation:** Install both. They cover overlapping but non-identical surfaces.
**Versions:**
- `pykrx >= 1.0.50` (actively maintained; issues posted Feb 2026)
- `FinanceDataReader >= 0.9.94` (copyright through 2026, maintained)

**Install:** `pip install pykrx finance-datareader`

**Rationale for both:**
- **`pykrx`** scrapes KRX + Naver Finance directly. Strength: OHLCV, 시가총액, 외국인/기관 매매동향, ETF NAV, 배당. Best for raw market microstructure. No upstream API rate limits (direct KRX/Naver endpoints).
- **`FinanceDataReader`** is a unified reader across KRX, NASDAQ, SSE, HKEX, forex. Strength: KRX listings (all ~2,800 tickers with ISIN/섹터/상장일), cross-market ETF lookup, global index data. Best for universe construction & cross-listing.
- **They disagree sometimes** on edge cases (suspended tickers, recent IPOs). Having both lets your collector cross-check. Single-lib dependency is a known pain point (FDR issue #227).

**What NOT to use:**
- `yahooquery` for Korean equities — Yahoo's KRX data is stale and incomplete for non-KOSPI200 names.
- Scraping KRX KIND directly — both libraries above already do this correctly; don't reinvent.

**Confidence:** HIGH.

---

### 1.3 네이버/다음 증권 크롤링 — Pick: `requests` + `pandas.read_html` + `BeautifulSoup4`

**Recommendation:** No dedicated library. Write thin scrapers using:
- `requests` 2.32+ (with `User-Agent` header set)
- `pandas.read_html()` for tabular pages (재무제표, 종목 요약, 거래동향)
- `BeautifulSoup4 >= 4.12` for parsing 종목토론실, 뉴스 리스트

**Rationale:**
- Naver Finance has no stable public API for most of what you want (종목토론, 리서치 카테고리, 종목 요약 본문). Libraries exist on GitHub but are unmaintained one-offs tied to specific page versions.
- `pandas.read_html()` on Naver's financial-statement iframe endpoints (e.g., `companyinfo.stock.naver.com/v1/company/ajax/cF1001.aspx?...`) is the documented community pattern and survives most layout changes.
- Write scrapers **per-page-type**, keep them tiny (<80 LOC each), and version-pin the HTML selectors. When Naver changes layout (happens 1-2x/year), you fix one file.

**Critical constraint (legal):**
- Naver Finance's robots.txt disallows aggressive scraping of some paths. Daily-batch low-rate collection (with UA identification and 1-2 req/sec cap) is the norm in Korean quant community, but treat this as gray area.
- Prefer **Naver Developers Open API** (News Search, etc.) for anything available — it has a quota but is legally unambiguous. You'll still scrape for 시세/토론방.

**What NOT to use:**
- `selenium` / `playwright` for Naver Finance crawling — overkill. These pages are SSR-ed HTML; `requests` is 50x faster and doesn't need a browser.
- `scrapy` — framework overhead vs. ~10 scripts is not worth it at this scale.

**Confidence:** HIGH.

---

### 1.4 뉴스 본문 추출 — Pick: `trafilatura`

**Recommendation:** `trafilatura >= 1.12`.
**Install:** `pip install trafilatura lxml`

**Rationale:**
- **Precision/recall leadership:** Sandia 2024 evaluation and the "Comparative Analysis of Open-Source News Crawlers" study both put trafilatura at the top for main-text extraction (F1 ~0.94, precision ~0.98). Newspaper3k is 5-10% behind on noisy pages.
- **Multilingual-first**: trafilatura explicitly targets multilingual sites; Korean news sites (한경, 이데일리, 서울경제, 조선비즈) with their heavy sidebar/navigation markup extract cleanly.
- **No ML dependency:** Pure Python with `lxml`. Fast (~10ms per article), no GPU, no model download.
- **RSS + discovery built in:** `trafilatura.feeds` handles RSS; `trafilatura.sitemaps` walks sitemaps. You don't need feedparser separately for most cases.

**Pattern:**
```python
import trafilatura
downloaded = trafilatura.fetch_url(url)
result = trafilatura.extract(
    downloaded,
    output_format="markdown",
    with_metadata=True,
    include_comments=False,
    target_language="ko",
)
```

**What NOT to use:**
- `newspaper3k` — maintenance issues; the `newspaper4k` fork is better but still trafilatura's inferior on precision benchmarks.
- `readability-lxml` — older algorithm, poor on Korean navigation-heavy layouts.
- `goose3` — unmaintained.

**Confidence:** HIGH.

---

### 1.5 한은 ECOS — Pick: `PublicDataReader`

**Recommendation:** `PublicDataReader`.
**Install:** `pip install PublicDataReader`

**Rationale:**
- Maintained by @WooilJeong (wooiljeong.github.io); Korean Python 금융 데이터 생태계에서 가장 많이 쓰임.
- Covers ECOS **and** other public-data APIs (공공데이터포털, SGIS, 한국부동산원) — useful future optionality.
- Clean DataFrame output; handles pagination and code metadata automatically.

**Alternatives considered:**
- `ecos_api_loader` (jmlee8939) — works, smaller surface, less maintained.
- `boklib` (neur0hak) — works, but smaller user base; slower bugfix cycle.
- Direct `requests` against `ecos.bok.or.kr/api/` — fine for a single endpoint, but you'll rebuild code management yourself. Don't.

**Caveat:** All ECOS access requires an API key from `ecos.bok.or.kr`. Key is free but needs email verification.

**Confidence:** MEDIUM (library is less popular than dart-fss/pykrx but no better competitor exists).

---

### 1.6 FRED & 글로벌 거시 — Pick: `fredapi` + `yfinance`

**Recommendation:**
- `fredapi >= 0.5.2` for FRED (미국 연준 경제통계).
- `yfinance >= 0.2.50` for 글로벌 지수/환율/원자재 (WTI, 금, DXY, VIX).
- **`CurrencyLayer` or `exchangerate.host`** via `requests` for authoritative 환율 (yfinance 환율은 대표시세라 미묘함).

**Rationale:**
- fredapi is the de-facto standard, ~10 years mature, trivial API.
- yfinance is scrappy (breaks ~1x/year when Yahoo changes internals) but nothing else covers the same breadth of global instruments for free.

**Confidence:** HIGH.

---

## 2. Scheduling — Pick: `systemd.timer` (Linux/WSL) or Windows Task Scheduler

**Recommendation:** **Use OS-native scheduling**. Wrap each collection script as an idempotent CLI entry point; trigger from systemd.timer (WSL/Linux) or Windows Task Scheduler.

**Rationale:**
- **Reliability > Flexibility at personal-scale.** systemd.timer survives reboots, logs to journalctl, and has zero Python dependencies. If the scheduler process dies, your data collection dies silently — this is exactly the APScheduler failure mode.
- **APScheduler requires a hosting process.** It's "not a daemon" (per its own docs). For a batch pipeline that runs 1-10x/day, you'd build a separate always-on runner just to host APScheduler. Strictly worse than systemd.timer.
- **Cron works but is worse than systemd.timer.** No structured logs, no persistence tracking, no `OnBootSec`, no dependencies between units. systemd.timer supersedes cron on modern Linux for good reasons.
- **GitHub Actions is wrong here.** Data is local (Obsidian vault on disk), Postgres is local, Ollama is local. Pulling collection into CI just to push results back via git is complexity for no benefit.

**When APScheduler IS right:**
- If and only if the MCP server process is always-on and needs to *also* trigger scheduled work internally (e.g., "refresh embeddings every 6h while I'm running"). Even then, prefer OS cron + MCP tool call over APScheduler.

**Pattern:**
```ini
# ~/.config/systemd/user/stock-collect.service
[Service]
Type=oneshot
WorkingDirectory=%h/workspace/stock
ExecStart=%h/workspace/stock/.venv/bin/python -m stock_collector.daily

# ~/.config/systemd/user/stock-collect.timer
[Timer]
OnCalendar=Mon..Fri 18:30 Asia/Seoul
Persistent=true

[Install]
WantedBy=timers.target
```
Then `systemctl --user enable --now stock-collect.timer`.

**Confidence:** HIGH.

---

## 3. Storage Layer — Pick: Native Postgres 17 + pgvector 0.8 + VectorChord-BM25

### 3.1 PGLite vs Native Postgres

**Recommendation for this project:** **Native Postgres 17 in Docker**, not PGLite.

| Criterion | PGLite | Native Postgres 17 |
|---|---|---|
| Setup friction | Zero (wasm, embedded) | Docker compose (~2 min) |
| Concurrency | Single connection only | Unlimited |
| MCP server + ingest batch concurrent access | **Broken** (single-user mode) | Fine |
| All pgvector features | Yes | Yes |
| VectorChord-BM25 extension | **Not available** (needs native OS) | Yes |
| Tooling (psql, pgAdmin) | Limited | Full |
| Gbrain default | Yes | Alt |

**gbrain uses PGLite as its default** (`@electric-sql/pglite ^0.4.4` in their `package.json`) because it ships as an npm library with zero install. That's right for gbrain's "clone and run" ethos.

**It's wrong for this project** because:
1. You have an **ingest pipeline** (batch writes, sometimes long-running) **and** an **MCP server** (ad-hoc reads from Claude Code) that must run concurrently. PGLite's single-connection limit (even with the new multiplexer) makes this painful.
2. You need **VectorChord-BM25** or `pg_search` for proper hybrid retrieval. These extensions require native Postgres — they don't run in WASM.
3. 2-5 users may eventually hit the DB (git-shared vault, independent MCP servers on each user's machine reading the same data is fine, but if anyone syncs the DB itself PGLite breaks).

**Setup:**
```yaml
# docker-compose.yml
services:
  postgres:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes: [./data/pg:/var/lib/postgresql/data]
    ports: ["127.0.0.1:5432:5432"]
```

`pgvector/pgvector:pg17` image includes pgvector 0.8.x pre-built. Add VectorChord-BM25 via:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS vchord_bm25;  -- from tensorchord/VectorChord-bm25
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- for Korean fuzzy match fallback
```

### 3.2 pgvector — Pin: 0.8.0

**Required features** (all land in 0.7+, polished in 0.8):
- `halfvec` type — 16-bit vectors, ~50% storage savings. Use for bge-m3's 1024-d vectors.
- `binary_quantize()` — scalar-quantized binary index for speed. Useful at >100k documents.
- Iterative HNSW scan — fixes filtered-query recall drop that plagued 0.6.x.

Pin to `0.8.0` to unlock all three.

### 3.3 BM25 extension — Pick: VectorChord-BM25

**Recommendation:** `vchord_bm25` (tensorchord/VectorChord-bm25).

**Rationale:**
- **3x faster than Elasticsearch** per VectorChord's own benchmarks (take with salt, but independent tests confirm the ballpark).
- Uses **BlockMax WeakAnd** — modern BM25 implementation, not naive inverted-index rank.
- Native PostgreSQL extension — composable with pgvector via RRF fusion in a single SQL query. This is exactly gbrain's hybrid pattern.
- Active development through 2026.

**Alternatives:**
- **ParadeDB `pg_search`** — excellent, but: (a) Neon dropped it as of 2026-03, signaling fragmentation, (b) built on Tantivy (Rust/Lucene-alike) — heavier binary, longer build. Pick this if you want facets/highlighting.
- **Timescale `pg_textsearch`** — released 2026-03, promising, but too new to bet on as of this research date. Revisit in 6 months.
- **Native `ts_rank` + `pg_trgm`** — works, but BM25 is a major quality upgrade per VectorChord benchmarks and the Tiger Data writeup. Worth the extension.

**Korean tokenization caveat:**
- Default Postgres `to_tsvector` has **no Korean analyzer**. Your BM25 tokenizer must be language-aware or you'll split on whitespace only — bad for Hangul-heavy documents where many search terms are compound nouns.
- VectorChord-BM25 supports custom tokenizers; plug in **Lindera with the Korean (mecab-ko) dictionary** or the simpler **`soynlp`-preprocessed** pipeline (preprocess in Python before indexing).
- Pragmatic path: **tokenize in Python with `mecab-ko` (via `konlpy` or `python-mecab-ko`) before insert**, store the tokenized form in a dedicated column, let VectorChord-BM25 tokenize on whitespace. This avoids pg-extension build complexity and lets you swap Korean tokenizers later.

**What NOT to use:**
- `ts_vector` alone (no BM25, no language-aware tokenization for Korean). Acceptable as a Phase-1 stopgap but don't plan around it.
- Elasticsearch / Meilisearch / Typesense — separate infrastructure, a whole second system to manage. Hard veto for this project's "keep it local and small" constraint.

**Confidence (section 3):** MEDIUM. Postgres + pgvector + BM25-extension space is moving fast in 2026. The recommendation is solid *today*; revisit BM25 extension choice in 6 months.

---

## 4. Embeddings — Pick: `bge-m3` via Ollama

**Recommendation:** **BAAI/bge-m3** served via Ollama.
**Ollama tag:** `bge-m3:latest` (Ollama ships the 568M-param model, ~1.3GB).

**Rationale:**
- **Multilingual top-tier.** Ranked #1 average on MIRACL (18 languages, nDCG@10=70.0) — outperforms mE5-large (65.4) on the standard multilingual retrieval benchmark. Korean falls squarely within its training distribution.
- **Unified dense + sparse + multi-vector.** bge-m3 produces dense embeddings (1024-d) AND learned sparse weights (lexical) AND ColBERT-style multi-vector in a single forward pass. For this project, use dense only (stored in pgvector) + separate BM25 for lexical. But the option to upgrade to learned-sparse later is valuable.
- **8192-token context.** Handles full 공시 텍스트, 뉴스 기사, 증권사 리포트 요약 without aggressive chunking.
- **Already trusted by gbrain-style setups** and the Korean ML community.

**Specialized variant:** **`dragonkue/BGE-m3-ko`** exists — Korean-optimized fine-tune. Pros: higher recall on Korean-only benchmarks. Cons: (1) slightly worse on English/cross-lingual (your 뉴스 will mix English), (2) less battle-tested. **Default to vanilla bge-m3**; switch to bge-m3-ko only if retrieval quality benchmarks on your corpus show measurable lift.

**Resource requirements (bge-m3 on Ollama):**
- **VRAM:** ~2GB at fp16, ~1GB at q4. Runs on any consumer GPU; acceptable on CPU (Apple Silicon M-series blazes, x86 CPU is ~200ms/doc).
- **Throughput:** On RTX 3060 (12GB), expect ~50 docs/sec batched, ~20 docs/sec single. On CPU-only M2, ~3 docs/sec.
- **Query latency:** <50ms on GPU, <200ms on CPU.
- **Storage cost per embedding:** 1024 × 4 bytes = 4KB (float32). With `halfvec` → 2KB. With binary quantize → 128 bytes. At 50k documents: 200MB → 100MB → 6MB.

**Alternatives considered:**

| Model | Dim | Korean | English | Cost | Verdict |
|---|---|---|---|---|---|
| **bge-m3** | 1024 | Strong | Strong | Free, local | **Pick** |
| multilingual-e5-large | 1024 | Strong | Strong | Free, local | Runner-up; slightly weaker MIRACL score |
| nomic-embed-text-v2 | 768 | OK | Strong | Free, local | MoE architecture is novel; under-tested on Korean; comparable size |
| OpenAI text-embedding-3-large | 3072 | Good | Excellent | $0.13/M tokens | Rejected: cost + external dep |
| Voyage-3 | 1024 | Good | Excellent | $0.12/M tokens | Rejected: cost |

**What NOT to use:**
- `text-embedding-ada-002` — obsolete.
- `sentence-transformers/all-MiniLM-L6-v2` — English-only, bad on Korean.
- Any BERT-base-multilingual — predates MIRACL-era methods by 3+ years; subpar.

**Confidence:** HIGH on the pick; MEDIUM on bge-m3-ko vs vanilla tradeoff (depends on your actual corpus).

---

## 5. Local LLM for Ingest — Pick: Qwen2.5-14B-Instruct (primary) + EXAONE-3.5-7.8B (Korean-heavy)

### 5.1 Primary model: Qwen2.5-14B-Instruct Q4_K_M

**Recommendation:** **Qwen2.5-14B-Instruct** at Q4_K_M via Ollama.
**Ollama tag:** `qwen2.5:14b-instruct-q4_K_M`.

**Rationale:**
- **Sweet spot for 16GB-VRAM GPUs.** Q4_K_M 14B uses ~10-12GB VRAM, leaves headroom for 8K-context ingest prompts + bge-m3 running simultaneously.
- **Strong multilingual instruction following** including Korean — outperforms Llama-3.1-8B on KoMT-Bench in LG's own published comparisons.
- **Structured output (JSON) is reliable** — critical for attribute extraction into frontmatter. Qwen2.5 was trained with heavy JSON-mode coverage.
- **128K context** — ingests long 증권사 리포트 whole if needed (rare, but nice).
- **Broad Ollama/llama.cpp/vLLM support.** No ecosystem surprises.

### 5.2 Korean-specialist fallback: EXAONE-3.5-7.8B

**When to use:** Documents that are 100% Korean prose (한은 보도자료, 장문 사설, 한국어 블로그 메모) where nuance matters.
**Ollama tag:** `exaone3.5:7.8b` (LG AI Research, permissive license).

**Rationale:**
- **50% Korean / 50% English vocabulary** — genuinely bilingual tokenizer. Qwen2.5 is multilingual but Chinese-first; Korean token efficiency is worse (more tokens per character).
- **KoMT-Bench highest scores at 7.8B size class** per LG's technical report. For pure Korean generation, this is the strongest sub-10B model in the published benchmarks.
- **Smaller footprint** (~5GB VRAM at Q4) — runs alongside Qwen2.5-14B on a 16GB card.

### 5.3 What NOT to use

- **Llama-3.3-70B** — too heavy. Requires 40GB+ VRAM at Q4; you'd need a workstation-class card. Benchmark gains over Qwen2.5-14B on extraction tasks don't justify the infra leap.
- **Qwen2.5-32B** — 22-24GB VRAM at Q4. Borderline on a 24GB card (RTX 4090/A5000) with context; if you already own one, fine. If you don't, 14B is a better ROI.
- **Llama-3.1-8B** — acceptable baseline but Korean performance lags Qwen2.5 and EXAONE meaningfully.
- **Gemma-2-27B** — Google-license concerns and no Korean tuning advantage.
- **EXAONE-4.0** — released mid-2026; promising but the 3.5 series is more field-tested. Upgrade in 6-12 months once issues stabilize.

### 5.4 Hardware guidance

| GPU | Qwen2.5-14B Q4 | EXAONE 7.8B Q4 | bge-m3 | Verdict |
|---|---|---|---|---|
| RTX 3060 12GB | Tight (12GB) | Fine (5GB) | Fine | OK; run one LLM at a time |
| RTX 4070 16GB | Fine (12GB) | Fine alongside | Fine | **Sweet spot** |
| RTX 4090 24GB | Plenty | Both concurrent | Fine | Overkill unless doing 32B |
| M2 Max 32GB unified | Fine (shared) | Fine | Fine | Viable; slower gen |
| CPU only | Painful (2-3 tok/s) | Painful | Fine | Ingest will take hours. Not recommended. |

### 5.5 Cost crossover with Claude Haiku

**Claude Haiku 4.5:** $1.00 / $5.00 per M input/output tokens.
**Claude Haiku 3.5 (legacy):** $0.80 / $4.00.

For a typical ingest attribute-extraction call:
- ~2k input tokens (doc + prompt), ~300 output tokens (JSON).
- **Haiku 4.5 cost per doc:** ~$0.0035. At 100 docs/day: $0.35/day = ~$130/year.
- **Haiku 3.5 cost per doc:** ~$0.0028. At 100 docs/day: ~$100/year.

Local Qwen2.5-14B amortized cost (assuming you already own the GPU): ~electricity, rounds to zero.

**Crossover logic:** If daily doc count exceeds ~50 *and* you have a GPU, local wins on cost. Below that, Haiku is easier.

**Recommended hybrid:** Primary is local Qwen2.5-14B. Fallback path (and for any single critical extraction needing higher reliability) is **Haiku 4.5** via Anthropic SDK. This is also the graceful-degradation path when Ollama/the GPU is unavailable.

**Confidence:** HIGH on model choice; MEDIUM on hardware (depends on user's GPU).

---

## 6. MCP Server — Pick: FastMCP 2.x (Python)

**Recommendation:** **FastMCP 2.x** (pin to a 2.11+ release).
**Install:** `pip install "fastmcp>=2.11,<3.0"`.

**Rationale:**
- FastMCP 2.x is **the** Python MCP framework. Decorator API (`@mcp.tool()`) auto-generates schemas from type hints; docstrings become tool descriptions. The Python MCP SDK itself wraps FastMCP for the high-level API.
- **Pin to 2.x for now.** 3.x shipped Feb 2026 with a major architectural rewrite (Providers / Transforms); it's promising but ecosystem catches up slowly, and Claude Code's MCP transport support is optimized for the 2.x patterns. Revisit in Q3 2026.
- **stdio transport** for local Claude Code integration — zero networking, simplest deployment. (Streamable HTTP is relevant only if multiple remote clients; not this project's use case.)

### Tool design pattern for stock-mcp

Based on 2026 MCP best practices (per Firecrawl and Effloow guides):

**Principles:**
1. **One responsibility per tool.** `search_vault(query)` ≠ `get_ticker_status(ticker)` ≠ `run_graph_query(cypher)`. Claude chooses based on semantic description — overload one tool and it gets confused.
2. **Return structured errors.** `{"error": "ticker_not_found", "message": "...", "suggestions": ["005930", ...]}` — Claude can reason about structured errors, not about exceptions or stack traces.
3. **Parameter types matter more than you think.** Use enums (`Literal["price", "news", "disclosure"]`) instead of free-text `source` params. Claude will stay inside the enum.
4. **Docstrings become the tool description.** Write them for an LLM: state purpose, inputs, typical use cases, one example.

**Recommended tool surface for stock-mcp (first pass):**

| Tool | Purpose |
|---|---|
| `search_vault(query, k=10, filter)` | Hybrid semantic+BM25 search over Obsidian notes |
| `get_ticker_summary(ticker)` | Aggregate latest price, 공시, 뉴스, 본인 메모 for a ticker |
| `list_portfolio()` | Read user portfolio frontmatter from dashboard note |
| `get_disclosure(rcept_no)` | Fetch full DART disclosure text by receipt number |
| `get_macro(series_id, lookback_days)` | FRED/ECOS series recent values |
| `run_graph_query(cypher_or_bfs)` | Traverse graphify output |
| `recent_events(ticker, days=7)` | Timeline of disclosures + news + price moves |

Keep initial surface **small (<10 tools)**. Add more only when Claude repeatedly asks for something the existing tools can't cleanly provide.

**Confidence:** MEDIUM-HIGH. The FastMCP 2.x vs 3.x decision is the main uncertainty; `2.x` is conservative but safe.

---

## 7. Obsidian Integration — Pick: Dataview (required), llm-wiki (optional)

### 7.1 Dataview — install now

**Recommendation:** Install **Dataview plugin** (blacksmithgu/obsidian-dataview) immediately.
**Why:** Your portfolio dashboard note ("보유 종목 상태·최근 이벤트·판단 근거 요약") is a Dataview query. Dataview reads YAML frontmatter (`ticker`, `event_type`, `sentiment`, `date`) from every note in the vault and renders dynamic tables — exactly what this project needs.

**Pattern:**
```dataview
TABLE ticker, price_krw, last_event, sentiment
FROM "disclosures"
WHERE date >= date(today) - dur(7 days)
SORT date DESC
```

### 7.2 llm-wiki plugin — optional, consider after MVP

Two distinct "llm-wiki" plugins circulate:
- **`domleca/llm-wiki`** — natural-language query over vault, extracts entities/concepts, generates cross-link pages. Runs locally; writes `wiki/kb.json` + per-entity markdown.
- **`kytmanov/obsidian-llm-wiki-local`** — 100% local variant with Ollama integration.

**Recommendation:** **Don't install in Phase 1.** Your ingest pipeline (stock-mcp's own script) already does what llm-wiki does — extracts entities, builds cross-links, writes structured frontmatter. Installing llm-wiki in parallel would run a second extraction on the same corpus with slightly different semantics, causing frontmatter drift and user confusion.

**Consider in Phase 3+** if (a) you want the plugin's interactive "ask your vault" UI in Obsidian directly (not via Claude Code), OR (b) the pattern it uses for entity pages turns out to be better than yours and you want to adopt it. **Reference it for design inspiration now, install later if needed.**

### 7.3 Frontmatter schema

Define and document your frontmatter schema **before ingest starts**. Example for a 공시 note:
```yaml
---
type: disclosure
source: dart
ticker: "005930"
corp_name: 삼성전자
rcept_no: "20260416800123"
report_name: 주요사항보고서(유상증자결정)
date: 2026-04-16
tags: [공시, 유상증자, 005930]
sentiment: neutral
event_category: capital_raise
affected_tickers: ["005930"]
---
```

Use **Zod or Pydantic** to validate frontmatter on write. This prevents schema drift that will otherwise break Dataview queries silently.

### 7.4 Dataview vs Bases (Obsidian 1.7+)

Obsidian shipped **Bases** in 2026 — a native frontmatter-query feature that overlaps with Dataview. For this project:
- **Stick with Dataview.** More powerful query language, richer community templates, stable.
- **Use Bases** only for lightweight filtered views where Dataview is overkill.

**Confidence:** HIGH.

---

## 8. graphify Integration — confirmed: `safishamsi/graphify` (PyPI: `graphifyy`)

### 8.1 Actual maintainer

**Correction to project brief:** The graphify tool is at **`safishamsi/graphify`** (PyPI: `graphifyy`), not `yamin1124/graphify`. The user's local skill at `~/.claude/skills/graphify/SKILL.md` wraps the `safishamsi/graphify` PyPI package (`graphifyy`). The SKILL.md confirms `pip install graphifyy`.

**Install:** `pip install graphifyy` (in the `stock` project's `.venv`).

### 8.2 Pipeline (three passes)

Per the SKILL.md and README:
1. **Pass 1 — AST (deterministic, free):** Tree-sitter walks code files. For this project: minimal (vault is mostly Markdown) — graphify will still run but AST contributes few nodes.
2. **Pass 2 — Transcription (local, if video/audio):** Not applicable unless you're adding broadcast/YouTube earnings calls.
3. **Pass 3 — Semantic (Claude subagents, costs tokens):** This is where the value is. Claude reads docs/PDFs/images in parallel, extracts **entities, relationships, design rationale**; results merged into NetworkX graph, clustered with Leiden community detection.

### 8.3 Outputs

Per SKILL.md Step 5 onwards, graphify produces into `graphify-out/`:
- `graph.json` — queryable JSON (primary; stock-mcp reads this).
- `index.html` — interactive pyvis visualization.
- `GRAPH_REPORT.md` — plain-language audit (every edge tagged EXTRACTED / INFERRED / AMBIGUOUS).
- Optional: `graph.svg`, `graph.graphml`, Neo4j cypher, Obsidian vault reflection (`--obsidian`).

**Each edge has an honesty tag** — for a judgment-support wiki this is critical; Claude can show you WHY it made a claim vs guessed.

### 8.4 How to use for this project

**Recommendation:**
```bash
# From vault root
graphify . --mode deep --directed --wiki --obsidian
```
- `--mode deep` — richer INFERRED edges (worth the extra tokens for a small-to-medium vault).
- `--directed` — preserves edge direction (`news_article --mentions--> ticker` ≠ reverse).
- `--wiki` — auto-generates community-index article pages (complementary to your Dataview dashboards).
- `--obsidian` — writes graph back into the vault as linked notes (so graphify output is itself Obsidian-native).

**Incremental refresh:**
```bash
graphify . --update
```
Re-extracts only new/changed files. Run this after each ingest batch.

**Integration with stock-mcp:**
- Option A: `stock-mcp` reads `graphify-out/graph.json` directly for tools like `run_graph_query`.
- Option B: Run `graphify --mcp` in a sidecar and compose both MCP servers in Claude Code (FastMCP supports composition).
- **Pick A** for Phase 1 (simpler, one process).

**Confidence:** HIGH (SKILL.md confirms capabilities and outputs directly).

---

## 9. Version Control — Pick: Commit vault + code; exclude `.obsidian/workspace*`, caches, DB data

### 9.1 What to commit

- **Every Markdown file in the vault** (prose + frontmatter) — this is the source of truth. Git history *is* your edit history.
- **`.obsidian/app.json`**, `.obsidian/hotkeys.json`, `.obsidian/plugins/*/data.json` (settings, not state).
- **Python source** for collectors, ingest pipeline, stock-mcp.
- **`pyproject.toml` / `uv.lock`** for dep pinning.

### 9.2 What to gitignore

```gitignore
# Obsidian UI state (churn, merge conflicts)
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/cache/
.obsidian/plugins/*/data.json.bak

# Trash & OS junk
.trash/
.DS_Store
Thumbs.db
desktop.ini

# Python
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.mypy_cache/

# Databases (NEVER commit)
data/pg/
*.db
*.sqlite

# graphify outputs (regeneratable)
graphify-out/
.graphify_detect.json
.graphify_python

# Secrets
.env
.env.*
!.env.example

# Raw collected data (too bulky, regeneratable from APIs)
# Decide per-project. For this project, COMMIT processed markdown (the vault),
# but exclude /raw binary dumps, PDFs, compressed HTMLs.
raw/*.pdf
raw/*.html.gz
```

### 9.3 Git LFS — probably not needed

- Markdown files are tiny (~KB each). 50k Markdown docs = ~500MB uncompressed, compresses well in git.
- **Skip Git LFS** unless you're committing raw PDFs (증권사 리포트 원문) — which you shouldn't per the license guidance in PROJECT.md. If you later decide to archive a few dozen PDFs, enable LFS just for `*.pdf`.

### 9.4 Branching & collab

For 2-5 user team:
- Single `main` branch, PR-based.
- **Each user's `stock-mcp` and Postgres instance is local and independent.** Only the Markdown vault (+ code) is shared via git.
- If DB schema migrations needed, use **Alembic** (standard Python Postgres migration tool) — commit migration scripts, each user runs `alembic upgrade head` locally.

### 9.5 Sensitive data

- DART/ECOS/Naver API keys → `.env` (gitignored).
- Portfolio specifics (actual holdings, avg cost) → **separate "private" folder** in vault + per-user override + gitignored path (or per-user private repo submodule).
- `/raw` folder (downloaded HTML, raw responses) → gitignore; regenerate from APIs if needed.

**Confidence:** HIGH.

---

## Installation Summary

```bash
# ---- Python environment (use uv) ----
curl -LsSf https://astral.sh/uv/install.sh | sh
cd ~/workspace/stock
uv venv --python 3.12
source .venv/bin/activate

# ---- Data collection ----
uv pip install \
  dart-fss \
  pykrx \
  finance-datareader \
  PublicDataReader \
  fredapi \
  yfinance \
  trafilatura \
  beautifulsoup4 \
  requests \
  pandas \
  lxml

# ---- Korean tokenization (for BM25 preprocessing) ----
uv pip install python-mecab-ko soynlp

# ---- MCP + ingest ----
uv pip install \
  "fastmcp>=2.11,<3.0" \
  anthropic \
  ollama \
  pydantic \
  sqlalchemy \
  psycopg[binary] \
  pgvector \
  python-frontmatter \
  pyyaml \
  alembic

# ---- Graph ----
uv pip install graphifyy

# ---- Dev ----
uv pip install --dev \
  pytest \
  ruff \
  mypy

# ---- Infrastructure (separate) ----
# Docker: Postgres 17 + pgvector
docker run -d --name stock-pg \
  -e POSTGRES_PASSWORD=stock \
  -p 127.0.0.1:5432:5432 \
  -v $PWD/data/pg:/var/lib/postgresql/data \
  pgvector/pgvector:pg17

# Then psql-exec: CREATE EXTENSION vector; CREATE EXTENSION vchord_bm25; CREATE EXTENSION pg_trgm;
# (vchord_bm25 must be added to the image; build custom image or use tensorchord/vchord image)

# Ollama: LLMs + embeddings
# Install Ollama: https://ollama.com/download
ollama pull bge-m3
ollama pull qwen2.5:14b-instruct-q4_K_M
ollama pull exaone3.5:7.8b   # optional, for Korean-heavy docs
```

---

## Alternatives Considered (Summary Table)

| Layer | Recommended | Alternative | When Alternative Makes Sense |
|---|---|---|---|
| DART | `dart-fss` | `OpenDartReader` | Never (dormant) |
| KRX | `pykrx` + `FinanceDataReader` | KRX KIND direct scrape | Never (both libs already do this) |
| Naver | `requests` + `read_html` | `selenium`/`playwright` | JS-rendered pages only (rare) |
| News | `trafilatura` | `newspaper3k` / `readability` | Legacy projects only |
| Scheduler | systemd.timer | APScheduler | Only inside an always-on Python process |
| DB | Native Postgres 17 | PGLite | Single-user zero-infra demo |
| BM25 | VectorChord-BM25 | ParadeDB pg_search | Need facets/highlighting |
| Embeddings | bge-m3 | multilingual-e5-large | Marginal; no reason to switch |
| Local LLM | Qwen2.5-14B Q4 | EXAONE-3.5 | Korean-only docs, small GPU |
| Cloud LLM fallback | Haiku 4.5 | Haiku 3.5 | Lower cost, slightly older |
| MCP | FastMCP 2.x | FastMCP 3.x | Revisit Q3 2026 |

---

## What NOT to Use (Hard Vetoes)

| Avoid | Why | Use Instead |
|---|---|---|
| `OpenDartReader` | Dormant 12+ months | `dart-fss` |
| `newspaper3k` | Lower precision than trafilatura on Korean news | `trafilatura` |
| `selenium`/`playwright` for Naver | 50x slower than `requests` for SSR pages | `requests` + `read_html` |
| GitHub Actions for daily collection | Pulls local pipeline into cloud for no benefit | systemd.timer |
| Cron (naked) | No structured logs, no persistence | systemd.timer |
| APScheduler (as main scheduler) | Needs an always-on host process | systemd.timer |
| PGLite (for this project) | Single-connection, can't run VectorChord-BM25 | Native Postgres 17 |
| Elasticsearch / Meilisearch | Separate infra, overkill | VectorChord-BM25 inside Postgres |
| Llama-3.3-70B local | 40GB+ VRAM needed | Qwen2.5-14B Q4 (or Haiku via API) |
| `text-embedding-ada-002` | Obsolete OpenAI model | `bge-m3` local |
| Obsidian Bases for complex dashboards | Less powerful than Dataview | Dataview plugin |
| `openpyxl`-based 증권사 리포트 파싱 | Formats vary wildly; fragile | Extract via LLM + trafilatura |

---

## Version Compatibility Notes

| Package A | Must pair with | Gotcha |
|---|---|---|
| pgvector 0.8.0 | Postgres >= 13 (ideally 17) | `halfvec` only in 0.7+; old clients may not know it |
| VectorChord-BM25 | Postgres 14+, native install | Not available on PGLite/WASM |
| bge-m3 | PyTorch >= 2.0 OR Ollama | 8192 context needs recent transformers |
| Qwen2.5-14B Q4_K_M | llama.cpp b3000+ / Ollama 0.4+ | Older Ollama may not have Q4_K_M variant |
| FastMCP 2.x | Python >= 3.10, mcp-sdk >= 1.0 | 3.x has breaking API changes |
| trafilatura 1.12 | lxml >= 4.9 | Don't run in parallel without `concurrent.futures` — internal state is not fully thread-safe |
| graphifyy | Python 3.10-3.12 | Not yet tested on 3.13 |
| dart-fss | Python 3.8+ | Requires valid `OPEN_DART_API_KEY` env var |

---

## Confidence Summary

| Area | Confidence | Why |
|---|---|---|
| Korean data libs (DART, KRX, ECOS) | **HIGH** | Verified maintenance status via Snyk; libs have years of community use |
| News extraction (trafilatura) | **HIGH** | Peer-reviewed benchmarks (Sandia, 2024 comparative) put it #1 |
| Scheduler (systemd.timer) | **HIGH** | Architectural reasoning, APScheduler docs self-admit the limitation |
| pgvector 0.8 | **HIGH** | Changelog + neon/aws docs confirm |
| VectorChord-BM25 | **MEDIUM** | Young but credible; ParadeDB pg_search is a viable alternative |
| PGLite vs native Postgres | **HIGH** | PGLite docs explicitly state single-user mode; mismatch with our concurrency needs |
| bge-m3 for Korean | **HIGH** | MIRACL scores published; Korean community adoption |
| Qwen2.5-14B / EXAONE | **HIGH** on choice; **MEDIUM** on sizing | KoMT-Bench confirms; sizing depends on user GPU |
| Claude Haiku pricing | **HIGH** | Anthropic public pricing, verified 2026-04 |
| FastMCP version pin (2.x vs 3.x) | **MEDIUM** | 3.x is new; conservative pin is safer but may lag |
| Obsidian integration (Dataview) | **HIGH** | Standard pattern |
| llm-wiki plugin | **MEDIUM** | Optional; value depends on UX preference |
| graphify | **HIGH** | Local SKILL.md confirms usage |
| Git strategy | **HIGH** | Community consensus on .gitignore patterns |

---

## Open Questions for Phase-Specific Research

1. **Korean BM25 tokenization pipeline**: mecab-ko vs soynlp vs kiwipiepy — which has best recall on equity-research vocabulary (종목명, 섹터, 재무용어)? Benchmark on real corpus during Phase 2.
2. **Chunking strategy for bge-m3**: With 8192 context, do we chunk long DART reports at all? If yes, at what granularity (section headers vs 512-token sliding)?
3. **VectorChord-BM25 installation**: Does the `pgvector/pgvector:pg17` image need extending, or is there a pre-built `tensorchord/vchord` image with both? Verify during Phase 2 spike.
4. **bge-m3-ko vs bge-m3**: Run retrieval benchmark on a labeled sample of our own 공시+뉴스 corpus before committing to one. Expected: near-tie; pick bge-m3 (broader).
5. **FastMCP 2.x → 3.x migration path**: Revisit in Q3 2026 when 3.x is more mature.
6. **Private portfolio data segregation**: How exactly to structure the vault so 3-5 users can share market data but keep individual holdings private? Git submodule vs symlinked private folder vs per-user frontmatter overlay.

---

## Sources

### HIGH confidence (Context7-equivalent + official docs)
- [garrytan/gbrain on GitHub](https://github.com/garrytan/gbrain) — gbrain architecture, PGLite 0.4.4 + pgvector 0.2.0 pinned
- [gbrain/package.json](https://github.com/garrytan/gbrain/blob/master/package.json) — actual deps
- [PGlite v0.4 announcement](https://electric-sql.com/blog/2026/03/25/announcing-pglite-v04) — single-user mode limits confirmed
- [pgvector CHANGELOG](https://github.com/pgvector/pgvector/blob/master/CHANGELOG.md) — 0.7+ halfvec, 0.8+ binary_quantize
- [FastMCP on PyPI](https://pypi.org/project/fastmcp/) — 2.x / 3.x version state as of 2026-04
- [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) — Haiku 3.5 $0.80/$4, Haiku 4.5 $1/$5
- [LG AI Research EXAONE 3.5 technical report](https://www.lgresearch.ai/data/upload/tech_report/ko/Technical_report_EXAONE_3.5.pdf) — Korean benchmarks
- [BAAI bge-m3 on HuggingFace](https://huggingface.co/BAAI/bge-m3) — MIRACL scores
- [VectorChord-BM25](https://github.com/tensorchord/VectorChord-bm25) — BM25 extension
- [graphify SKILL.md (local)](~/.claude/skills/graphify/SKILL.md) — pipeline and outputs
- [graphify on GitHub (safishamsi/graphify)](https://github.com/safishamsi/graphify) — v4 reference
- [APScheduler docs](https://apscheduler.readthedocs.io/) — "not a daemon" self-admission

### MEDIUM confidence (community references, recent 2026 articles)
- [dart-fss Snyk advisor](https://snyk.io/advisor/python/dart-fss) — maintenance status
- [OpenDartReader Snyk advisor](https://snyk.io/advisor/python/opendartreader) — dormancy status
- [pykrx on PyPI](https://pypi.org/project/pykrx/)
- [FinanceDataReader on GitHub](https://github.com/FinanceData/FinanceDataReader)
- [PublicDataReader ECOS docs](https://github.com/WooilJeong/PublicDataReader/blob/main/assets/docs/ecos/ecos.md)
- [trafilatura news scraping comparison](https://htdocs.dev/posts/comparative-analysis-of-open-source-news-crawlers/)
- [Ollama VRAM guide 2026](https://localllm.in/blog/ollama-vram-requirements-for-local-llms)
- [Qwen2.5-14B specs (apxml)](https://apxml.com/models/qwen2-5-14b)
- [domleca/llm-wiki](https://github.com/domleca/llm-wiki)
- [Dataview plugin](https://github.com/blacksmithgu/obsidian-dataview)
- [Obsidian gitignore forum](https://forum.obsidian.md/t/what-should-i-gitignore-for-my-vaults-github-repository/101077)
- [Hybrid search with ParadeDB pg_search vs pgvector](https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual)
- [FastMCP tutorial (firecrawl)](https://www.firecrawl.dev/blog/fastmcp-tutorial-building-mcp-servers-python)

### LOW confidence (single-source, speculative)
- VectorChord-BM25 benchmark vs Elasticsearch (3x figure) — vendor self-reported, treat as directional
- bge-m3-ko vs bge-m3 quality gap on our specific corpus — unverified, needs empirical test
- Claude Haiku 4.5 cost-crossover math — rough; dependent on actual doc volume and token length

---

*Stack research for: Korean-market stock wiki (Obsidian + gbrain-style retrieval + graphify + stock-mcp)*
*Researched: 2026-04-16*
