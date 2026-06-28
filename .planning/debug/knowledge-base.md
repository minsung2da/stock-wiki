# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## dart-fetch-body-broken — DART fetch_body RemoteDisconnected on all filings (viewer-scrape blocked)
- **Date:** 2026-06-28
- **Error patterns:** RemoteDisconnected, ConnectionError, Connection aborted, fetch_body, dart-fss, .pages, document viewer, collect_dart all filings failed
- **Root cause:** `fetch_body` scraped the DART document viewer (dart.fss.or.kr) via dart-fss `.pages`/`page.html`; the viewer drops scraper connections server-side, so every body fetch raised ConnectionError(RemoteDisconnected) and all filings landed in stats["failed"]. The OpenDART API host (opendart.fss.or.kr), used by list_ab_filings, was never the problem.
- **Fix:** Rewrote fetch_body to download bodies from the OpenDART document API (GET opendart.fss.or.kr/api/document.xml?crtfc_key=...&rcept_no=...) → ZIP → extract .xml members (sorted) → decode utf-8/cp949/euc-kr → tag-strip with space separator → whole text (Veto #8). Non-ZIP envelope: status 013 → ""; else DartDocumentError. Kept tenacity retry (+ HTTPError). Added client.get_api_key().
- **Files changed:** src/collectors/dart/fetcher.py, src/collectors/dart/client.py, tests/collectors/dart/test_fetcher.py, tests/test_dart_fetcher_retry.py
---
