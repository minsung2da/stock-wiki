"""Unit tests for fetch_body over the OpenDART document API (no network).

The body source is ``https://opendart.fss.or.kr/api/document.xml`` → a ZIP of
one-or-more ``.xml`` members. These tests patch the HTTP seam
(``fetcher._http_get``) with in-memory ZIP / error-envelope bytes and assert:

- ZIP member is decoded + tag-stripped into the whole body (Veto #8).
- Multiple ``.xml`` members concatenate in name order (main + correction).
- cp949/euc-kr members decode via the fallback chain.
- Tags strip with a space separator (Korean words do not glue together).
- OpenDART status 013 (no document) → "" (empty-body contract, not an error).
- Any other OpenDART status → DartDocumentError, and the key never leaks.
- Missing rcept_no short-circuits to "" without an HTTP call.
- Missing DART_API_KEY raises CollectorConfigError before any HTTP call.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

import pytest

from collectors.dart import fetcher
from collectors.dart.client import CollectorConfigError
from collectors.dart.client import get_api_key as _real_get_api_key


@dataclass
class _FakeFiling:
    rcept_no: str = "20260515002181"


@dataclass
class _FakeResp:
    content: bytes

    def raise_for_status(self) -> None:
        return None


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _dummy_key(monkeypatch):
    monkeypatch.setattr("collectors.dart.client.get_api_key", lambda: "dummy-key")


def _patch_get(monkeypatch, content: bytes) -> None:
    monkeypatch.setattr(fetcher, "_http_get",
                        lambda rcept_no, api_key: _FakeResp(content))


# ----- ZIP body extraction -----


def test_fetch_body_single_xml_member(monkeypatch) -> None:
    xml = "<DOCUMENT><TITLE>분기보고서</TITLE><BODY>삼성전자 본문</BODY></DOCUMENT>"
    _patch_get(monkeypatch, _zip_bytes({"20260515002181.xml": xml.encode("utf-8")}))

    body = fetcher.fetch_body(_FakeFiling())

    assert "분기보고서" in body
    assert "삼성전자 본문" in body
    assert "<" not in body and ">" not in body  # tags stripped


def test_fetch_body_multi_member_concatenated_in_name_order(monkeypatch) -> None:
    members = {
        "20260515002181_0002.xml": b"<P>CORRECTION SECOND</P>",
        "20260515002181_0001.xml": b"<P>MAIN FIRST</P>",
    }
    _patch_get(monkeypatch, _zip_bytes(members))

    body = fetcher.fetch_body(_FakeFiling())

    assert "MAIN FIRST" in body
    assert "CORRECTION SECOND" in body
    # _0001 sorts before _0002 → main precedes correction.
    assert body.index("MAIN FIRST") < body.index("CORRECTION SECOND")


def test_fetch_body_ignores_non_xml_members(monkeypatch) -> None:
    members = {
        "doc.xml": b"<P>real body</P>",
        "image.png": b"\x89PNG not xml",
    }
    _patch_get(monkeypatch, _zip_bytes(members))

    body = fetcher.fetch_body(_FakeFiling())
    assert body.strip() == "real body"


def test_fetch_body_decodes_cp949(monkeypatch) -> None:
    # Older filings may not be UTF-8. cp949-encoded Korean must still decode.
    xml = "<P>한국어 본문 cp949</P>".encode("cp949")
    _patch_get(monkeypatch, _zip_bytes({"old.xml": xml}))

    body = fetcher.fetch_body(_FakeFiling())
    assert "한국어 본문 cp949" in body


def test_fetch_body_tag_strip_uses_space_separator(monkeypatch) -> None:
    # Adjacent table cells must NOT glue together when tags are removed.
    xml = b"<TD>\xea\xb0\x80</TD><TD>\xeb\x82\x98</TD>"  # 가 / 나 in UTF-8
    _patch_get(monkeypatch, _zip_bytes({"d.xml": xml}))

    body = fetcher.fetch_body(_FakeFiling())
    assert body == "가 나"  # space-separated, not "가나"


# ----- Error envelope handling -----


def test_fetch_body_status_013_returns_empty(monkeypatch) -> None:
    envelope = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b"<result><status>013</status>"
        b"<message>\xec\xa1\xb0\xed\x9a\x8c\xeb\x90\x9c \xeb\x8d\xb0\xec\x9d"
        b"\xb4\xed\x84\xb0\xea\xb0\x80 \xec\x97\x86\xec\x8a\xb5\xeb\x8b\x88"
        b"\xeb\x8b\xa4.</message></result>"
    )
    _patch_get(monkeypatch, envelope)

    assert fetcher.fetch_body(_FakeFiling()) == ""


def test_fetch_body_permanent_status_raises_without_key_leak(monkeypatch) -> None:
    # status 014 (file does not exist) is permanent → raises immediately, no
    # retry. (020 is now a retryable throttle — see test_dart_fetcher_retry.py.)
    envelope = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b"<result><status>014</status>"
        b"<message>file does not exist</message></result>"
    )
    _patch_get(monkeypatch, envelope)

    with pytest.raises(fetcher.DartDocumentError) as exc:
        fetcher.fetch_body(_FakeFiling())
    msg = str(exc.value)
    assert "014" in msg
    assert "file does not exist" in msg
    assert "dummy-key" not in msg  # the API key must never leak into errors
    # 014 is a base DartDocumentError, NOT a retryable throttle.
    assert not isinstance(exc.value, fetcher.DartThrottleError)


def test_fetch_body_unparseable_non_zip_raises(monkeypatch) -> None:
    _patch_get(monkeypatch, b"<html>blocked by edge</html>")

    with pytest.raises(fetcher.DartDocumentError):
        fetcher.fetch_body(_FakeFiling())


# ----- Short-circuits (no HTTP) -----


def test_fetch_body_missing_rcept_no_returns_empty_without_http(monkeypatch) -> None:
    def _boom(rcept_no, api_key):  # pragma: no cover - must not run
        raise AssertionError("HTTP must not be called for empty rcept_no")

    monkeypatch.setattr(fetcher, "_http_get", _boom)
    assert fetcher.fetch_body(_FakeFiling(rcept_no="")) == ""


def test_fetch_body_missing_api_key_raises_before_http(monkeypatch) -> None:
    monkeypatch.delenv("DART_API_KEY", raising=False)
    # Restore the real get_api_key (captured at import, before the autouse dummy
    # replaced the module attribute) so it actually reads the env var.
    monkeypatch.setattr("collectors.dart.client.get_api_key", _real_get_api_key)

    def _boom(rcept_no, api_key):  # pragma: no cover - must not run
        raise AssertionError("HTTP must not be called when key is missing")

    monkeypatch.setattr(fetcher, "_http_get", _boom)

    with pytest.raises(CollectorConfigError):
        fetcher.fetch_body(_FakeFiling())
