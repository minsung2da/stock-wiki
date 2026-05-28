# Phase 5: Claude-Schedule Enrichment with Korean Number Safety - Context

**Gathered:** 2026-04-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4에서 `vault/raw/**/*.md` 로 축적된 raw 문서에 대해, **ingest venv 밖에서 실행되는 Claude Code Routines agent**(Anthropic cloud-hosted cron, 2026-04-14 GA)가 `_derived` frontmatter 블록을 채워 git으로 push하는 파이프라인을 구축한다. 이 페이즈는 **`_derived` 추출 루프까지만** 다룬다 — Phase 6 MCP 툴 확장 · Phase 7 그래프 · Phase 8 대시보드는 이후 페이즈.

**핵심 경계:**
- `src/collectors/` · `src/ingest/` 의 `anthropic`/`openai` import 금지 영구 유지(COLL-07 CI 가드).
- Schedule agent는 **별도 프로세스** — Claude Code Routines cloud 컨테이너에서 Claude Code 세션으로 기동, 사용자 Claude Max 구독 quota 사용(API 토큰 별도 청구 0). Container는 run당 fresh(상태 비보존, 자연 멱등).
- Agent는 `_derived` zone에만 쓴다. `provenance` · `ingest_state` 수정 금지(STORE-06 zone integrity).
- DART 재무제표 수치는 **LLM 무관여** — `dart-fss` 구조화 접근자 직접. 뉴스·리포트 서사 숫자만 regex→LLM→Pydantic→자릿수 체크섬 4단계 파이프라인.
- 임베딩 계산(bge-m3 1024-d)은 Phase 3에서 이미 작동 중 — 이 페이즈에서 재설정 없음.

</domain>

<decisions>
## Implementation Decisions

### Schedule Agent Execution Model (D-01 ~ D-06)

- **D-01:** **Claude Code Routines** (Anthropic cloud-hosted cron, 2026-04-14 GA) 채택. 로컬 systemd.timer / 수동 실행 옵션 탈락. 이유: 사용자가 Max 20x 구독 보유, PC 상태와 무관하게 동작 필요, 기동이 곧 Claude Code 세션 → 기존 skill·tool 생태계 재사용. Container는 run당 fresh(상태 비보존), 최소 cron 간격 1시간.
- **D-02:** 트리거 빈도 = **매일 1회, KST 07:00** (= 22:00 UTC 전날). 전날 수집분(Phase 4 `collect all`)의 새벽 enrichment. 주간 Claude 대화 quota 윈도우와 분리.
- **D-03:** Git 커밋 & push 전략 (**옵션 C — PR + auto-merge**):
  - 매 run에 routine이 `claude/enrich-YYYY-MM-DD` 브랜치로 push. 기본 브랜치 보호는 Routines 정책("main 직접 push 불가, `claude/*` 만 허용")을 자연스럽게 준수.
  - 1 run = 1 commit. 커밋 메시지: `enrich: _derived for N docs (YYYY-MM-DD)`.
  - Push 직후 GitHub PR 자동 생성 (routine 내 `gh pr create --label auto-merge --base main --head claude/enrich-YYYY-MM-DD`).
  - **GitHub auto-merge 활성화** — required checks (CI 테스트·import_guard) 통과 시 자동 병합. 리뷰 이력·CI 트레일은 PR에 보존되며 사고 시 `git revert` 1커밋으로 되돌림 가능.
  - Push 실패 시 (예: 기본 브랜치 한도 충돌) `git pull --rebase origin main` 재시도 1회. `_derived` append-only 특성상 conflict 가능성 매우 낮음.
  - 권한: GitHub fine-grained PAT, scope = Contents:RW + PullRequests:RW on **이 repo 단일**. Routines secrets 매니저에 주입 (주의: Routines는 아직 전용 secrets store 없음 — editor 권한자에게 env var 가시).
- **D-04:** 충돌 방지 — 파일 lock 없음. 수집기와 agent가 같은 파일을 동시에 append하는 경우는 거의 없으나, 발생 시 merge-on-conflict로 자연 해결. 충돌 지속 시 agent는 해당 문서 skip + `review_flags: ["merge_conflict"]`.
- **D-05:** 모델 = **Claude Sonnet 4.6**. 1 문서 = 1 호출(단일 prompt). 200K 토큰 초과 시 `_derived` null + `skip_reason: "oversize"` 기록. Haiku/Opus 대체 없음 (Sonnet 4.6의 한국어 금융 텍스트 구조화 출력이 최적점).
- **D-06:** 실행 quota 예산: Max 20x 기준 평시 ~4% / 실적 시즌 피크 ~9% (self-consistency 더블패스 포함). 다른 Claude 대화와 윈도우 분리됨. Routines 세션 메시지는 interactive Claude Code 사용과 동일한 Max 쿼터에서 차감.

