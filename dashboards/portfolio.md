---
title: Portfolio
type: dashboard
---

> 가격 기준일: ` = link("dashboards/_data/prices.md").file.frontmatter.as_of ` (자동 갱신, 전영업일 종가 기준)
>
> _주의: Dataview plugin 미설치 시 아래 표는 raw 코드블록으로 보입니다. Plugin 설치 후 새로고침하세요._

## Holdings × 평가액

```dataview
TABLE WITHOUT ID
  ticker AS "티커",
  name AS "종목명",
  shares AS "수량",
  avg_cost AS "평단",
  default(this.prices[ticker], "—") AS "현재가",
  shares * default(this.prices[ticker], 0) AS "평가액"
FROM "notes/private/portfolio.md"
FLATTEN file.lists AS holding
WHERE holding.section = "Holdings"
```

> NOTE: 위 쿼리가 빈 결과면 `notes/private/portfolio.md` 의 holdings 표를 frontmatter list로도 미러링하거나 `dashboards/_data/portfolio_holdings.md` derived 파일이 필요할 수 있습니다 (RESEARCH Pitfall 3 / Open Question 4 — UAT에서 검증).

## 보유 종목 최근 7일 이벤트

```dataview
TABLE provenance.date AS "날짜", _derived.event_type AS "이벤트", file.link AS "문서"
FROM "vault/raw"
WHERE provenance.date >= date(today) - dur(7 days)
SORT provenance.date DESC
LIMIT 20
```
