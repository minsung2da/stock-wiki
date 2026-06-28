---
slug: dart-fetch-body-broken
status: resolved
trigger: "DART fetch_body fails with RemoteDisconnected on all filings — dart-fss .pages viewer scraping is blocked; switch to OpenDART document.xml API (already root-caused and validated)"
created: 2026-06-28
updated: 2026-06-28
---

# Debug: DART fetch_body fails (RemoteDisconnected on all filings)

## Symptoms

- **Expected:** `collect_dart(corp_code, since, ...)` downloads each A+B filing's
  body text and UPSERTs it into the `filings` table (whole `body_md`, Veto #8).
- **Actual:** Every filing fails. `collect_dart` for Samsung (00126380,
  since=2026-01-01, max_docs=40) returned `{"total": 8, "inserted": 0,
  "updated": 0, "skipped": 0, "failed": 8}` in 181s — all 8 failed inside
  `fetch_body`.
- **Error:** `requests.exceptions.ConnectionError: ('Connection aborted.',
  RemoteDisconnected('Remote end closed connection without response'))`,
  retried 5× per filing (tenacity exponential backoff 2/4/8/16s) then reraised.
- **Timeline:** Discovered 2026-06-28 during first real DART collection against
  the live DB (Phase 1 collectors were only ever tested with mocked fetchers /
  testcontainers; no real DART body fetch had run before).
- **Reproduction:** `collect_dart(corp_code="00126380", since="2026-01-01",
  max_docs=40, engine=get_engine())` (env loaded from .env).

## Current Focus

reasoning_checkpoint:
  hypothesis: "fetch_body uses dart-fss .pages viewer scraping (dart.fss.or.kr),
    which the server drops (RemoteDisconnected); the key-authenticated OpenDART
    document.xml API (opendart.fss.or.kr) returns the body as a ZIP and works."
  confirming_evidence:
    - "Single isolated GET document.xml?rcept_no=20260515002181 → HTTP 200,
      Content-Type application/x-msdownload, PK ZIP, 351,660 bytes in 0.218s;
      member 20260515002181.xml decodes UTF-8 (4,318,370 chars) → 394,333
      stripped Korean chars ('분 기 보 고 서 (제 58 기)...'). Re-verified in-repo."
    - "list_ab_filings (OpenDART list API, same opendart.fss.or.kr host) works —
      only the dart.fss.or.kr viewer scrape fails. Host reachable; viewer blocks."
    - "Error envelope for missing doc = 147-byte XML <status>013</status> at HTTP
      200 (non-ZIP) — clean empty-vs-error discriminator."
  falsification_test: "If document.xml returned RemoteDisconnected/ConnectionError
    like .pages, the hypothesis is wrong. It returned 200+ZIP in 0.2s → not
    falsified."
  fix_rationale: "Replacing the blocked viewer-scrape transport with the document
    API addresses the root cause (wrong/blocked transport), not a symptom. Tenacity
    retry kept for genuine network flakes; HTTPError added to retryable set."
  blind_spots: "Older filings' cp949/euc-kr XML not tested live (handled via decode
    fallback); multi-member ZIPs not in this sample (handled by concatenating sorted
    .xml members); 020 rate-limit envelope not exercised live (raises typed error)."

- **next_action:** Replace fetch_body to download document.xml (ZIP) → extract
  all .xml members → decode (utf-8/cp949/euc-kr) → strip tags → return whole text.
  Add client.get_api_key(). Rewrite tests/test_dart_fetcher_retry.py onto the new
  _http_get seam. Run pytest tests/collectors/dart tests/collectors and the retry
  suite.
- **test:** Mocked-ZIP unit tests for fetch_body + existing collect_dart suite
  green; optional ONE live collect_dart(00126380) smoke (inserted>0, failed=0).
- **expecting:** fetcher returns decoded stripped body from ZIP; 013 → ""; other
  statuses → DartDocumentError; all existing dart tests green.

## Evidence (already gathered by orchestrator — verify, don't re-derive)

- timestamp 2026-06-28: `list_ab_filings` (OpenDART **list** API,
  opendart.fss.or.kr, key-auth) WORKS — returns 8 filings for Samsung.
- timestamp 2026-06-28: `fetch_body` via dart-fss `.pages` FAILS — single
  isolated `pages[0].html` access raises
  `ConnectionError RemoteDisconnected`. Not transient: reproduced across all 8
  filings + an isolated single-filing probe.
