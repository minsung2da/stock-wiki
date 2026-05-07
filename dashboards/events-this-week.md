---
title: Events This Week
type: dashboard
---

> 이번 주(KST 월~일) DART 공시·뉴스·KIND 이벤트 집계.
> 정렬 우선순위 (D-09): 공시 > 거래정지 > 실적 > 뉴스 → 날짜 desc

```dataview
TABLE WITHOUT ID
  provenance.date AS "날짜",
  row["_derived"].tickers AS "티커",
  row["_derived"].event_type AS "이벤트",
  provenance.title AS "제목",
  provenance.source AS "소스",
  provenance.url AS "링크"
FROM "vault/raw/dart" OR "vault/raw/news" OR "vault/raw/kind"
WHERE provenance.date >= date(today) - dur(7 days)
SORT
  choice(row["_derived"].event_type = "공시", 1,
    choice(row["_derived"].event_type = "거래정지", 2,
      choice(row["_derived"].event_type = "실적", 3, 4))) ASC,
  provenance.date DESC
LIMIT 50
```
