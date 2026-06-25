"""collectors.krx.client proactive-throttle wiring (CAP-1).

pykrx is stubbed via sys.modules so these tests need neither the pykrx package
nor a network call — they only assert that the scrape calls pass through the
shared politeness throttle.
"""

from __future__ import annotations

import sys
import time
import types

from collectors.krx import client as krx_client


def _install_fake_pykrx(monkeypatch) -> None:
    """Inject a fake ``pykrx`` whose stock funcs return sentinels (no network)."""
    fake_stock = types.SimpleNamespace(
        get_market_ohlcv_by_date=lambda *a, **k: "OHLCV",
    )
    fake_pykrx = types.ModuleType("pykrx")
    fake_pykrx.stock = fake_stock  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pykrx", fake_pykrx)
    monkeypatch.setitem(sys.modules, "pykrx.stock", fake_stock)


def test_get_ohlcv_paces_back_to_back_calls(monkeypatch) -> None:
    """Two consecutive get_ohlcv calls are spaced by >= the throttle interval."""
    interval = 0.12
    monkeypatch.setattr(krx_client._throttle, "min_interval_sec", interval)
    krx_client._throttle.reset()
    _install_fake_pykrx(monkeypatch)

    # First call primes the throttle (no sleep on a fresh/reset throttle).
    assert krx_client.get_ohlcv("005930", "20260417") == "OHLCV"

    start = time.monotonic()
    assert krx_client.get_ohlcv("005930", "20260417") == "OHLCV"
    assert time.monotonic() - start >= interval * 0.9