### Frontmatter Zone Safety (D-07)

- **D-07:** Agent는 `_derived` 키만 쓴다. 다른 zone 수정 감지 규칙:
  - Agent는 commit 전 frontmatter의 `provenance`·`ingest_state`·기타 상위 키를 SHA256 해시해 비교 → 변경됐다면 `_derived` 써넣기 중단 + `review_flags: ["agent_zone_violation"]`
  - Phase 6의 `ingest doctor` 가 주기 스캔으로 drift 확인

### DerivedBlock Schema Extension (D-08 ~ D-12)

현재 `src/shared/frontmatter.py::DerivedBlock`:
```python
class DerivedBlock(BaseModel):
    tickers: list[str] = Field(default_factory=list)
    event_type: str | None = None
    catalysts: list[str] = Field(default_factory=list)
    sentiment: SentimentBlock | None = None
    numeric_facts: list[NumericFact] = Field(default_factory=list)
    summary: str | None = None
```

Phase 5에서 다음 필드 추가:

- **D-08:** `event_type` 을 Literal enum으로 좁힘 (현재 `str | None`):
  ```python
  event_type: Literal[
      # DART 주요사항 (8)
      "earnings_release", "equity_issue", "mergers_acquisitions", "major_contract",
      "board_change", "ownership_change", "buyback_announcement", "dividend",
      # DART 거래소공시 (4)
      "suspension", "watchlist_designation", "unfaithful_disclosure", "delisting",
      # KIND (2)
      "investment_caution", "investment_risk",
      # 뉴스·리포트 (3)
      "analyst_upgrade", "analyst_downgrade", "macro_commentary", "market_gossip",
      # fallback
      "other",
  ] | None = None
  ```
  총 17개 + `other` + `null`. LLM이 적절한 bucket 없다고 판단하면 `other`. 이벤트성 없는 문서(일반 기업 소개)는 `null`.
- **D-09:** `NumericFact` 스키마 확장:
  ```python
  class NumericFact(BaseModel):
      key: str                             # 한글 — DART 표준 항목 또는 자유 한글
      value: float                         # 원문 숫자
      unit: Literal[
          "KRW원", "KRW백만", "KRW억", "KRW조",
          "USD", "EUR", "JPY",
          "pct", "bps", "multiplier", "shares", "days", "other"
      ]
      value_krw: float | None = None       # 금액일 때 원단위 정규화; Python util 계산
      source_span: str | None = None       # 원문 발췌 (byte echo-back 검증용)
      offset: int | None = None            # body 내 시작 offset (검증 트레일)
  ```
  - `key` 언어 = 한글 (영문 아님). DART 연결재무제표 표준 항목명은 이미 표준화돼 일관성 확보. 뉴스 서사는 자유 한글.
  - `unit` 필드는 Literal enum으로 좁힘 — free-string 금지.
  - `value_krw` 는 LLM이 채우지 않는다. `src/shared/units.py::normalize_to_krw(value, unit)` pure function이 계산 (Phase 5 신규 모듈).
- **D-10:** `SentimentBlock` 스키마 확장:
  ```python
  class SentimentBlock(BaseModel):
      label: Literal[
          "strongly_bullish", "bullish", "neutral",
          "bearish", "strongly_bearish", "unclear"
      ] | None = None
      bullish_score: float | None = None      # 0.0-1.0, null = 해당없음/판단불가
      rationale: str | None = None            # 판단 근거 한 문장 (검증)
      scope: Literal["tone", "outcome"] | None = None
  ```
  - `neutral` = 실제 중립 (긍·부 균형). `unclear` = 정보 부족 판단 보류. 혼용 금지.
  - `label` 과 `bullish_score` 매핑 검증 (Python post-check): strongly_bullish≥0.85, bullish 0.60-0.85, neutral 0.40-0.60, bearish 0.15-0.40, strongly_bearish≤0.15, unclear↔null. 불일치 → `review_flags: ["sentiment_score_label_mismatch"]`.
  - `scope`: "tone"=기자·애널리스트 논조, "outcome"=사건 자체의 기업 영향. 예: 악재지만 시장은 긍정 평가 → `label=bullish, scope=tone` 과 `label=bearish, scope=outcome` 분리 가능(현 구조는 단일 SentimentBlock이므로 한쪽 기록, 판별이 어려우면 `unclear`).

