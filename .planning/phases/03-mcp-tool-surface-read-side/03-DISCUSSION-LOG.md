# Phase 3: MCP Tool Surface (Read-Side) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-01
**Phase:** 03-mcp-tool-surface-read-side
**Areas discussed:** Tool error/empty semantics, hybrid_search return shape, Prompt-injection defense, Default result limits

**Note:** Before discussion, resolved a planning-integrity issue — the phase was being
mis-identified as the v1.0 archived name `one-company-walking-skeleton` (an untracked orphan
directory holding only a stray `probe-findings.md` test log). User approved cleanup; orphan
removed, phase re-resolved from ROADMAP as `mcp-tool-surface-read-side`.

---

## Tool error / empty-result semantics (Veto #7: fail loud)

| Option | Description | Selected |
|--------|-------------|----------|
| Empty=normal empty model, failure=typed exception | No-data → empty list/None in a valid Pydantic model; genuine failure → raise McpToolError (FastMCP → MCP error) | ✓ |
| Envelope on every response | All tools return {status, data, message} envelope | |
| Empty/error both None | Simplest, but silent-failure risk (Veto #7 violation) | |

**User's choice:** 빈결과=정상 빈 모델, 실패=예외 (recommended)
**Notes:** Distinguishes "no data" (normal) from "error" (loud) at the code level — direct Veto #7 alignment.

---

## hybrid_search return shape (references vs blobs)

| Option | Description | Selected |
|--------|-------------|----------|
| References + snippet only | ID + RRF score + short snippet; full body fetched via get_filing/get_note | ✓ |
| Snippet default + include_body option | Snippet by default, full body opt-in | |
| Full body included | body_md per match — heavy token cost | |

**User's choice:** 참조+스니펫만 (recommended)
**Notes:** Per redesign §2 "return references, not blobs" (98.7% token reduction). Search = candidate selection; full dump is a separate post-selection step.

---

## Prompt-injection defense posture (SC#5)

| Option | Description | Selected |
|--------|-------------|----------|
| Always XML-wrap + flag-on-match, pass through | Wrap all narrative bodies; on prefilter match, add warning flag in metadata but do NOT block | ✓ |
| Block | Exclude flagged bodies from LLM pipeline (safest, but false-negative risk drops legit filings) | |
| Sanitize | Strip suspicious patterns (corrupts source; conflicts with numeric verbatim checksum) | |

**User's choice:** 항상 XML 래핑 + 플래그 후 통과 (recommended)
**Notes:** Applies to narrative-returning tools (get_filing, get_note, hybrid_search snippets). Avoids losing legitimate DART filings/news to a naive filter; preserves source for checksum.

---

## Default result limits / range caps

| Option | Description | Selected |
|--------|-------------|----------|
| Sensible defaults + explicit limit args | Caller specifies from/to (ohlcv/flow); search_filings default 50; hybrid_search default top-10; explicit limit args | ✓ |
| Strict hard caps | ohlcv ≤365d, search ≤100, hybrid top-20 | |
| No caps (caller responsibility) | Unlimited; token-blowup risk | |

**User's choice:** 합리적 기본값 + 명시 limit 인자 (recommended)
**Notes:** Balance token-budget protection with flexibility; principle is "caller specifies range," defaults protect.

---

## Claude's Discretion

Delegated to planner/research (no user preference): module structure of `src/mcp_v2/`, snippet
length, prefilter pattern set + XML delimiter format, RRF k=60 implementation, `.mcp.json`
registration mechanics, per-tool Pydantic model definitions, peer_view median computation,
get_decision_card↔store.get_active wrapping, and get_briefing implementation timing (Phase 5 dep).

## Deferred Ideas

- `get_briefing` full wiring (depends on Phase 5 briefing rows / report_type column)
- decision_cards semantic search (body_embedding) — Phase 4+ if needed
- Write-side MCP tools — out of scope; Phase 4 calls src/cards/store directly
- Action/order tools (KIS) — Phase 6+
