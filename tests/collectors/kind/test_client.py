"""Unit tests for collectors.kind.client — throttle + scheme guard + EUC-KR."""

from __future__ import annotations

import time

import pytest

from collectors.kind import client as kind_client
from collectors.kind.client import KindSourceError


def test_non_kind_url_rejected():
    with pytest.raises(KindSourceError):
        kind_client.throttled_get("https://evil.example.com/x")
    with pytest.raises(KindSourceError):
        kind_client.throttled_post("http://kind.krx.co.kr/x", {})  # http:// not https


def test_throttle_enforces_min_interval(monkeypatch):
    """Two back-to-back throttled calls must take ≥ MIN_REQUEST_INTERVAL_SEC."""
    kind_client._reset_throttle()

    calls = []

    class _FakeResp:
        def raise_for_status(self):  # noqa: D401
            return None

        content = b""
        text = ""

    def _fake_get(url, **kwargs):
        calls.append(time.monotonic())
        return _FakeResp()

    monkeypatch.setattr("collectors.kind.client.requests.get", _fake_get)

    t0 = time.monotonic()
    kind_client.throttled_get("https://kind.krx.co.kr/investwarn/undisclosure.do")
    kind_client.throttled_get("https://kind.krx.co.kr/investwarn/undisclosure.do")
    elapsed = time.monotonic() - t0
    assert elapsed >= kind_client.MIN_REQUEST_INTERVAL_SEC * 0.9  # small slack
    assert len(calls) == 2


def test_decode_euckr_fixture():
    """undisclosure_ajax_page1.html is EUC-KR; decode produces Korean readable text."""
    from pathlib import Path

    fixture = Path(__file__).resolve().parents[2] / "fixtures/kind/undisclosure_ajax_page1.html"
    raw = fixture.read_bytes()

    class _Resp:
        content = raw

    text = kind_client.decode_euckr(_Resp())  # type: ignore[arg-type]
    assert "불성실" in text or "지정일" in text or "회사명" in text