- **D-11:** `DerivedBlock` 에 `review_flags: list[ReviewFlag] = Field(default_factory=list)` 추가:
  ```python
  class ReviewFlag(BaseModel):
      flag: Literal[
          "numeric_echo_mismatch",
          "numeric_sanity_violation",
          "dart_structured_disagreement",
          "self_inconsistent",
          "oversize_skipped",
          "prompt_injection_suspected",
          "sentiment_score_label_mismatch",
          "agent_zone_violation",
          "merge_conflict",
      ]
      detail: str
      fact_key: str | None = None
  ```
- **D-12:** `DerivedBlock.skip_reason: str | None = None` 추가 — `_derived` 가 비어있을 때 사유 기록(`"oversize"`, `"review_required"`, `"merge_conflict"`).

### Sentiment Source-Conditional Application (D-13)

- **D-13:** sentiment는 소스에 따라 선택 적용. 프롬프트가 `source` frontmatter 필드를 읽어 분기:
  - **추출 O**: 뉴스(한경/이데일리), DART 주요사항(B)
  - **추출 X (null)**: DART 정기보고서(A), DART 거래소공시(I)/KIND 이벤트, 거시 ECOS/FRED
  - 이유: 정기공시는 거의 중립, KIND/거래소 공시는 event_type이 이미 방향성 내포, 거시는 기업 비특정

### Numeric Fact Extraction Pipeline (D-14 ~ D-19)

- **D-14:** DART 재무제표 수치 (INGEST-06) = `dart-fss` 구조화 접근자 직접 사용, **LLM 무관여**. 파이프라인:
  1. DART 문서의 `rcept_no` 로 dart-fss `Report.financial_statement()` 호출
  2. 표준 line-item (매출액, 영업이익, 당기순이익, ...)을 한글 key 그대로 `numeric_facts` 에 기록
  3. `value_krw` = `value` (DART는 원 단위 제공)
  4. `source_span` = null (원문 string과 직접 비교 생략, DART 구조화 값이 권위 소스)
- **D-15:** 뉴스·리포트 서사 숫자 (INGEST-07) 4단계 파이프라인:
  1. **regex 후보 추출** (`src/shared/number_extraction.py::extract_numeric_candidates`, pure Python, LLM 무관):
     - 카테고리: 한글 금액·원·%·배·외화·주식·가격·지수 (8개)
     - 출력: `NumericCandidate(raw_text, offset, length, guessed_unit, sentence_text, pre_context, post_context, section_hint)`
     - enriched context로 LLM 정확도 향상
  2. **LLM 선택** — Sonnet 4.6가 후보 중 "의미 있는 fact" 선택 + `key` 부여 + `source_span` 의무 echo-back
  3. **Pydantic 검증** — 스키마 타입, unit enum 유효성
  4. **자릿수 체크섬**:
     - **character-level echo-back**: `body[offset:offset+len(source_span)] == source_span` (환각 차단 zero-tolerance). Python `str[i:j]`는 Unicode codepoint 인덱스이므로 한글도 문자 단위 비교로 동등하게 작동.
     - magnitude sanity: `SANITY_RULES[key]` 테이블로 범위 위반 감지
- **D-16:** **self-consistency 더블패스**: 문서당 LLM 2회 호출 (temperature=0). 비교자는 **논리 equality**(문자열 exact 아님):
  - `numeric_facts` 는 `(key, round(value, 4), unit)` 3-tuple 집합 equality
  - `tickers / event_type / catalysts / sentiment.label` 은 exact match
  - `summary / rationale` 같은 자유 산문은 비교 대상 제외 (Sonnet 4.6 temp=0도 "일부 변동 가능" 공식 인정)
  - 100% 일치 → commit
  - 불일치 → `review_flags: ["self_inconsistent"]` 기록 + F-1b 원칙대로 `_derived` 전체 null
  - 부하: Max 20x quota ~9% (허용 범위)
- **D-17:** **DART 전건 교차검증**: `_derived.numeric_facts`(LLM 추출) vs `dart-fss`(구조화) 값 자동 비교. 불일치 시 `review_flags: ["dart_structured_disagreement"]`. ROADMAP 10-filing golden set 제약을 전건으로 확장.
- **D-18:** **단위 sanity 테이블** (`src/shared/number_sanity.py`): key×unit 조합의 상식선 규칙. 예:
  ```python
  SANITY_RULES = {
      "매출액":       {"unit": "KRW원", "min_krw": 1e8, "max_krw": 1e15},
      "영업이익률":    {"unit": "pct", "min": -100, "max": 100},
      "외국인지분율": {"unit": "pct", "min": 0, "max": 100},
      "PER":          {"unit": "multiplier", "min": 0, "max": 1000},
      # ... 초기 20-30 규칙, 관찰하며 확장
  }
  ```
  위반 시 `review_flags: ["numeric_sanity_violation"]`.
