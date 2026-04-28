"""Snippet builder for MCP tool responses (D-08).

Prefers ``_derived.summary`` (Phase 5 enrichment) when present, else falls back
to the first ``SNIPPET_MAX_CHARS`` of the document body.

Output is wrapped in ``<vault_excerpt>...</vault_excerpt>`` XML delimiters so
downstream LLMs can distinguish the trusted system prompt from retrieved
vault content (D-08 / INGEST-09 trust boundary).

This wrapper is intentionally distinct from
``src.ingest.injection_defense.wrap_untrusted`` — that helper produces
``<untrusted source=... trust=... doc_id=...>`` which is correct for the search
tool (where we have full provenance), but Phase 6 tools may render snippets
without per-source attribution. The ``<vault_excerpt>`` form is the lighter
trust marker requested by the plan and the existing search citation contract
(see tests/e2e/test_search_citation_schema.py).
"""

from __future__ import annotations

__all__ = ["SNIPPET_MAX_CHARS", "build_snippet"]


SNIPPET_MAX_CHARS = 200


def build_snippet(body: str, derived_summary: str | None) -> str:
    """Return ``<vault_excerpt>...</vault_excerpt>`` wrapped snippet.

    Args:
        body: Untrusted document body. May be empty.
        derived_summary: Optional pre-extracted summary from
            ``_derived.summary`` (Phase 5). When present and non-empty, takes
            precedence over the body slice.

    Returns:
        XML-delimited snippet, ≤ ``SNIPPET_MAX_CHARS`` between the tags.
    """
    src = derived_summary if derived_summary else (body or "")
    trimmed = src[:SNIPPET_MAX_CHARS]
    return f"<vault_excerpt>{trimmed}</vault_excerpt>"
