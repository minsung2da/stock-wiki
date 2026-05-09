---
phase: 08-vault-dashboards-research-memo-templates
plan: 07
subsystem: docs
tags: [docs, vault-layout, gitignore, gap-closure]

# Dependency graph
requires:
  - phase: 08-vault-dashboards-research-memo-templates
    provides: GAP-01 fix (worker.ingest_run notes_root 자동 탐색, commit a72a649)
provides:
  - "CLAUDE.md Directory Layout — vault_root/notes_root 분리 명시 (GAP-01 재발 방지 문서화)"
  - "vault_root vs notes_root 멘탈 모델 섹션 + 4-경로 매트릭스 (notes/private vs vault/notes vs vault/raw vs vault/ingested)"
  - "repo-root ingested/ legacy 디렉토리 git rm + .gitignore 강화 (디렉토리 단위 차단)"
affects: [phase-09, future-collaborators, claude-schedule-agent]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Documentation invariant: CLAUDE.md Directory Layout이 production code 동작과 1:1 일치해야 함 (GAP-06 lesson)"
    - "Whitelist 디렉토리(vault/notes/)는 빈 상태로 git tree에 가시화 — gitignore하면 시스템 의도와 협업자 멘탈 모델이 어긋남"

key-files:
  created:
    - ".planning/phases/08-vault-dashboards-research-memo-templates/08-07-SURVEY.md"
  modified:
    - "CLAUDE.md (Directory Layout 갱신 + vault_root vs notes_root 섹션 신설)"
    - ".gitignore (ingested/_status/ → ingested/ 디렉토리 단위 차단)"
    - "ingested/.keep (deleted)"
    - "ingested/_status/.keep (deleted)"

key-decisions:
  - "vault/notes/ KEEP — 초기 plan 가정(DELETE) 정정. D-09 write-scope WHITELIST_PREFIXES의 절반이고 14+개 테스트 + MCP add_note tool이 의존하는 기능 디렉토리. .gitignore 미추가 (사용자 vault 메모는 git에 살아남아야 함)."
  - "ingested/ (repo-root) DELETE — tracked .keep만 있고 production code 0건 의존. 모든 heartbeat 경로는 vault_root scoped. .gitignore에서 'ingested/_status/' → 'ingested/' (디렉토리 단위)로 강화하여 stray sink 재생성 차단."
  - "CLAUDE.md notes_root 멘탈 모델 — 단순 도식 정정에 그치지 않고 4-경로 매트릭스 + ingest_run 자동 탐색 순서 + GAP-01 함정 경고를 별도 섹션으로 신설. 새로운 협업자/agent의 GAP-01 재발 가능성 차단."

patterns-established:
  - "Verification 가설은 raw evidence(grep/git ls-files) 앞에서 무력화될 수 있다 — SURVEY가 plan 가정을 정정하면 Task 3 action도 같이 수정"

requirements-completed: [DASH-01, DASH-04, NOTE-01]

# Metrics
duration: 25min
completed: 2026-05-09
---

# Phase 8 Plan 07: GAP-06 + GAP-08 Closure Summary

**CLAUDE.md Directory Layout이 vault_root vs notes_root 분리를 명시하도록 갱신 + repo-root legacy `ingested/` 디렉토리(tracked .keep만 잔재) 제거 — 새 협업자/agent가 GAP-01(thesis를 vault/notes/private에 작성하면 영구 미인덱싱)을 재발하지 않도록 문서·gitignore 양쪽 차단**

## Performance

- **Duration:** ~25 min (Task 1 SURVEY 13min + checkpoint pause + Task 3 12min)
- **Started:** 2026-05-09T08:31:00Z (approximate, plan dispatch)
- **Completed:** 2026-05-09T08:56:25Z
- **Tasks:** 3 (Task 1 SURVEY, Task 2 checkpoint:human-verify, Task 3 docs+cleanup)
- **Files modified:** 4 (1 created, 2 modified, 2 deleted)

## Accomplishments

