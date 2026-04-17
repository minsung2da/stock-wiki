"""Ingest worker orchestration (INGEST-01, STORE-06, RET-02; D-25/26/27).

Composes the Wave 2 leaf utilities (parsers, chunking, embedder, tokenizer,
injection_defense) into the end-to-end ingest pipeline:

    scan vault/raw/**/*.md
      -> read frontmatter + normalize body
      -> sha256 content-hash (new doc id)
      -> per-document transaction:
           - dedup: skip if doc id + embedding_model + processed flag unchanged
           - hash-change: delete old document + chunks rows (FK cascade)
           - parse sections (DART TOC or source-specific)
           - chunk_document -> Embedder.encode -> tokenize_ko per chunk
           - INSERT documents (incl. corp_code from fm.provenance — RET-02)
           - INSERT chunks (incl. embedding, bm25_tokens, section metadata)
      -> write back ingest_state zone only (STORE-06 zone integrity)
      -> record injection_flags from detect_injection_patterns (D-15 layer 3)
    record heartbeat (source='ingest') at end.

SQL discipline: zero f-string SQL. All user-sourced values flow through
SQLAlchemy `text()` + bind parameters (Phase 2 WR-03).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from ingest.chunking import chunk_document
from ingest.embedder import EMBEDDING_MODEL_VERSION, Embedder
from ingest.heartbeat import record_source_run
from ingest.injection_defense import detect_injection_patterns
from ingest.parsers import parse_sections
from ingest.tokenizer import tokenize_ko
from shared.content_hash import normalize_body
from shared.frontmatter import read_frontmatter, write_frontmatter

__all__ = ["process_document", "ingest_run"]


_INSERT_DOC_SQL = sa.text(
    "INSERT INTO documents "
    "(id, body, source, vault_path, source_url, source_urls, corp_code, "
    " first_seen_at, last_seen_at) "
    "VALUES (:id, :body, :source, :vp, :source_url, :source_urls, :corp_code, "
    " now(), now())"
)

_INSERT_CHUNK_SQL = sa.text(
    "INSERT INTO chunks "
    "(document_id, ord, text, embedding_model, embedding, "
    " section_path, section_index, bm25_tokens) "
    "VALUES (:doc_id, :ord, :text, :embedding_model, CAST(:emb AS vector), "
    " :section_path, :section_index, CAST(:toks AS int[]))"
)


def _format_vec(vec: list[float]) -> str:
    """Format a Python float list as a pgvector literal string ('[x,y,...]')."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def process_document(
    path: Path,
    engine: Engine,
    embedder: Embedder,
    *,
    force_reembed: bool = False,
) -> dict[str, Any]:
    """Process a single vault document. Per-doc transaction (D-26)."""
    fm_model, body = read_frontmatter(str(path))
    source = fm_model.provenance.source
    corp_code = fm_model.provenance.corp_code  # may be None (news, notes)

    # Content hash: sha256 of normalized body (D-13/D-14).
    new_hash = hashlib.sha256(normalize_body(body).encode("utf-8")).hexdigest()

    # Injection pattern scan (D-15 layer 3). Record to zone 2 regardless of dedup.
    hits = detect_injection_patterns(body)
    injection_flags = sorted({h["pattern_id"] for h in hits})

    with engine.begin() as conn:
        existing = conn.execute(
            sa.text("SELECT id FROM documents WHERE vault_path = :vp"),
            {"vp": str(path)},
        ).first()

        # Dedup short-circuit (INGEST-01 + D-27).
        if (
            existing is not None
            and existing.id == new_hash
            and not force_reembed
            and fm_model.ingest_state.processed
            and fm_model.ingest_state.embedding_model == EMBEDDING_MODEL_VERSION
        ):
            return {"status": "skipped", "doc_id": new_hash}

        # Hash changed OR force_reembed OR never processed:
        # delete existing document row (cascade deletes chunks via FK).
        if existing is not None:
            conn.execute(
                sa.text("DELETE FROM documents WHERE vault_path = :vp"),
                {"vp": str(path)},
            )

        # Insert documents row.
        source_url = fm_model.provenance.source_url
        source_urls = [source_url] if source_url else None
        conn.execute(
            _INSERT_DOC_SQL,
            {
                "id": new_hash,
                "body": body,
                "source": source,
                "vp": str(path),
                "source_url": source_url,
                "source_urls": source_urls,
                "corp_code": corp_code,
            },
        )

        # Parse -> chunk -> embed -> tokenize.
        sections = parse_sections(body, source)
        chunks = chunk_document(sections)

        texts = [c.text for c in chunks]
        if texts:
            vecs = embedder.encode(texts)
            bm25_lists = [tokenize_ko(t) for t in texts]
            for c, v, toks in zip(chunks, vecs, bm25_lists, strict=True):
                conn.execute(
                    _INSERT_CHUNK_SQL,
                    {
                        "doc_id": new_hash,
                        "ord": c.chunk_index,
                        "text": c.text,
                        "embedding_model": EMBEDDING_MODEL_VERSION,
                        "emb": _format_vec(list(v)),
                        "section_path": c.section_path,
                        "section_index": c.section_index,
                        "toks": toks,
                    },
                )

    # After commit: update zone 2 (ingest_state) and write back.
    fm_model.ingest_state.processed = True
    fm_model.ingest_state.processed_at = datetime.now(UTC)
    fm_model.ingest_state.embedding_model = EMBEDDING_MODEL_VERSION
    # Merge injection flags: union with previously-recorded flags so subsequent
    # runs preserve earlier detections even if patterns were removed from body.
    prior = set(fm_model.ingest_state.injection_flags or [])
    fm_model.ingest_state.injection_flags = sorted(prior | set(injection_flags))

    write_frontmatter(str(path), fm_model, body)

    return {"status": "processed", "doc_id": new_hash, "chunks": len(chunks)}


def ingest_run(
    vault_root: Path,
    engine: Engine,
    *,
    force_reembed: bool = False,
    embedder: Embedder | None = None,
) -> dict[str, Any]:
    """Scan vault/raw/**/*.md and ingest each document.

    Returns: ``{"total": int, "succeeded": int, "skipped": int, "failed": list}``.
    Per-document failure isolation: one bad doc never aborts the run (D-26).
    """
    if embedder is None:
        embedder = Embedder()

    stats: dict[str, Any] = {"total": 0, "succeeded": 0, "skipped": 0, "failed": []}

    raw_root = vault_root / "raw"
    if raw_root.exists():
        for path in sorted(raw_root.rglob("*.md")):
            stats["total"] += 1
            try:
                result = process_document(path, engine, embedder, force_reembed=force_reembed)
                if result["status"] == "skipped":
                    stats["skipped"] += 1
                else:
                    stats["succeeded"] += 1
            except Exception as exc:  # noqa: BLE001 — per-doc isolation (D-26)
                stats["failed"].append({"doc": str(path), "error": str(exc)[:200]})

    # Heartbeat (source='ingest'). Stats passed through unchanged; record_source_run
    # treats failed as list/int consistently.
    record_source_run(
        "ingest",
        stats,
        heartbeat_path=vault_root / "ingested/_status/heartbeat.md",
    )
    return stats
