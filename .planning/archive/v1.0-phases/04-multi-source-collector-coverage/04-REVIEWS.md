---
phase: 4
reviewers: [codex]
reviewed_at: 2026-04-18
plans_reviewed: [04-01-PLAN.md, 04-02-PLAN.md, 04-03-PLAN.md, 04-04-PLAN.md, 04-05-PLAN.md, 04-06-PLAN.md]
---

# Cross-AI Plan Review — Phase 4

## Codex Review

**Skill Use**

`using-superpowers` was applied to check workflow requirements. `brainstorming` was reviewed and not applied further because this turn is a plan review, not new feature/design creation.

## 04-01-PLAN.md

### 1. Summary
Solid prerequisite plan. It correctly centralizes shared dependencies before collector work starts: portfolio scope loading, alias resolution, heartbeat extensibility, frontmatter schema extension, and test scaffolding.

### 2. Strengths
- Dependency ordering is correct; Wave 2 plans do depend on these interfaces.
- Good focus on additive changes only, which reduces regression risk against Phase 3.
- Security controls are explicit where they matter: portfolio validation, SQL bind params, heartbeat extra-key restrictions.
- Tests cover the important contract points downstream plans rely on.

### 3. Concerns
- **MEDIUM**: `files_modified` includes existing shared files (`src/shared/frontmatter.py`, `src/ingest/heartbeat.py`) that affect prior phases, but the plan’s verification does not explicitly require running any existing Phase 3 tests beyond import guard. This is the main regression gap.
- **MEDIUM**: `tickers: list[dict]` and `observations: list[dict]` are weakly typed. Acceptable for speed, but this makes malformed frontmatter easier to write and harder to validate later.
- **LOW**: `seed_name_aliases.py` is created here, but nothing in later plans explicitly guarantees it will be run before `collect_news`. That is an operational precondition, not yet encoded into the plan set.

### 4. Suggestions
- Add a regression gate: run the Phase 3 collector/frontmatter/heartbeat tests after Task 3, not just import guard.
- Consider typed nested models for `TickerRef` and `Observation` instead of raw `dict`.
- Make alias seeding operationally explicit: either a CLI entrypoint, a migration step, or a documented pre-run command.

### 5. Overall Risk Assessment
**Low to Medium.** Good foundation, but shared-schema regressions are possible unless existing tests are included.

---

## 04-02-PLAN.md

### 1. Summary
Reasonable KRX collector plan with good module boundaries and idempotency coverage. It should satisfy `COLL-02` if the underlying pykrx assumptions hold.

### 2. Strengths
- Scope is tight and aligned with success criterion #1.
- Writer and orchestrator are separated cleanly.
- Holiday behavior, per-ticker isolation, and idempotent rerun behavior are explicitly tested.
- Path validation and trust-level handling are correct.

### 3. Concerns
- **HIGH**: The plan says frontmatter contains `corp_code`, but `collect_krx` resolves entities by ticker and tolerates missing entities. For watchlist tickers not yet seeded in `entities`, output may lack `corp_code`, which weakens downstream joins and may violate expectations.
- **MEDIUM**: It treats empty `ohlcv` as holiday globally per ticker, but short-balance emptiness can also be normal due to T+2 lag. The current write path may still render empty short data inconsistently.
- **MEDIUM**: `_read_existing_hash` via regex against raw markdown is fragile when `read_frontmatter` already exists.
- **LOW**: `tabulate` is added purely for markdown rendering; fine, but it introduces an extra runtime dependency for a cosmetic output format.

### 4. Suggestions
- Decide explicitly whether missing entity resolution is allowed for KRX outputs. If yes, say so in plan truth statements.
- Add a test for “OHLCV present, short balance empty” and define expected output.
- Reuse `read_frontmatter` for hash comparison rather than regex scraping.

### 5. Overall Risk Assessment
**Medium.** Likely implementable, but entity completeness and short-balance edge cases are under-specified.

---

