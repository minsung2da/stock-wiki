---
status: partial
phase: 08-vault-dashboards-research-memo-templates
source: [08-VERIFICATION.md]
started: 2026-05-07T15:25:00Z
updated: 2026-05-07T15:25:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. End-to-end thesis flow (NOTE-03)
expected: Obsidian에서 templates/notes/thesis.md를 notes/private/005930/thesis.md로 복사하고, `uv run stock ingest run` 실행 후, MCP search 툴로 thesis 키워드 검색 → `vault_path='notes/private/005930/thesis.md'`인 항목이 ≥1개 등장
result: [pending]

### 2. Dashboard 시각 검증
expected: Obsidian에서 dashboards/portfolio.md, dashboards/watchlist.md, dashboards/events-this-week.md를 열어 코드블록이 raw로 노출되지 않고 table이 렌더링됨 (빈 table도 OK)
result: [pending]

### 3. Hub 자동 생성 확인 (DASH-04)
expected: `uv run stock ingest run` 실행 후 `vault/ingested/by-ticker/{corp_code}.md` 파일 존재 및 idempotency 검증 (재실행 시 mtime 변경 없음 — content_hash 동일 시)
result: [pending]

### 4. Git 위생 검증
expected: `git status`에서 `dashboards/_data/` 및 `notes/private/`가 untracked로 노출되지 않음 (.gitignore 등록 확인)
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
