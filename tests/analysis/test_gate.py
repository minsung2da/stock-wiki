"""SC#6 / D-04 stance-change gate tests (Plan 04-04).

Locks the deterministic, NO-LLM gate behavior the runner depends on:

- each trigger drives a FULL debate (first run, new filing, ≥7% close-to-close move,
  near-expiry ≤7d, safety-net N elapsed);
- the no-trigger steady state returns REFRESH;
- ``lightweight_refresh`` keeps ``expires_at`` unchanged, preserves ``generated_at``,
  and returns a card that still validates through ``DecisionCard`` (Veto #2);
- a material shift (broken HIGH-weight assumption / new mid-refresh filing) yields the
  ``Escalate`` sentinel, not a refreshed card;
- the gate module imports NOTHING from ``analysis.subagents`` / ``analysis.runner`` and
  the REFRESH path spawns no sub-agent backend (SC#6 "skip the debate").

Fixtures are local to this file (the shared ``seeded_engine`` from the package
conftest is reused, not edited). The typed tools reach the same test DB via their own
``get_engine()`` (``DATABASE_URL`` set by ``pg_engine``), so seeding is sufficient —
no ``get_engine`` monkeypatch, mirroring ``tests/analysis/test_bundle.py``.
"""

from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import text

from analysis import gate
from analysis.gate import Escalate, decide, lightweight_refresh
from cards.models import Decision, DecisionCard, KeyClaim

_KST = ZoneInfo("Asia/Seoul")

# The two filings seeded by ``seeded_engine`` (conftest): newest 2026-05-20, then
# 2026-04-15 — both for corp 00126380 / ticker 005930.
_SEEDED_FILING = "dart:20260520000001"


def _dt(y: int, m: int, d: int, hh: int = 16) -> datetime:
    """A KST-close datetime (cards round-trip with +09:00)."""
    return datetime(y, m, d, hh, 0, tzinfo=_KST)


def _card(
    *,
    as_of: datetime,
    generated_at: datetime,
    expires_at: datetime,
    evidence: str = _SEEDED_FILING,
    weight: str = "HIGH",
    card_id: str = "card_005930_base",
) -> DecisionCard:
    """A valid prior DecisionCard for 삼성전자, evidence resolving by default."""
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
                weight=weight,  # type: ignore[arg-type]
                confidence=0.6,
            )
        ],
        assumptions=["DRAM contract ASP holds"],
        expires_at=expires_at,
        body_md="# 삼성전자 (005930) — HOLD\n",
    )


def _seed_ohlcv(engine, rows: list[tuple[str, float, int]]) -> None:
    """Insert (trade_date, close, volume) OHLCV bars for 005930 (open=high=low=close)."""
    with engine.begin() as conn:
        for trade_date, close, vol in rows:
            conn.execute(
                text(
                    "INSERT INTO ohlcv "
                    "(ticker, trade_date, open, high, low, close, volume, fetched_at) "
                    "VALUES ('005930', :d, :c, :c, :c, :c, :v, now())"
                ),
                {"d": trade_date, "c": close, "v": vol},
            )


# --------------------------------------------------------------------------- #
# decide() — each trigger forces FULL
# --------------------------------------------------------------------------- #
def test_first_run_forces_full(seeded_engine) -> None:
    """No prior active card → FULL (first run)."""
    result = decide(seeded_engine, None, _dt(2026, 6, 10))
    assert result.is_full
    assert any("first_run" in r for r in result.reasons)


def test_new_filing_forces_full(seeded_engine) -> None:
    """A filing filed since prior.as_of → FULL with a reason naming the filing trigger."""
    prior = _card(
        as_of=_dt(2026, 5, 1),  # BEFORE the 2026-05-20 seeded filing
        generated_at=_dt(2026, 5, 1),
        expires_at=_dt(2026, 7, 25),  # far → no near-expiry
        evidence="dart:20260415000002",  # resolves (filed 2026-04-15)
    )
    result = decide(seeded_engine, prior, _dt(2026, 5, 25))
    assert result.is_full
    assert any("new_filing" in r for r in result.reasons)


