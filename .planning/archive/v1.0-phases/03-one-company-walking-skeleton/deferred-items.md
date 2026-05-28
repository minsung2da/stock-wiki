# Phase 3 Deferred Items (post-JUDGE-04 E2E discoveries)

## [D-1] `ingest rebuild` does not re-seed `entities` table

**Symptom:** After `stock ingest rebuild`, `resolve_entity(ticker)` returns None because rebuild wipes `entities`/`entity_aliases` but only re-ingests documents/chunks from raw/. The collector populates entities during first collect — rebuild does not call the collector.

**Impact:** Violates STORE-05 contract ("vault alone reconstructs DB"). Ticker-filtered search returns `INVALID_TICKER` after rebuild until next collect.

**Fix options:**
- A) Ingest worker reads `fm.provenance.corp_code`/`ticker`/company name during document processing and calls `upsert_entity` — covers rebuild path automatically.
- B) `stock ingest rebuild` command runs an entity-seed pass that scans vault/raw/** for corp_code frontmatter before/after chunk ingestion.

**Recommendation:** Option A. Simpler, preserves existing rebuild flow, and tightens the "vault = source of truth" invariant (DART frontmatter now seeds both documents AND entities).

**Tracked for:** Phase 4 (when multi-source collectors arrive, same pattern applies) or a follow-up quick task.

---

## [D-2] DART large-filing fetch (사업보고서) still times out

**Symptom:** 3 of 5 filings failed with `RemoteDisconnected` even after retry hardening (5 attempts, 1–30s exponential). These are 사업보고서 HTML bodies which exceed tens of MB and sometimes hundreds; DART's origin server drops connections mid-stream for them.

**Current state:** Bug B retry hardening improved small filing reliability (주요사항보고서 now succeeds consistently). Large 정기보고서 (A-type) still fragile.

**Fix options:**
- A) Streaming fetch with resumable downloads (HTTP Range requests if DART supports)
- B) Fall back to dart-fss `Report.xbrl` accessor (structured data, smaller) for large A-type
- C) Accept as-is; Phase 3 scope is walking skeleton and 주요사항(B) covers the demo

**Recommendation:** Accept for Phase 3 (B-type filings are the primary signal for "최근 공시" queries anyway). Revisit in Phase 5 when dart-fss structured accessors are used for financial numbers.
