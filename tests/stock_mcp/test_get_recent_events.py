"""Tests for the ``get_recent_events`` MCP tool (Plan 06-04 Task 2, MCP-04/D-05/D-08)."""

from __future__ import annotations

from datetime import date as _date
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from stock_mcp.tools.events import EVENTS_LIMIT, get_recent_events

# ---- Fixture utilities ------------------------------------------------------


def _ticker_with_recent_events(engine: Engine) -> tuple[str, str]:
    """Pick a (ticker, corp_code) pair that has ≥1 dart/news/kind document."""
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT e.current_ticker AS ticker, d.corp_code AS corp_code, "
                "COUNT(*) AS n "
                "FROM documents d "
                "JOIN entities e USING (corp_code) "
                "WHERE d.source IN ('dart', 'news', 'kind') "
                "GROUP BY e.current_ticker, d.corp_code "
                "ORDER BY n DESC LIMIT 1"
            )
        ).first()
    assert row is not None, "fixture must have at least one event-bearing entity"
    return row.ticker, row.corp_code


# ---- Tests ------------------------------------------------------------------


def test_returns_chronological_timeline_no_body(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    """Test 1: events sorted DESC; carry id/snippet/vault_path; no body field."""
    engine, _vault_root, _repo_root = mcp_vault_engine
    ticker, _cc = _ticker_with_recent_events(engine)

    result = get_recent_events(ticker=ticker, since="2020-01-01")

    assert hasattr(result, "events"), f"unexpected error: {result!r}"
    assert len(result.events) >= 1
    # DESC by date
    dates = [ev.date for ev in result.events]
    assert dates == sorted(dates, reverse=True), f"not DESC: {dates}"
    # Required fields + no body/content
    for ev in result.events:
        assert ev.id and len(ev.id) == 64
        assert ev.source in ("dart", "news", "kind")
        assert ev.snippet_200ch.startswith("<vault_excerpt>")
        assert ev.snippet_200ch.endswith("</vault_excerpt>")
        assert ev.vault_path
        # Pydantic extra='forbid' guarantees no body/content slipped through;
        # double-check by serializing.
        dumped = ev.model_dump()
        assert "body" not in dumped
        assert "content" not in dumped


def test_eight_digit_corp_code_resolves_identically(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    """Test 2: 8-digit corp_code returns same events as 6-digit ticker."""
    engine, _vault_root, _repo_root = mcp_vault_engine
    ticker, corp_code = _ticker_with_recent_events(engine)

    by_ticker = get_recent_events(ticker=ticker, since="2020-01-01")
    by_corp = get_recent_events(ticker=corp_code, since="2020-01-01")

    assert hasattr(by_ticker, "events")
    assert hasattr(by_corp, "events")
    ids_a = {ev.id for ev in by_ticker.events}
    ids_b = {ev.id for ev in by_corp.events}
    assert ids_a == ids_b, "ticker and corp_code must resolve to same entity"


def test_unknown_ticker_returns_invalid_ticker(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    """Test 3: unresolvable ticker → INVALID_TICKER error envelope."""
    _ = mcp_vault_engine
    result = get_recent_events(ticker="999999", since="2020-01-01")
    assert isinstance(result, dict)
    assert result["error"]["code"] == "INVALID_TICKER"


def test_far_future_since_returns_empty(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    """Test 4: events=[] when `since` is past every document."""
    engine, _vault_root, _repo_root = mcp_vault_engine
    ticker, _cc = _ticker_with_recent_events(engine)

    result = get_recent_events(ticker=ticker, since="2099-01-01")
    assert hasattr(result, "events")
    assert result.events == []


def test_snippet_wrapper_and_length(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    """Test 5: snippet wrapped in <vault_excerpt>, content ≤ 200 chars."""
    engine, _vault_root, _repo_root = mcp_vault_engine
    ticker, _cc = _ticker_with_recent_events(engine)

    result = get_recent_events(ticker=ticker, since="2020-01-01")
    assert hasattr(result, "events")
    for ev in result.events:
        prefix = "<vault_excerpt>"
        suffix = "</vault_excerpt>"
        assert ev.snippet_200ch.startswith(prefix)
        assert ev.snippet_200ch.endswith(suffix)
        inner = ev.snippet_200ch[len(prefix) : -len(suffix)]
        assert len(inner) <= 200


def test_summary_preferred_over_body(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    """Test 6: when _derived.summary present, snippet equals that summary."""
    engine, vault_root, _repo_root = mcp_vault_engine
    _ = vault_root
    ticker, _cc = _ticker_with_recent_events(engine)

    result = get_recent_events(ticker=ticker, since="2020-01-01")
    assert hasattr(result, "events")
    # At least one event should source from a fixture doc with _derived.summary
    # (DART fixture rows include "summary" frontmatter, see build_mcp_vault_fixture.py).
    found_summary_event = False
    for ev in result.events:
        if ev.source != "dart":
            continue
        from shared.frontmatter import read_frontmatter

        try:
            fm, _ = read_frontmatter(ev.vault_path)
        except Exception:
            continue
        summary = fm.derived.summary
        if not summary:
            continue
        inner = ev.snippet_200ch[len("<vault_excerpt>") : -len("</vault_excerpt>")]
        assert inner == summary[:200], (
            f"snippet {inner!r} did not match _derived.summary {summary!r}"
        )
        found_summary_event = True
        break
    assert found_summary_event, "no dart event with _derived.summary found in fixture"


def test_docstring_has_four_sections(
    mcp_vault_engine: tuple[Engine, Path, Path],
) -> None:
    """Test 7: 4-section contract (D-24)."""
    _ = mcp_vault_engine
    doc = get_recent_events.__doc__ or ""
    for section in (
        "### Behavior contract",
        "### Response shape",
        "### Errors",
        "### Performance budget",
    ):
        assert section in doc, f"missing docstring section: {section}"


def test_event_cap_at_50(mcp_vault_engine: tuple[Engine, Path, Path]) -> None:
    """Test 8: response is hard-capped at 50 events (D-05)."""
    engine, _vault_root, _repo_root = mcp_vault_engine
    ticker, corp_code = _ticker_with_recent_events(engine)

    # Insert 60 synthetic docs for this corp_code so we exceed the cap.
    inserted_ids: list[str] = []
    try:
        with engine.begin() as conn:
            for i in range(60):
                doc_id = f"{i:064x}"
                inserted_ids.append(doc_id)
                conn.execute(
                    sa.text(
                        "INSERT INTO documents (id, body, source, vault_path, "
                        "corp_code, first_seen_at) "
                        "VALUES (:id, :body, 'news', :vp, :cc, :fs) "
                        "ON CONFLICT (id) DO NOTHING"
                    ),
                    {
                        "id": doc_id,
                        "body": f"synthetic event body {i}",
                        "vp": f"vault/raw/synthetic/{doc_id}.md",
                        "cc": corp_code,
                        "fs": f"2026-04-{(i % 28) + 1:02d}T00:00:00+00:00",
                    },
                )

        result = get_recent_events(ticker=ticker, since="2026-01-01")
        assert hasattr(result, "events")
        assert len(result.events) == EVENTS_LIMIT == 50
        assert any("50-row cap" in t for t in result.truncation_applied)
    finally:
        with engine.begin() as conn:
            for doc_id in inserted_ids:
                conn.execute(
                    sa.text("DELETE FROM documents WHERE id = :id"),
                    {"id": doc_id},
                )


def test_since_parses_iso_date(mcp_vault_engine: tuple[Engine, Path, Path]) -> None:
    """Test 9: invalid `since` → INVALID_DATE with details echoed."""
    _ = mcp_vault_engine

    bad = get_recent_events(ticker="005930", since="not-a-date")
    assert isinstance(bad, dict)
    assert bad["error"]["code"] == "INVALID_DATE"
    assert bad["error"]["details"]["since"] == "not-a-date"

    bad_sep = get_recent_events(ticker="005930", since="2026/04/01")
    assert isinstance(bad_sep, dict)
    assert bad_sep["error"]["code"] == "INVALID_DATE"


def test_since_bound_as_typed_date(
    mcp_vault_engine: tuple[Engine, Path, Path],
    monkeypatch: object,
) -> None:
    """Test 10: SQL bind receives a `datetime.date`, not a raw string."""
    engine, _vault_root, _repo_root = mcp_vault_engine
    ticker, _cc = _ticker_with_recent_events(engine)

    # Force the tool to use the testcontainer engine so our event listener
    # on that engine actually intercepts the query (the production
    # ``get_engine()`` builds a fresh engine from $DATABASE_URL each call).
    from stock_mcp.tools import events as events_mod

    monkeypatch.setattr(events_mod, "get_engine", lambda: engine)  # type: ignore[attr-defined]

    captured: list[tuple[str, object]] = []

    def _capture(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001, ARG001
        if "FROM documents" in statement and "first_seen_at" in statement:
            captured.append((statement, parameters))

    sa.event.listen(engine, "before_cursor_execute", _capture)
    try:
        result = get_recent_events(ticker=ticker, since="2026-01-01")
    finally:
        sa.event.remove(engine, "before_cursor_execute", _capture)

    assert hasattr(result, "events"), f"unexpected error: {result!r}"
    assert captured, f"expected to intercept the events SELECT; saw {captured!r}"
    _stmt, params = captured[-1]
    # Parameters may be dict (named) or tuple (positional) depending on dialect.
    if isinstance(params, dict):
        bound_since = params["since"]
    else:
        # Fall back: find the date value in the tuple.
        bound_since = next(p for p in params if isinstance(p, _date | str))
    assert isinstance(bound_since, _date), (
        f"expected datetime.date, got {type(bound_since).__name__}: {bound_since!r}"
    )
    assert not isinstance(bound_since, str)
