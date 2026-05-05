---
phase: 07-graph-layer-graphify-integration
reviewed: 2026-05-05T16:23:57Z
depth: standard
files_reviewed: 25
files_reviewed_list:
  - config/graphify.json
  - src/cli/__main__.py
  - src/cli/commands.py
  - src/db/migrations/versions/0004_phase07_edge_check.py
  - src/graph/__init__.py
  - src/graph/canonical.py
  - src/graph/snapshot.py
  - src/graph/window.py
  - src/ingest/edges.py
  - src/ingest/worker.py
  - tests/db/test_migration_0004.py
  - tests/graph/__init__.py
  - tests/graph/conftest.py
  - tests/graph/test_canonical_queries.py
  - tests/graph/test_edges_derived.py
  - tests/graph/test_edges_deterministic.py
  - tests/graph/test_edges_idempotency.py
  - tests/graph/test_get_related_regression.py
  - tests/graph/test_snapshot_cli.py
  - tests/graph/test_window.py
  - tests/stock_mcp/conftest.py
  - tests/stock_mcp/test_get_related.py
  - tests/test_cli.py
  - tests/test_ingest_worker.py
  - vault/graph/README.md
findings:
  critical: 0
  warning: 3
  info: 5
  total: 8
status: issues_found
---

# Phase 7: Code Review Report

**Reviewed:** 2026-05-05T16:23:57Z
**Depth:** standard
**Files Reviewed:** 25
**Status:** issues_found

## Summary

Phase 7 그래프 레이어 (GRAPH-01/02/03) 구현은 전반적으로 견고하다. 6-value edge_type CHECK 마이그레이션, idempotent edges.populate, soft-fail 격리(D-04), KST 기반 snapshot pipeline, 5개 캐노니컬 쿼리, README parity 테스트가 모두 잘 짜여 있고 테스트 커버리지가 두텁다. 보안 문제(SQL injection, 시크릿 등)는 없음 — 모든 SQL은 SQLAlchemy `text()` + bind 파라미터.

다만 다음 항목들이 동작 상의 미세한 결함 또는 contract 일관성 문제로 발견되었다:

1. **Q1/Q3/Q5 cutoff 시간대 불일치** — 코드는 OS-local `date.today()`를 사용하지만 README는 KST 자정 기준을 명시. 비-KST 환경(CI/타임존 다른 머신)에서 결과 흔들림.
2. **Q2 `days` 파라미터 미사용** — signature는 받지만 SQL에 반영되지 않음. README 계약과 불일치.
3. **worker.py 엔티티 재시드 경로의 부분적 예외 누설** — `engine.connect()` 자체 실패는 `contextlib.suppress` 밖이라 전파.

나머지는 Info급 가독성/관용 문제다.

## Warnings

### WR-01: Q1/Q3/Q5 cutoff은 KST가 아닌 OS-local 자정 기준

**File:** `src/graph/canonical.py:51, 129, 223`
**Issue:** `date.today()`는 호스트 OS 로컬 시간대를 사용한다. README(`vault/graph/README.md:9`)는 "모든 날짜는 KST 자정 기준"이라고 명시했고, snapshot 레이어(`snapshot.py:_today_kst`, `window.py`)는 일관되게 `ZoneInfo("Asia/Seoul")`을 사용한다. 하지만 캐노니컬 쿼리는 OS-local을 사용해 UTC/다른 TZ 머신에서 cutoff이 ±1일 어긋난다. 같은 vault·DB라도 머신 별로 결과가 흔들린다 — Q1 "오늘 어때?", Q3 "최근 14일", Q5 "최근 60일"의 contract 위반.
**Fix:**
```python
# src/graph/canonical.py 상단에 추가
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
    KST = ZoneInfo("Asia/Seoul")
except ImportError:
    from datetime import timezone, timedelta
    KST = timezone(timedelta(hours=9))

# 각 쿼리에서:
# - cutoff = date.today() - timedelta(days=days)
# + cutoff = (datetime.now(KST).date() - timedelta(days=days))
```

### WR-02: Q2 `days` 파라미터가 SQL에 반영되지 않음

**File:** `src/graph/canonical.py:81-119`
**Issue:** `q2_catalyst_chain(ticker: str, days: int = 90)`는 `days` 파라미터를 받지만 함수 본문 어디서도 사용하지 않는다 — 재귀 CTE는 `event_event` 엣지를 corp_code 접두사로만 필터링하고 시간 윈도우는 적용하지 않는다. Q1/Q3/Q5는 모두 `days`를 cutoff로 사용하므로 일관성 위반이고, 호출자(`tests/graph/test_canonical_queries.py:65`이 `days=365`로 호출)는 시간 제한이 적용된다고 오해할 수 있다. 실제로는 corp_code 전체 history가 반환된다.
**Fix:** event_event 엣지 자체는 시간 정보를 가지지 않으므로(synth event_id의 ISO timestamp suffix에만 존재) 두 가지 방안 중 하나:
```python
# Option A: 시그니처에서 days를 제거하고 README도 갱신
def q2_catalyst_chain(ticker: str) -> list[dict[str, Any]]:
    ...

# Option B: dst_id의 ISO timestamp로 cutoff 적용 (LIKE 또는 split)
# WHERE edge_type = 'event_event'
#   AND src_id LIKE :prefix
#   AND substring(src_id from '\d{4}-\d{2}-\d{2}T') >= :cutoff_iso
```
README parity test는 시그니처 비교까지 하지 않으므로 Option A가 가장 단순.

### WR-03: 엔티티 재시드 경로의 connect() 실패는 suppress 밖

