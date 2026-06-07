"""Prompt-injection WRAP+FLAG defense for narrative tool bodies (D-03, SC#5).

Every tool that returns narrative text (``get_filing`` body_md, ``get_note``
content_md, ``hybrid_search`` snippet, ``get_decision_card`` view="both" body_md)
runs the body through this leaf module before returning it. The policy is **WRAP +
FLAG, NEVER block, NEVER strip** (D-03):

- :func:`wrap_untrusted` always wraps the body — UNCHANGED — in a distinctive
  ``<untrusted source="..." ref="...">…</untrusted>`` XML delimiter. The delimiter
  is a *boundary marker* for the downstream LLM (treat the contents as data), not
  an enforcement primitive. The full body bytes are preserved (stripping would
  corrupt the numeric verbatim-checksum the analysis layer depends on — a Veto).
- :func:`detect` scans the body against a stable EN+KO ``PATTERNS`` table and
  returns advisory match metadata. The tool sets ``injection_suspected=True`` and
  records the matched ``pattern_id``s. A match is FLAGGED, never blocked — blocking
  would silently disappear real DART/news (false negatives).

This module is intentionally side-effect-free and imports nothing from the DB or
LLM libraries — it is a pure leaf consumed by the tool modules (Plans 03-04/05/06).

Ported from the v1.0 archive ``src/ingest/injection_defense.py`` — the PATTERNS
table is verbatim; the archive's ``is_adversarial``/``trust_level`` GATE is dropped
(D-03 never gates). ``detect_injection_patterns`` is renamed ``detect``.

Pattern IDs are STABLE across releases: downstream return models record the matched
IDs, and ``tests/mcp_v2/test_injection.py`` snapshots the exact set so a reorder or
removal is caught.
"""

from __future__ import annotations

import re

__all__ = ["PATTERNS", "detect", "wrap_untrusted"]


# Stable, ordered EN+KO instruction-override / role-injection / fake-tag patterns.
# Do NOT reorder or rename without updating the test snapshot — downstream consumers
# record these IDs. Ported verbatim from archive src/ingest/injection_defense.py.
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


# Delimiter attribute safety: source / ref_id are interpolated into the XML open
# tag, so they must be a strict character class. Allows the dot/colon/hyphen that
# appear in legitimate provenance ids (e.g. a rcept_no, a "notes/private"-style
# source tag is passed pre-sanitized). On a bad attr we raise WITHOUT echoing the
# offending value (info-disclosure guard, T-03-06).
_SAFE_ATTR = re.compile(r"^[A-Za-z0-9_:.-]+$")


def detect(body: str) -> list[dict]:
    """Scan ``body`` for the :data:`PATTERNS` injection markers.

    NEVER raises on content (D-03 — flag, do not block). Returns a list of matches
    sorted by starting offset; each is ``{"pattern_id": str, "match": str (≤80
    chars), "span": [start, end]}``. An empty list means a clean body.
    """
    hits: list[dict] = []
    for pid, rx in PATTERNS:
        for m in rx.finditer(body):
            hits.append(
                {
                    "pattern_id": pid,
                    "match": m.group(0)[:80],
                    "span": [m.start(), m.end()],
                }
            )
    hits.sort(key=lambda h: h["span"][0])
    return hits


def wrap_untrusted(body: str, source: str, ref_id: str) -> str:
    """Wrap ``body`` UNCHANGED in the ``<untrusted>`` XML delimiter (D-03).

    The body is never modified, truncated, or stripped — only delimited. ``source``
    and ``ref_id`` are validated against :data:`_SAFE_ATTR`; on a bad attribute we
    raise ``ValueError("invalid delimiter attribute")`` whose message contains
    NEITHER the offending value NOR the body (info-disclosure guard, T-03-06).
    """
    if not _SAFE_ATTR.match(source) or not _SAFE_ATTR.match(ref_id):
        raise ValueError("invalid delimiter attribute")
    return f'<untrusted source="{source}" ref="{ref_id}">\n{body}\n</untrusted>'
