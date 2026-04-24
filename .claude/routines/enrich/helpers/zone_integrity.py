"""D-07 zone-integrity check.

Computes a SHA256 hash over the provenance + ingest_state sub-frontmatter
blocks. The Routines skill hashes before the LLM write and after, comparing
to detect any drift (agent writing outside its permitted _derived zone).
"""

from __future__ import annotations

import hashlib

import yaml

from shared.frontmatter import FrontMatter


class ZoneViolationError(Exception):
    """Raised when provenance or ingest_state has been modified outside _derived."""


def compute_zone_hash(fm: FrontMatter) -> str:
    """Deterministic hash of (provenance, ingest_state) dumps."""
    prov = fm.provenance.model_dump(exclude_none=True, by_alias=True)
    ing = fm.ingest_state.model_dump(exclude_none=True, by_alias=True)
    payload = (
        yaml.safe_dump(prov, sort_keys=True, allow_unicode=True)
        + "\n::\n"
        + yaml.safe_dump(ing, sort_keys=True, allow_unicode=True)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assert_zones_unchanged(before: FrontMatter, after: FrontMatter) -> None:
    """Raise ZoneViolationError if provenance or ingest_state zone hash differs."""
    if compute_zone_hash(before) != compute_zone_hash(after):
        raise ZoneViolationError("provenance or ingest_state zone modified — agent_zone_violation")
