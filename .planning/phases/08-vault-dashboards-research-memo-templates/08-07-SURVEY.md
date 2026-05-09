# GAP-08 Directory Cleanup Survey

> Phase 8 Plan 07 Task 1 산출물. Task 2 checkpoint(human-verify)에서 사용자가 본 SURVEY의
> Decision/Action 컬럼을 검토·승인한 뒤 Task 3가 실행한다.
>
> **중요:** 초기 가설(`vault/notes/` = orphan)은 코드 검색 결과와 어긋남. SURVEY는 raw evidence에 근거해 재정렬됨.

## 후보 디렉토리

| Path | Tracked? | Empty? | Code references | Decision | Action |
|------|----------|--------|-----------------|----------|--------|
| `vault/notes/` | **no** (untracked, .gitignore line 14 `notes/private/` 외 별도 등재 없음) | **yes** (자기 자신만) | **MANY** — `src/stock_mcp/paths.py:28` `WHITELIST_PREFIXES = ("vault/notes/", "notes/private/")`, `src/stock_mcp/tools/notes.py` add_note D-09 write-scope, `src/graph/window.py`, `src/ingest/edges.py:123,183`, 14+ test files (`test_add_note_*`, `test_paths.py`, `test_get_ticker_overview.py`, `test_perf_gates.py`) | **KEEP (gitignore 추가만)** | `mkdir -p vault/notes` 보장하지 않음 (현재 빈 디렉토리 그대로). `.gitignore`에 `vault/notes/`는 **추가하지 않음** — 코드 화이트리스트가 의도적으로 허용하는 경로이므로 함정이 아님. 단, hub builder/CLAUDE.md 도식은 별도 정리(GAP-06 본 plan Task 3에서 다룸) |
| `ingested/` (repo-root) | **YES** (`ingested/.keep`, `ingested/_status/.keep` tracked) | no (.keep 파일 2개 + 빈 `_status/` 하위) | 직접 참조 0건. heartbeat 실제 경로는 모두 `vault_root / "ingested/_status/heartbeat.md"` — vault_root가 repo_root와 같을 때만(tests의 `tmp_path` 패턴) 이 디렉토리에 쓰여짐. **production 환경**(`vault_root=vault/`)에서는 `vault/ingested/_status/`가 정식 경로이므로 repo-root `ingested/`는 legacy. | **DELETE (git rm)** | `git rm -r ingested/` (tracked .keep 파일 2개 보존을 위한 history 유지). `.gitignore` line 51 `ingested/_status/`는 그대로 두되, **그 위에 디렉토리 단위 `ingested/` 추가**하여 repo-root에 우발적으로 재생성되어도 git 무시. |
| `vault/.graphify-staging/` | **no** (gitignored line 40 `vault/.graphify-staging/`) | **yes** | `src/graph/snapshot.py:88` `staging = repo_root / "vault" / ".graphify-staging" / today` (graphify 실행 시 자동 생성하는 임시 dir). 4개 graph 테스트 참조. | **KEEP** | 변경 없음. graphify 실행 시 자동 채워지고 끝나면 비워짐 (현재 빈 상태가 정상). |
| `.claude/worktrees/exciting-mendeleev-476256/` | n/a (claude-internal) | yes | n/a — claude code 도구 워크트리 디렉토리 | **KEEP (out of scope)** | 본 plan 범위 밖. claude-code 도구 관리 영역. |

## 검증 근거 (raw outputs)

### 1. 빈 디렉토리 후보 (`find . -type d -empty`)

```
./vault/.graphify-staging
./vault/notes
./.claude/worktrees/exciting-mendeleev-476256
```

(시스템 디렉토리 `./.git/*`, `./.venv/*`, `*/__pycache__*`, `./.obsidian/*` 제외)

### 2. Git tracking 상태

```
$ git ls-files vault/notes/         → 0 lines (untracked, but gitignored as `notes/private/` only — not `vault/notes/` itself)
$ git ls-files ingested/             → ingested/.keep, ingested/_status/.keep (TRACKED)
$ git ls-files vault/.graphify-staging/  → 0 lines (gitignored)
```

→ `ingested/`만 `git rm` 필요. 나머지는 untracked 또는 gitignored.

### 3. `vault/notes/` 코드 참조 분석

`vault/notes/`는 **legacy 잔재가 아니라 D-09 write-scope 화이트리스트의 절반**:

```
src/stock_mcp/paths.py:28: WHITELIST_PREFIXES = ("vault/notes/", "notes/private/")
src/stock_mcp/tools/notes.py:123: lives inside vault/notes/ or notes/private/ AFTER Path.resolve()
src/graph/window.py:58: for src_rel, key in (("vault/notes", "notes"), ("notes/private", "private")):
src/ingest/edges.py:123: source == "note" or "/vault/notes/" in vault_path or "/notes/private/" in vault_path
```

테스트 14+개 (`test_add_note_paths.py`, `test_add_note_append.py`, `test_paths.py`, `test_get_ticker_overview.py` 등)가 `vault/notes/<file>.md`로 add_note 호출 검증.

**결론:** `vault/notes/` 디렉토리 자체는 시스템이 의도적으로 허용하는 사용자 메모 위치. 빈 상태는 "아직 사용자가 vault 내부에 메모를 안 만든" 정상 상태. **삭제하면 add_note가 부모 디렉토리 자동 생성으로 동작은 하지만, 의도적인 화이트리스트를 git tree에서 가시화할 빈 placeholder가 사라져 GAP-01과 같은 혼선이 재발할 수 있음 → KEEP 권장.**

