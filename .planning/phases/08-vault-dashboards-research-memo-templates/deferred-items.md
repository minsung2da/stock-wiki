# Phase 8 — Deferred Items (out-of-scope discoveries)

> Items discovered during plan execution that are NOT directly caused by the
> current plan's changes. Documented here for follow-up planning, not fixed
> in-line (SCOPE BOUNDARY rule).

## From Plan 08-05 (2026-05-09)

### vault/raw `_derived` schema drift beyond event_type

`uv run python -c "from shared.frontmatter import read_frontmatter; ..."` against
all 8 files in `vault/raw/` reveals additional drift unrelated to GAP-03/04:

1. **`_derived.numeric_facts` shape mismatch (DART × 2, KRX × 2, macro nfs vary)**
   - Vault data uses `{metric, value, unit, period}` quartet
   - `NumericFact` Pydantic schema (Phase 5) requires `{key, value, unit}` and forbids extras (`extra="forbid"`)
   - `unit` literal does not include `주`, `원` (Korean unit suffixes used by enrichment routine)

2. **`_derived.sentiment` shape mismatch**
   - Vault: bare string `bullish` / `neutral` / `bearish`
   - Schema: `SentimentBlock` dict (`{label, confidence}` etc.)

3. **`_derived._uncertain` field**
   - Present on KRX docs as a list, not in `DerivedBlock` schema (`extra="forbid"` rejects)

4. **`_derived` block missing `review_flags` on some files**
   - DART files lack `review_flags: []`; default factory should still cover, but extras may collide.

These are introduced by `.claude/routines/enrich/prompts/derived_*.md` not
matching the Pydantic schema established in Phase 5 D-08. **Resolution path:**
- Either tighten enrichment prompts to emit schema-conformant YAML, or
- Migrate Phase 5 schema to accept the actual enrichment shape.

**Recommended follow-up:** new Phase 8 plan or Phase-9 enrichment hardening
quick task — `260509-prompt-schema-realign`.

### enrich prompts vs production enum

`.claude/routines/enrich/prompts/derived_dart_b.md` and `derived_news.md` both
allow LLM to produce `event_type: other` correctly, but `derived_dart_b.md`
specifies enum subset that excludes some valid Phase 5 enums (e.g.,
`watchlist_designation`). Acceptable for now (LLM should fall back to `other`)
but worth tightening alongside the schema realignment above.
