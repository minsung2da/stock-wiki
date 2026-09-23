---
phase: quick
plan: 260923-smr
type: execute
wave: 1
depends_on: []
files_modified:
  - src/orchestration/jev.py
  - src/db/jev_reviews.py
  - src/db/migrations/versions/0011_jev_reviews.py
  - src/collectors/news/__init__.py
  - src/collectors/news/jev_review.py
  - src/analysis/runner.py
  - src/analysis/jev_review.py
  - tests/orchestration/test_jev.py
  - tests/collectors/news/test_jev_review.py
  - tests/analysis/test_jev_review.py
autonomous: true
requirements: [USER-JEV-NEWS-MATCHING, USER-JEV-CARD-EVIDENCE, USER-SHADOW-COMPARISON]
must_haves:
  truths:
    - Jev reviews alias-matched news-company candidates and claim-specific cited evidence in shadow mode.
    - Shadow output does not change saved news associations, card decisions, deterministic numeric checks, or trading behavior.
    - Failures, missing evidence, and low confidence remain visible as audit results requiring review.
  artifacts:
    - path: src/orchestration/jev.py
      provides: Typed bounded Jev review adapter with off/shadow configuration and caching
    - path: src/db/jev_reviews.py
      provides: Separate persistent review audit and result lookup
  key_links:
    - from: src/collectors/news/jev_review.py
      to: src/orchestration/jev.py
      via: review_choices
    - from: src/analysis/jev_review.py
      to: src/orchestration/jev.py
      via: review_choices with claim-specific sources
---

<objective>
Implement the user-authorized TypeSafe/Jev API for bounded news-company matching and decision-card evidence review, initially as persisted shadow comparison. Existing Claude analysis, source checksums, card decisions, and trade controls retain their behavior.
</objective>

<context>
@AGENTS.md
@.planning/research/redesign-2026-05.md
@src/collectors/news/__init__.py
@src/analysis/runner.py

User authorization supersedes the older Max-only restriction solely for these two review tasks. It does not authorize a replacement Bull/Bear/Judge backend. Current news candidates come from matcher.match_tickers_in_text(title + body, alias_map); current full analysis saves a checksummed DecisionCard after Claude debate. Preserve lightweight refresh semantics: do not trigger fresh model reviews on the refresh path.

Agreed adapter contract: review_choices(engine, *, task, subject_id, state, questions, backend=None) -> dict, implemented in src/orchestration/jev.py. Persistence belongs to src/db/jev_reviews.py and migration 0011. Root owns card integration, CLI/explorer/config; adapter executor owns adapter/persistence; news executor owns news integration. They must preserve each other's edits. Record any final filename changes in SUMMARY.
</context>

<tasks>
<task type="auto" tdd="true">
  <name>Task 1: Implement bounded adapter and separate audit storage</name>
  <files>src/orchestration/jev.py, src/db/jev_reviews.py, src/db/migrations/versions/0011_jev_reviews.py, tests/orchestration/test_jev.py</files>
  <behavior>Off mode makes no network call. Shadow mode validates returned question IDs and allowed choices. Repeated identical state/model/prompt uses the cached review. Changed source content or prompt/model invalidates the cache. Timeout, malformed response, and low confidence cannot become verified results.</behavior>
  <action>Define the agreed adapter, injectable fake backend, JEV_MODE off default and shadow enabled only in local configuration. Use the verified installed API contract. Add an additive 0011 audit table with task, subject identity, input fingerprint, mode, model, prompt version, structured decisions, status, error metadata, and timestamps. Hash canonical task/questions/state plus model and prompt version. Persist successful, uncertain, and failed attempts distinctly; do not cache failure as success. Bound requests by timeout and payload size, validate IDs/choices/confidence, redact credentials from errors, and make storage failure visible without altering primary saved data. Never store API keys or print .env contents.</action>
  <verify><automated>.\.venv\Scripts\python.exe -m pytest tests/orchestration/test_jev.py -q</automated></verify>
  <done>Fake-backed behavior and isolated-DB audit persistence pass; off mode is backward compatible and review cache has complete identity.</done>