- **GAP-06 closed**: CLAUDE.md Directory Layout 도식이 production 동작과 1:1 일치. 새 협업자가 도식만 봐도 vault_root vs notes_root 분리를 즉시 이해 가능.
- **GAP-08 closed**: tracked legacy `ingested/.keep` + `ingested/_status/.keep` 제거. .gitignore가 디렉토리 단위로 강화되어 repo-root에 stray sink 재생성 차단.
- **GAP-01 재발 방지**: CLAUDE.md에 `vault_root vs notes_root (Phase 8 GAP-01 lesson)` 섹션 신설 — 4-경로 매트릭스, ingest_run 자동 탐색 순서, 명시적 WARNING.
- **Plan 가정 정정**: 초기 plan은 `vault/notes/` DELETE를 가정했으나 SURVEY가 D-09 write-scope 의존성을 발견 → KEEP으로 정정. 회귀 회피.

## Task Commits

1. **Task 1: 디렉토리 잔재 조사 + 사용처 검증 (SURVEY)** — `e8d6066` (docs)
2. **Task 2: human-verify checkpoint** — (commit 없음, 사용자 승인만)
3. **Task 3: CLAUDE.md notes_root 분리 + ingested/ 제거 + .gitignore** — `3d89a23` (docs)

## Files Created/Modified

- `.planning/phases/08-vault-dashboards-research-memo-templates/08-07-SURVEY.md` — 4개 후보 디렉토리(vault/notes/, ingested/, vault/.graphify-staging/, .claude/worktrees/...)별 Tracked/Empty/References/Decision/Action 매트릭스 + raw evidence + Task 2 결정 요청
- `CLAUDE.md` — Directory Layout 도식 갱신 (vault_root 하위에 raw/, ingested/{_status,by-ticker}, graph/, notes/, .graphify-staging/ 명시; repo-root notes/private/ 별도 표시; templates/notes/ 추가). 새 섹션 `### vault_root vs notes_root (Phase 8 GAP-01 lesson)` 추가 (4-경로 매트릭스, 자동 탐색 순서, GAP-01 WARNING, 레이어 규칙 갱신).
- `.gitignore` — `ingested/_status/` → `ingested/` (디렉토리 단위로 강화; 주석으로 GAP-08 lesson 명시)
- `ingested/.keep`, `ingested/_status/.keep` — `git rm` (legacy, history 보존)

## Decisions Made

1. **vault/notes/ KEEP (plan 가정 DELETE → 정정)**: 초기 plan은 vault/notes/를 빈 legacy 디렉토리로 가정했으나, `grep -rn "vault/notes" src/`가 D-09 write-scope `WHITELIST_PREFIXES = ("vault/notes/", "notes/private/")` (`src/stock_mcp/paths.py:28`) + 14+개 add_note 테스트 의존을 보임. 삭제·gitignore 시 (a) 시스템 의도 가시성 손실 + (b) 사용자가 add_note로 쓴 vault 메모가 git에서 invisible해져 협업 시 누락 → KEEP + .gitignore 미추가.

2. **ingested/ (repo-root) git rm (untracked 가정 → tracked 발견)**: `git ls-files ingested/`이 `.keep` 2개를 노출. 단순 `rm -rf`로는 history 손실 — `git rm -r`로 전환. 추가 untracked stale `ingested/_status/heartbeat.md` (2026-04-17 snapshot)도 정리. production heartbeat은 모두 `vault_root / "ingested/_status/heartbeat.md"`로 vault 내부에 씀 → repo-root 디렉토리는 안전 제거.

3. **.gitignore: `ingested/_status/` → `ingested/`**: 디렉토리 단위로 강화. line 51의 기존 패턴은 `ingested/` 자체와 `.keep`을 가리지 못해 모순적인 상태(ignored 하위 + tracked 상위)였음. 디렉토리 단위 차단으로 stray 재생성 시 git이 즉시 무시.

4. **CLAUDE.md notes_root 섹션은 단순 도식 정정 이상**: 4-경로 매트릭스 + ingest_run 자동 탐색 순서 + 명시적 GAP-01 WARNING으로 강화. 새 협업자/Claude Schedule agent가 도식만 봐도 함정 회피.

## Deviations from Plan

**Total deviations:** 2 plan-assumption corrections (auto-applied via SURVEY → checkpoint → user approval)

### Auto-fixed Issues