- **D-19:** `_derived` 멱등성:
  - 원문 body의 `content_hash` 가 동일하고 `_derived` 가 이미 존재 → skip.
  - 원문 body 변경 시 (`content_hash` 바뀜) → 기존 `_derived` 폐기, 재추출.
  - self-consistency/sanity 실패로 review_flag 붙어 stick된 문서도 `content_hash` 변경 전까지 재추출 금지 (F-4c).

### Failure Handling Policy (D-20 ~ D-22)

- **D-20:** **F-1b: document-level all-or-nothing** — fact 하나라도 검증 실패하면 문서 `_derived` 전체 null + `skip_reason: "review_required"` + `review_flags: [...]`.
- **D-21:** **F-4c: stick on failure** — 실패 후 재시도 없음. 원문 `content_hash` 변경 시에만 재추출. 같은 환각·규칙 위반을 반복해서 재호출하지 않음(비용 절감).
- **D-22:** **F-5b: 사람 교정은 `notes/` 로만** — `_derived` 는 agent 전용. 사람이 `_derived` 직접 편집하면 agent zone violation. Phase 6 MCP 툴이 쿼리 시 `notes/` 교정 메모 우선 적용 (Phase 6 스코프).

### Observability & Backlog (D-23 ~ D-26)

- **D-23:** `ingested/_status/heartbeat.md` 의 `enrich` source section 추가:
  ```yaml
  enrich:
    last_run: "2026-04-24T22:00:00Z"
    last_success: "2026-04-24T22:05:13Z"
    last_failure: null
    consecutive_failures: 0
    docs_processed: 47
    docs_skipped_oversize: 2
    docs_review_flagged: 3
    backlog_count: 12
    review_flags: {sentiment_score_label_mismatch: 1, dart_structured_disagreement: 2}
    alert_level: null      # null | "info" | "warn"
  ```
  및 최상위 `disk` section:
  ```yaml
  disk:
    vault_mb: 487
    git_mb: 1203
    db_mb: 2450
    pgdata_mb: 3800
    alert_level: null
  ```
- **D-24:** SLA 임계치 5가지:
  - `consecutive_failures >= 2` → alert_level = "warn"
  - `backlog_count > 50` → "warn"
  - `review_flagged > 10%` → "info"
  - `now - last_run > 26h` → "warn"
  - `vault_mb > 2000` → "info", `db_mb > 10000` → "warn"
- **D-25:** **`ingested/_status/backlog.md`** — 사람 수동 개입 필요 항목 전체 기록:
  - 매 run에서 오늘 날짜 섹션을 **regenerate**. 이전 날짜 섹션은 read-only 유지.
  - 항목 키 = `path + flag`. 같은 키가 이전 backlog에 있으면 `first_seen` 유지 (persistence tracking).
  - 섹션 구조: Missing _derived / Review flagged / Oversize skipped / Disk warnings / Schedule status warnings / Chronic items (3일 이상 미해결).
  - 30일 지난 날짜 섹션은 `ingested/_status/backlog-archive/YYYY-MM.md` 로 이동 (Phase 9 로테이션 정교화).
  - 스키마 version 필드 유지 (`schema_version: 1`) — 향후 변경 시 migration.
- **D-26:** 백로그 노출 경로 단계적 승격:
  - Phase 5: heartbeat 필드 + backlog.md 직접 읽기
  - Phase 6: MCP `health` 툴이 backlog.md 파싱해 구조화 JSON 반환
  - Phase 8: Obsidian Dataview 대시보드에 chronic items alert banner

### Auto-Recovery Scope (D-27)

- **D-27:** 자동 복구 대상:
  - Anthropic API rate-limit 히트 → 다음 run에서 자연 복구 (재시도 로직 불필요)
  - GitHub push 실패 → `git pull --rebase` 재시도 1회 (내장)
  - 그 외 (Claude 서비스 장애, portfolio.md 스키마 오류, 스키마 위반, 숫자 hallucination 누적 등) → 사람 개입. backlog.md / heartbeat 기록만.

### Disk Capacity Guard (D-28)

- **D-28:** 임베딩 타입 = `vector(1024)` full-float32 유지 (4 byte × 1024 = 4KB/chunk). 현재 노트북 성능 허용. halfvec 전환은 retrospective 결정 사항으로 보류 — Phase 5는 용량 메트릭만 기록, 임계치 초과 시 Phase 9에서 halfvec 마이그레이션 검토.

### Agent Code Location (D-29)

