---
title: Watchlist
type: dashboard
---

> SoT: `notes/private/portfolio.md` 의 `## Watchlist` 섹션. 별도 파일 없음 (D-07).

```dataview
TABLE WITHOUT ID
  ticker AS "티커",
  name AS "종목명",
  reason AS "관심 이유"
FROM "notes/private/portfolio.md"
FLATTEN file.lists AS w
WHERE w.section = "Watchlist"
```
