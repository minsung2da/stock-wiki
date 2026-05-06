"""Phase 8 Plan 02 Task 1: hub_builder TDD tests.

Covers:
- render_hub: pure function returning (body, content_hash) — D-03 4 sections
- content_hash idempotency: generated_at MUST NOT influence hash (Pitfall 1)
- write_hub_if_changed: idempotent disk writes (D-04)
- run: iterates entities, skips missing corp_code (Pitfall 5)
- Path containment: corp_code-based hub path (D-05, T-08-02-04)
- Valuation placeholder: Phase 10 D-12 hook present
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from ingest.hub_builder import (
    HubInputs,
    HubResult,
    render_hub,
    run,
    write_hub_if_changed,
)


# --- Test 1 ---------------------------------------------------------------
def test_render_hub_returns_body_and_hash(make_hub_inputs) -> None:
    inp = make_hub_inputs()
    body, h = render_hub(inp)
    assert isinstance(body, str)
    assert isinstance(h, str)
    assert len(h) == 64  # sha256 hex
    # 4 sections per D-03
    assert "## 최근 공시" in body
    assert "## 최근 뉴스" in body
    assert "## 가격 트렌드" in body
    assert "## Valuation" in body
    assert "## Private Notes" in body
    # Frontmatter has type: ticker_hub
    assert "type: ticker_hub" in body


# --- Test 2 ---------------------------------------------------------------
def test_content_hash_excludes_generated_at(make_hub_inputs) -> None:
    """Pitfall 1 — generated_at must NOT affect content_hash."""
    inp = make_hub_inputs()
    # Two render calls with different wall-clock times
    body1, h1 = render_hub(inp)
    body2, h2 = render_hub(inp)
    assert h1 == h2  # hash identical
    # bodies will differ in generated_at; fine.


# --- Test 3 ---------------------------------------------------------------
def test_write_hub_skips_unchanged(tmp_path: Path, make_hub_inputs) -> None:
    inp = make_hub_inputs()
    body, h = render_hub(inp)
    path = tmp_path / "by-ticker" / f"{inp.corp_code}.md"
    # First write
    assert write_hub_if_changed(path, body, h) is True
    mtime_before = path.stat().st_mtime_ns
    # Force os mtime to be old
    os.utime(path, ns=(mtime_before - 10_000_000, mtime_before - 10_000_000))
    mtime_pre = path.stat().st_mtime_ns
    # Second write with same hash → skip
    assert write_hub_if_changed(path, body, h) is False
    mtime_post = path.stat().st_mtime_ns
    assert mtime_post == mtime_pre  # no rewrite


# --- Test 4 ---------------------------------------------------------------
def test_write_hub_writes_when_changed(tmp_path: Path, make_hub_inputs) -> None:
    inp1 = make_hub_inputs()
    body1, h1 = render_hub(inp1)
    path = tmp_path / "by-ticker" / f"{inp1.corp_code}.md"
    write_hub_if_changed(path, body1, h1)

    inp2 = make_hub_inputs(latest_price=80000)  # different inputs → different hash
    body2, h2 = render_hub(inp2)
    assert h2 != h1
    assert write_hub_if_changed(path, body2, h2) is True
    new_text = path.read_text(encoding="utf-8")
    assert f"content_hash: {h2}" in new_text


# --- Test 5 ---------------------------------------------------------------
def test_write_hub_creates_new_file(tmp_path: Path, make_hub_inputs) -> None:
    inp = make_hub_inputs()
    body, h = render_hub(inp)
    path = tmp_path / "by-ticker" / "deeper" / f"{inp.corp_code}.md"
    assert not path.exists()
    assert write_hub_if_changed(path, body, h) is True
    assert path.exists()
    assert path.parent.is_dir()


# --- Test 6 ---------------------------------------------------------------
def test_run_skips_corp_code_missing(tmp_path: Path, make_hub_inputs) -> None:
    """Pitfall 5: corp_code in entities but no inputs → review_flag, not crash."""
    inp = make_hub_inputs()

    fake_corp_codes = ["00126380", "99999999"]  # second one won't resolve

    def fake_collect(_engine, cc: str):
        if cc == inp.corp_code:
            return inp
        return None  # missing

    class FakeConn:
        def execute(self, *a, **kw):
            class _R:
                def all(self_inner):
                    return [(cc,) for cc in fake_corp_codes]

            return _R()

    class FakeBegin:
        def __enter__(self_inner):
            return FakeConn()

        def __exit__(self_inner, *a):
            return False

    class FakeEngine:
        def begin(self_inner):
            return FakeBegin()

    with patch("ingest.hub_builder.collect_inputs_for_corp", side_effect=fake_collect):
        result: HubResult = run(FakeEngine(), vault_root=tmp_path, repo_root=tmp_path)

    assert result.written == 1
    # Missing corp_code recorded as review_flag
    assert any(f.get("corp_code") == "99999999" for f in result.review_flags)
    # Wrote hub for resolved corp_code
    assert (tmp_path / "ingested" / "by-ticker" / "00126380.md").exists()


# --- Test 7 ---------------------------------------------------------------
def test_hub_path_is_corp_code_based(tmp_path: Path, make_hub_inputs) -> None:
    """D-05: path uses corp_code (8 digits), never ticker (6 digits)."""
    inp = make_hub_inputs()  # corp_code="00126380", ticker="005930"

    def fake_collect(_engine, cc: str):
        return inp if cc == inp.corp_code else None

    class FakeConn:
        def execute(self, *a, **kw):
            class _R:
                def all(self_inner):
                    return [(inp.corp_code,)]

            return _R()

    class FakeBegin:
        def __enter__(self_inner):
            return FakeConn()

        def __exit__(self_inner, *a):
            return False

    class FakeEngine:
        def begin(self_inner):
            return FakeBegin()

    with patch("ingest.hub_builder.collect_inputs_for_corp", side_effect=fake_collect):
        run(FakeEngine(), vault_root=tmp_path, repo_root=tmp_path)

    assert (tmp_path / "ingested" / "by-ticker" / "00126380.md").exists()
    assert not (tmp_path / "ingested" / "by-ticker" / "005930.md").exists()


# --- Test 8 ---------------------------------------------------------------
def test_valuation_placeholder_present(make_hub_inputs) -> None:
    """D-12 Phase 10 hook: dataview placeholder code block in Valuation section."""
    inp = make_hub_inputs()
    body, _ = render_hub(inp)
    assert "## Valuation" in body
    # Dataview code block (placeholder for Phase 10)
    assert "```dataview" in body
