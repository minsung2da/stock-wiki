---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: DB-direct redesign
status: ready_to_plan
stopped_at: Phase 3 context gathered
last_updated: "2026-06-01T13:01:06.662Z"
progress:
  total_phases: 9
  completed_phases: 2
  total_plans: 12
  completed_plans: 12
  percent: 22
---

# Project State

## Project Reference

See:

- `.planning/PROJECT.md` (v1.0 framing — to be refreshed in Phase 1)
- `.planning/ROADMAP.md` (v2.0 9-phase roadmap)
- `.planning/research/redesign-2026-05.md` (authoritative architecture criteria + research synthesis)
- `CLAUDE.md` (Hard Vetoes + tech stack + directory layout)

**v2.0 Core Value:** AI는 종목을 찍어주지 않는다. 매일 모은 evidence를 *근거 카드(decision_card)*
로 압축해 사람에게 제시하고, 검증된 paper-trade 실적이 있는 종목만 KIS 자동매매로 보조한다.

**Current focus:** Phase 03 — MCP Tool Surface (Read-Side)

## Current Position

Phase: 03
Plan: Not started (context gathered)
Next: Phase 3 (MCP Tool Surface — Read-Side) — awaiting `/gsd:plan-phase 3`

Progress: [██████████] 100%

## Phase 1 Outcomes (2026-05-29)

- 6 new domain tables: `filings`, `news`, `ohlcv`, `macro_series`, `events`, `collector_runs`
- Legacy `events` → `events_legacy` rename (pre-rename row count = 0, verified)
- Legacy `documents`/`chunks` dormant (Phase 3 may revisit narrative-search layer)
- 5 collectors INSERT directly to Postgres; `writer.py` modules deleted
- `--vault-root` flag eliminated; runtime guard prevents resurrection
- `shared/heartbeat.py` deleted; replaced by dual-sink (`shared/run_log.py` + structured stderr)
- Veto #6 (no numeric embedding) verified at schema layer
- Veto #8 (no DART pre-chunking) verified at 308KB body roundtrip
- Veto #9 (no Markdown vault) enforced via 3 layers: physical deletion + CI rglob fence + runtime guard
- ~150 tests pass across 9 plans; vertical E2E smoke (`collect macro` → 0 .md files) green

Open items (logged in `.planning/phases/01-collector-db-cutover/deferred-items.md`):