- **D-29:** **Routines skill 위치 = repo 내 `.claude/routines/enrich/SKILL.md`** (리서처 confirm). `~/.claude/skills/` 아래는 로컬 전용이며 Routines cloud container는 repo clone 시점의 파일만 읽음. 별도 repo 옵션도 불필요 — 단일 repo 내부가 버전 관리·리뷰·PR 흐름 모두 깔끔.
  - 디렉터리 구조:
    ```
    .claude/routines/enrich/
      SKILL.md              # routine entry point (Claude Code가 읽음)
      prompts/
        derived_news.md     # 뉴스 전용 source 분기 프롬프트
        derived_dart_b.md   # DART 주요사항(B) 전용
        derived_kind.md     # KIND 이벤트 전용
        derived_macro.md    # 거시 전용
      helpers/
        facts_equal.py      # self-consistency 비교자 (D-16)
        prompt_build.py     # source별 prompt 조립
    ```

### Resolved Gray Areas (리서처 확인)

다음 항목은 CONTEXT 작성 당시 Claude's Discretion이었으나 리서치 결과로 결정됨:

- **self-consistency 비교자**: D-16 본문에 명시됨 — `(key, round(value,4), unit)` tuple-set equality on numeric_facts + exact match on tickers/event_type/catalysts/sentiment.label, summary/rationale 제외.
- **character-level echo-back**: D-15 본문에 명시됨 — Python str[i:j]는 codepoint 인덱스, 한글 동등 작동 ("byte-level" 용어는 오해 — 정정됨).
- **Routines skill 위치**: D-29로 이동 — `.claude/routines/enrich/`.
- **Push 전략**: D-03으로 이동 — PR + auto-merge (옵션 C), `claude/enrich-YYYY-MM-DD` 브랜치 경유.

### Claude's Discretion (남은 항목)

- backlog.md "Chronic items" 섹션의 연령 경계값 (3일 → 관측 후 조정)
- regex 후보 top-N 제한 — 현재 "제한 없음" (뉴스 2문단 수준에서 5-15개 후보로 충분); DART 본문이 10+ 후보 생성 시 관측 후 결정
- LLM 프롬프트의 few-shot 예시 포함 여부 — Sonnet 4.6 한국어 금융 기본 성능 관측 후 결정 (Wave-1 golden set으로 MVP는 zero-shot)
- schema_version 증가 시 backlog.md migration 스크립트 필요 시점 (v1 Phase 5, v2는 필요 시)
- DART line-item synonym map 확장 — `매출액` vs `수익(매출액)` 같은 DART 내부 동의어 관찰 후 매핑 테이블 작성 (backlog-driven growth)
- Routines container cold-start 시간 측정 — DART corp_list 다운로드가 매 run 반복되면 skill 내부에 cache 레이어 추가 검토

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 3 Artifacts (Pattern Templates)
- `src/shared/frontmatter.py::FrontMatter, ProvenanceBlock, IngestStateBlock, DerivedBlock, SentimentBlock, NumericFact` — 3-zone 스키마 · atomic write. Phase 5에서 확장 대상.
- `src/shared/content_hash.py::compute_content_hash, normalize_body` — body 정규화 + sha256. `_derived` 멱등성 기준.
- `src/ingest/worker.py` — 현재 ingest 파이프라인 (Phase 3 기준 작동 중). Phase 5 agent는 이와 별개이나 frontmatter 스키마를 공유.
- `src/ingest/heartbeat.py::record_source_run` — source별 heartbeat 갱신 API. `enrich` 키 추가 대상.
- `src/ingest/injection_defense.py::detect_injection_patterns` — INGEST-08 패턴 필터. agent 프롬프트에 wrap 대상.

### DART Integration
- `src/collectors/dart/client.py::get_client, find_corp` — dart-fss 세션 래퍼. 구조화 접근자 호출은 이 세션 재사용.
- `src/collectors/dart/fetcher.py` — filing 메타 조회 패턴.
- `dart-fss` 공식 문서 — `Report.financial_statement()` 반환 구조, 표준 line-item 목록.

### Phase 4 Artifacts (소스별 frontmatter 참조)
- `.planning/phases/04-multi-source-collector-coverage/04-CONTEXT.md` — trust_level 정의(D-24), news license_flag(D-13), KIND event_type mapping(D-14 Amended).
- `vault/raw/{dart,krx,news,macro,kind}/**/*.md` — 실제 frontmatter 예시.

### Requirements
- `.planning/REQUIREMENTS.md` — INGEST-02/03/04/05/06/07 (이 페이즈 타깃), INGEST-08/09 (Phase 3 완료, 재사용)

### Roadmap
- `.planning/ROADMAP.md` Phase 5 — Claude Schedule agent + Korean Number Safety 성공 기준 5가지

### Prior Decisions (Phase 3/4 계승)
- `.planning/phases/03-one-company-walking-skeleton/03-CONTEXT.md` — embedding_model version tracking, heartbeat pattern, injection defense layer
- Phase 4 D-24 trust_level (trusted/semi_trusted) — sentiment scope 분기 기준

