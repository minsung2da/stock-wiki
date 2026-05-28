---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: DB-direct redesign
status: planning
stopped_at: ROADMAP v2.0 published; ready for /gsd:plan-phase 1
last_updated: "2026-05-29T00:00:00.000Z"
last_activity: 2026-05-29
progress:
  total_phases: 9
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
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

**Current focus:** Phase 1 — Collector DB-Direct Cutover

## Current Position

Phase: 1 (Collector DB-Direct Cutover) — NOT YET PLANNED
Plan: 0 of TBD
Status: Awaiting `/gsd:plan-phase 1`
Last activity: 2026-05-29 (v2.0 ROADMAP + CLAUDE.md published)

Progress: [░░░░░░░░░░] 0%

## Milestone Transition (v1.0 → v2.0)

**2026-04-26 ~ 2026-05-29**: LLM-wiki strategy shutdown + DB-direct redesign.

- v1.0 final state: 8/11 phases complete (Phase 1-7 + 07.1 done; Phase 8 in progress at plan 08-07)
- Shutdown commit: `daf3edf` on origin/main
- Archive: `git tag pre-llm-wiki-shutdown` / `git branch archive/llm-wiki-2026-04`
- Research seed: `.planning/research/redesign-2026-05.md`
- v2.0 roadmap published: 2026-05-29

## Performance Metrics

**Velocity:** (v2.0, baseline reset)

- Total plans completed: 0
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

**Recent Trend:** —

*v1.0 velocity history archived; see `git show archive/llm-wiki-2026-04:.planning/STATE.md` if needed.*

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

Last session: 2026-05-29 (ROADMAP v2.0 publication)
Stopped at: ROADMAP v2.0 published; ready for `/gsd:plan-phase 1`
Resume file: None
