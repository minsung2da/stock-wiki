"""add_note frontmatter validation tests (Plan 06-06 Task 1, F1-F4 + D1)."""

from __future__ import annotations

import frontmatter as fm

from stock_mcp.tools.notes import add_note


def _is_error(resp) -> bool:
    return isinstance(resp, dict) and "error" in resp


def test_f1_missing_type_returns_invalid_frontmatter(mcp_vault_isolated):
    resp = add_note(path="vault/notes/x.md", body="hi", frontmatter={})
    assert _is_error(resp)
    assert resp["error"]["code"] == "INVALID_FRONTMATTER"


def test_f2_invalid_ticker_is_warning_not_error(mcp_vault_isolated):
    _engine, _vault, repo = mcp_vault_isolated
    resp = add_note(
        path="vault/notes/y.md",
        body="hi",
        frontmatter={"type": "note", "tickers": ["005930", "invalid"]},
    )
    assert not _is_error(resp), resp
    assert (repo / "vault" / "notes" / "y.md").exists()


def test_f3_frontmatter_none_means_missing_type(mcp_vault_isolated):
    resp = add_note(path="vault/notes/z.md", body="hi", frontmatter=None)
    assert _is_error(resp)
    assert resp["error"]["code"] == "INVALID_FRONTMATTER"


def test_f4_created_file_has_required_yaml_keys(mcp_vault_isolated):
    _engine, _vault, repo = mcp_vault_isolated
    resp = add_note(path="vault/notes/keys.md", body="hi", frontmatter={"type": "note"})
    assert not _is_error(resp), resp
    target = repo / "vault" / "notes" / "keys.md"
    post = fm.load(str(target))
    md = post.metadata
    for key in ("type", "tickers", "tags", "created", "updated", "author"):
        assert key in md, f"missing key: {key} (got {list(md.keys())})"


def test_d1_docstring_four_sections_present():
    from stock_mcp.tools.notes import add_note as fn

    doc = fn.__doc__ or ""
    for section in (
        "### Behavior contract",
        "### Response shape",
        "### Errors",
        "### Performance budget",
    ):
        assert section in doc, f"missing docstring section: {section}"
