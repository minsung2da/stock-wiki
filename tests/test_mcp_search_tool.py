"""stock-mcp search tool tests (S1-S6): schema, error shape, logging, budgets."""

from __future__ import annotations

import io
import json
import time

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

# ---------------------------------------------------------------------------
# Helpers — mirror tests/test_hybrid_search.py to seed a known corpus.
# ---------------------------------------------------------------------------

_DIM = 1024


def _vec_lit(slot: int) -> str:
    v = [0.0] * _DIM
    v[slot % _DIM] = 1.0
    return "[" + ",".join(repr(float(x)) for x in v) + "]"


def _seed(engine: Engine, n_docs: int = 7) -> None:
    with engine.begin() as conn:
        for di in range(n_docs):
            doc_id = f"{di:064d}"
            conn.execute(
                sa.text(
                    "INSERT INTO documents "
                    "(id, body, source, vault_path, corp_code, "
                    " first_seen_at, last_seen_at) "
                    "VALUES (:id, 'b', 'dart', :vp, '00126380', now(), now())"
                ),
                {"id": doc_id, "vp": f"vault/raw/dart/doc_{di}.md"},
            )
            for ci in range(3):
                conn.execute(
                    sa.text(
                        "INSERT INTO chunks "
                        "(document_id, ord, text, embedding_model, embedding, "
                        " section_path, section_index, bm25_tokens) "
                        "VALUES (:d, :o, :t, 'BAAI/bge-m3@v1', "
                        " CAST(:e AS vector), 'root', 0, CAST(:tk AS int[]))"
                    ),
                    {
                        "d": doc_id,
                        "o": ci,
                        "t": f"doc-{di} chunk-{ci} " + ("X" * 100),
                        "e": _vec_lit(di * 10 + ci),
                        "tk": [1001, 1002],
                    },
                )


@pytest.fixture
def seeded(pg_clean: Engine, monkeypatch: pytest.MonkeyPatch) -> Engine:
    _seed(pg_clean)

    # Rebind get_engine so the tool reaches our testcontainer DB.
    from stock_mcp.tools import search as search_mod

    monkeypatch.setattr(search_mod, "get_engine", lambda: pg_clean)

    # Fake the embedder + tokenizer — avoids 2GB HF download in CI.
    from stock_mcp import search_core

    monkeypatch.setattr(
        search_core,
        "encode_query",
        lambda q: tuple(1.0 if i == 0 else 0.0 for i in range(_DIM)),
    )
    monkeypatch.setattr(search_core, "tokenize_ko", lambda q: [1001, 1002])
    return pg_clean


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_search_tool_wraps_hybrid_search(seeded: Engine) -> None:
    """S1 — the search function returns a SearchResult for a healthy call."""
    from stock_mcp.models import SearchResult
    from stock_mcp.tools.search import search

    result = search(query="samsung")
    assert isinstance(result, SearchResult)
    assert result.total == len(result.hits)
    assert result.mode == "hybrid"
    assert result.query == "samsung"


def test_search_tool_error_response_on_invalid_ticker(seeded: Engine) -> None:
    """S2 — invalid ticker yields structured error (NOT raise)."""
    from stock_mcp.tools.search import search

    out = search(query="foo", ticker="abc")
    assert isinstance(out, dict)
    assert out["error"]["code"] == "INVALID_TICKER"


def test_stderr_json_log_per_tool_call(seeded: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """S3 — a valid JSON log line is emitted to stderr per call (D-23)."""
    buf = io.StringIO()
    monkeypatch.setattr("sys.stderr", buf)

    from stock_mcp.tools.search import search

    search(query="samsung")
    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    assert lines, "no stderr log line emitted"
    rec = json.loads(lines[-1])
    assert rec["tool"] == "search"
    assert "args" in rec
    assert isinstance(rec["latency_ms"], int)
    assert isinstance(rec["result_size_tokens"], int)


def test_response_under_8k_tokens(seeded: Engine) -> None:
    """S4 — top_k=10 response < 8000 approximate tokens (RET-03)."""
    from stock_mcp.tools.search import search

    result = search(query="samsung", top_k=10)
    # SearchResult.model_dump_json() length / 4 ≈ token count.
    size = len(result.model_dump_json()) // 4
    assert size < 8000, f"response too large: ~{size} tokens"


def test_p95_latency_under_5s(seeded: Engine) -> None:
    """S5 — p95 of 20 calls < 5000 ms (RET-03)."""
    from stock_mcp.tools.search import search

    timings: list[float] = []
    for i in range(20):
        t0 = time.perf_counter()
        _ = search(query=f"samsung query {i}", top_k=10)
        timings.append((time.perf_counter() - t0) * 1000)
    timings.sort()
    p95 = timings[int(0.95 * len(timings)) - 1]
    assert p95 < 5000, f"p95 latency too high: {p95:.1f} ms"


def test_vault_path_citation_present(seeded: Engine) -> None:
    """S6 — every hit has a vault_path under vault/raw/* (JUDGE-04)."""
    import re

    from stock_mcp.tools.search import search

    result = search(query="samsung", top_k=5)
    assert len(result.hits) > 0
    path_re = re.compile(r"^vault/raw/\w+/")
    for h in result.hits:
        assert path_re.match(h.vault_path), f"bad vault_path: {h.vault_path!r}"
