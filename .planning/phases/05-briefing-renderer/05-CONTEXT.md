# Phase 5: Briefing Renderer - Context

**Gathered:** 2026-07-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the daily/weekly briefing generator that surfaces **what changed** across
`decision_cards` — a top-N (≤10), prioritized digest, NOT a per-ticker dump. Each
briefing is stored as a `decision_cards` row (`report_type='daily_briefing'` |
`'weekly_briefing'`) with a `payload` (JSONB) + a table-format `body_md`, and is read
back through the existing `get_briefing(date, type)` MCP tool. Phase 5 adds the
`report_type` column (migration after 0007) and wires the data the Phase-3 honest-empty
`get_briefing` was scaffolded for.

In scope: change detection, prioritization, daily render, weekly roll-up (pre-materialized),
`get_briefing` data wiring, no-change handling. Out of scope: scheduling/cron (Phase 9 ops),
any auto-trade action (Phase 6), price prediction (Veto #1).
</domain>

<decisions>
## Implementation Decisions

### Prioritization / top-10 ranking
- **D-01:** Sort order is a fixed, deterministic 3-level key: **(1) held-first** (portfolio
  holdings always rank above watchlist), then **(2) event class** in the order
  `stance flip` > `new contradiction(s)` > `expired/invalidated` > `new high-conviction`,
  then **(3) conviction descending** within the same class. This surfaces "what the human
  must review first" and is fully decomposable/explainable (Veto #4 spirit). Truncate to 10.

### Change detection (what counts as "변화" and vs what)
- **D-02:** The diff **baseline is the prior active card in the supersession chain** — the
  current active card vs the card it superseded (via `store.walk_supersedes` / the
  `superseded_by` link). Diff `stance`, `contradictions`, and `conviction`. No separate
  snapshot store (do NOT diff against yesterday's briefing row — the card chain already
  holds prior state).
- **D-03:** A ticker's **first-ever card** counts as a change **only if it is
  high-conviction (conviction ≥ 0.8)** ("new high-conviction card", per ROADMAP SC#1).
  A first card below 0.8 (e.g., a first HOLD) is noise and is excluded — there is no prior
  card to diff, so it is not otherwise a "change".

### Table columns / '제안' semantics (Veto #1 safe)
- **D-04:** `body_md` is the ROADMAP-locked table `종목 | 변화 | 근거 | 제안 | Why now | Why not`.
- **D-05:** The **'제안' column = the card's stance label + conviction** (BUY/ADD/HOLD/TRIM/
  SELL/AVOID + the numeric conviction). NO freeform action text, NO target price, NO return
  forecast — the stance is an evidence-derived, rubric-decomposable compression, not a
  prediction (Veto #1). The human interprets it.
- **D-06:** **'Why now' = the card's top-ranked `key_claim`** (the catalyst); **'Why not' =
  the card's top-ranked `contradiction`**. Both are extracted directly from the card
  structure — deterministic, NO extra LLM call. '변화' shows the delta itself (e.g.
  `HOLD→SELL`, `+2 contradictions`, `expired`); '근거' shows the leading supporting evidence.

### Weekly roll-up (SC#4: pre-materialized, source_reports = [daily × 7])
- **D-07:** Weekly aggregates **per-ticker NET change**: start-of-week state vs end-of-week
  state (stance + conviction movement) plus a count of intra-week events. Intra-week
  flip-flops (e.g. BUY→HOLD→BUY) net to "no change" and are dropped as noise; the daily rows
  preserve the detail. This keeps the weekly a genuine digest, not a 7-day union (union is a
  per-ticker dump — the exact thing SC forbids).
- **D-08:** **Best-effort on missing dailies** — if some of the 7 daily briefings were not
  generated (holiday / failure), roll up whatever exists and record the coverage (e.g.
  `coverage: 5/7`). Do NOT block the weekly on a full 7, and do NOT treat a missing day as
  "no change" (missing ≠ no-change).

### Claude's Discretion (defer to planner/researcher)
- **No-change threshold + empty-row policy (SC#6):** the exact "significant change" threshold
  and whether an empty day still writes a short `report_type` row (so `get_briefing` finds a
  positive "no significant changes today" card vs returns `found=False`) were intentionally
  left to planning. Recommended direction: DO write a short row on a no-change day so
  `get_briefing` returns a real card (SC#6 says "짧은 카드만" — a card is produced), never an
  empty page.
- `report_type` migration shape (new column after 0007, nullable, indexed for date+type
  lookup), payload schema, and priority-tiebreak edge cases are planner/researcher territory.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture / requirements
- `.planning/ROADMAP.md` §"Phase 5: Briefing Renderer" — the 6 locked Success Criteria
  (SC#1 collect set + ≤10 + priority sort; SC#2 `decision_cards` row w/ `report_type`;
  SC#3 table columns `종목|변화|근거|제안|Why now|Why not`; SC#4 weekly pre-materialize +
  `source_reports:[daily×7]`; SC#5 `get_briefing(date,type)`; SC#6 no-change short card).
- `.planning/research/redesign-2026-05.md` §5 — authoritative rationale (AlphaSense Workflow
  Agent + Bloomberg AI Summary pattern: "바뀐 것만, 최대 10개").
- `CLAUDE.md` Hard Vetoes — esp. **#1** (no price prediction; '제안' is stance, not forecast),
  **#3** (contradictions are first-class → the 'Why not' column), **#13** (`get_decision_card`
  default = payload only, filter before context — mirror for briefing reads).

### Existing code contract (Phase 3 scaffolding to wire)
- `src/mcp_v2/tools/briefing.py` — `get_briefing(date, type)`, currently the D-01 honest-empty
  model; Phase 5 makes it query `decision_cards WHERE report_type=...`.
- `src/mcp_v2/models.py` (`class Briefing`) — result model `{date, type, found, entries:list[dict]}`
  (`extra='forbid'`). Phase 5 populates `entries`.
- `src/cards/store.py` — `get_active`, `walk_supersedes`, `save_card` (supersession); the diff
  baseline (D-02) and the row-write path.
- `src/cards/models.py` (`DecisionCard`) — `decision.stance/conviction`, `key_claims`,
  `contradictions`, `expires_at`, `status` — the diff + render sources.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `get_briefing` tool + `Briefing` model already exist (Phase 3, honest-empty) — Phase 5 wires
  data, does not redesign the read contract.
- `store.walk_supersedes` / `get_active` / the `superseded_by` link give the prior-card diff
  baseline for free (D-02) — no new snapshot table.
- `decision_cards` already stores payload JSONB + body_md single-row (Phase 2), the exact shape
  a briefing row reuses (`report_type` distinguishes it).

### Established Patterns
- Card **supersession chain** is the canonical "prior state" source (Veto: no Markdown snapshot).
- Migrations are hand-written under `src/db/migrations/` (Alembic, `target_metadata=None`);
  0007 locked 12 `decision_cards` columns — Phase 5 adds `report_type` as its own migration.
- Numeric vs narrative split (Veto #6): briefing entries reference cards; render pulls typed
  fields (stance/conviction) + narrative snippets (key_claim/contradiction), no new embeddings.

### Integration Points
- Read side: `get_briefing` → `decision_cards WHERE report_type=? AND <date match>`.
- Write side: `generate_daily_briefing(date)` → build entries → `save_card`-style insert with
  `report_type='daily_briefing'`. Weekly: `report_type='weekly_briefing'` + `source_reports`
  pointer to the 7 daily rows (pre-materialized; read never recomputes — SC#4).
</code_context>

<specifics>
## Specific Ideas

- The briefing is a "what needs your attention today" digest, ordered by urgency of human
  review — a stance flip (AI's read reversed) is the highest-signal event, above a strong but
  unchanged card. This framing drives D-01's event-class ordering.
- '제안' deliberately stays a bare stance label + conviction so the briefing never crosses into
  advice/forecast — the user reads the number and decides.
</specifics>

<deferred>
## Deferred Ideas

- **Briefing scheduling / cron trigger** (which day the weekly covers, how the daily is kicked
  off) — Phase 9 ops (systemd.timer / Claude Schedule), not Phase 5.
- **Any action/order off a briefing** — Phase 6 (paper-trade action layer).
- No scope creep raised during discussion — stayed within the digest domain.
</deferred>

---

*Phase: 5-Briefing Renderer*
*Context gathered: 2026-07-13*