</task>
<task type="auto" tdd="true">
  <name>Task 2: Connect news and cited-claim reviews without mutating primary decisions</name>
  <files>src/collectors/news/__init__.py, src/collectors/news/jev_review.py, src/analysis/runner.py, src/analysis/jev_review.py, tests/collectors/news/test_jev_review.py, tests/analysis/test_jev_review.py</files>
  <behavior>Each alias candidate receives primary/mentioned/unrelated/insufficient classification. Card claims receive supports/contradicts/unsupported using only their resolvable cited sources. Missing references and low confidence require manual review. Shadow failures leave news tickers, cards, checksums, and trading state unchanged.</behavior>
  <action>News integration submits existing candidates with company identity and the already licensed title/body scope, then records comparison after primary storage; it cannot add arbitrary tickers or rewrite matches. Card integration resolves each claim's evidence_refs independently into source text or typed facts. Never concatenate uncited bodies into a claim review, and explicitly flag missing, ambiguous, unsupported, or unavailable reference kinds. Preserve numeric checksum code and Claude backend. Run review after a full card save without rerunning Bull/Bear/Judge; lightweight refresh must remain free of new model calls. Ensure per-item review errors do not abort collection or undo saved cards. Expose review status through the existing CLI/explorer mechanisms owned by root, documenting their exact edited paths in SUMMARY.</action>
  <verify><automated>.\.venv\Scripts\python.exe -m pytest tests/collectors/news/test_jev_review.py tests/analysis/test_jev_review.py -q</automated></verify>
  <done>Both production paths use the adapter, source-reference isolation is tested, and primary behavior stays identical across off/shadow/error cases.</done>
</task>
<task type="auto">
  <name>Task 3: Validate persisted shadow comparison on stored data</name>
  <files>.planning/quick/260923-smr-integrate-jev-shadow-news-company-matchi/260923-smr-SUMMARY.md</files>
  <action>Run relevant existing collector/analysis regressions and additive migration checks. Apply migration to the configured DB only after isolated validation. Enable local shadow configuration using the already authorized API key without committing secrets. Review 25 existing stored news records and available existing decision cards through the same review functions; do not generate new debates or execute trades. Query persisted audit counts, classification distributions, disagreements, uncertainty/errors, latency and cache behavior. Compare before/after primary records to prove no mutation. Report actual sample counts and failures, not an accuracy claim without human labels. Record any unavoidable evidence gaps and the concrete operator query/view for results.</action>
  <verify><automated>Execute the stored-data review command implemented by root, then query audit task/status counts and assert sampled primary news associations and card payload fingerprints match their pre-run values.</automated></verify>
  <done>Live bounded reviews are persisted and inspectable; primary data invariance and fake-backed regressions pass; the summary distinguishes completed, failed, and manual-review samples.</done>
</task>
</tasks>

<threat_model>
| Boundary | Threat | Mitigation |
|---|---|---|
| Untrusted news/evidence to model | Prompt injection or unsupported attribution | Treat source text as data; constrained choices and IDs; citation-specific input; shadow only |
| Model output to DB | Invalid IDs, false verification, stale reuse | Typed validation, confidence/manual-review status, canonical source/model/prompt fingerprint |
| Local credentials to remote API | Key disclosure | Environment-only credentials, sanitized errors, no secret commits |
| Optional review to collector/analysis | Availability regression | Timeouts, visible failures, separately persisted audit, unchanged primary decisions |
</threat_model>

<verification>
Fake-backed tests, isolated additive migration validation, relevant existing regressions, and bounded real API review of stored samples. Exact dependencies must be verified against the official package source before any install; use the existing supported environment when possible. Do not weaken unrelated import guards or change trading gates.
</verification>

<success_criteria>
News-company and cited-card evidence reviews execute in shadow mode, are separately persisted and visible, and preserve existing primary outputs. No result lacking sufficient cited evidence is silently treated as verified. Stored-sample live results are reported with concrete counts and limitations.
</success_criteria>

<output>
Write 260923-smr-SUMMARY.md and update STATE.md quick-task history after implementation. Stage only this task's nonsecret files, preserve other workers' changes, and do not modify ROADMAP scope.
</output>
