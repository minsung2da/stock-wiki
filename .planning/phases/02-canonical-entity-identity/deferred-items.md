
## [02-03] Pre-existing: test_env_file_not_committed false positive

- **Issue:** `tests/test_secrets.py::test_env_file_not_committed` asserts `.env` must not exist at project root, even when gitignored.
- **Reality:** Plan 02-02 created a local gitignored `.env` (verified via `git check-ignore`) for live docker-compose Postgres pushes. This is an intentional dev setup, not a leak.
- **Status:** Pre-existing (test pre-dates 02-02). Out of scope for 02-03 — the test needs to be relaxed to `assert .env is gitignored` rather than "must not exist", but that's a Plan 01 cleanup task.
- **Impact on 02-03:** None — all 12 new tests (9 resolve + 3 supersedes) pass; all 17 Plan 02-02 tests still pass; 58 tests green, 1 pre-existing fail orthogonal to this plan.
