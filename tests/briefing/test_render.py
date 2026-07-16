"""tests/briefing/test_render.py — 6-column body_md render + build_entry (Task 2, D-04/05/06).

The 제안 column is a bare stance label + conviction only (Veto #1 — never a forecast /
target). The Why-not column is the top contradiction bear_claim (Veto #3).
"""

from __future__ import annotations

import re

from briefing.daily import ChangeEvent, build_entry, render_body_md


def _entry(make_card, *, stance="HOLD", conviction=0.42, contradictions=None, key_claims=None):
    card = make_card(
        corp_code="00000001",
        ticker="000001",
        stance=stance,
        conviction=conviction,
        contradictions=contradictions,
        key_claims=key_claims,
    )
    return build_entry(ChangeEvent(card=card, event_class="stance_flip", change="SELL→HOLD"))


def test_header_is_exact(make_card):
    body = render_body_md([_entry(make_card)])
    assert "종목 | 변화 | 근거 | 제안 | Why now | Why not" in body


def test_jean_is_stance_plus_conviction_only(make_card):
    body = render_body_md([_entry(make_card, stance="HOLD", conviction=0.42)])
    assert "HOLD (0.42)" in body
    # 제안 cell shape = STANCE (d.dd) — a rubric-decomposable compression, not a forecast.
    assert re.search(r"[A-Z]+ \(\d\.\d{2}\)", body)


def test_why_not_dash_when_no_contradictions(make_card):
    entry = _entry(make_card, contradictions=[])
    assert entry["why_not"] == "—"


def test_why_not_is_top_contradiction_bear_claim(make_card):
    entry = _entry(
        make_card,
        contradictions=[
            {
                "bull": "bull",
                "bear_evidence": "e",
                "bear_claim": "margin compression",
                "resolution": "unresolved",
            }
        ],
    )
    assert entry["why_not"] == "margin compression"


def test_why_now_is_top_weighted_key_claim(make_card):
    entry = _entry(
        make_card,
        key_claims=[
            {
                "id": "k1",
                "text": "low-weight note",
                "evidence_refs": ["dart:x"],
                "weight": "LOW",
                "confidence": 0.9,
            },
            {
                "id": "k2",
                "text": "HIGH catalyst",
                "evidence_refs": ["dart:y"],
                "weight": "HIGH",
                "confidence": 0.6,
            },
        ],
    )
    # weight HIGH outranks LOW even at lower confidence.
    assert entry["why_now"] == "HIGH catalyst"
    assert entry["evidence"] == "HIGH catalyst"


def test_empty_entries_render_short_message():
    assert render_body_md([]) == "오늘 유의미한 변화 없음"


def test_entry_is_flat_dict_with_locked_keys(make_card):
    entry = _entry(make_card)
    assert set(entry) == {
        "ticker",
        "name",
        "event_class",
        "change",
        "evidence",
        "stance",
        "conviction",
        "why_now",
        "why_not",
        "card_id",
    }
