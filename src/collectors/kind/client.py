"""KIND HTTP client — throttled GET/POST with browser-like UA (Option D).

Two-layer compliance (see docs/kind-robots-snapshot.txt + T-04-15/16):
- Monotonic throttle: ≤1 req/sec across the whole process (module-global).
- Browser-like User-Agent: minimal UAs are rejected by the KRX WAF.
- Scheme guard: only https://kind.krx.co.kr URLs accepted (SSRF defense).

EUC-KR decoding: KIND undisclosure AJAX responses are EUC-KR-encoded. Callers
that need decoded text should call `.decode_response(resp)` instead of
`.text` to guarantee the right encoding.
"""

from __future__ import annotations

import logging
import time

import requests

from collectors.kind.sources import BROWSER_UA, KIND_BASE

_log = logging.getLogger(__name__)


class KindSourceError(RuntimeError):
    """Raised when a non-KIND URL is passed to the client (T-04-10 SSRF guard)."""


class RobotsDisallowedError(RuntimeError):
    """Raised when a robots.txt (if published) disallows the target path.

    Current KIND robots.txt returns an error page (no directives); this error
    class remains defined so a future robots check can use it without API break.
    """


MIN_REQUEST_INTERVAL_SEC = 1.0
_DEFAULT_TIMEOUT = 15

_last_request_ts: float = 0.0


def _assert_kind_url(url: str) -> None:
    if not url.startswith(KIND_BASE):
        raise KindSourceError(f"url does not target KIND domain: {url!r}")


def _throttle() -> None:
    """Block until MIN_REQUEST_INTERVAL_SEC has elapsed since the last call."""
    global _last_request_ts
    elapsed = time.monotonic() - _last_request_ts
    if elapsed < MIN_REQUEST_INTERVAL_SEC:
        time.sleep(MIN_REQUEST_INTERVAL_SEC - elapsed)
    _last_request_ts = time.monotonic()


def _reset_throttle() -> None:
    """Test-only: reset the module-level monotonic timestamp."""
    global _last_request_ts
    _last_request_ts = 0.0


def throttled_get(url: str, **kwargs) -> requests.Response:
    """GET a KIND URL under the 1 req/sec throttle with a browser UA."""
    _assert_kind_url(url)
    _throttle()
    headers = {"User-Agent": BROWSER_UA}
    headers.update(kwargs.pop("headers", {}) or {})
    return requests.get(url, headers=headers, timeout=_DEFAULT_TIMEOUT, **kwargs)


def throttled_post(url: str, data: dict, **kwargs) -> requests.Response:
    """POST to a KIND URL under the 1 req/sec throttle with a browser UA."""
    _assert_kind_url(url)
    _throttle()
    headers = {"User-Agent": BROWSER_UA}
    headers.update(kwargs.pop("headers", {}) or {})
    return requests.post(url, data=data, headers=headers, timeout=_DEFAULT_TIMEOUT, **kwargs)


def decode_euckr(resp: requests.Response) -> str:
    """Return response body decoded as EUC-KR (KIND AJAX fragments)."""
    return resp.content.decode("euc-kr", errors="replace")
