# Phase 5: Briefing Renderer - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-13
**Phase:** 5-Briefing Renderer
**Areas discussed:** Prioritization ranking, Change detection baseline, '제안' column semantics, Weekly roll-up

---

## Prioritization / top-10 ranking

| Option | Description | Selected |
|--------|-------------|----------|
| Event-class first | stance flip > new contradiction > expired/invalidated > new high-conviction, conviction as tiebreak | ✓ |
| Conviction desc | pure conviction order (conflates "strong" with "changed") | |
| Change magnitude | biggest Δ (needs magnitude metric + settled diff baseline) | |

**User's choice:** Was unsure ("어떤 기준인지 잘 모르겠어") → Claude gave a trade-off analysis; user confirmed the **event-class** recommendation.

| Held vs watchlist | Description | Selected |
|--------|-------------|----------|
| Held always first | held-ticker changes rank above watchlist | ✓ |
| Equal treatment | no held/watch distinction | |
| Held daily, watch weekly | daily = held only, watch only in weekly | |

**User's choice:** Held always first.
**Notes:** Final sort = held-first → event-class → conviction desc.

---

## Change detection (baseline + first card)

| Option | Description | Selected |
|--------|-------------|----------|
| Prior active card diff | supersession chain (`walk_supersedes`); current vs superseded predecessor | ✓ |
| Yesterday's briefing snapshot | diff vs prior briefing row (circular — card chain already holds state) | |
| Fixed N-day lookback | all cards in last N days = change (noise from unchanged refreshes) | |

**User's choice:** Prior active card diff.

| First card | Description | Selected |
|--------|-------------|----------|
| First high-conviction only | first card counts only if conviction ≥ 0.8 (per SC#1 "new high-conviction") | ✓ |
| All first cards | novelty itself is news | |
| Exclude first cards | no predecessor to diff → not a change | |

**User's choice:** First high-conviction only.

---

## '제안' column semantics (Veto #1)

| Option | Description | Selected |
|--------|-------------|----------|
| stance label + conviction | evidence-derived, rubric-decomposable, no forecast | ✓ |
| stance + action nuance | freeform "관망/비중조절" — risk of drifting into prediction | |
| Evidence only (drop 제안) | no suggestion column (but SC#3 locks the column) | |

**User's choice:** stance label + conviction.

| Why now / Why not | Description | Selected |
|--------|-------------|----------|
| key_claims + contradictions auto-extract | Why now = top key_claim, Why not = top contradiction (deterministic, no LLM) | ✓ |
| Summarize Judge body_md | smoother but needs summary logic/LLM | |
| Why now = change reason only | gate trigger as Why now | |

**User's choice:** key_claims + contradictions auto-extract.

---

## Weekly roll-up

| Option | Description | Selected |
|--------|-------------|----------|
| Per-ticker NET change | week-start vs week-end state + event count; flip-flops net to zero | ✓ |
| Most-important event per ticker | single peak event by event-class | |
| Full union | all 7 days' changes (per-ticker dump — SC forbids) | |

**User's choice:** Per-ticker NET change.

| Missing dailies | Description | Selected |
|--------|-------------|----------|
| Best-effort on what exists | roll up available dailies, record coverage (e.g. 5/7) | ✓ |
| Require all 7 | skip weekly unless 7 present | |
| Treat missing as "no change" | conflates "not run" with "no change" | |

**User's choice:** Best-effort on what exists.

---

## Claude's Discretion

- No-change threshold + whether an empty day still writes a short `report_type` row (SC#6) — deferred to planning (recommended: DO write a short row so `get_briefing` returns a positive "no significant changes today" card).
- `report_type` migration shape, payload schema, priority-tiebreak edge cases — planner/researcher territory.

## Deferred Ideas

- Briefing scheduling / cron trigger — Phase 9 ops.
- Any action/order off a briefing — Phase 6.
- No scope creep raised — discussion stayed within the digest domain.