### External Tech
- **Claude Code Routines** (Anthropic cloud-hosted cron, 2026-04-14 GA) — 공식 문서: https://code.claude.com/docs/en/routines. 배포 = repo 내 SKILL.md commit (D-29). 기본 브랜치 보호 정책상 `claude/*` prefix 브랜치만 push 가능 → PR + auto-merge flow(D-03).
- **GitHub auto-merge** — required status checks(CI 테스트·import guard) 통과 시 자동 병합. operator runbook: repo Settings → General → "Allow auto-merge" 활성, branch protection rule `main`에 required checks 지정.
- **GitHub fine-grained PAT** — scope = Contents:RW + PullRequests:RW on 단일 repo. Routines secrets 매니저에 env var로 주입.
- Sonnet 4.6 한국어 금융 텍스트 구조화 출력 성능 — few-shot 필요성 판단 (Wave-1 golden set 관측)
- FastMCP 2.x — Phase 6 MCP `health` 툴과의 인터페이스 (backlog.md 파싱 규격)

### Test Fixtures
- `tests/conftest.py` — 기존 fixture 재사용
- 신규: `tests/fixtures/derived/*.yaml` — 골든 셋 `_derived` 예시 (DART 재무 10건, 뉴스 10건)
- 신규: `tests/fixtures/llm_responses/` — 더블패스 self-consistency 시뮬레이션용 LLM 응답 캡처

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/shared/frontmatter.py::read_frontmatter, write_frontmatter` — atomic read/write, zone 무결성 체크
- `src/shared/frontmatter.py::DerivedBlock` (확장 대상)
- `src/shared/content_hash.py::compute_content_hash` — `_derived` 멱등성 기준
- `src/ingest/heartbeat.py::record_source_run(..., extra=...)` — Phase 4에서 확장됨, `enrich` source 신규 사용
- `src/ingest/injection_defense.py::detect_injection_patterns` — agent prompt에 래핑
- `src/collectors/dart/client.py::get_client` — dart-fss 세션 (구조화 접근자 호출 재사용)

### Established Patterns (Phase 3/4 계승)
- frontmatter zone 분리 (provenance / ingest_state / _derived) + atomic write
- content_hash 기반 멱등성
- SQLAlchemy text() + bind parameters only (f-string SQL 금지)
- `src.` 접두사 없는 import (`from shared.frontmatter import ...`)
- anthropic/openai import CI 가드 (COLL-07) — 영구 유지
- heartbeat source별 독립 기록 + extra kwarg

### Integration Points (신규 생성)
- `src/shared/units.py::normalize_to_krw(value: float, unit: str) -> float | None` (신규) — pure function
- `src/shared/number_extraction.py::extract_numeric_candidates(body: str, section: str | None) -> list[NumericCandidate]` (신규) — regex pure util
- `src/shared/number_sanity.py::SANITY_RULES, check_sanity(fact: NumericFact) -> ReviewFlag | None` (신규) — 상식선 규칙
- `src/shared/frontmatter.py` 확장 — DerivedBlock/SentimentBlock/NumericFact/ReviewFlag 새 필드
- `src/ingest/backlog.py::BacklogManager, render_backlog(today_items, prior_backlog_path)` (신규) — backlog.md 생성 + first_seen 병합
- **Routines skill** (D-29) — `.claude/routines/enrich/SKILL.md` + `prompts/derived_{news,dart_b,kind,macro}.md` + `helpers/facts_equal.py`
- **Agent prompt template** (신규) — source별 분기, source_span character-level echo-back 의무, sentiment 적용 조건, review_flags 스키마

### Non-Touch (절대 변경 금지)
- `src/ingest/worker.py` — Phase 3 pipeline 그대로. Phase 5는 **별개 프로세스**. worker는 `_derived` 를 **소비**만 하지 **생성하지 않음**.
- `src/collectors/` 하위 전체 — Phase 4 작동. anthropic/openai import 영구 금지.

</code_context>

<specifics>
## Specific Ideas

### Agent 워크플로우 (1 run 의 pseudocode)

```
0. Routines container fresh start:
   - repo clone (auth via fine-grained PAT env var)
   - git checkout -b claude/enrich-YYYY-MM-DD origin/main
1. scan vault/raw/**/*.md:
     - parse frontmatter
     - if _derived not null AND content_hash unchanged → skip
     - if skip_reason in ["review_required", "oversize", "merge_conflict"] AND content_hash unchanged → skip (F-4c stick)
