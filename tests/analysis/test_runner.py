"""SC#1-7 integration tests for ``analysis.runner.analyze_ticker`` (Plan 04-06).

Each SC is locked by ONE named, quota-free test. The whole file injects the
``FakeDebateBackend`` (canned per-role ``structured_output`` + a ``.calls`` recorder),
so NO real ``claude`` process is ever spawned and ZERO Max quota is spent — the live
CLI path is proven separately, opt-in, in ``test_live.py`` under ``-m live``.

- ``test_returns_and_saves_card``           — SC#1 (return + active-save + supersede)
- ``test_blind_parallel``                   — SC#2 (Bull/Bear identical stdin; Judge sees both)
- ``test_numeric_checksum_drops``           — SC#3 (fabricated fact dropped → warnings)
- ``test_veto2_rejects_untimed``            — SC#4 (assumption-less Judge → ValidationError)
- ``test_empty_contradictions_warns``       — SC#5 (empty contradictions logs a warning)
- ``test_same_stance_refresh_skips_debate`` — SC#6 (no-trigger prior → REFRESH, backend untouched)
- ``test_cost_logged``                      — SC#7 (per-stage cost lines for bundle + each role)

``encode_query`` is stubbed to the seeded constant vector so ``build_bundle``'s
``hybrid_search`` runs without the ~2GB bge-m3 download (mirrors ``test_bundle.py``).
The typed tools reach the same test DB via their own ``get_engine()`` (``DATABASE_URL``
set by ``pg_engine``), so seeding ``seeded_engine`` is sufficient — no ``get_engine``
monkeypatch.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from analysis import analyze_ticker
from cards.models import Decision, DecisionCard, KeyClaim
from cards.store import get_active, save_card, walk_supersedes
from mcp_v2 import retrieval

_KST = ZoneInfo("Asia/Seoul")
_STUB_QVEC = tuple([0.01] * 1024)  # matches the seeded constant halfvec


def _dt(y: int, m: int, d: int, hh: int = 16) -> datetime:
    """A KST-close datetime (cards round-trip with +09:00)."""
    return datetime(y, m, d, hh, 0, tzinfo=_KST)


# After both seeded filings (2026-05-20 / 2026-04-15) so a fresh prior card never trips
# the new-filing gate trigger; matches the working as_of in test_bundle.py.
_AS_OF = _dt(2026, 6, 25)
_SEEDED_FILING = "dart:20260520000001"  # resolves via the seeded_engine filings


@pytest.fixture(autouse=True)
def _stub_query_embedder(monkeypatch) -> None:
    """Patch encode_query so build_bundle's hybrid_search skips the bge-m3 download."""
    monkeypatch.setattr(retrieval, "encode_query", lambda _q: _STUB_QVEC)


def _prior(
    *,
    as_of: datetime,
    generated_at: datetime,
    expires_at: datetime,
    card_id: str = "card_005930_prior",
    evidence: str = _SEEDED_FILING,
) -> DecisionCard:
    """A valid prior active DecisionCard for 삼성전자 whose evidence resolves by default."""
    return DecisionCard(
        card_id=card_id,
        corp_code="00126380",
        ticker="005930",
        generated_at=generated_at,
        as_of=as_of,
        decision=Decision(
            stance="HOLD",
            conviction=0.55,
            horizon_days=30,
            invalidation_triggers=["memory ASP guidance < -10% QoQ"],
        ),
        key_claims=[
            KeyClaim(
                id="c1",
                text="HBM3E qualification catalyst pending",
                evidence_refs=[evidence],
                weight="MEDIUM",
                confidence=0.6,
            )
        ],
        assumptions=["DRAM contract ASP holds"],
        expires_at=expires_at,
        body_md="# 삼성전자 (005930) — HOLD\n",
    )


