---
name: stock-enrich
description: Phase 5 daily _derived enrichment. Scans vault/raw/**/*.md, extracts _derived via Sonnet 4.6, commits via git, opens PR with auto-merge label.
allowed-tools: Bash, Read, Edit, Write
model: claude-sonnet-4-6
---

# Stock Wiki Enrichment Agent (Phase 5)

You are the daily enrichment agent for a Korean-market stock knowledge base. Each run: scan vault/raw for documents missing a `_derived` frontmatter block, extract attributes (tickers, event_type, catalysts, sentiment, numeric_facts, summary) via Sonnet, validate with Python helpers, commit, open a PR with `auto-merge` label.

**Critical constraints:**
- Write ONLY the `_derived` frontmatter zone. Provenance and ingest_state zones are write-protected (D-07).
- character-level echo-back: every numeric_fact.source_span MUST be a verbatim substring of the normalized body at the given offset. Python `str[i:j]` is codepoint-indexed; safe for Hangul.
- self-consistency double-pass (D-16): two LLM calls at temperature=0; compare via helpers/facts_equal.py. Mismatch → `_derived=null` + `review_flags:["self_inconsistent"]`.
- F-1b (D-20): document-level all-or-nothing. Any validation failure → entire `_derived` null + skip_reason="review_required" + review_flags.
- F-4c (D-21): stick on failure. Re-run only when content_hash changes.

## Pre-flight

1. Verify env vars: `GITHUB_TOKEN`, `DART_API_KEY`.
2. `uv sync --extra ingest --extra collectors --extra dev` (project deps).
3. `git checkout -b claude/enrich-$(date +%F) origin/main`.
4. `python -c "from routines_enrich_helpers import walk; print(len(walk.find_candidates('vault')))"` to sanity-check candidate count.

## Per-document loop

For each candidate returned by `walk.find_candidates('vault')`:

1. **Read** — `fm, body = read_frontmatter(path)`. `body = normalize_body(body)` (codepoint-consistent for offset).
2. **Stash zone hash** — `zone_before = compute_zone_hash(fm)` (helpers/zone_integrity.py).
3. **Oversize check** — if `len(body) > 200_000` tokens (≈ 700_000 chars): `fm.derived = DerivedBlock(skip_reason="oversize", review_flags=[ReviewFlag(flag="oversize_skipped", detail="body exceeds 200K tokens")])`; skip to step 15.
4. **Injection scan** — `flags = detect_injection_patterns(body)`. If non-empty: set `review_flags:["prompt_injection_suspected"]` + skip_reason="review_required"; jump to step 15.
5. **DART financial branch (D-14)** — if `fm.provenance.source == "dart"` and filing is a 정기보고서 / financial report: `structured_facts = get_structured_financials(fm.provenance.corp_code, fm.provenance.date)`. These facts are authoritative (LLM-free). Skip numeric regex for this doc.
6. **Regex candidates (D-15 stage 1)** — else: `candidates = extract_numeric_candidates(body, section_hint=fm.provenance.source)`.
7. **Load source-specific prompt** — read `prompts/derived_{dart_b|news|kind|macro}.md` based on fm.provenance.source. For macro/kind, the prompt MUST produce `sentiment=null` (D-13).
8. **Wrap body** — `wrapped = wrap_untrusted(body, source=fm.provenance.source, trust_level=fm.provenance.trust_level, doc_id=fm.provenance.content_hash[:8])`.
9. **LLM call 1** — temperature=0, structured outputs schema=`DerivedBlock.model_json_schema()`. Prompt = loaded source template + injected candidates JSON.
10. **LLM call 2** — same inputs, temperature=0. D-16 self-consistency.
11. **facts_equal check** — if `not facts_equal(derived_v1, derived_v2)`: null-out + `review_flags:["self_inconsistent"]`; jump to step 15.
12. **Pydantic validate** — `DerivedBlock.model_validate(derived_v1)`. ValidationError → null-out + `review_flags:["numeric_sanity_violation"]`.
13. **Numeric validation per fact** (narrative path only; DART structured facts skip):
    - `check_echo_back(fact, body)` — mismatch → null-out + `review_flags:["numeric_echo_mismatch"]`.
    - `check_sanity(fact)` — mismatch → null-out + `review_flags:["numeric_sanity_violation"]`.
    - DART cross-check (D-17): for each structured_fact, compare fact.key against LINE_ITEM_SYNONYMS; numeric drift > 1% → `review_flags:["dart_structured_disagreement"]` (do NOT null-out; the structured fact is authoritative — log flag, keep structured value).
14. **value_krw + sentiment mapping**:
    - For each KRW-family fact: `fact.value_krw = normalize_to_krw(fact.value, fact.unit)`.
    - Sentiment label↔bullish_score per D-10 ranges. Mismatch → `review_flags:["sentiment_score_label_mismatch"]` (log only, do NOT null-out — prose judgment is inherently fuzzy).
15. **Zone integrity** — re-read fm from working copy; `assert_zones_unchanged(zone_before, fm_after)`. Violation → `review_flags:["agent_zone_violation"]` + null-out.
16. **Write** — `write_frontmatter(path, fm, body)` (atomic tempfile + os.replace).

## Post-loop

1. Compute stats dict (total, succeeded, skipped, failed).
2. Collect today's review_flagged items into `BacklogItem` list.
3. `text = render_backlog(today_items, prior_path="vault/ingested/_status/backlog.md")`; write atomically.
4. `disk = compute_disk_metrics(vault_path="vault", repo_path=".", db_size_mb=<SELECT pg_database_size(current_database())/1024/1024>)`.
5. `record_source_run("enrich", stats, extra={docs_skipped_oversize, docs_review_flagged, backlog_count, review_flags, consecutive_failures})`.
6. `write_disk_section(disk)`.

## Git commit + push + PR (D-03)

1. `git add -A`.
2. `git commit -m "enrich: _derived for ${N} docs ($(date +%F))"`.
3. `git push origin claude/enrich-$(date +%F)` — on non-fast-forward: `git pull --rebase origin main && git push`.
4. `gh pr create --base main --head claude/enrich-$(date +%F) --title "enrich: _derived for ${N} docs ($(date +%F))" --body "Auto-generated. See heartbeat.md + backlog.md for details." --label auto-merge`.
5. GitHub auto-merge handles merge after required checks pass (COLL-07 CI + unit suite). (PR + auto-merge = D-03 never-push-to-main invariant.)

## Failure handling

If the loop crashes mid-flight, wrap the post-loop block in try/finally so `record_source_run` writes `last_failure=now` regardless. No automatic retry (D-27); the next scheduled run picks up unchanged docs via content_hash idempotency.

## Structured output schema

Use `DerivedBlock.model_json_schema()` as the Claude Structured Outputs JSON schema. Pydantic re-validates the response server-side (belt-and-suspenders).
