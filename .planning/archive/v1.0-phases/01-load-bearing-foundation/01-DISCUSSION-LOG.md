# Phase 1: Load-Bearing Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-17
**Phase:** 01-load-bearing-foundation
**Areas discussed:** Repo Layout, Private Portfolio Overlay, WSL Path Migration, Frontmatter 3-Zone Structure

---

## Repo Layout / Code Placement

| Option | Description | Selected |
|--------|-------------|----------|
| A) Code in `src/`, vault at root | 코드를 `src/` 하위에, vault 데이터는 루트 유지. Obsidian 재설정 불필요. | ✓ |
| B) Vault in subfolder | vault를 `vault/` 하위로 이동. Obsidian vault 경로 변경 필요. | |
| C) Flat at root | 코드와 데이터 모두 루트에 flat. 코드 파일이 Obsidian 검색에 잡힘. | |

**User's choice:** A — 코드 `src/`에, vault 루트 유지
**Notes:** pyproject.toml 구조는 Claude 재량에 위임

---

## Private Portfolio Overlay

| Option | Description | Selected |
|--------|-------------|----------|
| A) Gitignored local-only path | `notes/private/` gitignore. 가장 단순. 템플릿 제공. | ✓ |
| B) Git submodule | 별도 private repo를 submodule로. 버전 관리 가능하나 복잡. | |
| C) git-crypt | 암호화된 채 커밋. 팀원별 분리 어려움. | |
| D) `.env`-style overlay | 환경변수로 주입. Obsidian에서 편집 불가, vault-as-SoT 위배. | |

**User's choice:** A — gitignored 로컬-only 경로
**Notes:** None

---

## WSL Path Migration Timing

| Option | Description | Selected |
|--------|-------------|----------|
| A) Hard migrate now | Phase 1 시작 시 `~/stock/`으로 이동. Obsidian `\\wsl$\...`로 재연결. | ✓ |
| B) Script ready, run later | 마이그레이션 스크립트 준비만. 실행은 나중. | |
| C) Document only | README에 설명만 추가. 현재 경로 유지. | |

**User's choice:** A — 지금 하드 마이그레이션
**Notes:** None

---

## Frontmatter 3-Zone Structure

| Option | Description | Selected |
|--------|-------------|----------|
| A) Nested dictionaries | `provenance: {...}`, `ingest_state: {...}`, `_derived: {...}`. 구역 경계 명확. | ✓ |
| B) Flat prefix | `prov_source`, `ingest_processed`, `derived_sentiment`. Dataview 쿼리 짧음. | |
| C) Hybrid | provenance/ingest flat, `_derived`만 중첩. 절충안. | |

**User's choice:** A — 중첩 딕셔너리
**Notes:** Pydantic 모델 1:1 매핑, Dataview 중첩 접근(`provenance.source`) 사용

---

## Claude's Discretion

- pyproject.toml 구조 (단일 + groups vs uv 워크스페이스)
- Docker 이미지 선택
- Pre-commit hook 프레임워크
- CI 플랫폼
- 테스트 프레임워크 및 fixture 구성

## Deferred Ideas

None
