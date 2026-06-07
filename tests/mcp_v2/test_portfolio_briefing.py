"""No-DB tests for list_portfolio + get_briefing (Plan 03-04 Task 3).

list_portfolio reads ``notes/private/portfolio.md`` from the process cwd, so the
tests ``monkeypatch.chdir(tmp_path)`` and write a portfolio.md there.
get_briefing is pure logic — it POSITIVELY returns ``Briefing(found=False,
entries=[])`` this phase (Phase-5 wires data); the assertion checks the model
fields directly so a regression that starts returning rows or drops ``entries``
fails here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_v2.errors import DataBackendError, InvalidArgument
from mcp_v2.tools.briefing import get_briefing
from mcp_v2.tools.portfolio import list_portfolio

# No DB marker: portfolio reads disk, briefing is pure logic. Run -m "not db".

_PORTFOLIO_MD = (
    "---\n"
    "holdings:\n"
    "  - ticker: '005930'\n"
    "    qty: 10\n"
    "    avg_cost: 70000\n"
    "  - ticker: '000660'\n"
    "    qty: 5\n"
    "    avg_cost: 120000\n"
    "watchlist:\n"
    "  - '035720'\n"
    "---\n"
    "# Portfolio notes\n"
)


def _write_portfolio(repo_root: Path, content: str) -> None:
    target = repo_root / "notes" / "private" / "portfolio.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


# --------------------------------------------------------------------------- #
# list_portfolio
# --------------------------------------------------------------------------- #
def test_list_portfolio_returns_holdings_and_watchlist(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_portfolio(tmp_path, _PORTFOLIO_MD)

    result = list_portfolio()

    assert {h.ticker for h in result.holdings} == {"005930", "000660"}
    samsung = next(h for h in result.holdings if h.ticker == "005930")
    assert samsung.quantity == 10
    assert samsung.avg_price == 70000
    assert [w.ticker for w in result.watchlist] == ["035720"]


def test_list_portfolio_empty_is_valid(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_portfolio(tmp_path, "---\nholdings: []\nwatchlist: []\n---\n")

    result = list_portfolio()
    assert result.holdings == []
    assert result.watchlist == []


def test_list_portfolio_missing_file_raises_data_backend_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # no portfolio.md written
    with pytest.raises(DataBackendError):
        list_portfolio()


# --------------------------------------------------------------------------- #
# get_briefing — positively assert the empty model (independent of other tools)
# --------------------------------------------------------------------------- #
def test_get_briefing_positively_returns_empty_model():
    result = get_briefing("2026-06-07")
    # POSITIVE assertion on the model fields (not just report_type-absence):
    assert result.found is False
    assert result.entries == []
    assert result.date == "2026-06-07"
    assert result.type == "daily"


def test_get_briefing_weekly_also_empty():
    result = get_briefing("2026-06-07", type="weekly")
    assert result.found is False
    assert result.entries == []
    assert result.type == "weekly"


def test_get_briefing_does_not_reference_report_type():
    """Phase 3 must NOT query/reference a report_type column (Phase 5's migration).

    AST-checks briefing.py: ``report_type`` may appear ONLY inside the module
    docstring (explanatory prose naming the deferred column). It must NOT appear
    as a string Constant in any executable statement (a SQL bind / column ref) —
    a regression that started querying for the not-yet-existing column fails here.
    """
    import ast

    path = Path(__file__).resolve().parents[2] / "src" / "mcp_v2" / "tools" / "briefing.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    # Collect docstring Constant nodes (module + every def/class) — those are
    # explanatory prose, allowed to name the deferred column.
    docstring_nodes: set[int] = set()
    for parent in ast.walk(tree):
        if isinstance(parent, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            body = getattr(parent, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstring_nodes.add(id(body[0].value))

    offending: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and "report_type" in node.value
            and id(node) not in docstring_nodes
        ):
            offending.append(node.value[:60])
    assert offending == [], f"briefing.py references report_type in code: {offending}"


def test_get_briefing_bad_type_raises_invalid_argument():
    with pytest.raises(InvalidArgument):
        get_briefing("2026-06-07", type="monthly")
    with pytest.raises(InvalidArgument):
        get_briefing("2026-06-07", type="")
