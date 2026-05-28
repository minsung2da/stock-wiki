---
phase: 03-one-company-walking-skeleton
plan: 03
subsystem: ingest
tags: [ingest, injection-defense, embedder, tokenizer, chunking, parsers, security]

requires:
  - phase: 03-one-company-walking-skeleton
    plan: 01
    provides: "chunks.section_path/section_index/bm25_tokens schema + EMBEDDING_MODEL_VERSION locking"
provides:
  - "src/ingest/injection_defense.py — PATTERNS (6-family table) + wrap_untrusted + detect_injection_patterns + is_adversarial"
  - "src/ingest/tokenizer.py — tokenize_ko (mecab-ko NNG/NNP/SL/SN → blake2s int32)"
  - "src/ingest/embedder.py — Embedder class + EMBEDDING_MODEL_VERSION='BAAI/bge-m3@v1' + encode_query LRU(256)"
  - "src/ingest/chunking.py — Chunk dataclass + chunk_document(max_tokens=1500, win=512, overlap=64)"
  - "src/ingest/parsers/__init__.py — parse_sections(body, source) dispatch, generic ValueError on unknown source"
  - "src/ingest/parsers/dart.py — Section dataclass + Roman/Arabic TOC heading split with (root) fallback"
affects: [03-04, 03-05]

tech-stack:
  added: []
  patterns:
    - "Lazy SentenceTransformer import inside Embedder.__init__ — keeps version constant import torch-free"
    - "Lazy AutoTokenizer load via module-level _get_tok() so tests monkeypatch with a fake tokenizer (no 2GB HF download in CI)"
    - "Pattern IDs stable across releases — downstream ingest_state.injection_flags queries depend on snapshot"
    - "Generic ValueError messages (no user value interpolation) for T-3-15 info-disclosure hardening"
    - "Content-POS frozenset filter for mecab tokens: {NNG, NNP, SL, SN}"
    - "chunk_index monotonic per document; section_index resets per section (Q4 resolution)"

key-files:
  created:
    - src/ingest/injection_defense.py
    - src/ingest/tokenizer.py
    - src/ingest/embedder.py
    - src/ingest/chunking.py
    - src/ingest/parsers/__init__.py
    - src/ingest/parsers/dart.py
    - tests/test_injection_defense.py
    - tests/test_bm25_tokenizer.py
    - tests/test_embedder.py
    - tests/test_parsers.py
  modified:
    - pyproject.toml

key-decisions:
  - "injection_defense lives under src/ingest/ (per plan files_modified list) — leaf utility consumed by both worker (Plan 04) and MCP (Plan 05); no import of DB or LLM libs"
  - "Embedder lazy-imports SentenceTransformer so that E3 test_embedding_model_version_constant runs without torch"
  - "Hash-vocab int32 (blake2s digest_size=4 & 0x7FFFFFFF) — Phase-3 shortcut; Pattern 4 documents birthday-collision rationale"
  - "chunking._get_tok uses module-level global + lazy load so tests can monkeypatch the function without importing transformers"
  - "parsers.__init__ re-exports Section from .dart for ergonomic imports; dispatcher does NOT leak the user-supplied source in ValueError messages"
  - "Registered 'slow' pytest marker in pyproject.toml so E1/E2/E4 slow tests are deselectable without unknown-mark warnings"

patterns-established:
  - "Module-level lazy singletons with _get_X() accessor: tokenizer _mc, chunker _tok — balances import cost vs test-friendliness"
  - "Pattern-family table: ordered list[tuple[id, re.Pattern]] with snapshot test guaranteeing ID stability"
  - "Attribute-safety regex pattern: _SAFE_ATTR_RE + _SAFE_DOC_ID_RE at wrap_untrusted entry"

requirements-completed: [INGEST-08, INGEST-09, INGEST-10, INGEST-11, INGEST-12]

duration: 11min
completed: 2026-04-17
---

# Phase 03 Plan 03: Ingest Leaf Utilities Summary

**Ship the ingest worker's self-contained leaf modules — D-18 injection pattern prefilter + D-16 XML delimiter, mecab-ko BM25 tokenizer (D-12), bge-m3 embedder (INGEST-10/12), section-aware chunker (D-05), and DART TOC parser (D-07) — each DB-free and unit-tested so Plan 04's worker can compose them.**

