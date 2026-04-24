"""Stage 1 regex candidate extraction for the D-15 4-stage numeric pipeline.

Pure Python. No LLM, no I/O. Scans a body for numeric spans and returns each
as a NumericCandidate with character offsets and a guessed_unit. The LLM
(Stage 2) selects and echoes source_span verbatim; offsets seed the Stage 4
character-level echo-back check (Pitfall 4: Python str[i:j] is codepoint-
indexed, safe for Hangul).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

MAX_CANDIDATES_PER_DOC = 100

GuessedUnit = Literal[
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
    "index_pt",
    "other",
]


@dataclass(frozen=True)
class NumericCandidate:
    """A single numeric span identified by regex. Stage 1 output."""

    raw_text: str
    offset: int  # character index into body (codepoint-safe)
    length: int  # len(raw_text) in codepoints
    guessed_unit: str  # one of GuessedUnit; "other" if unclassified
    sentence_text: str
    pre_context: str
    post_context: str
    section_hint: str | None


# --- Pattern library, ordered longest-first per unit family ---
# Number token: digits with optional comma-groups and decimal part.
_NUM = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"

# Order matters: more specific / longer patterns first. Non-overlapping
# enforcement below prevents a shorter pattern from claiming a span already
# covered by a longer one.
_PATTERNS: list[tuple[str, str]] = [
    # Compound KRW amounts with 조/억/만 mixture + trailing 원
    (rf"{_NUM}\s*조\s*{_NUM}\s*억(?:\s*원)?", "KRW조"),
    (rf"{_NUM}\s*억\s*{_NUM}\s*만(?:\s*원)?", "KRW억"),
    # Single-denom KRW
    (rf"{_NUM}\s*조(?:\s*원)?", "KRW조"),
    (rf"{_NUM}\s*백만\s*원", "KRW백만"),
    (rf"{_NUM}\s*억(?:\s*원)?", "KRW억"),
    # Shares (must precede plain 원)
    (rf"{_NUM}\s*만\s*주", "shares"),
    (rf"{_NUM}\s*주", "shares"),
    # Plain KRW
    (rf"{_NUM}\s*원", "KRW원"),
    # Index / 포인트
    (rf"{_NUM}\s*포인트", "index_pt"),
    # Foreign currency (달러/엔/유로)
    (rf"{_NUM}\s*달러", "USD"),
    (rf"{_NUM}\s*엔", "JPY"),
    (rf"{_NUM}\s*유로", "EUR"),
    # bps / multiplier / pct
    (rf"{_NUM}\s*bps\b", "bps"),
    (rf"{_NUM}\s*배", "multiplier"),
    (rf"{_NUM}\s*%", "pct"),
]

_COMPILED: list[tuple[re.Pattern[str], str]] = [(re.compile(pat), unit) for pat, unit in _PATTERNS]


def _split_sentences(body: str) -> list[tuple[int, int, str]]:
    """Return list of (start, end, text) for each sentence.

    Sentence boundary = '.' followed by whitespace/EOF, or newline. Simple and
    tolerant — downstream only needs each candidate's enclosing sentence.
    """
    out: list[tuple[int, int, str]] = []
    start = 0
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if ch == "\n" or (ch == "." and (i + 1 == n or body[i + 1].isspace())):
            end = i + 1
            text = body[start:end].strip()
            if text:
                out.append((start, end, text))
            start = end
        i += 1
    if start < n:
        text = body[start:n].strip()
        if text:
            out.append((start, n, text))
    return out


def _find_sentence(sentences: list[tuple[int, int, str]], offset: int) -> str:
    for s, e, t in sentences:
        if s <= offset < e:
            return t
    return ""


def extract_numeric_candidates(
    body: str,
    section_hint: str | None = None,
) -> list[NumericCandidate]:
    """Extract all numeric spans from ``body``.

    Returns up to ``MAX_CANDIDATES_PER_DOC`` candidates, non-overlapping,
    ordered by offset ascending. Each candidate's offset is a Python character
    index into ``body`` so ``body[offset:offset+length] == raw_text`` holds
    (echo-back precondition).
    """
    if not body:
        return []
    sentences = _split_sentences(body)
    claimed: list[tuple[int, int]] = []  # list of (start, end), kept sorted
    candidates: list[NumericCandidate] = []

    def _overlaps(s: int, e: int) -> bool:
        return any(not (e <= cs or s >= ce) for cs, ce in claimed)

    for pattern, unit in _COMPILED:
        for m in pattern.finditer(body):
            s, e = m.start(), m.end()
            if _overlaps(s, e):
                continue
            raw = body[s:e]
            sent = _find_sentence(sentences, s)
            pre = body[max(0, s - 5) : s]
            post = body[e : min(len(body), e + 5)]
            candidates.append(
                NumericCandidate(
                    raw_text=raw,
                    offset=s,
                    length=e - s,
                    guessed_unit=unit,
                    sentence_text=sent,
                    pre_context=pre,
                    post_context=post,
                    section_hint=section_hint,
                )
            )
            claimed.append((s, e))
            claimed.sort()

    candidates.sort(key=lambda c: c.offset)
    return candidates[:MAX_CANDIDATES_PER_DOC]
