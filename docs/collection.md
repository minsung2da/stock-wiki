# 반복 수집

`collect all`은 실행할 때마다 `dart,krx,news,macro,fundamentals`를 모두 실행합니다.
종목 범위는 `notes/private/portfolio.md`의 보유 종목과 관심 종목 합집합입니다.
전체 시장의 모든 종목을 의미하지 않습니다. `--sources`는 실패한 수집원 등을
선택해서 재실행할 때만 사용하는 명시적 범위 축소 옵션입니다.

| 수집원 | 대상과 저장 항목 | 날짜 기준 |
|---|---|---|
| DART | 종목의 기업코드를 중복 제거하여 A/B 공시 메타데이터와 전체 본문 저장 | 지정일부터 공시 조회, 기업당 기존 상한 100건 |
| KRX | OHLCV·거래대금·투자자별 순매수·공매도 | 지정일 하루, 휴장일은 빈 결과 가능 |
| 뉴스 | 한경·이데일리 RSS의 포트폴리오 기업 관련 기사, 본문 첫 두 문단 | 지정일 KST 00:00 이상 다음 날 00:00 미만 |
| 매크로 | 설정된 ECOS/FRED 지표 전체 | 기존 수집원의 최근 365일 조회 유지 |
| fundamentals | PER·PBR·EPS·BPS·DIV·DPS 및 DART 기반 ROE | 지정일 하루 |

DIV는 `dividend_yield`에 백분율 그대로 저장합니다(2.1 = 2.1%).
DPS는 `dps`에 주당 원화로 저장합니다. 결측/NaN은 NULL, 0은 0입니다.
ROE 조회 실패 시 이전 ROE를 보존하며, 신규 행에서는 NULL일 수 있습니다.
이번 추가는 pykrx 반환 항목의 누락을 보완하며, DART의 모든 재무제표 항목을
새 테이블에 적재하는 변경은 포함하지 않습니다.

뉴스는 매번 RSS를 다시 조회합니다. 날짜가 없거나 당일이 아닌 기사는 본문 요청 전에
제외하며, `--max-per-feed`(기본 100)는 날짜가 일치하는 기사에 적용합니다.
과거 날짜 재실행은 RSS에 아직 남아 있는 기사만 대상으로 합니다.
RSS에서 이미 사라진 기사까지 복원하는 과거 뉴스 아카이브 수집은 아닙니다.

## 실행 준비와 명령

Postgres와 `.env`의 `DATABASE_URL`, 수집원 API 키, 포트폴리오 및 기업/별칭 seed가
준비되어 있어야 합니다. 먼저 기존 DB에 추가 컬럼 마이그레이션을 적용합니다.

```powershell
Set-Location -LiteralPath 'C:\Users\minsu\workspace\stock'
& 'C:\Users\minsu\workspace\stock\.venv\Scripts\python.exe' -m alembic -c src/db/alembic.ini upgrade head
& 'C:\Users\minsu\workspace\stock\.venv\Scripts\python.exe' -m cli collect all
# 특정 날짜: 뉴스/KRX/fundamentals는 해당 하루, DART는 해당일부터 조회
& 'C:\Users\minsu\workspace\stock\.venv\Scripts\python.exe' -m cli collect all --since=2026-09-23
# 특정 수집원만 재실행
& 'C:\Users\minsu\workspace\stock\.venv\Scripts\python.exe' -m cli collect all --sources=news,fundamentals
```

주기 실행은 위 기본 명령을 작업 디렉터리 `C:\Users\minsu\workspace\stock`에서
반복 호출하도록 구성하면 됩니다. 실행 주기가 지정되지 않아 스케줄러는 등록하지 않았습니다.
동일 시점의 중복 실행 대신 앞 실행 완료 후 다음 실행을 시작하도록 설정합니다.
매 실행 시작 때 KST 날짜를 한 번 정해 날짜 기반 수집원에 공유합니다.

동일 키/내용은 기존 UPSERT로 중복 저장하지 않고, 변경된 값은 갱신합니다.
한 기업 또는 수집원 실패 후에도 다른 수집원을 계속 실행합니다.
기업코드 미해결은 실패로 보고되므로 먼저 기업 seed를 보완해야 합니다.
종료 코드는 정상 0, 부분/전체 실패 1, 잘못된 수집원·날짜 인자 2입니다.
일괄 결과 JSON은 stderr로 출력하며 `collection_date`, 수집원별 상태,
`inserted`, `updated`, `skipped`, `failed`를 확인할 수 있습니다.
`docs_processed`는 inserted + updated + skipped이므로 필터 제외 건수도 포함합니다.

KIND 위험 이벤트 수집 코드와 CLI 명령은 제거했습니다. 기존 `events` 이력과
스키마, 기존 거래 안전장치는 보존합니다.