def test_price_spike_forces_full(seeded_engine) -> None:
    """A ≥7% close-to-close move in the window → FULL (price spike)."""
    # +10% jump on 2026-06-03, both bars after prior.as_of (2026-06-01).
    _seed_ohlcv(seeded_engine, [("2026-06-02", 100.0, 1000), ("2026-06-03", 110.0, 1000)])
    prior = _card(
        as_of=_dt(2026, 6, 1),  # after both seeded filings → no new-filing trigger
        generated_at=_dt(2026, 6, 1),
        expires_at=_dt(2026, 8, 1),
    )
    result = decide(seeded_engine, prior, _dt(2026, 6, 10))
    assert result.is_full
    assert any("price_spike" in r for r in result.reasons)


def test_near_expiry_forces_full(seeded_engine) -> None:
    """prior.expires_at within 7 days of as_of → FULL (near-expiry)."""
    prior = _card(
        as_of=_dt(2026, 6, 1),
        generated_at=_dt(2026, 6, 1),
        expires_at=_dt(2026, 6, 15),  # 5 days from as_of 2026-06-10 → ≤7d
    )
    result = decide(seeded_engine, prior, _dt(2026, 6, 10))
    assert result.is_full
    assert any("near_expiry" in r for r in result.reasons)


def test_safety_net_forces_full(seeded_engine) -> None:
    """N days elapsed since the last full generation → FULL even absent other triggers."""
    prior = _card(
        as_of=_dt(2026, 5, 21),  # after both filings → no new filing
        generated_at=_dt(2026, 5, 21),
        expires_at=_dt(2026, 7, 21),  # far → no near-expiry
    )
    result = decide(seeded_engine, prior, _dt(2026, 6, 5))  # 15 days ≥ N=14
    assert result.is_full
    assert any("safety_net" in r for r in result.reasons)
    # Isolated: safety-net is the ONLY trigger (no filing/price/expiry).
    assert all("safety_net" in r for r in result.reasons)


def test_no_trigger_returns_refresh(seeded_engine) -> None:
    """No trigger, stance fresh, within safety net → REFRESH (steady state)."""
    prior = _card(
        as_of=_dt(2026, 5, 21),  # after both filings
        generated_at=_dt(2026, 5, 21),
        expires_at=_dt(2026, 7, 21),  # far
    )
    result = decide(seeded_engine, prior, _dt(2026, 5, 28))  # 7 days < N=14
    assert not result.is_full
    assert result.action == gate.REFRESH
    assert result.reasons == ()


# --------------------------------------------------------------------------- #
# lightweight_refresh() — cheap re-validate, never extends expiry, escalates
# --------------------------------------------------------------------------- #
def test_refresh_keeps_expiry_and_returns_valid_card(seeded_engine) -> None:
    """Refresh returns a valid DecisionCard with new as_of/card_id, expiry unchanged."""
    prior = _card(
        as_of=_dt(2026, 5, 21),
        generated_at=_dt(2026, 5, 21),
        expires_at=_dt(2026, 7, 21),
    )
    refreshed = lightweight_refresh(seeded_engine, prior, _dt(2026, 5, 28))
    assert isinstance(refreshed, DecisionCard)
    assert refreshed.expires_at == prior.expires_at  # never extended (T-04-10)
    assert refreshed.generated_at == prior.generated_at  # safety-net clock preserved
    assert refreshed.as_of == _dt(2026, 5, 28)  # bumped
    assert refreshed.card_id != prior.card_id  # fresh id
    assert refreshed.assumptions  # Veto #2: non-empty
    assert refreshed.status is None  # freshly built, not yet persisted


