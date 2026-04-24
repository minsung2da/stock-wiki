"""Tests for D-07 zone-integrity helper."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

HELPER_PATH = Path(__file__).parent.parent / ".claude/routines/enrich/helpers/zone_integrity.py"
spec = importlib.util.spec_from_file_location("zi_mod", HELPER_PATH)
assert spec and spec.loader
zi_mod = importlib.util.module_from_spec(spec)
sys.modules["zi_mod"] = zi_mod
spec.loader.exec_module(zi_mod)
compute_zone_hash = zi_mod.compute_zone_hash
assert_zones_unchanged = zi_mod.assert_zones_unchanged
ZoneViolationError = zi_mod.ZoneViolationError

from shared.frontmatter import (  # noqa: E402
    DerivedBlock,
    FrontMatter,
    IngestStateBlock,
    ProvenanceBlock,
)


def _make(source="news", processed=False, tickers=None):
    return FrontMatter(
        provenance=ProvenanceBlock(source=source, content_hash="h"),
        ingest_state=IngestStateBlock(processed=processed),
        derived=DerivedBlock(tickers=tickers or []),
    )


def test_equal_zones_same_hash():
    a = _make()
    b = _make()
    assert compute_zone_hash(a) == compute_zone_hash(b)


def test_derived_change_ignored():
    """D-07: zone hash covers only provenance + ingest_state. _derived changes don't trip."""
    a = _make(tickers=[])
    b = _make(tickers=["005930"])
    assert compute_zone_hash(a) == compute_zone_hash(b)


def test_provenance_change_detected():
    a = _make(source="news")
    b = _make(source="dart")
    assert compute_zone_hash(a) != compute_zone_hash(b)
    with pytest.raises(ZoneViolationError):
        assert_zones_unchanged(a, b)


def test_ingest_state_change_detected():
    a = _make(processed=False)
    b = _make(processed=True)
    assert compute_zone_hash(a) != compute_zone_hash(b)


def test_assert_unchanged_passes_on_equal():
    a = _make()
    b = _make()
    assert_zones_unchanged(a, b)  # must not raise
