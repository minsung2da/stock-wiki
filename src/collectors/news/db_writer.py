"""News article DB writer — Phase 1 Plan 01-06.

Replaces ``collectors.news.writer.write_news_doc`` (Markdown vault output) with
direct UPSERTs into the ``news`` Postgres table. One row per URL, dedup keyed
on the full ``url_hash`` (sha256 of the URL), content-hash diff drives the
inserted / updated / skipped outcome.

Design choices (RESEARCH Q1 §news, Q2 news):

  * **``url_hash`` (full sha256), not the v1.0 ``url_hash8`` prefix.** Collision
    probability at 8 hex chars over a multi-year corpus is not zero; the full
    digest is the safe natural key. ``client.url_hash64`` is the canonical
    helper.

  * **Load-then-classify** (same pattern as ``collectors.macro.db_writer``):
    SELECT the existing row's ``content_hash`` first, classify the outcome in
    Python, then execute the UPSERT. This makes the inserted/updated/skipped
    return value deterministic and matches the Phase 1 stats counter shape.

  * **``CAST(:tickers AS text[])`` ARRAY binding.** Pitfall #8 in RESEARCH.md:
    psycopg3 binds Python ``list[str]`` as JSON by default. The explicit
    ``CAST(:tickers AS text[])`` in the INSERT (with the list passed through
    bind params) forces the right adapter behavior. The ORM column type
    (``postgresql.ARRAY(sa.Text)`` in ``entity_models.News``) confirms the
    target type at introspection time.

  * **Naive datetimes coerced to UTC.** Postgres ``TIMESTAMPTZ`` rejects
    naive datetimes through psycopg3. RSS feeds occasionally surface naive
    pubDate values; we treat them as UTC so the writer never fails on a
    spec-noncompliant feed. Aware datetimes pass through unchanged.

  * **D-13 / D-24 enforcement is upstream.** The collector wraps the body
    with ``extract_first_two_paragraphs`` before calling this writer; the
    ``license_flag`` default ``'summary_only'`` is the table-level default
    declared in migration 0006 and overridable through the kwarg.

Hard Veto reminders:

  * **Veto #6** — ``news`` carries narrative columns only on the body side
    (``body_md``, ``body_tsv``, ``body_embedding``). All numeric/categorical
    columns are typed. This writer never embeds numeric data.

  * **Veto #8** — news bodies are short (2-paragraph cap upstream), so
    chunking is N/A here; we store the whole body in ``body_md``.

  * **Veto #9** — no Markdown is written by this module. Successful return
    means rows landed in Postgres; no filesystem writes occur.

SQL safety:

  * No f-string interpolation into SQL. All values flow through SQLAlchemy
    bind params. ``corp_code`` is regex-validated when present.
  * ``tickers`` list elements are not validated here — the collector layer's
    matcher (``matcher.match_tickers_in_text``) produces 6-digit ticker
    strings; an empty list is rejected as a precondition violation.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import text

from collectors.news.client import url_hash64
from shared.content_hash import normalize_body

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_CORP_CODE_RE = re.compile(r"^[0-9]{8}$")
_TICKER_RE = re.compile(r"^[0-9]{6}$")

__all__ = ["upsert_news_article"]


_SELECT_EXISTING_SQL = text("SELECT content_hash FROM news WHERE url_hash = :uh")

_BUMP_LAST_SEEN_SQL = text("UPDATE news SET last_seen_at = now() WHERE url_hash = :uh")

_UPSERT_SQL = text(
    """
    INSERT INTO news
      (url_hash, url, outlet, corp_code, tickers, published_at, title,
       content_hash, body_md, license_flag, fetched_at,
       first_seen_at, last_seen_at)
    VALUES
      (:url_hash, :url, :outlet, :corp_code, CAST(:tickers AS text[]),
       :published_at, :title, :content_hash, :body_md, :license_flag, now(),
       now(), now())
    ON CONFLICT (url_hash) DO UPDATE SET
        title = EXCLUDED.title,
        body_md = EXCLUDED.body_md,
        content_hash = EXCLUDED.content_hash,
        tickers = EXCLUDED.tickers,
        corp_code = EXCLUDED.corp_code,
        last_seen_at = now()
    """
)


def _normalize_published_at(dt: datetime) -> datetime:
    """Treat naive datetimes as UTC; pass aware datetimes through."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _compute_content_hash(title: str, body_md: str) -> str:
    """sha256 of normalized ``title\\nbody_md`` — survives whitespace edits.

    Mirrors the v1.0 ``writer.compute_news_content_hash`` shape so re-running
    the collector against the same URL is idempotent.
    """
    return hashlib.sha256(
        normalize_body(f"{title}\n{body_md}").encode("utf-8")
    ).hexdigest()


