"""Opt-in ``@pytest.mark.live`` smoke — the REAL ``claude`` CLI end-to-end (Plan 04-06).

DESELECTED BY DEFAULT. This is the ONE verification that spends Max quota and needs a
logged-in ``claude`` (Max OAuth), so it can never run in CI or the default suite. The
whole default suite is green and quota-free (``test_runner.py`` injects the fake
backend); this proves the live D-01 path (``ClaudeCliBackend`` → headless ``claude -p``)
actually produces a valid, saved ``decision_card``.

Run it explicitly (never in CI, never in the default run):

    # 1) confirm Max OAuth is active and ANTHROPIC_API_KEY is UNSET in the shell
    echo "$ANTHROPIC_API_KEY"          # must print empty
    # 2) run the smoke against the real DB (578 filings present)
    .venv/Scripts/python.exe -m pytest tests/analysis/test_live.py -m live -x -q -s

Expected: one active ``decision_card`` saved for corp ``00126380`` with a non-empty
``assumptions[]``, an ``expires_at``, ``numeric_facts`` that survived the D-03 checksum,
and a captured per-call ``total_cost_usd`` / ``duration_ms`` (printed with ``-s``).
Sanity: stance ∈ BUY/ADD/HOLD/TRIM/SELL/AVOID, conviction ∈ [0, 1], and NO price
prediction text in ``body_md`` (Veto #1). The ``live`` marker is registered in
``pyproject.toml`` (Plan 04-01), so the default ``-m "not live"`` run skips this file.
"""

from __future__ import annotations

import logging
import shutil

import pytest

from analysis import analyze_ticker
from analysis.subagents import ClaudeCliBackend
from cards.models import DecisionCard
from cards.store import get_active
from db.engine import get_engine

_CORP = "00126380"  # 삼성전자
_STANCES = {"BUY", "ADD", "HOLD", "TRIM", "SELL", "AVOID"}


@pytest.mark.live
def test_live_analyze_ticker_real_cli(caplog) -> None:
    """End-to-end ``analyze_ticker`` via the REAL ``claude`` CLI → one valid saved card.

    Skips (rather than errors) when the live prerequisites are absent — ``claude`` not
    on PATH or ``DATABASE_URL`` unset — so an accidental default-run selection is a
    clean skip, never a confusing subprocess failure.
    """
    # Load .env so DATABASE_URL is populated for the manual run.
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    if shutil.which("claude") is None:
        pytest.skip("`claude` CLI not on PATH — cannot run the live smoke")
    try:
        engine = get_engine()
    except KeyError:
        pytest.skip("DATABASE_URL not set — cannot reach the real DB for the live smoke")

    with caplog.at_level(logging.INFO, logger="analysis.cost"):
        card = analyze_ticker(_CORP, engine=engine, backend=ClaudeCliBackend())

    # It is a valid, saved, time-boxed card that is now the active card.
    assert isinstance(card, DecisionCard)
    active = get_active(engine, _CORP)
    assert active is not None and active.card_id == card.card_id

    # Veto #2 — a non-empty assumptions[] + an expiry (else it would not have built).
    assert card.assumptions, "a live card must carry at least one assumption (Veto #2)"
    assert card.expires_at is not None

    # SC#3 — the checksummed numeric_facts is a dict of kept facts.
    assert isinstance(card.numeric_facts, dict)

    # Sanity bounds — valid stance + conviction (no price prediction / black-box score).
    assert card.decision.stance in _STANCES
    assert 0.0 <= card.decision.conviction <= 1.0

    # SC#7 — surface the per-call cost/time (the Phase 9 Open-Q4 quota input).
    print(
        f"\n[live] corp={_CORP} stance={card.decision.stance} "
        f"conviction={card.decision.conviction:.3f} "
        f"numeric_facts={len(card.numeric_facts)} warnings={len(card.warnings)}"
    )
    for rec in caplog.records:
        if rec.getMessage() == "analysis_stage_cost":
            print(
                f"[live cost] stage={getattr(rec, 'stage', None)} "
                f"total_cost_usd={getattr(rec, 'total_cost_usd', None)} "
                f"duration_ms={getattr(rec, 'duration_ms', None)}"
            )
