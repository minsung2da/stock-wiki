"""Prompt-injection defense scaffolding (INGEST-08/09, threat T-3-01).

Implements D-15 (3-layer scaffolding), D-16 (XML delimiter format),
D-18 (pattern prefilter table, English + Korean), D-19 (trust_level gate helper).

This module is intentionally side-effect-free and imports nothing from the
database or LLM libraries — it is a leaf utility consumed by the ingest
worker (Plan 04) and by stock-mcp (Plan 05) to wrap retrieved excerpts.

Pattern IDs are stable across releases; downstream frontmatter records
`ingest_state.injection_flags: [pattern_ids]` so the IDs must remain queryable.
"""

from __future__ import annotations

import re

__all__ = [
    "PATTERNS",
    "wrap_untrusted",
    "detect_injection_patterns",
    "is_adversarial",
]


# D-18 seeded pattern table — ordered; do not reorder without a data migration,
# downstream consumers snapshot the ID list (see tests/test_injection_defense.py).
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "EN_IGNORE_PREV",
        re.compile(
            r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|prompts|rules)",
            re.IGNORECASE,
        ),
    ),
    (
        "FAKE_SYSTEM_TAG",
        re.compile(
            r"</?(?:system|assistant|user|instructions|prompt)\s*>",
            re.IGNORECASE,
        ),
    ),
    (
        "DAN_MODE",
        re.compile(r"\b(?:DAN\s*mode|jailbreak|developer\s+mode)\b", re.IGNORECASE),
    ),
    (
        "ROLEPLAY_ADMIN",
        re.compile(
            r"(?:role[-\s]?play\s+as|pretend\s+(?:you\s+are|to\s+be))\s+(?:admin|root|system)",
            re.IGNORECASE,
        ),
    ),
    (
        "KO_IGNORE_PREV",
        re.compile(r"이전\s*(?:지시|프롬프트)\s*무시"),
    ),
    (
        "KO_ADMIN_MODE",
        re.compile(r"관리자\s*모드|시스템\s*프롬프트\s*출력"),
    ),
]


# Attribute safety regexes — keep the delimiter injection-proof.
_SAFE_ATTR_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_SAFE_DOC_ID_RE = re.compile(r"^[a-f0-9]{1,32}$")


def wrap_untrusted(
    body: str,
    source: str,
    trust_level: str,
    doc_id: str,
) -> str:
    """Wrap untrusted body text in the D-16 XML delimiter.

    Attributes are validated against strict character classes; a failed
    validation raises ``ValueError`` with a generic message that never
    includes the offending value (info-disclosure guard for T-3-15).

    The delimiter is NOT an authentication primitive — it only marks a
    trust boundary for downstream LLM consumers. Actual enforcement is
    the LLM's responsibility (Phase 5).
    """
    if not _SAFE_ATTR_RE.match(source):
        raise ValueError("invalid source attribute")
    if not _SAFE_ATTR_RE.match(trust_level):
        raise ValueError("invalid trust_level attribute")
    if not _SAFE_DOC_ID_RE.match(doc_id):
        raise ValueError("invalid doc_id attribute")
    open_tag = f'<untrusted source="{source}" trust="{trust_level}" doc_id="{doc_id}">'
    return f"{open_tag}\n{body}\n</untrusted>"


def detect_injection_patterns(body: str) -> list[dict]:
    """Scan ``body`` for D-18 injection patterns.

    Returns a list of matches sorted by starting offset. Each match is a
    dict with:
      - ``pattern_id``: stable string ID from PATTERNS
      - ``match``: substring (truncated to 80 chars)
      - ``span``: (start, end) offsets in the original body
    """
    hits: list[dict] = []
    for pid, rx in PATTERNS:
        for m in rx.finditer(body):
            hits.append(
                {
                    "pattern_id": pid,
                    "match": m.group(0)[:80],
                    "span": (m.start(), m.end()),
                }
            )
    hits.sort(key=lambda h: h["span"][0])
    return hits


def is_adversarial(trust_level: str) -> bool:
    """Gate helper for INGEST-09 — only ``"adversarial"`` is skipped from LLM."""
    return trust_level == "adversarial"
