"""Unit tests for shared.throttle.Throttle (CAP-1 collector hardening)."""

from __future__ import annotations

import time

import pytest

from shared.throttle import Throttle


def test_first_call_does_not_sleep() -> None:
    """A fresh throttle must not block on its first wait() even with a big interval."""
    t = Throttle(10.0)
    start = time.monotonic()
    t.wait()
    assert time.monotonic() - start < 0.5


def test_second_call_waits_min_interval() -> None:
    """Back-to-back calls are spaced by at least min_interval_sec."""
    interval = 0.15
    t = Throttle(interval)
    t.wait()  # primes _last_ts
    start = time.monotonic()
    t.wait()  # must sleep ~interval
    assert time.monotonic() - start >= interval * 0.9


def test_zero_interval_is_noop() -> None:
    """interval=0 disables throttling (used by tests to run fast)."""
    t = Throttle(0.0)
    start = time.monotonic()
    t.wait()
    t.wait()
    assert time.monotonic() - start < 0.05


def test_reset_clears_last_timestamp() -> None:
    """After reset(), the next call behaves like a first call (no sleep)."""
    interval = 0.15
    t = Throttle(interval)
    t.wait()
    t.reset()
    start = time.monotonic()
    t.wait()
    assert time.monotonic() - start < 0.05


def test_negative_interval_rejected() -> None:
    with pytest.raises(ValueError):
        Throttle(-1.0)