## 04-03-PLAN.md

### 1. Summary
Macro plan is mostly sound and correctly recognizes ECOS verification as the critical uncertainty. The Wave-0 checkpoint is the right idea.

### 2. Strengths
- Correctly isolates the riskiest part: ECOS series verification.
- Append-idempotent writer design matches D-07 well.
- Startup-time secret validation is good.
- Empty ECOS response fail-fast is the right decision for placeholder IDs.

### 3. Concerns
- **HIGH**: `autonomous: false` plus a blocking human checkpoint means this plan can stall Phase 4. That is fine operationally, but the dependency impact should be called out more strongly because Phase 06 depends on this being complete.
- **MEDIUM**: `collect_macro` catches `MacroEmptyResultError` into `stats["failed"]` rather than failing the run, while the plan text says “fail-fast.” That is a semantic mismatch.
- **MEDIUM**: `merge_observations` dedups by `date` only, but the requirements said duplicate `(date, value)` should skip. If a source revises a value for the same date, current behavior silently overwrites.
- **MEDIUM**: `load_catalog(path=Path(".planning") / "macro_series.yaml")` uses repo-relative path, not `vault_root` or module-relative resolution. Fine in repo execution, brittle elsewhere.
- **LOW**: `engine` is passed to `collect_macro` but unused.

### 4. Suggestions
- Resolve the “fail-fast” inconsistency: either collector-level error should abort immediately, or plan text should say “record failure and continue.”
- Decide whether same-date revised values should overwrite, error, or append with provenance. Right now it is implicit.
- Make catalog path resolution explicit and stable.
- If `engine` is intentionally unused, remove it from the public signature only if consistency with other collectors is not required.

### 5. Overall Risk Assessment
**Medium to High.** The plan is good structurally, but semantics around fail-fast and observation merging need tightening.

---

## 04-04-PLAN.md

### 1. Summary
This is the most scope-sensitive plan. It covers the right functionality, but the alias-matching design is weaker than the rest of the plan and is the biggest quality risk in the phase.

### 2. Strengths
- Good copyright discipline: two-paragraph cap is explicit and test-backed.
- Correct storage layout and dedup behavior for same-URL vs cross-URL cases.
- Trust handling and scope filtering align well with the context decisions.
- SSRF and path validation are addressed.

### 3. Concerns
- **HIGH**: `match_tickers` is based on regex token extraction from article body and repeated exact DB lookups. This is both recall-poor and potentially noisy. Korean company names often appear with particles, punctuation, shortened forms, market nicknames, or spacing variants, so this will miss a lot.
- **HIGH**: The plan says entity matching uses `resolve_entity_by_alias(name, as_of=published)`, but the implementation sketch does not use article title or any alias inventory pull; it scans tokens heuristically. That is not clearly aligned with D-11/D-12 quality expectations.
- **MEDIUM**: `client.fetch_url_html` uses `trafilatura.fetch_url` for RSS feed fetching too. That couples two different fetch concerns and may be unreliable for XML feeds.
- **MEDIUM**: Feed-level failures are added to `stats["failed"]`, which may make the whole source look partially failed even if most article collection succeeds. Acceptable, but worth being explicit.
- **LOW**: Cross-URL dedup is intentionally not canonicalized, but the plan should state that duplicate docs are an accepted Phase 4 tradeoff.

### 4. Suggestions
- Replace token-extraction matching with a DB-driven alias scan over the article title + body using a preloaded alias map limited to scoped entities.
- Separate feed retrieval from article retrieval. Use `requests` for RSS XML, `trafilatura` only for article extraction.
- Add tests for Korean spacing/punctuation variations and title-only matches.
- Explicitly document that Phase 4 accepts same-article multi-file duplicates across URLs.

### 5. Overall Risk Assessment
**High.** The storage/writer parts are solid, but the matching strategy is likely to underperform and compromise `COLL-03` usefulness.

---

## 04-05-PLAN.md

