"""Cross-module ticker shape-guard matrix (DB-free) — quick-260628-mh9 Bug 1.

The six collector / entity write paths each carry an identical ``_TICKER_RE``
pre-bind shape guard. BUG 1: KRX's new-style 6-char alphanumeric short codes
(e.g. "0001A0" for 덕양에너젠) were rejected by the old ``^[0-9]{6}$`` guard,
blocking every filing/entity write for any new-style-ticker company.

This module imports ``_TICKER_RE`` from all six modules and parametrizes the
SAME accept/reject matrix over every one of them — the primary proof that the
widened ``^[0-9A-Z]{6}$`` guard is applied consistently. Runs without Postgres.

Decision (uppercase-only): KRX issues uppercase short codes; lowercase stays
rejected. The widened class adds only ``A-Z`` — no SQL metacharacters — so the
pre-bind injection guard (Veto #7 / D-12) is intact.
"""

from __future__ import annotations

from collectors.dart.db_writer import _TICKER_RE as _DART_RE
from collectors.fundamentals.db_writer import _TICKER_RE as _FUND_RE
from collectors.kind.db_writer import _TICKER_RE as _KIND_RE
from collectors.krx.db_writer import _TICKER_RE as _KRX_RE
from collectors.news.db_writer import _TICKER_RE as _NEWS_RE
from db.entity import _TICKER_RE as _ENTITY_RE

import pytest

_ALL_GUARDS = [
    pytest.param(_DART_RE, id="dart.db_writer"),
    pytest.param(_ENTITY_RE, id="db.entity"),
    pytest.param(_KRX_RE, id="krx.db_writer"),
    pytest.param(_NEWS_RE, id="news.db_writer"),
    pytest.param(_KIND_RE, id="kind.db_writer"),
    pytest.param(_FUND_RE, id="fundamentals.db_writer"),
]

# Shapes that MUST be accepted by every guard.
_ACCEPT = ["0001A0", "005930", "AAAAAA", "0A0A0A", "999999"]

# Shapes that MUST be rejected by every guard.
_REJECT = [
    "00593",     # 5 chars (too short)
    "0059300",   # 7 chars (too long)
    "0001a0",    # lowercase — uppercase-only decision
    "0001A!",    # SQL/path metacharacter
    "0;DROP",    # SQL metacharacters
    "",          # empty
    "²²²²²²",     # non-ASCII (superscript) digits
    " 00001",    # leading space
    "00001\n",   # trailing newline (anchors must reject)
]


@pytest.mark.parametrize("guard", _ALL_GUARDS)
@pytest.mark.parametrize("value", _ACCEPT)
def test_ticker_guard_accepts(guard, value: str) -> None:
    assert guard.match(value) is not None, f"{value!r} should be accepted"


@pytest.mark.parametrize("guard", _ALL_GUARDS)
@pytest.mark.parametrize("value", _REJECT)
def test_ticker_guard_rejects(guard, value: str) -> None:
    assert guard.match(value) is None, f"{value!r} should be rejected"


def test_all_six_guards_share_identical_pattern() -> None:
    """All six guards must use the same widened literal (surgical per-file copy)."""
    patterns = {g.values[0].pattern for g in _ALL_GUARDS}
    assert patterns == {r"^[0-9A-Z]{6}$"}, patterns
