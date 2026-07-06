"""src/analysis/runner.py — ``analyze_ticker`` composite orchestrator (SC#1-7).

The phase deliverable: turn one ticker into a single saved, checksummed, time-boxed
``decision_card`` via the D-04 stance gate and (on a full run) the 3-role
Bull/Bear/Judge debate. This module COMPRESSES evidence into a card; it NEVER predicts
a price/return (Veto #1) and NEVER self-certifies its own numbers — every numeric fact
the Judge emits is re-verified against source by the deterministic D-03 checksum
(``checksum.py``), and any unverifiable fact is dropped into ``card.warnings`` (SC#3).

What closes here:

- **SC#1** — ``analyze_ticker`` returns ONE ``DecisionCard`` and saves it via
  ``store.save_card`` with atomic supersession of the prior active card.
- **SC#2** — a FULL run builds the fixed bundle → Bull/Bear run parallel-blind (each
  gets the SAME stdin, neither sees the other) → the Judge synthesizes both.
- **SC#3** — ``checksum_facts`` re-verifies the Judge's numbers; drops go to warnings.
- **SC#4** — card construction enforces Veto #2 (non-Optional ``expires_at`` +
  ``assumptions min_length=1``): an untimed/assumption-less thesis raises at build.
- **SC#5** — an empty ``contradictions[]`` logs a warning (never silently accepted).
- **SC#6** — a same-stance, no-trigger prior takes the lightweight refresh path and the
  sub-agent ``backend`` is NEVER called (the gate + refresh reach no LLM).
- **SC#7** — per-stage cost/time is emitted for the bundle build + each sub-agent call.

D-01 (Max-only Veto): the ONLY path to a model is the injected ``DebateBackend`` →
headless ``claude`` CLI. This module imports NO cloud-LLM SDK (``anthropic`` /
``openai``); ``tests/test_import_guard.py`` enforces that. The default backend is
``ClaudeCliBackend`` but the whole test suite injects the ``FakeDebateBackend`` so it
spends ZERO Max quota; one opt-in ``@pytest.mark.live`` smoke proves the real path.

Conviction/stance are deterministic, decomposable transforms (Veto #4): the Judge
scores the rubric axes, then ``rubric.score_to_conviction`` maps them to conviction
(with the Veto #5 multi-source cap) and ``rubric.derive_stance`` maps the debate
strengths + rubric signs + holding to one of the six stances (RESEARCH Discretion #1).
The Judge does NOT self-score conviction — its schema omits it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from cards.models import Decision, DecisionCard
from cards.store import get_active, save_card
from db.engine import get_engine
from db.entity import resolve_entity

from . import gate
from .bundle import build_bundle
from .checksum import checksum_facts
from .cost import StageCost, emit_cost
from .roles import prompt_for, schema_for
from .rubric import RUBRIC_WEIGHTS, derive_stance, score_to_conviction
from .subagents import ClaudeCliBackend, RoleResult, run_bull_bear

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from .bundle import EvidenceBundle
    from .subagents import DebateBackend

__all__ = ["analyze_ticker"]

_log = logging.getLogger(__name__)
_KST = ZoneInfo("Asia/Seoul")

# The ``-p`` instruction shared by all three roles; each role's behavior is shaped by
# its ``--append-system-prompt`` (``roles.prompt_for``), not this line. Evidence rides
# stdin (T-04-13); this only tells the sub-agent WHERE the evidence is and to emit the
# schema object only.
_DEBATE_INSTRUCTION = (
    "Read the evidence bundle provided on stdin and produce ONLY the single JSON "
    "object your role's schema requires. The evidence bundle is the sole source of "
    "truth — cite it; never invent facts or predict a price."
)

# The rubric axis centre (0-10 scale): a subscore above the centre is a positive sign
# for ``derive_stance``, below is negative.
_AXIS_CENTRE = 5.0

# Map an evidence_ref prefix (``dart:`` / ``news:`` / ...) to the corroborating source
# family ``rubric.score_to_conviction`` recognises (Veto #5). Sentiment is deliberately
# absent — it can never corroborate a thesis to >=0.8 on its own.
_FAMILY_BY_PREFIX: dict[str, str] = {
    "dart": "DART",
    "news": "news",
    "macro": "macro",
    "note": "user_thesis",
    "user_thesis": "user_thesis",
    "krx": "KRX",
    "ohlcv": "KRX",
    "flow": "KRX",
}


def analyze_ticker(
    corp_code: str,
    as_of: datetime | None = None,
    *,
    engine: Engine | None = None,
    backend: DebateBackend | None = None,
    timeout_s: float = 180.0,
) -> DecisionCard:
    """Analyze one ticker into a single saved ``DecisionCard`` (SC#1-7).

    Composes the Wave-1/2 leaves: ``gate`` → (3-role debate | lightweight refresh) →
    D-03 ``checksum`` → ``rubric`` → ``store``. Same ``(corp_code, as_of)`` on the same
    DB with the same backend ⇒ the same card (the Phase-8 CPCV anchor).

    Args:
        corp_code: the 8-digit DART corp code to analyze.
        as_of: the data cutoff (KST close). ``None`` derives the most recent KST
            trading-day close <= now (Discretion #9); Phase 8 pins a historical value
            for determinism.
        engine: SQLAlchemy engine; defaults to ``db.engine.get_engine()``.
        backend: the injected ``DebateBackend`` (the ONLY path to a model, D-01);
            defaults to ``ClaudeCliBackend()``. The whole test suite injects a fake.
        timeout_s: per-sub-agent wall-clock timeout passed through to the backend.

    Returns:
        The saved active ``DecisionCard`` (superseding any prior active card).

    Raises:
        ValueError: ``corp_code`` does not resolve, or the entity has no current ticker.
        ValidationError: the Judge output cannot be assembled into a valid card even
            after one retry (fail loudly — Discretion #2).
    """
    engine = engine if engine is not None else get_engine()
    backend = backend if backend is not None else ClaudeCliBackend()

    as_of_dt = as_of if as_of is not None else _default_as_of()
    if as_of_dt.tzinfo is None:
        as_of_dt = as_of_dt.replace(tzinfo=_KST)

    entity = resolve_entity(engine, corp_code)
    if entity is None:
        raise ValueError(f"analyze_ticker: unknown corp_code {corp_code!r}")
    if entity.current_ticker is None:
        raise ValueError(
            f"analyze_ticker: entity {corp_code!r} has no current ticker (cannot build a card)"
        )
    ticker = entity.current_ticker

    prior = get_active(engine, corp_code)
    decision = gate.decide(engine, prior, as_of_dt)

    # --- REFRESH path (SC#6): cheap re-validate, the backend is NEVER touched -------
    if not decision.is_full:
        assert prior is not None  # decide() returns FULL(first_run) when prior is None
        refreshed = gate.lightweight_refresh(engine, prior, as_of_dt)
        if isinstance(refreshed, DecisionCard):
            _maybe_warn_no_contradictions(refreshed)
            save_card(engine, refreshed, supersedes=prior.card_id)
            return refreshed
        # Escalate sentinel — a material shift surfaced; fall through to the FULL debate.
        _log.info(
            "gate refresh escalated to full debate",
            extra={"corp_code": corp_code, "reasons": list(refreshed.reasons)},
        )

    # --- FULL path (SC#2): fixed bundle → parallel-blind Bull/Bear → Judge ----------
    # Phase 6 wires portfolio membership (only-if-held); until then no thesis note is
    # attached and the ticker is treated as not-held for the stance table.
    portfolio_note_path: str | None = None
    currently_held = portfolio_note_path is not None

    t0 = time.perf_counter()
    bundle = build_bundle(
        engine, corp_code, as_of_dt.date().isoformat(), portfolio_note_path=portfolio_note_path
    )
    bundle_stdin = bundle.to_stdin()
    emit_cost(StageCost(role="bundle", duration_ms=int((time.perf_counter() - t0) * 1000)))
    source_bodies = _source_bodies(bundle)

    bull, bear, judge = _run_debate(backend, bundle_stdin, timeout_s)
    for role_result in (bull, bear, judge):
        emit_cost(StageCost(**role_result.cost))

    generated_at = datetime.now(_KST)
    try:
        card = _assemble_card(
            corp_code=corp_code,
            ticker=ticker,
            as_of=as_of_dt,
            generated_at=generated_at,
            judge=judge,
            bull=bull,
            bear=bear,
            source_bodies=source_bodies,
            currently_held=currently_held,
        )
    except ValidationError:
        # Constrained decoding guarantees SHAPE, not SEMANTICS — retry the Judge ONCE,
        # then fail loudly (Discretion #2). Bull/Bear are unchanged.
        _log.warning(
            "judge structured_output failed card re-validation — retrying judge once",
            extra={"corp_code": corp_code},
        )
        judge = _rerun_judge(backend, bundle_stdin, bull, bear, timeout_s)
        emit_cost(StageCost(**judge.cost))
        card = _assemble_card(
            corp_code=corp_code,
            ticker=ticker,
            as_of=as_of_dt,
            generated_at=generated_at,
            judge=judge,
            bull=bull,
            bear=bear,
            source_bodies=source_bodies,
            currently_held=currently_held,
        )

    _maybe_warn_no_contradictions(card)
    save_card(engine, card, supersedes=prior.card_id if prior else None)
    return card


# ===========================================================================
# Debate orchestration (the only async region — the model path).
# ===========================================================================
def _run_debate(
    backend: DebateBackend, bundle_stdin: str, timeout_s: float
) -> tuple[RoleResult, RoleResult, RoleResult]:
    """Run Bull+Bear (parallel-blind) then the Judge; return the three role results."""
    return asyncio.run(_debate_async(backend, bundle_stdin, timeout_s))


async def _debate_async(
    backend: DebateBackend, bundle_stdin: str, timeout_s: float
) -> tuple[RoleResult, RoleResult, RoleResult]:
    """SC#2: Bull+Bear over the IDENTICAL bundle (blind), then Judge over bundle+both."""
    bull, bear = await run_bull_bear(
        backend,
        instruction=_DEBATE_INSTRUCTION,
        bundle_stdin=bundle_stdin,
        prompts={"bull": prompt_for("bull"), "bear": prompt_for("bear")},
        schemas={"bull": schema_for("bull"), "bear": schema_for("bear")},
        timeout_s=timeout_s,
    )
    judge = await backend.run(
        "judge",
        _DEBATE_INSTRUCTION,
        prompt_for("judge"),
        schema_for("judge"),
        bundle_stdin + _debate_appendix(bull, bear),
        timeout_s=timeout_s,
    )
    return bull, bear, judge


def _rerun_judge(
    backend: DebateBackend,
    bundle_stdin: str,
    bull: RoleResult,
    bear: RoleResult,
    timeout_s: float,
) -> RoleResult:
    """Re-run ONLY the Judge over the same bundle + the same Bull/Bear outputs."""
    return asyncio.run(
        backend.run(
            "judge",
            _DEBATE_INSTRUCTION,
            prompt_for("judge"),
            schema_for("judge"),
            bundle_stdin + _debate_appendix(bull, bear),
            timeout_s=timeout_s,
        )
    )


def _debate_appendix(bull: RoleResult, bear: RoleResult) -> str:
    """The Bull + Bear outputs appended to the Judge's stdin (SC#2c — Judge sees both).

    Bull/Bear never receive this appendix (they are blind to each other); only the
    Judge's stdin is ``bundle + this``.
    """
    return (
        "\n\n## BULL OUTPUT\n"
        + json.dumps(bull.data, ensure_ascii=False, indent=2)
        + "\n\n## BEAR OUTPUT\n"
        + json.dumps(bear.data, ensure_ascii=False, indent=2)
        + "\n"
    )


# ===========================================================================
# Card assembly — Judge output → checksummed, time-boxed DecisionCard.
# ===========================================================================
def _assemble_card(
    *,
    corp_code: str,
    ticker: str,
    as_of: datetime,
    generated_at: datetime,
    judge: RoleResult,
    bull: RoleResult,
    bear: RoleResult,
    source_bodies: str,
    currently_held: bool,
) -> DecisionCard:
    """Build the ``DecisionCard`` from the Judge output (may raise ``ValidationError``).

    Order matters: ``Decision`` is built first so an absent/invalid ``horizon_days``
    raises before ``expires_at`` is derived from it; ``DecisionCard`` then enforces
    Veto #2 (non-Optional ``expires_at`` + ``assumptions min_length=1``) — that IS SC#4.
    """
    jdata = judge.data
    jdecision = jdata.get("decision", {})
    rubric = jdata.get("rubric", {})
    key_claims = jdata.get("key_claims", [])

    # Conviction (Veto #4 decomposable + Veto #5 multi-source cap).
    subscores = {axis: _axis_score(rubric, axis) for axis in RUBRIC_WEIGHTS}
    conviction = score_to_conviction(
        subscores, evidence_refs=_conviction_evidence_refs(key_claims)
    )

    # Stance from the deterministic table (RESEARCH Discretion #1): net Bull-Bear
    # strength + fundamentals/catalyst sign + holding. Decomposable, no black box.
    stance = derive_stance(
        _side_strength(bull.data),
        _side_strength(bear.data),
        _axis_score(rubric, "fundamentals") - _AXIS_CENTRE,
        _axis_score(rubric, "catalyst") - _AXIS_CENTRE,
        currently_held=currently_held,
    )

    decision = Decision(
        stance=stance,  # type: ignore[arg-type]  # derive_stance returns a valid member
        conviction=conviction,
        horizon_days=jdecision.get("horizon_days"),  # None → ValidationError (SC#4 arm)
        price_ref=jdecision.get("price_ref"),
        invalidation_triggers=jdecision.get("invalidation_triggers", []),
    )
    expires_at = as_of + timedelta(days=decision.horizon_days)

    # SC#3: re-verify every numeric fact against source; drop unverifiable → warnings.
    kept_facts, warnings = checksum_facts(jdata.get("numeric_facts", []), source_bodies)

    return DecisionCard(
        card_id=_new_card_id(ticker, as_of),
        corp_code=corp_code,
        ticker=ticker,
        generated_at=generated_at,
        as_of=as_of,
        decision=decision,
        key_claims=key_claims,
        contradictions=jdata.get("contradictions", []),
        assumptions=jdata.get("assumptions", []),  # empty → ValidationError (SC#4 / Veto #2)
        numeric_facts=kept_facts,
        evidence_weights=jdata.get("evidence_weights", {}),
        guards_passed=[],  # Phase-4 fills the FIELD only; actual gate eval is Phase 6
        expires_at=expires_at,  # non-Optional → SC#4 / Veto #2
        body_md=jdata.get("body_md", ""),
        warnings=warnings,
    )


def _maybe_warn_no_contradictions(card: DecisionCard) -> None:
    """SC#5: an empty ``contradictions[]`` is suspect — log it (never silently accept)."""
    if not card.contradictions:
        _log.warning(
            "card has no contradictions — suspect",
            extra={"corp_code": card.corp_code, "card_id": card.card_id},
        )


# ===========================================================================
# Pure helpers.
# ===========================================================================
def _default_as_of() -> datetime:
    """The most recent KST trading-day close (16:00 KST) <= now (Discretion #9).

    Steps back to the prior weekday when now is before today's close or lands on a
    weekend. Holiday-aware calendars are out of scope — callers pin ``as_of`` for
    determinism (Phase 8); this default only serves the live daily routine.
    """
    now = datetime.now(_KST)
    close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    if now < close:
        close -= timedelta(days=1)
    while close.weekday() >= 5:  # Saturday=5, Sunday=6
        close -= timedelta(days=1)
    return close


def _new_card_id(ticker: str, as_of: datetime) -> str:
    """A fresh, collision-free card id for this run."""
    return f"card_{ticker}_{as_of.date().isoformat()}_{uuid.uuid4().hex[:8]}"


def _source_bodies(bundle: EvidenceBundle) -> str:
    """All narrative source bodies from the bundle, concatenated for the D-03 checksum.

    The ``<untrusted>`` wrapper only adds delimiter lines (inner bytes unchanged), so
    scanning the concatenation for numeric candidates is safe (Veto #8 whole body).
    """
    parts: list[str] = []
    if bundle.portfolio_note is not None:
        parts.append(bundle.portfolio_note.content_md)
    parts.extend(f.body_md for f in bundle.filings)
    parts.extend(nb.body for nb in bundle.hybrid_bodies)
    return "\n".join(parts)


def _side_strength(role_data: dict) -> float:
    """A side's debate strength = the mean confidence of its claims (0.0 if none).

    A decomposable proxy (Veto #4): the stance derives from the two sides' claim
    confidences, not a black-box score. ``[ASSUMED]`` — Phase 8 may tune the reducer.
    """
    claims = role_data.get("claims", [])
    confidences = [
        float(c.get("confidence", 0.0)) for c in claims if isinstance(c, dict)
    ]
    return sum(confidences) / len(confidences) if confidences else 0.0


def _axis_score(rubric: dict, axis: str) -> float:
    """The Judge's 0-10 subscore for one rubric axis (0.0 if absent/malformed)."""
    entry = rubric.get(axis)
    if isinstance(entry, dict):
        try:
            return float(entry.get("score", 0.0))
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _conviction_evidence_refs(key_claims: list[dict]) -> list[dict]:
    """Project the Judge's key_claims to the ``[{weight, family}]`` the Veto #5 cap reads.

    Each claim's ``weight`` is paired with the corroborating family of each of its
    evidence refs (``dart:`` → DART, ``news:`` → news, ...). Unknown-prefix refs map to
    an empty family so they never count toward corroboration.
    """
    refs: list[dict] = []
    for claim in key_claims:
        if not isinstance(claim, dict):
            continue
        weight = claim.get("weight")
        for ref in claim.get("evidence_refs", []):
            refs.append({"weight": weight, "family": _ref_family(str(ref))})
    return refs


def _ref_family(ref: str) -> str:
    """The corroborating source family for an evidence ref (``""`` if unrecognized)."""
    prefix = ref.split(":", 1)[0].lower() if ":" in ref else ref.lower()
    return _FAMILY_BY_PREFIX.get(prefix, "")
