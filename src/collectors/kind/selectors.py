"""KIND HTML selector constants + ParseError (D-17 single source of truth).

Selector drift defense: on miss, raise ParseError — heartbeat will set
`kind_parse_error: true`. No silent graceful degradation.

Confirmed against tests/fixtures/kind/undisclosure_ajax_page1.html
(EUC-KR fragment, `<table class="list">`, 15 data rows per page).
"""

from __future__ import annotations


class ParseError(RuntimeError):
    """Raised when a KIND HTML fragment does not contain expected structure."""


# --- undisclosure AJAX fragment selectors ---
# table class="list" summary=... with caption "목록". Each data row is a <tr>
# under <tbody>. Cells (by column index, matching the EUC-KR summary):
#   0: 번호
#   1: 회사명
#   2: 벌점
#   3: 제재금(만원)
#   4: 공시책임자등 교체요구
#   5: 불성실유형
#   6: 지정일 (YYYY-MM-DD)
#   7: 지정사유
UNDISCLOSURE_TABLE = "table.list"
UNDISCLOSURE_ROWS = "table.list > tbody > tr"
UNDISCLOSURE_CELL_COMPANY = 1
UNDISCLOSURE_CELL_SUBTYPE = 5
UNDISCLOSURE_CELL_DATE = 6
UNDISCLOSURE_CELL_REASON = 7
