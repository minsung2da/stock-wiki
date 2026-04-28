"""Phase 6 Plan 06-02 Task 2: snippet builder tests (D-08)."""

from __future__ import annotations

from stock_mcp.snippets import SNIPPET_MAX_CHARS, build_snippet


def test_s1_prefers_derived_summary_when_present() -> None:
    body = "abc" * 100
    out = build_snippet(body=body, derived_summary="short summary")
    assert out == "<vault_excerpt>short summary</vault_excerpt>"


def test_s2_falls_back_to_body_first_200_chars() -> None:
    body = "x" * 500
    out = build_snippet(body=body, derived_summary=None)
    assert out.startswith("<vault_excerpt>")
    assert out.endswith("</vault_excerpt>")
    inner = out[len("<vault_excerpt>") : -len("</vault_excerpt>")]
    assert inner == "x" * SNIPPET_MAX_CHARS
    assert len(inner) == 200


def test_s3_empty_body_and_no_summary_yields_empty_wrapper() -> None:
    out = build_snippet(body="", derived_summary=None)
    assert out == "<vault_excerpt></vault_excerpt>"


def test_empty_string_summary_falls_through_to_body() -> None:
    # An empty derived_summary string is not "present"; falls back to body.
    out = build_snippet(body="hello", derived_summary="")
    assert out == "<vault_excerpt>hello</vault_excerpt>"
