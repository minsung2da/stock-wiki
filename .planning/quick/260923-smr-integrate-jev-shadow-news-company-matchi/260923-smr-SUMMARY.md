---
task: 260923-smr
status: complete
completed: 2026-09-23
implementation_commit: 4cc743a
---

# JEV shadow integration

Implemented candidate-based news-company classification and individual claim/citation review using TypeSafe SDK 0.7.1, Jev 1.13.0. Local configuration enables shadow mode; default/example configuration remains off. Existing news associations and card decisions are preserved.

## Delivered

- Shared orchestration adapter validates finite confidence/probabilities and exact question choices, caches completed identical inputs, bounds input size and API timeout/retries, and records sanitized failures.
- Migration 0011 creates separate append-only review audit storage; applied to local PostgreSQL.
- Standard news collection reviews alias-matched candidates before persistence. Full analysis reviews the saved card with its actual bundle; lightweight refresh remains model-free.
- Historical replay CLI resolves exact dated news/filing references. Missing numeric snapshots remain unavailable rather than being reconstructed from current data.
- DB explorer exposes JEV review records, inputs, answers, request IDs, usage and errors.
- Usage and limitations documented in docs/jev-review.md.

## Verification

- Related automated suite: 157 passed, 2 existing warnings; includes isolated PostgreSQL, failure/cache handling, source isolation, temporal cutoffs, full/refresh hooks, import guard and explorer APIs.
- Ruff passed. Adapter/store strict mypy passed; card/CLI module mypy passed with follow-imports=skip (not a full-project type check).
- uv lock --check and wheel build passed. Wheel includes orchestration, cards, briefing and migration 0011.
- Live September news: 25 completed; 38 candidate judgments: primary 20, mentioned 13, unrelated 4, insufficient 1. Eighteen articles require review. One initial malformed response succeeded on replay; initial failure retained.
- Existing Samsung card card_005930_2026-07-06_10d7c16a: 15 citation pairs; 9 API results (supports 3, unsupported 6), 6 missing_source records for absent historical numeric snapshots. Fourteen pairs require review.
- Live audit rows: 41 including initial failure. Explorer search/detail HTTP 200.
- Before/after hashes of news and cards identical. These judgments are not human-validated accuracy measurements.

## Plan adjustments

News and card review modules live under src/orchestration/ instead of the proposed collector/analysis locations, keeping API handling behind the orchestration boundary. Added explicit replay commands to validate existing records without rerunning Claude analysis, and included cards/briefing in wheel packaging because the CLI imports these modules.

API credentials, live result files, historical hash snapshots and the built wheel remain in ignored local paths. Existing unrelated workspace changes were preserved. No automatic filtering, card rewriting or trading behavior was introduced.
