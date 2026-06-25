"""Reusable monotonic min-interval request throttle (CAP-1, collector hardening).

Gray-area scrapers (``pykrx`` → KRX/Naver, news article HTML) have NO formal API
rate limit; the binding constraint is IP-throttle / robots politeness. The
Korean quant-community norm is 1-2 req/s (``.planning/research/STACK.md`` line 93).
``collectors.kind.client`` already paces itself at ≤1 req/s; this module
generalizes that pattern so ``krx`` and ``news`` pace their *normal* request flow
too — not just back off on failure (that is the tenacity retry layer's job).

This is a PROACTIVE politeness gate, NOT an HTTP-429 handler (see
``shared``-adjacent retry classification for 429). A single serial collector loop
is assumed (see ``collectors.dart.__init__`` rate-limit note), so the throttle is
intentionally lock-free. If a collector ever adds concurrency, wrap ``wait()`` in
a lock.
"""

from __future__ import annotations

import time

__all__ = ["Throttle"]


class Throttle:
    """Block until ``min_interval_sec`` has elapsed since the previous ``wait()``.

    The first call (or first after :meth:`reset`) never sleeps — the initial
    ``_last_ts`` of ``0.0`` is effectively "long ago" against
    ``time.monotonic()``. An interval of ``0`` makes ``wait()`` a no-op (tests
    lower the interval to keep the suite fast).
    """

    def __init__(self, min_interval_sec: float) -> None:
        if min_interval_sec < 0:
            raise ValueError(
                f"min_interval_sec must be >= 0, got {min_interval_sec!r}"
            )
        self.min_interval_sec = float(min_interval_sec)
        self._last_ts: float = 0.0

    def wait(self) -> None:
        """Sleep just long enough to keep successive calls ≥ interval apart."""
        if self.min_interval_sec <= 0:
            return
        elapsed = time.monotonic() - self._last_ts
        if 0.0 <= elapsed < self.min_interval_sec:
            time.sleep(self.min_interval_sec - elapsed)
        self._last_ts = time.monotonic()

    def reset(self) -> None:
        """Test hook: forget the last-call timestamp (next call won't sleep)."""
        self._last_ts = 0.0
