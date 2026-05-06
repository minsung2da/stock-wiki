"""Pydantic v2 models for the 3-zone frontmatter schema.

Zone 1 (provenance): Written by collectors at fetch time. Never overwritten by ingest.
    trust_level gates prompt-injection defense (D-19): trusted (DART/ECOS/FRED) →
    LLM-allowed; semi_trusted (news) → allowed with delimiter wrap; adversarial
    (forums) → LLM-skipped (INGEST-09).
Zone 2 (ingest_state): Written by ingest pipeline. Tracks processing state.
    injection_flags: pattern IDs from detect_injection_patterns (D-18) — recorded
    by the ingest worker (Plan 04) so downstream LLM gates can skip poisoned docs.
Zone 3 (_derived): LLM-extracted attributes. Regenerable; do not hand-edit.

Dataview queries use nested access: WHERE provenance.source = "dart" (per D-11).
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import frontmatter as fm
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class TickerRef(BaseModel):
    """Typed ticker reference embedded in news ProvenanceBlock.tickers (R-07, D-10)."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(pattern=r"^[0-9]{6}$")
    corp_code: str | None = Field(default=None, pattern=r"^[0-9]{8}$")
    name: str | None = None  # canonical_name at fetch time (optional)


class Observation(BaseModel):
    """Typed macro observation embedded in ProvenanceBlock.observations (R-07, D-07)."""

    model_config = ConfigDict(extra="forbid")

    date: date_type  # pydantic auto-coerces ISO-8601 YYYY-MM-DD strings
    value: float


class ProvenanceBlock(BaseModel):
    """Zone 1: Written by collectors. Never overwritten by ingest."""

    source: str  # dart | naver | news | macro | krx | note | kind
    source_id: str | None = None
    source_url: str | None = None
    date: str | None = None
    fetched_at: datetime | None = None
    content_hash: str | None = None
    corp_code: str | None = None  # DART 8-digit canonical ID
    ticker: str | None = None  # KRX 6-digit convenience field
    company_name: str | None = None  # Canonical corp name (Bug D-1: re-seed entities on rebuild)
    lang: str = "ko"
    trust_level: Literal["trusted", "semi_trusted", "adversarial"] = "trusted"
    # --- Phase 4 additive fields (all Optional defaulting to None) ---
    # news writer (Plan 04): tickers matched against entity_aliases (D-10 step 4).
    tickers: list[TickerRef] | None = None
    outlet: str | None = None  # news: 'hankyung' | 'edaily' | ... (D-09)
    # news: D-13 legal flag — 'summary_only' for copyrighted outlets, 'full' otherwise.
    license_flag: Literal["summary_only", "full"] | None = None
    # macro writer (Plan 03): [{date, value}, ...] (D-07).
    observations: list[Observation] | None = None


class IngestStateBlock(BaseModel):
    """Zone 2: Written by ingest pipeline. Tracks processing state."""

    processed: bool = False
    processed_at: datetime | None = None
    embedding_model: str | None = None
    ingest_model: str | None = None
    ingest_version: int | None = None
    injection_flags: list[str] = Field(default_factory=list)


class ReviewFlag(BaseModel):
    """D-11: structured review marker attached to DerivedBlock when validation fails."""

    model_config = ConfigDict(extra="forbid")

    flag: Literal[
        "numeric_echo_mismatch",
        "numeric_sanity_violation",
        "dart_structured_disagreement",
        "self_inconsistent",
        "oversize_skipped",
        "prompt_injection_suspected",
        "sentiment_score_label_mismatch",
        "agent_zone_violation",
        "merge_conflict",
    ]
    detail: str
    fact_key: str | None = None


class SentimentBlock(BaseModel):
    """D-10: tone/outcome sentiment with Literal label."""

    model_config = ConfigDict(extra="forbid")

    label: (
        Literal[
            "strongly_bullish",
            "bullish",
            "neutral",
            "bearish",
            "strongly_bearish",
            "unclear",
        ]
        | None
    ) = None
    bullish_score: float | None = None  # 0.0-1.0, null allowed
    rationale: str | None = None
    scope: Literal["tone", "outcome"] | None = None


class NumericFact(BaseModel):
    """D-09: numeric fact with Literal unit, KRW normalization, source span echo-back."""

    model_config = ConfigDict(extra="forbid")

    key: str
    value: float
    unit: Literal[
        "KRW원",
        "KRW백만",
        "KRW억",
        "KRW조",
        "USD",
        "EUR",
        "JPY",
        "pct",
        "bps",
        "multiplier",
        "shares",
        "days",
        "other",
    ]
    value_krw: float | None = None
    source_span: str | None = None
    offset: int | None = None