## Performance

- **Duration:** ~11 min
- **Started:** 2026-04-17T13:54:35Z
- **Completed:** 2026-04-17T14:05Z
- **Tasks:** 3
- **Files created:** 10 (6 source + 4 test)
- **Files modified:** 1 (pyproject.toml — slow marker registration)

## Accomplishments

- **injection_defense.py** — 6-family pattern table with STABLE IDs (`EN_IGNORE_PREV`, `FAKE_SYSTEM_TAG`, `DAN_MODE`, `ROLEPLAY_ADMIN`, `KO_IGNORE_PREV`, `KO_ADMIN_MODE`) exactly as seeded in D-18. `wrap_untrusted` emits the D-16 XML delimiter literally and validates `source`/`trust_level`/`doc_id` with strict regex classes — on failure raises generic `ValueError` that never echoes the offending value (T-3-15 info-disclosure hardening). `detect_injection_patterns` returns span-sorted match dicts with 80-char match truncation. `is_adversarial` is the INGEST-09 gate.
- **tokenizer.py** — `tokenize_ko(text)` runs mecab-ko with `_CONTENT_POS = {NNG, NNP, SL, SN}`, lowercases surface, hashes to 32-bit positive int via `blake2s(digest_size=4) & 0x7FFFFFFF`. D-12 contract: same function used for both ingest and query tokenization.
- **embedder.py** — `EMBEDDING_MODEL_VERSION = "BAAI/bge-m3@v1"` module constant (exported via `__all__`). `Embedder` class lazy-imports `sentence_transformers.SentenceTransformer` inside `__init__` so the version-constant test runs without torch. `get_default_embedder()` provides a process-wide singleton. `@functools.lru_cache(maxsize=256) encode_query(q)` returns a tuple for hashability (D-11).
- **chunking.py** — `@dataclass Chunk`, `chunk_document(sections, max_tokens=1500, win=512, overlap=64)`. For each Section: if `len(ids) <= max_tokens` emit one Chunk with `section_index=0`, else slide `win-overlap=448`-step windows and emit Chunks with increasing `section_index`. `chunk_index` is monotonic per document (no reset — Q4 decision).
- **parsers/__init__.py + parsers/dart.py** — DART parser uses Roman-numeral (`I. …`) and Arabic-numeral (`1. …`) heading regexes with a two-level stack for `section_path` hierarchy. Fallback: single `(root)` Section when no headings present (for short 주요사항 filings). Dispatch raises generic `ValueError` for unknown sources.
- **27/27 fast tests green** (13 injection + 5 tokenizer + 1 embedder version-constant + 8 chunking/parser). 3 slow embedder tests (`E1`/`E2`/`E4`) registered under `pytest.mark.slow` and run on demand with warm HF cache.
- **No `anthropic`/`openai` imports** anywhere under `src/ingest/` — `grep -rE '(import|from) (anthropic|openai)' src/ingest/` prints nothing (CI guard clean).

## Task Commits

1. **Task 1: injection_defense module (INGEST-08/09, D-15/16/18)** — `ba81661` (feat)
2. **Task 2: bge-m3 embedder + mecab-ko tokenizer (INGEST-10/11/12, D-11/12)** — `424a1d9` (feat)
3. **Task 3: section-aware chunker + DART TOC parser (D-05/D-07/D-08)** — `31cdfdc` (feat)

## Canonical Constants (for Plan 04 + Plan 05 consumers)

### EMBEDDING_MODEL_VERSION

```python
from ingest.embedder import EMBEDDING_MODEL_VERSION
# EMBEDDING_MODEL_VERSION == "BAAI/bge-m3@v1"
```

This is the EXACT string Plan 04 writes to `chunks.embedding_model`. D-27 reuse policy compares `chunks.embedding_model == EMBEDDING_MODEL_VERSION` at ingest-rebuild time. Any version bump here triggers a full re-embed.

### Tokenizer content-POS set

```python
_CONTENT_POS = frozenset({"NNG", "NNP", "SL", "SN"})
```

- `NNG` — general noun
- `NNP` — proper noun
- `SL` — foreign/latin token (e.g., "KOSPI", "5G")
- `SN` — number (e.g., "2026", "74.9")

