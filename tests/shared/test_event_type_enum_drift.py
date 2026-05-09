"""Phase 8 GAP-03 — regression guard for EventType ↔ vault/raw drift.

Whenever an enrichment routine writes an `_derived.event_type` value not
present in `EventType` Literal, this test fails fast with the offending
file and value. The Plan 05 mitigation:
  - extends EventType with `price_micro` (KRX intent),
  - migrates two hallucinated values in vault (`disclosure`, `news_micro`).
"""

from __future__ import annotations

import pathlib
import re
from typing import get_args

import yaml

from shared.frontmatter import EventType

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
VAULT_RAW = REPO_ROOT / "vault" / "raw"
ALLOWED: set[str | None] = set(get_args(EventType)) | {None}


def _extract_event_type(md_path: pathlib.Path) -> str | None:
    text = md_path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    return (fm.get("_derived") or {}).get("event_type")


def test_no_event_type_drift_in_vault_raw():
    if not VAULT_RAW.exists():
        # Fresh clone / CI without populated vault — nothing to check.
        return
    offenders: list[tuple[str, object]] = []
    for p in VAULT_RAW.rglob("*.md"):
        v = _extract_event_type(p)
        if v not in ALLOWED:
            offenders.append((str(p.relative_to(REPO_ROOT)), v))
    assert not offenders, f"event_type drift — values not in EventType Literal: {offenders}"
