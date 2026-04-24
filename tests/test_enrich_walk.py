"""Tests for Routines walk.find_candidates (D-19 idempotency, D-21 F-4c)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HELPER_PATH = Path(__file__).parent.parent / ".claude/routines/enrich/helpers/walk.py"
spec = importlib.util.spec_from_file_location("walk_mod", HELPER_PATH)
assert spec and spec.loader
walk_mod = importlib.util.module_from_spec(spec)
sys.modules["walk_mod"] = walk_mod
spec.loader.exec_module(walk_mod)
find_candidates = walk_mod.find_candidates

from shared.content_hash import compute_content_hash  # noqa: E402
from shared.frontmatter import (  # noqa: E402
    DerivedBlock,
    FrontMatter,
    IngestStateBlock,
    ProvenanceBlock,
    write_frontmatter,
)


def _make_doc(vault: Path, relpath: str, body: str, derived=None, skip_reason=None):
    path = vault / "raw" / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write once with placeholder hash to produce a file, then read actual hash, update
    prov = ProvenanceBlock(source="news", content_hash="placeholder")
    d = derived or DerivedBlock(skip_reason=skip_reason)
    fm = FrontMatter(provenance=prov, ingest_state=IngestStateBlock(), derived=d)
    write_frontmatter(str(path), fm, body)
    # Now replace content_hash with true hash
    actual = compute_content_hash(str(path))
    fm.provenance.content_hash = actual
    write_frontmatter(str(path), fm, body)
    return path


def test_missing_derived_yields_candidate(tmp_path):
    _make_doc(tmp_path, "news/2026-04/a.md", "some news body")
    cands = find_candidates(str(tmp_path))
    assert len(cands) == 1
    assert cands[0].reason == "missing_derived"


def test_populated_derived_stable_hash_skipped(tmp_path):
    d = DerivedBlock(tickers=["005930"], summary="already enriched")
    _make_doc(tmp_path, "news/2026-04/b.md", "body b", derived=d)
    cands = find_candidates(str(tmp_path))
    assert cands == []


def test_hash_changed_triggers_reprocess(tmp_path):
    d = DerivedBlock(tickers=["005930"])
    path = _make_doc(tmp_path, "news/2026-04/c.md", "original body", derived=d)
    # Simulate body edit — rewrite with different body, keeping stored hash stale
    text = path.read_text(encoding="utf-8")
    # Find body section after closing --- and replace
    parts = text.split("---\n", 2)
    new_text = parts[0] + "---\n" + parts[1] + "---\nNEW DIFFERENT BODY\n"
    path.write_text(new_text, encoding="utf-8")
    cands = find_candidates(str(tmp_path))
    assert len(cands) == 1
    assert cands[0].reason == "hash_changed"


def test_skip_reason_sticks_until_hash_changes(tmp_path):
    """F-4c: docs with skip_reason='review_required' and stable hash are skipped."""
    d = DerivedBlock(skip_reason="review_required", review_flags=[])
    _make_doc(tmp_path, "news/2026-04/d.md", "body d", derived=d)
    cands = find_candidates(str(tmp_path))
    assert cands == []  # sticky


def test_empty_vault_returns_empty(tmp_path):
    assert find_candidates(str(tmp_path)) == []