All josa (JKS/JKO/JKG/JX), endings (EF/EC/EP), verb/adjective stems (VV/VA), symbols, and punctuation are filtered out.

### Chunking index rule (Q4 resolution)

- `chunk_index`: **monotonic per document**. Never resets at a section boundary. Matches the existing `chunks.chunk_index INT` semantics from Phase 2 migration 0001.
- `section_index`: **resets to 0 at each new section**. `0` for sections that fit in a single chunk; `0..N` for sections split by the D-05 second pass.

### PATTERNS ID snapshot

For downstream frontmatter queries (`ingest_state.injection_flags: [pattern_ids]`):

```python
[
    "EN_IGNORE_PREV",
    "FAKE_SYSTEM_TAG",
    "DAN_MODE",
    "ROLEPLAY_ADMIN",
    "KO_IGNORE_PREV",
    "KO_ADMIN_MODE",
]
```

Order is stable. New pattern families append to the end; existing IDs never rename.

## Decisions Made

- **injection_defense lives under `src/ingest/` (not `src/shared/`).** Plan's `files_modified` list names `src/ingest/injection_defense.py`; consumers are both the worker (Plan 04) and MCP (Plan 05). Keeping it under `ingest/` matches RESEARCH.md §Architecture structure and avoids pulling `shared/` into the MCP server's import surface. MCP can import from `ingest.injection_defense` (no DB or LLM deps) without pulling the full worker.
- **Lazy SentenceTransformer import inside `Embedder.__init__`.** Alternative: top-level `from sentence_transformers import SentenceTransformer`. Rejected — the version-constant test (E3) must run on CI without a 2.3GB model download. Lazy import means `from ingest.embedder import EMBEDDING_MODEL_VERSION` costs zero torch/transformers import time.
- **Chunking uses module-level `_get_tok()` accessor** instead of a top-level `_tok = AutoTokenizer.from_pretrained(...)` binding. Rejected top-level because the bge-m3 tokenizer pulls ~500MB. The accessor is trivially monkeypatchable from tests (see `_DummyTok` in `tests/test_parsers.py`), keeping Task 3's 8 tests fully offline.
- **Hash-vocab IDs (blake2s 4-byte) — Phase-3 shortcut.** No vocab table; VectorChord-BM25 computes IDF from the INT[] contents. Pattern 4 documents the collision-risk math (~50k tokens over 2^31 space = negligible birthday risk). v2 may introduce a vocab table if IDF accuracy becomes measurable.
- **DART parser uses regex heading split, not `dart-fss Report.to_dict()` TOC accessor.** Plan 02 collector stores only plain-text body (`.pages` stripped), so by this layer we have no access to the structured Report object. Regex scanner is adequate for Phase-3 scope (documented as Assumption A4 follow-up); Plan 04 or v2 may upgrade to pass the structured TOC through if needed.
- **Registered `slow` pytest marker in `pyproject.toml`** to allow clean `-m 'not slow'` runs without "unknown mark" warnings. Small config hygiene change; no behavior impact.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test assumption about mecab-ko standalone-josa parsing**
- **Found during:** Task 2 (first `pytest tests/test_bm25_tokenizer.py`)
- **Issue:** Original `test_tokenize_ko_content_only` asserted `tokenize_ko("의 은 는 가 이") == []`, on the assumption that Korean josa in isolation would tag as JKG/JX. In practice mecab-ko (context-free) mis-tags standalone `의` as NNG and `은` as NNG — only inside a real sentence do they correctly resolve. Phase-3 ingest only ever sees real sentences, so this is a test-design bug, not a tokenizer bug.
- **Fix:** Replaced the standalone-josa check with an in-context check: `tokenize_ko("삼성전자 실적 증가") ⊆ tokenize_ko("삼성전자의 실적은 증가하였다")` AND the full tokenization is within +2 tokens of the content-only baseline. This correctly demonstrates josa filtering in real-world input.
- **Files modified:** `tests/test_bm25_tokenizer.py`
- **Verification:** 5/5 tokenizer tests green; probe output confirms in-context `의 | JKG`, `은 | JX` are correctly filtered.
- **Committed in:** `424a1d9`