### 1. Summary
The plan understands the KIND collector is the highest-risk integration. It does a good job isolating probe work, robots compliance, and parser drift detection.

### 2. Strengths
- Correctly treats live URL/selector confirmation as a blocking checkpoint.
- Good compliance posture: robots gate, throttle, identifiable UA.
- Parser drift is handled explicitly with `ParseError` and heartbeat metadata.
- Event typing and path constraints are clear.

### 3. Concerns
- **HIGH**: The plan still carries multiple unresolved assumptions into implementation code, especially KRX MDC response shapes and suspension endpoint code. The placeholders in Task 2/3 are too close to implementation for a genuinely uncertain surface.
- **HIGH**: Scope alignment issue: D-14 says suspension uses DART API supplementally, but the execution plan effectively omits DART-derived suspension entirely and relies on KRX + KIND only.
- **MEDIUM**: `check_robots_txt` uses a broad `path="/disclosureinfo/"`. If robots allow one subpath but disallow another, this may over- or under-block.
- **MEDIUM**: `parse_nfaith_page` tests `if rows is None`, but `soup.select()` returns a list, so malformed layouts may yield `[]` instead of raising. That could silently pass as “no events” unless selector presence is checked differently.
- **MEDIUM**: Event dedup “KRX wins over DART” is mentioned in behavior, but DART ingestion path is not actually implemented in the task actions.
- **LOW**: Rate-limit tests using real sleep can make test suite slower and flaky.

### 4. Suggestions
- Either add the DART supplemental suspension path or explicitly remove it from Phase 4 scope and update the plan/context.
- Make parser failure detection structural: assert the table/container exists before row extraction, not just row count.
- Narrow robots checking to the exact target path once confirmed.
- Decouple response-shape parsing from endpoint fetch so fixture evolution is easier.

### 5. Overall Risk Assessment
**High.** This is the riskiest plan technically and legally/compliance-wise. Good safeguards exist, but implementation assumptions are still too soft.

---

## 04-06-PLAN.md

### 1. Summary
Good orchestration plan. It is appropriately late in the sequence and mostly limited to CLI surface plus isolation behavior.

### 2. Strengths
- Dependency ordering is correct.
- Isolation semantics, exit codes, and JSON stderr reporting are clear.
- Backward compatibility for `stock collect dart` is explicitly protected.
- Tests cover the main control-flow outcomes.

### 3. Concerns
- **MEDIUM**: Success Criterion #5 says heartbeat records per-source status in an orchestrated forced-failure run, but `cmd_collect_all` itself does not write aggregate heartbeat state; it relies entirely on each collector. That is probably fine, but the plan should say this explicitly.
- **MEDIUM**: `_engine()` is created once and shared across all collectors. If one collector poisons engine/session state, later collectors may be affected.
- **LOW**: `collect all` forwards `since` only to `krx/news/kind`, not `macro`; that is intentional, but should be explicit in help text or docs.
- **LOW**: `unknown source -> exit 2` is implemented in command logic, not argparse choices. Acceptable, but slightly weaker than parser-level validation.

### 4. Suggestions
- State explicitly that per-source heartbeat comes from collectors, not from the CLI layer.
- Consider fresh engine acquisition per source if DB state contamination becomes an issue.
- Add one test asserting collectors are still invoked after a prior collector raises before heartbeat write.

### 5. Overall Risk Assessment
**Low to Medium.** This plan is straightforward and mostly bounded by collector correctness.

---

## Cross-Plan Assessment

### Strengths
- Overall decomposition is strong.
- Shared prerequisites are mostly placed correctly in Plan 01.
- The plans consistently preserve Phase 3 collector patterns.
- Test-first discipline is much better than average.

### Main Risks
- **Highest risk:** `04-04` news matching quality.
- **Second highest risk:** `04-05` KIND endpoint/schema uncertainty and partial drift from D-14.
- **Shared regression risk:** `04-01` changes shared schema and heartbeat behavior without enough explicit backward-regression testing.
- **Operational risk:** `04-03`, `04-04`, `04-05` all contain blocking human checkpoints; Phase 4 may stall unless those probes are treated as first-class deliverables.

