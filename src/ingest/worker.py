"""Ingest worker orchestration (INGEST-01, STORE-06, RET-02; D-25/26/27).

Composes the Wave 2 leaf utilities (parsers, chunking, embedder, tokenizer,
injection_defense) into the end-to-end ingest pipeline:

    scan <vault_root>/raw/**/*.md (vault_root defaults to repo root, D-01)
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

import contextlib
import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from db.entity import upsert_entity
from ingest.chunking import chunk_document
from ingest.edges import populate as edges_populate
from ingest.embedder import EMBEDDING_MODEL_VERSION, Embedder
from ingest.heartbeat import record_source_run
from ingest.injection_defense import detect_injection_patterns
from ingest.parsers import parse_sections
from ingest.parsers.note import parse_note
from ingest.tokenizer import tokenize_ko
from shared.content_hash import normalize_body
from shared.frontmatter import read_frontmatter, write_frontmatter

logger = logging.getLogger(__name__)

__all__ = ["process_document", "process_private_note", "ingest_run"]


def _is_private_note_path(path: Path, vault_root: Path) -> bool:
    """Detect ``notes/private/**/*.md`` by relative path under vault_root."""
    try:
        rel = path.resolve().relative_to(vault_root.resolve())
    except ValueError:
        return False
    parts = rel.parts
    return len(parts) >= 2 and parts[0] == "notes" and parts[1] == "private"


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
    fm_ticker = fm_model.provenance.ticker
    fm_company_name = fm_model.provenance.company_name

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

    # Bug D-1: re-seed entities from frontmatter so `ingest rebuild` (which
    # wipes entities/entity_aliases) restores ticker->corp_code resolution
    # using vault alone. Collector also calls upsert_entity (idempotent), so
    # this double-seed is safe. Best-effort: never fail a document ingest on
    # an entity seeding hiccup (mirrors collector's defense-in-depth).
    if corp_code:
        canonical_name = fm_company_name
        if canonical_name is None:
            with engine.connect() as conn:
                existing_name = conn.execute(
                    sa.text("SELECT canonical_name FROM entities WHERE corp_code = :cc"),
                    {"cc": corp_code},
                ).scalar()
            canonical_name = existing_name or f"corp_{corp_code}"
        with contextlib.suppress(Exception):  # seed is best-effort (D-1)
            upsert_entity(engine, corp_code, canonical_name, fm_ticker)

    # After commit: update zone 2 (ingest_state) and write back.
    fm_model.ingest_state.processed = True
    fm_model.ingest_state.processed_at = datetime.now(UTC)
    fm_model.ingest_state.embedding_model = EMBEDDING_MODEL_VERSION
    # Merge injection flags: union with previously-recorded flags so subsequent
    # runs preserve earlier detections even if patterns were removed from body.
    prior = set(fm_model.ingest_state.injection_flags or [])
    fm_model.ingest_state.injection_flags = sorted(prior | set(injection_flags))

    write_frontmatter(str(path), fm_model, body)

    return {
        "status": "processed",
        "doc_id": new_hash,
        "document_id": new_hash,
        "chunks": len(chunks),
    }


def process_private_note(
    path: Path,
    engine: Engine,
    embedder: Embedder,
    *,
    force_reembed: bool = False,
) -> dict[str, Any]:
    """Phase 8 D-15 — process a ``notes/private/**/*.md`` user memo.

    Dispatches via ``parse_note`` for type-specific Pydantic validation,
    inserts a documents row with ``source='private_note'`` and ``note_type``
    set to the parsed type. Validation failures still index the body but
    record ``note_schema_violation`` in ingest_state.review_flags.

    Per-doc transaction (D-26). No frontmatter write-back is attempted because
    private_note frontmatter does not embed an ``ingest_state`` zone.
    """
    parsed = parse_note(path)
    body = parsed.body
    note_type = parsed.note_type or "note"

    new_hash = hashlib.sha256(normalize_body(body).encode("utf-8")).hexdigest()

    # WR-01 (Phase 8): private_note frontmatter has no `ingest_state` zone, so
    # there is currently no place to persist injection_flags. Until a JSONB
    # column or audit table lands (tracked for Phase 9), skip the detection
    # call entirely rather than computing-and-discarding (the previous
    # `# noqa: F841 — recorded for parity` comment was misleading: nothing
    # was recorded).
    # TODO Phase 9: persist injection_flags on documents row + gate LLM extract.

    with engine.begin() as conn:
        existing = conn.execute(
            sa.text("SELECT id FROM documents WHERE vault_path = :vp"),
            {"vp": str(path)},
        ).first()

        if existing is not None and existing.id == new_hash and not force_reembed:
            return {"status": "skipped", "doc_id": new_hash}

        if existing is not None:
            conn.execute(
                sa.text("DELETE FROM documents WHERE vault_path = :vp"),
                {"vp": str(path)},
            )

        conn.execute(
            sa.text(
                "INSERT INTO documents "
                "(id, body, source, vault_path, note_type, "
                " first_seen_at, last_seen_at) "
                "VALUES (:id, :body, 'private_note', :vp, :nt, now(), now())"
            ),
            {
                "id": new_hash,
                "body": body,
                "vp": str(path),
                "nt": note_type,
            },
        )

        # Chunk + embed + tokenize so the memo lands in search results (NOTE-03).
        # Section parser is dart-only today; chunk the body as a single section
        # to keep parity with Phase 3 chunking semantics.
        from ingest.parsers.dart import Section

        sections = (
            [Section(title="body", path="body", text=body, order=0)]
            if body.strip()
            else []
        )
        chunks = chunk_document(sections) if sections else []

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

    return {
        "status": "processed",
        "doc_id": new_hash,
        "document_id": new_hash,
        "note_type": note_type,
        "review_flags": list(parsed.review_flags),
        "chunks": len(chunks),
    }


def ingest_run(
    vault_root: Path,
    engine: Engine,
    *,
    force_reembed: bool = False,
    embedder: Embedder | None = None,
) -> dict[str, Any]:
    """Scan `<vault_root>/raw/**/*.md` and ingest each document.

    Returns: ``{"total": int, "succeeded": int, "skipped": int, "failed": list}``.
    Per-document failure isolation: one bad doc never aborts the run (D-26).
    """
    if embedder is None:
        embedder = Embedder()

    stats: dict[str, Any] = {"total": 0, "succeeded": 0, "skipped": 0, "failed": []}
    committed_doc_ids: list[str] = []

    raw_root = vault_root / "raw"
    started_at = datetime.now(UTC)
    if raw_root.exists():
        for path in sorted(raw_root.rglob("*.md")):
            stats["total"] += 1
            try:
                result = process_document(path, engine, embedder, force_reembed=force_reembed)
                if result["status"] == "skipped":
                    stats["skipped"] += 1
                else:
                    stats["succeeded"] += 1
                # Track every committed document id (processed OR skipped — the
                # row is in `documents` either way and may need edge derivation).
                doc_id = result.get("document_id") or result.get("doc_id")
                if doc_id:
                    committed_doc_ids.append(doc_id)
            except Exception as exc:  # noqa: BLE001 — per-doc isolation (D-26)
                stats["failed"].append({"doc": str(path), "error": str(exc)[:200]})

    # Phase 8 NOTE-03 — private_note dispatch. Scan notes/private/**/*.md and
    # route through process_private_note (parse_note + documents.note_type).
    # Per-doc failure isolation (D-26) mirrors the raw branch above.
    private_root = vault_root / "notes" / "private"
    if private_root.exists():
        for path in sorted(private_root.rglob("*.md")):
            stats["total"] += 1
            try:
                result = process_private_note(
                    path, engine, embedder, force_reembed=force_reembed
                )
                if result["status"] == "skipped":
                    stats["skipped"] += 1
                else:
                    stats["succeeded"] += 1
                doc_id = result.get("document_id") or result.get("doc_id")
                if doc_id:
                    committed_doc_ids.append(doc_id)
            except Exception as exc:  # noqa: BLE001 — per-doc isolation
                stats["failed"].append({"doc": str(path), "error": str(exc)[:200]})

    # Phase 7 GRAPH-01 (D-03): post-pass typed-edge population.
    # Soft-fail per D-04: a buggy edge rule does NOT roll back doc commits.
    # Edge population runs in its OWN engine.begin() block, separate from the
    # per-doc transactions above — so an exception here cannot rewind the
    # already-committed documents/chunks rows.
    edges_counters: dict[str, Any] = {}
    try:
        with engine.begin() as conn:
            edges_counters = edges_populate(committed_doc_ids, conn)
    except Exception as exc:  # noqa: BLE001 — D-04 soft-fail
        edges_counters = {"error": str(exc)[:200]}
        logger.exception("edges.populate top-level failure")

    # Record an ingest_runs row for source='edges' so OPS observability sees it.
    # CONTEXT D-04 amendment 2026-05-05: counters land under JSONB sub-key
    # `stats["edges_warning"]` — there is no `extra` column on ingest_runs.
    edges_run_stats: dict[str, Any] = {
        "total": len(committed_doc_ids),
        "succeeded": int(edges_counters.get("inserted", 0) or 0),
        "skipped": int(edges_counters.get("skipped_conflict", 0) or 0),
        "failed": list(edges_counters.get("failed_per_type", {}).keys()),
        "edges_warning": edges_counters,
    }
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO ingest_runs "
                    "(started_at, finished_at, kind, source, stats, error) "
                    "VALUES (:s, :f, 'edges', 'edges', CAST(:stats AS JSONB), :err)"
                ),
                {
                    "s": started_at,
                    "f": datetime.now(UTC),
                    "stats": json.dumps(edges_run_stats, default=str),
                    "err": edges_counters.get("error"),
                },
            )
    except Exception:  # noqa: BLE001 — observability is best-effort
        logger.exception("failed to record ingest_runs row for edges")

    # Heartbeat: record edges as its own source row so health() and ingest doctor
    # see degraded state when failed_per_type is non-empty (D-05).
    # `extra=` here is the heartbeat-helper kwarg name (its own internal merging
    # key) — unrelated to any DB column.
    record_source_run(
        "edges",
        {
            "total": len(committed_doc_ids),
            "succeeded": int(edges_counters.get("inserted", 0) or 0),
            "skipped": int(edges_counters.get("skipped_conflict", 0) or 0),
            "failed": list(edges_counters.get("failed_per_type", {}).keys()),
        },
        heartbeat_path=vault_root / "ingested/_status/heartbeat.md",
        extra=edges_counters,
    )

    # Heartbeat (source='ingest'). Stats passed through unchanged; record_source_run
    # treats failed as list/int consistently.
    record_source_run(
        "ingest",
        stats,
        heartbeat_path=vault_root / "ingested/_status/heartbeat.md",
    )

    # Phase 8 D-01 — auto post-cycle hooks (best-effort, isolated).
    # Order: price_snapshot first (writes dashboards/_data/prices.md),
    # then hub_builder (may consume prices.md in future).
    # Failures here MUST NOT propagate — ingest must already be successful.
    # vault_root in this project is the repo root (raw/ lives under it),
    # so we pass it as both vault_root and repo_root.
    try:
        from ingest import price_snapshot
        price_snapshot.run(engine, repo_root=vault_root)
    except Exception:  # noqa: BLE001 — D-01 isolation
        logger.exception("Phase 8 price_snapshot hook failed")

    try:
        from ingest import hub_builder
        hub_builder.run(engine, vault_root=vault_root, repo_root=vault_root)
    except Exception:  # noqa: BLE001 — D-01 isolation
        logger.exception("Phase 8 hub_builder hook failed")

    return stats