**2. [Rule 3 - Blocking] Unknown `slow` pytest marker warning**
- **Found during:** Task 2 (first `pytest -m 'not slow'` run)
- **Issue:** `pytest.mark.slow` emits PytestUnknownMarkWarning without explicit registration in `pyproject.toml`. Warnings accumulate across test files and obscure real output.
- **Fix:** Added `markers = ["slow: marks tests as slow (deselect with -m 'not slow')"]` under `[tool.pytest.ini_options]`.
- **Files modified:** `pyproject.toml`
- **Verification:** `pytest -m 'not slow'` runs warning-free.
- **Committed in:** `424a1d9`

---

**Total deviations:** 2 auto-fixed (1 Rule 1 bug in test, 1 Rule 3 blocking warning). Neither changes plan intent.

## Known Stubs

None. All modules are fully functional; there are no hardcoded empty returns flowing to downstream consumers. The slow bge-m3 tests (E1/E2/E4) are gated by `pytest.mark.slow` + optional `HF_HUB_OFFLINE=1` skip — this is a CI optimization, not a stub.

## Threat Flags

None. All new surface is explicitly covered by the plan's `<threat_model>`:
- Prompt injection (T-3-01) → 6-pattern prefilter + D-16 delimiter ✓
- HF supply chain (T-3-11) → documented accept; lazy load doesn't widen the window
- Resource exhaustion (T-3-14) → D-05 1500/512/64 bounds enforced in chunk_document
- Info disclosure (T-3-15) → generic ValueError in `parsers/__init__.py` + `wrap_untrusted`

## Test Coverage

- `tests/test_injection_defense.py` — 13 tests: D-16 format, attribute validation (incl. info-leak guard), all 6 pattern families, clean-text negative, multi-match ordering, `is_adversarial` gate, PATTERN ID snapshot, result-shape assertion
- `tests/test_bm25_tokenizer.py` — 5 tests: int32 range, determinism, josa filtering (in-context), empty input, D-12 query↔index overlap
- `tests/test_embedder.py` — 4 tests: E3 constant (fast, 1 runs on CI), E1/E2/E4 shape+norm/batch/LRU-cache (slow marker — runs on demand)
- `tests/test_parsers.py` — 8 tests: single-short/long-split chunks, monotonic chunk_index, section_path preservation, DART single-root fallback, DART TOC hierarchical split, unknown-source raise + info-leak guard

**Fast subset: 27 green in ~1.2s.**

## User Setup Required

None for Plan 03. When Plan 04's worker first runs, the bge-m3 model (~2.3GB) will download from HuggingFace. Users behind corporate proxies or offline should pre-download:

```bash
uv run --group ingest python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"
```

## Next Phase Readiness

- **Plan 04 (ingest worker)** unblocked: all composition primitives ready. Worker flow is `read_frontmatter(path)` → `parse_sections(body, source)` → `chunk_document(sections)` → `Embedder.encode([c.text for c in chunks])` → `tokenize_ko(c.text)` for each chunk → INSERT with `embedding_model=EMBEDDING_MODEL_VERSION`.
- **Plan 05 (MCP hybrid_search)** unblocked: `encode_query(q)` gives a cached query vector; `tokenize_ko(q)` gives the BM25 token array (D-12 same-pipeline guarantee).
- **Plan 06 (stock-mcp server)** unblocked for the excerpt-wrapping side: `wrap_untrusted(body, source, trust_level, doc_id)` can be repurposed (or a sibling `wrap_vault_excerpt` helper added) for D-17 `<vault_excerpt>` delimiter.

---
*Phase: 03-one-company-walking-skeleton*
*Completed: 2026-04-17*

## Self-Check: PASSED

- `src/ingest/injection_defense.py`: FOUND
- `src/ingest/tokenizer.py`: FOUND
- `src/ingest/embedder.py`: FOUND
- `src/ingest/chunking.py`: FOUND
- `src/ingest/parsers/__init__.py`: FOUND
- `src/ingest/parsers/dart.py`: FOUND
- `tests/test_injection_defense.py`: FOUND
- `tests/test_bm25_tokenizer.py`: FOUND
- `tests/test_embedder.py`: FOUND
- `tests/test_parsers.py`: FOUND
- Commit `ba81661`: FOUND in git log
- Commit `424a1d9`: FOUND in git log
- Commit `31cdfdc`: FOUND in git log
- 27/27 fast tests green; CI import guard clean (no anthropic/openai in src/ingest/)