2. for each candidate doc:
     a. if token_count(body) > 200_000 → _derived = null, skip_reason = "oversize"; continue
     b. source_type = fm.provenance.source  (dart, news, macro, kind, krx)
     c. if sentiment 적용 소스 아님 (D-13) → sentiment prompt 생략
     d. load prompt template per source (prompts/derived_{news|dart_b|kind|macro}.md)
     e. LLM call 1 (temperature=0) → derived_v1
     f. LLM call 2 (temperature=0) → derived_v2  # self-consistency
     g. if not facts_equal(derived_v1, derived_v2) → _derived=null, review_flags+=["self_inconsistent"]; continue
        # facts_equal = (key, round(value,4), unit) tuple-set equality on numeric_facts
        #             + exact match on tickers/event_type/catalysts/sentiment.label
        #             + summary/rationale 제외
     h. for each numeric_fact:
          - character-level echo-back: body[offset:offset+len(source_span)] == source_span?  (Python codepoint slice)
          - sanity check: SANITY_RULES[key]
          - if DART source: compare vs dart-fss structured
          - any fail → _derived=null (F-1b all-or-nothing), review_flags+=[...]
     i. compute value_krw via units.normalize_to_krw  (Python util, LLM 무관여)
     j. check sentiment label/score mapping (D-10)
     k. check agent_zone_violation: non-_derived keys unchanged?
     l. write frontmatter (atomic)