**File:** `src/ingest/worker.py:165-174`
**Issue:** Bug D-1 fix 주석은 "best-effort: never fail a document ingest on an entity seeding hiccup"이라고 명시한다. 그러나 다음 구조에서 `engine.connect()`/내부 `conn.execute()`가 실패하면 예외가 그대로 전파되어 doc은 이미 commit된 후 worker가 죽는다:
```python
if canonical_name is None:
    with engine.connect() as conn:          # ← 여기서 OperationalError 발생 시
        existing_name = conn.execute(...)   #   suppress 밖이라 ingest_run loop의
                                            #   per-doc except에서만 잡힘 (다음 doc은
                                            #   계속되지만 W17 같이 single-doc인 경우
                                            #   엣지 단계로 못 넘어가는 우려는 약함).
with contextlib.suppress(Exception):
    upsert_entity(...)
```
실제 운영 영향은 작지만 (per-doc try/except가 위에서 잡음) 주석의 "best-effort" 의도와 코드 위치가 어긋난다.
**Fix:**
```python
if corp_code:
    with contextlib.suppress(Exception):  # 전체 블록을 suppress로 감싸기
        canonical_name = fm_company_name
        if canonical_name is None:
            with engine.connect() as conn:
                existing_name = conn.execute(
                    sa.text("SELECT canonical_name FROM entities WHERE corp_code = :cc"),
                    {"cc": corp_code},
                ).scalar()
            canonical_name = existing_name or f"corp_{corp_code}"
        upsert_entity(engine, corp_code, canonical_name, fm_ticker)
```

## Info

### IN-01: `mentions_ticker` 중복 emit으로 인한 skipped_conflict 카운터 인플레

**File:** `src/ingest/edges.py:152-179`
**Issue:** DART 문서가 ProvenanceBlock.tickers (e.g. ["005930"])를 갖고 동시에 corp_code → entities.current_ticker 가 같은 "005930"을 반환하면 같은 엣지로 두 번 `_emit` 호출. ON CONFLICT로 안전하게 dedupe되지만 두 번째 호출은 `counters["skipped_conflict"]`를 증가시켜 첫 실행에서도 conflict 카운터가 0이 아닌 것으로 보임. 관측 데이터 해석을 흐리게 한다.
**Fix:** doc 단위 로컬 set으로 중복 endpoint를 미리 차단:
```python
emitted = set()
for tref in prov_tickers:
    ticker = getattr(tref, "ticker", None)
    if ticker and _TICKER_RE.match(ticker) and ticker not in emitted:
        _emit(conn, "document", r["id"], "ticker", ticker, "mentions_ticker", counters)
        emitted.add(ticker)
if r["source"] == "dart" and r["corp_code"]:
    t = ...
    if t and _TICKER_RE.match(t) and t not in emitted:
        _emit(...)
```

### IN-02: `_derive_event_event`는 인접 쌍만 처리 — "sliding window"라는 주석과 차이

**File:** `src/ingest/edges.py:281-337`
**Issue:** docstring과 주석은 "90-day sliding window"라 적혀 있지만 실제 구현은 인접 페어(`zip(events[:-1], events[1:])`)만 본다. 같은 corp_code의 docA(t=0), docB(t=10), docC(t=70)에서 docA↔docC (70일 < 90일)은 엣지 생성되지 않음. 의도된 설계(체인 only, 가지 X)일 가능성 높지만 주석이 sliding window라 오해 소지.
**Fix:** docstring 첫 줄을 다음으로 갱신:
```
"""Same-corp_code temporal precedence chain (adjacent pairs only).

For each corp_code, sort docs by first_seen_at and emit one event_event edge
between each adjacent pair where 0 < delta_days <= 90. Non-adjacent pairs
within the 90-day window are NOT connected by design (chain, not clique).
"""
```

### IN-03: snapshot.py의 dual-import 패턴은 fragile

**File:** `src/graph/snapshot.py:78-81`
**Issue:** `try: from src.graph.window ... except ModuleNotFoundError: from graph.window` — 두 가지 sys.path 환경을 모두 지원하기 위함이나 Python 패키지 구조의 정상화로 해결할 문제. 한 곳에 합리적인 import path를 정하고 `pyproject.toml`/conftest의 sys.path 설정으로 통일하는 것이 권장.
**Fix:** 프로젝트 전체가 `src/`-layout이라면 `from graph.window import build_staging`만 남기고 sys.path를 통일. 테스트는 `pyproject.toml`의 `[tool.pytest.ini_options]`에 `pythonpath = ["src"]`로 해결됨.

### IN-04: `worker.py:226` 중복 키 lookup

**File:** `src/ingest/worker.py:226`
**Issue:** `doc_id = result.get("document_id") or result.get("doc_id")` — `process_document`는 항상 두 키 모두 동일 값으로 반환(line 188-191). `doc_id` 한 번만 읽으면 충분.
**Fix:**
```python
doc_id = result.get("doc_id")  # process_document always returns both keys
if doc_id:
    committed_doc_ids.append(doc_id)
```

### IN-05: snapshot.py의 `community_labels` 라벨링이 placeholder

**File:** `src/graph/snapshot.py:125`
**Issue:** `labels = {cid: f"Community {cid}" for cid in communities}` — 사람이 읽기 어려운 generic 라벨. graphify가 자체 community 라벨링 API를 제공한다면 그것을 사용하거나, 적어도 구성원 수가 가장 많은 노드 이름 등 의미 있는 라벨로 대체하면 GRAPH_REPORT.md 가독성이 올라간다. 현재는 contract만 충족.
**Fix:** Phase 9 follow-up 태그로 두거나, top-degree node label을 가져오는 한 줄 추가:
```python
labels = {
    cid: f"{members[0] if members else cid}" for cid, members in communities.items()
}
```

---

_Reviewed: 2026-05-05T16:23:57Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