# D-08: full event_type Literal enum.
EventType = Literal[
    # DART 주요사항 (8)
    "earnings_release",
    "equity_issue",
    "mergers_acquisitions",
    "major_contract",
    "board_change",
    "ownership_change",
    "buyback_announcement",
    "dividend",
    # DART 거래소공시 (4)
    "suspension",
    "watchlist_designation",
    "unfaithful_disclosure",
    "delisting",
    # KIND (2)
    "investment_caution",
    "investment_risk",
    # 뉴스·리포트 (4)
    "analyst_upgrade",
    "analyst_downgrade",
    "macro_commentary",
    "market_gossip",
    # fallback
    "other",
]


class DerivedBlock(BaseModel):
    """Zone 3: LLM-extracted attributes. Regenerable; do not hand-edit."""

    model_config = ConfigDict(extra="forbid")

    tickers: list[str] = Field(default_factory=list)
    event_type: EventType | None = None
    catalysts: list[str] = Field(default_factory=list)
    sentiment: SentimentBlock | None = None
    numeric_facts: list[NumericFact] = Field(default_factory=list)
    summary: str | None = None
    # --- Phase 5 additive ---
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    skip_reason: Literal["oversize", "review_required", "merge_conflict"] | None = None


class FrontMatter(BaseModel):
    """Top-level frontmatter container. Maps to YAML 1:1 (per D-10).

    YAML key '_derived' maps to the 'derived' Python field via alias.
    Use model_dump(by_alias=True) to emit '_derived' key in YAML output.
    Use model_config populate_by_name=True to accept both 'derived' and '_derived'.
    """

    provenance: ProvenanceBlock
    ingest_state: IngestStateBlock = Field(default_factory=IngestStateBlock)
    derived: DerivedBlock = Field(default_factory=DerivedBlock, alias="_derived")

    model_config = {"populate_by_name": True}


def read_frontmatter(path: str) -> tuple[FrontMatter, str]:
    """Read a markdown file and parse its frontmatter into a Pydantic model.

    Returns:
        Tuple of (FrontMatter model, document body text).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If frontmatter YAML is malformed or fails schema validation.
    """
    try:
        post = fm.load(path)
    except Exception as exc:
        raise ValueError(f"Failed to load frontmatter from {path!r}: {exc}") from exc
    try:
        model = FrontMatter.model_validate(dict(post.metadata))
    except ValidationError as exc:
        raise ValueError(f"Frontmatter schema validation failed for {path!r}: {exc}") from exc
    return model, post.content


