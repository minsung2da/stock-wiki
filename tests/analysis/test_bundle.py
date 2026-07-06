"""D-02 EvidenceBundle tests against the seeded corpus (Plan 04-03).

Locks the bundle behavior SC#2 step (a) depends on: one fixed pre-fetch via the
in-process MCP tools, injection delimiters preserved verbatim (D-03), numeric ranges
+ peers present (Veto #5/#6), a bounded reproducible ``to_stdin`` (T-04-08), and the
portfolio note attached only when the ticker is held. No live ``claude`` CLI.

``encode_query`` is stubbed to the seeded constant vector so ``hybrid_search`` runs
without the ~2GB bge-m3 download (mirrors tests/mcp_v2/test_hybrid_search.py). The
tools reach the same test DB via their own ``get_engine()`` (DATABASE_URL is set by
``pg_engine``), so seeding ``seeded_engine`` is sufficient — no ``get_engine`` patch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analysis import bundle as bundle_mod
from analysis.bundle import EvidenceBundle, FilingHitBody, build_bundle
from mcp_v2 import retrieval
from mcp_v2.models import FlowRange, NoteContent, OhlcvRange

_AS_OF = "2026-06-25"  # after both seeded filings (2026-05-20 / 2026-04-15)
_STUB_QVEC = tuple([0.01] * 1024)  # matches the seeded constant halfvec


@pytest.fixture(autouse=True)
def _stub_query_embedder(monkeypatch):
    """Patch encode_query so hybrid_search skips the bge-m3 download (constant vec)."""
    monkeypatch.setattr(retrieval, "encode_query", lambda _q: _STUB_QVEC)


def test_build_bundle_prefetches_wrapped_filings(seeded_engine) -> None:
    """build_bundle returns non-empty filings whose bodies keep the <untrusted> wrap."""
    b = build_bundle(seeded_engine, "00126380", _AS_OF)
    assert b.corp_code == "00126380"
    assert b.ticker == "005930"
    assert b.filings, "expected the seeded filings to be pre-fetched (Veto #8 whole body)"
    for f in b.filings:
        assert "<untrusted source=" in f.body_md  # D-03 delimiter preserved verbatim


def test_bundle_includes_numeric_ranges_and_peers(seeded_engine) -> None:
    """The bundle carries ohlcv + flow ranges and a PeerView per metric (Veto #5/#6)."""
    b = build_bundle(seeded_engine, "00126380", _AS_OF)
    assert isinstance(b.ohlcv, OhlcvRange) and b.ohlcv.ticker == "005930"
    assert isinstance(b.flow, FlowRange) and b.flow.ticker == "005930"
    assert len(b.peers) >= 1
    assert {p.metric for p in b.peers} == {"per", "pbr", "roe"}


def test_to_stdin_preserves_delimiters_and_is_bounded(seeded_engine) -> None:
    """to_stdin echoes the <untrusted> delimiter and stays within the module cap."""
    b = build_bundle(seeded_engine, "00126380", _AS_OF)
    s = b.to_stdin()
    assert "<untrusted source=" in s
    assert len(s) <= bundle_mod._STDIN_CHAR_CAP


def test_build_bundle_is_reproducible(seeded_engine) -> None:
    """Same (corp_code, as_of) on the same DB ⇒ equal bundle (Phase-8 CPCV anchor)."""
    b1 = build_bundle(seeded_engine, "00126380", _AS_OF)
    b2 = build_bundle(seeded_engine, "00126380", _AS_OF)
    assert b1 == b2
    assert b1.to_stdin() == b2.to_stdin()


def test_portfolio_note_only_when_held(seeded_engine, monkeypatch) -> None:
    """The thesis note is attached only when a portfolio path is supplied (held)."""
    # Not held: no path → no note.
    b_absent = build_bundle(seeded_engine, "00126380", _AS_OF)
    assert b_absent.portfolio_note is None

    # Held: a path is supplied → get_note is called and attached (wrapped body).
    canned = NoteContent(
        path="notes/private/samsung.md",
        content_md='<untrusted source="note" ref="note:samsung">\nthesis\n</untrusted>',
    )
    monkeypatch.setattr(bundle_mod, "get_note", lambda _p: canned)
    b_held = build_bundle(
        seeded_engine, "00126380", _AS_OF, portfolio_note_path="notes/private/samsung.md"
    )
    assert b_held.portfolio_note is not None
    assert "<untrusted source=" in b_held.portfolio_note.content_md
    assert "<untrusted source=" in b_held.to_stdin()


def test_cap_drops_whole_bodies_never_mid_body() -> None:
    """An oversized body is dropped WHOLE; a smaller sibling survives intact."""
    big_ref, small_ref = "20260101000001", "20260102000002"
    big_body = (
        f'<untrusted source="dart" ref="{big_ref}">\n'
        + ("x" * (bundle_mod._STDIN_CHAR_CAP + 5_000))
        + "\n</untrusted>"
    )
    small_body = f'<untrusted source="dart" ref="{small_ref}">\nhello world\n</untrusted>'
    b = EvidenceBundle(
        corp_code="00126380",
        ticker="005930",
        as_of=_AS_OF,
        filings=[
            FilingHitBody(rcept_no=big_ref, body_md=big_body),  # highest priority, oversized
            FilingHitBody(rcept_no=small_ref, body_md=small_body),
        ],
        ohlcv=OhlcvRange(ticker="005930", bars=[]),
        flow=FlowRange(ticker="005930", rows=[]),
        peers=[],
    )
    s = b.to_stdin()
    assert len(s) <= bundle_mod._STDIN_CHAR_CAP
    assert f'ref="{big_ref}"' not in s  # oversized body dropped whole
    assert f'ref="{small_ref}"' in s  # smaller body kept
    assert "hello world" in s  # kept body intact — never truncated mid-body


def test_unknown_corp_code_raises(seeded_engine) -> None:
    """An unresolvable corp_code is a clear ValueError, not a silent empty bundle."""
    with pytest.raises(ValueError):
        build_bundle(seeded_engine, "99999999", _AS_OF)


def test_no_raw_sql_no_cloud_llm_sdk() -> None:
    """bundle.py adds no run_sql escape hatch (Veto #7) and imports no cloud LLM SDK."""
    src = Path(bundle_mod.__file__).read_text(encoding="utf-8")
    assert "run_sql(" not in src  # no escape-hatch SQL call (Veto #7)
    assert "text(" not in src  # no raw SQL construction — only the typed tools
    assert "import anthropic" not in src
    assert "import openai" not in src
