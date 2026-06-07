"""notes-ingest db_writer — Plan 03-02 (D-05).

Single public function: ``upsert_note``.

Whole responsibility is one row in the ``notes`` table per ``path`` (the
repo-relative on-disk path of a ``notes/private/*.md`` thesis memo), with the
WHOLE memo stored verbatim in ``notes.content_md TEXT`` — **no pre-chunking**
(Hard Veto #8: one note row = one hybrid candidate, exactly like filings/news).

Embedding / BM25:
- ``content_emb halfvec(1024)`` is the bge-m3 narrative embedding (Veto #6 — only
  narrative is embedded; numbers never are; a note is narrative).
- ``bm25_tokens INT[]`` is the mecab-ko content-POS token id array.
- ``body_tsv`` is the SC#6 ``'simple'`` fallback tsvector — NEVER ``'korean'``
  (PG17 has no korean tsearch config; RESEARCH Pitfall 1). Korean morphology is
  carried by the mecab-ko → VectorChord-BM25 path, not Postgres tsearch.

Idempotency / change-detection (matches the dart/krx pattern):
- ``content_hash = sha256(normalize_body(content_md))`` (shared algorithm via
  ``shared.content_hash.normalize_body``).
- Load-then-classify: SELECT the existing content_hash; if it matches the
  computed hash, the call is idempotent (``"skipped"``) and nothing is rewritten
  — re-embedding an unchanged note would burn bge-m3 cycles for no gain.

SQL safety (Hard Veto #7):
- All values flow through SQLAlchemy bind params; no f-string interpolation.
- The single statement is a module-level ``text()`` constant.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Literal

from sqlalchemy import text

from shared.content_hash import normalize_body

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

__all__ = ["upsert_note", "format_halfvec_literal"]


# ON CONFLICT (path) DO UPDATE — re-ingest of a changed memo overwrites in place.
# body_tsv uses to_tsvector('simple', ...) — NEVER 'korean' (Pitfall 1).
# content_emb is bound as a halfvec literal string and CAST in SQL.
_UPSERT_SQL = text(
    """
    INSERT INTO notes
      (path, corp_code, content_md, content_hash, updated_at,
       body_tsv, content_emb, bm25_tokens)
    VALUES
      (:path, :corp_code, :content_md, :content_hash, now(),
       to_tsvector('simple', :content_md),
       CAST(:vec AS halfvec),
       :toks)
    ON CONFLICT (path) DO UPDATE SET
      corp_code    = EXCLUDED.corp_code,
      content_md   = EXCLUDED.content_md,
      content_hash = EXCLUDED.content_hash,
      updated_at   = now(),
      body_tsv     = EXCLUDED.body_tsv,
      content_emb  = EXCLUDED.content_emb,
      bm25_tokens  = EXCLUDED.bm25_tokens
    """
)

_SELECT_EXISTING_HASH_SQL = text("SELECT content_hash FROM notes WHERE path = :p")

_BUMP_UPDATED_AT_SQL = text("UPDATE notes SET updated_at = now() WHERE path = :p")


def format_halfvec_literal(vec: list[float] | tuple[float, ...]) -> str:
    """Format a Python float sequence as a pg(half)vec literal '[x,y,...]'.

    Ported from archive search_core._format_vec. The same textual literal works
    for both ``vector`` and ``halfvec`` columns via an explicit CAST in SQL.
    """
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def upsert_note(
    engine: Engine,
    *,
    path: str,
    content_md: str,
    embedding: list[float] | tuple[float, ...],
    bm25_tokens: list[int],
    corp_code: str | None = None,
) -> Literal["inserted", "updated", "skipped"]:
    """Upsert one ``notes`` row keyed on the repo-relative ``path``.

    Args:
        engine: SQLAlchemy engine (psycopg3).
        path: repo-relative path of the memo (e.g. ``notes/private/foo.md``). PK.
        content_md: WHOLE memo text. Stored verbatim — NO chunking (Veto #8).
        embedding: bge-m3 1024-d narrative vector for ``content_emb``.
        bm25_tokens: mecab-ko content-POS token id array for ``bm25_tokens``.
        corp_code: optional 8-digit DART corp code (FK, nullable). Notes are not
            required to reference a ticker.

    Returns:
        ``"inserted"`` — no prior row with this path; freshly written.
        ``"updated"``  — prior row existed; content changed (content_hash differs)
                         → re-embedded + rewritten.
        ``"skipped"``  — prior row existed with identical content_hash; only
                         ``updated_at`` bumped (no re-embed).
    """
    content_hash = hashlib.sha256(normalize_body(content_md).encode("utf-8")).hexdigest()
    params = {
        "path": path,
        "corp_code": corp_code,
        "content_md": content_md,
        "content_hash": content_hash,
        "vec": format_halfvec_literal(embedding),
        "toks": bm25_tokens,
    }

    with engine.begin() as conn:
        existing = conn.execute(_SELECT_EXISTING_HASH_SQL, {"p": path}).scalar()
        if existing is None:
            outcome: Literal["inserted", "updated", "skipped"] = "inserted"
        elif existing != content_hash:
            outcome = "updated"
        else:
            conn.execute(_BUMP_UPDATED_AT_SQL, {"p": path})
            return "skipped"
        conn.execute(_UPSERT_SQL, params)
    return outcome