def write_frontmatter(path: str, model: FrontMatter, body: str) -> None:
    """Write a markdown file with validated frontmatter.

    Uses model_dump(by_alias=True, exclude_none=True) to emit '_derived'
    key and omit None values for clean YAML output.

    Content is fully computed before the file is opened, so a serialization
    error will not leave a zero-byte or partial file at path.

    Uses an atomic write pattern (write to temp file in same directory, then
    os.replace) so a crash or KeyboardInterrupt during the write cannot leave a
    partial file at path.  os.replace() is atomic on POSIX; on Windows it is
    best-effort (not guaranteed atomic but still safe — the original file is
    only removed after the temp write succeeds).
    """
    import contextlib
    import os
    import tempfile
    from pathlib import Path

    post = fm.Post(body)
    post.metadata = model.model_dump(by_alias=True, exclude_none=True)
    content = fm.dumps(post)  # Compute before opening file
    dir_ = Path(path).parent
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(content)
        os.replace(tmp_path, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def _derived_is_populated(derived: DerivedBlock) -> bool:
    """Return True if any DerivedBlock field is non-default.

    Mirrors the heuristic used by ``.claude/routines/enrich/helpers/walk.py``;
    duplicated here intentionally to avoid an ``src/`` ↔ ``.claude/routines/``
    import (layering smell).
    """
    return bool(
        derived.tickers
        or derived.event_type
        or derived.catalysts
        or derived.sentiment is not None
        or derived.numeric_facts
        or derived.summary
        or derived.review_flags
        or derived.skip_reason is not None
    )


def read_existing_derived(path: Path) -> DerivedBlock | None:
    """Return the prior ``_derived`` block from a vault file, or None.

    Quick task 260426-k8h: collectors call this BEFORE constructing a fresh
    ``FrontMatter`` so the Phase 5 Routine-enriched ``_derived`` block is
    carried forward verbatim across collector rewrites. ``walk.find_candidates``
    remains the single freshness gate (CONTEXT.md D-01).

    Returns ``None`` when:
      - the file does not exist (first-time collection),
      - frontmatter cannot be parsed (malformed YAML / schema fail),
      - or the ``_derived`` block is structurally empty (default).

    NOTE: callers must NOT feed the returned block into content_hash
    computation. The new content_hash MUST be computed solely from the new
    body — no hash poisoning from carried-over enrichment.
    """
    if not path.exists():
        return None
    try:
        model, _body = read_frontmatter(str(path))
    except (ValueError, OSError):
        return None
    if not _derived_is_populated(model.derived):
        return None
    return model.derived


def read_existing_injection_flags(path: Path) -> list[str] | None:
    """Return prior ``ingest_state.injection_flags`` from a vault file, or None.

    Quick task 260426-mic: collectors call this BEFORE constructing a fresh
    ``FrontMatter`` so the D-18 prompt-injection security marker
    (``ingest_state.injection_flags``) is carried forward verbatim across
    collector rewrites. Without this, a previously-flagged adversarial doc
    becomes silently re-eligible for LLM extraction the next time the routine
    sees it (security regression — k8h REVIEW WR-01).

    Returns ``None`` when:
      - the file does not exist (first-time collection),
      - frontmatter cannot be parsed (malformed YAML / schema fail),
      - or ``injection_flags`` is empty (default).

    NOTE: Call BEFORE computing the new content_hash. Must NOT feed into hash
    computation. The new ``content_hash`` MUST be computed solely from the new
    body — no hash poisoning from carried-over markers.

    SCOPE: ONLY ``injection_flags`` is preserved. Other ``ingest_state`` fields
    (``processed``, ``processed_at``, ``embedding_model``, ``ingest_model``,
    ``ingest_version``) are pipeline-state markers owned by the ingest worker;
    they MUST reset on collector rewrite so re-processing is correctly
    triggered. ``injection_flags`` is the sole security marker that must
    survive.
    """
    if not path.exists():
        return None
    try:
        model, _body = read_frontmatter(str(path))
    except (ValueError, OSError):
        return None
    flags = model.ingest_state.injection_flags
    if not flags:
        return None
    return list(flags)


# ---------------------------------------------------------------------------
# Phase 6 Plan 06-02 (Task 2): NoteFrontmatter
# Schema for user-authored notes written via the ``add_note`` MCP tool (D-11).
# Phase 8 NOTE-03 will reuse this exact model — defined here so both Phase 6
# (write path) and Phase 8 (downstream consumers) read from one place.
# ---------------------------------------------------------------------------


def _now_kst() -> datetime:
    return datetime.now(ZoneInfo("Asia/Seoul"))


class NoteFrontmatter(BaseModel):
    """Frontmatter schema for ``add_note`` user-authored notes (D-11).

    ``type`` is required; ``created``/``updated`` auto-fill to now (KST) when
    omitted. ``conviction_score`` is optional and bounded to [0.0, 1.0].

    Phase 8 D-15 update: ``extra='allow'`` so user free-form keys (e.g. ``mood``,
    ``weather``) do not crash ingest. Schema violations on KNOWN fields are
    caught by ``ingest.parsers.note.parse_note`` and recorded as
    ``note_schema_violation`` review_flags (Pitfall 4 avoidance). add_note
    still validates by passing the dict to this model — unknown keys silently
    pass through, but Literal/range constraints on known fields still raise.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: Literal["thesis", "journal", "conviction", "note"]
    tickers: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created: datetime = Field(default_factory=_now_kst)
    updated: datetime = Field(default_factory=_now_kst)
    author: str = "yamin"
    conviction_score: float | None = Field(default=None, ge=0.0, le=1.0)


class ThesisFrontmatter(NoteFrontmatter):
    """Phase 8 D-13 — thesis-specific extension of NoteFrontmatter.

    Adds ``kill_criteria``, ``conviction``, ``target_price`` for NOTE-01
    research memos. Inherits ``extra='allow'`` policy from NoteFrontmatter.
    """

    type: Literal["thesis"] = "thesis"  # type: ignore[assignment]
    kill_criteria: list[str] = Field(default_factory=list)
    conviction: Literal["low", "medium", "high"] = "medium"
    target_price: int | None = None  # KRW


# Dispatch table (Phase 8 D-15) — frontmatter['type'] → Pydantic class.
# ``ingest.parsers.note.parse_note`` looks up by raw frontmatter ``type`` value;
# unknown types fall back to NoteFrontmatter.
NOTE_MODEL_BY_TYPE: dict[str, type[NoteFrontmatter]] = {
    "thesis": ThesisFrontmatter,
    "journal": NoteFrontmatter,
    "conviction": NoteFrontmatter,
    "note": NoteFrontmatter,
}