### Suggestions
- Add a cross-plan “Wave 0 verification bundle” before Wave 2 implementation starts, rather than embedding separate probes inside 03/04/05.
- Tighten the contract for entity availability and alias seeding before any collector work.
- Add a small compatibility suite that reruns Phase 3 DART collector tests after Plan 01 lands.
- Rework news matching from token-heuristic to scoped-alias inventory matching.

## Overall Risk Assessment

**Overall: Medium-High.**

The plan set is well-structured and likely implementable, but Phase goals are only fully met if three weak spots are fixed first:

1. News alias matching quality
2. KIND source/protocol certainty
3. Shared-schema regression coverage after Plan 01

Without those fixes, the phase may “complete” technically while still underdelivering on actual collector usefulness and robustness.

---

## Consensus Summary

Single reviewer (Codex). Consensus reflects Codex's synthesis across the 6 plans.

### Agreed Strengths
- Dependency ordering and Wave structure are correct.
- Phase 3 collector patterns (client/fetcher/writer/__init__) are preserved.
- Test-first discipline is strong; idempotency and Wave-0 checkpoints are explicit.

### Top Concerns (by severity)

**HIGH**
1. **News alias matching quality (Plan 04)** — regex token extraction vs. DB-driven alias scan. D-11 expects `resolve_entity_by_alias` driven matching; current sketch is token-heuristic. Will miss Korean company names with particles/punctuation/nicknames.
2. **KIND source/protocol certainty (Plan 05)** — Wave-0 probe must land real endpoints; current plan has fallback paths that may drift from D-14 hybrid strategy.
3. **KRX entity completeness (Plan 02)** — watchlist tickers not yet seeded in `entities` may produce frontmatter without `corp_code`, weakening downstream joins.

**MEDIUM**
4. **Phase 3 regression coverage gap (Plan 01)** — `src/shared/frontmatter.py` and `src/ingest/heartbeat.py` are modified but only the import guard runs; existing Phase 3 collector/frontmatter/heartbeat tests should re-run after Task 3.
5. **Macro fail-fast semantics (Plan 03)** — plan text says "fail-fast" for empty ECOS responses, but `collect_macro` catches `MacroEmptyResultError` into `stats["failed"]`. Inconsistent.
6. **Observation merge semantics (Plan 03)** — `merge_observations` dedups by `date` only; revised values for same date silently overwrite, not documented.
7. **Weakly typed frontmatter fields (Plan 01)** — `tickers: list[dict]` and `observations: list[dict]` lack nested typed models (TickerRef, Observation).
8. **RSS/article fetch coupling (Plan 04)** — `trafilatura.fetch_url` used for both RSS XML and article HTML; should separate (requests for RSS, trafilatura for articles).

**LOW**
9. **Alias seeding precondition** — `seed_name_aliases.py` exists but nothing guarantees it runs before `collect_news`.
10. **Catalog path resolution (Plan 03)** — `.planning/macro_series.yaml` resolved repo-relative, brittle for non-repo execution contexts.
11. **Cross-URL dedup intentional duplication (Plan 04)** — should document as accepted Phase 4 tradeoff.
12. **Unused `engine` parameter in `collect_macro`** — keep for collector signature consistency or drop.

### Divergent Views

Not applicable — single reviewer.

### Suggested Next Actions
1. Strengthen Plan 04 news matching: pre-load scoped alias map, match against title + body, replace regex tokenization.
2. Add Phase 3 regression test gate to Plan 01 Task 3 (rerun existing collector tests after schema extension).
3. Clarify Plan 03 fail-fast vs. isolation semantics (choose one and align code + plan text).
4. Document observation merge strategy for revised same-date values.
5. Consider a cross-plan "Wave 0 verification bundle" deliverable prior to Wave 2 implementation.
