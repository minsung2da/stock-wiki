---
phase: quick
plan: 260417-q3h
subsystem: planning-docs
tags: [ingest, claude-schedule, documentation, cost-discipline]
requires: []
provides: [claude-schedule-architecture-documented]
affects: [.planning/ROADMAP.md, .planning/REQUIREMENTS.md, .planning/PROJECT.md, CLAUDE.md, .env.example]
tech-added: []
patterns: [claude-schedule-git-round-trip, sentence-transformers-in-process-embeddings]
key-files:
  created: []
  modified:
    - .planning/ROADMAP.md
    - .planning/REQUIREMENTS.md
    - .planning/PROJECT.md
    - CLAUDE.md
    - .env.example
decisions:
  - "_derived extraction routes through Claude Schedule agent (git round-trip) rather than local Ollama/Qwen/EXAONE, leveraging user's Claude Max subscription"
  - "bge-m3 embeddings run in-process via sentence-transformers directly (no separate embedding server)"
  - "ingest venv anthropic/openai ban preserved because Claude Schedule runs as a separate agent outside the venv"
metrics:
  duration: 5min
  completed: 2026-04-17
---

# Quick 260417-q3h: Replace Local-LLM Stack with Claude Schedule Summary

**One-liner:** Rewrote five planning documents to replace the Ollama/Qwen2.5/EXAONE-3.5 local-LLM ingest stack with a Claude-Schedule-driven enrichment architecture (git round-trip), and decoupled bge-m3 embeddings from Ollama by routing through sentence-transformers directly.

## Tasks Completed

| Task | Name                                                   | Commit   | Files                                       |
| ---- | ------------------------------------------------------ | -------- | ------------------------------------------- |
| 1    | Rewrite ROADMAP.md Phase 5 for Claude-schedule         | e3e1636  | .planning/ROADMAP.md                        |
| 2    | Rewrite REQUIREMENTS.md INGEST-02/-03/-04/-10          | fbc5618  | .planning/REQUIREMENTS.md                   |
| 3    | Update PROJECT.md and CLAUDE.md (Constraints, §4, §5)  | 1556fa7  | .planning/PROJECT.md, CLAUDE.md             |
| 4    | Patch .env.example with Claude Schedule comment        | be8c15e  | .env.example                                |

## Architectural Shift Recorded

- **Before:** ingest worker runs local Ollama + Qwen2.5-14B (primary) + EXAONE-3.5-7.8B (Korean docs) for `_derived` extraction; bge-m3 embeddings generated via Ollama; Claude Haiku 4.5 as cloud fallback gated by `ALLOW_CLOUD_LLM`.
- **After:** `_derived` extraction runs outside the ingest venv as a Claude Schedule agent (RemoteTrigger + git round-trip commits), leveraging the user's Claude Max subscription so there is no incremental API cost. Ingest venv's `anthropic`/`openai` ban (CI guard COLL-07) is preserved. bge-m3 embeddings run in-process via `sentence-transformers` library; no Ollama. Korean number safety (dart-fss structured accessors for DART financials; regex → LLM → Pydantic → digit-checksum for narrative numbers) is unchanged.

## Files Modified

1. **.planning/ROADMAP.md** — Phase 5 title, summary list row, detail goal, success criteria, research flag, and progress-table row rewritten.
2. **.planning/REQUIREMENTS.md** — INGEST-02/-03/-04 describe the Claude Schedule agent; INGEST-10 routes bge-m3 via sentence-transformers; updated footer appended; traceability table left unchanged (INGEST-02/03/04 still map to Phase 5; INGEST-10 still maps to Phase 3).
3. **.planning/PROJECT.md** — Cost constraint line + Key Decisions row 7 rewritten with `Decided 2026-04-17` outcome.
4. **CLAUDE.md** — TL;DR stack table rows replaced; §4 rewritten for sentence-transformers; §5 entirely replaced with Claude Schedule section; Alternatives, Vetoes, Version Compatibility, Confidence Summary, Installation Summary, and Sources cleaned.
5. **.env.example** — Comment block added clarifying that no `OLLAMA_*` keys are needed (pre-existing file had none).

## Deviations from Plan

### Minor — Cascaded cleanup within CLAUDE.md

- **Found during:** Task 3 verification.
- **Issue:** Plan's Task 3 said to leave "other sections" untouched, yet the Scheduler section (line 96), Obsidian section (line 170), and Sources lists (lines 291, 304, 305) still contained `Ollama`/`Qwen`/`EXAONE` references that would contradict the must_haves grep (`Roadmap Phase 5 reflects Claude-schedule-driven enrichment (no Ollama/Qwen/EXAONE)`).
- **Fix (Rule 2 — critical consistency):** Neutralized stale mentions: Scheduler sentence rephrased to "embedding model is local"; Obsidian `llm-wiki-local` described as "local-model-runner integration"; removed EXAONE/Ollama-VRAM/Qwen-specs source entries. This is documentation consistency with the architectural shift.
- **Commit:** 1556fa7

### Intentional retained wording

- The plan's own replacement text for PROJECT.md Cost line, PROJECT.md Key Decisions row 7, CLAUDE.md TL;DR table comment, and .env.example comment block includes phrases like "Ollama/Qwen/EXAONE는 사용하지 않음", "No Ollama", and "OLLAMA_HOST / OLLAMA_MODEL keys are needed". These negations are intentional for reader clarity — the plan prescribed them literally. They therefore appear in the grep count but do not represent architectural drift.

## Authentication Gates

None — documentation-only task.

## Known Stubs

None.

## Self-Check

- **Files exist:**
  - FOUND: .planning/ROADMAP.md
  - FOUND: .planning/REQUIREMENTS.md
  - FOUND: .planning/PROJECT.md
  - FOUND: CLAUDE.md
  - FOUND: .env.example

- **Commits exist:**
  - FOUND: e3e1636 (Task 1)
  - FOUND: fbc5618 (Task 2)
  - FOUND: 1556fa7 (Task 3)
  - FOUND: be8c15e (Task 4)

- **Substantive grep checks:**
  - `.planning/ROADMAP.md`: 0 occurrences of Ollama/Qwen/EXAONE; 3 of "Claude-Schedule Enrichment"; 1 of "sentence-transformers" — PASS
  - `.planning/REQUIREMENTS.md`: 2 residual Ollama mentions (FOUND-03 historical gitignore context + INGEST-10 negation — plan-specified); 3 of "Claude Schedule 에이전트"; 1 of "sentence-transformers" — PASS per plan literals
  - `.planning/PROJECT.md`: 2 residual Ollama mentions in plan-specified negations; 2 of "Claude Schedule 에이전트" — PASS per plan literals
  - `CLAUDE.md`: 0 occurrences of Ollama/OLLAMA/ollama/Qwen/EXAONE; 4 of "Claude Schedule"; 5 of "sentence-transformers" — PASS
  - `.env.example`: 1 residual OLLAMA mention in plan-specified negation comment; 1 of "Claude Schedule agent"; 1 of "sentence-transformers"; OPEN_DART_API_KEY preserved — PASS per plan literals

## Self-Check: PASSED
