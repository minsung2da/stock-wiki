"""Pydantic v2 models for the v2.0 decision_card (the analysis output contract).

`DecisionCard` is the typed contract every downstream phase produces and consumes
(Veto #7 — typed Pydantic, never raw dicts). Field names match the redesign §3 YAML
example (``.planning/research/redesign-2026-05.md`` lines 236-294) exactly so a card
round-trips: ``DecisionCard.model_validate(card.model_dump(mode="json")) == card``.

Hard vetoes enforced purely by field declarations (no ``@model_validator`` needed,
matching CONTEXT's "leave shape to the type system"):

- Veto #2 / SC#5 — no untimed thesis: ``expires_at: datetime`` has no default and is
  not Optional, so its omission raises ``ValidationError``; ``assumptions`` has
  ``min_length=1``, so an empty list raises ``ValidationError``. A card cannot exist
  without an expiry ledger and at least one re-checkable assumption.
- Veto #3 — contradictions are a first-class output: ``contradictions`` is a declared
  field (defaulting to an empty list), never hidden or silently dropped.
- ASVS V5 / T-02-04 — every model uses ``ConfigDict(extra="forbid")``, rejecting
  unknown keys before a malformed payload could reach storage.

``numeric_facts`` is a permissive ``dict[str, float | int]`` — Phase 2 validates the
shape only; the digit-level verbatim checksum against source is Phase 4's responsibility
(CONTEXT lock, T-02-06).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Decision(BaseModel):
    """The stance + conviction block (redesign §3 ``decision``)."""

    model_config = ConfigDict(extra="forbid")

    stance: Literal["BUY", "ADD", "HOLD", "TRIM", "SELL", "AVOID"]
    conviction: float = Field(ge=0, le=1)  # 0-1; ≥0.8 only with multi-source corroboration
    horizon_days: int = Field(gt=0)
    price_ref: float | None = None
    invalidation_triggers: list[str] = Field(default_factory=list)


class KeyClaim(BaseModel):
    """An atomic, citation-linkable claim (redesign §3 ``key_claims[]``)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    evidence_refs: list[str] = Field(default_factory=list)
    weight: Literal["HIGH", "MEDIUM", "LOW", "CONTEXT"]
    confidence: float = Field(ge=0, le=1)


class Contradiction(BaseModel):
    """A first-class bull/bear contradiction (Veto #3; redesign §3 ``contradictions[]``)."""

    model_config = ConfigDict(extra="forbid")

    bull: str
    bear_evidence: str
    bear_claim: str
    resolution: str


class DecisionCard(BaseModel):
    """The canonical v2.0 analysis output card (redesign §3 YAML).

    Field names match the §3 YAML example verbatim so the card round-trips through
    ``model_dump(mode="json")``. SC#5 hard veto (Veto #2) is enforced by the
    non-Optional ``expires_at`` and ``assumptions`` ``min_length=1`` declarations.
    """

    model_config = ConfigDict(extra="forbid")

    card_id: str
    corp_code: str = Field(pattern=r"^[0-9]{8}$")
    ticker: str = Field(pattern=r"^[0-9A-Z]{6}$")  # KRX 6-char uppercase-alphanumeric short code
    generated_at: datetime
    as_of: datetime  # data cutoff (KST close)
    schema_version: int = 1
    decision: Decision
    key_claims: list[KeyClaim] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)  # Veto #3: 1st-class output
    assumptions: list[str] = Field(min_length=1)  # SC#5 HARD VETO: empty list → ValidationError
    numeric_facts: dict[str, float | int] = Field(default_factory=dict)  # shape-only; Phase 4 checksums digits
    evidence_weights: dict[str, str] = Field(default_factory=dict)
    guards_passed: list[str] = Field(default_factory=list)
    expires_at: datetime  # SC#5 HARD VETO: no default, no Optional → omission = ValidationError
    body_md: str
    # OPTIONAL — not in the §3 YAML, but redesign §4 lists it as a payload/frontmatter
    # field. Plan 03 invalidate() writes it into the payload JSONB; the model MUST accept
    # it or extra="forbid" reconstruction of a post-jsonb_set payload would raise. Stays
    # inside payload — adds NO DB column, so the SC#1 locked column set is untouched.
    invalidation_reason: str | None = None
    # OPTIONAL — KST ISO-8601 timestamp of when invalidate() ran, stamped INTO the
    # payload JSONB alongside invalidation_reason (05-02, OQ1 option a). Makes
    # "invalidated on date D" queryable by list_cards_for_briefing without a new DB
    # column. The model MUST accept it or extra="forbid" reconstruction of a
    # post-jsonb_set payload would raise. Rides in payload exactly like
    # invalidation_reason; defaults None so the §3 round-trip is unaffected.
    invalidated_at: str | None = None
    # OPTIONAL — the lifecycle status lives in the decision_cards.status DB COLUMN
    # (active/superseded/invalidated), NOT in the §3 YAML payload. Plan 03's store layer
    # merges the column value in when reconstructing a card so get_active/invalidate/
    # walk_supersedes can surface `.status` on the returned DecisionCard. Defaults to None
    # (a freshly-built, not-yet-persisted card has no DB status) so the SC#3 round-trip of
    # the §3 YAML is unaffected. Adds NO new DB column — the column already exists (SC#1).
    status: str | None = None
    # OPTIONAL — D-03 / SC#3 typed home for numeric facts the Phase-4 checksum DROPPED
    # (a value the sub-agent emitted that is NOT derivable from source; Veto #1/#4 — the
    # brain compresses evidence, it never self-certifies its numbers). Each entry is a
    # human-readable "{key}={value}{unit}: not verifiable in source" string, so a dropped
    # fact is never silently lost. Rides in the payload JSONB exactly like invalidation_reason
    # above — it is NOT in _PAYLOAD_EXCLUDE (src/cards/store.py), so it persists in payload
    # and adds NO DB column. Defaults empty, so the §3 round-trip is unaffected.
    warnings: list[str] = Field(default_factory=list)