- timestamp 2026-06-28: **Path A validated** — direct GET
  `https://opendart.fss.or.kr/api/document.xml?crtfc_key=<DART_API_KEY>&rcept_no=<rcept_no>`
  returns HTTP 200, `Content-Type: application/x-msdownload`, a ZIP
  (`PK\x03\x04` magic) of 351,660 bytes in **0.2s**. ZIP member:
  `20260515002181.xml`.
- timestamp 2026-06-28: ZIP member decodes as **UTF-8** (4,318,370 chars XML);
  tag-stripping (`re.sub(r"<[^>]+>", " ", xml)` + whitespace collapse) yields
  **394,333 chars** of clean Korean body text. Verified sample renders correctly
  ("분 기 보 고 서 (제 58 기) … 삼성전자주식회사 … II. 사업의 내용 …").
- Distinction: list endpoint = OpenDART API (works); body endpoint = dart-fss
  viewer scrape (broken). Fix = move body fetch onto the OpenDART document API
  we already have a key for.

## Constraints (must hold for any fix)

- **Veto #8:** whole `body_md`, no pre-chunking on insert. The `chunks` table is
  not touched by this collector.
- **Veto #9:** no Markdown vault writes; no `vault_root`.
- **COLL-07:** no `anthropic` / `openai` imports in collectors.
- **Serial only:** do NOT parallelize across filings/corps (DART rate limit).
- **DART_API_KEY** comes from env via `collectors.dart.client.get_client()`.
- Keep `fetch_body(filing)` signature and the per-filing isolation in
  `collect_dart` (a single filing failure must not abort the run).
- Document XML encoding: try UTF-8 first, fall back to cp949/euc-kr (older
  filings may not be UTF-8).
- Multi-member ZIP: a filing may contain more than one .xml (main + corrections);
  concatenate all `.xml` members in order.

## Eliminated

- (none yet)

## Resolution

- root_cause: `fetch_body` fetched filing bodies by scraping the DART document
  *viewer* (dart.fss.or.kr) via dart-fss `.pages` → `page.html`; that viewer
  drops scraper connections server-side, so every fetch raised
  `ConnectionError(RemoteDisconnected)` and all filings landed in
  `stats["failed"]`. The OpenDART *API* host (opendart.fss.or.kr) — already used
  successfully by `list_ab_filings` — was never the problem.
- fix: Rewrote `fetch_body` (src/collectors/dart/fetcher.py) to download the body
  from the OpenDART document API
  (`GET https://opendart.fss.or.kr/api/document.xml?crtfc_key=<key>&rcept_no=<no>`)
  via `requests`. Response is a ZIP → extract every `.xml` member (sorted by
  name) → decode (utf-8 → cp949 → euc-kr) → tag-strip with a space separator →
  return the whole concatenated text (Veto #8, no chunking). Non-ZIP envelopes:
  status 013 (no document) → `""` (empty-body contract); any other status →
  new typed `DartDocumentError` (key never logged). Tenacity retry kept
  (added `requests.HTTPError` for transient 5xx). Added `client.get_api_key()`.
- verification:
  - Isolated GET of rcept_no 20260515002181 → HTTP 200, application/x-msdownload,
    PK ZIP, 351,660 bytes in 0.22s; member decodes UTF-8 → 394,333 stripped
    Korean chars. Error envelope for a bogus rcept_no = 147-byte XML status 013.
  - Unit: tests/collectors/dart/test_fetcher.py (12) + rewritten
    tests/test_dart_fetcher_retry.py (6) — all pass; mock the `_http_get` seam,
    never hit the network.
  - Regression: `pytest tests/collectors/dart tests/collectors` → 164 passed;
    `tests/test_import_guard.py` (COLL-07) → 4 passed.
  - Live end-to-end: `collect_dart(00126380, since=2026-04-01, max_docs=3)` →
    total=1, inserted=1, failed=0; stored `filings.body_md` = 394,333 chars
    (byte-exact with the isolated verification).
- files_changed:
  - src/collectors/dart/fetcher.py (fetch_body rewritten onto OpenDART
    document.xml; added DartDocumentError, _http_get, _extract_zip_text,
    _handle_error_envelope, _decode, _strip_xml; removed .pages/_strip_html)
  - src/collectors/dart/client.py (added get_api_key accessor)
  - tests/collectors/dart/test_fetcher.py (new — document.xml extraction)
  - tests/test_dart_fetcher_retry.py (rewritten onto the _http_get seam)
