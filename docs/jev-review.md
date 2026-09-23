# JEV 뉴스 기업 매칭·카드 근거 검토

2026-09-23 적용. 현재 로컬 설정은 `JEV_MODE=shadow`입니다.
JEV 판정을 실제 API로 받아 DB에 기록하며, 기존 뉴스의 종목 연결과 카드의 판단·확신도는 유지합니다.
외부 API는 뉴스 발췌문·기업 후보 또는 카드 주장·인용 근거를 받습니다. API 키는 `.env`에서만 읽습니다.

## 연결된 처리

### 뉴스

일반 `collect news` 및 `collect all` 실행에서 기존 별칭 매칭 후 후보 기업마다 다음 중 하나를 평가합니다.

| 값 | 의미 |
|---|---|
| `primary` | 해당 기업이 기사의 주요 대상 |
| `mentioned` | 해당 기업이 언급되지만 주된 대상은 아님 |
| `unrelated` | 별칭의 우연한 일치 등으로 기업과 무관 |
| `insufficient` | 발췌문만으로 기업·관련성을 확정하기 어려움 |

기존 후보 밖의 기업을 새로 발굴하는 기능은 아닙니다. 후보가 없으면 API를 호출하지 않습니다.
여러 기업 후보는 한 요청의 독립 질문으로 평가합니다. 오류가 나도 기존 기사 저장은 계속합니다.

### 카드

`analyze_ticker`의 전체 분석 경로에서 숫자 checksum과 카드 저장 후 JEV 검토가 실행됩니다.
주장과 인용 한 쌍마다 `supports / contradicts / unsupported / insufficient`를 평가합니다.
다른 인용의 내용을 섞지 않고, 사용된 분석 묶음의 근거를 전달합니다.
여러 인용이 함께 있어야 성립하는 주장은 개별 인용 기준으로 `unsupported`가 나올 수 있습니다.
이 결과만으로 카드가 잘못됐다고 확정하거나 삭제하지 않습니다.

기존의 경량 refresh 경로는 모델을 호출하지 않는 계약을 유지합니다.
저장된 카드의 재검토 명령은 DB의 해당 공시·뉴스 원문을 읽고 카드 기준일 이후 자료는 제외합니다.
원래 수치 입력 스냅샷이 없는 과거 카드의 OHLCV·수급·동종업계 비교 인용은 현재 값으로
대체하지 않고 `missing_source`로 남깁니다. 현재 DB 원문은 과거 입력의 완전한 재현을 보장하지 않습니다.

## 결과와 오류

- `Choice.confidence <= 0.8`이면 검토가 필요합니다. 임계값은 초기 운영값이며 정확도 검증값이 아닙니다.
- `contradicts / unsupported / insufficient`는 confidence와 무관하게 검토 대상으로 표시합니다.
- confidence는 JEV 판정의 불확실성 지표이며 투자 수익 확률이나 카드의 conviction이 아닙니다.
- 키 누락·API 오류·잘못된 응답·근거 누락은 오류 audit로 기록하며 확인 성공으로 취급하지 않습니다.
- 입력·질문·모델·프롬프트 버전·임계값이 같은 완료 결과는 재사용합니다. 오류는 재사용하지 않습니다.
- 입력이 100,000자를 넘으면 근거를 조용히 자르지 않고 `input_too_large`로 기록합니다.
- API timeout은 30초, 재시도는 최대 1회입니다. DB 기록에 실패하면 로그와 반환값에 오류를 남깁니다.

## 설정 및 실행

필요한 추가 패키지는 `typesafe-sdk==0.7.1`이며 `jev` dependency group에 고정했습니다.
기존 DB·collector 의존성과 함께 설치하고 migration `0011`을 적용합니다.

```powershell
uv sync --group collectors --group db --group mcp --group jev
.\.venv\Scripts\python.exe -m alembic -c src/db/alembic.ini upgrade head
```

`.env`에는 `TYPESAFE_API_KEY`, `TYPESAFE_DEFAULT_MODEL=jev-1.13.0`, `JEV_MODE=shadow`,
`JEV_CONFIDENCE_THRESHOLD=0.8`을 설정합니다. 배포 기본값과 예제는 `off`이며, 현재 로컬은 활성화했습니다.
`JEV_MODE=off`이면 JEV API와 감사 DB 쓰기를 건너뜁니다. 기존 Claude 분석 백엔드는 그대로입니다.

저장된 자료를 재검토하려면 프로젝트 루트에서 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m cli review news --since 2026-09-01 --until 2026-09-23 --limit 25
.\.venv\Scripts\python.exe -m cli review card --card-id <저장된-card_id>
```

뉴스 재검토는 현재 포트폴리오 범위이며 `--limit` 기본값은 25건입니다. 허용 범위는 1~500입니다.
종료 코드 0은 실행 오류 없음(저신뢰 검토 필요 결과는 포함 가능), 1은 오류 또는 근거 누락 존재,
2는 잘못된 기간·한도 또는 찾을 수 없는 카드입니다. API를 호출하는 작업이므로 재실행 시 캐시 건수를 확인합니다.

[DB 검색 화면](http://127.0.0.1:8766/)의 **JEV 검토 기록**에서 결과를 확인합니다.
검색어 `news_company` 또는 `card_evidence`로 분류하고 상세 보기에서 입력 근거·질문·판정·confidence·
API request ID·사용량·오류 코드를 확인할 수 있습니다. 기준 날짜는 원문 날짜가 아니라 검토 실행일입니다.

## 실제 적용 검증

- 9월 뉴스 25건 모두 판정 완료: 기업 후보 38개에 대해 primary 20, mentioned 13, unrelated 4,
  insufficient 1. 검토 필요 기사는 18건입니다. 원래 기사·종목 연결은 유지했습니다.
- 처음 응답 검증 오류 1건은 재실행으로 해결됐으며, 초기 오류 이력은 보존했습니다.
- 기존 삼성전자 카드의 인용 15쌍: 원문 확인 가능한 9쌍은 API 검토 완료(supports 3, unsupported 6),
  수치 스냅샷이 없는 6쌍은 missing_source. 총 14쌍이 검토 필요로 표시됐습니다.
- 위 건수는 실제 API 판정 분포이며 사람의 정답 평가를 통한 정확도 수치는 아닙니다.
- 뉴스·카드 검토 전후 해시 일치, 원본 변경 없음. 신규 audit 41건(초기 오류 포함)을 확인했습니다.
- 관련 테스트 157개 통과: 격리 PostgreSQL, malformed 응답·캐시·오류·근거 시점·인용 분리·
  원본 보존·전체 분석 후 hook·refresh 무호출·검색 API 포함.

설계 근거: [TypeSafe Python SDK](https://docs.typesafe.ai/sdk/python/usage),
[인용 검토 패턴](https://docs.typesafe.ai/cookbooks/citation_check),
[confidence 설명](https://docs.typesafe.ai/confidence).