# --------------------------------------------------------------------------- #
# SC#1 — returns ONE card, saves it active, atomically supersedes the prior.
# --------------------------------------------------------------------------- #
def test_returns_and_saves_card(seeded_engine, make_fake_backend) -> None:
    """A FULL run returns a DecisionCard, persists it as the active card, and
    supersedes the prior active card in the same store transaction."""
    # A near-expiry prior forces the gate to FULL (so the debate runs and supersedes).
    prior = _prior(
        as_of=_dt(2026, 6, 20),
        generated_at=_dt(2026, 6, 20),
        expires_at=_dt(2026, 6, 28),  # within 7d of _AS_OF → near-expiry FULL trigger
    )
    save_card(seeded_engine, prior)
    backend = make_fake_backend()

    card = analyze_ticker("00126380", as_of=_AS_OF, engine=seeded_engine, backend=backend)

    assert isinstance(card, DecisionCard)
    # It is the active card now, and it is NOT the prior.
    active = get_active(seeded_engine, "00126380")
    assert active is not None
    assert active.card_id == card.card_id
    assert card.card_id != prior.card_id
    # The FULL debate actually ran (all three roles) ...
    assert [c.role for c in backend.calls] == ["bull", "bear", "judge"]
    # ... and the new card supersedes the prior (atomic supersession chain).
    chain_ids = [c.card_id for c in walk_supersedes(seeded_engine, card.card_id)]
    assert prior.card_id in chain_ids


# --------------------------------------------------------------------------- #
# SC#2 — Bull/Bear parallel-blind over the SAME stdin; Judge synthesizes both.
# --------------------------------------------------------------------------- #
def test_blind_parallel(seeded_engine, make_fake_backend) -> None:
    """Bull and Bear receive identical stdin and neither sees the other's output; the
    Judge receives the bundle plus BOTH sub-agent outputs."""
    backend = make_fake_backend()  # no prior → first-run FULL

    analyze_ticker("00126380", as_of=_AS_OF, engine=seeded_engine, backend=backend)

    assert [c.role for c in backend.calls] == ["bull", "bear", "judge"]
    bull_call = next(c for c in backend.calls if c.role == "bull")
    bear_call = next(c for c in backend.calls if c.role == "bear")
    judge_call = next(c for c in backend.calls if c.role == "judge")

    # Bull and Bear got the IDENTICAL evidence bundle ...
    assert bull_call.evidence_stdin == bear_call.evidence_stdin
    # ... and are BLIND: neither carries the debate appendix nor the other's output.
    assert "BULL OUTPUT" not in bull_call.evidence_stdin
    assert "BEAR OUTPUT" not in bear_call.evidence_stdin
    assert "ASP downtrend risk" not in bull_call.evidence_stdin  # bear's canned disconfirming

    # The Judge sees the bundle (as a prefix) plus BOTH outputs (SC#2c synthesis).
    assert judge_call.evidence_stdin.startswith(bull_call.evidence_stdin)
    assert "BULL OUTPUT" in judge_call.evidence_stdin
    assert "BEAR OUTPUT" in judge_call.evidence_stdin
    assert "ASP downtrend risk" in judge_call.evidence_stdin  # bear output reached the Judge
    # A bull-only canned marker also reached the Judge (proves both feeds, not one).
    bull_marker = "HBM3E 12-stack NVIDIA qualification is a near-term catalyst"
    assert bull_marker in judge_call.evidence_stdin


# --------------------------------------------------------------------------- #
# SC#3 — a fabricated numeric fact is dropped and recorded in warnings.
# --------------------------------------------------------------------------- #
def test_numeric_checksum_drops(seeded_engine, make_fake_backend, canned_judge) -> None:
    """A Judge numeric fact absent from the bundle bodies is dropped from
    ``numeric_facts`` and surfaced in ``warnings`` (never silently kept)."""
    variant = dict(canned_judge)
    variant["numeric_facts"] = [
        # verifiable — 42.5조원 appears verbatim in the seeded filing body
        {"key": "revenue_krw", "value": 42.5, "unit": "조원", "source_ref": _SEEDED_FILING},
        # fabricated — 987,654억원 (≈9.9e16 KRW) appears nowhere in the bundle
        {"key": "fabricated_metric", "value": 987654.0, "unit": "억원", "source_ref": "dart:x"},
    ]
    backend = make_fake_backend(judge=variant)

    card = analyze_ticker("00126380", as_of=_AS_OF, engine=seeded_engine, backend=backend)

    assert "revenue_krw" in card.numeric_facts  # verifiable fact survived
    assert "fabricated_metric" not in card.numeric_facts  # dropped
    assert any("fabricated_metric" in w for w in card.warnings)  # recorded, not lost