- DI-1: `tests/test_migration.py::test_events_jsonb_and_fk` still references pre-rename events shape (out of 01-09 scope)
- DI-2: intermittent flake on `test_collect_dart_writes_collector_runs_row` (couldn't reproduce in final state)

## Milestone Transition (v1.0 → v2.0)

**2026-04-26 ~ 2026-05-29**: LLM-wiki strategy shutdown + DB-direct redesign.

- v1.0 final state: 8/11 phases complete (Phase 1-7 + 07.1 done; Phase 8 in progress at plan 08-07)
- Shutdown commit: `daf3edf` on origin/main
- Archive: `git tag pre-llm-wiki-shutdown` / `git branch archive/llm-wiki-2026-04`
- Research seed: `.planning/research/redesign-2026-05.md`
- v2.0 roadmap published: 2026-05-29

## Performance Metrics

**Velocity:** (v2.0, baseline reset)

- Total plans completed: 3
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 (Collector DB cutover) | 0 | - | - |
| 2 (Decision card schema) | 0 | - | - |
| 3 (MCP tool surface) | 0 | - | - |
| 4 (Analysis runner) | 0 | - | - |
| 5 (Briefing renderer) | 0 | - | - |
| 6 (Paper-trade action) | 0 | - | - |
| 7 (Live trade) | 0 | - | - |
| 8 (Eval harness) | 0 | - | - |
| 9 (Ops hardening) | 0 | - | - |
| 02 | 3 | - | - |

**Recent Trend:** —

*v1.0 velocity history archived; see `git show archive/llm-wiki-2026-04:.planning/STATE.md` if needed.*
| Phase 02-decision-card-schema-storage P01 | 12 min | 3 tasks | 5 files |
| Phase 02-decision-card-schema-storage P02 | 11 min | 3 tasks | 5 files |
| Phase 02-decision-card-schema-storage P03 | 8 min | 2 tasks | 4 files |

## Accumulated Context (v2.0)

### Decisions

v2.0 architecture decisions are locked in `.planning/research/redesign-2026-05.md` (sections 1-7) and
encoded as Hard Vetoes in `CLAUDE.md`. Recent decisions affecting Phase 1+:

- **Postgres is source of truth.** Markdown vault폐기. 사용자 thesis 메모만 `notes/private/`에 잔존.
- **Collectors write directly to typed Postgres tables** (Phase 1). `vault_root` 인자 + `heartbeat`
  stub 제거.

- **MCP 도구는 타입드 코드 API.** `run_sql` escape hatch 금지. (Phase 3)
- **decision_card schema가 분석 출력의 표준.** 만료일·assumptions·contradictions 강제. (Phase 2-4)
- **Auto-trade는 paper-shadow ≥30일 + Gates A-D 통과만.** Default disabled per-ticker. (Phase 6-7)
- **백테스트는 CPCV+embargo만.** Walk-forward 단독 금지. (Phase 8)

v1.0 decisions (~70개 누적, mostly LLM-wiki specific) — historical reference로 archive branch에 보존.
v2.0 redesign 시 lessons learned 중 carry-over는 위 항목 + `CLAUDE.md` 통해 통합됨.

- [Phase 02-decision-card-schema-storage]: decision_cards.body_tsv uses to_tsvector('simple',...) GENERATED STORED; PG17 lacks 'korean' config (Pitfall #1) — SC#6 is an explicit fallback search; Korean morphology stays in the Python mecab-ko/VectorChord-BM25 path
- [Phase 02-decision-card-schema-storage]: DecisionCard declared on the shared entity_models.Base (single Base) — Keeps ORM round-trip parity simple (RESEARCH A3); required widening test_migration_0006 metadata-set assertion to 7 tables
- [Phase 02-decision-card-schema-storage]: DecisionCard SC#5 hard veto enforced by field declarations only (non-Optional expires_at + assumptions min_length=1), no @model_validator — CONTEXT 'leave shape to the type system' + Veto #2; ValidationError fires at the model boundary
- [Phase 02-decision-card-schema-storage]: Added optional invalidation_reason field to DecisionCard (not in §3 YAML) — redesign §4 payload field; Plan 03 invalidate() writes it into payload JSONB so extra='forbid' reconstruct must accept it; adds no DB column (SC#1 untouched)
- [Phase 02-decision-card-schema-storage]: src/cards/store.py: 4 typed SC#4 CRUD helpers (save_card/get_active/walk_supersedes/invalidate), atomic single-txn supersession, jsonb_set invalidation reason in payload (OQ-1, no new column); no run_sql escape hatch (Veto #7) — Phase 3 MCP get_decision_card + Phase 4 analyze_ticker call this storage API; supersession must be atomic, all SQL parameterized, get_active returns full typed DecisionCard so view=payload|both is a serialize-time exclude (Veto #13)
- [Phase 02-decision-card-schema-storage]: Added optional status: str|None=None to DecisionCard (Rule 2) so invalidate/get_active/walk return cards surfacing the DB lifecycle status; merged in at reconstruct, defaults None (SC#3 round-trip unaffected, no new DB column) — Plan 02-03 acceptance criteria require invalidate() to return a card with .status=='invalidated'; status is a DB column not §3 payload, mirrors the existing optional invalidation_reason precedent

### Lessons Carried Over from v1.0

(v1.0 phase 진행 중 학습한 것 중 v2.0에서도 유효한 것)

- **CPython 3.12 + uv** — Python 3.13은 ML deps 안정성 부족
- **Postgres 17 + pgvector 0.8 (`halfvec`) + VectorChord-BM25** — testcontainer parity 위해 마이그
  레이션 안에서 `CREATE EXTENSION` 실행

- **psycopg3 driver** (`postgresql+psycopg://`) — testcontainers URL normalization 픽스처 경계에서
- **`corp_code` (DART 8-digit)가 canonical entity PK** — KRX 6-digit ticker 재활용 위험
- **Alembic `target_metadata=None`** — 손으로 작성한 마이그레이션만, autogenerate X
- **Content-hash dedup** (sha256) — primitive로만, 보안 아님
- **mecab-ko 한국어 tokenizer 전처리** — VectorChord-BM25는 whitespace tokenizer로 동작, 한국어
  복합어는 Python에서 사전 토큰화 필수

- **Half-open temporal interval `[valid_from, valid_to)` + depth<20 recursive CTE 가드** — entity
  history walk

- **dart-fss의 attachment parsing** — Open DART API가 노출 안 하는 항목 (linked-note financials)
  커버

- **CI guard: collectors/는 `anthropic`/`openai` import 금지** — Sonnet은 Claude Code 세션을 통해서만
  접근. (이 가드는 Phase 1 재작성 시 다시 추가 필요 — `tests/test_import_guard.py` 이미 잔존)

### Pending Todos

- `/gsd:plan-phase 1` 실행 → Phase 1 plan 산출
- Phase 1 plan 완성 후 PROJECT.md를 v2.0 framing으로 업데이트
- (선택) `.planning/phases/01-08, 07.1, 10` 디렉토리를 `.planning/archive/v1.0/`로 이동 — 현재 그대로 두고
  ROADMAP의 v1.0 섹션에서 명시적으로 historical reference라 표시

### Blockers/Concerns

- **Phase 1 우선 결정 필요**: Phase 4 (analysis runner)에서 Sonnet sub-agent를 어떻게 spawn할지 —
  Claude Code session 내 Task tool? 별도 Claude Schedule routine? quota 영향 측정 필요. Phase 4 plan 단계에서 확정.

- **KIS API 모의 환경 접근권**: Phase 6 시작 전 모의투자 계정 발급 및 API 키 확보 필요.
- **`notes/private/portfolio.md` schema 미정**: Phase 1에서 entity seed + Phase 6에서 auto_trade_enabled
  토글까지 사용. 한 번에 결정 vs 점진 진화 — Phase 1 plan에서 결정.

### Quick Tasks Completed

v1.0의 7개 quick task는 archive branch에 보존. v2.0 quick task는 새로 누적.

| # | Description | Date | Commit | Status | Directory |
|---|-------------|------|--------|--------|-----------|
| (none yet for v2.0) | | | | | |

## Session Continuity

Last session: 2026-06-01T13:01:06.641Z
Stopped at: Phase 3 context gathered
Resume file: .planning/phases/03-mcp-tool-surface-read-side/03-CONTEXT.md
