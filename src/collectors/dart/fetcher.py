"""DART filing list + body accessors (D-01, D-04).

D-01: Only 공시유형 A(정기보고서) + B(주요사항보고서) are collected. C/D are
scaffolded in the source_type enum but not fetched in Phase 3.

D-04: Attachments (PDF/HWP) are NOT parsed. Body text only.

Body source (2026-06-28 fix — debug session dart-fetch-body-broken):
``fetch_body`` downloads each filing's body via the **OpenDART document API**
(``https://opendart.fss.or.kr/api/document.xml``, key-authenticated). The
response is a ZIP of one-or-more ``.xml`` members; we decode and tag-strip
them into the whole body text (Veto #8 — no chunking).

This replaced the previous dart-fss ``.pages`` strategy, which scraped the
DART *document viewer* (``dart.fss.or.kr``) and was blocked server-side
(every fetch raised ``RemoteDisconnected``). The OpenDART API host is the
same one ``list_ab_filings`` already uses successfully.

``fetch_body`` retries transient network failures (flakes, rate-limit
spikes) via tenacity. OpenDART application errors (non-ZIP envelopes) are
NOT retried: status 013 (no document) returns ``""`` per the empty-body
contract; any other status raises ``DartDocumentError``.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from typing import Any

import requests
from requests.exceptions import ChunkedEncodingError
from requests.exceptions import ConnectionError as ReqConnectionError
from requests.exceptions import HTTPError as ReqHTTPError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from urllib3.exceptions import ProtocolError

from collectors.dart import client

_log = logging.getLogger(__name__)

# OpenDART document API — returns a ZIP of the filing's XML body member(s).
_DOCUMENT_API_URL = "https://opendart.fss.or.kr/api/document.xml"

# (connect, read) timeout. 사업보고서 ZIPs can be a few hundred KB; the read
# leg is generous to tolerate large reports while still failing a dead socket.
_HTTP_TIMEOUT: tuple[float, float] = (10.0, 120.0)

# OpenDART status code returned when a filing has no document to serve. This is
# a legitimate empty body (some 주요사항보고서), NOT a failure → return "".
_NO_DATA_STATUS = "013"

# Transient network classes surfaced with large 사업보고서 bodies:
# requests -> urllib3 -> http.client. ProtocolError wraps RemoteDisconnected;
# ChunkedEncodingError covers truncated Transfer-Encoding:chunked responses;
# ReqConnectionError is the umbrella for DNS/socket flakes; HTTPError covers
# transient 5xx from the OpenDART edge (raised by resp.raise_for_status()).
_RETRYABLE_EXC: tuple[type[BaseException], ...] = (
    ReqConnectionError,
    ChunkedEncodingError,
    ProtocolError,
    ReqHTTPError,
)

# Encodings tried in order. OpenDART XML is UTF-8 today; older filings may be
# cp949/euc-kr (cp949 is a superset of euc-kr — euc-kr kept as a last resort).
_DECODE_ENCODINGS: tuple[str, ...] = ("utf-8", "cp949", "euc-kr")


class DartDocumentError(RuntimeError):
    """OpenDART document.xml returned an error envelope (non-013).

    Carries the OpenDART status code + message and the public rcept_no. Never
    includes the API key (the envelope itself does not echo the key).
    """


def list_ab_filings(corp_code: str, since: str, max_docs: int) -> list[Any]:
    """List A+B filings for a corp since a date, capped at max_docs (D-03).

    Parameters
    ----------
    corp_code : str
        8-digit DART corp code.
    since : str
        ISO date "YYYY-MM-DD" — converted to dart-fss "YYYYMMDD" internally.
    max_docs : int
        Phase-3 cap (D-03).

    Returns
    -------
    list
        dart-fss Report instances (up to max_docs).
    """
    corp = client.find_corp(corp_code)
    bgn_de = since.replace("-", "")
    results = corp.search_filings(
        bgn_de=bgn_de,
        pblntf_ty=["A", "B"],  # D-01: only 정기 + 주요사항
        last_reprt_at="Y",
    )
    # SearchResults.report_list holds Report instances; fallback to iter(results)
    # for mock stubs that return a plain list.
    report_list = getattr(results, "report_list", results)
    return list(report_list)[:max_docs]


def _http_get(rcept_no: str, api_key: str) -> requests.Response:
    """Single GET against the OpenDART document API (patchable test seam).

    Raises ``requests.HTTPError`` on a non-2xx status (transient 5xx are then
    retried by ``fetch_body``). OpenDART returns HTTP 200 for application-level
    errors (e.g., status 013), so the envelope is inspected by the caller.
    """
    resp = requests.get(
        _DOCUMENT_API_URL,
        params={"crtfc_key": api_key, "rcept_no": rcept_no},
        timeout=_HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    return resp


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1.0, min=1.0, max=30.0),
    retry=retry_if_exception_type(_RETRYABLE_EXC),
    before_sleep=before_sleep_log(_log, logging.WARNING),
    reraise=True,
)
def fetch_body(filing: Any) -> str:
    """Return the whole body text of a DART filing (Veto #8 — no chunking).

    Downloads ``document.xml`` (a ZIP) from the OpenDART API for the filing's
    ``rcept_no``, decodes every ``.xml`` member, strips tags, and returns the
    concatenated text. A filing with no document (OpenDART status 013) returns
    ``""`` rather than raising; any other OpenDART error raises
    ``DartDocumentError``.
    """
    rcept_no = str(getattr(filing, "rcept_no", "") or "")
    if not rcept_no:
        return ""

    api_key = client.get_api_key()
    resp = _http_get(rcept_no, api_key)
    content = resp.content or b""

    # ZIP magic "PK" → the real document. Otherwise it's an OpenDART envelope.
    if content[:2] == b"PK":
        return _extract_zip_text(content)
    return _handle_error_envelope(content, rcept_no)


def _extract_zip_text(content: bytes) -> str:
    """Decode + tag-strip every ``.xml`` member of the document ZIP.

    Members are concatenated in name order so a filing's main XML and any
    correction XML land in a stable sequence.
    """
    texts: list[str] = []
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = sorted(n for n in zf.namelist() if n.lower().endswith(".xml"))
        for name in names:
            xml = _decode(zf.read(name))
            stripped = _strip_xml(xml)
            if stripped:
                texts.append(stripped)
    return "\n\n".join(texts)


def _handle_error_envelope(content: bytes, rcept_no: str) -> str:
    """Map a non-ZIP OpenDART response to "" (no data) or raise DartDocumentError."""
    text = _decode(content)
    status_match = re.search(r"<status>\s*([0-9]+)\s*</status>", text)
    status = status_match.group(1) if status_match else None

    if status == _NO_DATA_STATUS:
        _log.info(
            "dart_document_no_data",
            extra={"rcept_no": rcept_no, "status": status},
        )
        return ""

    msg_match = re.search(r"<message>\s*(.*?)\s*</message>", text, re.DOTALL)
    message = msg_match.group(1) if msg_match else "unrecognized non-ZIP response"
    raise DartDocumentError(
        f"OpenDART document.xml error for rcept_no={rcept_no}: "
        f"status={status} message={message}"
    )


def _decode(raw: bytes) -> str:
    """Decode DART bytes trying UTF-8 → cp949 → euc-kr; last resort lossy UTF-8."""
    for enc in _DECODE_ENCODINGS:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _strip_xml(xml: str) -> str:
    """Tag-strip DART document XML to plain text.

    Replaces each tag with a single space (so adjacent cells/paragraphs do not
    glue together — important for Korean body text) and collapses runs of
    whitespace. Matches the extraction validated against a live 분기보고서
    (394,333 chars from member 20260515002181.xml).
    """
    no_tags = re.sub(r"<[^>]+>", " ", xml)
    return re.sub(r"\s+", " ", no_tags).strip()