# --------------------------------------------------------------------------- #
# SC#4 — Veto #2: an assumption-less thesis is rejected at construction.
# --------------------------------------------------------------------------- #
def test_veto2_rejects_untimed(seeded_engine, make_fake_backend, canned_judge) -> None:
    """A Judge output with no ``assumptions`` fails ``DecisionCard`` validation (even
    after the single Judge retry) → the run raises ``ValidationError`` (Veto #2)."""
    variant = {k: v for k, v in canned_judge.items() if k != "assumptions"}
    backend = make_fake_backend(judge=variant)

    with pytest.raises(ValidationError):
        analyze_ticker("00126380", as_of=_AS_OF, engine=seeded_engine, backend=backend)


# --------------------------------------------------------------------------- #
# SC#5 — an empty contradictions[] logs a warning (Veto #3 observability).
# --------------------------------------------------------------------------- #
def test_empty_contradictions_warns(
    seeded_engine, make_fake_backend, canned_judge, caplog
) -> None:
    """A card with no contradictions is saved but logs a 'no contradictions' warning."""
    variant = dict(canned_judge)
    variant["contradictions"] = []
    backend = make_fake_backend(judge=variant)

    with caplog.at_level(logging.WARNING, logger="analysis.runner"):
        card = analyze_ticker("00126380", as_of=_AS_OF, engine=seeded_engine, backend=backend)

    assert card.contradictions == []
    assert any("no contradictions" in r.getMessage() for r in caplog.records)


# --------------------------------------------------------------------------- #
# SC#6 — a same-stance, no-trigger prior takes the cheap refresh; backend untouched.
# --------------------------------------------------------------------------- #
def test_same_stance_refresh_skips_debate(seeded_engine, make_fake_backend) -> None:
    """With a fresh prior and no gate trigger, the REFRESH path saves a refreshed card
    WITHOUT ever calling the sub-agent backend (SC#6 'skip the debate')."""
    prior = _prior(
        as_of=_dt(2026, 6, 25),  # after both filings → no new-filing trigger
        generated_at=_dt(2026, 6, 25),
        expires_at=_dt(2026, 8, 25),  # far → no near-expiry
    )
    save_card(seeded_engine, prior)
    backend = make_fake_backend()

    result = analyze_ticker(
        "00126380", as_of=_dt(2026, 6, 30), engine=seeded_engine, backend=backend
    )

    assert isinstance(result, DecisionCard)
    assert backend.calls == []  # the debate backend was NEVER touched (SC#6)
    active = get_active(seeded_engine, "00126380")
    assert active is not None
    assert active.card_id == result.card_id
    assert result.card_id != prior.card_id  # a fresh refreshed card, superseding prior


# --------------------------------------------------------------------------- #
# SC#7 — per-stage cost/time is emitted for the bundle build + each sub-agent call.
# --------------------------------------------------------------------------- #
def test_cost_logged(seeded_engine, make_fake_backend, caplog) -> None:
    """One structured cost line per stage (bundle + bull + bear + judge) is emitted."""
    backend = make_fake_backend()  # no prior → first-run FULL

    with caplog.at_level(logging.INFO, logger="analysis.cost"):
        analyze_ticker("00126380", as_of=_AS_OF, engine=seeded_engine, backend=backend)

    stages = {
        r.stage for r in caplog.records if r.getMessage() == "analysis_stage_cost"
    }
    assert {"bundle", "bull", "bear", "judge"} <= stages
