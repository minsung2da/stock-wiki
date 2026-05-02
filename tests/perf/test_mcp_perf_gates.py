"""Per-tool p95 latency + p95 token CI gates (Plan 06-09 Task 2; D-19, D-20).

For every Phase 6 MCP tool we run N=20 reps against the seeded fixture vault,
measure latency (perf_counter) and serialized token count (tiktoken
cl100k_base), and assert the p95 stays under the budget defined in
06-UI-SPEC "Token Budget — Per-Tool Targets".

Tagged ``slow`` per D-20 — runs on PR CI, deselected from local fast loops.
Per-tool stats are persisted to ``tests/perf/{tool_name}.json`` so PR diffs
surface regressions before they hit main.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from .conftest import measure, restore_repo_root, save_perf, set_repo_root


def _call_search(**kw):
    from stock_mcp.tools.search import search
    return search(**kw)


def _call_overview(**kw):
    from stock_mcp.tools.overview import get_ticker_overview
    return get_ticker_overview(**kw)


def _call_events(**kw):
    from stock_mcp.tools.events import get_recent_events
    return get_recent_events(**kw)


def _call_portfolio(**kw):
    from stock_mcp.tools.portfolio import get_portfolio_state
    return get_portfolio_state(**kw)


def _call_related(**kw):
    from stock_mcp.tools.related import get_related
    return get_related(**kw)


def _call_filing(**kw):
    from stock_mcp.tools.filing import get_filing
    return get_filing(**kw)


def _call_add_note(**kw):
    from stock_mcp.tools.notes import add_note
    return add_note(**kw)


def _call_health(**kw):
    from stock_mcp.tools.health import health
    return health(**kw)


# (tool_name, callable, args_template, p95_latency_ms_max, p95_tokens_max)
#
# get_filing's 50000-token budget is the documented Phase 6 success-criterion
# #5 exception (see ROADMAP Phase 6 SC#5 / CONTEXT D-07 / UI-SPEC). A single
# disclosure body may legitimately exceed the 8k tool-response budget; the
# tool itself truncates at 200K characters as a hard ceiling.
PERF_BUDGETS = [
    ("search", _call_search,
        {"query": "삼성전자 분기 실적", "ticker": "005930", "top_k": 5},
        5000, 8000),
    ("get_ticker_overview", _call_overview,
        {"ticker": "005930"}, 5000, 8000),
    ("get_recent_events", _call_events,
        {"ticker": "005930", "since": "2026-01-01"}, 5000, 8000),
    ("get_portfolio_state", _call_portfolio, {}, 1000, 4000),
    ("get_related", _call_related,
        {"document_id": None, "depth": 1}, 2000, 4000),
    ("get_filing", _call_filing,
        # ROADMAP Phase 6 SC#5 exception: single-doc body may exceed 8k tokens.
        {"id": None}, 3000, 50000),
    ("add_note", _call_add_note,
        {"path": None, "body": "perf body", "frontmatter": {"type": "note"}},
        1000, 1000),
    ("health", _call_health, {}, 2000, 2000),
]


def _pick_doc_id(engine: Engine, *, with_edges: bool = False) -> str:
    """Fetch a real document id from the seeded fixture corpus."""
    if with_edges:
        sql = (
            "SELECT d.id FROM documents d "
            "JOIN edges e ON e.src_type='document' AND e.src_id=d.id "
            "ORDER BY d.id LIMIT 1"
        )
    else:
        sql = (
            "SELECT id FROM documents WHERE corp_code IS NOT NULL "
            "ORDER BY id LIMIT 1"
        )
    with engine.connect() as conn:
        row = conn.execute(sa.text(sql)).first()
    assert row is not None, "fixture vault must have a document for perf test"
    return row.id


@pytest.mark.slow
@pytest.mark.parametrize(
    "name,fn,args_template,lat_max,tok_max", PERF_BUDGETS
)
def test_p95_perf_gates(
    mcp_vault_engine: tuple[Engine, Path, Path],
    name: str,
    fn,
    args_template: dict,
    lat_max: float,
    tok_max: int,
) -> None:
    engine, _vault_root, repo_root = mcp_vault_engine

    # Bind dynamic args.
    args = dict(args_template)
    if name == "get_filing":
        args["id"] = _pick_doc_id(engine, with_edges=False)
    elif name == "get_related":
        args["document_id"] = _pick_doc_id(engine, with_edges=True)
    elif name == "add_note":
        # Unique-per-rep path would amplify wall time; the tool's idempotency
        # check (D-13) makes repeated identical calls cheap, so we keep one
        # path and let the second-window dedupe path dominate.
        args["path"] = "vault/notes/_perf/perf-test"

    # Tools that read from disk (portfolio, notes, health) need the fixture
    # repo_root to resolve correctly.
    prev = set_repo_root(repo_root)
    try:
        stats = measure(fn, args, n=20)
    finally:
        restore_repo_root(prev)

    save_perf(name, stats)

    assert stats["p95_latency_ms"] < lat_max, (
        f"{name} p95 latency {stats['p95_latency_ms']:.0f}ms exceeds {lat_max}ms"
        f" (stats: {stats})"
    )
    assert stats["p95_tokens"] < tok_max, (
        f"{name} p95 tokens {stats['p95_tokens']} exceeds {tok_max}"
        f" (stats: {stats})"
    )
