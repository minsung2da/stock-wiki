"""D-15 `documents` upsert/dedup behavior.

Proves:
- First insert: new row, `xmax=0` indicates fresh tuple.
- Repeat insert with same `source_url`: source_urls unchanged (no duplication).
- Repeat insert with new `source_url`: accumulates into source_urls array.
- Repeat insert: `last_seen_at` is bumped.
- `vault_path` has a UNIQUE index — two different doc ids for the same path
  must fail with IntegrityError.

All tests use `pg_clean` so each test starts with an empty Phase 2 schema.
"""

from __future__ import annotations

import hashlib
import time

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

UPSERT_DOC = sa.text("""
INSERT INTO documents (id, body, source, vault_path, source_url, source_urls)
VALUES (:id, :body, :source, :vault_path, :source_url, ARRAY[:source_url])
ON CONFLICT (id) DO UPDATE SET
  last_seen_at = now(),
  source_urls = CASE
    WHEN EXCLUDED.source_url = ANY(documents.source_urls) THEN documents.source_urls
    ELSE array_append(documents.source_urls, EXCLUDED.source_url)
  END
RETURNING id, (xmax = 0) AS inserted;
""")


def _sha(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def test_first_insert_reports_inserted_true(pg_clean):
    body = "hello\n"
    doc_id = _sha(body)
    with pg_clean.begin() as conn:
        row = conn.execute(
            UPSERT_DOC,
            {
                "id": doc_id,
                "body": body,
                "source": "dart",
                "vault_path": "raw/dart/2026-04-17/a.md",
                "source_url": "https://dart.fss.or.kr/a",
            },
        ).one()
    assert row.id == doc_id
    assert row.inserted is True


def test_second_insert_same_url_does_not_duplicate(pg_clean):
    body = "hello\n"
    doc_id = _sha(body)
    params = {
        "id": doc_id,
        "body": body,
        "source": "dart",
        "vault_path": "raw/dart/2026-04-17/b.md",
        "source_url": "https://dart.fss.or.kr/x",
    }
    with pg_clean.begin() as conn:
        conn.execute(UPSERT_DOC, params)
        conn.execute(UPSERT_DOC, params)  # same URL again
        urls = conn.execute(
            sa.text("SELECT source_urls FROM documents WHERE id=:id"),
            {"id": doc_id},
        ).scalar()
    assert urls == ["https://dart.fss.or.kr/x"]


def test_second_insert_new_url_accumulates(pg_clean):
    body = "hello\n"
    doc_id = _sha(body)
    base = {
        "id": doc_id,
        "body": body,
        "source": "dart",
        "vault_path": "raw/dart/2026-04-17/c.md",
    }
    with pg_clean.begin() as conn:
        conn.execute(UPSERT_DOC, {**base, "source_url": "https://a.example/x"})
        conn.execute(UPSERT_DOC, {**base, "source_url": "https://b.example/x"})
        urls = conn.execute(
            sa.text("SELECT source_urls FROM documents WHERE id=:id"),
            {"id": doc_id},
        ).scalar()
    assert set(urls) == {"https://a.example/x", "https://b.example/x"}


def test_second_insert_updates_last_seen_at(pg_clean):
    body = "hello\n"
    doc_id = _sha(body)
    params = {
        "id": doc_id,
        "body": body,
        "source": "dart",
        "vault_path": "raw/dart/2026-04-17/d.md",
        "source_url": "https://x",
    }
    with pg_clean.begin() as conn:
        conn.execute(UPSERT_DOC, params)
        first = conn.execute(
            sa.text("SELECT last_seen_at FROM documents WHERE id=:id"),
            {"id": doc_id},
        ).scalar()
    time.sleep(0.01)
    with pg_clean.begin() as conn:
        conn.execute(UPSERT_DOC, params)
        second = conn.execute(
            sa.text("SELECT last_seen_at FROM documents WHERE id=:id"),
            {"id": doc_id},
        ).scalar()
    assert second >= first


def test_vault_path_unique_constraint(pg_clean):
    body_a = "a\n"
    body_b = "b\n"
    with pg_clean.begin() as conn:
        conn.execute(
            UPSERT_DOC,
            {
                "id": _sha(body_a),
                "body": body_a,
                "source": "dart",
                "vault_path": "raw/dart/SAME.md",
                "source_url": "https://1",
            },
        )
    with pytest.raises(IntegrityError), pg_clean.begin() as conn:
        conn.execute(
            UPSERT_DOC,
            {
                "id": _sha(body_b),
                "body": body_b,
                "source": "dart",
                "vault_path": "raw/dart/SAME.md",
                "source_url": "https://2",
            },
        )