def test_refresh_does_not_extend_expiry_even_when_as_of_advances(seeded_engine) -> None:
    """A far-forward as_of still leaves expires_at exactly at the prior value."""
    prior = _card(
        as_of=_dt(2026, 5, 21),
        generated_at=_dt(2026, 5, 21),
        expires_at=_dt(2026, 7, 21),
    )
    refreshed = lightweight_refresh(seeded_engine, prior, _dt(2026, 6, 30))
    assert isinstance(refreshed, DecisionCard)
    assert refreshed.expires_at == prior.expires_at  # NOT extended toward the new as_of


def test_refresh_escalates_on_broken_high_weight_assumption(seeded_engine) -> None:
    """A HIGH-weight claim whose evidence no longer resolves → Escalate (not a card)."""
    prior = _card(
        as_of=_dt(2026, 5, 21),  # after both filings → no new-filing escalation
        generated_at=_dt(2026, 5, 21),
        expires_at=_dt(2026, 7, 21),
        evidence="dart:99999999999999",  # 14 digits, absent → FilingNotFound
        weight="HIGH",
    )
    result = lightweight_refresh(seeded_engine, prior, _dt(2026, 5, 28))
    assert isinstance(result, Escalate)
    assert any("lost evidence" in r or "escalate" in r for r in result.reasons)


def test_refresh_escalates_on_new_mid_refresh_filing(seeded_engine) -> None:
    """A filing that surfaced since prior.as_of during refresh → Escalate."""
    prior = _card(
        as_of=_dt(2026, 5, 1),  # BEFORE the 2026-05-20 filing
        generated_at=_dt(2026, 5, 1),
        expires_at=_dt(2026, 7, 21),
        evidence="dart:20260415000002",  # resolves
    )
    result = lightweight_refresh(seeded_engine, prior, _dt(2026, 5, 25))
    assert isinstance(result, Escalate)
    assert any("new_filing" in r for r in result.reasons)


# --------------------------------------------------------------------------- #
# SC#6 — the REFRESH path can never reach the LLM
# --------------------------------------------------------------------------- #
def test_gate_imports_no_subagent_or_runner() -> None:
    """gate.py imports NOTHING from analysis.subagents / analysis.runner (assertable).

    AST-parse the module's import statements (a substring scan would be fooled by the
    docstring, which legitimately names those modules to explain the guarantee).
    """
    tree = ast.parse(Path(gate.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert not any(m.startswith("analysis.subagents") for m in imported)
    assert not any(m.startswith("analysis.runner") for m in imported)
    # No cloud-LLM SDK (D-01) and no subprocess spawn from the gate either.
    assert "anthropic" not in imported
    assert "openai" not in imported
    assert "subprocess" not in imported


def test_refresh_path_spawns_no_subagent_backend(seeded_engine, fake_debate_backend) -> None:
    """decide→REFRESH + lightweight_refresh complete WITHOUT any sub-agent call (SC#6).

    The gate/refresh functions take no backend at all — this hands them a
    ``FakeDebateBackend`` and proves its ``.calls`` stays empty (no role ever ran).

    The *structural* guarantee (gate.py imports neither ``analysis.subagents`` nor
    ``analysis.runner``) is locked durably by
    ``test_gate_imports_no_subagent_or_runner`` above. The previous ``sys.modules``
    proxy here was unreliable: pytest legitimately imports ``analysis.subagents``
    while COLLECTING the sub-agent tests (04-05), so the session-global module set is
    not a valid signal for the gate code path.
    """
    prior = _card(
        as_of=_dt(2026, 5, 21),
        generated_at=_dt(2026, 5, 21),
        expires_at=_dt(2026, 7, 21),
    )
    assert decide(seeded_engine, prior, _dt(2026, 5, 28)).action == gate.REFRESH
    refreshed = lightweight_refresh(seeded_engine, prior, _dt(2026, 5, 28))
    assert isinstance(refreshed, DecisionCard)

    # The cheap path never touches a debate backend — the fake records zero calls.
    assert fake_debate_backend.calls == []