**1. [Rule 1 - Bug-equivalent] vault/notes/ DELETE → KEEP 정정**
- **Found during:** Task 1 SURVEY (grep code references)
- **Issue:** Plan은 vault/notes/를 빈 legacy 디렉토리로 가정하고 DELETE + .gitignore 추가를 지시했으나, 실제로는 D-09 write-scope WHITELIST의 절반이며 14+개 테스트가 의존. 실행 시 add_note 사용자 메모가 git에서 invisible해지는 회귀 발생.
- **Fix:** SURVEY에서 정정안을 명시 → Task 2 checkpoint에서 사용자 승인 → Task 3는 KEEP + .gitignore 미추가로 진행. CLAUDE.md 도식에 vault/notes/는 "사용자 메모 화이트리스트(D-09)"로 명시.
- **Files modified:** SURVEY.md (정정안), CLAUDE.md (도식 갱신)
- **Verification:** `! grep -E "^vault/notes/" .gitignore` → OK; `grep "WHITELIST_PREFIXES" src/stock_mcp/paths.py` 변경 없음
- **Committed in:** `e8d6066` (SURVEY 정정안), `3d89a23` (Task 3)

**2. [Rule 3 - Blocking] ingested/ rm -rf → git rm -r 전환 + stale heartbeat 정리**
- **Found during:** Task 3 실행
- **Issue:** Plan은 ingested/를 untracked로 가정하고 `rm -rf` 지시. 실제로는 `.keep` 2개가 tracked. 또한 `ingested/_status/heartbeat.md`(2026-04-17 stale untracked)가 살아있어 단순 rmdir 불가.
- **Fix:** `git rm -r ingested/` (tracked .keep history 보존) → 잔여 stale heartbeat.md `rm` → `rmdir _status ingested`. .gitignore line 51을 `ingested/_status/` → `ingested/`로 강화하여 재발 차단.
- **Files modified:** ingested/.keep (deleted), ingested/_status/.keep (deleted), ingested/_status/heartbeat.md (deleted, untracked), .gitignore
- **Verification:** `test ! -d ingested/` → OK
- **Committed in:** `3d89a23`

**Impact on plan:** 두 정정 모두 plan의 의도를 더 정확히 충족. 회귀 회피(Deviation 1) + idempotency 확보(Deviation 2). 범위 확장 없음.

## Issues Encountered

- `git index.lock` 충돌 2회 (concurrent git status에서 발생) — 짧은 sleep 후 재시도로 해결. 작업 자체에는 영향 없음.

## Verification Evidence

```
test ! -d ingested/                          → OK (디렉토리 부재)
grep -c "notes_root" CLAUDE.md               → 6 (충분히 명시됨)
grep "GAP-01 함정" CLAUDE.md                 → OK
! grep "vault/notes/.*사람" CLAUDE.md         → OK (outdated 문구 제거)
grep "^ingested/$" .gitignore                → OK (디렉토리 단위)
! grep "^vault/notes/" .gitignore            → OK (의도적으로 미추가)
import smoke test (ingest.worker, stock_mcp.paths, graph.window 등) → 6 모듈 OK
```

## User Setup Required

None.

## Next Phase Readiness

- **GAP-06, GAP-08 closed** — Phase 8 verifier가 식별한 8개 gap 중 2건 추가 정리. 남은 OPEN gap: GAP-03(event_type literal drift), GAP-04(macro section parser, 이미 commit 7a5755a로 해결 가능성 — 확인 필요), GAP-05(vault_path absolute), GAP-07(verifier 위양성 강화).
- **CLAUDE.md as living document** — 향후 디렉토리 layout 변경 시(예: vault/ingested/ 하위 추가) 본 plan이 만든 4-경로 매트릭스를 함께 갱신해야 함.
- **Phase 9 readiness**: 새 phase agent가 CLAUDE.md를 읽으면 vault_root vs notes_root 분리를 즉시 이해. GAP-01 재발 가능성 0.

## Self-Check: PASSED

- ✅ `.planning/phases/08-vault-dashboards-research-memo-templates/08-07-SURVEY.md` exists (verified by Read)
- ✅ Commit `e8d6066` exists (`git log --oneline -3` 확인)
- ✅ Commit `3d89a23` exists (`git log --oneline -3` 확인)
- ✅ CLAUDE.md modified — `notes_root` 6 hits, `GAP-01 함정` present, vault/notes/ outdated 문구 제거
- ✅ .gitignore modified — `ingested/` 디렉토리 단위 차단
- ✅ ingested/ directory absent (`test ! -d ingested/` PASS)

---
*Phase: 08-vault-dashboards-research-memo-templates*
*Plan: 07 (GAP-06 + GAP-08 closure)*
*Completed: 2026-05-09*
