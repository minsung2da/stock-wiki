"""Macro source parser (Phase 8 GAP-04).

ECOS/FRED 본문은 numeric series 표 + 짧은 메모 형태. DART처럼 TOC를 풀어내지
않고 단일 section으로 처리한다 (Phase 8 worker.process_private_note의 동일한
단일-section 패턴 — chunking + embedding은 정상 동작).

Empty/whitespace-only body → 빈 리스트 반환 (worker가 zero-section 문서를 안전히
스킵).
"""

from __future__ import annotations

from .dart import Section

__all__ = ["parse_sections"]


def parse_sections(body: str, source: str) -> list[Section]:
    text = body.strip()
    if not text:
        return []
    return [Section(title="body", path="body", text=text, order=0)]
