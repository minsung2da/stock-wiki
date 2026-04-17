"""DART section parser (D-07, A4 follow-up).

Extracts hierarchical sections from DART filing body text using Korean-numeral
TOC markers (``I. …``, ``1. …``, etc).

Phase-3 scope: DART 주요사항보고서 bodies typically fit in a single root section;
정기보고서 bodies carry the standard 목차 so we split by heading lines. The
collector in Plan 02 stores only the plain-text body (not the structured
``Report.to_dict()`` dict), so this layer uses a regex over line starts rather
than calling back into dart-fss. Documented as Assumption A4 follow-up; Plan 04
or v2 may upgrade to use the dart-fss TOC accessor directly if needed.

Case A (TOC present): scan lines, maintain a title stack keyed by depth, emit
  a Section for each heading with ``path`` = "/".join(ancestor_titles).
Case B (no TOC): return a single root-level Section.
Robustness fallback: if Case A yields zero sections or only empty titles,
fall back to Case B.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["parse_sections", "Section"]


@dataclass
class Section:
    title: str
    path: str
    text: str
    order: int


# Heading line patterns — depth inferred from marker style.
#   Roman numeral + dot + space + non-space  ->  depth 0 ("I. 회사의 개요")
#   Arabic numeral + dot + space + non-space ->  depth 1 ("1. 회사의 개요")
_ROMAN_HEAD_RE = re.compile(r"^([IVX]+)\.\s+(\S.*)$")
_ARABIC_HEAD_RE = re.compile(r"^([0-9]+)\.\s+(\S.*)$")


def _classify_heading(line: str) -> tuple[int, str] | None:
    """Return (depth, title) for a heading line or None for body text."""
    m = _ROMAN_HEAD_RE.match(line)
    if m:
        return 0, line.strip()
    m = _ARABIC_HEAD_RE.match(line)
    if m:
        return 1, line.strip()
    return None


def parse_sections(body: str, source: str) -> list[Section]:  # noqa: ARG001  (source unused; kept for signature parity)
    lines = body.splitlines()
    sections: list[Section] = []
    stack: list[str] = []  # stack[depth] = current title at that depth
    current_title: str | None = None
    current_path: str | None = None
    current_text_lines: list[str] = []
    order = 0

    def flush() -> None:
        nonlocal order
        if current_title is None:
            return
        sections.append(
            Section(
                title=current_title,
                path=current_path or current_title,
                text="\n".join(current_text_lines).strip(),
                order=order,
            )
        )
        order += 1

    for line in lines:
        cls = _classify_heading(line)
        if cls is not None:
            depth, title = cls
            # Flush previous section
            flush()
            # Adjust the ancestor stack for this depth
            del stack[depth:]
            stack.append(title)
            current_title = title
            current_path = "/".join(stack)
            current_text_lines = []
        else:
            if current_title is not None:
                current_text_lines.append(line)
    # Flush trailing section
    flush()

    # Case B / robustness fallback
    if not sections or all(not s.title for s in sections):
        return [Section(title="(root)", path="(root)", text=body, order=0)]
    return sections