3. compute stats + review_flags counters
4. render ingested/_status/backlog.md (today's section + chronic items)
5. render ingested/_status/heartbeat.md (enrich + disk sections, alert_level)
6. git add -A; git commit -m "enrich: _derived for N docs (YYYY-MM-DD)"
7. git push origin claude/enrich-YYYY-MM-DD
   - if push fails (main 업데이트로 base 변경): git pull --rebase origin main && git push (1회 재시도)
8. gh pr create --base main --head claude/enrich-YYYY-MM-DD \
     --title "enrich: _derived for N docs (YYYY-MM-DD)" \
     --body "Auto-generated by Routines enrich skill. See heartbeat.md for details." \
     --label auto-merge
   → GitHub auto-merge가 required checks 통과 후 자동 병합
```

### DART 구조화 fact 추출 예시

DART 재무제표에서 삼성전자 2025 Q4 실적보고서:
- dart-fss `Report.financial_statement('연결')` 호출 → DataFrame
- 표준 line-item 매핑 예시:
  ```python
  DART_STANDARD_LINE_ITEMS = {
      "revenue": "매출액",
      "operating_profit": "영업이익",
      "net_income": "당기순이익",
      "total_assets": "자산총계",
      "total_liabilities": "부채총계",
      # ... 약 30개
  }
  ```
- 출력:
  ```yaml
  numeric_facts:
    - key: 매출액
      value: 65000000000000
      unit: KRW원
      value_krw: 65000000000000
      source_span: null      # DART 구조화 값, 원문 대조 불요
  ```

### regex 후보 예시

뉴스 본문 "삼성전자의 2025년 4분기 영업이익이 전년 대비 5.3% 증가한 4조 2,000억 원으로 집계됐다."

regex 추출 → 2 candidates:
```python
[
  NumericCandidate(
    raw_text="5.3%",
    offset=36,
    length=4,
    guessed_unit="pct",
    sentence_text="삼성전자의 2025년 4분기 영업이익이 전년 대비 5.3% 증가한 4조 2,000억 원으로 집계됐다.",
    pre_context=" 전년 대비 ",
    post_context=" 증가한 4조",
    section_hint=None,
  ),
  NumericCandidate(
    raw_text="4조 2,000억 원",
    offset=45,
    length=11,
    guessed_unit="KRW조",
    sentence_text="... 5.3% 증가한 4조 2,000억 원으로 집계됐다.",
    pre_context=" 증가한 ",
    post_context=" 으로 집",
    section_hint=None,
  ),
]
```

LLM 출력 (fact 2건):
```yaml
- key: 영업이익증가율_yoy
  value: 5.3
  unit: pct
  value_krw: null
  source_span: "5.3%"
  offset: 36
- key: 영업이익
  value: 4.2
  unit: KRW조
  value_krw: 4.2e12     # Python util이 계산
  source_span: "4조 2,000억 원"
  offset: 45
```

### backlog.md 예시

```markdown
---
updated: 2026-04-24T22:05:13Z
schema_version: 1
---

# Schedule Agent Backlog

*운영자 수동 개입이 필요한 항목. 매 schedule run에 오늘 날짜 섹션을 regenerate.*

---

## 2026-04-24 (run at 22:05:13Z, 12 items)

### Missing _derived (3)
| Path | First seen | Age |
|------|-----------|-----|
| vault/raw/news/2026-04/hankyung_a3f4b2c1.md | 2026-04-24 | 0 |
...

### Review flagged (3)
| Path | Flag | First seen | Note |
|------|------|-----------|------|
| vault/raw/dart/00164779/20260420000456.md | dart_structured_disagreement | 2026-04-20 | 4 days; 사람 교정 필요 |
...

### Chronic items (3 days+)
...

---

## 2026-04-23 (run at 22:05:41Z, 10 items)
*[이전 run 기록 — read-only]*
...
```

### event_type 매핑 휴리스틱 (프롬프트 힌트)

소스별 일반적 event_type 후보:
- **DART 주요사항(B) `report_nm`**:
  - "매출액 또는 손익구조 30% 이상 변동" → `earnings_release`
  - "유상증자결정" → `equity_issue`
  - "단일판매·공급계약체결" → `major_contract`
  - "타법인 주식 및 출자증권 취득결정" → `mergers_acquisitions`
  - "임원·주요주주의특정증권등소유상황보고서" → `ownership_change`
  - "자기주식취득결정" → `buyback_announcement`
  - "현금·현물배당결정" → `dividend`
- **뉴스 제목 키워드**:
  - "목표가 상향" → `analyst_upgrade`
  - "목표가 하향" → `analyst_downgrade`
  - "기준금리", "CPI", "무역수지" → `macro_commentary`
  - "테마주", "관련주", "급등" → `market_gossip` (낮은 신뢰)

</specifics>

<deferred>
## Deferred Ideas

- **원문 숫자 확장** — 나이·기간·순위·개수 카테고리는 regex 범위에서 제외. Phase 9 관측 후 추가 여부 결정.
- **LLM few-shot 예시 첨부** — Sonnet 4.6의 한국어 금융 기본 성능 관측 후. MVP는 zero-shot.
- **DART 사업보고서 map-reduce** (D oversize 대응) — Phase 9 운영 하드닝.
- **halfvec 마이그레이션** — DB 크기 임계치 도달 시 (Phase 9).
- **`stock enrich` 수동 CLI** — Phase 5 MVP는 Claude Code Routines만. 로컬 systemd.timer backup, `stock enrich --dry-run` 같은 편의는 Phase 9.
- **V2-NEWS-01: 영문 뉴스 보조 레이어** — Phase 5는 한글 primary (한경/이데일리). 영문 뉴스는 별도 backlog 항목으로 분리.
  - 권장 소스: **Bloomberg Asia** (trust_level=trusted, 거시 글로벌 관점 · 외환 포지셔닝 · EM 자본 흐름) + **The Korea Herald Business** (trust_level=semi_trusted, 외국인 perspective)
  - 제외 권장: Korea Times · SEDaily English · Yonhap English — 한글 원본의 **번역본**으로 속보성 1일 지연, 정보 밀도 한경·이데일리의 1/10, fidelity 손실 (K-IFRS→IFRS 번역, hedge 표현 flattening). Cross-check 가치 약함.
  - 적용 범위: 주로 `event_type=macro_commentary` — portfolio ticker 특정이 아닌 거시 흐름. 기업 특정 뉴스는 한글 소스가 속보·보도량 모두 우위.
  - 구현: `src/collectors/news/feeds.py` 에 `source="news_en"` 분기 추가 (signature 동일, outlet enum 확장). Phase 9 이후 시점.
- **MCP `health` 툴 구현** — Phase 6 스코프.
- **Obsidian Dataview 백로그 대시보드** — Phase 8 스코프.
- **Push 알림 / 이메일 경보** — Phase 9 운영 하드닝 검토 (현재는 backlog.md / heartbeat 수동 확인).
- **LLM 모델 업그레이드 스왑** — Sonnet 4.7/Opus 4.7 출시 시 성능 비교. 현재 Sonnet 4.6 lock.
- **DART 전건 교차검증 관측 후 scope 조정** — disagreement가 대부분 용어 동의어 문제일 경우 룰 완화 / 일치 임계치 설정 (Phase 9).
- **`notes/` 교정 메모 → MCP 쿼리 반영** — Phase 6 스코프. 현재 spec은 "Phase 6 MCP 툴이 쿼리 시 notes 우선" 만 약속.
- **schema_version 2 migration** — v1 범위로 Phase 5 완결. 파일 shape 변경 필요 시 Phase 9.
- **종목토론방 같은 adversarial source 전용 파이프라인** — INGEST-09 현재 LLM 추출 제외로 완결. Phase 5 재논의 없음.
- **실시간 웹훅 트리거** — `vault/raw/` 변경 시 즉시 agent 기동 (Claude Code Routines의 event-driven 트리거 모드). Phase 9 검토.

### Reviewed Todos (not folded)
(없음 — Phase 5 관련 todo 0건)

</deferred>

---

*Phase: 05-claude-schedule-enrichment-with-korean-number-safety*
*Context gathered: 2026-04-24*
