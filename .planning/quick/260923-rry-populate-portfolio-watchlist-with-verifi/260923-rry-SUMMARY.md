---
phase: quick
plan: 260923-rry
subsystem: collection-scope
tags: [portfolio, wics, market-cap, private-config]
requires: [existing-portfolio-loader]
provides: [198-company-sector-watchlist]
affects: [collector-scope]
tech-stack:
  added: []
  patterns: [dated-public-source-snapshot]
key-files:
  created:
    - notes/private/portfolio.md
    - notes/private/portfolio-source-20260923.json
  modified: []
key-decisions:
  - Use WICS 10 broad sectors and full listed-share market capitalization.
  - Keep actual holdings empty and store selected companies only in watchlist.
  - Preserve 18 utilities rather than invent two missing constituents.
  - Keep portfolio and source snapshot gitignored.
completed: 2026-09-23
---

# Quick Plan 260923-rry Summary

WICS 10개 대분류의 시가총액 상위 기업 198개를 기업명·순위·시장·시가총액 근거와 함께 수집용 portfolio에 등록했습니다.

## 완료 작업

1. 공개 원본 스냅샷 검증: NAVER KOSPI 2,484행/25페이지, KOSDAQ 1,821행/19페이지와 WICS 2,459개 구성종목을 모두 매핑했습니다. 누락은 0개입니다.
2. `notes/private/portfolio.md` 생성: `holdings: []`, 6자리 문자열 `watchlist` 198개, 10개 섹터별 순위표를 작성했습니다.

## 기준과 출처

- WICS 분류 기준일: 2026-09-23 KST, 각 원본 `TRD_DT`를 검증했습니다.
- 원본 조회 완료: 2026-09-23T20:02:41.700096+09:00.
- 순위는 NAVER `marketValue` 전체 시가총액(억원)의 내림차순, 동률은 종목코드 오름차순입니다. WiseIndex의 지수 산출용 유동 시가총액 `MKT_VAL`은 사용하지 않았습니다.
- 시가총액은 조회 시점 최신 시세이며 NXT 장후 시세 등이 반영될 수 있습니다. KRX 정규장 종가만을 사용한 순위라고 주장하지 않습니다.
- 섹터별 20개, 유틸리티는 전체 구성종목이 18개여서 18개입니다. 총 198개이며 중복은 없습니다.
- 각 표의 WiseIndex 원본 링크와 NAVER 시장별 출처 링크, 종목별 시세 시각을 포함한 로컬 JSON 스냅샷을 보존했습니다.

## 검증 결과

- 운영 코드 `Portfolio.load(Path('.'))` 성공: holdings 0개, watchlist 198개, scope 198개.
- 모든 선정 순위가 원본 전체 구성종목을 전체 시가총액으로 정렬한 상위 `min(20, count)`와 일치합니다.
- 모든 표 종목코드와 YAML watchlist의 순서·값이 정확히 일치합니다.
- 6자리 영문 대문자·숫자 종목코드, 시가총액 정수·비음수, Unicode 손상문자 부재를 검증했습니다.
- `git check-ignore`로 portfolio와 스냅샷 두 파일의 제외를 확인했습니다. 검증 시 staged 파일은 없었습니다.

## 운영상 남은 사항

부모 에이전트의 읽기 전용 DB 확인에서 선정 198개 중 130개는 기업 매핑이 등록되어 있고 68개는 미등록입니다. 전체 수집을 위해 별도 매핑 등록이 필요합니다. 이번 작업에서 DB 쓰기, 실제 API 수집 실행, 거래 실행은 하지 않았습니다. 종목 목록은 고정 스냅샷이며 자동 순위 갱신 기능을 추가하지 않았습니다.

## Deviations from Plan

없음. 20개 미만 분류의 전체 수록과 개인 파일의 Git 제외는 계획대로 수행했습니다. Task 1의 원본 조회는 부모 에이전트가 수행했고 executor는 기존 스냅샷을 재검증했습니다. 개인 파일은 커밋하지 않으며 계획·상태·요약 메타데이터 커밋은 부모 에이전트가 담당합니다.

## Self-Check: PASSED

portfolio와 원본 스냅샷의 존재, 운영 loader 읽기, 원본 순위 대비 검증, 198개 중복 제거, 10개 섹터 표, 개인 파일 Git 제외를 확인했습니다.