def upsert_news_article(
    engine: Engine,
    *,
    url: str,
    outlet: str,
    published_at: datetime,
    title: str,
    body_md: str,
    tickers: list[str],
    corp_code: str | None,
    license_flag: str = "summary_only",
) -> Literal["inserted", "updated", "skipped"]:
    """UPSERT one news article into the ``news`` table.

    Args:
        engine: SQLAlchemy Engine (psycopg3).
        url: canonical article URL — sha256 over the whitespace-stripped value
            becomes ``url_hash``.
        outlet: lower-case slug (``hankyung`` / ``edaily``); the collector
            pre-filters by ``detect_outlet`` so this is trusted.
        published_at: RSS ``pubDate`` mapped to TIMESTAMPTZ. Naive datetimes
            are coerced to UTC.
        title: article title (TEXT NOT NULL).
        body_md: 2-paragraph body (D-13 cap is enforced upstream by the
            collector's ``extract_first_two_paragraphs``).
        tickers: list of 6-digit ticker strings the collector matched against
            the title+body. Must be non-empty (precondition).
        corp_code: 8-digit DART corp code for the primary (first) matched
            ticker, or None if the entity is not seeded. FK ON DELETE SET NULL
            means deleting the entity preserves the news row.
        license_flag: D-24 publisher license flag — defaults to
            ``'summary_only'`` (the migration 0006 column default).

    Returns:
        ``"inserted"`` — no row existed for this ``url_hash``; new row written.
        ``"updated"``  — row existed, ``content_hash`` differs (body edited
                         after first fetch).
        ``"skipped"``  — row existed with the same ``content_hash``; only
                         ``last_seen_at`` is bumped.

    Raises:
        ValueError: ``tickers`` empty, ``corp_code`` shape invalid, or any
            element of ``tickers`` is not a 6-digit string.
    """
    if not tickers:
        raise ValueError("upsert_news_article: tickers must be non-empty")
    for t in tickers:
        if not _TICKER_RE.match(t):
            raise ValueError(
                f"upsert_news_article: invalid ticker shape (need 6 ASCII digits), got {t!r}"
            )
    if corp_code is not None and not _CORP_CODE_RE.match(corp_code):
        raise ValueError(
            f"upsert_news_article: invalid corp_code shape (need 8 ASCII digits or None), got {corp_code!r}"
        )

    uh = url_hash64(url)
    new_content_hash = _compute_content_hash(title, body_md)
    pub_at = _normalize_published_at(published_at)

    params = {
        "url_hash": uh,
        "url": url,
        "outlet": outlet,
        "corp_code": corp_code,
        "tickers": list(tickers),  # explicit list copy — psycopg3 bind safety
        "published_at": pub_at,
        "title": title,
        "content_hash": new_content_hash,
        "body_md": body_md,
        "license_flag": license_flag,
    }

    with engine.begin() as conn:
        existing = conn.execute(_SELECT_EXISTING_SQL, {"uh": uh}).first()
        if existing is None:
            outcome: Literal["inserted", "updated", "skipped"] = "inserted"
            conn.execute(_UPSERT_SQL, params)
        elif existing.content_hash == new_content_hash:
            # Skip path: do NOT clobber body / title / tickers (they may be the
            # same already, but the UPSERT would still rewrite first_seen_at
            # via DEFAULT). Only bump last_seen_at.
            conn.execute(_BUMP_LAST_SEEN_SQL, {"uh": uh})
            return "skipped"
        else:
            outcome = "updated"
            conn.execute(_UPSERT_SQL, params)

    return outcome