또한 `.gitignore`에 `vault/notes/`를 넣으면, MCP `add_note`로 사용자가 `vault/notes/foo.md`에 쓴 메모가 git에서 보이지 않게 되어 **공유 vault의 사용자 메모가 영구 누락**됨 — GAP-01보다 더 큰 회귀.

### 4. `ingested/` (repo-root) 분석

```
$ ls -la ingested/
.keep
_status/   (하위에 .keep 만)
```

heartbeat 실제 쓰기 경로: 모든 production code에서 `vault_root / "ingested/_status/heartbeat.md"`.

- production CLI (`stock collect *`): `vault_root=vault/` → `vault/ingested/_status/heartbeat.md` 사용
- tests의 `tmp_path` fixtures: 일부에서 `tmp_path / "ingested/_status"` 패턴 (vault_root=tmp_path 시 적용)

repo-root `ingested/`는 **production 코드에서 어디에도 쓰지 않음**. legacy 디렉토리. tracked .keep 파일은 **`vault/ingested/`가 .gitignore되기 전 시대의 잔재**.

`.gitignore` line 51 `ingested/_status/` 라인은 repo-root `ingested/_status/` 하위 status 파일을 무시하지만, 정작 `ingested/` 디렉토리 자체와 `.keep`은 tracked — 모순적인 상태.

→ `git rm -r ingested/`로 tracked 잔재 제거 + `.gitignore`에 `ingested/` (디렉토리 단위) 추가하여 재발 방지.

### 5. heartbeat 실제 쓰기 경로 confirm

`src/ingest/heartbeat.py:26`: `HEARTBEAT_PATH_DEFAULT = Path("vault/ingested/_status/heartbeat.md")`
`src/ingest/worker.py:440,449`: `vault_root / "ingested/_status/heartbeat.md"` (vault_root는 production에서 `vault/`)

→ vault/ingested/_status/heartbeat.md 가 정식 경로. `vault/ingested/`는 .gitignore 처리되지 않았으나 raw/와 동일하게 vault 내부에 살므로 무방.

## .gitignore 변경 사항 (Task 3에서 적용)

```diff
 # Machine-generated pipeline state (heartbeat updated by collectors/ingest)
-ingested/_status/
+# (Phase 8 GAP-08) repo-root legacy `ingested/` removed entirely.
+# Production heartbeat lives at vault/ingested/_status/ — kept in vault.
+ingested/
```

**주의 사항:**
- `vault/notes/`는 `.gitignore`에 **추가하지 않음** — D-09 write-scope 화이트리스트의 절반이므로 사용자 메모가 git에 살아있어야 함.
- `notes/private/`는 line 14에서 이미 ignored (D-03 사적 메모) — 변경 없음.
- repo-root `ingested/` 차단으로 tests의 `tmp_path / "ingested"` 사용은 영향 없음(tmp_path는 .gitignore 평가 대상 아님).

## 삭제 영향 평가

- **회귀 리스크 0**:
  - `git rm -r ingested/`: production code 0건 의존. `.keep`만 들어있으므로 데이터 손실 없음. test fixtures는 tmp_path 기반이라 무관.
  - `vault/notes/` KEEP: 시스템 동작 변경 없음.
  - `vault/.graphify-staging/` KEEP: graphify 사용 시 정상 자동 채움.
- **Idempotency**: `git rm -r ingested/` 재실행 시 `did not match any files` (이미 없음, 무해).
- **CLAUDE.md 도식 정정** (Task 3): vault/notes/ 라인 제거 + notes_root 분리 멘탈 모델 명시.

## Task 2 사용자 결정 요청

다음 항목을 검토:

1. **`ingested/` (repo-root) 삭제 동의** — `git rm -r ingested/` (tracked .keep 2개 history에 보존됨). production 코드 의존 0건 확인됨.
2. **`vault/notes/` KEEP 동의** — 빈 디렉토리이지만 D-09 write-scope 화이트리스트의 절반. 삭제하면 사용자 vault 메모 경로 가시성 손실. **CLAUDE.md 도식의 outdated 설명만 Task 3에서 정정**(직접 디렉토리는 그대로 둠).
3. **`vault/.graphify-staging/` KEEP 동의** — graphify 사용 시 자동 채움.
4. **`.gitignore` 변경 동의** —
   - `ingested/_status/` → `ingested/` (디렉토리 단위로 강화)
   - `vault/notes/` 추가 **하지 않음** (사용자 vault 메모 보존)

전부 OK면 `approved`. 일부 수정 요청 시 명시 (예: "vault/notes/도 .gitignore에 추가", "ingested/는 KEEP" 등).

## Survey-Driven Updates to Task 3

Task 3 plan은 다음 가정 하에 작성됨 — SURVEY 결과로 일부 수정 필요:

- ❌ Task 3 plan: "vault/notes/ 삭제됨" → ✅ 실제: KEEP (기능 화이트리스트)
- ❌ Task 3 plan: ".gitignore에 vault/notes/ 추가" → ✅ 실제: 추가하지 않음
- ✅ Task 3 plan: "ingested/ 삭제" → 일치 (단, `git rm -r` 필요)
- ✅ Task 3 plan: "CLAUDE.md notes_root 분리 명시" → 일치 (도식에서 vault/notes 라인은 제거하되, 주석으로 "사용자 메모 화이트리스트 절반" 명시)

Task 2에서 위 변경을 같이 승인.
